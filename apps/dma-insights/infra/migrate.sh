#!/usr/bin/env bash
# apps/dma-insights/infra/migrate.sh
#
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  ERROR HISTORY — keep this list in sync with new failure modes.      ║
# ╠══════════════════════════════════════════════════════════════════════╣
# ║  M1  'FATAL: password authentication failed for user postgres'       ║
# ║      → Secret Manager DSN out of sync with SQL user password         ║
# ║      FIX: pre-flight via recover-db-passwords.sh --verify-only;      ║
# ║           auto-heal on drift; --skip-verify escape hatch             ║
# ║                                                                      ║
# ║  M2  'StringDataRightTruncation: value too long for char varying(32)'║
# ║      → alembic_version.version_num is VARCHAR(32) but revision ID    ║
# ║        was 35 chars (`021_runs_data_source_drive_backfill`)          ║
# ║      FIX: 3 layers —                                                 ║
# ║        a) revision renamed to 23 chars (021_runs_drive_backfill)     ║
# ║        b) alembic/env.py widens column to VARCHAR(128) per run       ║
# ║        c) test_migration_id_lengths.py CI-fails any new overrun      ║
# ║        d) THIS SCRIPT detects the signature in failed Cloud Run Job  ║
# ║           logs + prints the one-shot ALTER hot-fix command           ║
# ║                                                                      ║
# ║  M3  Migration body executes but rollback erases all the DDL         ║
# ║      → same M2 — UPDATE alembic_version fails AFTER the body runs    ║
# ║      FIX: covered by M2.b (widener runs BEFORE body)                 ║
# ║                                                                      ║
# ║  M4  Cloud Run Job missing on a fresh project                        ║
# ║      → 'Cloud Run Job dma-insights-migrations not found'             ║
# ║      FIX: section 0 of this script — fail fast with the canonical    ║
# ║           './deploy.sh first' bootstrap instruction                  ║
# ║                                                                      ║
# ║  M5  IPv6 routing failures from Cloud Shell during gcloud calls      ║
# ║      FIX: GODEBUG=netdns=go set unconditionally at line 105          ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Self-healing migration runner.
#
# Wraps the `dma-insights-migrations` Cloud Run Job so the recurring
# Cloud SQL password-drift symptom is handled automatically:
#
#   FATAL: password authentication failed for user "postgres"
#
# Flow:
#   1. Verify both DB user passwords via cloud-sql-proxy.
#   2. If drift detected → invoke ./recover-db-passwords.sh to heal it
#      + force Cloud Run revision rolls (so the migrations job re-reads
#      the freshly-written secret on its next start).
#   3. Trigger the migrations job and wait for completion.
#   4. Tail the last 30 log lines so the operator sees the alembic
#      `head` revision without having to chase log URIs.
#
# Resilience contract — state branches:
#
#   passwords_match
#     → skip recovery; execute migrations job directly.
#
#   superuser_drift_only
#     → run recovery with only db_superuser_setup replaced; the app
#       user is left alone so concurrent app-user reads keep working.
#
#   app_user_drift_only
#     → mirror of above for db_app_user_setup.
#
#   both_drifted
#     → run recovery with both setups replaced.
#
#   recovery_failed
#     → exit non-zero with a clear pointer to --diagnose mode + the
#       recovery script's --rotate fallback.
#
#   migration_job_missing
#     → fail fast with the canonical bootstrap instruction
#       (./deploy.sh must have run at least once to create the job).
#
# Usage:
#   ./migrate.sh                        # heal-if-needed, then migrate
#   ./migrate.sh --skip-verify          # straight to migrate (assume passwords OK)
#   ./migrate.sh --verify-only          # check passwords; do not migrate
#
# All flags are forwarded to recover-db-passwords.sh when recovery fires.
set -euo pipefail

# Cloud Shell IPv6 NAT pool mitigation (same pattern as deploy.sh and
# recover-db-passwords.sh). Go's resolver picks IPv6 records that the
# NAT layer can't route — pure-Go resolver picks IPv4 first.
export GODEBUG=netdns=go

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Silence the benign per-call "Regional Access Boundary ... 404" gcloud
# stderr noise (Cloud Shell federated identities; see the filter file).
[ -f "${SCRIPT_DIR}/gcloud-noise-filter.sh" ] && . "${SCRIPT_DIR}/gcloud-noise-filter.sh"
REGION="${REGION:-us-central1}"
JOB_NAME="${JOB_NAME:-dma-insights-migrations}"

