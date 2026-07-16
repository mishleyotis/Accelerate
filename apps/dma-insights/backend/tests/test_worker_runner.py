# ruff: noqa: SIM117  (nested with-statements are intentional for env+patch combo readability)
"""Worker execution runner — context manager wraps every worker with
job_executions lifecycle UPDATEs (RUNNING → SUCCEEDED / FAILED).

State coverage per test
-----------------------
test_happy_path_marks_succeeded   — body runs cleanly → mark_succeeded called
test_exception_marks_failed       — body raises → mark_failed called + exception re-raised
test_counters_passed_through      — ex.update(N) merges into final mark_succeeded
test_no_execution_id_creates_row  — DMA_JOB_EXECUTION_ID unset → create_execution_row called
test_db_unavailable_swallowed     — DB raises on every lifecycle call → body still runs
test_existing_execution_id_used   — DMA_JOB_EXECUTION_ID set → no create_row call
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

# Workers package is one level up from the backend root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def _env(**vars):
    """Set env vars for the duration of a test."""
    saved = {k: os.environ.get(k) for k in vars}
    for k, v in vars.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_happy_path_marks_succeeded() -> None:
    """Body runs cleanly → mark_succeeded called with final counters,
    no mark_failed call, no exception."""
    from workers._runner import track_job_execution

    calls = {"mark_started": 0, "mark_succeeded": 0, "mark_failed": 0}

    def _started(_id):
        calls["mark_started"] += 1

    def _succeeded(_id, **kwargs):
        calls["mark_succeeded"] += 1
        calls["succ_counters"] = kwargs

    def _failed(_id, **kwargs):
        calls["mark_failed"] += 1

    with _env(DMA_JOB_EXECUTION_ID="exec-abc"), \
         patch("workers._runner._safe_mark_started", _started), \
         patch("workers._runner._safe_mark_succeeded", _succeeded), \
         patch("workers._runner._safe_mark_failed", _failed):

        with track_job_execution("drive_crawler", mode="full") as ex:
            ex.update(folders_seen=12, files_parsed=87)

    assert calls["mark_started"] == 1
    assert calls["mark_succeeded"] == 1
    assert calls["mark_failed"] == 0
    assert calls["succ_counters"] == {"folders_seen": 12, "files_parsed": 87}


def test_exception_marks_failed() -> None:
    """Body raises → mark_failed called with the error + tail; exception
    propagates to caller (worker exits non-zero)."""
    from workers._runner import track_job_execution

    fail_args = {}

    def _failed(_id, **kwargs):
        fail_args.update(kwargs)

    raised = False
    with _env(DMA_JOB_EXECUTION_ID="exec-xyz"), \
         patch("workers._runner._safe_mark_started", lambda _id: None), \
         patch("workers._runner._safe_mark_succeeded",
               lambda _id, **kw: (_ for _ in ()).throw(
                   AssertionError("mark_succeeded must not fire on exception")
               )), \
         patch("workers._runner._safe_mark_failed", _failed):

        try:
            with track_job_execution("embedder") as ex:
                ex.update(files_parsed=3)
                raise RuntimeError("simulated worker bug")
        except RuntimeError as e:
            raised = True
            assert "simulated worker bug" in str(e)

    assert raised, "exception must propagate to caller"
    assert "error_message" in fail_args
    assert "simulated worker bug" in fail_args["error_message"]
    assert "stderr_tail" in fail_args
    # Counters captured at time of exception, NOT silently dropped.
    assert fail_args.get("files_parsed") == 3


def test_no_execution_id_creates_row() -> None:
    """DMA_JOB_EXECUTION_ID unset → runner creates a new row for the
    scheduler/cli invocation (trigger_source inferred)."""
    from workers._runner import track_job_execution

    created = {}

    def _create(job_name, mode, trigger_source):
        created["job_name"] = job_name
        created["mode"] = mode
        created["trigger_source"] = trigger_source
        return "new-row-id-123"

    with _env(DMA_JOB_EXECUTION_ID=None), \
         patch("workers._runner._safe_create_row", _create), \
         patch("workers._runner._safe_mark_started", lambda _id: None), \
         patch("workers._runner._safe_mark_succeeded", lambda _id, **kw: None):

        with track_job_execution("peer_patterns", mode="full") as ex:
            assert ex.execution_id == "new-row-id-123"

    assert created["job_name"] == "peer_patterns"
    assert created["mode"] == "full"
    assert created["trigger_source"] in ("cli", "scheduler", "pubsub")


def test_db_unavailable_swallowed() -> None:
    """The inner DB import raises (e.g. job_executions_db module not
    on path, or DATABASE_URL_SYNC unset) → the runner's _safe_*
    helpers MUST swallow + log; body must still run to completion.

    We force this by setting DMA_JOB_EXECUTION_ID + ensuring the
    job_executions_db import will fail (no DATABASE_URL_SYNC). The
    _safe_mark_started / _safe_mark_succeeded internal try/except
    must catch the RuntimeError raised by _get_engine().
    """
    from workers._runner import track_job_execution

    body_executed = False
    with _env(DMA_JOB_EXECUTION_ID="exec-zzz", DATABASE_URL_SYNC=None):
        with track_job_execution("ccg_loader") as ex:
            body_executed = True
            ex.update(rows_added=5)

    assert body_executed, "body must execute even when audit DB is down"


def test_get_current_tracker_returns_active_tracker() -> None:
    """Worker body can reach the active tracker via the thread-local
    accessor without parameter threading. Counter updates published
    via the accessor land in the snapshot."""
    from workers._runner import (
        get_current_tracker,
        track_job_execution,
    )

    captured_counters = {}

    def _succeeded(_id, **kwargs):
        captured_counters.update(kwargs)

    with _env(DMA_JOB_EXECUTION_ID="exec-tl"):
        with patch("workers._runner._safe_mark_started", lambda _id: None):
            with patch("workers._runner._safe_mark_succeeded", _succeeded):
                with track_job_execution("embedder"):
                    # Inside the body — but NOT using the `as ex` binding.
                    # Body code (e.g. embed_run in a deep call stack)
                    # reaches the tracker via the thread-local accessor.
                    ex = get_current_tracker()
                    assert ex is not None
                    ex.update(rows_added=42, files_errored=1)

    # mark_succeeded received the counters via tracker.snapshot()
    assert captured_counters.get("rows_added") == 42
    assert captured_counters.get("files_errored") == 1


def test_get_current_tracker_returns_none_outside_context() -> None:
    """Outside any track_job_execution block, the accessor returns None
    so worker code can safely call it unconditionally."""
    from workers._runner import get_current_tracker
    assert get_current_tracker() is None


def test_nested_track_job_execution_restores_outer() -> None:
    """If a worker happens to nest track_job_execution (rare, but
    possible if a Pub/Sub subscriber wraps each message AND the
    handler itself wraps a sub-job), the outer tracker must be
    restored on inner exit."""
    from workers._runner import (
        get_current_tracker,
        track_job_execution,
    )

    with _env(DMA_JOB_EXECUTION_ID="exec-outer"):
        with patch("workers._runner._safe_mark_started", lambda _id: None):
            with patch("workers._runner._safe_mark_succeeded", lambda _id, **kw: None):
                with track_job_execution("ccg_loader") as outer:
                    assert get_current_tracker() is outer
                    with _env(DMA_JOB_EXECUTION_ID="exec-inner"):
                        with track_job_execution("embedder") as inner:
                            assert get_current_tracker() is inner
                            assert inner is not outer
                        # After inner exits, outer restored.
                        assert get_current_tracker() is outer
    assert get_current_tracker() is None


def test_env_var_restored_after_auto_created_row() -> None:
    """Long-lived subscriber regression: if DMA_JOB_EXECUTION_ID was
    UNSET before track_job_execution and the wrapper auto-creates a
    new row (mutating the env var to the new id), the env var MUST
    be UNSET again on exit. Otherwise the next message in a
    --subscribe loop would reuse the just-completed row id instead
    of creating a fresh one.

    Before this fix: subscriber message #1 auto-creates row R1, sets
    env=R1; message #2 sees env=R1 → wrapper thinks the row is pre-
    existing → all messages share one row that flip-flops forever.
    """
    from workers._runner import track_job_execution

    created_ids = []

    def _create(job_name, mode, trigger_source):
        new = f"row-{len(created_ids)}"
        created_ids.append(new)
        return new

    with _env(DMA_JOB_EXECUTION_ID=None):
        with patch("workers._runner._safe_create_row", _create), \
             patch("workers._runner._safe_mark_started", lambda _id: None), \
             patch("workers._runner._safe_mark_succeeded", lambda _id, **kw: None):

            # First "message" — env unset, should create row-0
            with track_job_execution("embedder"):
                pass
            # Env must be UNSET again, NOT left at row-0
            assert os.environ.get("DMA_JOB_EXECUTION_ID") is None, (
                "env var must be restored to its prior (unset) state "
                "so the next subscriber message creates a fresh row"
            )

            # Second "message" — should create a DIFFERENT row id
            with track_job_execution("embedder"):
                pass

    assert created_ids == ["row-0", "row-1"], (
        f"each subscriber invocation must create a fresh row; "
        f"got {created_ids} (if these are equal, the env-restore "
        f"regressed and rows are bleeding across messages)"
    )


def test_env_var_restored_to_prior_value_when_set() -> None:
    """If env was SET to row-A before the wrapper opens, and the
    wrapper reuses that id, then on exit env must still be row-A
    (not unset, not some other row's id)."""
    from workers._runner import track_job_execution

    with _env(DMA_JOB_EXECUTION_ID="row-A"):
        with patch("workers._runner._safe_mark_started", lambda _id: None), \
             patch("workers._runner._safe_mark_succeeded", lambda _id, **kw: None):
            with track_job_execution("ccg_loader"):
                pass
        # Inside _env block, restoration should leave the env at "row-A"
        assert os.environ.get("DMA_JOB_EXECUTION_ID") == "row-A"


def test_existing_execution_id_used() -> None:
    """When DMA_JOB_EXECUTION_ID is set (admin-UI trigger case), the
    runner does NOT call create_execution_row — the row already exists."""
    from workers._runner import track_job_execution

    create_calls = []

    def _create(*a, **kw):
        create_calls.append((a, kw))
        return "should-not-fire"

    with _env(DMA_JOB_EXECUTION_ID="exec-preexisting"), \
         patch("workers._runner._safe_create_row", _create), \
         patch("workers._runner._safe_mark_started", lambda _id: None), \
         patch("workers._runner._safe_mark_succeeded", lambda _id, **kw: None):

        with track_job_execution("sheet_poller") as ex:
            assert ex.execution_id == "exec-preexisting"

    assert create_calls == [], "create_execution_row must not fire when ID provided"


def test_auto_created_id_does_not_leak_across_invocations() -> None:
    """Regression for long-lived subscriber leak.

    The embedder/intelligence_recompute --subscribe mode run the
    worker body once per Pub/Sub message inside a single long-lived
    process. Each message MUST get its own job_executions row.

    The original bug: when DMA_JOB_EXECUTION_ID was unset, the runner
    auto-created a row + wrote the new id back into os.environ.
    Because nothing UNSET it on context exit, the next message saw
    the prior id, marked the already-succeeded row as "started" again,
    and stamped its progress UPDATEs onto a row that belonged to the
    PREVIOUS task.

    Contract:
      • Pre-existing env value (None) MUST be restored on exit.
      • Auto-created id from invocation N MUST NOT be visible to
        invocation N+1 on the same process.

    This test would FAIL on the prior implementation (which only
    SET the env var and never restored it).
    """
    from workers._runner import track_job_execution

    create_calls = []
    started_with = []
    succeeded_with = []

    # Each create_row call returns a fresh id; we want to prove
    # invocation #2 calls create AGAIN (instead of being misled by
    # invocation #1's stale env var into reusing the prior id).
    next_ids = iter(["row-msg-1", "row-msg-2"])

    def _create(*a, **kw):
        new = next(next_ids)
        create_calls.append(new)
        return new

    def _started(_id):
        started_with.append(_id)

    def _succeeded(_id, **kw):
        succeeded_with.append(_id)

    with _env(DMA_JOB_EXECUTION_ID=None), \
         patch("workers._runner._safe_create_row", _create), \
         patch("workers._runner._safe_mark_started", _started), \
         patch("workers._runner._safe_mark_succeeded", _succeeded):

        # Invocation 1 — simulates Pub/Sub message #1.
        with track_job_execution("embedder", mode="subscribe") as ex1:
            assert ex1.execution_id == "row-msg-1"
            assert os.environ.get("DMA_JOB_EXECUTION_ID") == "row-msg-1"

        # The fix: env var MUST be cleared after exit so the next
        # invocation creates a fresh row instead of reusing row-msg-1.
        assert os.environ.get("DMA_JOB_EXECUTION_ID") is None, (
            "DMA_JOB_EXECUTION_ID leaked across invocations — long-lived "
            "subscriber would stamp message #N+1's progress onto message #N's row"
        )

        # Invocation 2 — simulates Pub/Sub message #2 on the SAME process.
        with track_job_execution("embedder", mode="subscribe") as ex2:
            assert ex2.execution_id == "row-msg-2", (
                "second invocation must get a fresh row id, not reuse "
                "the prior row"
            )

    # Both invocations created independent rows; neither was mistaken
    # for the other.
    assert create_calls == ["row-msg-1", "row-msg-2"]
    assert succeeded_with == ["row-msg-1", "row-msg-2"]
    # Final env restoration — back to None as it was before the test.
    assert os.environ.get("DMA_JOB_EXECUTION_ID") is None


def test_pre_existing_env_id_is_restored_on_exit() -> None:
    """When DMA_JOB_EXECUTION_ID is set BEFORE the context (admin-UI
    trigger path), the runner must restore that exact value on exit
    rather than unsetting it. This protects nested-context cases where
    the OUTER context provided the id, the INNER ran inside it, and
    the OUTER expects its env var still present after the inner exits.
    """
    from workers._runner import track_job_execution

    with _env(DMA_JOB_EXECUTION_ID="exec-outer-preset"), \
         patch("workers._runner._safe_mark_started", lambda _id: None), \
         patch("workers._runner._safe_mark_succeeded", lambda _id, **kw: None):

        with track_job_execution("drive_crawler"):
            assert os.environ["DMA_JOB_EXECUTION_ID"] == "exec-outer-preset"

        # After exit, the pre-existing value must still be present.
        assert os.environ.get("DMA_JOB_EXECUTION_ID") == "exec-outer-preset"
