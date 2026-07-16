#!/usr/bin/env bash
# apps/dma-insights/infra/force-heal-db.sh
#
# Last-resort DB password heal — Secret Manager is the source of truth.
#
# When `recover-db-passwords.sh` reports "✓ Recovery complete" but the
# backend still returns
#   /readyz   {"status":"degraded","db":"down: InvalidPasswordError"}
#   sign-in  Domain restricted — [503] DB error during sign-in:
#            InvalidPasswordError: password authentication failed for user
#            "dma_insights"
# the drift is between Cloud SQL ↔ Secret Manager ↔ Cloud Run revision.
# The terraform-driven heal re-randomizes the password and force-sets it on
# both Cloud SQL + Secret Manager + rolls revisions. That breaks down when:
#
#   1. terraform apply fails silently (network, lock, IAM) → only ONE of
#      the two sides actually updated.
#   2. Cloud Run resolves `version = "latest"` at container START. A
#      revision created BEFORE the secret rotated still serves the
#      pre-rotation value for its lifetime.
#   3. A concurrent operator changed the Cloud SQL password directly
#      AFTER the terraform-driven heal.
#
# This script takes the OPPOSITE direction:
#
#   Secret Manager IS the truth → force-set Cloud SQL user to match →
#   force-roll Cloud Run revisions.
#
# It never touches terraform. It never re-randomizes. Whatever the
# `dma-insights-database-url` secret currently embeds becomes the live
# password on the Cloud SQL user `dma_insights` AND the live env-var on
# the backend service + every Cloud Run Job.
#
# Use this when:
#   - You've already run recover-db-passwords.sh and the sign-in still 503s.
#   - You manually rotated the secret and need Cloud SQL to catch up.
#   - You're not sure where the drift is and want a bulletproof reset
#     that doesn't require running terraform.
#
# Usage:
#   ./force-heal-db.sh                  # secret → SQL → roll revisions
#   ./force-heal-db.sh --verify-only    # confirm via cloud-sql-proxy; no writes
#   ./force-heal-db.sh --no-roll        # update creds but skip revision roll
#
# Exit codes:
#   0   healed (or verify-only passed)
#   2   verify-only detected drift (no writes attempted)
#   3   Secret Manager secret missing or malformed (can't extract password)
#   4   gcloud sql users set-password failed
#   5   one of the Cloud Run revision rolls failed
set -euo pipefail

# ── Inputs ──────────────────────────────────────────────────────────────────
REGION="${REGION:-us-central1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
INSTANCE="${INSTANCE:-dma-insights-pg}"
DB_NAME="${DB_NAME:-dma_insights}"
APP_USER="${APP_USER:-dma_insights}"
SECRET_NAME="${SECRET_NAME:-dma-insights-database-url}"
BACKEND_SVC="${BACKEND_SVC:-dma-insights-backend}"

MODE="heal"
ROLL=true
for arg in "$@"; do
  case "$arg" in
    --verify-only) MODE="verify" ;;
    --no-roll)     ROLL=false ;;
    -h|--help)
      sed -n '1,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "::error::unknown flag: $arg" >&2; exit 1 ;;
  esac
done

if [[ -z "${PROJECT_ID}" ]]; then
  echo "::error::PROJECT_ID not set and gcloud has no default project" >&2
  exit 1
fi

echo "→ Project: $PROJECT_ID · Region: $REGION · Instance: $INSTANCE"
echo "→ Secret:  $SECRET_NAME"
echo "→ User:    $APP_USER@$DB_NAME"
echo ""

# ── Step 1: read the live password from Secret Manager ─────────────────────
# The secret stores the full DSN:
#   postgresql+asyncpg://dma_insights:PASSWORD@/dma_insights?host=/cloudsql/...
# We extract the password between the first `:` after `://user:` and the
# `@`. The password is URL-safe (terraform's `random_password ... special
# = false`) so percent-decoding is unnecessary.
echo "→ Reading password from Secret Manager (version=latest)..."
DSN="$(gcloud secrets versions access latest \
        --secret="$SECRET_NAME" \
        --project="$PROJECT_ID" 2>/dev/null || true)"
