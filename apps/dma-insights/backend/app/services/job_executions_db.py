"""SQL-executing lifecycle helpers for `job_executions`.

The pure `app.services.job_executions` module owns the JOB_REGISTRY,
validation, and summary helpers. This module owns the I/O — the
SQL UPDATEs that move a row through the running → succeeded / failed
state machine.

State transitions (single-row lifecycle):
  create_execution_row(name, mode, source)
      → INSERT status='running', started_at=NOW(). Returns row id.
  mark_started(row_id)
      → UPDATE; no-op if row already at status='running' (idempotent).
  update_progress(row_id, **counters)
      → UPDATE the per-row counters (folders_seen / files_parsed / etc).
  mark_succeeded(row_id, **counters)
      → UPDATE status='succeeded', completed_at=NOW(), duration_sec,
        merging final counters in.
  mark_failed(row_id, error_message, stderr_tail, **counters)
      → UPDATE status='failed', completed_at=NOW(), capturing the
        error message + tail for the JobLogDrawer.

All helpers use a SHORT-LIVED sync engine (psycopg) — workers must
not hold the connection across job iterations. Sync (not async)
because workers run synchronous code. The engine is cached at module
level so repeated lifecycle calls inside one worker run share the
pool.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = structlog.get_logger()


_engine: Engine | None = None


def _get_engine() -> Engine:
    """Lazy sync engine cached at module level. Workers reuse one
    pool across all lifecycle calls within a single execution."""
    global _engine
    if _engine is None:
        # Workers historically only had `DATABASE_URL` (asyncpg)
        # injected by terraform — the explicit `DATABASE_URL_SYNC`
        # path is reserved for the migrations job, which uses a
        # different secret (superuser). `resolve_sync_dsn` derives
        # the sync DSN from `DATABASE_URL` when the explicit var
        # is missing. Single resolver, used by every sync-DB path
        # (job_executions, synthesis_cache, ccg_loader_runs).
        from app.services.sync_dsn import resolve_sync_dsn
        url = resolve_sync_dsn()
        if not url:
            raise RuntimeError(
                "Neither DATABASE_URL_SYNC nor DATABASE_URL is set "
                "— job_executions lifecycle calls require a sync DSN. "
                "(Local-dev workers without a DB should run with "
                "DMA_JOB_EXECUTION_ID unset; the runner safely no-ops.)"
            )
        _engine = create_engine(url, pool_pre_ping=True, pool_size=2)
    return _engine


# Counters that map 1:1 to `job_executions` columns. Anything else
# passed via **counters is silently dropped (so workers can pass
# arbitrary kwargs without breaking on schema drift).
_COLUMN_COUNTERS = {
    "folders_seen", "folders_new", "folders_changed",
    "files_parsed", "files_skipped", "files_errored",
    "rows_added", "rows_updated", "rows_deleted",
    "parser_warnings",
}


# Counter columns that are JSONB — their value must be JSON-serialized
# and the SET clause must CAST, since psycopg can't auto-adapt a Python
# list/dict to jsonb (2026-06-10 deploy-sim: ccg_loader passed
# parser_warnings as list[dict] and EVERY job-tracking UPDATE raised
# "cannot adapt type 'dict'", so completed jobs were recorded failed).
_JSONB_COUNTERS = {"parser_warnings"}


def _filter_counters(counters: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in counters.items():
        if k not in _COLUMN_COUNTERS:
            continue
        out[k] = json.dumps(v) if k in _JSONB_COUNTERS and not isinstance(v, str) else v
    return out


def _set_clause(col: str) -> str:
    """`col = :col`, with a ::jsonb cast for JSONB counter columns."""
    return f"{col} = CAST(:{col} AS JSONB)" if col in _JSONB_COUNTERS else f"{col} = :{col}"


def create_execution_row(
    *,
    job_name: str,
    mode: str | None,
    trigger_source: str,
    triggered_by_user_id: str | None = None,
) -> str:
    """INSERT a new row, status='running'. Returns the row id (uuid
    string). Used by scheduler / pubsub / CLI invocations that don't
    have a pre-existing execution_id."""
    row_id = str(uuid.uuid4())
    eng = _get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
            INSERT INTO job_executions
                (id, job_name, mode, triggered_by_user_id, trigger_source,
                 status, started_at)
            VALUES
                (:id, :job_name, :mode, :user_id, :trigger_source,
                 'running', NOW())
        """), {
            "id": row_id,
            "job_name": job_name,
            "mode": mode,
            "user_id": triggered_by_user_id,
            "trigger_source": trigger_source,
        })
    return row_id


