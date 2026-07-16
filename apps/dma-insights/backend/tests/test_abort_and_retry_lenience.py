"""Tests for the operator abort endpoint + retry-mode lenience.

Two layers:

  1. Pure-source assertions that the wire format is intact across:
     - admin.py route
     - mark_cancelled helper
     - the Import page's Cancel button (ImportPage.tsx ActiveJobCard)
     - _check_aborted worker poll
     - historical_backfill retry-with-backoff loop

  2. Live-PG tests (skipped without SEED_CI_PG_URL):
     - mark_cancelled flips a real row + is idempotent
     - _check_aborted reads the cancelled status correctly
     - the worker abort poll exits the loop early

Pure-logic — no DB, no Drive, no Cloud Run. The live-PG layer
exercises the actual SQL when CI runs it.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

LIVE_DB_URL = os.environ.get("SEED_CI_PG_URL", "")
HAS_LIVE_DB = bool(LIVE_DB_URL)


# ── Wire-format consistency ────────────────────────────────────────────


def test_admin_abort_route_path_locked() -> None:
    """The frontend POSTs to a specific path; if the BE moves it, the
    UI's Abort button silently breaks."""
    admin = (APP_DIR / "routers" / "admin.py").read_text()
    assert "/jobs/executions/{execution_id}:abort" in admin, (
        "/api/v1/admin/jobs/executions/{id}:abort route is missing — "
        "the Import page's Cancel button POSTs here"
    )
    assert "async def abort_job_execution" in admin


def test_mark_cancelled_helper_exists_and_idempotent() -> None:
    """mark_cancelled must be a function (callable) that filters on
    `status='running'` so re-calling on an already-cancelled row is
    a no-op."""
    from app.services.job_executions_db import mark_cancelled

    assert callable(mark_cancelled)
    db_src = (
        APP_DIR / "services" / "job_executions_db.py"
    ).read_text()
    assert "AND status = 'running'" in db_src, (
        "mark_cancelled must filter on status='running' for idempotency"
    )


def test_frontend_abort_mutation_posts_to_admin_path() -> None:
    """The Import page's Cancel button (ImportPage.tsx ActiveJobCard)
    must POST to the exact admin path the BE serves. A typo here =
    silent UI breakage.

    (This contract used to live in the net-new OperationsPanel, which was
    removed for strict prototype fidelity; the abort affordance relocated
    to the ActiveJobCard on the /admin/import page.)"""
    page = (
        FRONTEND_DIR / "src" / "pages" / "ImportPage.tsx"
    ).read_text()
    # Must POST to the abort path with a template literal for the
    # execution id (the variable name is incidental — `${ex.id}` today).
    assert "/api/v1/admin/jobs/executions/" in page
    assert re.search(
        r"executions/\$\{[^}]+\}:abort", page,
    ), (
        "ImportPage.tsx must POST to "
        "/api/v1/admin/jobs/executions/{id}:abort with a template literal"
    )
    assert "apiPost(" in page, (
        "the Cancel button must POST via apiPost to the abort path"
    )
    # The Cancel button is only rendered for running rows.
    assert re.search(
        r"\bstatus\s*===\s*['\"]running['\"]", page,
    ), (
        "Cancel button must be gated to status='running' — showing it "
        "on completed/failed rows would mislead operators"
    )


def test_worker_polls_for_abort_signal() -> None:
    """The worker must check `job_executions.status` after every folder
    so the operator's Abort click takes effect within seconds, not at
    end-of-batch."""
    backfill_src = (
        APP_DIR / "scripts" / "historical_backfill.py"
    ).read_text()
    assert "_check_aborted" in backfill_src
    assert "ABORT signal received" in backfill_src, (
        "Worker must print a clear ABORT message when the row flips"
    )
    # The poll must compare against the 'cancelled' status string.
    assert "'cancelled'" in backfill_src or '"cancelled"' in backfill_src


# ── _check_aborted — failure modes ─────────────────────────────────────


def test_check_aborted_returns_false_without_execution_id() -> None:
    from app.scripts.historical_backfill import _check_aborted

    assert _check_aborted(None) is False
    assert _check_aborted("") is False


