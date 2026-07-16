#!/usr/bin/env bash
# apps/dma-insights/infra/recover-db-passwords.sh
#
# Self-heal Cloud SQL password drift.
#
# Symptom this fixes:
#   psycopg.OperationalError: FATAL: password authentication failed for
#     user "postgres" (or "dma_insights")
#   /readyz returns {"status":"degraded","db":"down: InvalidPasswordError"}
#
# Root cause:
#   Terraform owns the canonical passwords via `random_password.db_*` and
#   pushes them to the SQL users via `null_resource.db_*_setup`
#   provisioners. The secrets `dma-insights-database-url{,-superuser}`
#   embed those same passwords.
#
#   When someone (a prior recovery script, a manual `gcloud sql users
#   set-password`, a Cloud SQL outage that wiped credentials) changes the
#   SQL user's password OUT-OF-BAND, the system drifts:
#     - Secret still has the Terraform-managed password (X)
#     - SQL user has the out-of-band password (Y)
#     - Apps load the secret → try X → SQL says "wrong password" → 503
#
# Cloud Run secret caching:
#   Cloud Run resolves `version = "latest"` at container start. Running
#   service containers KEEP the resolved value for their lifetime — so
#   even after the secret is updated, the live revision still serves
#   the old value until a new revision starts. This script forces a
#   no-op env var change ("DMA_SECRET_ROLL=<timestamp>") that triggers
#   fresh revisions on the backend service + workers so they re-read.
#
# Resilience:
#   - Disables IPv6 at kernel level (Cloud Shell NAT pool workaround)
#   - Wraps terraform apply with escalating-parallelism retry (10 → 4 → 2 → 1)
#   - Forces Cloud Run revisions to roll so secrets are re-read
#
# Usage:
#   ./recover-db-passwords.sh                 # heal drift; keep current passwords
#   ./recover-db-passwords.sh --rotate        # FRESH passwords end-to-end (bulletproof)
#   ./recover-db-passwords.sh --verify-only   # just check; no changes
#   ./recover-db-passwords.sh --diagnose      # dump secret + revision state for debugging
#
# SHA semantics (heal + --rotate modes):
#   `terraform apply` evaluates the three
#   `data "google_artifact_registry_docker_image"` blocks during planning,
#   so $SHA must point at a tag whose images exist in gcr.io. Resolution
#   priority: explicit $SHA > /tmp/dma-insights-deploy-sha (set by
#   build.sh) > deployed Cloud Run backend revision SHA > git HEAD. The
#   "deployed revision" default is the right answer for standalone
#   recovery — Cloud Run wouldn't be running an image that doesn't
#   exist. If the resolved SHA has no images, the script auto-builds
#   them inline via `gcloud builds submit` (~10-15 min) before applying.
set -euo pipefail

# ── IPv6 mitigation (Cloud Shell NAT pool flake) ────────────────────────────
export GODEBUG=netdns=go
if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1 >/dev/null 2>&1 || true
  sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1 >/dev/null 2>&1 || true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${SCRIPT_DIR}/terraform"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

MODE="heal"
case "${1:-}" in
  --rotate) MODE="rotate" ;;
  --verify-only) MODE="verify" ;;
  --diagnose) MODE="diagnose" ;;
  --help|-h)
    grep '^#' "$0" | sed 's/^# \?//' | head -50
    exit 0
    ;;
esac

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-us-central1}"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "ERROR: PROJECT_ID unset. Run: gcloud config set project digital-maturity-assessor" >&2
  exit 1
fi