def mark_started(execution_id: str) -> None:
    """Idempotent — if the row is already at status='running' this
    only updates the started_at timestamp (a no-op for admin-UI
    triggers that already set it; meaningful for pub/sub redeliveries
    where the actual processing didn't begin until now)."""
    eng = _get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
            UPDATE job_executions
            SET started_at = COALESCE(started_at, NOW()),
                status = 'running'
            WHERE id = :id
              AND status IN ('running', 'pending')
        """), {"id": execution_id})


def update_progress(execution_id: str, **counters: Any) -> None:
    """Cheap mid-run counter UPDATE. Workers call this liberally."""
    filtered = _filter_counters(counters)
    if not filtered:
        return
    set_clauses = ", ".join(_set_clause(k) for k in filtered)
    eng = _get_engine()
    with eng.begin() as conn:
        conn.execute(
            text(f"UPDATE job_executions SET {set_clauses} WHERE id = :id"),
            {**filtered, "id": execution_id},
        )


def mark_succeeded(execution_id: str, **counters: Any) -> None:
    """RUNNING → SUCCEEDED. Computes duration_sec from started_at."""
    filtered = _filter_counters(counters)
    set_extras = ""
    if filtered:
        set_extras = ", " + ", ".join(_set_clause(k) for k in filtered)
    eng = _get_engine()
    with eng.begin() as conn:
        conn.execute(text(f"""
            UPDATE job_executions
            SET status = 'succeeded',
                completed_at = NOW(),
                duration_sec = EXTRACT(EPOCH FROM (NOW() - started_at))
                {set_extras}
            WHERE id = :id
        """), {**filtered, "id": execution_id})


def mark_failed(
    execution_id: str,
    *,
    error_message: str,
    stderr_tail: str,
    **counters: Any,
) -> None:
    """RUNNING → FAILED. Captures the error message + stderr tail
    so the admin JobLogDrawer renders meaningful content."""
    filtered = _filter_counters(counters)
    set_extras = ""
    if filtered:
        set_extras = ", " + ", ".join(_set_clause(k) for k in filtered)
    eng = _get_engine()
    with eng.begin() as conn:
        conn.execute(text(f"""
            UPDATE job_executions
            SET status = 'failed',
                completed_at = NOW(),
                duration_sec = EXTRACT(EPOCH FROM (NOW() - started_at)),
                error_message = :err,
                stderr_tail = :tail
                {set_extras}
            WHERE id = :id
        """), {
            "id": execution_id,
            "err": error_message[:500],
            "tail": stderr_tail[:8000],
            **filtered,
        })


def mark_cancelled(
    execution_id: str,
    *,
    cancelled_by_email: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """RUNNING → CANCELLED. Used by the /admin/jobs/executions/{id}:abort
    endpoint when the operator clicks Abort.

    Returns the post-update row mapping (id, status, completed_at,
    error_message) so the API can surface the new state in its response.

    Idempotent: re-running on an already-cancelled (or already-finished)
    row is a no-op — the UPDATE WHERE clause filters out non-running
    rows. Returns the row's current state regardless.
    """
    err_message = "aborted by operator"
    if cancelled_by_email:
        err_message = f"aborted by {cancelled_by_email}"
    if reason:
        err_message = f"{err_message}: {reason[:200]}"
    eng = _get_engine()
    with eng.begin() as conn:
        row = conn.execute(text("""
            UPDATE job_executions
            SET status = 'cancelled',
                completed_at = NOW(),
                duration_sec = EXTRACT(EPOCH FROM (NOW() - started_at)),
                error_message = COALESCE(error_message, :err)
            WHERE id = :id
              AND status = 'running'
            RETURNING id, status, started_at, completed_at,
                      duration_sec, job_name, error_message
        """), {"id": execution_id, "err": err_message[:500]}).mappings().first()
        if row is None:
            # Row wasn't running — fetch its current state so the caller
            # can surface "already finished" vs "found + cancelled".
            row = conn.execute(text("""
                SELECT id, status, started_at, completed_at,
                       duration_sec, job_name, error_message
                  FROM job_executions
                 WHERE id = :id
            """), {"id": execution_id}).mappings().first()
    return dict(row) if row else {}


def reset_engine_for_tests() -> None:
    """Test hook — clears the cached engine so tests can swap
    DATABASE_URL_SYNC between cases."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
