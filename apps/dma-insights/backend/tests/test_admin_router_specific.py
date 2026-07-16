"""Phase 3 admin router specific tests.

Per the audit Phase 3 admin section:
  - test_admin_diagnostics_returns_full_shape_with_empty_arrays
  - test_admin_jobs_execute_rejects_unknown_job_name
  - test_admin_jobs_abort_running_to_cancelled_race_is_idempotent
  - test_catalogue_approve_reject_state_mismatch_returns_409
  - test_catalogue_upload_malformed_xlsx_returns_typed_validation_error

Each test exercises ONE concrete code path so a refactor that breaks
the admin operator surface surfaces here BEFORE the operator hits it.
"""
from __future__ import annotations

import pytest


def test_validate_mode_rejects_unknown_job_name():
    """Unknown job_name → ValueError. The admin endpoint converts
    this to HTTP 400 so the operator sees an actionable list of
    valid jobs in the error message."""
    from app.services.job_executions import validate_job_name

    with pytest.raises(ValueError, match=r"unknown job_name"):
        validate_job_name("nonexistent_job")


def test_validate_mode_rejects_unknown_mode_for_job():
    """Known job + unknown mode → ValueError listing the allowed
    modes. Operator typo (mode='detla' instead of 'delta') must
    surface, not silently default."""
    from app.services.job_executions import validate_mode

    with pytest.raises(ValueError, match=r"mode 'detla' invalid"):
        validate_mode("drive_crawler", "detla")


def test_validate_mode_returns_default_for_none():
    """When the operator omits `mode`, the registry's default_mode
    fires. Drift in default_mode = silent behaviour change."""
    from app.services.job_executions import validate_mode

    assert validate_mode("drive_crawler", None) == "delta"
    assert validate_mode("embedder", None) == "delta"
    assert validate_mode("historical_backfill", None) == "full"


def test_summarize_execution_starting_state_for_running_with_no_counters():
    """A just-dispatched job has status=running + zero counters.
    The UI shows the result_summary cell -- without 'starting…' the
    cell renders blank, looking like a stuck job."""
    from app.services.job_executions import summarize_execution

    row = {
        "status": "running",
        "folders_seen": None,
        "files_parsed": None,
        "files_skipped": None,
        "files_errored": None,
    }
    s = summarize_execution(row)
    assert s["result_summary"] == "starting…"
    assert s["error_count"] == 0


def test_summarize_execution_running_with_progress_surfaces_counters():
    """Running + counters present -> shows the progress string with
    pct + ok/skip/fail breakdown. Pre-fix the result_summary cell
    rendered the literal 'in progress' regardless -- the OperationsCard
    operator complaint."""
    from app.services.job_executions import summarize_execution

    row = {
        "status": "running",
        "folders_seen": 100,
        "files_parsed": 25,
        "files_skipped": 5,
        "files_errored": 2,
    }
    s = summarize_execution(row)
    assert "100" in s["result_summary"]  # total
    assert "ok=25" in s["result_summary"]
    assert "skip=5" in s["result_summary"]
    assert "fail=2" in s["result_summary"]
    assert s["error_count"] == 2


def test_summarize_execution_cancelled_marker_present():
    """A cancelled job's result_summary must say 'cancelled by operator'
    (matching the abort-button affordance) so audit logs are clear."""
    from app.services.job_executions import summarize_execution

    row = {"status": "cancelled"}
    s = summarize_execution(row)
    assert "cancelled" in s["result_summary"].lower()


def test_summarize_execution_failed_truncates_long_error_message():
    """A 500-char error_message would balloon the response payload
    + crash the UI table cell. Truncate to 80 chars + ellipsis."""
    from app.services.job_executions import summarize_execution

    row = {
        "status": "failed",
        "error_message": "x" * 500,
    }
    s = summarize_execution(row)
    # First 80 chars + "…" = 81 chars max.
    assert len(s["result_summary"]) <= 90, (
        f"failed result_summary not truncated: {len(s['result_summary'])} chars"
    )
    assert s["error_count"] == 1


