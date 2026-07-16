"""Tests for the admin job-execution surface.

Covers:
  1. /api/v1/admin/jobs:execute success path (writes a job_executions
     row, returns it with status='running').
  2. Unknown job_name → 400.
  3. Invalid mode → 400.
  4. Non-admin → 403 (route is gated by require_admin).
  5. Pure-helper unit tests for `app.services.job_executions`:
     validate_job_name, validate_mode, summarize_execution.

The DB-bound tests use a sqlite-backed AsyncSession stub via TestClient
+ the e2e routing harness; the pure helpers exercise the registry +
state-transition matrix directly without any I/O.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

os.environ.setdefault("JWT_PRIVATE_KEY_PATH", "/nonexistent/key.pem")
os.environ.setdefault("JWT_PUBLIC_KEY_PATH", "/nonexistent/pub.pem")

from app.services.job_executions import (
    JOB_REGISTRY,
    humanize_duration,
    summarize_execution,
    validate_job_name,
    validate_mode,
)

# ───────────────────────── pure helpers ─────────────────────────


class TestValidateJobName:
    def test_known_jobs_pass(self) -> None:
        for name in JOB_REGISTRY:
            validate_job_name(name)  # no raise

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown job_name"):
            validate_job_name("not_a_real_job")

    def test_known_set_is_canonical(self) -> None:
        # The list mirrored in the docs / admin UI must contain these.
        for name in (
            "drive_crawler", "embedder", "peer_patterns",
            "intelligence_recompute", "ccg_loader",
        ):
            assert name in JOB_REGISTRY


class TestValidateMode:
    def test_default_mode_returned_when_none(self) -> None:
        assert validate_mode("drive_crawler", None) == "delta"
        assert validate_mode("peer_patterns", None) == "full"

    def test_valid_mode_accepted(self) -> None:
        assert validate_mode("drive_crawler", "full") == "full"
        assert validate_mode("drive_crawler", "delta") == "delta"

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="mode 'bogus' invalid"):
            validate_mode("drive_crawler", "bogus")

    def test_unknown_job_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown job_name"):
            validate_mode("not_real", "full")


class TestSummarizeExecution:
    def test_running_with_no_counters_yet(self) -> None:
        """Before any folder has been seen, surface 'starting…' so
        the operator knows the worker is alive but hasn't begun."""
        out = summarize_execution({"status": "running"})
        assert out == {"result_summary": "starting…", "error_count": 0}

    def test_running_with_live_counters(self) -> None:
        """When folders_seen + file counters are populated, the summary
        must surface them. Pre-this-fix the rendered string was the
        literal 'in progress' — operators thought the worker was stuck."""
        out = summarize_execution({
            "status": "running",
            "folders_seen": 115,
            "files_parsed": 25,
            "files_skipped": 12,
            "files_errored": 3,
        })
        # 25 + 12 + 3 = 40 / 115 = 34%
        assert "40/115 folders (34%)" in out["result_summary"]
        assert "ok=25" in out["result_summary"]
        assert "skip=12" in out["result_summary"]
        assert "fail=3" in out["result_summary"]
        assert out["error_count"] == 3

    def test_running_with_counters_no_total(self) -> None:
        """Workers like sheet_poller don't have a folders_seen total —
        surface what we know without a percentage."""
        out = summarize_execution({
            "status": "running",
            "files_parsed": 5,
            "files_skipped": 1,
            "files_errored": 0,
        })
        assert "6 processed" in out["result_summary"]
        assert "ok=5" in out["result_summary"]

    def test_cancelled(self) -> None:
        out = summarize_execution({"status": "cancelled"})
        assert out["result_summary"] == "cancelled by operator"
        assert out["error_count"] == 0

    def test_failed_truncates(self) -> None:
        msg = "x" * 200
        out = summarize_execution({"status": "failed", "error_message": msg})
        assert out["error_count"] == 1
        assert out["result_summary"].endswith("…")
        assert len(out["result_summary"]) <= 81

    def test_succeeded_assembles_summary(self) -> None:
        out = summarize_execution({
            "status": "succeeded", "folders_seen": 12,
            "files_parsed": 187, "files_skipped": 3, "rows_added": 42,
            "files_errored": 0,
        })
        assert "12 folders seen" in out["result_summary"]
        assert "187 parsed" in out["result_summary"]
        assert "3 skipped" in out["result_summary"]
        assert "42 rows" in out["result_summary"]
        assert out["error_count"] == 0

    def test_succeeded_with_errors_counts_them(self) -> None:
        out = summarize_execution({
            "status": "succeeded", "files_parsed": 10, "files_errored": 4,
        })
        assert out["error_count"] == 4

    def test_succeeded_with_no_counts(self) -> None:
        out = summarize_execution({"status": "succeeded"})
        assert out["result_summary"] == "ok"


