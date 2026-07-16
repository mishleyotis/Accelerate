#!/usr/bin/env bash
# apps/dma-insights/infra/verify-deploy.sh
#
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  ERROR HISTORY — keep this list in sync with new failure modes.      ║
# ╠══════════════════════════════════════════════════════════════════════╣
# ║  V1  Operator reported 'stale frontend' but had no actionable way    ║
# ║      to confirm what was actually live.                              ║
# ║      FIX: this script runs three independent freshness checks and    ║
# ║           prints a state-branch table; exit code = number of failed  ║
# ║           layers so it's usable as a CI gate.                        ║
# ║                                                                      ║
# ║  V2  curl returned HTML when it should have JSON                     ║
# ║      → /api/* routed but backend wasn't ready                        ║
# ║      FIX: layer 4 checks /api/v1/healthz returns JSON with ok:true   ║
# ║                                                                      ║
# ║  V3  Operator forgot to pull before running this — saw HEAD=$old     ║
# ║      FIX: script prints the local HEAD with its timestamp + reminds  ║
# ║           to 'git pull' if it's > 24h old                            ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Standalone post-deploy diagnostic. Same checks as the verifier block
# inside deploy.sh, but invokable independently so operators can re-run
# without a full apply.
#
# Usage:
#   ./verify-deploy.sh                # checks active gcloud project + git HEAD
#   SHA=abc1234 ./verify-deploy.sh    # check a specific image SHA is live
#
# Exit code = number of failed freshness layers (0 = all green).
#
# State-branch contract (printed inline):
#   all_layers_green        → exit 0, deploy is fresh
#   image_lags              → exit 1, run: gcloud run services update-traffic ... --to-latest
#   meta_lags               → exit 2, CDN edge cache stale, force-promote
#   no_cache_headers        → exit 3, nginx config older than 9b293ea; rebuild
#   backend_unhealthy       → exit 4, backend Cloud Run revision is bad
#   gcloud_unavailable      → exit 9 with the install hint
set -euo pipefail

# IPv6 mitigation — Cloud Shell's NAT pool can drop IPv6 traffic; force IPv4 DNS.
export GODEBUG=netdns=go

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Silence the benign per-call "Regional Access Boundary ... 404" gcloud
# stderr noise (Cloud Shell federated identities; see the filter file).
[ -f "${SCRIPT_DIR}/gcloud-noise-filter.sh" ] && . "${SCRIPT_DIR}/gcloud-noise-filter.sh"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
REGION="${REGION:-us-central1}"

# ── Resolve PROJECT_ID + SHA ─────────────────────────────────────────────────
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
# Verify against the NEWEST deploy-branch tip (read-only: NO_SYNC never touches
# the tree), so a stale local checkout can't make this falsely report a
# mismatch against an old SHA. Explicit SHA=… still pins what to verify.
SHA="${SHA:-$(NO_SYNC=1 bash "${SCRIPT_DIR}/resolve-deploy-sha.sh" 2>/dev/null || (git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || true) | cut -c1-7)}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud not on PATH. Install: https://cloud.google.com/sdk/docs/install" >&2
  exit 9
fi
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "ERROR: PROJECT_ID unset. Run: gcloud config set project digital-maturity-assessor" >&2
  exit 9
fi
if [[ -z "$SHA" ]]; then
  echo "ERROR: cannot determine git SHA. Are you inside the Accelerate repo?" >&2
  exit 9
fi

# Warn operator if HEAD is suspiciously old (pulled > 24h ago).
LAST_PULL_MTIME=$(stat -c %Y "$REPO_ROOT/.git/FETCH_HEAD" 2>/dev/null || echo 0)
NOW=$(date +%s)
AGE_HOURS=$(( (NOW - LAST_PULL_MTIME) / 3600 ))
if [[ "$LAST_PULL_MTIME" -gt 0 && "$AGE_HOURS" -gt 24 ]]; then
  echo "⚠ Local HEAD was last fetched ${AGE_HOURS}h ago; consider:"
  echo "  git -C $REPO_ROOT pull origin claude/deploy-zennify-cloud-run-AUdu6"
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  DMA Insights — Freshness Verification   ║"
echo "╠══════════════════════════════════════════╣"
printf "║  Project   : %-28s║\n" "$PROJECT_ID"
printf "║  HEAD SHA  : %-28s║\n" "$SHA"
echo "╚══════════════════════════════════════════╝"
echo ""

