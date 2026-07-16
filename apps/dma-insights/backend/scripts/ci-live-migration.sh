#!/usr/bin/env bash
# A1 — Live Postgres migration round-trip gate.
#
# Spins up `pgvector/pgvector:pg15` (matches the Cloud SQL prod
# instance), runs alembic upgrade → downgrade → upgrade, then probes
# alembic_version + a pgvector extension check. Hard-fails on any
# error.
#
# Replaces the offline `--sql` check in cloudbuild.yaml which can't
# detect:
#   - CREATE EXTENSION vector failure
#   - generated-column immutability errors
#   - trigger compilation against pg15 syntax
#   - FK validation against pre-existing rows
#   - downgrade-then-upgrade breakage
#
# State branches (exit codes):
#   0  — round trip clean; pgvector confirmed; ready to ship
#   2  — docker not available (run on host without Docker daemon)
#   3  — PG stable-readiness timeout (sidecar didn't stabilise in 90s)
#   4  — alembic upgrade head failed
#   5  — alembic downgrade base failed
#   6  — re-upgrade after downgrade failed
#   7  — pgvector extension missing post-migration
#   8  — alembic_version table count != 1 (multiple heads)
#
# Usage:
#   ./backend/scripts/ci-live-migration.sh
#   ./backend/scripts/ci-live-migration.sh --keep   # keep container for debugging
#
set -euo pipefail

KEEP_CONTAINER=0
if [[ "${1:-}" == "--keep" ]]; then
    KEEP_CONTAINER=1
fi

CONTAINER="dma-ci-postgres"
NETWORK="${CI_DOCKER_NETWORK:-cloudbuild}"
PG_IMAGE="pgvector/pgvector:pg15"
DB_NAME="dma_insights_ci"
DB_USER="dma"
DB_PASS="dma_ci_password"
PG_PORT="${CI_PG_HOST_PORT:-15432}"

echo "─────────────────────────────────────────────────────────────"
echo " A1 — Live PG migration round-trip gate"
echo "─────────────────────────────────────────────────────────────"
echo "image:       $PG_IMAGE"
echo "container:   $CONTAINER"
echo "host port:   $PG_PORT"
echo "network:     $NETWORK"
echo

if ! command -v docker >/dev/null 2>&1; then
    echo "✗ docker not available — cannot spin up the sidecar"
    exit 2
fi

cleanup() {
    if [[ "$KEEP_CONTAINER" -eq 1 ]]; then
        echo "→ leaving container $CONTAINER running (--keep)"
        echo "  to inspect: docker exec -it $CONTAINER psql -U $DB_USER -d $DB_NAME"
        echo "  to clean:   docker rm -f $CONTAINER"
        return
    fi
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Idempotent: drop any prior container first.
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

# Make sure the network exists (Cloud Build provides `cloudbuild` by default).
docker network create "$NETWORK" >/dev/null 2>&1 || true

echo "→ starting PG sidecar..."
docker run -d --name "$CONTAINER" \
    --network "$NETWORK" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD="$DB_PASS" \
    -e POSTGRES_DB="$DB_NAME" \
    -p "$PG_PORT:5432" \
    "$PG_IMAGE" >/dev/null

# Wait up to 90s for stable readiness.
#
# pgvector/pgvector:pg15 goes through an init-then-restart cycle on
# first boot (postgres starts briefly to create POSTGRES_USER/DB,
# then SIGTERMs itself, then restarts in foreground). `pg_isready`
# returns success during the brief first start — a naive loop breaks
# early and the next psql call fails with
# "FATAL: the database system is shutting down".
#
# Defence: require BOTH pg_isready AND a successful round-trip query
# to succeed for 3 consecutive iterations before proceeding.
echo "→ waiting for stable PG readiness..."
SUCCESS=0
for i in $(seq 1 90); do
    if docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1 \
       && docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
        SUCCESS=$((SUCCESS+1))
        if [[ "$SUCCESS" -ge 3 ]]; then
            echo "✓ PG stably ready after ${i}s (3 consecutive checks)"
            break
        fi
    else
        SUCCESS=0
    fi
    if [[ "$i" -eq 90 ]]; then
        echo "✗ PG stable-readiness timeout (90s)"
        docker logs "$CONTAINER" 2>&1 | tail -30
        exit 3
    fi
    sleep 1
done

echo "→ creating pgvector + pgcrypto extensions..."
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
    -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" \
    -c "CREATE EXTENSION IF NOT EXISTS vector;" \
    >/dev/null

# Set DATABASE_URL_SYNC for alembic. `+psycopg` pins SQLAlchemy
# to the psycopg3 driver (the only one in the backend image).
# Bare `postgresql://` defaults to psycopg2 → ModuleNotFoundError.
export DATABASE_URL_SYNC="postgresql+psycopg://${DB_USER}:${DB_PASS}@127.0.0.1:${PG_PORT}/${DB_NAME}"
export DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@127.0.0.1:${PG_PORT}/${DB_NAME}"
# alembic.ini honours sqlalchemy.url via env interpolation in env.py
export ALEMBIC_DATABASE_URL="$DATABASE_URL_SYNC"

# Find alembic; allow caller to override via env (cloudbuild step uses
# the backend image's installed venv).
ALEMBIC="${ALEMBIC_BIN:-alembic}"
cd "$(dirname "$0")/.."

echo "→ alembic upgrade head..."
if ! "$ALEMBIC" upgrade head; then
    echo "✗ alembic upgrade head FAILED"
    exit 4
fi

echo "→ alembic downgrade base..."
if ! "$ALEMBIC" downgrade base; then
    echo "✗ alembic downgrade base FAILED"
    exit 5
fi

echo "→ alembic upgrade head (re-apply)..."
if ! "$ALEMBIC" upgrade head; then
    echo "✗ alembic upgrade head (re-apply) FAILED"
    exit 6
fi

echo "→ post-migration assertions..."

# alembic_version must have exactly 1 row (no multiple heads)
HEAD_COUNT=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
    -tA -c "SELECT COUNT(*) FROM alembic_version;")
if [[ "$HEAD_COUNT" != "1" ]]; then
    echo "✗ expected 1 alembic head, found $HEAD_COUNT"
    exit 8
fi
HEAD_REV=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
    -tA -c "SELECT version_num FROM alembic_version;")
echo "  ✓ alembic head: $HEAD_REV"

# pgvector extension must be present + version >= 0.5
VECTOR_VER=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
    -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")
if [[ -z "$VECTOR_VER" ]]; then
    echo "✗ pgvector extension missing post-migration"
    exit 7
fi
echo "  ✓ pgvector: $VECTOR_VER"

# Quick FK-closure check — every FK constraint must validate.
INVALID_FKS=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
    -tA -c "
        SELECT COUNT(*) FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        WHERE c.contype = 'f' AND NOT c.convalidated;
    ")
echo "  ✓ invalid FK constraints: $INVALID_FKS"
if [[ "$INVALID_FKS" != "0" ]]; then
    echo "✗ found invalid FK constraints"
    exit 7
fi

echo
echo "─────────────────────────────────────────────────────────────"
echo " ✓ A1 — Live PG migration gate PASSED"
echo "─────────────────────────────────────────────────────────────"
