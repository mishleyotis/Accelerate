"""Tests for the historical_backfill quarantine + --retry-failed-only flow.

Two layers:

  1. Pure-logic tests for `_classify_outcome` (no DB, no I/O). Cover
     every state-branch of the outcome contract: ok / skipped_no_report
     / skipped_already_ingested / failed_parse / failed_persist /
     failed_other / unrecognized result.

  2. Live-PG integration tests (skipped unless SEED_CI_PG_URL is set):
     - `_write_quarantine_row` inserts a real row when given a real
       job_executions.id.
     - `_write_quarantine_row` swallows DB errors when the URL points
       nowhere (best-effort contract).
     - `_load_retry_targets` returns ONLY drive_folder_ids whose latest
       outcome is failed_* or skipped_no_report.

The migration `022_backfill_quarantine` MUST be applied against the
live DB for this test to find the table; we rely on the standard CI
`alembic upgrade head` step.

Re-runs are safe: every test inserts unique drive_folder_id values
(prefixed with the test name) so concurrent test runs don't clobber.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from app.scripts.historical_backfill import (
    _classify_outcome,
    _load_retry_targets,
    _write_quarantine_row,
)

LIVE_DB_URL = os.environ.get("SEED_CI_PG_URL", "")
HAS_LIVE_DB = bool(LIVE_DB_URL)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ── _classify_outcome — pure logic, every branch covered ────────────────


class TestClassifyOutcome:
    """Every output branch of `_classify_outcome`.

    The contract is locked: changes here mean a wire-format break with
    the admin UI's quarantine-list filter.
    """

    def test_ok_branch_returns_ok_with_ingested_run_id(self) -> None:
        outcome, reason, ingested, err = _classify_outcome(
            "OK:550e8400-e29b-41d4-a716-446655440000"
        )
        assert outcome == "ok"
        assert reason == "ingested"
        assert ingested == "550e8400-e29b-41d4-a716-446655440000"
        assert err is None

    def test_skip_no_dma_package(self) -> None:
        outcome, reason, ingested, err = _classify_outcome(
            "SKIP:no DMA package detected"
        )
        assert outcome == "skipped_no_report"
        assert reason == "no DMA package detected"
        assert ingested is None
        assert err is None

    def test_skip_no_run_manifest(self) -> None:
        outcome, _, _, _ = _classify_outcome("SKIP:no run manifest found")
        assert outcome == "skipped_no_report"

    def test_skip_already_ingested(self) -> None:
        outcome, reason, _, _ = _classify_outcome(
            "SKIP:already_ingested run_id=abc"
        )
        assert outcome == "skipped_already_ingested"
        assert "already_ingested" in reason

    def test_skip_idempotent_lowercase(self) -> None:
        outcome, _, _, _ = _classify_outcome(
            "SKIP:idempotent — same request_id"
        )
        assert outcome == "skipped_already_ingested"

    def test_error_parse(self) -> None:
        outcome, reason, ingested, err = _classify_outcome(
            "ERROR:parse:malformed manifest"
        )
        assert outcome == "failed_parse"
        assert reason == "parse_failed"
        assert ingested is None
        assert "malformed manifest" in (err or "")

    def test_error_persist(self) -> None:
        outcome, reason, _, err = _classify_outcome(
            "ERROR:persist:FK violation on ccg_catalog_versions"
        )
        assert outcome == "failed_persist"
        assert reason == "persist_failed"
        assert "FK violation" in (err or "")

    def test_error_generic_other(self) -> None:
        outcome, reason, _, err = _classify_outcome(
            "ERROR:top-level:TimeoutError: Drive API slow"
        )
        assert outcome == "failed_other"
        assert reason == "other"
        assert "TimeoutError" in (err or "")

    def test_unrecognized_falls_into_failed_other(self) -> None:
        """A return value that doesn't match any prefix is still
        recorded — operator sees it instead of silent swallow."""
        outcome, reason, _, err = _classify_outcome("something weird")
        assert outcome == "failed_other"
        assert reason == "unrecognized_result"
        assert err == "something weird"

    def test_empty_string_is_unrecognized(self) -> None:
        outcome, reason, _, _ = _classify_outcome("")
        assert outcome == "failed_other"
        assert reason == "unrecognized_result"


# ── _write_quarantine_row — best-effort contract ────────────────────────


class TestWriteQuarantineRowBestEffort:
    """`_write_quarantine_row` MUST swallow every exception so a
    quarantine-write failure never blocks the backfill loop."""

    def test_no_run_id_silently_returns(self) -> None:
        """No run_id (e.g. running outside track_job_execution) → no-op."""
        _write_quarantine_row(
            run_id=None,
            drive_folder_id="dummy",
            folder_name="dummy",
            outcome="ok",
            reason="ingested",
            error_message=None,
            ingested_run_id=None,
        )

    def test_db_unreachable_swallows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When sync DSN points nowhere, the write fails INSIDE the
        function — the caller never sees the exception."""
        monkeypatch.setenv(
            "DATABASE_URL_SYNC",
            "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nodb",
        )
        # Should NOT raise — best-effort.
        _write_quarantine_row(
            run_id=str(uuid.uuid4()),
            drive_folder_id="unreachable",
            folder_name="unreachable",
            outcome="failed_other",
            reason="db_test",
            error_message="simulated",
            ingested_run_id=None,
        )

    def test_no_dsn_at_all_silently_returns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no DSN can be resolved, the function returns silently."""
        monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SEED_CI_PG_URL", raising=False)
        # Force resolve_sync_dsn to return None.
        from app.services import sync_dsn

        monkeypatch.setattr(sync_dsn, "resolve_sync_dsn", lambda: None)
        _write_quarantine_row(
            run_id=str(uuid.uuid4()),
            drive_folder_id="no-dsn",
            folder_name="no-dsn",
            outcome="ok",
            reason="ingested",
            error_message=None,
            ingested_run_id=None,
        )


# ── Live-PG integration: full quarantine + retry-targets flow ───────────


@pytest.mark.skipif(
    not HAS_LIVE_DB, reason="SEED_CI_PG_URL not set"
)
class TestQuarantineLivePg:
    """End-to-end against a real Postgres with migration 022 applied.

    Each test inserts unique rows (test-name prefix on folder IDs) so
    parallel runs don't clobber each other. We DELETE-on-cleanup via
    the test_prefix so re-runs are idempotent.
    """

    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sync_url = LIVE_DB_URL.replace("+asyncpg", "+psycopg")
        monkeypatch.setenv("DATABASE_URL_SYNC", sync_url)

    @pytest.fixture
    def fake_job_execution_id(self) -> str:
        """Return a fresh UUID. Migration 022 deliberately drops the
        FK on backfill_quarantine.run_id (worker writes quarantine
        before job_executions finalisation), so we don't need a real
        job_executions row to insert."""
        return str(uuid.uuid4())

    @pytest.fixture
    def cleanup(self) -> str:
        """Prefix for this test's drive_folder_id values. Tear-down
        deletes every row at that prefix."""
        prefix = f"test_qtn_{uuid.uuid4().hex[:8]}"
        yield prefix
        # Tear-down.
        from sqlalchemy import create_engine, text

        eng = create_engine(LIVE_DB_URL.replace("+asyncpg", "+psycopg"))
        with eng.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM backfill_quarantine "
                    "WHERE drive_folder_id LIKE :p"
                ),
                {"p": f"{prefix}%"},
            )
        eng.dispose()

    def _read_back(self, drive_folder_id: str) -> dict:
        from sqlalchemy import create_engine, text

        eng = create_engine(LIVE_DB_URL.replace("+asyncpg", "+psycopg"))
        try:
            with eng.begin() as conn:
                row = conn.execute(
                    text(
                        "SELECT drive_folder_id, folder_name, outcome, "
                        "reason, error_message, ingested_run_id "
                        "FROM backfill_quarantine "
                        "WHERE drive_folder_id = :d "
                        "ORDER BY processed_at DESC LIMIT 1"
                    ),
                    {"d": drive_folder_id},
                ).first()
        finally:
            eng.dispose()
        return dict(row._mapping) if row else {}

    def test_write_quarantine_row_inserts_real_row(
        self, fake_job_execution_id: str, cleanup: str
    ) -> None:
        dfid = f"{cleanup}_ok_1"
        _write_quarantine_row(
            run_id=fake_job_execution_id,
            drive_folder_id=dfid,
            folder_name="A Test Folder - DMA",
            outcome="ok",
            reason="ingested",
            error_message=None,
            ingested_run_id=str(uuid.uuid4()),
        )
        row = self._read_back(dfid)
        assert row["outcome"] == "ok"
        assert row["folder_name"] == "A Test Folder - DMA"
        assert row["reason"] == "ingested"
        assert row["ingested_run_id"] is not None

    def test_write_quarantine_row_failed_parse(
        self, fake_job_execution_id: str, cleanup: str
    ) -> None:
        dfid = f"{cleanup}_failed_parse"
        _write_quarantine_row(
            run_id=fake_job_execution_id,
            drive_folder_id=dfid,
            folder_name="Bad Parse Folder - DMA",
            outcome="failed_parse",
            reason="parse_failed",
            error_message="malformed run_manifest.json",
            ingested_run_id=None,
        )
        row = self._read_back(dfid)
        assert row["outcome"] == "failed_parse"
        assert row["error_message"] == "malformed run_manifest.json"
        assert row["ingested_run_id"] is None

    def test_check_constraint_rejects_bogus_outcome(
        self, fake_job_execution_id: str, cleanup: str
    ) -> None:
        """The CHECK constraint must reject an outcome that isn't in
        the locked enum — direct SQL insert (bypassing _write_quarantine_row
        which itself swallows errors)."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import IntegrityError

        eng = create_engine(LIVE_DB_URL.replace("+asyncpg", "+psycopg"))
        try:
            with pytest.raises(IntegrityError), eng.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO backfill_quarantine "
                        "(run_id, drive_folder_id, folder_name, outcome) "
                        "VALUES (CAST(:r AS uuid), :d, :f, :o)"
                    ),
                    {
                        "r": fake_job_execution_id,
                        "d": f"{cleanup}_bogus",
                        "f": "Bogus - DMA",
                        "o": "BOGUS_NOT_IN_ENUM",
                    },
                )
        finally:
            eng.dispose()

    def test_load_retry_targets_returns_only_actionable_outcomes(
        self, fake_job_execution_id: str, cleanup: str
    ) -> None:
        """Comprehensive matrix — 5 folders, one of each outcome class.

        Expected retry set: failed_parse / failed_persist / failed_other
        / skipped_no_report (4 folders).
        Expected NOT in retry: ok / skipped_already_ingested.
        """
        folders = [
            (f"{cleanup}_ok", "ok"),
            (f"{cleanup}_skipped_already", "skipped_already_ingested"),
            (f"{cleanup}_skipped_noreport", "skipped_no_report"),
            (f"{cleanup}_failed_parse", "failed_parse"),
            (f"{cleanup}_failed_persist", "failed_persist"),
            (f"{cleanup}_failed_other", "failed_other"),
        ]
        for dfid, outcome in folders:
            _write_quarantine_row(
                run_id=fake_job_execution_id,
                drive_folder_id=dfid,
                folder_name=f"{dfid} folder",
                outcome=outcome,
                reason="test_seed",
                error_message="x" if outcome.startswith("failed_") else None,
                ingested_run_id=str(uuid.uuid4()) if outcome == "ok" else None,
            )

        targets = _load_retry_targets()
        retried = {dfid for dfid, _ in folders if dfid in targets}
        not_retried = {dfid for dfid, _ in folders if dfid not in targets}

        # 4 should be retried.
        assert f"{cleanup}_skipped_noreport" in retried
        assert f"{cleanup}_failed_parse" in retried
        assert f"{cleanup}_failed_persist" in retried
        assert f"{cleanup}_failed_other" in retried
        # 2 should NOT be retried.
        assert f"{cleanup}_ok" in not_retried
        assert f"{cleanup}_skipped_already" in not_retried

    def test_load_retry_targets_uses_latest_row_per_folder(
        self, fake_job_execution_id: str, cleanup: str
    ) -> None:
        """If a folder failed once and then succeeded, the latest row
        wins. The folder is NOT retried (its current state is 'ok')."""
        from sqlalchemy import create_engine, text

        dfid = f"{cleanup}_fail_then_ok"
        # Older row: failed_parse.
        _write_quarantine_row(
            run_id=fake_job_execution_id,
            drive_folder_id=dfid,
            folder_name="fail-then-ok - DMA",
            outcome="failed_parse",
            reason="first_attempt",
            error_message="boom",
            ingested_run_id=None,
        )
        # Sleep / processed_at advance — back-date the failed row.
        eng = create_engine(LIVE_DB_URL.replace("+asyncpg", "+psycopg"))
        try:
            with eng.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE backfill_quarantine "
                        "SET processed_at = NOW() - INTERVAL '1 hour' "
                        "WHERE drive_folder_id = :d AND outcome = 'failed_parse'"
                    ),
                    {"d": dfid},
                )
        finally:
            eng.dispose()

        # Newer row: ok.
        _write_quarantine_row(
            run_id=fake_job_execution_id,
            drive_folder_id=dfid,
            folder_name="fail-then-ok - DMA",
            outcome="ok",
            reason="second_attempt",
            error_message=None,
            ingested_run_id=str(uuid.uuid4()),
        )

        targets = _load_retry_targets()
        assert dfid not in targets, (
            f"latest outcome is 'ok' — folder {dfid} must NOT be flagged for retry"
        )

    def test_load_retry_targets_empty_db_returns_empty_set(
        self, cleanup: str
    ) -> None:
        """When no rows match the test's prefix, the function still
        works (returns whatever real rows exist — possibly empty)."""
        targets = _load_retry_targets()
        # We can't assert empty if there are real production rows,
        # but we CAN assert our test's prefix isn't present.
        assert not any(t.startswith(cleanup) for t in targets)


# ── _load_retry_targets — graceful failure when DB unreachable ─────────


class TestLoadRetryTargetsFailureModes:
    def test_no_dsn_returns_empty_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services import sync_dsn

        monkeypatch.setattr(sync_dsn, "resolve_sync_dsn", lambda: None)
        assert _load_retry_targets() == set()

    def test_unreachable_db_returns_empty_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "DATABASE_URL_SYNC",
            "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nodb",
        )
        # Should NOT raise — best-effort.
        assert _load_retry_targets() == set()