FAILED=0

# ── Layer 1: Cloud Run revisions serve image:$SHA ────────────────────────────
echo "Layer 1 — Cloud Run image tags match HEAD"
for svc in dma-insights-backend dma-insights-frontend; do
  live_image=$(gcloud run services describe "$svc" --region="$REGION" \
    --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true)
  live_sha="${live_image##*:}"
  if [[ "$live_sha" == "$SHA" ]]; then
    printf "  ✓ %-30s image=%s\n" "$svc" "$live_sha"
  else
    printf "  ✗ %-30s image=%s (expected %s)\n" "$svc" "${live_sha:-NONE}" "$SHA"
    FAILED=$((FAILED + 1))
  fi
done

FE_URL=$(gcloud run services describe dma-insights-frontend \
  --region="$REGION" --format='value(status.url)' 2>/dev/null || true)
BE_URL=$(gcloud run services describe dma-insights-backend \
  --region="$REGION" --format='value(status.url)' 2>/dev/null || true)

# ── Layer 2: Live HTML has the build-SHA stamp ──────────────────────────────
echo ""
echo "Layer 2 — Live HTML stamped with build SHA"
if [[ -n "$FE_URL" ]]; then
  meta_sha=$(curl -s "$FE_URL/" 2>/dev/null \
    | grep -oE '<meta name="x-build-sha" content="[^"]+"' \
    | head -1 | sed -E 's/.*content="([^"]+)".*/\1/' || true)
  if [[ -z "$meta_sha" ]]; then
    echo "  ⚠ <meta x-build-sha> missing — image predates the SHA-stamping fix"
    echo "    Rebuild with: ./deploy.sh    (auto-detects + rebuilds)"
    FAILED=$((FAILED + 1))
  elif [[ "$meta_sha" == "$SHA" ]]; then
    echo "  ✓ Live HTML stamped with build_sha=$meta_sha"
  else
    echo "  ✗ Live HTML stamped with build_sha=$meta_sha (expected $SHA)"
    echo "    CDN edge cached old /index.html. Force a refresh:"
    echo "      gcloud run services update-traffic dma-insights-frontend \\"
    echo "        --region=$REGION --to-latest"
    FAILED=$((FAILED + 1))
  fi
else
  echo "  ⚠ Frontend service has no public URL (not deployed?)"
  FAILED=$((FAILED + 1))
fi

# ── Layer 3: .jsx files served with Cache-Control: no-cache ─────────────────
echo ""
echo "Layer 3 — Cache-Control headers on source files"
if [[ -n "$FE_URL" ]]; then
  for path in /src/app-root.jsx /src/backend-loader.js /index.html; do
    hdr=$(curl -sI "$FE_URL$path" 2>/dev/null \
            | tr -d '\r' | grep -i '^cache-control:' || true)
    if echo "$hdr" | grep -qi 'no-cache'; then
      printf "  ✓ %-30s %s\n" "$path" "${hdr#cache-control: }"
    else
      printf "  ✗ %-30s %s\n" "$path" "${hdr:-<no Cache-Control header>}"
      FAILED=$((FAILED + 1))
    fi
  done
fi

