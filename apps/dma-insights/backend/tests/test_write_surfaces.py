"""B-7/B-8/B-9 write-surface tests (insight annotations, focus-area KPI
overrides, notifications) — migration 025.

Mirrors the repo's live-DB opt-in pattern (`test_seed_ci.py`): the
persistence checks run only when ``WRITE_SURFACES_PG_URL`` points to a real
Postgres that is already migrated to head. Without it, only the schema /
constraint contract is asserted statically so the file is never a no-op.

To run the live path locally:
    initdb + start PG, `alembic upgrade head`, then
    WRITE_SURFACES_PG_URL=postgresql+asyncpg://postgres@127.0.0.1:5432/dma \
      pytest tests/test_write_surfaces.py
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

LIVE_DB_URL = os.environ.get("WRITE_SURFACES_PG_URL", "")
_live = pytest.mark.skipif(
    not LIVE_DB_URL, reason="WRITE_SURFACES_PG_URL not set — live write-surface tests skipped"
)


# ── static contract (always runs) ─────────────────────────────────────────
def test_migration_025_declares_three_tables() -> None:
    from pathlib import Path

    mig = (
        Path(__file__).resolve().parents[1]
        / "alembic" / "versions" / "025_new_write_surfaces.py"
    ).read_text()
    for table in (
        "insight_annotations",
        "focus_area_kpi_overrides",
        "notifications",
    ):
        assert f'"{table}"' in mig, f"025 must create {table}"
    # down_revision must chain off the prior head
    assert 'down_revision = "024_post_commit_trigger"' in mig
    # downgrade must drop all three
    assert mig.count("op.drop_table(") == 3


def test_schemas_enforce_enums() -> None:
    """The Pydantic layer must reject out-of-domain enum values before they
    ever reach the DB CHECK constraints."""
    from pydantic import ValidationError

    from app.schemas.write_surfaces import (
        AnnotationIn,
        KpiOverrideIn,
    )

    # valid
    assert AnnotationIn(body="x", status="ACTIONED").status == "ACTIONED"
    assert KpiOverrideIn(kpi_label="L", source_mode="hidden").source_mode == "hidden"
    # invalid enum
    with pytest.raises(ValidationError):
        AnnotationIn(body="x", status="BOGUS")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        KpiOverrideIn(kpi_label="L", source_mode="BOGUS")  # type: ignore[arg-type]
    # body min length
    with pytest.raises(ValidationError):
        AnnotationIn(body="")


def test_health_version_diff_does_not_select_phantom_run_columns() -> None:
    """Regression guard (QA 2026-06): `runs` has NO `overall_score` /
    `pillar_scores` columns — both are computed from `subcap_scores`. A
    SELECT of those columns from `runs` 500s at runtime (the D6 Health
    "Diff" tab). The contract test only checks route registration, so this
    static guard catches the column reference returning."""
    from pathlib import Path

    health = (
        Path(__file__).resolve().parents[1] / "app" / "routers" / "health.py"
    ).read_text()
    # The version-diff query block must not pull these phantom columns
    # straight out of `runs`.
    assert "overall_score, pillar_scores" not in health, (
        "health.py selects phantom runs.overall_score/pillar_scores — "
        "compute from subcap_scores instead (AVG + LEFT(subcap_id,2))."
    )


# ── live persistence path ─────────────────────────────────────────────────
@_live
def test_write_surfaces_roundtrip_live() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def _run() -> None:
        engine = create_async_engine(LIVE_DB_URL)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        eid, rid, uid = (str(uuid.uuid4()) for _ in range(3))
        async with sm() as s:
            await s.execute(text(
                "INSERT INTO ccg_catalog_versions (version,released_at,source_sha256s,loader_run_id) "
                "VALUES ('v7.0',NOW(),'{}'::jsonb,gen_random_uuid()) ON CONFLICT (version) DO NOTHING"))
            await s.execute(text(
                "INSERT INTO entities (id,display_id,name,subvertical) "
                "VALUES (CAST(:i AS uuid),:d,:n,:sv)"),
                {"i": eid, "d": "ws-" + eid[:6], "n": "WS Bank", "sv": "REG_BANK"})
            await s.execute(text(
                "INSERT INTO runs (id,entity_id,request_id,status,data_source) "
                "VALUES (CAST(:i AS uuid),CAST(:e AS uuid),:r,'ACTIVE','PROJECT_API')"),
                {"i": rid, "e": eid, "r": "REQ-" + rid[:8]})
            await s.commit()

            # B-7
            st = (await s.execute(text(
                "INSERT INTO insight_annotations (run_id,entity_id,ic_id,author,role,body,status) "
                "VALUES (CAST(:r AS uuid),CAST(:e AS uuid),'IC-003','a@z.com','ANALYST','note','ACTIONED') "
                "RETURNING status"), {"r": rid, "e": eid})).scalar_one()
            assert st == "ACTIONED"

            # B-8 idempotent upsert
            for m in ("public", "client"):
                await s.execute(text(
                    "INSERT INTO focus_area_kpi_overrides (entity_id,fa_id,kpi_label,source_mode,updated_at) "
                    "VALUES (CAST(:e AS uuid),'FA-01','Adoption',:m,NOW()) "
                    "ON CONFLICT (entity_id,fa_id,kpi_label) DO UPDATE SET source_mode=EXCLUDED.source_mode"),
                    {"e": eid, "m": m})
            await s.commit()
            rows = (await s.execute(text(
                "SELECT count(*) FROM focus_area_kpi_overrides WHERE entity_id=CAST(:e AS uuid)"),
                {"e": eid})).scalar_one()
            assert rows == 1  # upsert, not duplicate

            # B-9 + mark-read
            await s.execute(text(
                "INSERT INTO notifications (user_id,kind,title) VALUES (CAST(:u AS uuid),'alert','t')"),
                {"u": uid})
            await s.commit()
            res = await s.execute(text(
                "UPDATE notifications SET seen_at=NOW() WHERE user_id=CAST(:u AS uuid) AND seen_at IS NULL"),
                {"u": uid})
            assert res.rowcount == 1
        await engine.dispose()

    asyncio.run(_run())


# ── migration 055: KPI evidence traceability read path ────────────────────
# The KPI strip must be able to open the exact evidence row a derived
# number was read from; pre-055 environments (no evidence_e_id column)
# must keep serving with the field defaulting to None.


class _KpiRow:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _KpiResult:
    def __init__(self, rows):
        self._rows = rows or []

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _KpiFakeSession:
    """Canned responses; optionally raises on SELECTs naming a column
    (simulates a pre-055 DB missing evidence_e_id)."""

    def __init__(self, responses, fail_on: str | None = None):
        self.responses = list(responses)
        self.fail_on = fail_on
        self.calls: list[str] = []

    def begin_nested(self):
        return _Nested()

    async def execute(self, sql, params=None):
        s = str(sql)
        self.calls.append(s)
        if self.fail_on and self.fail_on in s:
            raise RuntimeError(f'column "{self.fail_on}" does not exist')
        if self.responses:
            return _KpiResult(self.responses.pop(0))
        return _KpiResult([])


def test_kpi_override_out_defaults_evidence_e_id_none() -> None:
    from datetime import datetime

    from app.schemas.write_surfaces import KpiOverrideOut

    row = KpiOverrideOut(
        fa_id="a" * 32, kpi_label="STP rate", source_mode="public",
        updated_at=datetime(2026, 7, 6),
    )
    assert row.evidence_e_id is None


def test_list_kpi_overrides_serves_evidence_e_id() -> None:
    from datetime import datetime

    from app.routers.write_surfaces import list_kpi_overrides

    eid = str(uuid.uuid4())
    fake = _KpiFakeSession([
        [_KpiRow(id=eid)],                        # _resolve_entity
        [_KpiRow(fa_id="f" * 32, kpi_label="STP rate", source_mode="public",
                 current_value="18%", target_value=None,
                 evidence_e_id="E-014", updated_at=datetime(2026, 7, 6))],
    ])
    resp = asyncio.run(list_kpi_overrides(
        "acme-bank-0001", str(uuid.uuid4()), _user=None, session=fake,
    ))
    assert resp.items[0].evidence_e_id == "E-014"
    assert "evidence_e_id" in fake.calls[-1]


def test_list_kpi_overrides_pre055_fallback_keeps_serving() -> None:
    from datetime import datetime

    from app.routers.write_surfaces import list_kpi_overrides

    eid = str(uuid.uuid4())
    fake = _KpiFakeSession(
        [
            [_KpiRow(id=eid)],                    # _resolve_entity
            # first KPI select raises (fail_on) without consuming this:
            [_KpiRow(fa_id="f" * 32, kpi_label="STP rate",
                     source_mode="public", current_value="18%",
                     target_value=None, updated_at=datetime(2026, 7, 6))],
        ],
        fail_on="evidence_e_id",
    )
    resp = asyncio.run(list_kpi_overrides(
        "acme-bank-0001", str(uuid.uuid4()), _user=None, session=fake,
    ))
    assert len(resp.items) == 1
    assert resp.items[0].evidence_e_id is None    # honest default
