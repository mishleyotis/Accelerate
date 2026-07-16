"""Tests for the pure sheet-poller normalization handlers."""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

# Workers package is one level up from the backend root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.sheet_poller.handlers import (  # noqa: E402
    detect_drive_url_in_comment,
    map_sheet_status_to_run,
    normalize_audit_row,
    normalize_comments_row,
    normalize_request_row,
    normalize_team_row,
)


class TestNormalizeRequestRow:
    def test_happy_path(self) -> None:
        out = normalize_request_row({
            "request_id": "REQ-A6654887",
            "ts_utc": "2026-05-20T15:00:00Z",
            "entity": "Farm Credit East",
            "domain": "farmcrediteast.com",
            "mode": "hybrid",
            "status": "in_progress",
            "assigned_to": "Mishley",
            "last_updated_utc": "2026-05-20T15:30:00Z",
            "feedback_rating": "9",
        })
        assert out["request_id"] == "REQ-A6654887"
        assert out["mode"] == "hybrid"
        assert out["status"] == "in_progress"
        assert out["assigned_to"] == "Mishley"
        assert out["entity"] == "Farm Credit East"
        assert out["ts_utc"] == datetime(2026, 5, 20, 15, 0, 0, tzinfo=UTC)
        assert out["last_updated_utc"] == datetime(2026, 5, 20, 15, 30, 0, tzinfo=UTC)
        assert out["feedback_rating"] == 9

    def test_mode_defaults_to_public_and_lowercased(self) -> None:
        out = normalize_request_row({"request_id": "REQ-X", "mode": "HYBRID"})
        assert out["mode"] == "hybrid"
        out2 = normalize_request_row({"request_id": "REQ-X", "mode": ""})
        assert out2["mode"] == "public"

    def test_empty_strings_become_none(self) -> None:
        out = normalize_request_row({
            "request_id": "REQ-X", "domain": "", "notes": "  ",
        })
        assert out["domain"] is None
        assert out["notes"] is None

    def test_bad_date_strings_become_none(self) -> None:
        out = normalize_request_row({"request_id": "REQ-X", "ts_utc": "not-a-date"})
        assert out["ts_utc"] is None


class TestNormalizeTeamRow:
    def test_active_defaults_true(self) -> None:
        out = normalize_team_row({
            "slack_id": "U123", "name": "Mishley",
            "calendar_id": "mishley.otiende@zennify.com",
        })
        assert out["active"] is True
        assert out["stretch_eligible"] is False

    def test_explicit_active_false(self) -> None:
        out = normalize_team_row({
            "slack_id": "U123", "name": "X", "calendar_id": "x@zennify.com",
            "active": "false",
        })
        assert out["active"] is False

    def test_daily_cap_parsed(self) -> None:
        out = normalize_team_row({
            "slack_id": "U", "name": "X", "calendar_id": "x@y",
            "daily_cap": "2.5",
        })
        assert out["daily_cap"] == 2.5


class TestNormalizeAuditRow:
    def test_keeps_json_blobs(self) -> None:
        before = {"status": "pending"}
        after = {"status": "in_progress"}
        out = normalize_audit_row({
            "s_utc": "2026-05-20T15:30:00Z",
            "request_id": "REQ-A1B2C3D4",
            "action": "status_change",
            "actor_slack_id": "U123",
            "before_json": before,
            "after_json": after,
        })
        assert out["before_json"] == before
        assert out["after_json"] == after
        assert out["action"] == "status_change"


class TestNormalizeCommentsRow:
    def test_visibility_defaults_to_external(self) -> None:
        out = normalize_comments_row({"comment_id": "C1", "request_id": "R",
                                       "body": "hi", "visibility": ""})
        assert out["visibility"] == "external"

    def test_visibility_internal(self) -> None:
        out = normalize_comments_row({"comment_id": "C1", "request_id": "R",
                                       "body": "x", "visibility": "INTERNAL"})
        assert out["visibility"] == "internal"

    def test_bad_visibility_defaults_external(self) -> None:
        out = normalize_comments_row({"comment_id": "C1", "request_id": "R",
                                       "body": "x", "visibility": "private"})
        assert out["visibility"] == "external"


class TestStatusMapping:
    def test_known_mappings(self) -> None:
        assert map_sheet_status_to_run("pending") == "IN_PROGRESS"
        assert map_sheet_status_to_run("delivered") == "ACTIVE"
        assert map_sheet_status_to_run("cancelled") == "FAILED"

    def test_case_insensitive(self) -> None:
        assert map_sheet_status_to_run("DELIVERED") == "ACTIVE"

    def test_unknown_returns_none(self) -> None:
        assert map_sheet_status_to_run("zombie") is None
        assert map_sheet_status_to_run(None) is None


class TestDriveUrlDetection:
    def test_detects_drive_url(self) -> None:
        assert detect_drive_url_in_comment(
            "see https://drive.google.com/file/d/abc/view"
        )

    def test_case_insensitive(self) -> None:
        assert detect_drive_url_in_comment("https://Drive.Google.COM/x")

    def test_no_url(self) -> None:
        assert detect_drive_url_in_comment("just a note") is False

    def test_none_safe(self) -> None:
        assert detect_drive_url_in_comment(None) is False
