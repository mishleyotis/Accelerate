"""job_executions service — pure helpers around the `job_executions`
table for the Admin "trigger a worker" surface.

State-transition contract:
  trigger_job(name, mode, source, user)        →   status='running' row
  mark_started(row_id)                          →   confirms running
  update_progress(row_id, **counters)           →   in-place UPDATE
  mark_succeeded(row_id, result_summary, **)   →   running → succeeded
  mark_failed(row_id, error, stderr_tail)      →   running → failed

Pure helpers (no I/O, easy to unit-test):
  validate_job_name(name)                       →   raises ValueError on unknown
  validate_mode(name, mode)                     →   raises ValueError on bad combo
  summarize_execution(row)                      →   {result_summary, error_count}

The `JOB_REGISTRY` is the single source of truth for which job names
the admin endpoint accepts and which modes each supports. Adding a new
worker = adding one entry here + a routes test will exercise it.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

JOB_REGISTRY: dict[str, dict[str, Any]] = {
    "drive_crawler": {
        "modes": {"full", "delta"},
        "default_mode": "delta",
        "description": "Walk the Drive root folder; ingest new + changed packages.",
    },
    "embedder": {
        "modes": {"full", "delta", "entity"},
        "default_mode": "delta",
        "description": "Compute pgvector embeddings for evidence + sections.",
    },
    "peer_patterns": {
        "modes": {"full"},
        "default_mode": "full",
        "description": "KMeans on entity score vectors → peer_archetypes rows.",
    },
    "cross_entity_patterns": {
        "modes": {"full"},
        "default_mode": "full",
        "description": "Recurring subcap gaps + open issues across a "
                       "subvertical cohort → cross_entity_patterns rows.",
    },
    "intelligence_recompute": {
        "modes": {"full", "entity"},
        "default_mode": "entity",
        "description": "Roll runs into customer_intelligence_profiles.",
    },
    "ccg_loader": {
        "modes": {"full"},
        "default_mode": "full",
        "description": "Re-load V7 capability catalogue from XLSX workbooks.",
    },
    "sheet_poller": {
        "modes": {"once"},
        "default_mode": "once",
        "description": "Poll Ops Sheet for new requests + AE-assignment changes.",
    },
    "chat_learning": {
        # Nightly rollup over chat_messages → chat_learning_signals.
        # dry-run prints what it would write without persisting.
        "modes": {"live", "dry-run"},
        "default_mode": "live",
        "description": "KMeans rollup of chat feedback into reranker signals.",
    },
    "historical_backfill": {
        # full   → walk every '* - DMA' folder under DRIVE_ROOT_FOLDER_ID
        # retry  → re-run ONLY folders whose latest quarantine outcome was
        #          failed_* or skipped_no_report (sets --retry-failed-only
        #          via args.extra_args)
        "modes": {"full", "retry"},
        "default_mode": "full",
        "description": (
            "Walk Drive folders and ingest DMA packages. "
            "Use mode=retry + extra_args=['--retry-failed-only'] for "
            "per-folder quarantine retry."
        ),
    },
}


def validate_job_name(name: str) -> None:
    """Raises ValueError if `name` is not a known job. Pure."""
    if name not in JOB_REGISTRY:
        known = ", ".join(sorted(JOB_REGISTRY))
        raise ValueError(f"unknown job_name '{name}' — must be one of: {known}")


def validate_mode(name: str, mode: str | None) -> str:
    """Validates / defaults `mode` against the registry. Returns the
    canonical mode string. Pure."""
    validate_job_name(name)
    spec = JOB_REGISTRY[name]
    if mode is None:
        return spec["default_mode"]
    if mode not in spec["modes"]:
        ok = ", ".join(sorted(spec["modes"]))
        raise ValueError(f"mode '{mode}' invalid for {name}; allowed: {ok}")
    return mode


def summarize_execution(row: dict[str, Any]) -> dict[str, Any]:
    """Builds a small {result_summary, error_count} dict for the admin
    UI's 'Last run' label. Pure.

    Logic:
      - running + counts present      → 'N/M folders (ok=A skip=B fail=C)'
      - running + no counts yet       → 'starting…'
      - succeeded + counts present    → 'N files parsed, M rows added' etc.
      - failed                        → first 80 chars of error_message
      - cancelled                     → 'cancelled by operator'
    """
    status = row.get("status")
    if status == "running":
        # Surface LIVE counters during a run. Pre-this-fix the result_summary
        # cell on the admin UI rendered the literal string 'in progress'
        # regardless of how many folders the worker had already chewed
        # through — operators thought the worker was stuck even when the
        # counters were updating in real time. The OperationsPanel
        # renders `result_summary` as the Progress cell; surfacing the
        # actual counters here is the single most impactful UI fix.
        folders_seen = row.get("folders_seen")
        files_parsed = row.get("files_parsed") or 0
        files_skipped = row.get("files_skipped") or 0
        files_errored = row.get("files_errored") or 0
        progressed = files_parsed + files_skipped + files_errored
        if folders_seen is None and progressed == 0:
            return {"result_summary": "starting…", "error_count": 0}
        if folders_seen is not None and folders_seen > 0:
            pct = int(100 * progressed / folders_seen) if folders_seen else 0
            return {
                "result_summary": (
                    f"{progressed}/{folders_seen} folders ({pct}%) "
                    f"— ok={files_parsed} skip={files_skipped} "
                    f"fail={files_errored}"
                ),
                "error_count": files_errored,
            }
        # Counters present but no folders_seen total → show what we know.
        return {
            "result_summary": (
                f"{progressed} processed — ok={files_parsed} "
                f"skip={files_skipped} fail={files_errored}"
            ),
            "error_count": files_errored,
        }
    if status == "cancelled":
        return {"result_summary": "cancelled by operator", "error_count": 0}
    if status == "failed":
        msg = (row.get("error_message") or "failed").strip()
        return {
            "result_summary": msg[:80] + ("…" if len(msg) > 80 else ""),
            "error_count": 1,
        }
    # succeeded
    parts: list[str] = []
    files_parsed = row.get("files_parsed")
    files_errored = row.get("files_errored") or 0
    files_skipped = row.get("files_skipped") or 0
    rows_added = row.get("rows_added")
    folders_seen = row.get("folders_seen")
    if folders_seen is not None:
        parts.append(f"{folders_seen} folders seen")
    if files_parsed is not None:
        parts.append(f"{files_parsed} parsed")
    if files_skipped:
        parts.append(f"{files_skipped} skipped")
    if rows_added is not None:
        parts.append(f"{rows_added} rows")
    if not parts:
        parts.append("ok")
    return {
        "result_summary": ", ".join(parts),
        "error_count": int(files_errored or 0),
    }


def humanize_duration(started_at: datetime | None, completed_at: datetime | None) -> str:
    """Pure — returns a 'Xs / Xm Ys' string for the admin status line."""
    if started_at is None:
        return "—"
    end = completed_at or datetime.now(UTC).astimezone(started_at.tzinfo)
    secs = max(0, int((end - started_at).total_seconds()))
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    return f"{m}m {s}s"