MODE="auto"
case "${1:-}" in
  --skip-verify) MODE="skip-verify" ;;
  --verify-only) MODE="verify-only" ;;
  --help|-h)
    grep '^#' "$0" | sed 's/^# \?//' | head -40
    exit 0
    ;;
esac

# ── 0. Pre-flight: project + job presence ───────────────────────────────────
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "ERROR: PROJECT_ID unset. Run: gcloud config set project digital-maturity-assessor" >&2
  exit 1
fi

if ! gcloud run jobs describe "$JOB_NAME" --region="$REGION" \
       --format='value(name)' >/dev/null 2>&1; then
  echo "ERROR: Cloud Run Job '$JOB_NAME' not found in region $REGION." >&2
  echo "       Run ./deploy.sh first to bootstrap the migrations job." >&2
  exit 1
fi

# ── 0. Cloud SQL liveness (auto-start if STOPPED) ──────────────────────────
# 2026-06 self-healing addition: if Cloud SQL was idle-stopped or is
# mid-maintenance, the password verify below has nothing to connect to
# and the script crashes with an opaque cloud-sql-proxy "connection
# refused". Run preflight-cloud-sql.sh first so the deploy is resilient
# to STOPPED state. Skippable via SKIP_CLOUD_SQL_CHECK=true for
# environments where the operator has already verified instance state.
if [[ "${SKIP_CLOUD_SQL_CHECK:-false}" != "true" ]] \
   && [[ -x "$SCRIPT_DIR/preflight-cloud-sql.sh" ]]; then
  if ! "$SCRIPT_DIR/preflight-cloud-sql.sh"; then
    echo "FATAL: Cloud SQL instance is not RUNNABLE; aborting migrate." >&2
    exit 1
  fi
fi

# ── 1. Verify passwords (unless --skip-verify) ──────────────────────────────
NEEDS_RECOVERY=false
if [[ "$MODE" != "skip-verify" ]]; then
  echo "→ Verifying DB password state (via cloud-sql-proxy)..."
  if ! "$SCRIPT_DIR/recover-db-passwords.sh" --verify-only; then
    NEEDS_RECOVERY=true
    echo "  ⚠ Password drift detected."
  else
    echo "  ✓ Both users authenticate cleanly."
  fi
fi

if [[ "$MODE" == "verify-only" ]]; then
  $NEEDS_RECOVERY && exit 2 || exit 0
fi

# ── 2. Heal if needed ───────────────────────────────────────────────────────
# 2026-06 deployment hardening: the prior code aborted on
# recover-db-passwords.sh failure with an actionable-looking error that
# the operator couldn't actually act on inside CI. When terraform state
# is unreachable (Cloud Build SA missing bucket ACL, or the operator is
# running the script outside the project's terraform context), heal via
# force-heal-db.sh — it uses Secret-Manager-as-truth and forces the
# Cloud SQL user passwords to match the secret. This is the recovery
# path the original recover script was supposed to wrap.
if $NEEDS_RECOVERY; then
  echo ""
  echo "→ Running recover-db-passwords.sh to heal..."
  if "$SCRIPT_DIR/recover-db-passwords.sh"; then
    : # success — fall through to settle wait
  elif [[ -x "$SCRIPT_DIR/force-heal-db.sh" ]]; then
    echo "" >&2
    echo "  ⚠ recover-db-passwords.sh failed; trying force-heal-db.sh" >&2
    echo "    (Secret-Manager-as-truth — bypasses terraform state)" >&2
    if ! "$SCRIPT_DIR/force-heal-db.sh"; then
      echo "" >&2
      echo "✗ Both recovery paths failed." >&2
      echo "  Diagnose secret + revision state:" >&2
      echo "    $SCRIPT_DIR/recover-db-passwords.sh --diagnose" >&2
      echo "  Or full rotation (last resort):" >&2
      echo "    $SCRIPT_DIR/recover-db-passwords.sh --rotate" >&2
      exit 1
    fi
    echo "  ✓ force-heal-db.sh healed the password drift" >&2
  else
    echo "" >&2
    echo "✗ recover-db-passwords.sh failed and no force-heal-db.sh fallback." >&2
    echo "  Try --diagnose to inspect secret + revision state:" >&2
    echo "    $SCRIPT_DIR/recover-db-passwords.sh --diagnose" >&2
    echo "  Or fall back to full rotation:" >&2
    echo "    $SCRIPT_DIR/recover-db-passwords.sh --rotate" >&2
    exit 1
  fi
  # Give Cloud Run a beat to settle after the revision roll before we
  # trigger the migrations job — otherwise we can race the secret-reread.
  echo "  → settling Cloud Run revisions (5s)..."
  sleep 5
