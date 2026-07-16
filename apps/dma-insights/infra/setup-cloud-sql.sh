#!/usr/bin/env bash
# Provision Cloud SQL Postgres for DMA Insights — idempotent, resilient,
# auth-persistent. Replaces the §0.5.4 paste block that hit three
# recurring failure modes:
#
#   1. Tier `db-custom-2-7680` is rejected by ENTERPRISE_PLUS-default
#      projects with the unhelpful "Use a predefined Tier like
#      db-perf-optimized-N-* instead." We pin `--edition=ENTERPRISE`
#      explicitly so the classic db-custom-* tiers keep working AND
#      the per-instance cost stays predictable.
#
#   2. `gcloud sql connect` interactively prompts for the postgres
#      password EVERY session. The operator's local $SQL_PASSWORD was
#      stale after a re-run; they typed the wrong thing; got "password
#      authentication failed for user 'postgres'"; and were locked out
#      until they remembered to `gcloud sql users set-password`.
#
#   3. Re-runs in the same shell didn't pick up the LATEST password
#      from Secret Manager — operators ended up with three different
#      "current" passwords across local env, secret v1, and SQL.
#
# What this script does, in order, idempotently:
#   • Validates $PROJECT_ID + $REGION (fail-fast).
#   • Creates Cloud SQL instance if absent, with --edition=ENTERPRISE
#     pinned so db-custom-2-7680 keeps working.
#   • Creates the database if absent.
#   • Creates the app user (dma_insights — the canonical Terraform
#     convention; see main.tf + post_migrate.py) if absent. Pulls the
#     CURRENT app password from `dma-insights-database-url` secret
#     version=latest; if the secret doesn't exist yet, generates a
#     fresh password + writes secret v1.
#   • Rotates the postgres (superuser) password to a fresh value AND
#     destroys all prior versions of `dma-insights-pg-superuser-pw`.
#     Every re-run produces a NEW password + the old ones go away,
#     so an operator can't accidentally authenticate with a stale one.
#   • Persists DATABASE_URL (asyncpg) + DATABASE_URL_SYNC (psycopg)
#     secrets at version=latest (idempotent — adds a version if the
#     password rotated this run).
#   • Writes `~/.dma-pg-superuser-pw` (mode 0600) with the CURRENT
#     superuser password so future psql invocations + setup-pg-
#     extensions.sh pick it up via $PGPASSWORD without prompting.
#   • Verifies the password actually works via a live psql round-trip
#     through cloud-sql-proxy.
#
# Persistence across sessions: the script ALWAYS pulls the current
# password from Secret Manager (not local env). Secret Manager IS the
# durable source of truth — your shell can disappear and the next
# session still picks up the right password. The local
# `~/.dma-pg-superuser-pw` cache is just a perf optimization; if
# missing or stale, the script re-fetches it.
#
# Usage:
#   PROJECT_ID=… REGION=us-central1 \
#     bash apps/dma-insights/infra/setup-cloud-sql.sh
#
#   # Re-run later — picks up the latest password, rotates if needed:
#   bash apps/dma-insights/infra/setup-cloud-sql.sh
#
#   # In any subsequent session, source the password cache so psql
#   # works without prompting:
#   source ~/.dma-pg-superuser-pw
#   psql -h 127.0.0.1 -p 5432 -U postgres -d dma_insights -c '\dt'
set -euo pipefail
export GODEBUG=netdns=go

INSTANCE_NAME="${INSTANCE_NAME:-dma-insights-pg}"
DB_NAME="${DB_NAME:-dma_insights}"
# Canonical app user MUST match Terraform (main.tf creates `dma_insights`)
# and post_migrate.py (grants to `dma_insights`). A prior default of
# `dma_insights_app` here is what drifted the live DSN secret away from the
# granted user — causing Phase-4 /readyz 503 "app user lacks SELECT on
# alembic_version" (the grants landed on dma_insights, the app connected as
# dma_insights_app). Keep this in lockstep; fix an already-drifted secret
# with `recover-db-passwords.sh --rotate`.
APP_USER="${APP_USER:-dma_insights}"
TIER="${TIER:-db-custom-2-7680}"
EDITION="${EDITION:-ENTERPRISE}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-}"

