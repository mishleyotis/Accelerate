#!/usr/bin/env bash
# apps/dma-insights/infra/preflight-cloud-sql.sh
#
# Verify the Cloud SQL instance is RUNNABLE; start it if STOPPED;
# wait until it is genuinely accepting connections. Idempotent + safe
# to run as a no-op when the instance is already up.
#
# 2026-06: added as part of the self-healing deploy contract. The
# recurring `/readyz` 503 failures the operator saw on b1da810 traced
# to Cloud SQL being momentarily unreachable (cold-start after the
# instance was idle-stopped, or a maintenance window). The previous
# deploy scripts assumed RUNNABLE forever and crashed on the very
# first gcloud sql describe call. This preflight makes the deploy
# resilient to:
#
#   - STOPPED   → start the instance + poll until RUNNABLE (≤5 min)
#   - PENDING_CREATE / PENDING_DELETE → fail fast (operator action)
#   - MAINTENANCE → wait up to 10 min then fail
#   - RUNNABLE   → no-op (this is the common case)
#   - any other state → log + best-effort proceed (deploy may still
#                       succeed if the instance recovers on its own)
#
# Permissions: requires `cloudsql.instances.get` (always needed) and
# `cloudsql.instances.update` (only when STOPPED → start). When the
# acting SA lacks update permission, we log a warning + return success
# so the deploy proceeds (the next gcloud sql call will get a clearer
# error than failing here).
#
# Exit codes:
#   0  → instance is RUNNABLE (or operator allowed continuation)
#   2  → instance is in a non-recoverable state (PENDING_DELETE, etc.)
#   3  → start timeout — instance never reached RUNNABLE within budget
#   4  → unable to describe the instance (wrong PROJECT_ID / INSTANCE
#        name / permissions); deploy should NOT proceed
#
# Usage:
#   ./preflight-cloud-sql.sh                       # uses defaults
#   ./preflight-cloud-sql.sh dma-insights-pg       # explicit instance
#   PROJECT_ID=foo INSTANCE=bar ./preflight-cloud-sql.sh
#   ./preflight-cloud-sql.sh --max-wait-sec 600    # extended wait

set -euo pipefail
_NF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "${_NF_DIR}/gcloud-noise-filter.sh" ] && . "${_NF_DIR}/gcloud-noise-filter.sh"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
INSTANCE="${INSTANCE:-${1:-dma-insights-pg}}"
MAX_WAIT_SEC="${MAX_WAIT_SEC:-300}"  # 5 min default

# Strip flag-style args; positional INSTANCE wins.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-wait-sec) MAX_WAIT_SEC="$2"; shift 2 ;;
    --project)      PROJECT_ID="$2"; shift 2 ;;
    --instance)     INSTANCE="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^set -e/p' "$0" | sed 's/^# \{0,1\}//; /^set -e/d'
      exit 0 ;;
    --) shift; break ;;
    -*) echo "Unknown flag: $1" >&2; exit 1 ;;
    *) INSTANCE="$1"; shift ;;
  esac
done

if [[ -z "$PROJECT_ID" ]]; then
  echo "::error::PROJECT_ID unset and no gcloud default project configured" >&2
  exit 4
fi

echo "→ preflight-cloud-sql: project=$PROJECT_ID instance=$INSTANCE"

# 1. Describe — fails fast if instance name / project / permissions
#    are wrong (no point in trying to start something we can't even read).
if ! STATE="$(gcloud sql instances describe "$INSTANCE" \
                --project="$PROJECT_ID" --format='value(state)' 2>/dev/null)"; then
  echo "::error::cannot describe Cloud SQL instance $INSTANCE in $PROJECT_ID" >&2
  echo "  Check:" >&2
  echo "    - instance name matches gcloud sql instances list" >&2
  echo "    - the acting SA has cloudsql.instances.get permission" >&2
  echo "    - the project ID is correct" >&2
  exit 4
fi
echo "  current state: $STATE"

# 2. Branch on state.
case "$STATE" in
  RUNNABLE)
    echo "  ✓ instance is RUNNABLE — no action needed"
    exit 0
    ;;
  STOPPED|SUSPENDED)
    echo "  ⟳ instance is $STATE — issuing start"
    if ! gcloud sql instances patch "$INSTANCE" \
           --project="$PROJECT_ID" \
           --activation-policy=ALWAYS \
           --quiet 2>&1 | head -5; then
      echo "::warning::could not start $INSTANCE (likely missing" \
           "cloudsql.instances.update permission); the deploy will" \
           "proceed and fail loudly on the next DB op if the" \
           "instance stays down" >&2
      exit 0
    fi
    ;;
  PENDING_CREATE)
    echo "::warning::instance is still PENDING_CREATE — polling for RUNNABLE"
    ;;
  PENDING_DELETE|FAILED)
    echo "::error::instance is $STATE — operator intervention required" >&2
    echo "  Use: gcloud sql instances list --filter=\"name:$INSTANCE\"" >&2
    exit 2
    ;;
  MAINTENANCE)
    echo "::warning::instance is in MAINTENANCE — polling for RUNNABLE"
    ;;
  *)
    echo "::warning::unrecognised state ($STATE) — best-effort poll"
    ;;
esac

# 3. Poll until RUNNABLE. Exponential backoff capped at 30s/iter.
echo "  → waiting up to ${MAX_WAIT_SEC}s for RUNNABLE state..."
start_ts=$(date +%s)
delay=5
while true; do
  STATE="$(gcloud sql instances describe "$INSTANCE" \
            --project="$PROJECT_ID" --format='value(state)' 2>/dev/null \
            || echo "UNREACHABLE")"
  if [[ "$STATE" == "RUNNABLE" ]]; then
    elapsed=$(($(date +%s) - start_ts))
    echo "  ✓ instance reached RUNNABLE after ${elapsed}s"
    exit 0
  fi
  elapsed=$(($(date +%s) - start_ts))
  if [[ $elapsed -ge $MAX_WAIT_SEC ]]; then
    echo "::error::timeout — instance still $STATE after ${elapsed}s" >&2
    echo "  The deploy will fail at the next DB op. Investigate via:" >&2
    echo "    gcloud sql operations list --instance=$INSTANCE --limit=5" >&2
    exit 3
  fi
  printf "  ... state=%s (waited %ss)\n" "$STATE" "$elapsed"
  sleep $delay
  # Exponential backoff capped at 30s — avoids spamming gcloud while
  # still re-polling reasonably often for the common 60-120s start.
  delay=$(( delay * 2 ))
  [[ $delay -gt 30 ]] && delay=30
done
