#!/usr/bin/env bash
# apps/dma-insights/infra/verify-frontend-sha.sh
#
# Operator diagnostic: "why am I still seeing the old website?"
#
# Probes the live Cloud Run frontend URL and reports:
#   1. What SHA is stamped in the served /index.html
#   2. What revision is serving 100% traffic
#   3. What image SHA that revision is built from
#   4. Whether nginx is sending the right Cache-Control headers
#   5. Whether the SERVED SHA matches the operator's local HEAD
#
# If the served SHA doesn't match the operator expectation, this script
# prints the exact next-step command to force-promote + flush.
#
# Usage:
#   ./verify-frontend-sha.sh                    # expect HEAD = served
#   EXPECTED_SHA=abc1234 ./verify-frontend-sha.sh   # pin an expected SHA
#   ./verify-frontend-sha.sh --fix              # auto-promote if mismatch
#
# Exit codes:
#   0 → served SHA matches EXPECTED_SHA
#   1 → served SHA does NOT match (--fix not passed; or fix failed)
#   2 → frontend service / URL not resolvable
#   3 → served HTML has no <meta x-build-sha> tag (image too old)
set -euo pipefail

export GODEBUG=netdns=go

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
REGION="${REGION:-us-central1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
FRONTEND_SVC="${FRONTEND_SVC:-dma-insights-frontend}"
# Expect the NEWEST deploy-branch tip (read-only NO_SYNC), so a stale checkout
# can't make this verify the served bundle against an old SHA.
EXPECTED_SHA="${EXPECTED_SHA:-$(NO_SYNC=1 bash "$SCRIPT_DIR/resolve-deploy-sha.sh" 2>/dev/null || (git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true) | cut -c1-7)}"

DO_FIX=false
for arg in "$@"; do
  case "$arg" in
    --fix) DO_FIX=true ;;
    -h|--help)
      sed -n '1,30p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "::error::unknown flag: $arg" >&2; exit 1 ;;
  esac
done

if [[ -z "$PROJECT_ID" ]]; then
  echo "::error::PROJECT_ID unset" >&2
  exit 2
fi
if [[ -z "$EXPECTED_SHA" ]]; then
  echo "::error::EXPECTED_SHA unset and git HEAD unavailable" >&2
  exit 2
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Frontend served-SHA verifier                            ║"
echo "╠══════════════════════════════════════════════════════════╣"
printf "║  Service       : %-40s║\n" "$FRONTEND_SVC"
printf "║  Region        : %-40s║\n" "$REGION"
printf "║  EXPECTED_SHA  : %-40s║\n" "$EXPECTED_SHA"
echo "╚══════════════════════════════════════════════════════════╝"

# 1. Resolve URL + revision
FE_URL=$(gcloud run services describe "$FRONTEND_SVC" --region="$REGION" \
          --project="$PROJECT_ID" --format='value(status.url)' 2>/dev/null || true)
if [[ -z "$FE_URL" ]]; then
  echo "::error::no status.url on $FRONTEND_SVC — service not deployed" >&2
  exit 2
fi
echo ""
echo "→ Cloud Run state:"
echo "  URL: $FE_URL"

LATEST_REV=$(gcloud run services describe "$FRONTEND_SVC" --region="$REGION" \
              --project="$PROJECT_ID" \
              --format='value(status.latestReadyRevisionName)' 2>/dev/null)
SERVING_REV=$(gcloud run services describe "$FRONTEND_SVC" --region="$REGION" \
               --project="$PROJECT_ID" \
               --format='value(status.traffic[0].revisionName)' 2>/dev/null)
SERVING_PCT=$(gcloud run services describe "$FRONTEND_SVC" --region="$REGION" \
               --project="$PROJECT_ID" \
               --format='value(status.traffic[0].percent)' 2>/dev/null)
SERVING_IMG=$(gcloud run revisions describe "$SERVING_REV" --region="$REGION" \
               --project="$PROJECT_ID" \
               --format='value(spec.containers[0].image)' 2>/dev/null || true)
SERVING_IMG_SHA="${SERVING_IMG##*:}"

printf "  Serving rev : %s (%s%%)\n" "$SERVING_REV" "$SERVING_PCT"
printf "  Latest rev  : %s\n" "$LATEST_REV"
printf "  Image       : %s\n" "$SERVING_IMG"
printf "  Image SHA   : %s\n" "$SERVING_IMG_SHA"