SECRET_SUPER="dma-insights-pg-superuser-pw"
SECRET_APP_DSN="dma-insights-database-url"
SECRET_APP_DSN_SYNC="dma-insights-database-url-sync"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo 'FATAL: PROJECT_ID not set.' >&2
  echo '  Run:  gcloud config set project <PROJECT_ID>  OR  export PROJECT_ID=...' >&2
  exit 2
fi
if [[ -z "$REGION" ]]; then
  echo 'FATAL: REGION not set (e.g. us-central1).' >&2
  exit 2
fi

echo "→ Cloud SQL setup"
echo "  PROJECT_ID    = $PROJECT_ID"
echo "  REGION        = $REGION"
echo "  INSTANCE_NAME = $INSTANCE_NAME"
echo "  DB_NAME       = $DB_NAME"
echo "  APP_USER      = $APP_USER"
echo "  TIER          = $TIER  (edition=$EDITION)"
echo ""

# ── Helper: read latest version of a Secret Manager secret. Returns
#    empty string if the secret doesn't exist yet. Never raises so
#    the caller can `[[ -z "$pw" ]] && generate-and-create`.
_read_secret() {
  gcloud secrets versions access latest --secret="$1" --project="$PROJECT_ID" 2>/dev/null || true
}

# ── Helper: write a NEW version of a secret + destroy ALL prior
#    versions so the old password can never be used again. Idempotent
#    on the "already-up-to-date" case.
_rotate_secret() {
  local secret="$1" payload="$2"
  if ! gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1; then
    printf '%s' "$payload" | gcloud secrets create "$secret" \
      --data-file=- --replication-policy=automatic \
      --project="$PROJECT_ID" >/dev/null
    echo "  ✓ created secret $secret v1"
  else
    local current
    current="$(_read_secret "$secret")"
    if [[ "$current" == "$payload" ]]; then
      echo "  ✓ secret $secret already at latest payload — skipping"
      return 0
    fi
    printf '%s' "$payload" | gcloud secrets versions add "$secret" \
      --data-file=- --project="$PROJECT_ID" >/dev/null
    echo "  ✓ added new version to $secret"
    # Destroy ALL prior versions so a stale token can't authenticate.
    # The version we JUST added is now `latest`; everything else dies.
    gcloud secrets versions list "$secret" --project="$PROJECT_ID" \
      --filter="state:ENABLED" --format='value(name)' 2>/dev/null \
      | while read -r ver; do
          [[ -z "$ver" ]] && continue
          # Skip the latest (the one we just added).
          local latest_ver
          latest_ver="$(gcloud secrets versions list "$secret" \
                        --project="$PROJECT_ID" --limit=1 \
                        --format='value(name)' 2>/dev/null)"
          if [[ "$ver" != "$latest_ver" ]]; then
            gcloud secrets versions destroy "$ver" --secret="$secret" \
              --project="$PROJECT_ID" --quiet >/dev/null 2>&1 || true
          fi
        done
    echo "  ✓ destroyed all prior versions of $secret (only latest is reachable)"
  fi
}

# ── 1. Cloud SQL instance ───────────────────────────────────────────
echo "[1/6] Ensure Cloud SQL instance '$INSTANCE_NAME' in $REGION"
if gcloud sql instances describe "$INSTANCE_NAME" \
     --project="$PROJECT_ID" --format='value(name)' >/dev/null 2>&1; then
  echo "  ✓ already exists — skipping create"
