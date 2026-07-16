"""Tests for `app.services.startup_diagnostic.run_startup_diagnostic`.

Non-blocking contract — every exception path MUST be caught + logged
so the deploy can never be wedged by a diagnostic bug. These tests
exercise each branch (db-unreachable, query-failure, healthy, issues
detected) and assert the right log call shape for each.

Live-DB tests are gated by SEED_CI_PG_URL; stage-0 runs the pure-logic
branches with mocks.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

LIVE_DB_URL = os.environ.get("SEED_CI_PG_URL", "")
HAS_LIVE_DB = bool(LIVE_DB_URL)


@pytest.mark.asyncio
async def test_diagnostic_handles_engine_unavailable_gracefully(monkeypatch):
    """When `app.database.get_engine` raises, the diagnostic must
    log a warning and return — NEVER propagate. The deploy depends
    on it not raising."""
    from app.services import startup_diagnostic as sd

    def _raises(*args, **kwargs):
        raise RuntimeError("engine offline")

    monkeypatch.setattr("app.database.get_engine", _raises)

    captured: list[tuple[str, dict]] = []
    log = MagicMock()
    log.warning = lambda event, **kwargs: captured.append((event, kwargs))
    log.info = lambda event, **kwargs: captured.append((event, kwargs))

    # Must complete without raising.
    await sd.run_startup_diagnostic(log)

    # And we should see the engine_unavailable warning.
    events = [e for e, _ in captured]
    assert "startup_diagnostic.engine_unavailable" in events, (
        f"expected engine_unavailable warning; got events: {events}"
    )


@pytest.mark.asyncio
async def test_diagnostic_handles_connect_failure_gracefully(monkeypatch):
    """When the connection itself fails inside the context manager,
    the diagnostic must log + return without propagating."""
    from app.services import startup_diagnostic as sd

    class FakeEngine:
        def connect(self):
            raise RuntimeError("connection refused")

    monkeypatch.setattr("app.database.get_engine", lambda: FakeEngine())

    captured: list[tuple[str, dict]] = []
    log = MagicMock()
    log.warning = lambda event, **kwargs: captured.append((event, kwargs))
    log.info = lambda event, **kwargs: captured.append((event, kwargs))

    await sd.run_startup_diagnostic(log)

    events = [e for e, _ in captured]
    assert "startup_diagnostic.connect_failed" in events, (
        f"expected connect_failed warning; got events: {events}"
    )


@pytest.mark.asyncio
async def test_diagnostic_queries_cover_all_categories():
    """The 5 diagnostic categories must each be present in the SQL
    query list — frontend admin UI + DEPLOYMENT.md §44 rely on the
    exact same set as the `/admin/diagnostics` HTTP endpoint."""
    from app.services.startup_diagnostic import _DIAGNOSTIC_QUERIES

    keys = {q[0] for q in _DIAGNOSTIC_QUERIES}
    expected = {
        "catalogue_versions_referenced_but_missing",
        "catalogue_versions_with_no_child_rows",
        "job_executions_stuck_running",
        "runs_with_unresolved_catalogue",
        "backfill_folders_flagged_for_retry",
    }
    assert keys == expected, (
        f"diagnostic queries cover {keys}; expected {expected}. "
        f"The set must match `/admin/diagnostics` exactly so the "
        f"startup log emits the same shape as the HTTP endpoint."
    )


def test_scalar_repr_handles_uuid_datetime():
    """`_scalar_repr` is what makes the structured log payload
    JSON-friendly. Must coerce UUIDs + datetimes to strings."""
    from datetime import datetime
    from uuid import uuid4

    from app.services.startup_diagnostic import _scalar_repr

    u = uuid4()
    d = datetime(2026, 5, 28, 12, 0, 0)
    assert _scalar_repr(u) == str(u)
    assert _scalar_repr(d) == d.isoformat()
    assert _scalar_repr("plain") == "plain"
    assert _scalar_repr(42) == 42
    assert _scalar_repr(None) is None


# ── Live-PG branches ──────────────────────────────────────────────────


@pytest.mark.skipif(
    not HAS_LIVE_DB,
    reason="SEED_CI_PG_URL not set — live-DB diagnostic tests skipped",
)
class TestLiveDiagnostic:
    """Exercises the diagnostic against a real Postgres in 3 states:
    healthy, single-category-issue, all-categories-issue.
    """

    @pytest.mark.asyncio
    async def test_healthy_state_logs_info(self, monkeypatch):
        """Clean DB → log.info with overall_healthy=True, no warnings."""
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.services import startup_diagnostic as sd

        monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
        monkeypatch.setenv("DATABASE_URL", LIVE_DB_URL)

        engine = create_async_engine(LIVE_DB_URL)
        try:
            # Wipe everything the diagnostic checks so all 4
            # categories return empty.
            async with engine.begin() as conn:
                await conn.execute(text("TRUNCATE job_executions"))
                await conn.execute(text("TRUNCATE runs CASCADE"))
                # Insert a non-band-aid version (so the with_no_child_rows
                # check returns 0) — actually no, we want the category to
                # be CLEAN, which means ccg_catalog_versions must have
                # NO rows at all OR every row has children. Easiest:
                # leave it empty.
                await conn.execute(text(
                    "TRUNCATE ccg_catalog_versions CASCADE"
                ))

            # Force app.database.get_engine to return OUR engine.
            from app import database as db_mod
            monkeypatch.setattr(db_mod, "get_engine", lambda: engine)

            captured: list[tuple[str, dict]] = []
            log = MagicMock()
            log.warning = lambda e, **kw: captured.append(("warning", e, kw))
            log.info = lambda e, **kw: captured.append(("info", e, kw))

            await sd.run_startup_diagnostic(log)

            # Should have ONE info event with overall_healthy=True,
            # NO warning events.
            info_events = [
                (e, kw) for level, e, kw in captured if level == "info"
            ]
            warning_events = [
                (e, kw) for level, e, kw in captured if level == "warning"
            ]
            healthy = [
                kw for e, kw in info_events
                if e == "startup_diagnostic.healthy"
            ]
            assert healthy, (
                f"expected startup_diagnostic.healthy log.info; "
                f"got info={info_events}, warning={warning_events}"
            )
            assert healthy[0]["overall_healthy"] is True
            assert healthy[0]["catalogue_versions_with_no_child_rows"] == 0
            assert healthy[0]["job_executions_stuck_running"] == 0
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_issues_detected_logs_warning_per_category(self, monkeypatch):
        """Seed 2 categories' worth of issues → log.warning fires for
        each affected category, then a summary warning with the total."""
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.services import startup_diagnostic as sd

        monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
        monkeypatch.setenv("DATABASE_URL", LIVE_DB_URL)

        engine = create_async_engine(LIVE_DB_URL)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("TRUNCATE job_executions"))
                await conn.execute(text("TRUNCATE runs CASCADE"))
                await conn.execute(text(
                    "TRUNCATE ccg_catalog_versions CASCADE"
                ))

                # Seed: catalogue parent with no children → issue 1
                await conn.execute(text("""
                    INSERT INTO ccg_catalog_versions
                      (version, released_at, source_sha256s,
                       loader_run_id, frozen_at, notes)
                    VALUES ('v7.0', NOW(), '{}'::jsonb,
                            gen_random_uuid(), NOW(),
                            'startup-diagnostic test band-aid')
                """))

                # Seed: stuck running job → issue 2
                await conn.execute(text("""
                    INSERT INTO job_executions
                      (job_name, mode, trigger_source, status, started_at)
                    VALUES ('historical_backfill', 'full', 'cli',
                            'running', NOW() - INTERVAL '1 hour')
                """))

            from app import database as db_mod
            monkeypatch.setattr(db_mod, "get_engine", lambda: engine)

            captured: list[tuple[str, dict]] = []
            log = MagicMock()
            log.warning = lambda e, **kw: captured.append(("warning", e, kw))
            log.info = lambda e, **kw: captured.append(("info", e, kw))

            await sd.run_startup_diagnostic(log)

            warning_events = [
                (e, kw) for level, e, kw in captured if level == "warning"
            ]
            # Per-category warning(s).
            issue_warnings = [
                kw for e, kw in warning_events
                if e == "startup_diagnostic.issue_detected"
            ]
            categories_hit = {kw["category"] for kw in issue_warnings}
            assert "catalogue_versions_with_no_child_rows" in categories_hit
            assert "job_executions_stuck_running" in categories_hit

            # And a summary at the end.
            summary = [
                kw for e, kw in warning_events
                if e == "startup_diagnostic.summary"
            ]
            assert summary, (
                f"expected startup_diagnostic.summary warning; "
                f"got warnings: {warning_events}"
            )
            assert summary[0]["overall_healthy"] is False
            assert summary[0]["total_issues"] >= 2
        finally:
            await engine.dispose()
