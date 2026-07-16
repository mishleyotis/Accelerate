"""Worker execution runner — context manager wrapping every worker
entrypoint so the admin `job_executions` row gets a real status
update (RUNNING → SUCCEEDED / FAILED) plus counter updates as work
progresses.

Without this wrapper, the admin pill on `/admin` would stay at
"RUNNING" forever after a button click — the backend endpoint
inserts the row at status='running' on click, but no one ever
flipped it to 'succeeded'.

State transitions handled here:
  __enter__
    - Read `DMA_JOB_EXECUTION_ID` env var (set by the
      /admin/jobs:execute endpoint via Cloud Run Job env).
    - If present  → call `mark_started(execution_id)` (idempotent;
                    the row is already at status='running').
    - If absent   → scheduler-triggered or CLI invocation; create a
                    fresh row with trigger_source='scheduler' or
                    'cli' so the admin UI sees it next refresh.
  update(**counters)
    - Mid-run progress UPDATE. Cheap; called liberally as the
      worker processes folders / files / rows.
  __exit__ (no exception)
    - `mark_succeeded(execution_id, **final_counters)`. Flips the
      pill from RUNNING → SUCCEEDED.
  __exit__ (exception)
    - `mark_failed(execution_id, error_message, stderr_tail)`. Pill
      flips RUNNING → FAILED; admin UI mounts JobLogDrawer with the
      tail when the operator clicks "View log".

Resilience:
  - DB unavailable at __enter__ → context manager STILL runs the
    worker body (we'd rather process the job than fail on
    audit-table issues). Logs a warning.
  - DB unavailable at __exit__ → same: log + swallow. The next
    scheduler tick OR the admin UI's stale-row sweep will reconcile.
"""
from __future__ import annotations

import os
import sys
import threading
import traceback
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger()


# Thread-local pointer to the active _ExecutionTracker, populated by
# track_job_execution. Lets worker bodies that aren't directly inside
# a `with track_job_execution(...) as ex:` block still publish counter
# updates without needing the `ex` parameter threaded through every
# function call. The classic worker pattern is:
#
#     if __name__ == "__main__":
#         with track_job_execution("name"):
#             raise SystemExit(main())
#
# Inside `main()` (or any function it calls), code can do:
#
#     from workers._runner import get_current_tracker
#     ex = get_current_tracker()
#     if ex is not None:
#         ex.update(folders_seen=N, files_parsed=M)
#
# Thread-local so concurrent invocations don't cross-contaminate each
# other's counters (e.g., the Pub/Sub subscriber spawns one task per
# message).
_local = threading.local()


def get_current_tracker():
    """Returns the active _ExecutionTracker if a track_job_execution
    context is open in this thread, else None. Safe to call
    unconditionally — the None return is the no-op signal."""
    return getattr(_local, "tracker", None)


class _ExecutionTracker:
    """Mutable handle exposing .update(**counters) to the worker body."""

    def __init__(self, execution_id: str | None, job_name: str, mode: str | None) -> None:
        self.execution_id = execution_id
        self.job_name = job_name
        self.mode = mode
        self._counters: dict[str, Any] = {}
        self._started_at = datetime.now(UTC)

    def update(self, **counters: Any) -> None:
        """Merge counters into the in-memory snapshot. Optionally
        flushes to DB if `flush=True` is passed (default False — we
        only flush at __exit__ to avoid one round-trip per row)."""
        flush = counters.pop("flush", False)
        self._counters.update(counters)
        if flush and self.execution_id:
            _safe_update_db(self.execution_id, **counters)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._counters)


