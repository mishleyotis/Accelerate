"""Regression test for asyncpg AmbiguousParameterError on the
job_executions INSERT path.

The operator reported on 2026-05-24:
  Failed to trigger drive_crawler: 500 ·
  {"detail":"job_executions INSERT failed: ProgrammingError:
   AmbiguousParameterError: could not determine data type"}

Root cause: the prior workaround used
  CASE WHEN :eid IS NULL THEN CAST(NULL AS uuid)
       ELSE CAST(:eid AS uuid) END
which references `:eid` twice — once in a boolean context (IS NULL),
once in a uuid context (CAST AS uuid). asyncpg can't unify the
parameter type across those two references and fails statement
preparation.

Fix: ONE reference, ONE explicit CAST.
  CAST(:eid AS uuid)
asyncpg + SQLAlchemy both correctly translate Python None → SQL
NULL when the parameter appears exactly once inside an explicit
CAST.

This test exercises the actual INSERT against a live Postgres (gated
by SEED_CI_PG_URL) so any future regression of the param-type
unification trips immediately rather than at the next admin click.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest

LIVE_DB_URL = os.environ.get("SEED_CI_PG_URL", "")
HAS_LIVE_DB = bool(LIVE_DB_URL)


pytestmark = pytest.mark.skipif(
    not HAS_LIVE_DB,
    reason="SEED_CI_PG_URL not set — live-PG regression test skipped",
)


@pytest.mark.asyncio
async def test_job_executions_insert_with_null_entity_id():
    """The bug-trigger case: entity_id=None on a drive_crawler INSERT."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    async_url = (
        LIVE_DB_URL if "+asyncpg" in LIVE_DB_URL
        else LIVE_DB_URL.replace("postgresql://", "postgresql+asyncpg://")
    )
    engine = create_async_engine(async_url)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("""
                    INSERT INTO job_executions (
                        job_name, mode, triggered_by_user_id, triggered_by_email,
                        trigger_source, status, entity_id, args
                    ) VALUES (
                        :name, :mode, CAST(:uid AS uuid), :email,
                        'admin_ui', 'running',
                        CAST(:eid AS uuid),
                        CAST(:args AS jsonb)
                    )
                    RETURNING id, entity_id
                """),
                {
                    "name": "drive_crawler", "mode": "full",
                    "uid": str(uuid.uuid4()),
                    "email": "regression-test@zennify.com",
                    "eid": None,
                    "args": json.dumps({}),
                },
            )
            row = result.first()
            assert row is not None
            assert row.entity_id is None, (
                f"expected NULL entity_id, got {row.entity_id}"
            )
            # Cleanup
            await conn.execute(
                text("DELETE FROM job_executions WHERE id = :i"),
                {"i": row.id},
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_job_executions_insert_with_real_entity_id():
    """Inverse case: entity_id=<UUID> on the same INSERT shape must
    also work (the original case from before any param-type issues)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    async_url = (
        LIVE_DB_URL if "+asyncpg" in LIVE_DB_URL
        else LIVE_DB_URL.replace("postgresql://", "postgresql+asyncpg://")
    )
    engine = create_async_engine(async_url)
    target_eid = str(uuid.uuid4())
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("""
                    INSERT INTO job_executions (
                        job_name, mode, triggered_by_user_id, triggered_by_email,
                        trigger_source, status, entity_id, args
                    ) VALUES (
                        :name, :mode, CAST(:uid AS uuid), :email,
                        'admin_ui', 'running',
                        CAST(:eid AS uuid),
                        CAST(:args AS jsonb)
                    )
                    RETURNING id, entity_id
                """),
                {
                    "name": "drive_crawler", "mode": "delta",
                    "uid": str(uuid.uuid4()),
                    "email": "regression-test@zennify.com",
                    "eid": target_eid,
                    "args": json.dumps({"force": True}),
                },
            )
            row = result.first()
            assert row is not None
            assert str(row.entity_id) == target_eid
            await conn.execute(
                text("DELETE FROM job_executions WHERE id = :i"),
                {"i": row.id},
            )
    finally:
        await engine.dispose()


def test_admin_router_uses_single_eid_reference():
    """Source-code assertion: the admin router must NOT have the
    `:eid IS NULL` boolean-context reference that originally caused
    the AmbiguousParameterError."""
    from pathlib import Path
    admin_py = (
        Path(__file__).resolve().parents[1] / "app" / "routers" / "admin.py"
    )
    # Allow `:eid IS NULL` to appear in inline comments (the docstring
    # documents the historic bug). Flag only when it appears in an
    # actual SQL statement — i.e. the line is not a comment.
    offending = [
        ln for ln in admin_py.read_text().splitlines()
        if ":eid IS NULL" in ln
        and not ln.lstrip().startswith("--")
        and "#" not in ln.split(":eid IS NULL")[0]
    ]
    assert not offending, (
        "admin.py reintroduced the `:eid IS NULL` workaround that "
        "trips asyncpg's AmbiguousParameterError. Use a single "
        "CAST(:eid AS uuid) reference instead. Offending line(s):\n"
        + "\n".join(offending)
    )