else
  SUPERUSER_PW="$(openssl rand -hex 24)"
  echo "  → creating (edition=$EDITION tier=$TIER pg16)..."
  # --edition=ENTERPRISE keeps db-custom-* tiers working. Without it,
  # recent Cloud SQL projects default to ENTERPRISE_PLUS which rejects
  # db-custom-* with "Use a predefined Tier like db-perf-optimized-N-*".
  gcloud sql instances create "$INSTANCE_NAME" \
    --database-version=POSTGRES_16 \
    --edition="$EDITION" \
    --tier="$TIER" \
    --region="$REGION" \
    --root-password="$SUPERUSER_PW" \
    --storage-size=20 \
    --storage-type=SSD \
    --availability-type=ZONAL \
    --enable-google-private-path \
    --project="$PROJECT_ID"
  # Persist immediately so a Ctrl-C between create + secret-write
  # doesn't lose the password forever.
  _rotate_secret "$SECRET_SUPER" "$SUPERUSER_PW"
fi

# ── 2. Database ─────────────────────────────────────────────────────
echo ""
echo "[2/6] Ensure database '$DB_NAME'"
if gcloud sql databases describe "$DB_NAME" --instance="$INSTANCE_NAME" \
     --project="$PROJECT_ID" --format='value(name)' >/dev/null 2>&1; then
  echo "  ✓ already exists — skipping create"
else
  gcloud sql databases create "$DB_NAME" --instance="$INSTANCE_NAME" \
    --project="$PROJECT_ID"
fi

# ── 3. Rotate the postgres (superuser) password EVERY RUN ──────────
# Every re-run sets a fresh password + destroys all prior versions.
# This is the contract that solves the "stale password" recurrence:
# after this step, ONLY the value in Secret Manager (and ~/.dma-pg-
# superuser-pw) authenticates as postgres. Anyone with the prior
# password is locked out.
echo ""
echo "[3/6] Rotate postgres (superuser) password + revoke old"
NEW_SUPERUSER_PW="$(openssl rand -hex 24)"
gcloud sql users set-password postgres --instance="$INSTANCE_NAME" \
  --password="$NEW_SUPERUSER_PW" --project="$PROJECT_ID" >/dev/null
_rotate_secret "$SECRET_SUPER" "$NEW_SUPERUSER_PW"
SUPERUSER_PW="$NEW_SUPERUSER_PW"

# ── 4. App user + DSN secrets ───────────────────────────────────────
echo ""
echo "[4/6] Ensure app user '$APP_USER' + DSN secrets"
INSTANCE_CONN="$(gcloud sql instances describe "$INSTANCE_NAME" \
  --format='value(connectionName)' --project="$PROJECT_ID")"

EXISTING_DSN="$(_read_secret "$SECRET_APP_DSN")"
if [[ -n "$EXISTING_DSN" ]]; then
  # Extract the password from the existing DSN so we don't pointlessly
  # rotate it. App-password rotation has its own playbook
  # (recover-db-passwords.sh --rotate) — don't conflate it with this
  # superuser-password rotation.
  APP_PW="$(printf '%s' "$EXISTING_DSN" \
    | sed -nE 's#^postgresql\+asyncpg://[^:]+:([^@]+)@.*#\1#p')"
  if [[ -n "$APP_PW" ]]; then
    echo "  ✓ reusing app password from $SECRET_APP_DSN"
  fi
fi
if [[ -z "${APP_PW:-}" ]]; then
  APP_PW="$(openssl rand -hex 24)"
  echo "  → generated new app password (no existing DSN secret)"
fi

# Create the user OR update its password (idempotent — gcloud SQL
# user create errors on duplicate; the `set-password` path covers
# both fresh-create and password-rotation).
if gcloud sql users describe "$APP_USER" --instance="$INSTANCE_NAME" \
     --project="$PROJECT_ID" --format='value(name)' >/dev/null 2>&1; then
  gcloud sql users set-password "$APP_USER" --instance="$INSTANCE_NAME" \
    --password="$APP_PW" --project="$PROJECT_ID" >/dev/null
  echo "  ✓ app user already exists — password set to current secret value"
else
  gcloud sql users create "$APP_USER" --instance="$INSTANCE_NAME" \
    --password="$APP_PW" --project="$PROJECT_ID" >/dev/null
  echo "  ✓ app user created"
fi