fi

# ── 3. Force the job to re-read secrets before executing ───────────────────
# 2026-06 root-cause fix for the recurring
#   "InvalidPasswordError: password authentication failed for user dma_insights"
# that hits ~every other deploy:
#
# Cloud Run Jobs cache env-var values (including
# `--set-secrets=POSTGRES_DSN=postgres-dsn:latest`) at JOB CREATION time
# AND when a new job revision is created via `gcloud run jobs update`.
# `gcloud run jobs execute` does NOT re-read secrets — it runs the
# latest job revision verbatim. So if Secret Manager rotated the DSN
# between deploys (e.g. recover-db-passwords.sh ran, or
# force-heal-db.sh updated the secret), the next migration execute
# fires with the STALE cached DSN → 503 InvalidPasswordError.
#
# The DMA_SECRET_ROLL env-var bump forces Cloud Run to create a new job
# revision, which re-reads every `--set-secrets` source. The env var
# itself is unused by the app; it's a deterministic cache-buster, not
# a feature flag.
#
# Safe under concurrency: gcloud run jobs update is atomic; if two
# operators race, the loser sees a 409 which we retry once with a
# fresh ROLL stamp.
# ── 2.5 Pin the migrations job to the deploying SHA's image ───────────────
# 2026-06-06 root-cause fix for the recurring
#   "InsufficientPrivilegeError: permission denied for table alembic_version"
# Phase 4 503 that hits every deploy whose code changes post_migrate.py:
#
# Cloud Run JOBS are NOT updated by `gcloud run services update` (that's
# services only). The dma-insights-migrations Cloud Run Job's image is
# whatever terraform last applied — which can be MANY deploys behind
# what the backend service is being deployed to RIGHT NOW.
#
# Concretely: deploy-two-phase.sh Phase 2 updates the BACKEND SERVICE
# image to gcr.io/$PROJECT_ID/dma-insights-backend:$SHA, then Phase 3
# calls this script to run migrations. If we just `gcloud run jobs
# execute dma-insights-migrations` here, we run the OLD migrations
# image — OLD alembic, OLD post_migrate.py. The OLD post_migrate may
# not have the GRANT chain the NEW backend's /readyz expects (e.g.
# the explicit alembic_version GRANT added 2026-06-06). The NEW backend
# then 503's /readyz on Phase 4 and the deploy aborts.
#
# Fix: when SHA + PROJECT_ID are set (deploy-two-phase.sh exports
# both), update the migrations job's image to match the deploying
# SHA BEFORE we execute. Idempotent: same SHA = no-op.
#
# 2026-06-06 audit fix (anti-pattern C): when SHA is unset (operator
# running migrate.sh standalone for a one-shot heal), the prior
# implementation used whatever image terraform last applied — usually
# stale relative to the live backend's expectations, causing the same
# "permission denied for table alembic_version" failure mode as if the
# pin had been skipped during a normal deploy. Now we fall back to the
# SHA currently deployed on the backend service, so standalone heal
# uses the SAME image as the live backend.
if [[ -z "${SHA:-}" && -n "${PROJECT_ID:-}" ]]; then
  echo ""
  echo "→ SHA env unset; detecting from deployed backend image..."
  deployed_image="$(gcloud run services describe dma-insights-backend \
    --region="$REGION" --project="$PROJECT_ID" \
    --format='value(spec.template.spec.containers[0].image)' 2>/dev/null \
    || true)"
  if [[ "$deployed_image" =~ :([a-f0-9]+)$ ]]; then
    SHA="${BASH_REMATCH[1]}"
    echo "  ✓ inferred SHA=$SHA from deployed backend image"
  else
    echo "  ⚠ deployed backend image has no tag suffix ('$deployed_image')"
    echo "    -- falling back to whatever migrations job image terraform"
    echo "    last applied. If Phase 4 503s with a permission-denied or"
    echo "    schema-drift symptom, re-run with SHA=<deployed-sha> set"
    echo "    explicitly:"
    echo "      SHA=abc1234 PROJECT_ID=$PROJECT_ID bash infra/migrate.sh"
  fi
