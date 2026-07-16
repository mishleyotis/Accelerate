#!/usr/bin/env bash
# Provision Cloud Memorystore for Redis end-to-end. Replaces the
# multi-step doc block in DEPLOYMENT.md §0.2.7 (Memorystore branch)
# that previously required the operator to paste 5+ separate commands,
# each with implicit $REGION / $PROJECT_ID / $REDIS_HOST dependencies.
# Paste fusion + missing-var bugs broke that flow repeatedly
# (2026-05-30 operator hit it: empty $REGION → instance never created
# → REDIS_HOST empty → REDIS_URL=redis://:6379/0).
#
# What this script does, idempotently and in order:
#   1. Validate $PROJECT_ID + $REGION (fail-fast if missing).
#   2. Reserve the /16 PSA range (`google-managed-services-default`)
#      — skipped if already present.
#   3. Establish the VPC peering to servicenetworking.googleapis.com
#      — skipped if already peered.
#   4. POLL `gcloud services vpc-peerings list` until the peering is
#      visible (replaces the fragile "wait ~30s" sleep — actual
#      observed convergence varies).
#   5. Create the Redis instance `dma-insights-redis` (basic tier,
#      1 GB, redis_7_0, PRIVATE_SERVICE_ACCESS) — skipped if it
#      already exists.
#   6. POLL until the instance reports state=READY.
#   7. Read `host` from the instance descriptor and build REDIS_URL.
#   8. Emit `export REDIS_URL=…` AND optionally write it to a
#      sourceable env file (`~/.dma-redis-url`) so the operator
#      can pick it up after the script exits (export inside a
#      subshell doesn't persist to the caller).
#
# Usage:
#   PROJECT_ID=… REGION=us-central1 \
#     bash apps/dma-insights/infra/setup-memorystore.sh
#
#   # Then source the env file the script wrote:
#   source ~/.dma-redis-url
#   echo "$REDIS_URL"
#
# Output:
#   On success the LAST line is `REDIS_URL=…` so the operator can
#   `eval $(bash setup-memorystore.sh | tail -1)` if they prefer.
set -euo pipefail
export GODEBUG=netdns=go

# ── Fail-fast on missing required vars ─────────────────────────────
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-}"
INSTANCE="${INSTANCE:-dma-insights-redis}"
NETWORK="${NETWORK:-default}"
PSA_RANGE="${PSA_RANGE:-google-managed-services-default}"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo 'FATAL: PROJECT_ID not set (and `gcloud config get-value project` returned nothing).' >&2
  echo '  Run:  gcloud config set project <PROJECT_ID>  OR  export PROJECT_ID=...' >&2
  exit 2
fi
if [[ -z "$REGION" ]]; then
  echo "FATAL: REGION not set (e.g. us-central1)." >&2
  echo "  Run:  export REGION=us-central1" >&2
  echo "  (Memorystore is regional, so the script can't guess — pass it explicitly.)" >&2
  exit 2
fi

echo "→ Memorystore setup"
echo "  PROJECT_ID = $PROJECT_ID"
echo "  REGION     = $REGION"
echo "  INSTANCE   = $INSTANCE"
echo "  NETWORK    = $NETWORK"

# ── Step 2: PSA range (idempotent) ──────────────────────────────────
echo ""
echo "[1/4] Ensure PSA range '$PSA_RANGE' exists"
if gcloud compute addresses describe "$PSA_RANGE" --global --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "  ✓ already exists — skipping create"
else
  echo "  → creating /16 PSA range..."
  gcloud compute addresses create "$PSA_RANGE" \
    --global --purpose=VPC_PEERING --prefix-length=16 \
    --network="$NETWORK" --project="$PROJECT_ID"
fi

# ── Step 3 + 4: VPC peering (idempotent + poll for convergence) ─────
echo ""
echo "[2/4] Ensure VPC peering to servicenetworking is established"
if gcloud services vpc-peerings list --network="$NETWORK" --project="$PROJECT_ID" \
     --format='value(peering)' 2>/dev/null \
     | grep -qx "servicenetworking-googleapis-com"; then
  echo "  ✓ peering already present"
else
  echo "  → connecting..."
  gcloud services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges="$PSA_RANGE" \
    --network="$NETWORK" --project="$PROJECT_ID"
fi

