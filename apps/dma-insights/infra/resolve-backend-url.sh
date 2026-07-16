#!/usr/bin/env bash
# apps/dma-insights/infra/resolve-backend-url.sh
#
# Resolves the LIVE Cloud Run backend URL (the one serving traffic) so
# downstream e2e / smoke / seed scripts can hit the real service
# instead of a localhost stub.
#
# Operator complaint (recurring): "For the backend tests, can you
# retrieve the real backend link and use it instead? These errors have
# been persistent. The deploy should provision the proper backend and
# get the right link that serves traffic."
#
# Contract:
#   - Idempotent: re-running prints the same URL.
#   - Self-healing on missing service: bails with the
#     `infra/deploy-two-phase.sh` instruction (the only operation that
#     creates the service).
#   - Self-healing on no-traffic-on-LATEST: prints the URL but warns +
#     returns exit-code 1 so the caller can route to
#     `infra/post-deploy-refresh.sh` (which promotes traffic).
#
# Usage:
#   ./resolve-backend-url.sh                   # prints URL to stdout, logs to stderr
#   ./resolve-backend-url.sh --export FILE     # also write `BACKEND_URL=<url>` to FILE
#   ./resolve-backend-url.sh --require-traffic # fail if traffic not 100% on LATEST
#
# Output (stdout): the bare URL, e.g. https://dma-insights-backend-xxx.run.app
# Output (stderr): human-readable progress.
#
# Exit codes:
#   0 → URL resolved + traffic 100% on LATEST (or --require-traffic absent)
#   1 → URL resolved BUT traffic not on LATEST (--require-traffic mode)
#   2 → service does not exist; operator must run deploy-two-phase.sh
#   3 → URL is empty (Cloud Run returned no status.url) — service is in
#       a half-deployed state
set -euo pipefail

REGION="${REGION:-us-central1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
BACKEND_SVC="${BACKEND_SVC:-dma-insights-backend}"

EXPORT_FILE=""
REQUIRE_TRAFFIC=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --export)           EXPORT_FILE="$2"; shift 2 ;;
    --require-traffic)  REQUIRE_TRAFFIC=true; shift ;;
    -h|--help)
      sed -n '1,30p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "::error::unknown flag: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$PROJECT_ID" ]]; then
  echo "::error::PROJECT_ID unset (gcloud config set project <id>)" >&2
  exit 2
fi

if ! gcloud run services describe "$BACKEND_SVC" --region="$REGION" \
       --project="$PROJECT_ID" --format='value(name)' >/dev/null 2>&1; then
  echo "::error::Cloud Run service '$BACKEND_SVC' not found in $REGION" >&2
  echo "         Run deploy-two-phase.sh first to provision it:" >&2
  echo "           bash apps/dma-insights/infra/deploy-two-phase.sh" >&2
  exit 2
fi

URL=$(gcloud run services describe "$BACKEND_SVC" --region="$REGION" \
        --project="$PROJECT_ID" --format='value(status.url)' 2>/dev/null || true)
if [[ -z "$URL" ]]; then
  echo "::error::service exists but status.url is empty — half-deployed state" >&2
  echo "         Inspect: gcloud run services describe $BACKEND_SVC --region=$REGION" >&2
  exit 3
fi

echo "→ resolved backend URL: $URL" >&2

# Check traffic split — operator may have deployed but never promoted.
LATEST_REV=$(gcloud run services describe "$BACKEND_SVC" --region="$REGION" \
              --project="$PROJECT_ID" \
              --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)
SERVING_REV=$(gcloud run services describe "$BACKEND_SVC" --region="$REGION" \
               --project="$PROJECT_ID" \
               --format='value(status.traffic[0].revisionName)' 2>/dev/null || true)
SERVING_PCT=$(gcloud run services describe "$BACKEND_SVC" --region="$REGION" \
               --project="$PROJECT_ID" \
               --format='value(status.traffic[0].percent)' 2>/dev/null || true)

if [[ "$SERVING_REV" == "$LATEST_REV" && "$SERVING_PCT" == "100" ]]; then
  echo "  ✓ 100% traffic on $LATEST_REV (LATEST)" >&2
else
  echo "  ⚠ traffic split: $SERVING_PCT% on $SERVING_REV (LATEST is $LATEST_REV)" >&2
  if $REQUIRE_TRAFFIC; then
    echo "::error::--require-traffic set; abort. Promote to LATEST:" >&2
    echo "         gcloud run services update-traffic $BACKEND_SVC \\" >&2
    echo "           --to-latest --region=$REGION" >&2
    echo "         OR run: bash apps/dma-insights/infra/post-deploy-refresh.sh" >&2
    printf '%s\n' "$URL"
    exit 1
  fi
fi

# Probe /readyz so callers know the URL serves a live (not booting) backend.
READY_HTTP=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 \
             "${URL%/}/readyz" 2>/dev/null || echo "000")
if [[ "$READY_HTTP" == "200" ]]; then
  echo "  ✓ /readyz returns 200" >&2
else
  echo "  ⚠ /readyz returned HTTP $READY_HTTP (URL still printed, but caller should investigate)" >&2
fi

if [[ -n "$EXPORT_FILE" ]]; then
  printf 'BACKEND_URL=%s\n' "$URL" > "$EXPORT_FILE"
  echo "  ✓ wrote BACKEND_URL=$URL to $EXPORT_FILE" >&2
fi

printf '%s\n' "$URL"
