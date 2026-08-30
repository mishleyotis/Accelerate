#!/usr/bin/env bash
# Bring up a local PostgreSQL that `tests/schema/` can actually run against.
#
#     infra/local/up.sh [--reset]
#
# WHY THIS EXISTS. `tests/schema/` is 47 tests that assert the things the
# build charter calls invariants — four bands on the RAW score with no fifth
# value in the enum, generated columns STORED not virtual, the api role denied
# on staging, a null published_date banding UNVERIFIED and never CURRENT, the
# active-run partial unique holding under concurrent insert. Every one of them
# needs a real PostgreSQL, and without one they do not fail: they ERROR, 22 of
# them, and the suite line reads "4332 passed, 22 errors" for months while
# nobody can say which invariant is unproven.
#
# docker-compose.yml is the documented way and it needs a docker daemon. This
# environment has the docker CLI and no daemon, which is the state a checker
# must handle rather than assume away — so this falls back to the system
# PostgreSQL 16 that is already installed, and says which path it took.
#
# It is idempotent: run it twice and the second run migrates an already
# migrated database and exits 0.
set -euo pipefail

RESET=0
[ "${1:-}" = "--reset" ] && RESET=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB=dma_insights
URL="postgresql+pg8000://postgres:local@localhost:5432/${DB}"
say() { printf '  %s\n' "$*"; }

echo "local database — bringing up PostgreSQL for tests/schema/"

# ---- 1 · a running server, by whichever route this machine offers --------
if docker info >/dev/null 2>&1; then
  say "docker daemon present — using docker-compose.yml (the documented path)"
  [ "$RESET" = 1 ] && docker compose down -v >/dev/null 2>&1 || true
  docker compose up -d db
  for _ in $(seq 1 30); do
    docker compose exec -T db pg_isready -U postgres >/dev/null 2>&1 && break
    sleep 2
  done
  MODE=docker
else
  say "no docker daemon — falling back to the system PostgreSQL 16"
  command -v pg_ctlcluster >/dev/null 2>&1 || {
    echo "FAILED: neither a docker daemon nor a system PostgreSQL 16." >&2
    echo "  install one: apt-get install -y postgresql-16" >&2
    exit 1; }

  # pgvector is not in the base postgres package and the schema needs it:
  # `vector`, plus the HNSW index the TRD creates once at migration.
  if [ ! -f /usr/share/postgresql/16/extension/vector.control ]; then
    say "installing postgresql-16-pgvector"
    apt-get install -y --no-install-recommends postgresql-16-pgvector >/dev/null
  fi

  if [ "$RESET" = 1 ]; then
    pg_ctlcluster 16 main stop >/dev/null 2>&1 || true
    rm -rf /var/lib/postgresql/16/main
    pg_createcluster 16 main >/dev/null
  fi
  # A data directory the image left group-readable refuses to start with
  # "invalid permissions", which reads as corruption and is a chmod.
  chmod 0700 /var/lib/postgresql/16/main 2>/dev/null || true
  pg_ctlcluster 16 main start >/dev/null 2>&1 || true
  for _ in $(seq 1 30); do
    su postgres -c "pg_isready" >/dev/null 2>&1 && break
    sleep 1
  done
  MODE=system
fi
say "server up (${MODE})"

# ---- 2 · the database, and the IAM-parity roles the grants need ----------
if [ "$MODE" = system ]; then
  PSQL() { su postgres -c "psql -v ON_ERROR_STOP=1 $*"; }
else
  PSQL() { docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres $*; }
fi
PSQL "-tAc \"ALTER ROLE postgres PASSWORD 'local'\"" >/dev/null
PSQL "-tAc \"SELECT 1 FROM pg_database WHERE datname='${DB}'\"" | grep -q 1 \
  || PSQL "-c 'CREATE DATABASE ${DB}'" >/dev/null
say "database ${DB} present"

# The migrations' role-membership grants are written against the Cloud SQL IAM
# user names; the same login roles locally are what make a grant behave
# identically in both places rather than being skipped here and enforced in
# production, which is the shape of a test that passes and proves nothing.
if [ "$MODE" = system ]; then
  su postgres -c "psql -q -d ${DB} -f ${REPO}/infra/local/pg-init/01-iam-parity-users.sql" \
    2>/dev/null || say "parity roles already present"
fi
say "IAM-parity roles present"

# ---- 3 · schema at head -------------------------------------------------
python3 -c "import alembic" 2>/dev/null || {
  say "installing migration dependencies"
  pip install -q -r "${REPO}/migrations/requirements.txt"
}
( cd "${REPO}/migrations" && LOCAL_DATABASE_URL="$URL" python3 -m alembic upgrade head >/dev/null )
say "schema at head"

# ---- 4 · say what is and is not provable ---------------------------------
cat <<EOF

  export LOCAL_DATABASE_URL="${URL}"
  python3 -m pytest tests/schema/ -q

The catalogue tests SKIP until a catalogue is loaded — they assert real counts
(851 cells, 16 categories, the v5->v7 resolution) that only the real workbooks
carry, so a synthetic one would make them assert against a fixture of
themselves. Load it with:

  python3 -m ccg_loader --version v7.0 --dir <the four pillar xlsx>

from gs://digital-maturity-assessor-catalogue-staging/v7.0/, which needs a
principal with storage.objects.list on that bucket.
EOF