if [[ -z "$DSN" ]]; then
  echo "::error::secret $SECRET_NAME version=latest is empty or missing" >&2
  exit 3
fi

# Parse the password out of the DSN. Format:
#   postgresql+asyncpg://USER:PASS@/DB?host=...
# Use python for a robust parse (handles any future URL changes).
PASSWORD="$(python3 - "$DSN" <<'EOF'
import sys, urllib.parse as up
url = sys.argv[1]
# urlparse needs a scheme it knows; rewrite the +asyncpg suffix.
canon = url.replace("+asyncpg", "").replace("+psycopg", "")
parsed = up.urlparse(canon)
if parsed.password:
    print(parsed.password)
else:
    sys.exit(1)
EOF
)" || {
  echo "::error::couldn't parse password out of secret value" >&2
  echo "         secret prefix: ${DSN:0:40}..." >&2
  exit 3
}

if [[ -z "$PASSWORD" || ${#PASSWORD} -lt 8 ]]; then
  echo "::error::extracted password looks invalid (len=${#PASSWORD})" >&2
  exit 3
fi
echo "  ✓ extracted password from secret (len=${#PASSWORD})"

# ── Step 2: verify by attempting a TCP connection via cloud-sql-proxy ─────
echo ""
echo "→ Verifying password against Cloud SQL user '$APP_USER'..."
PROXY_PID=""
TMPSOCK="/tmp/dma-heal-sql-$$"
mkdir -p "$TMPSOCK"
trap 'rm -rf "$TMPSOCK"; [[ -n "$PROXY_PID" ]] && kill "$PROXY_PID" 2>/dev/null || true' EXIT

CONN_NAME="$(gcloud sql instances describe "$INSTANCE" --project="$PROJECT_ID" \
              --format='value(connectionName)' 2>/dev/null || true)"
if [[ -z "$CONN_NAME" ]]; then
  echo "::error::couldn't resolve connectionName for instance $INSTANCE" >&2
  exit 4
fi
echo "  connection: $CONN_NAME"

if ! command -v cloud-sql-proxy >/dev/null 2>&1; then
  echo "  ⚠ cloud-sql-proxy not on PATH — skipping pre-check; will try set-password directly."
  PROXY_VERIFY_OK=false
else
  cloud-sql-proxy --unix-socket="$TMPSOCK" "$CONN_NAME" >/dev/null 2>&1 &
  PROXY_PID=$!
  sleep 3
  PROXY_VERIFY_OK=false
  if PGPASSWORD="$PASSWORD" psql -h "$TMPSOCK/$CONN_NAME" -U "$APP_USER" \
                                    -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
    PROXY_VERIFY_OK=true
    echo "  ✓ secret password authenticates cleanly"
  else
    echo "  ✗ secret password REJECTED — drift between secret and SQL"
  fi
fi

if [[ "$MODE" == "verify" ]]; then
  if $PROXY_VERIFY_OK; then
    echo "✓ verify-only: no drift detected."
    exit 0
  fi
  echo "✗ verify-only: drift confirmed. Re-run without --verify-only to heal."
  exit 2
fi

# ── Step 2.5: pre-heal Cloud SQL snapshot (persistence guard) ──────────────
# Take an on-demand backup BEFORE the password set-password. Even though
# set-password is a metadata op that doesn't touch data, we still want a
# fresh recovery point: if the password change cascades into a Cloud Run
# instance restart that loses an in-flight large transaction, the most
# recent automated nightly backup may be 24h old. backup-before-heal.sh
# fails open — never blocks the heal — so worst case is "same recovery
# window as before this script was added."
if [[ -x "$(dirname "$0")/backup-before-heal.sh" ]]; then
  BACKUP_TAG="force-heal-db-$(date +%s)" \
    "$(dirname "$0")/backup-before-heal.sh" || \
    echo "  ⚠ backup-before-heal returned non-zero (continuing heal)" >&2
fi

# ── Step 3: force-set the Cloud SQL user's password to the secret value ──
echo ""
echo "→ Force-setting Cloud SQL user '$APP_USER' password to match secret..."
if ! gcloud sql users set-password "$APP_USER" \
       --instance="$INSTANCE" \
       --password="$PASSWORD" \
       --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "::error::gcloud sql users set-password failed" >&2
  exit 4
fi
echo "  ✓ set-password OK"

# Re-verify via the proxy (if available). If verification keeps failing
# after the set-password reports success, the secret value itself is
# unparseable / corrupted by SQL (e.g. an encoding issue between the
# secret bytes and what SCRAM-SHA-256 stores) — in that case the only
# safe path is to REGENERATE a clean password and write it to BOTH
# sides atomically (Secret Manager first, then SQL). That's done in
# step 3b below.
NEED_REGENERATE=false
if [[ "$PROXY_VERIFY_OK" == "false" ]] && command -v cloud-sql-proxy >/dev/null 2>&1; then
  sleep 2
  if PGPASSWORD="$PASSWORD" psql -h "$TMPSOCK/$CONN_NAME" -U "$APP_USER" \
                                    -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
    echo "  ✓ post-set verification OK"
  else
    echo "  ⚠ post-set verification STILL failing — retrying in 10s (replication lag)..."
    sleep 10
    if PGPASSWORD="$PASSWORD" psql -h "$TMPSOCK/$CONN_NAME" -U "$APP_USER" \
                                     -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
      echo "  ✓ verification OK after retry"
    else
      echo "  ⚠ verification STILL failing after 10s. Falling through to" \
           "regenerate-password path (write new password to BOTH secret + SQL)."
      NEED_REGENERATE=true
    fi
  fi
fi

# ── Step 3b: regenerate-password escape hatch ───────────────────────────────
# When set-password reports success but psql still rejects the value, we
# can't trust the secret bytes. Generate a fresh URL-safe random password
# (matches terraform's `random_password ... special = false` shape), write
# it to BOTH sides in the correct order:
#
#   1. Write new password to Secret Manager (atomic, versioned)
#   2. Set the new password on the Cloud SQL user
#   3. Verify via psql that the NEW password authenticates
#
# Step 1 → 2 ordering means: if step 2 fails, we still have a clean,
# accessible password in Secret Manager (no half-written state). If step
# 3 fails after both writes, the SECRET is the source of truth — the
# next heal cycle picks up the new password from Secret Manager and
# tries again.
if [[ "$NEED_REGENERATE" == "true" ]]; then
  echo ""
  echo "→ Regenerating password (escape hatch — both secret + SQL get the new value)..."
  # 48-char URL-safe: matches terraform `length = 48, special = false`.
  NEW_PW="$(python3 -c "import secrets, string; \
print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(48)))")"
  if [[ -z "$NEW_PW" || ${#NEW_PW} -ne 48 ]]; then
    echo "::error::failed to generate replacement password" >&2
    exit 4
  fi
  # Reconstruct the DSN with the new password, preserving everything else.
  NEW_DSN="$(python3 - "$DSN" "$NEW_PW" <<'EOF'
import sys, urllib.parse as up
url, new_pw = sys.argv[1], sys.argv[2]
canon = url.replace("+asyncpg", "").replace("+psycopg", "")
parsed = up.urlparse(canon)
new_netloc = f"{parsed.username}:{new_pw}@{parsed.hostname or ''}"
if parsed.port:
    new_netloc += f":{parsed.port}"
rebuilt = parsed._replace(netloc=new_netloc).geturl()
# Restore the +asyncpg driver hint if present in the original.
if "+asyncpg" in url:
    rebuilt = rebuilt.replace("postgresql://", "postgresql+asyncpg://", 1)
elif "+psycopg" in url:
    rebuilt = rebuilt.replace("postgresql://", "postgresql+psycopg://", 1)
print(rebuilt)
EOF
)" || { echo "::error::DSN rebuild failed" >&2; exit 4; }

  echo "  → writing new DSN to Secret Manager (creates new version)..."
  if ! printf '%s' "$NEW_DSN" | gcloud secrets versions add "$SECRET_NAME" \
         --project="$PROJECT_ID" --data-file=- >/dev/null 2>&1; then
    echo "::error::secrets versions add failed; SQL untouched, secret unchanged" >&2
    exit 4
  fi
  echo "  ✓ new secret version written"

  echo "  → setting new password on Cloud SQL user '$APP_USER'..."
  if ! gcloud sql users set-password "$APP_USER" \
         --instance="$INSTANCE" \
         --password="$NEW_PW" \
         --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "::error::set-password failed for regenerated password; secret has new value but SQL doesn't" >&2
    echo "         Re-run this script to retry the SQL set; secret is the source of truth." >&2
    exit 4
  fi
  echo "  ✓ SQL set-password OK"

  # Verify via psql with the NEW password.
  if command -v cloud-sql-proxy >/dev/null 2>&1; then
    sleep 3
    if PGPASSWORD="$NEW_PW" psql -h "$TMPSOCK/$CONN_NAME" -U "$APP_USER" \
                                    -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
      echo "  ✓ regenerated password authenticates cleanly"
    else
      sleep 8
      if PGPASSWORD="$NEW_PW" psql -h "$TMPSOCK/$CONN_NAME" -U "$APP_USER" \
                                      -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
        echo "  ✓ regenerated password OK after replication delay"
      else
        echo "::error::regenerated password STILL rejected. Possible causes:" >&2
        echo "         (1) the dma_insights user does not exist in this instance" >&2
        echo "         (2) the dma_insights database doesn't exist in this instance" >&2
        echo "         (3) Cloud SQL Auth Proxy is connecting to a different instance" >&2
        echo "  Diagnose:" >&2
        echo "    gcloud sql users list --instance=$INSTANCE --project=$PROJECT_ID" >&2
        echo "    gcloud sql databases list --instance=$INSTANCE --project=$PROJECT_ID" >&2
        exit 4
      fi
    fi
  fi
  # Update PASSWORD for the rest of the script (Cloud Run roll uses the
  # secret directly, so this is just for log clarity).
  PASSWORD="$NEW_PW"
fi

# ── Step 4: force-roll Cloud Run revisions so they re-read the secret ────
# Cloud Run resolves `version = "latest"` at container START. Live
# revisions keep the resolved value for their lifetime. Updating the
# secret is invisible to running revisions; we have to roll them.
# Since the SECRET didn't change here (Secret Manager already had this
# password), the Cloud Run revisions are ALREADY serving the right
# value — UNLESS a revision was deployed at a time when the secret had
# a different value and never rolled since. Force-roll to be safe.
if ! $ROLL; then
  echo ""
  echo "→ --no-roll specified, skipping revision rolls."
  echo "✓ DB password heal complete (Cloud SQL ↔ Secret aligned)."
  exit 0
fi

echo ""
echo "→ Rolling Cloud Run revisions so they re-read the secret..."
STAMP="$(date +%s)"

if gcloud run services update "$BACKEND_SVC" \
     --region="$REGION" --project="$PROJECT_ID" \
     --update-env-vars="DMA_SECRET_ROLL=${STAMP}" \
     --quiet >/dev/null 2>&1; then
  echo "  ✓ $BACKEND_SVC rolled"
else
  echo "::error::failed to roll $BACKEND_SVC" >&2
  exit 5
fi

# Same set the existing recover-db-passwords.sh rolls.
for job in dma-insights-migrations dma-insights-historical-backfill \
           dma-insights-drive-crawler dma-insights-sheet-poller \
           dma-insights-embedder dma-insights-ccg-loader \
           dma-insights-peer-patterns dma-insights-chat-learning \
           dma-insights-intelligence-recompute; do
  if gcloud run jobs update "$job" --region="$REGION" --project="$PROJECT_ID" \
       --update-env-vars="DMA_SECRET_ROLL=${STAMP}" --quiet >/dev/null 2>&1; then
    echo "  ✓ $job rolled"
  else
    echo "  ⚠ couldn't roll $job (may not exist) — continuing"
  fi
done

echo ""
echo "✓ Force-heal complete."
echo ""
echo "Verify the backend is healthy:"
echo "  BE_URL=\"\$(gcloud run services describe $BACKEND_SVC --region=$REGION --format='value(status.url)')\""
echo "  curl -s \"\${BE_URL}/readyz\" | jq ."
echo ""
echo "If /readyz still reports db=down, capture diagnostics:"
echo "  gcloud run services logs read $BACKEND_SVC --region=$REGION --limit=80"