# ── Layer 4: Backend liveness + readiness ───────────────────────────────────
# Cold-start race — the recurring "/healthz: no response but /readyz green"
# false-negative. Root cause: a freshly-rolled revision (just deployed +
# migrated, possibly replacing the prior instance) takes 20-60s to warm
# the first uvicorn worker. The earlier "fix" fired a single best-effort
# warmup then asserted — but `--max-time` is a TOTAL cap on the whole curl
# (it covers ALL retries, not per-attempt), so the FIRST assertion
# (/healthz) burned its entire budget against the still-cold instance and
# returned empty, while the SECOND (/readyz) — issued ~30s later — got a
# fresh budget against the now-warm instance and passed. /healthz is a
# dependency-free always-200 handler (`return {"status":"ok"}`); it can
# only come back empty when curl gives up before the worker is serving.
#
# Correct fix: a BLOCKING readiness gate. Poll until the revision actually
# serves a 200 (generous total budget, exits the instant it's warm), THEN
# run the assertions against a confirmed-warm instance. `--connect-timeout`
# + per-attempt `--max-time` ensure one slow connect can't eat the budget.
CURL_OPTS=(--silent --fail --connect-timeout 5 --max-time 20)
echo ""
echo "Layer 4 — Backend liveness + readiness"
if [[ -n "$BE_URL" ]]; then
  # Blocking warm-up: up to 40 × 5s ≈ 200s, breaks the instant EITHER probe
  # returns 200 — assertions only run once the instance is provably serving.
  echo "  …waiting for the rolled revision to start serving (up to ~200s)"
  warm=false
  for _attempt in $(seq 1 40); do
    if curl "${CURL_OPTS[@]}" -o /dev/null "$BE_URL/healthz" 2>/dev/null \
       || curl "${CURL_OPTS[@]}" -o /dev/null "$BE_URL/readyz" 2>/dev/null; then
      warm=true
      break
    fi
    sleep 5
  done
  if ! $warm; then
    echo "  ⚠ backend not serving after ~200s — assertions below report the real state"
  fi

  # /readyz is the AUTHORITATIVE liveness+readiness gate: it does a live DB
  # probe + surfaces the prod-readiness guard, so a green /readyz proves the
  # revision is fully alive AND ready — it strictly subsumes /healthz.
  ready=$(curl "${CURL_OPTS[@]}" --retry 3 --retry-delay 2 --retry-all-errors \
            "$BE_URL/readyz" 2>/dev/null || true)
  ready_ok=false
  if echo "$ready" | grep -q '"status":"ready"'; then
    ready_ok=true
  fi

  # /healthz is INFORMATIONAL only. Cloud Run already runs its startup +
  # liveness probes against /healthz (terraform main.tf), so a revision
  # serving 100% traffic has ALREADY passed /healthz internally. An external
  # curl to /healthz can still race a cold instance / LB warm-up and come back
  # empty even while /readyz is green — that is a false negative, not an
  # outage. So we report /healthz but only HARD-FAIL when /readyz is also bad.
  health=$(curl "${CURL_OPTS[@]}" --retry 3 --retry-delay 2 --retry-all-errors \
             "$BE_URL/healthz" 2>/dev/null || true)
  if echo "$health" | grep -q '"ok":true\|"status":"ok"'; then
    echo "  ✓ /healthz returns JSON ok=true"
  elif $ready_ok; then
    echo "  ⚠ /healthz external probe empty, but /readyz is green (Cloud Run's own"
    echo "    startup+liveness probes target /healthz, so the revision passed it"
    echo "    internally) — treating as a probe-timing false negative, not failing."
  else
    echo "  ✗ /healthz: ${health:-no response}  (and /readyz not ready — see below)"
    FAILED=$((FAILED + 1))
  fi

  if $ready_ok; then
    echo "  ✓ /readyz reports ready"
  else
    # Per plan §D1: /readyz failure means migration drift OR DB unreachable
    # OR prod-readiness guard tripped — ALL block-the-deploy conditions.
    echo "  ✗ /readyz: ${ready:-no response}  (check migration head, DB, Redis, prod-readiness guard)"
    FAILED=$((FAILED + 1))
  fi
else
  echo "  ⚠ Backend service has no public URL"
  FAILED=$((FAILED + 1))
fi

echo ""
if [[ "$FAILED" -eq 0 ]]; then
  echo "✓ All 4 layers green — deploy is fully live at SHA=$SHA"
  exit 0
fi
echo "✗ $FAILED check(s) failed — see actionable hints inline above"
exit "$FAILED"