ASYNC_DSN="postgresql+asyncpg://${APP_USER}:${APP_PW}@/${DB_NAME}?host=/cloudsql/${INSTANCE_CONN}"
SYNC_DSN="postgresql+psycopg://${APP_USER}:${APP_PW}@/${DB_NAME}?host=/cloudsql/${INSTANCE_CONN}"
_rotate_secret "$SECRET_APP_DSN" "$ASYNC_DSN"
_rotate_secret "$SECRET_APP_DSN_SYNC" "$SYNC_DSN"

# ── 5. Persist superuser password to ~/.dma-pg-superuser-pw ─────────
# Auto-loaded by setup-pg-extensions.sh + any psql one-liner in the
# doc via `source ~/.dma-pg-superuser-pw`. Mode 0600 so it isn't
# world-readable. Persists across sessions because it's in $HOME.
echo ""
echo "[5/6] Cache the CURRENT superuser password for cross-session reuse"
ENV_FILE="${HOME}/.dma-pg-superuser-pw"
{
  printf '# Auto-generated by setup-cloud-sql.sh — current postgres password.\n'
  printf '# Always reflects Secret Manager latest. Re-run setup-cloud-sql.sh to rotate.\n'
  printf 'export PGPASSWORD=%q\n' "$SUPERUSER_PW"
  printf 'export DMA_PG_SUPERUSER_PW=%q\n' "$SUPERUSER_PW"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE" 2>/dev/null || true
echo "  ✓ wrote $ENV_FILE"
echo "    (mode 0600; source it to use psql/pg_isready without an interactive prompt)"

# ── 6. Verify the password actually authenticates ───────────────────
echo ""
echo "[6/6] Verify postgres password via cloud-sql-proxy"
if ! command -v /tmp/cloud-sql-proxy >/dev/null 2>&1 && [[ ! -x /tmp/cloud-sql-proxy ]]; then
  echo "  → downloading cloud-sql-proxy..."
  curl -fsSL -o /tmp/cloud-sql-proxy \
    https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.16.0/cloud-sql-proxy.linux.amd64
  chmod +x /tmp/cloud-sql-proxy
fi
PORT=15499
pkill -f "cloud-sql-proxy.*--port[= ]${PORT}" 2>/dev/null || true
/tmp/cloud-sql-proxy --port="$PORT" "$INSTANCE_CONN" \
  > /tmp/dma-sql-proxy.log 2>&1 &
PROXY_PID=$!
trap 'kill '"$PROXY_PID"' 2>/dev/null || true' EXIT
for _ in $(seq 1 15); do
  pg_isready -h 127.0.0.1 -p "$PORT" -U postgres >/dev/null 2>&1 && break
  sleep 1
done
# Single-statement SELECT via -c — never enters interactive mode, so
# no terminal-state issues even in non-TTY shells.
if PGPASSWORD="$SUPERUSER_PW" psql -h 127.0.0.1 -p "$PORT" -U postgres \
     -d "$DB_NAME" -tAc 'SELECT 1' >/dev/null 2>&1; then
  echo "  ✓ postgres authenticated cleanly (SELECT 1 returned)"
else
  echo "  ✗ postgres authentication FAILED — the proxy log:" >&2
  tail -20 /tmp/dma-sql-proxy.log >&2 || true
  exit 5
fi
kill "$PROXY_PID" 2>/dev/null || true
trap - EXIT

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Cloud SQL ready."
echo ""
echo "  Superuser password is in Secret Manager + cached at:"
echo "    $ENV_FILE   (mode 0600)"
echo ""
echo "  To use psql without an interactive prompt in any session:"
echo "    source $ENV_FILE"
echo "    psql -h 127.0.0.1 -p 5432 -U postgres -d $DB_NAME -c '\\dt'"
echo ""
echo "  Next: enable pgvector + pg_trgm + pgcrypto extensions:"
echo "    bash \"\$(git rev-parse --show-toplevel)/apps/dma-insights/infra/setup-pg-extensions.sh\""
echo "═══════════════════════════════════════════════════════════════"
