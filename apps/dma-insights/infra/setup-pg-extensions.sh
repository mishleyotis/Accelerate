#!/usr/bin/env bash
# Enable the pgvector + pg_trgm + pgcrypto extensions on the Cloud SQL
# Postgres instance — one-time, idempotent, NO INTERACTIVE PROMPT.
#
# Auth resolution order (the operator never types a password):
#   1. $PGPASSWORD if already exported
#   2. `source ~/.dma-pg-superuser-pw` (written by setup-cloud-sql.sh)
#   3. Pull live from Secret Manager `dma-insights-pg-superuser-pw`
# Falls back to a fatal error before connecting if all three fail —
# better than hanging on `gcloud sql connect`'s interactive prompt.
#
# Replaces the original `gcloud sql connect ... <<EOF` heredoc which
# was both a paste hazard AND would interactively prompt for the
# postgres password every time (the 2026-05-31 recurrence).
set -euo pipefail
export GODEBUG=netdns=go

INSTANCE_NAME="${INSTANCE_NAME:-dma-insights-pg}"
DB_NAME="${DB_NAME:-dma_insights}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
SECRET_SUPER="${SECRET_SUPER:-dma-insights-pg-superuser-pw}"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo 'FATAL: PROJECT_ID not set — gcloud config set project <id>' >&2
  exit 2
fi

# ── Resolve the postgres password without prompting ─────────────────
if [[ -z "${PGPASSWORD:-}" ]]; then
  if [[ -r "${HOME}/.dma-pg-superuser-pw" ]]; then
    # shellcheck disable=SC1090
    source "${HOME}/.dma-pg-superuser-pw"
    echo "→ loaded postgres password from ~/.dma-pg-superuser-pw"
  fi
fi
if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "→ pulling postgres password from Secret Manager ($SECRET_SUPER)…"
  PGPASSWORD="$(gcloud secrets versions access latest \
                --secret="$SECRET_SUPER" --project="$PROJECT_ID" 2>/dev/null || true)"
fi
if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "FATAL: couldn't resolve postgres password." >&2
  echo "  Either:" >&2
  echo "    • Run setup-cloud-sql.sh first (creates the secret + cache)" >&2
  echo "    • OR export PGPASSWORD=<the postgres password>" >&2
  exit 3
fi
export PGPASSWORD

# ── Bring up cloud-sql-proxy on a local port ────────────────────────
INSTANCE_CONN="$(gcloud sql instances describe "$INSTANCE_NAME" \
  --project="$PROJECT_ID" --format='value(connectionName)' 2>/dev/null)"
if [[ -z "$INSTANCE_CONN" ]]; then
  echo "FATAL: instance '$INSTANCE_NAME' not visible in project '$PROJECT_ID'" >&2
  exit 4
fi

if [[ ! -x /tmp/cloud-sql-proxy ]]; then
  echo "→ downloading cloud-sql-proxy…"
  curl -fsSL -o /tmp/cloud-sql-proxy \
    https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.16.0/cloud-sql-proxy.linux.amd64
  chmod +x /tmp/cloud-sql-proxy
fi
PORT="${PORT:-15433}"
pkill -f "cloud-sql-proxy.*--port[= ]${PORT}" 2>/dev/null || true
/tmp/cloud-sql-proxy --port="$PORT" "$INSTANCE_CONN" \
  > /tmp/dma-pg-ext-proxy.log 2>&1 &
PROXY_PID=$!
trap 'kill '"$PROXY_PID"' 2>/dev/null || true' EXIT

for _ in $(seq 1 20); do
  pg_isready -h 127.0.0.1 -p "$PORT" -U postgres >/dev/null 2>&1 && break
  sleep 1
done
if ! pg_isready -h 127.0.0.1 -p "$PORT" -U postgres >/dev/null 2>&1; then
  echo "FATAL: cloud-sql-proxy never accepted connections. Log:" >&2
  tail -20 /tmp/dma-pg-ext-proxy.log >&2
  exit 5
fi

# ── Enable extensions via psql + verify ────────────────────────────
# pgvector  — embedding columns (evidence_, section_, insight_, ...)
# pg_trgm   — trigram matching in alert.assigned_to + parser fuzzy
# pgcrypto  — gen_random_uuid() / digest() (content_hash backfill)
PSQL=(psql -h 127.0.0.1 -p "$PORT" -U postgres -d "$DB_NAME")
for ext in vector pg_trgm pgcrypto; do
  echo "→ ensure extension '$ext'…"
  "${PSQL[@]}" -tAc "CREATE EXTENSION IF NOT EXISTS ${ext};" >/dev/null
done

echo ""
echo "→ extensions present (+ versions):"
"${PSQL[@]}" -c \
  "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm','pgcrypto') ORDER BY extname;"

echo ""
echo "✓ extensions in place. (Expect: pgcrypto, pg_trgm, vector >= 0.6)"
