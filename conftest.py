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

import pytest

_DSN = os.environ.get(
    "LOCAL_DATABASE_URL",
    "postgresql://postgres:local@localhost:5432/dma_insights")

# Versions the fixtures pin runs to. v5.0 is the HISTORICAL lineage version
# (charter adjudication, 2026-08-04); a run pinned to it must be insertable
# for the cross-version diff tests to be reachable at all.
_FK_VERSIONS = ("v7.0", "v5.0")


def _connect():
    import pg8000.dbapi
    from urllib.parse import urlparse
    u = urlparse(_DSN)
    return pg8000.dbapi.connect(
        host=u.hostname or "localhost", port=u.port or 5432,
        user=u.username or "postgres", password=u.password or "local",
        database=(u.path or "/dma_insights").lstrip("/"))


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
    finally:
        conn.close()