fi

if [[ -n "${SHA:-}" && -n "${PROJECT_ID:-}" ]]; then
  MIGRATIONS_IMAGE="gcr.io/${PROJECT_ID}/dma-insights-backend:${SHA}"
  echo ""
  echo "→ Pinning $JOB_NAME image to ${MIGRATIONS_IMAGE}..."
  current_image="$(gcloud run jobs describe "$JOB_NAME" \
    --region="$REGION" \
    --format='value(template.template.containers[0].image)' 2>/dev/null || true)"
  if [[ "$current_image" == "$MIGRATIONS_IMAGE" ]]; then
    echo "  ✓ already at $MIGRATIONS_IMAGE — no update needed"
  else
    if ! gcloud run jobs update "$JOB_NAME" \
           --region="$REGION" \
           --image="$MIGRATIONS_IMAGE" >/dev/null 2>&1; then
      echo "" >&2
      echo "✗ Could not pin $JOB_NAME image to $MIGRATIONS_IMAGE." >&2
      echo "  This means migrations would run an OLD post_migrate.py and" >&2
      echo "  the NEW backend's /readyz will 503 on Phase 4 with" >&2
      echo "  'permission denied for table alembic_version' or similar." >&2
      echo "  Manual fix:" >&2
      echo "    gcloud run jobs update $JOB_NAME --region=$REGION \\" >&2
      echo "      --image=$MIGRATIONS_IMAGE" >&2
      exit 1
    fi
    echo "  ✓ pinned (was: ${current_image:-<unset>})"
  fi
else
  echo ""
  echo "→ SHA/PROJECT_ID unset — running migrations with whatever image"
  echo "  $JOB_NAME currently has. (Standalone heal mode.)"
fi

# ── 3. Force the job to re-read secrets before executing ───────────────────
# 2026-06 root-cause fix for the recurring
#   "InvalidPasswordError: password authentication failed for user dma_insights"
# that hits ~every other deploy:
#
# Cloud Run Jobs cache env-var values (including
# `--set-secrets=POSTGRES_DSN=postgres-dsn:latest`) at JOB CREATION time
# AND when a new job revision is created via `gcloud run jobs update`.
# `gcloud run jobs execute` does NOT re-read secrets — it runs the
# latest job revision verbatim. So if Secret Manager rotated the DSN
# between deploys (e.g. recover-db-passwords.sh ran, or
# force-heal-db.sh updated the secret), the next migration execute
# fires with the STALE cached DSN → 503 InvalidPasswordError.
#
# The DMA_SECRET_ROLL env-var bump forces Cloud Run to create a new job
# revision, which re-reads every `--set-secrets` source. The env var
# itself is unused by the app; it's a deterministic cache-buster, not
# a feature flag.
#
# Safe under concurrency: gcloud run jobs update is atomic; if two
# operators race, the loser sees a 409 which we retry once with a
# fresh ROLL stamp.
echo ""
echo "→ Forcing $JOB_NAME revision roll so it re-reads Secret Manager..."
# 2026-06-06 audit fix (anti-pattern D): the prior implementation
# swallowed the second-attempt failure with `|| { echo "MAY still
# pick up..."; }` and continued executing the job. That's silent
# corruption: a cached DSN does NOT get re-read until the revision
# is actually new, so the migration runs against the pre-rotation
# password and Phase 4 then 503s with no obvious link back to the
# missed roll. Both attempts now must succeed or the script exits
# non-zero — the operator gets an actionable failure mode instead
# of a mysterious Phase 4 503.
roll_stamp="$(date +%s)-${SHA:-no-sha}"
roll_succeeded=0
if gcloud run jobs update "$JOB_NAME" \
       --region="$REGION" \
       --update-env-vars="DMA_SECRET_ROLL=${roll_stamp}" >/dev/null 2>&1; then
  roll_succeeded=1