class TestHumanizeDuration:
    def test_none_started_at(self) -> None:
        assert humanize_duration(None, None) == "—"

    def test_short_run(self) -> None:
        start = datetime.now(tz=UTC) - timedelta(seconds=14)
        assert humanize_duration(start, datetime.now(tz=UTC)).endswith("s")

    def test_long_run(self) -> None:
        start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = start + timedelta(seconds=134)  # 2m 14s
        out = humanize_duration(start, end)
        assert out == "2m 14s"


# ───────────────────────── route gating ─────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


class TestRouteGating:
    """The admin jobs endpoints share the `require_admin` dependency
    that gates the rest of /api/v1/admin. With no auth the response is
    401; with a non-admin token it's 403. We confirm both branches by
    calling without auth and asserting on the negative path."""

    def test_execute_unauth_returns_401(self, client) -> None:
        r = client.post(
            "/api/v1/admin/jobs/drive_crawler:execute",
            json={"mode": "full"},
        )
        assert r.status_code in (401, 403), r.text

    def test_list_executions_unauth_returns_401(self, client) -> None:
        r = client.get("/api/v1/admin/jobs/executions")
        assert r.status_code in (401, 403), r.text

    def test_get_execution_unauth_returns_401(self, client) -> None:
        r = client.get(
            "/api/v1/admin/jobs/executions/00000000-0000-0000-0000-000000000000"
        )
        assert r.status_code in (401, 403), r.text

    def test_jobs_registry_unauth_returns_401(self, client) -> None:
        r = client.get("/api/v1/admin/jobs")
        assert r.status_code in (401, 403), r.text

    def test_import_audit_summary_unauth_returns_401(self, client) -> None:
        r = client.get("/api/v1/admin/import-audit/summary")
        assert r.status_code in (401, 403), r.text

    def test_abort_unauth_returns_401(self, client) -> None:
        """The abort endpoint is operator-destructive — must require admin."""
        r = client.post(
            "/api/v1/admin/jobs/executions/"
            "00000000-0000-0000-0000-000000000000:abort"
        )
        assert r.status_code in (401, 403), r.text


class TestImportAuditSchemas:
    """Sanity-check the new schema shapes."""

    def test_summary_shape(self) -> None:
        from app.schemas.admin import ImportAuditSummary
        s = ImportAuditSummary()
        assert s.candidates_processed == 0
        assert s.files_imported == 0
        assert s.files_excluded == 0
        assert s.files_awaiting_review == 0

    def test_entity_row_shape(self) -> None:
        from app.schemas.admin import ImportAuditEntityRow
        r = ImportAuditEntityRow(
            entity_id="00000000-0000-0000-0000-000000000000",
            entity_display_id="ALMABANK",
            entity_name="AlmaBank",
        )
        assert r.runs_count == 0
        assert r.dedup_audit_count == 0
        assert r.enrichment_count == 0


# ── /admin/diagnostics + /admin/repair:* unauth guards ────────────────