def test_check_aborted_swallows_db_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable DB must not crash the worker — _check_aborted
    returns False (worker keeps running)."""
    from app.scripts.historical_backfill import _check_aborted

    monkeypatch.setenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nodb",
    )
    # Should NOT raise.
    assert _check_aborted(str(uuid.uuid4())) is False


def test_check_aborted_no_dsn_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.scripts.historical_backfill import _check_aborted
    from app.services import sync_dsn

    monkeypatch.setattr(sync_dsn, "resolve_sync_dsn", lambda: None)
    assert _check_aborted(str(uuid.uuid4())) is False


# ── Retry-with-backoff (worker side) ──────────────────────────────────


def test_retry_failed_only_triggers_3_attempts() -> None:
    """When --retry-failed-only is active, transient Drive errors get
    3 attempts (vs 1 for the first pass)."""
    backfill_src = (
        APP_DIR / "scripts" / "historical_backfill.py"
    ).read_text()
    assert "attempts = 3 if retry_failed_only else 1" in backfill_src, (
        "Retry mode must use 3 attempts vs 1 for the first pass"
    )
    # Exponential backoff: 2s/4s/8s.
    assert "delay = 2 ** attempt" in backfill_src, (
        "Worker retry must use exponential backoff (2^attempt seconds)"
    )


def test_retry_captures_full_traceback() -> None:
    """Retry mode must capture full traceback into the quarantine
    error_message so re-retries have richer context."""
    backfill_src = (
        APP_DIR / "scripts" / "historical_backfill.py"
    ).read_text()
    assert "_tb.format_exc()" in backfill_src, (
        "Retry mode must capture full traceback (not just first line)"
    )


def test_retry_handles_transient_http_codes() -> None:
    """Retry-with-backoff must specifically target 429/500/502/503/504
    (and 403 rate-limit)."""
    backfill_src = (
        APP_DIR / "scripts" / "historical_backfill.py"
    ).read_text()
    # We want at least the 4xx rate-limits + the 5xx range.
    for code in (429, 503, 504):
        assert str(code) in backfill_src, (
            f"Retry transient list missing HTTP {code} — Drive API "
            f"returns this under load + the retry must back off"
        )


# ── summarize_execution — live-counter contract ────────────────────────


def test_summarize_execution_running_no_counters() -> None:
    """Before any folder is seen, surface 'starting…' (not 'in progress')
    so the operator can distinguish 'worker booting' from 'worker stuck'."""
    from app.services.job_executions import summarize_execution

    out = summarize_execution({"status": "running"})
    assert out["result_summary"] == "starting…"


def test_summarize_execution_running_with_progress() -> None:
    """The KEY visibility fix — the result_summary must surface
    live counters during a run, not the static 'in progress' string."""
    from app.services.job_executions import summarize_execution

    out = summarize_execution({
        "status": "running",
        "folders_seen": 115,
        "files_parsed": 30,
        "files_skipped": 5,
        "files_errored": 2,
    })
    # Progress = 30 + 5 + 2 = 37 / 115 = 32%
    summary = out["result_summary"]
    assert "37/115" in summary
    assert "32%" in summary
    assert "ok=30" in summary
    assert "skip=5" in summary
    assert "fail=2" in summary
    assert out["error_count"] == 2


def test_summarize_execution_cancelled() -> None:
    """Cancelled state must be distinguishable from failed (different
    summary string + 0 error count — cancellation is operator-initiated,
    not a real failure)."""
    from app.services.job_executions import summarize_execution

    out = summarize_execution({"status": "cancelled"})
    assert out["result_summary"] == "cancelled by operator"
    assert out["error_count"] == 0


# ── Live-PG: real abort flow ────────────────────────────────────────────


@pytest.mark.skipif(
    not HAS_LIVE_DB, reason="SEED_CI_PG_URL not set"
)
class TestAbortLivePg:
    """End-to-end against a real Postgres with migrations applied."""

    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sync_url = LIVE_DB_URL.replace("+asyncpg", "+psycopg")
        monkeypatch.setenv("DATABASE_URL_SYNC", sync_url)
        from app.services.job_executions_db import reset_engine_for_tests
        reset_engine_for_tests()

    @pytest.fixture
    def running_row(self):
        """INSERT a fresh running row; yield its id. Tear-down DELETEs."""
        from sqlalchemy import create_engine, text

        sync_url = LIVE_DB_URL.replace("+asyncpg", "+psycopg")
        row_id = str(uuid.uuid4())
        eng = create_engine(sync_url)
        with eng.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO job_executions
                        (id, job_name, trigger_source, status, started_at)
                    VALUES
                        (CAST(:id AS uuid), :job, 'cli', 'running', NOW())
                """),
                {"id": row_id, "job": "test_abort_flow"},
            )
        yield row_id
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM job_executions WHERE id = CAST(:id AS uuid)"),
                {"id": row_id},
            )
        eng.dispose()

    def test_mark_cancelled_flips_running_row(self, running_row: str) -> None:
        from sqlalchemy import create_engine, text

        from app.services.job_executions_db import mark_cancelled

        out = mark_cancelled(
            running_row,
            cancelled_by_email="operator@zennify.com",
            reason="test abort",
        )
        assert out["status"] == "cancelled"
        assert out["completed_at"] is not None

        # Verify direct DB state.
        sync_url = LIVE_DB_URL.replace("+asyncpg", "+psycopg")
        eng = create_engine(sync_url)
        with eng.begin() as conn:
            row = conn.execute(
                text("SELECT status, error_message FROM job_executions "
                     "WHERE id = CAST(:id AS uuid)"),
                {"id": running_row},
            ).first()
        assert row[0] == "cancelled"
        assert "operator@zennify.com" in (row[1] or "")
        assert "test abort" in (row[1] or "")
        eng.dispose()

    def test_mark_cancelled_idempotent_on_completed_row(
        self, running_row: str,
    ) -> None:
        """Calling mark_cancelled twice doesn't clobber the first
        result — re-cancelling a cancelled row is a no-op."""
        from app.services.job_executions_db import mark_cancelled

        first = mark_cancelled(
            running_row, cancelled_by_email="first@x.com"
        )
        assert first["status"] == "cancelled"
        # Second call: the WHERE status='running' filter rejects the
        # update; mark_cancelled re-fetches the existing state.
        second = mark_cancelled(
            running_row, cancelled_by_email="second@x.com"
        )
        assert second["status"] == "cancelled"
        # error_message preserved from first call (COALESCE on UPDATE
        # doesn't overwrite + the WHERE filter skipped the second UPDATE).
        assert "first@x.com" in (second.get("error_message") or "")

    def test_check_aborted_returns_true_after_cancel(
        self, running_row: str,
    ) -> None:
        from app.scripts.historical_backfill import _check_aborted
        from app.services.job_executions_db import mark_cancelled

        assert _check_aborted(running_row) is False  # running → False
        mark_cancelled(running_row, cancelled_by_email="abort@test.com")
        assert _check_aborted(running_row) is True  # cancelled → True