@contextmanager
def track_job_execution(job_name: str, mode: str | None = None):
    """Context manager wrapping a worker run with `job_executions`
    lifecycle updates.

    Usage in each worker `main.py`:

        from workers._runner import track_job_execution

        def main(argv=None) -> int:
            with track_job_execution("drive_crawler", mode="full") as ex:
                folders = list_dma_folders()
                ex.update(folders_seen=len(folders))
                for f in folders:
                    ingest(f)
                ex.update(files_parsed=ex.snapshot().get('files_parsed', 0) + 1)
            return 0
    """
    # 2026-05-28 audit fix: fire the production-readiness guard before
    # the worker does any real work. Backend service calls this from
    # app/main.py::on_startup; workers never did, so a Cloud Run Job
    # could boot with missing DATABASE_URL / GCP_PROJECT_ID and silently
    # no-op every step. Run only when ENV is set to prod/dev (the guard
    # short-circuits on local/test); failures here exit the container
    # non-zero so Cloud Run flips the revision unhealthy.
    try:
        from app.config import assert_production_ready, get_settings
        _settings = get_settings()
        assert_production_ready(_settings, role="worker")
    except RuntimeError:
        # Re-raise to fail the container -- the operator sees the
        # exact missing-secret list in Cloud Logging.
        raise
    except Exception as _guard_exc:
        # Importing app.config can fail in pure-CLI dev contexts where
        # PYTHONPATH doesn't include the backend. Log + continue --
        # we'd rather run the worker than hard-fail on dev imports.
        log.warning(
            "worker.production_guard_skipped",
            err=str(_guard_exc), job_name=job_name,
        )

    execution_id = os.environ.get("DMA_JOB_EXECUTION_ID")
    tracker = _ExecutionTracker(execution_id, job_name, mode)

    # Snapshot the prior env value so we can restore it in `finally`.
    # CRITICAL — without restore, long-lived workers (e.g. embedder
    # --subscribe, intelligence_recompute --subscribe) leak the
    # auto-created id across successive Pub/Sub messages: message #1
    # auto-creates row R1, sets env=R1; message #2 finds env=R1 and
    # writes its status updates onto row R1 instead of getting a fresh
    # row. The result is one "running" row that flips back and forth
    # forever, while the admin pill misreports cross-task counters.
    _prior_env_execution_id = execution_id

    # Mark started (or create row for scheduler/cli invocations).
    if execution_id:
        _safe_mark_started(execution_id)
    else:
        new_id = _safe_create_row(job_name, mode, trigger_source=_infer_trigger_source())
        if new_id:
            tracker.execution_id = new_id
            os.environ["DMA_JOB_EXECUTION_ID"] = new_id     # for nested contexts

    log.info(
        "worker.start",
        job_name=job_name,
        mode=mode,
        execution_id=tracker.execution_id,
    )
    # Publish to the thread-local so downstream code can grab it
    # without parameter threading. Restored on exit.
    _prior_tracker = getattr(_local, "tracker", None)
    _local.tracker = tracker
    try:
        yield tracker
    except (SystemExit, KeyboardInterrupt) as e:
        # 2026-06-10 deploy-sim: workers end with `raise SystemExit(main())`.
        # A clean exit (code 0 / None) is SUCCESS, not failure — but
        # SystemExit is a BaseException, so the old `except BaseException`
        # recorded EVERY completed job (ccg_loader, embedder, …) as FAILED
        # in the admin Operations panel. Treat exit-0 SystemExit as success;
        # only a non-zero code is a real failure.
        code = e.code if isinstance(e, SystemExit) else 1
        if code in (0, None):
            if tracker.execution_id:
                _safe_mark_succeeded(tracker.execution_id, **tracker.snapshot())
            log.info("worker.succeeded", job_name=job_name,
                     execution_id=tracker.execution_id)
        else:
            tb = traceback.format_exc()
            tail = "\n".join(tb.splitlines()[-30:])
            if tracker.execution_id:
                _safe_mark_failed(
                    tracker.execution_id,
                    error_message=f"exited with code {code}",
                    stderr_tail=tail, **tracker.snapshot(),
                )
            log.error("worker.failed", job_name=job_name,
                      execution_id=tracker.execution_id, error=f"exit {code}")
        raise
    except BaseException as e:
        # Capture stderr tail + first error line for admin log drawer.
        tb = traceback.format_exc()
        tail = "\n".join(tb.splitlines()[-30:])
        err_line = str(e).splitlines()[0][:200] if str(e) else type(e).__name__
        if tracker.execution_id:
            _safe_mark_failed(
                tracker.execution_id,
                error_message=err_line,
                stderr_tail=tail,
                **tracker.snapshot(),
            )
        log.error(
            "worker.failed",
            job_name=job_name,
            execution_id=tracker.execution_id,
            error=err_line,
        )
        raise
    else:
        if tracker.execution_id:
            _safe_mark_succeeded(tracker.execution_id, **tracker.snapshot())
        log.info(
            "worker.succeeded",
            job_name=job_name,
            execution_id=tracker.execution_id,
            counters=tracker.snapshot(),
        )
    finally:
        # Restore prior tracker (handles nested track_job_execution
        # contexts) so we don't leak state between independent
        # invocations on the same thread.
        _local.tracker = _prior_tracker
        # Restore prior env value. If we auto-created a row here (and
        # the prior env value was unset), this UNSETS the env var so
        # the next invocation on the same process creates a fresh row
        # instead of stamping its updates onto the just-completed row.
        if _prior_env_execution_id is None:
            os.environ.pop("DMA_JOB_EXECUTION_ID", None)
        else:
            os.environ["DMA_JOB_EXECUTION_ID"] = _prior_env_execution_id


