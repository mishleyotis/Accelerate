#!/usr/bin/env bash
# apps/dma-insights/backend/scripts/run-local-tests.sh
#
# Turnkey local backend test runner — replaces the fragile multi-line
# block in DEPLOYMENT.md §0.6c that required `sudo -u postgres`, manual
# `export` lines, and a hand-installed Postgres on :5432.
#
# What it does, with ZERO sudo and ZERO typed passwords:
#   1. Brings up the pgvector Postgres + Redis via docker compose
#      (creds + pgvector/pgcrypto/pg_trgm are baked into
#      docker-compose.yml + scripts/init-extensions.sql).
#   2. Creates an isolated `dma_insights_ci` database inside that
#      container (so the test suite never clobbers your dev DB) and
#      applies the 3 extensions — all via `docker compose exec`, no
#      host psql, no sudo.
#   3. Ensures a project venv (.venv) with the dev dependencies,
#      installing the EXACT pins from pyproject.toml (no duplicated
#      list to drift).
#   4. Exports every env var the suite needs — the local throwaway
#      password is baked in, never typed.
#   5. Runs `alembic upgrade head` then the full pytest suite.
#
# The connection + password are AUTO-PICKED: the script resolves
# whichever Postgres backend is available and wires the env for you.
#
# Usage:
#   bash backend/scripts/run-local-tests.sh                 # full suite
#   bash backend/scripts/run-local-tests.sh --reinstall     # force dep reinstall
#   bash backend/scripts/run-local-tests.sh -- -k auth -x   # passthrough to pytest
#   bash backend/scripts/run-local-tests.sh --no-db -- -k unit   # skip docker;
#                                                # use an already-running PG you
#                                                # pointed SEED_CI_PG_URL at
#
# Re-runnable + idempotent. Safe to invoke from any directory.
set -euo pipefail

# Force IPv4 DNS — Cloud Shell's NAT pool can drop IPv6 (same mitigation
# the other infra scripts use).
export GODEBUG=netdns=go

# ── Resolve repo paths absolutely (fixes the `cd apps/dma-insights/backend`
#    "No such file or directory" error when invoked from the wrong dir) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_DIR="$(cd "${BACKEND_DIR}/.." && pwd)"          # apps/dma-insights
COMPOSE_FILE="${APP_DIR}/docker-compose.yml"

# ── Local CI connection facts (throwaway — match docker-compose.yml) ──
PG_HOST="127.0.0.1"
PG_PORT="5433"          # docker-compose maps host 5433 → container 5432
PG_USER="dma_insights"
PG_PW="dma_insights_local"
PG_DB="dma_insights_ci" # isolated test DB (NOT the dev `dma_insights` db)

# ── Flags ─────────────────────────────────────────────────────────────
REINSTALL=false
SKIP_DB=false
PYTEST_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reinstall) REINSTALL=true; shift ;;
    --no-db)     SKIP_DB=true; shift ;;
    --)          shift; PYTEST_ARGS=("$@"); break ;;
    -h|--help)   grep '^#' "$0" | sed 's/^# \?//' | head -40; exit 0 ;;
    *)           PYTEST_ARGS+=("$1"); shift ;;
  esac
done

echo "→ DMA Insights — local backend test runner"
echo "  backend : $BACKEND_DIR"