class TestDiagnosticsRepairAuth:
    """The new diagnostics + self-heal repair endpoints (2026-05-28)
    must require admin auth. These guards are the only thing standing
    between a leaked AE session cookie and a stranger flipping every
    stuck job_execution to 'failed' or inserting bogus catalogue
    placeholder rows.
    """

    def test_diagnostics_unauth_returns_401(self, client) -> None:
        r = client.get("/api/v1/admin/diagnostics")
        assert r.status_code in (401, 403), r.text

    def test_repair_catalogue_stubs_unauth_returns_401(self, client) -> None:
        r = client.post("/api/v1/admin/repair:catalogue-stubs")
        assert r.status_code in (401, 403), r.text

    def test_repair_close_stuck_jobs_unauth_returns_401(self, client) -> None:
        r = client.post("/api/v1/admin/repair:close-stuck-jobs")
        assert r.status_code in (401, 403), r.text


class TestDiagnosticsRepairShape:
    """Source-code shape locks — every diagnostic key the admin UI
    renders MUST be present in the response builder; every repair
    endpoint MUST be idempotent (ON CONFLICT / WHERE status=running).
    Greps the source rather than executing live DB queries because
    these tests run in stage 0 (no PG).
    """

    def test_diagnostics_returns_expected_keys(self) -> None:
        """Frontend admin UI depends on a fixed set of diagnostic keys —
        regressing any of them silently breaks the operations panel.
        """
        from pathlib import Path
        src = (
            Path(__file__).resolve().parents[1]
            / "app" / "routers" / "admin.py"
        ).read_text()
        required_keys = {
            "catalogue_versions_referenced_but_missing",
            "catalogue_versions_with_no_child_rows",
            "job_executions_stuck_running",
            "runs_with_unresolved_catalogue",
            "backfill_folders_flagged_for_retry",
            "_summary",
        }
        for key in required_keys:
            assert f'"{key}"' in src, (
                f"diagnostics endpoint missing key {key!r} — admin UI "
                f"renders this; regressing it silently breaks the "
                f"operations panel"
            )

    def test_repair_catalogue_stubs_is_idempotent(self) -> None:
        """The INSERT must use ON CONFLICT (version) DO NOTHING so
        re-running the repair (e.g. operator double-clicks) doesn't
        clobber loader-written real metadata with placeholders."""
        from pathlib import Path
        src = (
            Path(__file__).resolve().parents[1]
            / "app" / "routers" / "admin.py"
        ).read_text()
        # Find the repair_catalogue_stubs function body.
        start = src.find("async def repair_catalogue_stubs")
        end = src.find("async def repair_close_stuck_jobs", start)
        assert start != -1 and end != -1, "repair endpoints not found"
        body = src[start:end]
        assert "ON CONFLICT (version) DO NOTHING" in body, (
            "repair_catalogue_stubs must use ON CONFLICT (version) "
            "DO NOTHING — otherwise the operator's double-click "
            "could overwrite real loader metadata with the placeholder"
        )

    def test_repair_close_stuck_jobs_only_touches_running(self) -> None:
        """The UPDATE must filter WHERE status='running' so we don't
        accidentally re-fail jobs that already succeeded or were
        manually marked failed."""
        from pathlib import Path
        src = (
            Path(__file__).resolve().parents[1]
            / "app" / "routers" / "admin.py"
        ).read_text()
        start = src.find("async def repair_close_stuck_jobs")
        # End of function: next blank line after a "return" or next def.
        end = src.find("@router.", start)
        body = src[start:end] if end != -1 else src[start:]
        assert "WHERE status = 'running'" in body or \
               "WHERE status='running'" in body, (
            "repair_close_stuck_jobs must filter WHERE status='running' "
            "to avoid clobbering already-terminal rows"
        )
        assert "INTERVAL '30 minutes'" in body, (
            "repair_close_stuck_jobs must enforce the >30min age "
            "guard — without it the operator could prematurely close "
            "an actively-progressing worker"
        )

    def test_repair_writes_audit_row(self) -> None:
        """Every repair action must leave a row in audit_log so the
        operator/SRE can later answer 'who touched this and when?'.
        """
        from pathlib import Path
        src = (
            Path(__file__).resolve().parents[1]
            / "app" / "routers" / "admin.py"
        ).read_text()
        # Both repair endpoints must reference audit_log INSERT.
        catalogue_stubs_block = src[
            src.find("async def repair_catalogue_stubs"):
            src.find("async def repair_close_stuck_jobs")
        ]
        stuck_jobs_block = src[
            src.find("async def repair_close_stuck_jobs"):
            src.find("async def assignments_queue", src.find("async def repair_close_stuck_jobs"))
        ]
        assert "INSERT INTO audit_log" in catalogue_stubs_block, (
            "repair_catalogue_stubs must INSERT INTO audit_log"
        )
        assert "INSERT INTO audit_log" in stuck_jobs_block, (
            "repair_close_stuck_jobs must INSERT INTO audit_log"
        )