# ── SHA resolution (priority chain) ─────────────────────────────────────────
# Why this matters: `terraform apply` evaluates the three
# `data "google_artifact_registry_docker_image"` blocks (backend, frontend,
# workers) during planning. If $SHA points at a tag that doesn't have built
# images in gcr.io, the apply fails on EVERY retry with `Requested image
# was not found` — regardless of which resources are being changed.
#
# This script runs in two contexts with very different "correct SHA" semantics:
#
#   (a) During `deploy-two-phase.sh` Phase 3 → caller already built images
#       in Phase 1 at the deploy SHA. That SHA is written to
#       `/tmp/dma-insights-deploy-sha` so we can pick it up here.
#
#   (b) Standalone recovery — operator just wants to rotate the DB password
#       on the CURRENTLY-DEPLOYED app. The deployed Cloud Run revision's
#       image SHA is the right default; git HEAD may be ahead (operator
#       made doc-only commits since deploy) or behind (operator checked
#       out an older branch). The deployed revision's image is GUARANTEED
#       to exist in gcr.io because Cloud Run wouldn't be running it
#       otherwise — using it makes the apply succeed without a re-build.
#
# Priority chain:
#   1. Explicit $SHA env (operator was explicit; trust them but verify
#      images exist below; auto-build if missing).
#   2. /tmp/dma-insights-deploy-sha (deploy-two-phase handoff).
#   3. Deployed Cloud Run backend revision's image SHA (recovery default).
#   4. git HEAD (developer / first-deploy fallback).
#
# 2026-05-29 fix — pinned by test_recover_db_passwords_resolves_sha_from_deployed_revision.
_sha_from_deployed_revision() {
  # Read the backend service's image URI, e.g.
  # `gcr.io/digital-maturity-assessor/dma-insights-backend:9aafdc1` and
  # return the tag after the last `:`. Empty if service doesn't exist.
  local img
  img="$(gcloud run services describe dma-insights-backend \
         --region="$REGION" --project="$PROJECT_ID" \
         --format='value(spec.template.spec.containers[0].image)' \
         2>/dev/null || true)"
  if [[ -z "$img" ]]; then return 0; fi
  # Strip everything up to and including the last `:` to keep just the tag.
  printf '%s\n' "${img##*:}"
}

_sha_source="explicit"
if [[ -z "${SHA:-}" ]]; then
  # Prefer the image ACTUALLY deployed (the password roll must target the
  # running image), then the NEWEST deploy-branch tip, then the build handoff,
  # then HEAD. The stale-prone /tmp handoff no longer outranks the live
  # revision — a leftover /tmp/dma-insights-deploy-sha from a prior deploy used
  # to make the roll target an old image (a contributor to the bde8329 issue).
  SHA="$(_sha_from_deployed_revision)"
  _sha_source="deployed-revision"
  if [[ -z "$SHA" ]]; then
    SHA="$(NO_SYNC=1 bash "$SCRIPT_DIR/resolve-deploy-sha.sh" 2>/dev/null || true)"
    _sha_source="deploy-branch-tip"
  fi
  if [[ -z "$SHA" && -f /tmp/dma-insights-deploy-sha ]]; then
    SHA="$(cat /tmp/dma-insights-deploy-sha)"
    _sha_source="deploy-handoff"
  fi
  if [[ -z "$SHA" ]]; then
    SHA="$( (git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true) | cut -c1-7 )"
    _sha_source="git-head"
  fi
fi

if [[ -z "$SHA" ]] && [[ "$MODE" != "verify" ]] && [[ "$MODE" != "diagnose" ]]; then
  echo "ERROR: SHA could not be resolved. Either:" >&2
  echo "  - export SHA=\$(git rev-parse --short HEAD)" >&2
  echo "  - or deploy a Cloud Run revision first" >&2
  exit 1
fi

if [[ -n "$SHA" ]]; then
  echo "→ SHA=$SHA (resolved via: $_sha_source)"
fi