def _infer_trigger_source() -> str:
    """If we ended up here without an execution_id, infer how we got
    triggered for audit purposes. Cloud Scheduler sets specific env
    vars on its OIDC tokens; we approximate by checking if we're in
    a TTY (CLI) vs a Cloud Run Job (scheduler/pubsub)."""
    if sys.stdin.isatty():
        return "cli"
    if os.environ.get("CLOUD_RUN_JOB"):
        return "scheduler"
    if os.environ.get("PUBSUB_MESSAGE_ID"):
        return "pubsub"
    return "scheduler"


# ── DB helpers — all swallow errors so the worker body never fails on
# audit-table issues ────────────────────────────────────────────────────

def _safe_mark_started(execution_id: str) -> None:
    try:
        from app.services.job_executions_db import mark_started
        mark_started(execution_id)
    except Exception as e:
        log.warning("job_executions.mark_started_failed", err=str(e))


def _safe_mark_succeeded(execution_id: str, **counters: Any) -> None:
    try:
        from app.services.job_executions_db import mark_succeeded
        mark_succeeded(execution_id, **counters)
    except Exception as e:
        log.warning("job_executions.mark_succeeded_failed", err=str(e))


def _safe_mark_failed(execution_id: str, error_message: str,
                      stderr_tail: str, **counters: Any) -> None:
    try:
        from app.services.job_executions_db import mark_failed
        mark_failed(execution_id, error_message=error_message,
                    stderr_tail=stderr_tail, **counters)
    except Exception as e:
        log.warning("job_executions.mark_failed_failed", err=str(e))


def _safe_create_row(job_name: str, mode: str | None,
                     trigger_source: str) -> str | None:
    """Create a job_executions row for an entrypoint that wasn't given
    an existing DMA_JOB_EXECUTION_ID. Failure to write the row means
    the worker runs INVISIBLY — the admin UI shows no execution, no
    counters, no abort affordance. That was the gap that drove the
    operator's "UI shows no runs even while CLI jobs run" complaint.

    Strategy on failure:
      - Print a LOUD WARNING to stderr (visible in Cloud Run logs +
        in the operator's terminal when running from gcloud CLI).
      - Return None so the caller continues — we don't BLOCK ingest
        on DB-write failure; better to ingest invisibly than not at all.
      - structlog the underlying error for forensics.

    The new Secret Manager fallback in `resolve_sync_dsn` covers the
    common Cloud Shell path; this warning fires only when even that
    fails (no ADC, IAM denied, etc.).
    """
    try:
        from app.services.job_executions_db import create_execution_row
        return create_execution_row(
            job_name=job_name, mode=mode, trigger_source=trigger_source,
        )
    except Exception as e:
        log.warning(
            "job_executions.create_failed",
            err=str(e), job_name=job_name, trigger_source=trigger_source,
        )
        # LOUD operator-visible warning — every CLI / Cloud Shell
        # operator must see this if their run is going to be invisible
        # to the admin UI.
        try:
            import sys
            print("", file=sys.stderr, flush=True)
            print(
                "╔══════════════════════════════════════════════════════════════╗",
                file=sys.stderr, flush=True,
            )
            print(
                "║  WARNING: job_executions row NOT written.                     ║",
                file=sys.stderr, flush=True,
            )
            print(
                "║  This run will NOT appear in the admin UI.                    ║",
                file=sys.stderr, flush=True,
            )
            print(
                "║  Cause: cannot resolve sync DSN (DATABASE_URL_SYNC unset +    ║",
                file=sys.stderr, flush=True,
            )
            print(
                "║  Secret Manager fallback failed). Worker will run             ║",
                file=sys.stderr, flush=True,
            )
            print(
                "║  invisibly. To fix:                                           ║",
                file=sys.stderr, flush=True,
            )
            print(
                "║    a. Set DATABASE_URL_SYNC=postgresql+psycopg://...           ║",
                file=sys.stderr, flush=True,
            )
            print(
                "║    b. Or run via `gcloud run jobs execute ...` (Terraform     ║",
                file=sys.stderr, flush=True,
            )
            print(
                "║       wires DATABASE_URL_SYNC into the Cloud Run Job env).    ║",
                file=sys.stderr, flush=True,
            )
            print(
                f"║  Error: {(str(e) or type(e).__name__)[:50]:<53}║",
                file=sys.stderr, flush=True,
            )
            print(
                "╚══════════════════════════════════════════════════════════════╝",
                file=sys.stderr, flush=True,
            )
            print("", file=sys.stderr, flush=True)
        except Exception:
            # Print failure → swallow (worker continues regardless).
            pass
        return None


def _safe_update_db(execution_id: str, **counters: Any) -> None:
    try:
        from app.services.job_executions_db import update_progress
        update_progress(execution_id, **counters)
    except Exception as e:
        log.warning("job_executions.update_progress_failed", err=str(e))
