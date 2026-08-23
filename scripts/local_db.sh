#!/usr/bin/env bash
# Stand up the database the DB-backed suites open, WITHOUT Docker.
#
# WHY THIS EXISTS. On 2026-08-23 four consecutive commits merged red. Each
# had been verified locally — `3047 passed` — and each failed CI with six
# errors in apps/mcp/tests/test_promote.py. Both numbers were honest: every
# DB-backed fixture in this repo guards its connect with
#
#     except Exception: pytest.skip("no migrated local database")
#
# so on a machine with no Postgres the promote transaction, the enrichment
# ledger, the retained-verdict refusal and the redaction tests against the
# real schema all report as dots. A local green and a CI red were the same
# suite measuring different programs, and the only place the difference
# showed was a pull request.
#
# docker-compose.yml is the documented path and it is the right one where a
# Docker daemon exists. In a Claude Code remote container it does not, which
# left no local path at all — hence this script, which builds the same
# database out of the distro's own Postgres.
#
# WHAT IT DOES, in the order CI does it:
#   1. postgresql-16 + pgvector (migration 0009 creates the vector extension
#      and the HNSW index; stock postgres cannot run it)
#   2. initdb into a throwaway cluster, trust auth, port 5432
#   3. CREATE DATABASE dma_insights, and a `local` password so the DSN every
#      fixture defaults to actually connects
#   4. infra/local/pg-init/01-iam-parity-users.sql — the four Cloud SQL IAM
#      identities as ordinary login roles. BEFORE alembic, because 0001
#      grants the group role to the member only `IF EXISTS`, and doing it
#      the other way round leaves four roles with no grants and a suite that
#      fails on permissions rather than skipping honestly. (conftest.py
#      seeds them too, and idempotently — this keeps the ordering right for
#      the grants.)
#   5. alembic upgrade head
#   6. prove it: the table count, through the driver the fixtures use
#
# The password is `local` and the cluster is disposable. Nothing here can
# run against Cloud SQL, where these identities are IAM principals with no
# password at all.
#
# Usage:
#   scripts/local_db.sh                 # bring one up; reuse if 5432 answers
#   scripts/local_db.sh --recreate      # tear the cluster down and rebuild
#   scripts/local_db.sh --start-only    # just start an existing cluster
#   LOCAL_DATABASE_URL=postgresql://postgres:local@localhost:5432/dma_insights \
#     python -m pytest apps/mcp/tests/ -q
#
# Idempotent on purpose. If 5432 already answers with a migrated
# dma_insights, this reuses it and says so rather than destroying a cluster
# somebody is mid-run against — the default has to be the safe one, because
# the recovery from the other default is "re-migrate and lose the state you
# were debugging".
set -euo pipefail

PGBIN=/usr/lib/postgresql/16/bin
PGDATA=${PGDATA:-/var/lib/postgresql/local-dma}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PGPASSWORD=local

need_root() {
  [ "$(id -u)" = "0" ] || { echo "run as root (initdb needs to su to postgres)"; exit 2; }
}

ensure_packages() {
  if [ ! -x "$PGBIN/initdb" ]; then
    echo "== installing postgresql-16"
    apt-get install -y --no-install-recommends postgresql-16 >/dev/null
  fi
  # pgvector ships separately and migration 0009 hard-requires it.
  if [ ! -f /usr/share/postgresql/16/extension/vector.control ]; then
    echo "== installing postgresql-16-pgvector"
    apt-get install -y --no-install-recommends postgresql-16-pgvector >/dev/null
  fi
}

start() {
  su postgres -c "PATH=$PGBIN:\$PATH pg_ctl -D $PGDATA \
    -o '-p 5432 -c listen_addresses=localhost' -l $PGDATA/server.log start -w"
}

if [ "${1:-}" = "--start-only" ]; then
  need_root; start; exit 0
fi

need_root
ensure_packages

# WHAT IS ALREADY ON 5432. Three cases and they are not interchangeable: a
# migrated dma_insights (reuse it), a reachable one that is not migrated
# (migrate it), and something else entirely (refuse — a script that drops a
# stranger's database to make room for its own is a worse bug than the one
# it fixes).
serving=no
if "$PGBIN/pg_isready" -h localhost -p 5432 -q 2>/dev/null; then serving=yes; fi