# ── Image preflight: ensure all 3 images exist at $SHA ──────────────────────
# Why: `terraform apply` evaluates the three `data
# "google_artifact_registry_docker_image"` blocks during planning. If any
# is missing at $SHA, every retry fails identically with `Requested image
# was not found` — exhausting the parallelism-escalation loop without
# making progress.
#
# Recovery: build all 3 via Cloud Build. The cloudbuild.yaml builds all
# three in one job. ~10-15 minutes; we do it inline rather than abort so
# the operator gets a working end-to-end recovery from a single command
# (no "now run gcloud builds submit ... and re-invoke me").
#
# Skip-fast path: if the SHA was resolved from the deployed revision,
# images are guaranteed to exist (Cloud Run wouldn't be running them
# otherwise) — skip the gcloud describe calls. Verify in all other cases.
ensure_images_built() {
  if [[ "$_sha_source" == "deployed-revision" ]]; then
    echo "  ✓ images for $SHA are present (running in deployed revision)"
    return 0
  fi
  local missing=()
  local img
  for img in dma-insights-backend dma-insights-frontend dma-insights-workers; do
    if ! gcloud container images describe \
         "gcr.io/${PROJECT_ID}/${img}:${SHA}" \
         --project="$PROJECT_ID" --format=json >/dev/null 2>&1; then
      missing+=("${img}")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    echo "  ✓ all 3 images present at gcr.io/${PROJECT_ID}/...:${SHA}"
    return 0
  fi
  echo "  ⚠ ${#missing[@]} image(s) missing at SHA ${SHA}: ${missing[*]}"
  echo "  → building images via Cloud Build (~10-15 minutes)..."
  echo "    gcloud builds submit --config ${SCRIPT_DIR}/cloudbuild.yaml \\"
  echo "      --substitutions=_IMAGE_SHA=${SHA} --region ${REGION} ${SCRIPT_DIR}/.."
  if ! gcloud builds submit \
       --config "${SCRIPT_DIR}/cloudbuild.yaml" \
       --substitutions=_IMAGE_SHA="${SHA}" \
       --region "${REGION}" \
       "${SCRIPT_DIR}/.." ; then
    echo "  ✗ Cloud Build failed at SHA ${SHA}. Cannot proceed with terraform apply." >&2
    echo "    Inspect logs above; fix the build, then re-run this script." >&2
    return 1
  fi
  # Re-verify all 3 now exist.
  for img in dma-insights-backend dma-insights-frontend dma-insights-workers; do
    if ! gcloud container images describe \
         "gcr.io/${PROJECT_ID}/${img}:${SHA}" \
         --project="$PROJECT_ID" --format=json >/dev/null 2>&1; then
      echo "  ✗ image ${img}:${SHA} still missing after build — likely a tag mismatch in cloudbuild.yaml" >&2
      return 1
    fi
  done
  echo "  ✓ all 3 images built + verified at gcr.io/${PROJECT_ID}/...:${SHA}"
}

# ── Diagnose mode: dump secret + revision state, then exit ──────────────────
if [[ "$MODE" == "diagnose" ]]; then
  echo "=== Secret versions ==="
  for s in dma-insights-database-url dma-insights-database-url-superuser; do
    echo "--- $s ---"
    gcloud secrets versions list "$s" --format='table(name,state,createTime)' 2>/dev/null || echo "  (not found)"
  done

  echo ""
  echo "=== Last 4 chars of password embedded in each secret (latest version) ==="
  for s in dma-insights-database-url dma-insights-database-url-superuser; do
    val="$(gcloud secrets versions access latest --secret="$s" 2>/dev/null | sed -nE "s#^postgresql\\+(asyncpg|psycopg)://[^:]+:([^@]+)@.*#\\2#p" || true)"
    if [[ -n "$val" ]]; then
      tail4="${val: -4}"
      echo "  $s → ...$tail4 (len=${#val})"
    else
      echo "  $s → (couldn't parse)"
    fi
  done

  echo ""
  echo "=== Migrations job env var (which secret version it points at) ==="
  gcloud run jobs describe dma-insights-migrations --region="$REGION" \
    --format='yaml(template.template.containers[0].env)' 2>/dev/null \
    || echo "  (job not found)"

  echo ""
  echo "=== Backend service env var (DATABASE_URL) ==="
  gcloud run services describe dma-insights-backend --region="$REGION" \
    --format='yaml(spec.template.spec.containers[0].env)' 2>/dev/null \
    | grep -A 5 "DATABASE_URL" || echo "  (backend not found)"

  echo ""
  echo "=== Last 2 migrations job executions ==="
  gcloud run jobs executions list \
    --job=dma-insights-migrations --region="$REGION" --limit=2 \
    --format='table(name,creationTimestamp,completionStatus,statusMessage)' \
    2>/dev/null || echo "  (no executions)"

  echo ""
  echo "Done. If secrets show different tail-4 chars across runs, the secret"
  echo "was rotated between attempts. If migrations job env points at a"
  echo "specific version (not 'latest'), force a revision roll via:"
  echo "    gcloud run jobs update dma-insights-migrations --region="$REGION" \\"
  echo "      --update-env-vars=DMA_SECRET_ROLL=\$(date +%s)"
  exit 0
fi

cd "$TF_DIR"

