"""Per-tab Ops-sheet handlers.

Each handler is a pure function: takes a list of dict-rows (as produced by
the Sheets API), returns a list of dict-rows ready for SQL upsert. Side
effects (SQL writes, SSE emits) happen in main.py; handlers are testable
without a database.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_dt(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _bool_or_none(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes", "1", "y", "t"):
        return True
    if s in ("false", "no", "0", "n", "f"):
        return False
    return None


def _float_or_none(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_request_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map a Requests-tab row to an ops_requests insert dict.

    Per plan ④, sheet column names are stable; columns we don't recognize
    are dropped (we never want loose columns to break the load).
    """
    return {
        "request_id": _str_or_none(row.get("request_id")),
        "ts_utc": _parse_dt(row.get("ts_utc")),
        "requester_slack_id": _str_or_none(row.get("requester_slack_id")),
        "requester_name": _str_or_none(row.get("requester_name")),
        "submitter_slack_id": _str_or_none(row.get("submitter_slack_id")),
        "submitter_name": _str_or_none(row.get("submitter_name")),
        "entity": _str_or_none(row.get("entity")),
        "domain": _str_or_none(row.get("domain")),
        "mode": (_str_or_none(row.get("mode")) or "public").lower(),
        "notes": _str_or_none(row.get("notes")),
        "priority": _str_or_none(row.get("priority")),
        "source": _str_or_none(row.get("source")),
        "parent_request_id": _str_or_none(row.get("parent_request_id")),
        "requested_due_date": _parse_dt(row.get("requested_due_date")),
        "assigned_to": _str_or_none(row.get("assigned_to")),
        "scheduled_date": _parse_dt(row.get("scheduled_date")),
        "status": (_str_or_none(row.get("status")) or "pending").lower(),
        "delivered_date": _parse_dt(row.get("delivered_date")),
        "folder_url": _str_or_none(row.get("folder_url")),
        "assessment_url": _str_or_none(row.get("assessment_url")),
        "research_url": _str_or_none(row.get("research_url")),
        "deck_url": _str_or_none(row.get("deck_url")),
        "sla_met": _bool_or_none(row.get("sla_met")),
        "last_updated_utc": _parse_dt(row.get("last_updated_utc")),
        "workflow_ts": _str_or_none(row.get("workflow_ts")),
        "feedback_status": _str_or_none(row.get("feedback_status")),
        "feedback_rating": (
            int(row["feedback_rating"])
            if row.get("feedback_rating") not in (None, "")
            else None
        ),
        "feedback_comments": _str_or_none(row.get("feedback_comments")),
        "feedback_at_utc": _parse_dt(row.get("feedback_at_utc")),
    }


def normalize_team_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slack_id": _str_or_none(row.get("slack_id")),
        "name": _str_or_none(row.get("name")),
        "calendar_id": _str_or_none(row.get("calendar_id")),
        "daily_cap": _float_or_none(row.get("daily_cap")),
        "stretch_eligible": _bool_or_none(row.get("stretch_eligible")) or False,
        "active": _bool_or_none(row.get("active")) if row.get("active") is not None else True,
    }


def normalize_audit_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "s_utc": _parse_dt(row.get("s_utc")),
        "request_id": _str_or_none(row.get("request_id")),
        "action": _str_or_none(row.get("action")),
        "actor_slack_id": _str_or_none(row.get("actor_slack_id")),
        "before_json": row.get("before_json"),
        "after_json": row.get("after_json"),
    }


def normalize_comments_row(row: dict[str, Any]) -> dict[str, Any]:
    visibility = (_str_or_none(row.get("visibility")) or "external").lower()
    if visibility not in ("internal", "external"):
        visibility = "external"
    return {
        "comment_id": _str_or_none(row.get("comment_id")),
        "request_id": _str_or_none(row.get("request_id")),
        "ts_utc": _parse_dt(row.get("ts_utc")),
        "author_slack_id": _str_or_none(row.get("author_slack_id")),
        "author_name": _str_or_none(row.get("author_name")),
        "body": _str_or_none(row.get("body")),
        "visibility": visibility,
        "notified_at": _parse_dt(row.get("notified_at")),
    }


# ---------- run-status sync ----------

# Map Ops-sheet `status` strings → our local `runs.status` enum.
STATUS_MAP: dict[str, str] = {
    "pending": "IN_PROGRESS",
    "in_progress": "IN_PROGRESS",
    "delivered": "ACTIVE",
    "cancelled": "FAILED",
    "needs_review": "PENDING_REVIEW",
    "stale": "STALE",
}


def map_sheet_status_to_run(sheet_status: str | None) -> str | None:
    if not sheet_status:
        return None
    return STATUS_MAP.get(sheet_status.lower())


def detect_drive_url_in_comment(body: str | None) -> bool:
    """When a comment body contains a Drive URL, the request may need a
    public → hybrid evidence_mode upgrade. Detection only — admin proposes.
    """
    if not body:
        return False
    return "drive.google.com" in body.lower()
