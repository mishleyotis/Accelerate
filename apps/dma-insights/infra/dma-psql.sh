#!/usr/bin/env bash
# Turnkey psql to the DMA Insights Cloud SQL Postgres — handles BOTH
# auth (password) AND connectivity (cloud-sql-proxy) in one command.
#
# The recurring confusion (2026-05-31): operators sourced
# ~/.dma-pg-superuser-pw (auth ✓) then ran `psql -h 127.0.0.1 -p 5432`
# and got "Connection refused" — because Cloud SQL is NOT directly
# reachable. Nothing listens on 5432 unless cloud-sql-proxy is running.
# The password solves auth; it does NOT start the proxy. This script
# does both, every time, then cleans up the proxy on exit.
#
# Auth resolution (never prompts), in order:
#   1. $PGPASSWORD if already exported
#   2. ~/.dma-pg-superuser-pw  (written by setup-cloud-sql.sh)
#   3. Secret Manager dma-insights-pg-superuser-pw (latest)
#   4. Secret Manager dma-insights-database-url-superuser (DSN form —
#      legacy; password parsed out of the URL)
#
# Usage:
#   bash apps/dma-insights/infra/dma-psql.sh                 # interactive shell
#   bash apps/dma-insights/infra/dma-psql.sh -c '\dt'        # one command
#   bash apps/dma-insights/infra/dma-psql.sh -c 'SELECT version, status FROM ccg_loader_runs ORDER BY loader_started_at DESC LIMIT 5;'
#   DB_USER=dma_insights_app bash .../dma-psql.sh -c 'SELECT 1'   # connect as the app user
#
# All args after the script name are passed straight to psql, so any
# psql flag works (-c, -f, -t, -A, --csv, etc.).
set -euo pipefail
export GODEBUG=netdns=go

INSTANCE_NAME="${INSTANCE_NAME:-dma-insights-pg}"
DB_NAME="${DB_NAME:-dma_insights}"
DB_USER="${DB_USER:-postgres}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-us-central1}"
PORT="${PORT:-5432}"   # local proxy port; default 5432 so the doc's psql line works

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo 'FATAL: PROJECT_ID not set — gcloud config set project <id>' >&2
  exit 2
fi

# ── Resolve the password (no prompt) ────────────────────────────────
if [[ -z "${PGPASSWORD:-}" && -r "${HOME}/.dma-pg-superuser-pw" && "$DB_USER" == "postgres" ]]; then
  # shellcheck disable=SC1090
  source "${HOME}/.dma-pg-superuser-pw"
fi
if [[ -z "${PGPASSWORD:-}" ]]; then
  if [[ "$DB_USER" == "postgres" ]]; then
    PGPASSWORD="$(gcloud secrets versions access latest \
      --secret=dma-insights-pg-superuser-pw --project="$PROJECT_ID" 2>/dev/null || true)"
    if [[ -z "$PGPASSWORD" ]]; then
      # Legacy fallback: parse the password out of the superuser DSN secret.
      dsn="$(gcloud secrets versions access latest \
        --secret=dma-insights-database-url-superuser --project="$PROJECT_ID" 2>/dev/null || true)"
      [[ -n "$dsn" ]] && PGPASSWORD="$(printf '%s' "$dsn" \
        | sed -nE 's#^postgresql\+(asyncpg|psycopg)://[^:]+:([^@]+)@.*#\2#p')"
    fi
  else
    # App user — parse from the app DSN secret.
    dsn="$(gcloud secrets versions access latest \
      --secret=dma-insights-database-url --project="$PROJECT_ID" 2>/dev/null || true)"
    [[ -n "$dsn" ]] && PGPASSWORD="$(printf '%s' "$dsn" \
      | sed -nE 's#^postgresql\+(asyncpg|psycopg)://[^:]+:([^@]+)@.*#\2#p')"
  fi
fi
if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "FATAL: couldn't resolve a password for user '$DB_USER'." >&2
  echo "  Run setup-cloud-sql.sh first, OR export PGPASSWORD=..." >&2
  exit 3
fi
export PGPASSWORD

# ── Connectivity: cloud-sql-proxy (the bit the operator kept missing) ─
INSTANCE_CONN="$(gcloud sql instances describe "$INSTANCE_NAME" \
  --project="$PROJECT_ID" --format='value(connectionName)' 2>/dev/null)"
if [[ -z "$INSTANCE_CONN" ]]; then
  echo "FATAL: instance '$INSTANCE_NAME' not visible in project '$PROJECT_ID'." >&2
  exit 4
fi

if [[ ! -x /tmp/cloud-sql-proxy ]]; then
  echo "→ downloading cloud-sql-proxy…" >&2
  curl -fsSL -o /tmp/cloud-sql-proxy \
    https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.16.0/cloud-sql-proxy.linux.amd64
  chmod +x /tmp/cloud-sql-proxy
fi

# If something's already listening on $PORT, assume a proxy is up and
# reuse it (don't double-bind). Otherwise start our own + clean up.
STARTED_PROXY=0
if ! pg_isready -h 127.0.0.1 -p "$PORT" >/dev/null 2>&1; then
  /tmp/cloud-sql-proxy --port "$PORT" "$INSTANCE_CONN" \
    > /tmp/dma-psql-proxy.log 2>&1 &
  PROXY_PID=$!
  STARTED_PROXY=1
  trap '[[ "$STARTED_PROXY" == "1" ]] && kill '"$PROXY_PID"' 2>/dev/null || true' EXIT
  for _ in $(seq 1 20); do
    pg_isready -h 127.0.0.1 -p "$PORT" >/dev/null 2>&1 && break
    sleep 1
  done
  if ! pg_isready -h 127.0.0.1 -p "$PORT" >/dev/null 2>&1; then
    echo "FATAL: cloud-sql-proxy never came up on :$PORT. Log:" >&2
    tail -20 /tmp/dma-psql-proxy.log >&2
    exit 5
  fi
fi

# ── Run psql with all passthrough args ──────────────────────────────
# No args → interactive shell. With args (-c/-f/...) → batch.
exec psql -h 127.0.0.1 -p "$PORT" -U "$DB_USER" -d "$DB_NAME" "$@"
