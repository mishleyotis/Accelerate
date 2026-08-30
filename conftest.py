"""Repo-root conftest: make the DB-backed suites RUNNABLE, not skippable.

Every fixture that reaches Postgres in `apps/worker`, `apps/mcp` and
`apps/api` guards with `pytest.skip("no migrated local database")`. CI's
`python-tests` job runs with no Postgres service, so all of them skipped —
30-plus modules covering the promote transaction, the enrichment ledger,
the retained-verdict refusal and the redaction tests that run against the
real schema. They passed on a developer's machine and enforced nothing on
a pull request, which is the CHECK_NEVER_RAN_READS_AS_UNKNOWN shape one
layer up: green CI meant "not run", and nothing said so.

Measured 2026-08-19 against an empty database migrated to head: 1391
passed, 1 failed, 7 errors. All eight non-passes were ONE cause, and it is
not the catalogue's contents — `runs.ccg_catalog_version` carries an FK to
`ccg_versions(version)`, so a fixture inserting a run pinned to 'v7.0'
fails on a missing FK target. Insert the version row and the same database
returns 1397 passed, 3 skipped.

That distinction is the whole reason this file is small. The FK target is
an identifier, not catalogue data: no cells, no categories, no names, no
`is_current`. Nothing here can stand in for a catalogue or let a test pass
on invented catalogue content — a suite that needs cells still needs the
loader, and still skips without one.
"""
from __future__ import annotations

import os

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "apps" / "mcp"))

_DSN = os.environ.get(
    "LOCAL_DATABASE_URL",
    "postgresql://postgres:local@localhost:5432/dma_insights")

# The version the DB-backed fixtures pin runs to, and only that one. v5.0 is
# the HISTORICAL lineage version, but every test that reaches for it drives a
# fake connection rather than the database, so seeding it here would add a row
# no test needs and one more thing for a schema check to have an opinion about.
_FK_VERSIONS = ("v7.0",)


def _connect():
    import pg8000.dbapi
    from urllib.parse import urlparse
    u = urlparse(_DSN)
    return pg8000.dbapi.connect(
        host=u.hostname or "localhost", port=u.port or 5432,
        user=u.username or "postgres", password=u.password or "local",
        database=(u.path or "/dma_insights").lstrip("/"))


# The four service identities the DB-backed fixtures log in as. In production
# these are Cloud SQL IAM principals and no password exists; locally and in CI
# they are ordinary login roles, and the tests connect as them ON PURPOSE —
# asserting a grant works is the whole point of several of them.
_SERVICE_ROLES = (
    ("dmai-migrate@digital-maturity-assessor.iam", "svc_migrate"),
    ("dmai-worker@digital-maturity-assessor.iam", "svc_worker"),
    ("dmai-mcp@digital-maturity-assessor.iam", "svc_mcp"),
    ("dmai-api@digital-maturity-assessor.iam", "svc_api"),
)


def _seed_service_roles(conn):
    """CREATE the login roles, because roles are CLUSTER-scoped and a fresh
    Postgres has none.

    This is what actually cost 62 tests in CI, and it hid behind the same
    message as everything else. The fixtures connect as
    `dmai-worker@digital-maturity-assessor.iam` and friends; the migrations
    create the GROUP roles (`svc_worker`, `svc_mcp`, …) and grant to them, but
    the per-service LOGIN roles come from `infra/provision.sh` against Cloud
    SQL, which no test runner has ever run. On a developer's machine they
    happen to exist from an earlier setup, so every DB-backed test passed
    locally; on a fresh cluster the connect raised, the fixture's blanket
    `except` reported "no migrated local database", and the database was
    migrated perfectly. `Role "dmai-worker@…" does not exist` was in the
    service container's log the whole time, several hundred lines below where
    anyone was looking.

    Idempotent, and superuser-only — which the test runner is, and production
    is not: nothing here can run against Cloud SQL, where these identities are
    IAM principals with no password at all.
    """
    cur = conn.cursor()
    for login, group in _SERVICE_ROLES:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (login,))
        if not cur.fetchone():
            # `local` matches what every fixture in this repo passes, and the
            # password only exists on a throwaway cluster.
            cur.execute(f'CREATE ROLE "{login}" LOGIN PASSWORD \'local\'')
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (group,))
        if cur.fetchone():
            cur.execute(f'GRANT "{group}" TO "{login}"')
    conn.commit()


def _seed_gate_registry(conn):
    """`gate_results.gate_id` has an FK onto `gate_registry`, and the registry
    is seeded at runtime by `ensure_gate_registry` rather than by a migration.

    So on a fresh database the row set exists only after something has run the
    connector. That made an api suite depend on an mcp suite having run first
    — invisible for as long as this whole class of test was skipped in CI, and
    the first thing to surface when it stopped being: `Key (gate_id)=(SG-S8)
    is not present in table "gate_registry"`, on the run where the tests began
    executing rather than skipping.

    Calling production's own seeder, never a hand-written row list: a fixture
    that wrote its own registry would let a gate pass here that the connector
    does not actually publish."""
    import dma_mcp.gates as gates
    gates.ensure_gate_registry(conn)
    conn.commit()


@pytest.fixture(scope="session", autouse=True)
def _catalogue_version_fk_targets():
    """Idempotent, and silent when there is no database — the per-suite
    skips stay in charge of that. `is_current` is deliberately left NULL:
    `ccg_versions_current_uq` is a unique index over `(true) WHERE
    is_current`, so claiming currency here would make a real catalogue load
    fail against a test artefact."""
    try:
        conn = _connect()
    except Exception:
        return
    try:
        cur = conn.cursor()
        for v in _FK_VERSIONS:
            cur.execute("INSERT INTO ccg_versions (version, loaded_at) "
                        "VALUES (%s, now()) ON CONFLICT (version) DO NOTHING",
                        (v,))
        conn.commit()
    except Exception:
        conn.rollback()          # a schema without the table is not our call
    # Roles first: the gate-registry seed and every DB-backed fixture below
    # need them, and a failure here is the one worth seeing rather than
    # swallowing into another skip.
    try:
        _seed_service_roles(conn)
    except Exception as exc:                       # noqa: BLE001
        print(f"conftest: could not create the service login roles ({exc}). "
              f"Every fixture that connects as one will report "
              f"'no migrated local database' whatever the database is.")
        conn.rollback()
    try:
        _seed_gate_registry(conn)
    except Exception:
        conn.rollback()
    finally:
        conn.close()