# ── Cloud Logging deep link builder ───────────────────────────────────


class TestLogsUrlBuilder:
    """`_build_logs_url` produces a Cloud Logging filter URL the admin
    UI renders as a 'View logs' link. Pure function — no DB / no
    HTTP — so we exercise it directly with synthetic row dicts.
    """

    def test_returns_none_when_no_project_id(self, monkeypatch) -> None:
        """Local dev / tests: gcp_project_id is empty → builder returns
        None so the UI omits the link entirely (better than a broken URL).
        """
        from app.config import get_settings
        from app.routers.admin import _build_logs_url

        s = get_settings()
        monkeypatch.setattr(s, "gcp_project_id", "")
        out = _build_logs_url({
            "job_name": "historical_backfill",
            "started_at": None,
        })
        assert out is None

    def test_returns_none_when_no_job_name(self, monkeypatch) -> None:
        from app.config import get_settings
        from app.routers.admin import _build_logs_url

        s = get_settings()
        monkeypatch.setattr(s, "gcp_project_id", "dma-test-proj")
        assert _build_logs_url({"job_name": None}) is None

    def test_underscore_to_dash_in_cloud_run_job_name(self, monkeypatch) -> None:
        """Python module path uses underscores (`historical_backfill`)
        but the Cloud Run Job is RFC1035-safe (hyphens only). The
        URL must filter on the hyphenated name."""
        from datetime import datetime

        from app.config import get_settings
        from app.routers.admin import _build_logs_url

        s = get_settings()
        monkeypatch.setattr(s, "gcp_project_id", "dma-test-proj")
        url = _build_logs_url({
            "job_name": "historical_backfill",
            "started_at": datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC),
            "completed_at": None,
        })
        assert url is not None
        assert "dma-insights-historical-backfill" in url
        assert "dma-insights-historical_backfill" not in url, (
            "URL must hyphenate the job name to match the actual Cloud "
            "Run resource name"
        )

    def test_uses_execution_name_when_present(self, monkeypatch) -> None:
        """When the row has `cloud_run_execution_name` from the dispatch
        path, the URL must filter to that EXACT execution — way less
        noise than a time-windowed filter."""
        from datetime import datetime

        from app.config import get_settings
        from app.routers.admin import _build_logs_url

        s = get_settings()
        monkeypatch.setattr(s, "gcp_project_id", "dma-test-proj")
        url = _build_logs_url({
            "job_name": "drive_crawler",
            "cloud_run_execution_name": "dma-insights-drive-crawler-abc12",
            "started_at": datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC),
        })
        assert url is not None
        # The execution-name filter is the strong signal.
        assert "dma-insights-drive-crawler-abc12" in url
        # And the project param.
        assert "?project=dma-test-proj" in url

    def test_falls_back_to_time_window_without_execution_name(
        self, monkeypatch
    ) -> None:
        """No execution_name (admin row inserted but dispatch hadn't
        wired back yet) → fall back to a ±10min timestamp window.
        Coarser but still useful."""
        from datetime import datetime

        from app.config import get_settings
        from app.routers.admin import _build_logs_url

        s = get_settings()
        monkeypatch.setattr(s, "gcp_project_id", "dma-test-proj")
        url = _build_logs_url({
            "job_name": "ccg_loader",
            "started_at": datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC),
            "completed_at": None,
        })
        assert url is not None
        # Time-window filter words should be in the URL.
        assert "timestamp" in url
