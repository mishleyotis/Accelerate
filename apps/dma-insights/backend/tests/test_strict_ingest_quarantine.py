"""Strict-gate quarantine wiring for the LOCAL --dir backfill path
(2026-06-10) + the PENDING_REVIEW persist policy for junk names.

Before this change the local --dir path left NO persistent record of
skipped/failed packages — stdout was the only audit trail, and
--retry-failed-only had nothing to re-pick. Now every local outcome
writes a backfill_quarantine row, and an UNSCORED package (strict
ingest gate) lands as `skipped_no_report` — the outcome class the
retry path re-picks once the scored deliverable lands in Drive.

The persist-side tests pin the junk-name policy: a scored package
whose resolved institution_name fails check_institution_name persists
with entities.status='PENDING_REVIEW' (admin queue; AE lists filter
status='ACTIVE'), and a junk re-ingest can never clobber a clean name.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import app.scripts.historical_backfill as hb

# `workers` lives at the app root (one level above backend/) — CI sets
# PYTHONPATH to include it; mirror that for bare local pytest runs.
_APP_ROOT = str(Path(__file__).resolve().parents[2])
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)


class _Result:
    def __init__(self, rows=None):
        self._rows = rows or []

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, params=None):
        self.calls.append((str(sql), dict(params or {})))
        return _Result()

    async def commit(self):
        pass


class _FakeSessionCtx:
    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return False


def test_local_dir_unscored_package_writes_skipped_no_report_quarantine(
    tmp_path, monkeypatch,
) -> None:
    pkg_dir = tmp_path / "Foo Bank - DMA"
    pkg_dir.mkdir()
    (pkg_dir / "run_manifest.json").write_text("{}")

    monkeypatch.setattr(hb, "_find_local_package_roots", lambda base: [pkg_dir])
    # Manifest computation is irrelevant to the gate — stub it cheap.
    import app.services.artifact_manifest as am
    monkeypatch.setattr(
        am, "compute_package_manifest",
        lambda root: SimpleNamespace(
            material_manifest_hash=None, entries=[],
            material_count=0, cosmetic_count=0, unknown_count=0,
        ),
    )
    session = _FakeSession()
    monkeypatch.setattr(hb, "get_sessionmaker", lambda: (lambda: _FakeSessionCtx(session)))
    # Parsed package with ZERO subcap scores but plenty of narrative —
    # the strict gate must skip it anyway.
    monkeypatch.setattr(
        hb, "parse_package",
        lambda root: SimpleNamespace(
            subcap_scores=[],
            report_sections=[object()] * 33,
            recommendations=[object()] * 5,
            evidence=[],
        ),
    )
    import workers._runner as runner
    monkeypatch.setattr(
        runner, "get_current_tracker",
        lambda: SimpleNamespace(execution_id="exec-123"),
    )
    captured: list[dict] = []

    def _recorder(run_id, drive_folder_id, folder_name, outcome,
                  reason, error_message, ingested_run_id):
        captured.append({
            "run_id": run_id, "drive_folder_id": drive_folder_id,
            "folder_name": folder_name, "outcome": outcome,
            "reason": reason,
        })

    monkeypatch.setattr(hb, "_write_quarantine_row", _recorder)

    counts = asyncio.run(hb._ingest_local_dir(tmp_path, force=True))

    assert counts["skipped_unscored"] == 1
    assert counts["ok"] == 0
    assert len(captured) == 1
    row = captured[0]
    assert row["outcome"] == "skipped_no_report"
    assert row["run_id"] == "exec-123"
    assert row["drive_folder_id"] == "local:Foo Bank - DMA"
    assert "0 subcap scores" in row["reason"]
    # The retry classifier must NOT mistake this for an idempotent skip.
    assert "already" not in row["reason"].lower()


def test_local_dir_parse_error_writes_failed_parse_quarantine(
    tmp_path, monkeypatch,
) -> None:
    pkg_dir = tmp_path / "Bar Bank - DMA"
    pkg_dir.mkdir()

    monkeypatch.setattr(hb, "_find_local_package_roots", lambda base: [pkg_dir])
    import app.services.artifact_manifest as am
    monkeypatch.setattr(
        am, "compute_package_manifest",
        lambda root: SimpleNamespace(
            material_manifest_hash=None, entries=[],
            material_count=0, cosmetic_count=0, unknown_count=0,
        ),
    )
    session = _FakeSession()
    monkeypatch.setattr(hb, "get_sessionmaker", lambda: (lambda: _FakeSessionCtx(session)))

    def _boom(root):
        raise RuntimeError("synthetic parser crash")

    monkeypatch.setattr(hb, "parse_package", _boom)
    import workers._runner as runner
    monkeypatch.setattr(
        runner, "get_current_tracker",
        lambda: SimpleNamespace(execution_id="exec-456"),
    )
    captured: list[dict] = []
    monkeypatch.setattr(
        hb, "_write_quarantine_row",
        lambda run_id, drive_folder_id, folder_name, outcome, reason,
               error_message, ingested_run_id:
        captured.append({"outcome": outcome, "err": error_message}),
    )

    counts = asyncio.run(hb._ingest_local_dir(tmp_path, force=True))

    assert counts["error"] == 1
    assert captured and captured[0]["outcome"] == "failed_parse"
    assert "synthetic parser crash" in captured[0]["err"]


# ── PENDING_REVIEW persist policy (junk institution_name) ─────────────


def _persist_with_name(name: str, drive_folder_id: str | None):
    """Run persist_package with the concurrent-safeguards fake session
    pattern (tests/test_concurrent_ingest_safeguards.py) and return the
    recorded (sql, params) calls."""
    from app.services.parsers.package_persist import persist_package
    from tests.test_concurrent_ingest_safeguards import _FakeSession as FS
    from tests.test_concurrent_ingest_safeguards import _Pkg

    pkg = _Pkg(institution_name=name)
    session = FS()
    asyncio.run(persist_package(
        session, pkg,
        data_source="MANUAL_BACKFILL",
        drive_folder_id=drive_folder_id,
    ))
    return session.calls


def _entity_insert_params(calls):
    for sql, params in calls:
        if "INSERT INTO entities" in sql:
            return sql, params
    raise AssertionError("no entity INSERT captured")


def test_junk_name_persists_as_pending_review() -> None:
    calls = _persist_with_name("VNO DMA Engagement FINAL", None)
    sql, params = _entity_insert_params(calls)
    assert params["status"] == "PENDING_REVIEW"
    assert "failed sanity" in (params["inf_src"] or "")
    assert params["keep_name"] is False


def test_clean_name_persists_as_active() -> None:
    calls = _persist_with_name("Foo Bank", None)
    sql, params = _entity_insert_params(calls)
    assert params["status"] == "ACTIVE"
    assert params["inf_src"] is None
    assert params["keep_name"] is True


def test_junk_reingest_never_clobbers_clean_existing_name() -> None:
    """ON CONFLICT keeps the existing name when the incoming one is
    junk, and never flips status (admins own PENDING_REVIEW→ACTIVE)."""
    calls = _persist_with_name("1NYe2zU3wmBEvd8ZRFWEHpAGIUuK1O1L2", None)
    sql, params = _entity_insert_params(calls)
    assert params["keep_name"] is False
    # the conflict clause must guard the name with the keep_name bind
    assert "CASE WHEN CAST(:keep_name AS BOOLEAN) THEN EXCLUDED.name" in sql
    # and must NOT touch status on conflict
    conflict_clause = sql.split("ON CONFLICT", 1)[1]
    assert "status" not in conflict_clause


# ── linked_e_ids sanitizer (varchar(16)[] column) ─────────────────────


def test_clean_e_ids_splits_comma_joined_blobs() -> None:
    """Sunflower Bank corpus defect (2026-06-10): one array element was
    a 58-char comma-joined fact-ref blob — asyncpg raised
    StringDataRightTruncationError and the only scored fixture that
    failed persist was lost. The sanitizer must split/strip/truncate."""
    from app.services.parsers.package_persist import _clean_e_ids

    raw = [
        "E-009", "E-016",
        "E-009:F1, E-009:F2, E-016:F1, E-016:F2, E-019:F1, E-019:F2",
        "E-034",
    ]
    out = _clean_e_ids(raw)
    assert all(len(v) <= 16 for v in out)
    assert "E-009" in out and "E-009:F1" in out and "E-034" in out
    # dedupe preserves first occurrence
    assert out.count("E-009") == 1
    assert _clean_e_ids(None) == []
    assert _clean_e_ids(["", "  "]) == []


# ── tolerant subvertical mapper (peer-cohort prerequisite) ────────────


def test_canonical_subvertical_tolerates_corpus_variants() -> None:
    """82/95 ACTIVE corpus entities had NULL subvertical under the old
    exact-match mapper — every peer-cohort surface rendered empty. The
    tolerant mapper must resolve the real corpus spelling census."""
    from app.services.parsers.package_persist import _canonical_subvertical

    cases = {
        ("SV2 — Credit Unions", None): "CU",
        ("SV2_Credit_Unions", None): "CU",
        ("Regional Bank (SV1)", None): "RB",
        ("regional_banks", None): "RB",
        ("SV1 — Regional Banks (Mega >$50B)", None): "RB",
        ("SV3 - Commercial Lending (Mortgage Sub-Servicing variant)", None): "CL",
        ("SV5", None): "RIA",
        ("SV6 - Asset Management", None): "AM",
        (None, "Independent RIA/Broker-Dealer"): "RIA",
        (None, "RIAs & Broker-Dealers (Retirement Plan Administration)"): "RIA",
        (None, "P&C Insurance - Mutual"): "IC",
        (None, "Insurance Brokers"): "IB",
        (None, "Commercial Agricultural Lending"): "FC",
        (None, "Banking — Lending (Independent Mortgage Banker)"): "CL",
        (None, "Credit Unions (Medium, $2B-$10B)"): "CU",
        ("RB", None): "RB",  # exact codes still win
    }
    for (code, name), expected in cases.items():
        got = _canonical_subvertical(code, name)
        assert got == expected, f"({code!r},{name!r}) -> {got!r} != {expected!r}"


def test_canonical_subvertical_rejects_garbage() -> None:
    from app.services.parsers.package_persist import _canonical_subvertical

    assert _canonical_subvertical("TBD - Step 1.4", None) is None
    assert _canonical_subvertical(
        "dma_output/DMA-RES-X-0001/00_entity_profile/subvertical_classification.json",
        None,
    ) is None
    assert _canonical_subvertical(None, None) is None