# 2. Curl the served HTML
echo ""
echo "→ Served HTML probe:"
HTML=$(curl -s --max-time 15 "$FE_URL/" 2>/dev/null || true)
if [[ -z "$HTML" ]]; then
  echo "::error::curl returned empty body" >&2
  exit 2
fi
SERVED_SHA=$(printf '%s' "$HTML" \
              | grep -oE '<meta name="x-build-sha" content="[^"]+"' \
              | head -1 | sed -E 's/.*content="([^"]+)".*/\1/' || true)
if [[ -z "$SERVED_SHA" ]]; then
  echo "  ✗ <meta x-build-sha> MISSING in served HTML"
  echo "    Image $SERVING_IMG predates the SHA-stamping fix."
  echo "    Force rebuild: bash $SCRIPT_DIR/deploy-two-phase.sh"
  exit 3
fi
echo "  Served HTML stamped with SHA=$SERVED_SHA"

# 3. Cache-Control header check
HDR=$(curl -sI --max-time 10 "$FE_URL/" 2>/dev/null \
       | tr -d '\r' | grep -i '^cache-control:' || true)
if echo "$HDR" | grep -qi 'no-cache'; then
  echo "  ✓ Cache-Control: $(echo "$HDR" | sed 's/cache-control: //I')"
else
  echo "  ⚠ Cache-Control: ${HDR:-MISSING} (browser may cache index.html)"
fi

# 4. Verdict
echo ""
if [[ "$SERVED_SHA" == "$EXPECTED_SHA" ]]; then
  echo "✓ FRONTEND SERVES EXPECTED_SHA=$EXPECTED_SHA"
  echo "  If your browser still shows the old content, hard-refresh:"
  echo "    macOS: Cmd+Shift+R    Windows/Linux: Ctrl+Shift+R"
  echo "    Or open in incognito to bypass browser cache."
  exit 0
fi

echo "✗ MISMATCH: served=$SERVED_SHA expected=$EXPECTED_SHA"
echo ""
echo "Root-cause matrix:"
if [[ "$SERVING_IMG_SHA" == "$EXPECTED_SHA" ]]; then
  echo "  → image $SERVING_IMG IS the expected SHA, but the served HTML"
  echo "    stamps an older SHA. Likely the Cloud Run edge cache holds"
  echo "    an old /index.html. Cloud Run edge cache TTL is ~5 min."
  echo "    Fix: wait ~5 min, OR force-update the revision to bust the edge:"
  echo "      gcloud run services update $FRONTEND_SVC --region=$REGION \\"
  echo "        --update-env-vars=DMA_EDGE_BUST=\$(date +%s)"
elif [[ "$SERVING_IMG_SHA" != "$EXPECTED_SHA" ]]; then
  echo "  → image $SERVING_IMG is NOT the expected SHA. The new image"
  echo "    either wasn't built or wasn't deployed. Likely causes:"
  echo "      a) build was skipped (deploy was --skip-build but no prior image)"
  echo "      b) terraform apply / gcloud run update fired against the wrong tag"
  echo "      c) Phase 7 wasn't reached because an earlier phase errored"
  echo "    Fix: re-run a clean deploy:"
  echo "      bash $SCRIPT_DIR/deploy-two-phase.sh"
fi

if [[ "$SERVING_REV" != "$LATEST_REV" ]]; then
  echo "  → ALSO: serving rev ($SERVING_REV) is not the LATEST rev"
  echo "    ($LATEST_REV). Traffic is pinned to a prior revision."
  echo "    Fix: promote to LATEST:"
  echo "      gcloud run services update-traffic $FRONTEND_SVC \\"
  echo "        --region=$REGION --to-latest"
fi

if $DO_FIX; then
  echo ""
  echo "→ --fix passed: applying both the env-bust + traffic promote..."
  gcloud run services update "$FRONTEND_SVC" --region="$REGION" \
    --update-env-vars="DMA_EDGE_BUST=$(date +%s)" --quiet >/dev/null 2>&1 \
    && echo "  ✓ env-bump issued"
  gcloud run services update-traffic "$FRONTEND_SVC" --region="$REGION" \
    --to-latest --quiet >/dev/null 2>&1 \
    && echo "  ✓ traffic promoted to LATEST"
  echo "  Re-run this script in ~30s to confirm propagation."
fi

exit 1