# ── Pick a docker invocation that works WITHOUT interactive sudo ──────
# Tries, in order: plain docker → `sudo -n docker` (non-interactive, only
# if passwordless sudo is configured). Never prompts for a password.
DOCKER=()
resolve_docker() {
  if docker ps >/dev/null 2>&1; then
    DOCKER=(docker)
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker ps >/dev/null 2>&1; then
    DOCKER=(sudo -n docker)
  else
    return 1
  fi
  # docker compose v2 (subcommand) vs docker-compose v1 (standalone)
  if "${DOCKER[@]}" compose version >/dev/null 2>&1; then
    COMPOSE=("${DOCKER[@]}" compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker-compose version >/dev/null 2>&1; then
    COMPOSE=(sudo -n docker-compose)
  else
    return 1
  fi
  return 0
}

# python3 is required for the venv AND the DB-reachability probe below.
if ! command -v python3 >/dev/null 2>&1; then
  echo "FATAL: python3 not found on PATH (needed for the venv + DB probe)." >&2
  exit 2
fi

# ── TCP-probe a DSN's host:port ──────────────────────────────────────
# Uses the SYSTEM python3 (no venv, no psql/pg_isready needed). This is
# what stops a STALE inherited SEED_CI_PG_URL (e.g. a 127.0.0.1:5432 left
# over from an earlier manual attempt) from silently defeating the
# turnkey path: we only trust an external DSN that actually answers.
# Exit codes: 0 = reachable, 1 = TCP refused/timeout, 2 = un-probeable
# (unix-socket DSN or unparseable — caller decides what to do).
_db_reachable() {
  python3 - "$1" <<'PY' 2>/dev/null
import sys, socket
dsn = sys.argv[1]
if "://" not in dsn:
    sys.exit(2)
rest = dsn.split("://", 1)[1]
authority = rest.split("/", 1)[0].split("?", 1)[0]   # user:pw@host:port
hostpart = authority.split("@")[-1]                    # host:port
if not hostpart:                                       # unix-socket DSN
    sys.exit(2)
if ":" in hostpart:
    host, _, port = hostpart.rpartition(":")
    try:
        port = int(port)
    except ValueError:
        host, port = hostpart, 5432
else:
    host, port = hostpart, 5432
try:
    socket.create_connection((host, port), timeout=3).close()
except OSError:
    sys.exit(1)
sys.exit(0)
PY
}

# Mask the password in a DSN for safe display.
_mask_dsn() {
  printf '%s\n' "$1" | sed -E 's#(://[^:/@]+:)[^@]+@#\1***@#'
}

# ── Decide the DB backend ─────────────────────────────────────────────
# Priority:
#   --no-db          → operator's SEED_CI_PG_URL (must not be refused)
#   reachable SEED_CI_PG_URL → respect it (operator wired a working DB)
#   otherwise        → docker-compose Postgres (the turnkey default)
#
# CRITICAL (2026-05-29 fix): a STALE SEED_CI_PG_URL inherited from an
# earlier manual attempt (e.g. 127.0.0.1:5432 with nothing listening)
# must NOT be trusted blindly — that silently skipped the docker bring-up
# and made `alembic upgrade head` fail with "connection refused" on 5432.
# We TCP-probe the URL first and only honour it when it actually answers.
bring_up_docker() {
  if ! resolve_docker; then
    echo "FATAL: docker (with compose) is not available without a password," >&2
    echo "       and no reachable SEED_CI_PG_URL was provided." >&2
    echo "  Either:" >&2
    echo "    • install Docker + add yourself to the docker group, OR" >&2
    echo "    • start any Postgres 16 (with the vector/pgcrypto/pg_trgm" >&2
    echo "      extensions) and re-run with:" >&2
    echo "        SEED_CI_PG_URL='postgresql+asyncpg://user:pw@host:port/db' \\" >&2
    echo "          bash backend/scripts/run-local-tests.sh --no-db" >&2
    exit 2
  fi
  echo "  docker  : ${DOCKER[*]} / compose: ${COMPOSE[*]}"
  echo "→ Starting Postgres (pgvector) + Redis via docker compose…"
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" up -d postgres redis

  echo "→ Waiting for Postgres to accept connections…"
  ok=0
  for _ in $(seq 1 45); do
    if "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T postgres \
         pg_isready -U "$PG_USER" -d dma_insights >/dev/null 2>&1 \
       && "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T postgres \
         psql -U "$PG_USER" -d dma_insights -c 'SELECT 1' >/dev/null 2>&1; then
      ok=$((ok + 1))
      # Require 3 consecutive successes — defeats the init-then-restart
      # race the official image does on first boot.
      [[ "$ok" -ge 3 ]] && break
    else
      ok=0
    fi
    sleep 2
  done
  if [[ "$ok" -lt 3 ]]; then
    echo "FATAL: Postgres never became stable-ready. Logs:" >&2
    "${COMPOSE[@]}" -f "$COMPOSE_FILE" logs --tail=30 postgres >&2 || true
    exit 3
  fi

  echo "→ Ensuring isolated test DB '${PG_DB}' + extensions (no sudo)…"
  # POSTGRES_USER is a superuser in the official image, so CREATE
  # DATABASE / CREATE EXTENSION run over the compose exec without sudo.
  if ! "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T postgres \
        psql -U "$PG_USER" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${PG_DB}'" 2>/dev/null \
        | grep -q 1; then
    "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T postgres \
      psql -U "$PG_USER" -d postgres \
      -c "CREATE DATABASE ${PG_DB} OWNER ${PG_USER}" >/dev/null
    echo "  ✓ created database ${PG_DB}"
  else
    echo "  ✓ database ${PG_DB} already exists"
  fi
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "$PG_USER" -d "$PG_DB" \
    -c "CREATE EXTENSION IF NOT EXISTS vector;
        CREATE EXTENSION IF NOT EXISTS pgcrypto;
        CREATE EXTENSION IF NOT EXISTS pg_trgm;" >/dev/null
  echo "  ✓ vector + pgcrypto + pg_trgm present in ${PG_DB}"

  # Auto-pick the env — password baked in, never typed. HARD export so a
  # stale inherited DATABASE_URL/SYNC can't leak into alembic/pytest.
  export DATABASE_URL="postgresql+asyncpg://${PG_USER}:${PG_PW}@${PG_HOST}:${PG_PORT}/${PG_DB}"
  export DATABASE_URL_SYNC="postgresql+psycopg://${PG_USER}:${PG_PW}@${PG_HOST}:${PG_PORT}/${PG_DB}"
  export SEED_CI_PG_URL="$DATABASE_URL"
  export REDIS_URL="redis://127.0.0.1:6380/0"
}

if [[ "$SKIP_DB" == "true" ]]; then
  if [[ -z "${SEED_CI_PG_URL:-}" ]]; then
    echo "FATAL: --no-db requires SEED_CI_PG_URL to point at a reachable Postgres." >&2
    exit 2
  fi
  probe_rc=0; _db_reachable "$SEED_CI_PG_URL" || probe_rc=$?
  if [[ "$probe_rc" -eq 1 ]]; then
    echo "FATAL: --no-db given but SEED_CI_PG_URL refused the connection:" >&2
    echo "         $(_mask_dsn "$SEED_CI_PG_URL")" >&2
    echo "       Start that Postgres, fix the URL, or drop --no-db to use docker." >&2
    exit 2
  fi
  echo "  ℹ --no-db: using your SEED_CI_PG_URL ($(_mask_dsn "$SEED_CI_PG_URL"))"
  # Derive BOTH DSN forms from the URL we just probed — never inherit a
  # possibly-stale DATABASE_URL/SYNC from the environment.
  export DATABASE_URL="${SEED_CI_PG_URL/+psycopg:/+asyncpg:}"
  export DATABASE_URL_SYNC="${SEED_CI_PG_URL/+asyncpg:/+psycopg:}"
  export SEED_CI_PG_URL
else
  use_external=false
  if [[ -n "${SEED_CI_PG_URL:-}" ]]; then
    probe_rc=0; _db_reachable "$SEED_CI_PG_URL" || probe_rc=$?
    if [[ "$probe_rc" -eq 0 ]]; then
      use_external=true
    else
      echo "  ⚠ SEED_CI_PG_URL is set but NOT reachable ($(_mask_dsn "$SEED_CI_PG_URL"))."
      echo "    Ignoring the stale value and bringing up docker-compose Postgres."
      echo "    (To use that DB instead: start it, then re-run — or pass --no-db.)"
      # Clear inherited DB env so nothing stale leaks into alembic/pytest;
      # bring_up_docker hard-sets all of them.
      unset SEED_CI_PG_URL DATABASE_URL DATABASE_URL_SYNC
    fi
  fi
  if [[ "$use_external" == "true" ]]; then
    echo "  ℹ SEED_CI_PG_URL is set and reachable ($(_mask_dsn "$SEED_CI_PG_URL")) — using it"
    # Derive BOTH DSN forms from the probed URL — never inherit a
    # possibly-stale DATABASE_URL/SYNC from the environment.
    export DATABASE_URL="${SEED_CI_PG_URL/+psycopg:/+asyncpg:}"
    export DATABASE_URL_SYNC="${SEED_CI_PG_URL/+asyncpg:/+psycopg:}"
    export SEED_CI_PG_URL
  else
    bring_up_docker
  fi
fi

# Bearer keys so the security tests RUN their assertions (not skip).
export DMA_BOT_API_KEY="${DMA_BOT_API_KEY:-ci-bot-key}"
export RAG_API_BEARER_KEY="${RAG_API_BEARER_KEY:-ci-rag-key}"

# ── venv + dependencies (no `pip install -e .` — flat layout has
#    multiple top-level dirs which breaks setuptools auto-discovery;
#    install the exact pins from pyproject instead) ──────────────────
VENV="${BACKEND_DIR}/.venv"
if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "→ Creating venv at ${VENV}…"
  python3 -m venv "$VENV"
fi
PY="${VENV}/bin/python"

# Deps-fingerprint guard — auto-reinstall when pyproject deps change.
# Without this, a stale .venv (e.g. one built before a pin was added or
# an extra widened) silently keeps a broken install, producing
# `ModuleNotFoundError` at test-collection time even though `import
# pytest, alembic` still passes. 2026-05-29 regression: pyproject was
# updated to `pydantic[email]==2.9.2` but operators' existing .venvs
# kept plain pydantic + no email_validator → 5 test collection errors.
#
# The fingerprint hashes the sorted (runtime + dev + ocr) dep list. If
# pyproject changes ANY pin / extra / additional dep, the hash changes
# and the script reinstalls automatically.
DEPS_FP="${VENV}/.deps-fingerprint"
current_fp="$("$PY" - "$BACKEND_DIR/pyproject.toml" <<'PY'
import sys, tomllib, hashlib
data = tomllib.load(open(sys.argv[1], "rb"))
deps  = list(data["project"]["dependencies"])
deps += list(data["project"]["optional-dependencies"]["dev"])
deps += list(data["project"]["optional-dependencies"].get("ocr", []))
print(hashlib.sha256("\n".join(sorted(deps)).encode()).hexdigest())
PY
)"
stored_fp="$(cat "$DEPS_FP" 2>/dev/null || true)"