# Initialise backend if state isn't reachable yet (idempotent, ~3s).
# 2026-06 deployment hardening: when MODE==verify the script only needs
# Secret Manager + a Cloud SQL connection — terraform isn't required
# at all. The original `terraform init` precondition was failing on
# Cloud Build runners where the GCS backend bucket ACL excludes the
# build SA, blocking migrations behind a "re-run ./deploy.sh first"
# error that the operator can't actually act on. Make terraform init
# non-fatal in verify mode (the verify path uses Secret Manager
# directly, identical to force-heal-db.sh). In heal/rotate modes
# terraform IS required to manage state, so failure there still aborts.
if ! terraform init -reconfigure \
       -backend-config="bucket=${PROJECT_ID}-tfstate" \
       -input=false >/dev/null 2>&1; then
  if [[ "$MODE" == "verify" ]]; then
    echo "  ⚠ terraform init unavailable — falling back to Secret-Manager-only verify"
    echo "    (this is fine for --verify-only; heal/rotate would still need terraform)"
  else
    echo "ERROR: terraform init failed; cannot perform heal/rotate without state." >&2
    echo "  --verify-only still works (skips terraform). To diagnose state access:" >&2
    echo "    gsutil ls gs://${PROJECT_ID}-tfstate" >&2
    echo "  If the bucket is unreachable, recover via Secret-Manager-as-truth instead:" >&2
    echo "    $(dirname "$0")/force-heal-db.sh" >&2
    exit 1
  fi
fi

# ── Verify connection BEFORE healing ─────────────────────────────────────────
verify_password() {
  local user="$1"
  local secret_name="$2"
  local dsn
  dsn="$(gcloud secrets versions access latest --secret="$secret_name" 2>/dev/null || true)"
  if [[ -z "$dsn" ]]; then
    echo "  ⚠ secret $secret_name is empty"; return 1
  fi

  # Extract BOTH the user and password from the DSN. The DSN shape is
  #   postgresql+(asyncpg|psycopg)://<user>:<pw>@/<db>?host=...
  # IMPORTANT: do NOT interpolate the expected `${user}` into the regex.
  # An out-of-band secret version can carry a DIFFERENT user (e.g. an
  # operator's first deploy created `dma_insights_app` while Terraform's
  # convention is `dma_insights`). Hardcoding `://dma_insights:` then
  # fails to match `://dma_insights_app:` and the verify reports a false
  # "regex mismatch" even though the credential pair is internally
  # consistent. Extract the user generically + connect AS the DSN's user
  # so the check reflects whether the SECRET's credential actually works.
  # (2026-05-29 fix.) Use `#` as the sed separator so `|` stays free for
  # regex alternation.
  local dsn_user dsn_pw
  dsn_user="$(printf '%s' "$dsn" | sed -nE "s#^postgresql\\+(asyncpg|psycopg)://([^:]+):([^@]+)@.*#\\2#p")"
  dsn_pw="$(printf '%s' "$dsn" | sed -nE "s#^postgresql\\+(asyncpg|psycopg)://([^:]+):([^@]+)@.*#\\3#p")"
  if [[ -z "$dsn_pw" || -z "$dsn_user" ]]; then
    echo "  ⚠ couldn't parse user:password from $secret_name DSN (malformed)"
    return 1
  fi
  # Drift signal: the DSN's user differs from the user Terraform expects.
  # Don't fail on it here (we still verify the credential that's actually
  # in the secret), but surface it loudly — divergent async vs sync DSN
  # users will break the app (workers use the sync DSN, the API the async).
  if [[ "$dsn_user" != "$user" ]]; then
    echo "  ⚠ DRIFT: $secret_name DSN uses user '$dsn_user' but Terraform"
    echo "    convention is '$user'. Verifying the secret's actual user."
    echo "    Fix: re-sync this secret to the '$user' credential — run"
    echo "    \`$0 --rotate\` to regenerate both DSNs end-to-end on '$user'."
  fi
  local pw="$dsn_pw"
  user="$dsn_user"

  local conn
  conn="$(gcloud sql instances describe dma-insights-pg --format='value(connectionName)')"

  local proxy_port=15432
  local proxy_log="/tmp/dma-proxy-verify-$$.log"
  if [[ ! -x /tmp/cloud-sql-proxy ]]; then
    curl -fsSL -o /tmp/cloud-sql-proxy \
      https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.16.0/cloud-sql-proxy.linux.amd64
    chmod +x /tmp/cloud-sql-proxy
  fi
  pkill -f "cloud-sql-proxy.*--port=${proxy_port}" 2>/dev/null || true
  /tmp/cloud-sql-proxy --port="$proxy_port" "$conn" > "$proxy_log" 2>&1 &
  local proxy_pid=$!
  trap 'kill '"$proxy_pid"' 2>/dev/null || true; rm -f '"$proxy_log"  EXIT
  sleep 3

  if PGPASSWORD="$pw" psql -h 127.0.0.1 -p "$proxy_port" -U "$user" \
        -d dma_insights -c 'SELECT 1' >/dev/null 2>&1; then
    kill "$proxy_pid" 2>/dev/null || true
    trap - EXIT
    return 0
  else
    kill "$proxy_pid" 2>/dev/null || true
    trap - EXIT
    return 1
  fi
}

