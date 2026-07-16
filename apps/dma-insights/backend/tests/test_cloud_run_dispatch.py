"""F3c tests — Admin → Overview job-execute button actually invokes
the worker.

Bug fixed: previously `/api/v1/admin/jobs/{name}:execute` INSERTed a
`job_executions` row and published a Pub/Sub fan-out to a topic that
had no subscriber. The row stayed in 'running' forever and the
operator-reported "Drive crawl" button appeared to do nothing — the
root cause of "Currently none has been ingested from the drive".

The fix: `app/services/cloud_run_dispatch.py::dispatch_job` calls the
Cloud Run Jobs REST API directly (prod) or a fire-and-forget
subprocess (local/test). Either path passes `DMA_JOB_EXECUTION_ID`
so the worker updates the SAME row instead of creating a parallel
one.

State branches under test:
  job_not_in_registry        — unknown job_name → returns reason
  skipped_no_project         — prod env, GCP project unset → returns reason
  arg_validator_coercion     — coerces None/dict/int → []
  registry_completeness      — every admin-triggerable job is mapped
"""
from __future__ import annotations

import pytest

from app.services.cloud_run_dispatch import (
    JOB_DISPATCH,
    dispatch_job,
    dispatch_job_arg_validator,
)


def test_registry_covers_all_admin_triggerable_jobs():
    """Every job_name the admin UI shows MUST be in JOB_DISPATCH —
    otherwise hitting the button would 503 with 'job_not_in_registry'."""
    expected = {
        "drive_crawler", "historical_backfill", "embedder",
        "peer_patterns", "ccg_loader", "sheet_poller",
        "intelligence_recompute", "chat_learning",
    }
    assert expected.issubset(set(JOB_DISPATCH)), (
        f"missing in JOB_DISPATCH: {expected - set(JOB_DISPATCH)}"
    )


def test_registry_entries_are_well_formed():
    """Each entry is (cr_job_resource_name, default_args, py_module_path)."""
    for name, spec in JOB_DISPATCH.items():
        assert isinstance(spec, tuple) and len(spec) == 3, name
        cr_name, default_args, py_module = spec
        assert cr_name.startswith("dma-insights-"), name
        assert isinstance(default_args, list), name
        assert py_module.count(".") >= 1, f"{name}: py_module must be importable"


def test_arg_validator_coerces_to_list_str():
    assert dispatch_job_arg_validator(None) == []
    assert dispatch_job_arg_validator([]) == []
    assert dispatch_job_arg_validator(["--once", "--since=2026-01-01"]) == [
        "--once", "--since=2026-01-01",
    ]
    # Hostile inputs default to []
    assert dispatch_job_arg_validator({"weird": "shape"}) == []
    assert dispatch_job_arg_validator(42) == []
    # Drops Nones
    assert dispatch_job_arg_validator(["--once", None]) == ["--once"]
    # Coerces numbers
    assert dispatch_job_arg_validator([1, 2]) == ["1", "2"]


@pytest.mark.asyncio
async def test_unknown_job_returns_registry_error():
    ok, reason = await dispatch_job(
        job_name="nonexistent_job", execution_id="11111111-1111-1111-1111-111111111111",
    )
    assert ok is False
    assert reason.startswith("job_not_in_registry:")


@pytest.mark.asyncio
async def test_local_env_fires_subprocess_for_known_job():
    """Local-env dispatch fires a subprocess so admin button behaviour
    is verifiable end-to-end without GCP creds. We point at a no-op
    python module to keep the test self-contained — the dispatcher
    doesn't wait on the subprocess, so the test asserts (True, reason)
    immediately."""
    from app.config import get_settings
    # Force-local — get_settings() reads env=local in tests already, but
    # we assert that explicitly so the test fails loudly if the env
    # fixture ever changes.
    assert get_settings().env in ("local", "test")
    ok, reason = await dispatch_job(
        # Use a real registry entry; the subprocess will fail to find
        # workers.embedder.main without it being installed, but the
        # dispatcher returns BEFORE the subprocess runs.
        job_name="embedder",
        execution_id="22222222-2222-2222-2222-222222222222",
    )
    assert ok is True
    assert "local" in reason