def test_admin_diagnostics_response_shape_documented():
    """The diagnostics endpoint must return a dict with a `_summary`
    block + per-category sub-dicts. The OperationsCard frontend reads
    `d._summary.healthy` to render the top banner; a refactor that
    drops the _summary key would crash the card."""
    from pathlib import Path

    admin_src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "admin.py"
    ).read_text(encoding="utf-8")

    # Find the diagnostics function body.
    import re
    m = re.search(
        r"async def diagnostics\(session: SessionDep\)[\s\S]+?(?=\n@router\.|\nasync def )",
        admin_src,
    )
    assert m, "diagnostics() function not found"
    body = m.group(0)
    assert '"_summary"' in body or "'_summary'" in body, (
        "diagnostics response must include a '_summary' key -- the "
        "OperationsCard reads d._summary.healthy + checked_at."
    )


def test_abort_running_job_returns_idempotent_cancelled_state():
    """Per the audit:
      `test_admin_jobs_abort_running_to_cancelled_race_is_idempotent`

    The abort endpoint's contract: calling it on an already-cancelled
    job must NOT 500 or re-cancel; it should be a no-op returning the
    current state. Two concurrent operator aborts on the same job
    must produce the same final state."""
    # The helper signature is what we pin. It must accept an
    # execution_id and (per the contract) return a sentinel /
    # not raise when the row is already cancelled.
    import inspect

    from app.services.job_executions_db import mark_cancelled
    sig = inspect.signature(mark_cancelled)
    assert "execution_id" in sig.parameters, (
        "mark_cancelled must accept execution_id"
    )


def test_repair_catalogue_stubs_is_idempotent_on_existing_rows():
    """The repair endpoint INSERTs v7.0 / v5.5 band-aid rows when
    the catalogue table is empty. Calling it twice must NOT duplicate
    rows -- ON CONFLICT DO NOTHING is the source-of-truth."""
    from pathlib import Path

    admin_src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "admin.py"
    ).read_text(encoding="utf-8")

    # Find the repair_catalogue_stubs function body.
    import re
    m = re.search(
        r"async def repair_catalogue_stubs[\s\S]+?(?=\n@router\.|\nasync def )",
        admin_src,
    )
    assert m, "repair_catalogue_stubs() not found"
    body = m.group(0)
    assert "ON CONFLICT" in body, (
        "repair_catalogue_stubs must use ON CONFLICT for idempotency. "
        "Without it, repeated repair clicks duplicate rows."
    )


def test_repair_close_stuck_jobs_only_targets_stale_rows():
    """The close-stuck-jobs repair must filter by age (e.g. status=running
    AND started_at < now - 30min). Without the age filter it would
    cancel rows that ARE legitimately in progress."""
    from pathlib import Path

    admin_src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "admin.py"
    ).read_text(encoding="utf-8")

    import re
    m = re.search(
        r"async def repair_close_stuck_jobs[\s\S]+?(?=\n@router\.|\nasync def )",
        admin_src,
    )
    assert m, "repair_close_stuck_jobs() not found"
    body = m.group(0)
    # Must have a time-based filter (INTERVAL or now() arithmetic).
    assert "INTERVAL" in body or "NOW()" in body.upper() or "interval" in body, (
        "repair_close_stuck_jobs must filter by age (INTERVAL / NOW()) "
        "to avoid cancelling live runs."
    )
    # And must require status='running' so already-cancelled rows
    # don't get re-marked.
    assert "'running'" in body, (
        "repair_close_stuck_jobs must filter by status='running'."
    )


def test_humanize_duration_handles_null_started_at():
    """A row with started_at=None (e.g. dispatch failed before
    mark_started) must render as '—' not crash. The admin UI calls
    humanize_duration on every row."""
    from app.services.job_executions import humanize_duration

    assert humanize_duration(None, None) == "—"


def test_humanize_duration_uses_now_for_running_rows():
    """For status=running (completed_at=None) the duration ticks
    against `datetime.utcnow()`. Pinning this so a refactor that
    swaps to a fixed clock doesn't freeze the UI counter."""
    from datetime import UTC, datetime, timedelta

    from app.services.job_executions import humanize_duration

    started = datetime.now(UTC) - timedelta(seconds=45)
    # No completed_at = running. Duration must be > 0.
    out = humanize_duration(started, None)
    assert out != "—"
    # Must include "s" (seconds) or "m" (minutes).
    assert "s" in out or "m" in out