# ── Auto-import secrets that exist in GCP but not in Terraform state ─
# Recurring failure mode: `Error 409: Secret … already exists`. A secret
# was created out-of-band (gcloud, prior partial-apply, dev-shell)
# but Terraform's state file has no record of it, so `terraform apply`
# tries to CREATE and 409s on every retry. Lower parallelism doesn't
# help — only `terraform import` does. This helper detects the 409 in
# the prior apply's stderr and runs the right import command for every
# Terraform-managed secret resource.
#
# Idempotent: `terraform state list | grep -q` skips the import if the
# resource is ALREADY in state. Safe to invoke on every retry.
tf_import_drifted_secrets() {
  local stderr_file="$1"
  # Map: terraform_address -> secret_id
  # Only secrets Terraform OWNS (writes versions). OOB secrets use
  # `data` blocks + are managed by gcloud, so don't import those.
  local -A MANAGED_SECRETS=(
    [google_secret_manager_secret.database_url]="dma-insights-database-url"
    [google_secret_manager_secret.database_url_sync]="dma-insights-database-url-sync"
    [google_secret_manager_secret.database_url_superuser]="dma-insights-database-url-superuser"
    [google_secret_manager_secret.jwt_signing_key]="dma-insights-jwt-signing-key"
  )
  local imported=0
  for addr in "${!MANAGED_SECRETS[@]}"; do
    local sid="${MANAGED_SECRETS[$addr]}"
    # Only act when the prior apply complained about THIS specific secret.
    if ! grep -qE "Secret \[projects/[0-9]+/secrets/${sid}\] already exists" "$stderr_file" 2>/dev/null; then
      continue
    fi
    # Skip if Terraform already knows about it.
    if terraform state list 2>/dev/null | grep -Fxq "$addr"; then
      continue
    fi
    echo "  ↻ importing drifted secret: $addr ← projects/${PROJECT_ID}/secrets/${sid}"
    if terraform import \
         -var "project_id=${PROJECT_ID}" \
         -var "image_sha=${SHA}" \
         "$addr" "projects/${PROJECT_ID}/secrets/${sid}" >/dev/null 2>&1; then
      imported=$((imported + 1))
    else
      echo "  ✗ import failed for $addr — see \`terraform state\` + \`gcloud secrets list\`"
    fi
  done
  [[ "$imported" -gt 0 ]]
}