if [ "$serving" = yes ] && [ "${1:-}" != "--recreate" ]; then
  tables=$(psql -h localhost -U postgres -d dma_insights -tAc \
    "SELECT count(*) FROM pg_tables WHERE schemaname='public'" 2>/dev/null || echo unreachable)
  case "$tables" in
    unreachable)
      echo "port 5432 answers but dma_insights is not reachable as postgres/local."
      echo "That is not this repo's cluster. Stop it, or pass --recreate to"
      echo "rebuild \$PGDATA ($PGDATA) — this script will not drop it for you."
      exit 3 ;;
    ''|*[!0-9]*)
      echo "port 5432 answers with an unreadable table count ($tables); refusing"
      exit 3 ;;
  esac
  if [ "$tables" -ge 100 ]; then
    echo "== reusing the cluster already on 5432 ($tables public tables)"
    echo "   pass --recreate to rebuild from empty"
    SKIP_INIT=1
  else
    echo "== cluster on 5432 has $tables tables; migrating it rather than rebuilding"
    SKIP_INIT=1
  fi
fi

if [ "${SKIP_INIT:-0}" != "1" ]; then
  # FREE THE PORT FIRST, and name what is being stopped. initdb into $PGDATA
  # succeeds while another cluster holds 5432, and then pg_ctl fails with
  # "could not start server" and a hint three lines deep in a log file —
  # measured, twice. The running postmaster is asked for its own
  # data_directory rather than guessed at, so this can only stop a cluster it
  # could already connect to and identify.
  if "$PGBIN/pg_isready" -h localhost -p 5432 -q 2>/dev/null; then
    other=$(psql -h localhost -U postgres -d postgres -tAc "SHOW data_directory" 2>/dev/null || true)
    if [ -n "$other" ]; then
      echo "== stopping the cluster on 5432 ($other)"
      su postgres -c "PATH=$PGBIN:\$PATH pg_ctl -D '$other' stop -m immediate" >/dev/null 2>&1 || true
    else
      echo "port 5432 is held by something this script cannot identify."
      echo "Stop it and re-run; it will not be killed blind."
      exit 3
    fi
  fi
  echo "== cluster at $PGDATA"
  su postgres -c "PATH=$PGBIN:\$PATH pg_ctl -D $PGDATA stop -m immediate" >/dev/null 2>&1 || true
  rm -rf "$PGDATA"; mkdir -p "$PGDATA"
  chown postgres:postgres "$PGDATA"; chmod 700 "$PGDATA"
  su postgres -c "PATH=$PGBIN:\$PATH initdb -D $PGDATA -U postgres \
    --auth-local=trust --auth-host=trust" >/dev/null
  start

  psql -h localhost -U postgres -d postgres -q \
    -c "ALTER USER postgres PASSWORD 'local';" \
    -c "CREATE DATABASE dma_insights;"
fi

# The .sql is plain CREATE ROLE — right for CI, which always runs it against
# a fresh container, and fatal on a reused cluster. Guarded here rather than
# made conditional there: CI's copy is the one production parity is argued
# from, and it should keep failing loudly if it ever runs twice.
have=$(psql -h localhost -U postgres -d dma_insights -tAc \
       "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'dmai-%'" 2>/dev/null || echo 0)
if [ "$have" -lt 4 ]; then
  echo "== parity users (before alembic, so 0001's conditional grants fire)"
  psql -h localhost -U postgres -d dma_insights -q \
       -f "$ROOT/infra/local/pg-init/01-iam-parity-users.sql"
else
  echo "== parity users already present ($have)"
fi

echo "== alembic upgrade head"
( cd "$ROOT/migrations" \
  && pip install -q -r requirements.txt \
  && LOCAL_DATABASE_URL="postgresql+pg8000://postgres:local@localhost:5432/dma_insights" \
     python -m alembic upgrade head >/dev/null )

# THE PROOF, through the driver the fixtures use — not through psql. A
# database that is reachable, migrated, and reachable-but-different all look
# identical from a fixture's blanket `except`, so the check has to fail on
# its own terms here instead.
python - <<'PROOF'
import pg8000.dbapi
c = pg8000.dbapi.connect(host="localhost", port=5432, user="postgres",
                         password="local", database="dma_insights")
cur = c.cursor()
cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'")
n = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'dmai-%'")
roles = cur.fetchone()[0]
print(f"public tables: {n} · dmai login roles: {roles}")
if n < 100:
    raise SystemExit(f"only {n} tables — alembic did not reach head")
if roles != 4:
    raise SystemExit(f"{roles} of 4 parity roles — the fixtures log in as these")
PROOF

cat <<'DONE'

Ready. Run the suites CI runs, against the database CI runs them against:

  LOCAL_DATABASE_URL=postgresql://postgres:local@localhost:5432/dma_insights \
    python -m pytest apps/worker/tests/ apps/mcp/tests/ apps/api/tests/ \
      scripts/tests/ plugins/dma-insights/scripts/tests/ tests/skills/ \
      infra/jobs/tests/ -q -rs -rf

Expect 11 skipped or fewer — CI fails the build above 12.
DONE