needs_install=false
$REINSTALL && needs_install=true
"${VENV}/bin/python" -c "import pytest, alembic" >/dev/null 2>&1 || needs_install=true
# Belt + braces: probe the modules that have historically been missed
# by a fingerprint-stale venv (email_validator is the 2026-05-29 case).
"${VENV}/bin/python" -c "import email_validator" >/dev/null 2>&1 || needs_install=true
if [[ "$current_fp" != "$stored_fp" ]]; then
  needs_install=true
  if [[ -n "$stored_fp" ]]; then
    echo "  ℹ pyproject deps changed since last install — refreshing the venv"
  fi
fi

if $needs_install; then
  echo "→ Installing backend deps (runtime + dev + ocr from pyproject.toml)…"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" - "$BACKEND_DIR/pyproject.toml" <<'PY'
import sys, tomllib, subprocess
data = tomllib.load(open(sys.argv[1], "rb"))
deps  = list(data["project"]["dependencies"])
deps += list(data["project"]["optional-dependencies"]["dev"])
# Include the ocr extra so deep_extract tests aren't quietly skipped
# and the local env matches the prod backend/worker Dockerfiles
# (which install these same packages). Cold install adds Pillow +
# pdf2image + pytesseract — pure-Python wheels, no system libs
# required at IMPORT time (only at runtime, where the codepath
# handles missing tesseract gracefully).
deps += list(data["project"]["optional-dependencies"].get("ocr", []))
subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *deps])
PY
  printf '%s\n' "$current_fp" > "$DEPS_FP"
  echo "  ✓ deps installed (fingerprint: ${current_fp:0:12}…)"
