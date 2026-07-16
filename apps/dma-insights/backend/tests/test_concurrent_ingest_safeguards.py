"""Regression tests for the concurrent-ingest safeguards in
package_persist.

Operator mandate (2026-06): "As we are ingesting over 100 files, check
that the ingestion pipeline is robust enough. Check that it allows
concurrent ingestion and parsing without breaking the pipeline or
running into errors. Check that all safeguards are considered."

Race conditions covered:

  - Two concurrent ingests for the SAME `drive_folder_id` but with
    different display_ids would both pass the SELECT (no row matches),
    both INSERT INTO entities, and the second would hit the partial
    UNIQUE(drive_folder_id) index → IntegrityError aborts ingest.
    The advisory lock keyed on `dma_entity_upsert:{drive_folder_id}`
    serializes the entity-upsert path so the second waits + sees the
    first's row + reuses it.

  - Two concurrent ingests with the SAME `request_id` (re-uploaded zip
    via two browsers) would both pass the SELECT, both INSERT INTO
    runs, and the second would hit UNIQUE(request_id) → IntegrityError.
    The advisory lock keyed on `dma_run_upsert:{run_id}` serializes
    so the second sees the first's row and takes the UPDATE path.

These tests verify the lock SQL is emitted; the actual blocking
behavior is exercised by live-PG integration tests (gated on
SEED_CI_PG_URL).
"""
from __future__ import annotations


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows=None, scalar=None, rowcount=1):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar

    def mappings(self):
        return self


class _FakeSession:
    """Records every executed (sql_text, params); minimal-shape Results."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.committed = False

    async def execute(self, sql, params=None):
        sql_text = str(sql)
        self.calls.append((sql_text, dict(params or {})))

        # Insert-with-RETURNING paths need an id back.
        if "RETURNING id" in sql_text or "RETURNING id::text" in sql_text:
            return _Result(rows=[_Row(
                id="00000000-0000-0000-0000-000000000001",
            )])
        # Entity-or-run existence lookups → return None to take the
        # INSERT branch.
        if "WHERE drive_folder_id =" in sql_text or "WHERE request_id =" in sql_text:
            return _Result(rows=[])
        # Catalogue version check → return None to take the stub-insert.
        if "FROM ccg_catalog_versions WHERE version" in sql_text:
            return _Result(rows=[])
        # Existing-subcap count check → return 0 to trigger bootstrap.
        if "SELECT COUNT(*) FROM ccg_subcaps" in sql_text:
            return _Result(scalar=0)
        # Catalogue resolver fetch_subcap → return a resolved row.
        if "FROM ccg_subcaps" in sql_text and "WHERE version" in sql_text:
            return _Result(rows=[])
        # Platform readiness lookup pulls from subcap_scores.
        if "FROM subcap_scores" in sql_text:
            return _Result(rows=[])
        # Insight cards → none.
        if "FROM insight_cards" in sql_text:
            return _Result(rows=[])
        return _Result()

    async def commit(self):
        self.committed = True


class _RunManifest:
    def __init__(self, *, run_id="REQ-12345678", institution_name="Foo Bank",
                 subvertical_code="RB", subvertical_name="Retail Banking",
                 rubric_version="5.5", skill_version=None,
                 evidence_mode="public"):
        self.run_id = run_id
        self.institution_name = institution_name
        self.subvertical_code = subvertical_code
        self.subvertical_name = subvertical_name
        self.rubric_version = rubric_version
        self.skill_version = skill_version
        self.evidence_mode = evidence_mode


class _Pkg:
    def __init__(self, *, drive_folder_id="folder_abc",
                 institution_name="Foo Bank"):
        self.run_manifest = _RunManifest(institution_name=institution_name)
        self.parser_warnings: list[str] = []
        self.firmographics = None
        self.subcap_scores: list = []
        self.evidence: list = []
        self.issue_register: list = []
        self.recommendations: list = []
        self.peers: list = []
        self.tech_stack: list = []
        self.category_scores: list = []
        self.pillar_scores: list = []
        self.report_sections: list = []
        self.focus_areas: list = []
        # 2026-06-10 deploy-sim: persist_package now consumes these
        # IngestedPackage fields directly; the hand-rolled stub must
        # mirror the real schema's list defaults or persist AttributeErrors.
        self.timeline_events: list = []
        self.insight_cards: list = []
        self.caps_applied_log: list = []
        self.assumptions_register: list = []
        self.parser_observations: list = []
        self.audit_logs = None


def _calls_matching(session: _FakeSession, fragment: str) -> list[dict]:
    return [p for (s, p) in session.calls if fragment in s]


def test_entity_upsert_takes_advisory_lock_when_drive_folder_id_present() -> None:
    """The new advisory lock SQL fires BEFORE the entity SELECT FOR
    UPDATE so concurrent ingests for the same drive_folder_id
    serialize through the upsert. Without this, the race produces an
    IntegrityError on the partial UNIQUE(drive_folder_id) index."""
    import asyncio

    from app.services.parsers.package_persist import persist_package

    session = _FakeSession()
    asyncio.run(persist_package(
        session, _Pkg(),
        data_source="DRIVE_BACKFILL",
        drive_folder_id="folder_abc",
    ))
    lock_calls = _calls_matching(session, "pg_advisory_xact_lock")
    # Two locks fire: one keyed on drive_folder_id, one on request_id.
    keys = [c["dfid"] for c in lock_calls if "dfid" in c] + \
           [c["rid"] for c in lock_calls if "rid" in c]
    assert "dma_entity_upsert:folder_abc" in keys
    assert "dma_run_upsert:REQ-12345678" in keys


def test_run_upsert_takes_advisory_lock_when_no_drive_folder_id() -> None:
    """Manual /ingest/package uploads (no drive_folder_id) still get
    the request_id advisory lock so two concurrent re-uploads of the
    same zip serialize on the runs UPSERT."""
    import asyncio

    from app.services.parsers.package_persist import persist_package

    session = _FakeSession()
    asyncio.run(persist_package(
        session, _Pkg(),
        data_source="MANUAL_BACKFILL",
        drive_folder_id=None,
    ))
    lock_calls = _calls_matching(session, "pg_advisory_xact_lock")
    rid_keys = [c["rid"] for c in lock_calls if "rid" in c]
    assert "dma_run_upsert:REQ-12345678" in rid_keys
    # No entity lock because drive_folder_id is None.
    dfid_keys = [c["dfid"] for c in lock_calls if "dfid" in c]
    assert dfid_keys == []


def test_advisory_lock_sql_uses_hashtext_bigint_cast() -> None:
    """The advisory lock SQL must cast hashtext output to bigint to
    fit `pg_advisory_xact_lock`'s int8 parameter. Without the explicit
    cast PostgreSQL infers int4, which truncates hash collisions and
    raises type errors at runtime."""
    import asyncio

    from app.services.parsers.package_persist import persist_package

    session = _FakeSession()
    asyncio.run(persist_package(
        session, _Pkg(),
        data_source="DRIVE_BACKFILL",
        drive_folder_id="folder_abc",
    ))
    lock_sqls = [s for (s, _) in session.calls if "pg_advisory_xact_lock" in s]
    for sql in lock_sqls:
        assert "hashtext(:" in sql
        assert "::bigint" in sql