echo "  → polling until peering converges (up to 120s)"
ok=0
for _ in $(seq 1 24); do
  if gcloud services vpc-peerings list --network="$NETWORK" --project="$PROJECT_ID" \
       --format='value(peering)' 2>/dev/null \
       | grep -qx "servicenetworking-googleapis-com"; then
    ok=1; break
  fi
  sleep 5
done
if [[ "$ok" -ne 1 ]]; then
  echo "FATAL: VPC peering didn't converge after 120s." >&2
  echo "  Inspect:  gcloud services vpc-peerings list --network=$NETWORK --project=$PROJECT_ID" >&2
  exit 3
fi
echo "  ✓ peering converged"

# ── Step 5 + 6: Redis instance (idempotent + poll for READY) ────────
echo ""
echo "[3/4] Ensure Memorystore instance '$INSTANCE' exists in $REGION"
if gcloud redis instances describe "$INSTANCE" --region="$REGION" --project="$PROJECT_ID" \
     --format='value(name)' >/dev/null 2>&1; then
  echo "  ✓ instance already exists — skipping create"
else
  echo "  → creating (basic tier, 1 GB, redis_7_0, PRIVATE_SERVICE_ACCESS)..."
  # `gcloud redis instances create` blocks until the API returns a long-
  # running operation. The instance state then transitions
  # CREATING → READY over ~3-6 min — the loop below polls for it.
  gcloud redis instances create "$INSTANCE" \
    --size=1 \
    --region="$REGION" \
    --redis-version=redis_7_0 \
    --tier=basic \
    --connect-mode=PRIVATE_SERVICE_ACCESS \
    --network="$NETWORK" \
    --project="$PROJECT_ID"
fi

echo "  → polling until state=READY (up to 10 min)"
ready=0
for i in $(seq 1 60); do
  st="$(gcloud redis instances describe "$INSTANCE" \
        --region="$REGION" --project="$PROJECT_ID" \
        --format='value(state)' 2>/dev/null || true)"
  case "$st" in
    READY)
      ready=1; break ;;
    CREATING|UPDATING|MAINTENANCE|"")
      printf "  [%02d/60] state=%s — waiting 10s\n" "$i" "${st:-pending}"
      sleep 10 ;;
    *)
      echo "FATAL: unexpected state '$st' — investigate via Cloud Console" >&2
      exit 4 ;;
  esac
done
if [[ "$ready" -ne 1 ]]; then
  echo "FATAL: instance never reached state=READY within 10 minutes." >&2
  exit 4
fi
echo "  ✓ instance READY"

# ── Step 7 + 8: Read host + emit REDIS_URL ──────────────────────────
echo ""
echo "[4/4] Read instance host + emit REDIS_URL"
HOST="$(gcloud redis instances describe "$INSTANCE" \
        --region="$REGION" --project="$PROJECT_ID" \
        --format='value(host)')"
PORT="$(gcloud redis instances describe "$INSTANCE" \
        --region="$REGION" --project="$PROJECT_ID" \
        --format='value(port)')"
if [[ -z "$HOST" || -z "$PORT" ]]; then
  echo "FATAL: instance is READY but host/port came back empty — inspect via Cloud Console." >&2
  exit 5
fi
REDIS_URL="redis://${HOST}:${PORT}/0"
echo "  ✓ host=${HOST}  port=${PORT}"

# Persist to a sourceable file so the operator can pick it up after
# the script exits. ~/.dma-redis-url is gitignored-by-convention
# (it's outside the repo); operators source it with `source ~/.dma-
# redis-url`. Mode 0600 so the file isn't world-readable.
ENV_FILE="${HOME}/.dma-redis-url"
printf 'export REDIS_URL=%q\n' "$REDIS_URL" > "$ENV_FILE"
chmod 600 "$ENV_FILE" 2>/dev/null || true
echo "  ✓ wrote ${ENV_FILE} (run: source ${ENV_FILE})"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Memorystore ready. To pick up REDIS_URL in your current shell:"
echo "    source ${ENV_FILE}"
echo ""
echo "  Then verify (works from any directory inside the repo):"
echo '    bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-redis.sh"'
echo ""
echo "  This export line is also emitted on the LAST stdout line so you"
echo "  can shortcut: eval \$(bash setup-memorystore.sh | tail -1)"
echo "═══════════════════════════════════════════════════════════════"
# LAST line — easy to `tail -1` and eval.
echo "export REDIS_URL=${REDIS_URL}"