# ── Resilient terraform apply with retry + parallelism escalation ────────────
tf_apply_with_retry() {
  local -a EXTRA_ARGS=("$@")
  local -a PARALLELISMS=(10 4 2 1)
  local -a WAITS=(2 4 8 16)
  local attempt
  local stderr_file
  stderr_file="$(mktemp)"
  trap 'rm -f "$stderr_file"' RETURN
  for attempt in "${!PARALLELISMS[@]}"; do
    local p="${PARALLELISMS[$attempt]}"
    local w="${WAITS[$attempt]}"
    echo "  → terraform apply attempt $((attempt+1))/${#PARALLELISMS[@]} (parallelism=$p)"
    # Capture stderr so we can inspect for the recurring 409 drift
    # before the next retry — `tee` keeps the live stream intact.
    if terraform apply \
        -var "project_id=${PROJECT_ID}" \
        -var "image_sha=${SHA}" \
        -parallelism="$p" \
        -auto-approve \
        "${EXTRA_ARGS[@]}" 2> >(tee "$stderr_file" >&2); then
      return 0
    fi
    if [[ $attempt -lt $((${#PARALLELISMS[@]} - 1)) ]]; then
      # If the apply 409'd on a Terraform-managed secret that drifted,
      # import the GCP-side resource into state so the NEXT retry can
      # update-in-place instead of re-creating.
      if tf_import_drifted_secrets "$stderr_file"; then
        echo "  ↻ imported drifted secret(s); retrying immediately"
      else
        echo "  ⚠ apply failed — retrying in ${w}s with lower parallelism"
        sleep "$w"
      fi
    fi
  done
  return 1
}

# ── Force Cloud Run revisions to roll so they re-read 'latest' secrets ──────
# Why: Cloud Run resolves `version = "latest"` at CONTAINER START. A long-
# running service revision keeps the resolved value for its lifetime,
# even after the secret gets a new version. Without this, the backend
# service would keep serving the OLD password until something else
# triggered a revision change.
force_revision_rolls() {
  local stamp
  stamp="$(date +%s)"
  echo "→ Forcing Cloud Run revisions to roll (DMA_SECRET_ROLL=${stamp})..."

  if gcloud run services update dma-insights-backend \
       --region="$REGION" \
       --update-env-vars="DMA_SECRET_ROLL=${stamp}" \
       --quiet >/dev/null 2>&1; then
    echo "  ✓ backend service rolled"
  else
    echo "  ⚠ couldn't roll backend service (may not exist yet — skipping)"
  fi

  # 2026-05-28 audit fix (F-301): added peer_patterns, chat_learning,
  # intelligence_recompute (declared in Terraform Wave 2). Without
  # them a password rotation would leave cached creds in those
  # Cloud Run Jobs until their next manual deploy.
  # 2026-06-23: added cross_entity_patterns (Terraform local.jobs).
  # 2026-07-10: added evidence_crawler (Terraform local.jobs) — the
  # redeployment QA sweep caught it missing: a password rotation would
  # have left the evidence-crawler job on cached stale creds.
  for job in dma-insights-migrations dma-insights-historical-backfill \
             dma-insights-drive-crawler dma-insights-sheet-poller \
             dma-insights-embedder dma-insights-ccg-loader \
             dma-insights-peer-patterns dma-insights-chat-learning \
             dma-insights-intelligence-recompute \
             dma-insights-cross-entity-patterns \
             dma-insights-evidence-crawler; do
    if gcloud run jobs update "$job" --region="$REGION" \
         --update-env-vars="DMA_SECRET_ROLL=${stamp}" \
         --quiet >/dev/null 2>&1; then
      echo "  ✓ $job rolled"
    else
      echo "  ⚠ couldn't roll $job (may not exist yet — skipping)"
    fi
  done
}

echo "→ Verifying current password state..."
SUPERUSER_OK=true
APPUSER_OK=true
verify_password "postgres" "dma-insights-database-url-superuser" || SUPERUSER_OK=false
verify_password "dma_insights" "dma-insights-database-url" || APPUSER_OK=false

# Consistency cross-check: the async (`database_url`) and sync
# (`database_url_sync`) DSNs MUST reference the same DB user + password —
# they're the same account, only the driver prefix differs. If a manual
# `gcloud secrets versions add` (or a half-finished first deploy) left
# them pointing at different users (e.g. async=dma_insights_app,
# sync=dma_insights), the API (async) and the workers (sync) authenticate
# as DIFFERENT accounts → schema-ownership + grant chaos. Detect + warn.
_dsn_user() {
  gcloud secrets versions access latest --secret="$1" 2>/dev/null \
    | sed -nE "s#^postgresql\\+(asyncpg|psycopg)://([^:]+):.*#\\2#p"
}
ASYNC_USER="$(_dsn_user dma-insights-database-url)"
SYNC_USER="$(_dsn_user dma-insights-database-url-sync)"
if [[ -n "$ASYNC_USER" && -n "$SYNC_USER" && "$ASYNC_USER" != "$SYNC_USER" ]]; then
  echo "  ⚠ DRIFT: async DSN user '$ASYNC_USER' != sync DSN user '$SYNC_USER'."
  echo "    The backend (async) and workers (sync) would auth as different"
  echo "    accounts. Forcing APPUSER re-sync via full rotation is the clean"
  echo "    fix: \`$0 --rotate\` (regenerates both DSNs on the same user)."
  APPUSER_OK=false
fi

if $SUPERUSER_OK && $APPUSER_OK; then
  echo "✓ Both users authenticate cleanly via cloud-sql-proxy."
  if [[ "$MODE" == "verify" ]]; then exit 0; fi
  if [[ "$MODE" == "heal" ]]; then
    echo ""
    echo "  Note: this only confirms the SECRET matches the SQL user via TCP."
    echo "  If the migrations job / backend still 503s with InvalidPasswordError,"
    echo "  Cloud Run is serving a stale cached secret value. Forcing revision roll..."
    force_revision_rolls
    echo ""
    echo "✓ Recovery complete. Re-run migrations:"
    echo "    gcloud run jobs execute dma-insights-migrations --region=$REGION --wait"
    exit 0
  fi
fi

$SUPERUSER_OK || echo "  ✗ postgres (superuser) password mismatch detected"
$APPUSER_OK   || echo "  ✗ dma_insights (app user) password mismatch detected"

if [[ "$MODE" == "verify" ]]; then
  echo ""
  echo "Drift detected. Re-run without --verify-only to fix:"
  echo "  $0"
  exit 2
fi

# ── Heal or rotate ───────────────────────────────────────────────────────────
echo ""

# 2026-06 persistence guard: take an on-demand Cloud SQL backup BEFORE
# any rotation. The backup is non-blocking — if it fails (permissions,
# disk pressure, instance busy) we log + proceed, falling back to the
# nightly automated backup as the recovery point. The script itself
# never fails the heal — heal is the prod-recovery path; refusing to
# heal because the snapshot also failed would leave the DB in worse
# shape than just proceeding. Snapshot description carries the SHA +
# action verb so `gcloud sql backups list` reads as a clear audit log.
if [[ -x "$(dirname "$0")/backup-before-heal.sh" ]]; then
  BACKUP_TAG="recover-db-passwords-${SHA:-no-sha}-$(date +%s)" \
    "$(dirname "$0")/backup-before-heal.sh" || \
    echo "  ⚠ backup-before-heal returned non-zero (continuing)" >&2
fi

# Preflight: every `terraform apply` evaluates the three
# google_artifact_registry_docker_image data blocks; if any image is
# missing at $SHA the apply fails identically on every retry. Build
# them first so the apply has the resources it expects.
echo "→ Verifying images at SHA $SHA exist in gcr.io..."
ensure_images_built || {
  echo "✗ Cannot proceed — terraform apply would fail at image data lookups." >&2
  exit 1
}
echo ""

if [[ "$MODE" == "rotate" ]]; then
  echo "→ Rotating to fresh random passwords (replace both random_password + setup)..."
  tf_apply_with_retry \
    -replace=random_password.db_superuser \
    -replace=random_password.db_app_user \
    -replace=null_resource.db_superuser_setup \
    -replace=null_resource.db_app_user_setup \
    || { echo "✗ terraform apply exhausted retries. See recover-db-passwords.sh --help." >&2; exit 1; }
else
  echo "→ Healing drift — re-pushing Terraform-state passwords to SQL users..."
  REPLACE_FLAGS=()
  $SUPERUSER_OK || REPLACE_FLAGS+=(-replace=null_resource.db_superuser_setup)
  $APPUSER_OK   || REPLACE_FLAGS+=(-replace=null_resource.db_app_user_setup)
  tf_apply_with_retry "${REPLACE_FLAGS[@]}" \
    || { echo "✗ terraform apply exhausted retries. See recover-db-passwords.sh --help." >&2; exit 1; }
fi

echo ""
echo "→ Re-verifying..."
sleep 5    # Cloud SQL takes ~5s to propagate the password change
verify_password "postgres" "dma-insights-database-url-superuser" \
  && echo "  ✓ postgres now authenticates" \
  || { echo "  ✗ postgres STILL fails — check Cloud SQL state manually"; exit 1; }
verify_password "dma_insights" "dma-insights-database-url" \
  && echo "  ✓ dma_insights now authenticates" \
  || { echo "  ✗ dma_insights STILL fails — check Cloud SQL state manually"; exit 1; }

# CRITICAL: force the backend + jobs to re-read the latest secret values.
echo ""
force_revision_rolls

echo ""
echo "✓ DB password drift healed + Cloud Run revisions rolled."
echo "  Re-run the migrations job:"
echo "    gcloud run jobs execute dma-insights-migrations --region=$REGION --wait"
echo ""
echo "  Then verify the backend (run from infra/, not infra/terraform/):"
echo "    cd ${SCRIPT_DIR}"
echo "    BACKEND=\"\$(terraform -chdir=terraform output -raw backend_url)\""
echo "    curl -sf \"\${BACKEND}/readyz\" | jq ."
echo "    # Expected: {\"status\":\"ready\"}"