else
  echo "→ Deps present + fingerprint match (pass --reinstall to refresh)"
fi

# Safety net for `workers.*` imports: expose apps/dma-insights on the
# path so `import workers` resolves regardless of pytest import mode.
# (`app.*` resolves via tests/conftest.py's sys.path insert.)
export PYTHONPATH="${APP_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

# Drop a sourceable env file so the operator can re-run pytest by hand
# without re-deriving any of this.
ENV_FILE="${BACKEND_DIR}/.env.local-ci"
cat > "$ENV_FILE" <<EOF
# Auto-generated by run-local-tests.sh — \`source\` me to re-run pytest manually.
export DATABASE_URL="${DATABASE_URL}"
export DATABASE_URL_SYNC="${DATABASE_URL_SYNC}"
export SEED_CI_PG_URL="${SEED_CI_PG_URL}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/0}"
export DMA_BOT_API_KEY="${DMA_BOT_API_KEY}"
export RAG_API_BEARER_KEY="${RAG_API_BEARER_KEY}"
export PYTHONPATH="${APP_DIR}"
EOF
echo "  ✓ wrote ${ENV_FILE} (source it to re-run pytest by hand)"

# ── Migrate + run the suite ───────────────────────────────────────────
cd "$BACKEND_DIR"
echo "→ alembic upgrade head…"
"$PY" -m alembic upgrade head

echo "→ Running the full test suite (expect 0 skips for the DB/bearer-gated tests)…"
set +e
"$PY" -m pytest tests/ -q "${PYTEST_ARGS[@]}"
rc=$?
set -e

echo ""
if [[ $rc -eq 0 ]]; then
  echo "✓ Test suite passed."
else
  echo "✗ pytest exited $rc — see failures above."
fi
echo "  Re-run by hand (works from anywhere — uses absolute paths):"
echo "    cd \"${BACKEND_DIR}\" && source .env.local-ci && .venv/bin/python -m pytest tests/ -q"
exit $rc