else
  # 409 race / quota — retry ONCE with a fresh stamp.
  sleep 2
  roll_stamp="$(date +%s)-retry"
  if gcloud run jobs update "$JOB_NAME" \
       --region="$REGION" \
       --update-env-vars="DMA_SECRET_ROLL=${roll_stamp}" >/dev/null 2>&1; then
    roll_succeeded=1
  fi
fi
if [[ "$roll_succeeded" -ne 1 ]]; then
  echo "" >&2
  echo "✗ Could not force $JOB_NAME revision roll after 2 attempts." >&2
  echo "  Without the roll, the migrations job's cached POSTGRES_DSN is" >&2
  echo "  stale; running migrations now would 503 Phase 4 with an" >&2
  echo "  InvalidPasswordError that looks like a database issue but" >&2
  echo "  is really 'Cloud Run never reloaded the rotated secret'." >&2
  echo "" >&2
  echo "  Diagnose:" >&2
  echo "    gcloud run jobs describe $JOB_NAME --region=$REGION" >&2
  echo "    gcloud auth list" >&2
  echo "    gcloud iam service-accounts get-iam-policy \\" >&2
  echo "      \$(gcloud run jobs describe $JOB_NAME --region=$REGION \\" >&2
  echo "         --format='value(template.serviceAccountName)')" >&2
  echo "" >&2
  exit 1
fi
echo "  ✓ rolled revision (DMA_SECRET_ROLL=${roll_stamp})"

# ── 4. Execute migrations job ───────────────────────────────────────────────
echo ""
echo "→ Executing $JOB_NAME in $REGION..."
if ! gcloud run jobs execute "$JOB_NAME" --region="$REGION" --wait; then
  echo "" >&2
  echo "✗ Migrations job failed." >&2
  echo "  Inspect the last execution for root cause:" >&2
  LAST_EXEC="$(gcloud run jobs executions list \
    --job="$JOB_NAME" --region="$REGION" --limit=1 \
    --format='value(name)' 2>/dev/null || true)"
  if [[ -n "$LAST_EXEC" ]]; then
    echo "    gcloud beta run jobs executions logs read $LAST_EXEC --region=$REGION" >&2

    # ── 3a. Detect alembic_version column-truncation case ────────────────────
    # State branches:
    #   no_truncation_in_logs  → exit 1, generic failure
    #   truncation_detected    → emit T14 hot-fix command + exit 1
    LOG_TAIL="$(gcloud beta run jobs executions logs read "$LAST_EXEC" \
      --region="$REGION" 2>/dev/null | tail -200 || true)"
    if grep -q "StringDataRightTruncation\|value too long for type character varying(32)" \
         <<<"$LOG_TAIL"; then
      echo "" >&2
      echo "⚠ Detected alembic_version VARCHAR(32) truncation." >&2
      echo "  This happens when a revision ID > 32 chars hits the default" >&2
      echo "  alembic_version column. The env.py widener landed in this" >&2
      echo "  release; if the migration image was built BEFORE the widener," >&2
      echo "  apply the one-shot SQL hot-fix and re-run this script:" >&2
      echo "" >&2
      echo "    gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \\" >&2
      echo "      --command=\"ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);\"" >&2
      echo "    ./migrate.sh --skip-verify" >&2
      echo "" >&2
      echo "  Full T14 docs: DEPLOYMENT.md §19 T14." >&2
    fi
  fi
  exit 1
fi

# ── 4. Tail recent logs so the operator sees alembic head + post_migrate ────
echo ""
echo "→ Recent execution logs:"
LAST_EXEC="$(gcloud run jobs executions list \
  --job="$JOB_NAME" --region="$REGION" --limit=1 \
  --format='value(name)')"
gcloud beta run jobs executions logs read "$LAST_EXEC" \
  --region="$REGION" 2>/dev/null | tail -30 || true

echo ""
echo "✓ Migrations complete."
