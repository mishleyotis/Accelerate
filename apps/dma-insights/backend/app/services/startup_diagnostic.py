"""Backend startup diagnostic — surfaces stale catalogue / stuck jobs /
unresolved-score state to Cloud Logging on every deploy rollover.

Mirrors the SQL behind `GET /api/v1/admin/diagnostics`. The endpoint
returns JSON for the admin UI; this module emits structured log lines
that Cloud Logging picks up and surfaces in the deploy observability
view. Together they give the operator two non-blocking surfaces for
the same data — UI polling for live state, structured logs for deploy
forensics.

Hard non-blocking contract: this MUST NEVER raise. If the DB is
unreachable at startup the deploy must still complete so the operator
can hit `/healthz` and roll back. Every exception is caught + logged
at WARNING and execution continues.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

_DIAGNOSTIC_QUERIES: tuple[tuple[str, str, str], ...] = (
    (
        "catalogue_versions_referenced_but_missing",
        "runs reference a catalogue version with no parent row — "
        "FK violations will fire on next backfill",
        """
        SELECT DISTINCT r.ccg_catalog_version AS version,
               COUNT(*) OVER (PARTITION BY r.ccg_catalog_version) AS run_count
          FROM runs r
         WHERE r.ccg_catalog_version IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM ccg_catalog_versions cv
                WHERE cv.version = r.ccg_catalog_version
           )
        """,
    ),
    (
        "catalogue_versions_with_no_child_rows",
        "ccg_catalog_versions rows exist but have no ccg_subcaps children — "
        "loader has not run for real; scored packages will emit "
        "catalogue_empty_for_version warnings",
        """
        SELECT cv.version
          FROM ccg_catalog_versions cv
         WHERE NOT EXISTS (
               SELECT 1 FROM ccg_subcaps s WHERE s.version = cv.version
         )
        """,
    ),
    (
        "job_executions_stuck_running",
        "job_executions rows have been running >30min — worker likely "
        "died mid-run; admin UI shows stale 'in progress' state",
        """
        SELECT id, job_name,
               EXTRACT(EPOCH FROM (NOW() - started_at))::int AS age_sec
          FROM job_executions
         WHERE status = 'running'
           AND started_at < NOW() - INTERVAL '30 minutes'
         LIMIT 20
        """,
    ),
    (
        "runs_with_unresolved_catalogue",
        "persisted runs have parser_warnings indicating ALL parsed "
        "subcap_scores failed catalogue resolution — UI shows blank "
        "scores for these entities until ccg_loader runs",
        """
        SELECT r.id, r.request_id, r.ccg_catalog_version
          FROM runs r
         WHERE r.ccg_catalog_version IS NOT NULL
           AND r.parser_warnings::text LIKE '%catalogue_empty_for_version%'
         LIMIT 20
        """,
    ),
    (
        "backfill_folders_flagged_for_retry",
        "drive folders whose latest backfill outcome was failed_* or "
        "skipped_no_report — re-runnable via `--retry-failed-only` "
        "(operator clicks 'Retry failed folders' in Operations panel)",
        # Defensive: backfill_quarantine may not exist yet on a freshly
        # migrated DB (added by migration 022). The per-query
        # SQLAlchemyError handler in run_startup_diagnostic swallows
        # `relation does not exist` so this is safe — the category is
        # simply absent from the structured log until migration 022 is
        # applied.
        """
        SELECT * FROM (
            SELECT DISTINCT ON (drive_folder_id)
                   drive_folder_id, folder_name, outcome
              FROM backfill_quarantine
          ORDER BY drive_folder_id, processed_at DESC
        ) latest
         WHERE outcome IN (
            'failed_parse', 'failed_persist',
            'failed_other', 'skipped_no_report'
         )
         LIMIT 50
        """,
    ),
)


async def run_startup_diagnostic(log: Any) -> None:
    """Run each diagnostic SQL and emit structured log lines.

    Args:
      log: a structlog BoundLogger from the caller — we don't import
        the global one here to keep the contract pure-async-friendly.

    Branches (matches the contract in lifespan):
      db_unreachable     → log.warning + return (deploy continues)
      no_issues_detected → log.info with overall_healthy=True
      issues_detected    → log.warning per category, then a summary
                           log.warning with total_issues count
    """
    try:
        # Lazy import — keeps the module importable in tests that
        # don't have a live DB (the diagnostic module file gets
        # parsed during `python -m pytest --collect-only` even when
        # no test exercises it).
        from app.database import get_engine
    except ImportError as e:
        log.warning("startup_diagnostic.import_failed", err=str(e))
        return

    try:
        engine = get_engine()
    except Exception as e:
        log.warning(
            "startup_diagnostic.engine_unavailable",
            err=str(e)[:200],
            err_type=type(e).__name__,
        )
        return

    total_issues = 0
    per_category: dict[str, int] = {}

    try:
        async with engine.connect() as conn:
            for key, human_msg, sql in _DIAGNOSTIC_QUERIES:
                try:
                    rows = (await conn.execute(text(sql))).mappings().all()
                except SQLAlchemyError as e:
                    # An individual query failing (e.g. table not
                    # migrated yet) must not stop the others. The DB
                    # could be in mid-migration state on the very
                    # first deploy of a new schema.
                    log.warning(
                        "startup_diagnostic.query_failed",
                        category=key,
                        err=str(e)[:200],
                        err_type=type(e).__name__,
                    )
                    continue
                count = len(rows)
                per_category[key] = count
                total_issues += count
                if count > 0:
                    # Log the FIRST 5 rows verbatim so the operator can
                    # see which specific entities/versions are affected
                    # without having to immediately go query the DB.
                    log.warning(
                        "startup_diagnostic.issue_detected",
                        category=key,
                        count=count,
                        human=human_msg,
                        sample_rows=[
                            {k: _scalar_repr(v) for k, v in r.items()}
                            for r in rows[:5]
                        ],
                    )
    except Exception as e:
        log.warning(
            "startup_diagnostic.connect_failed",
            err=str(e)[:200],
            err_type=type(e).__name__,
        )
        return

    if total_issues == 0:
        log.info(
            "startup_diagnostic.healthy",
            overall_healthy=True,
            **per_category,
        )
    else:
        log.warning(
            "startup_diagnostic.summary",
            overall_healthy=False,
            total_issues=total_issues,
            **per_category,
            remediation=(
                "Investigate each category via the admin UI / "
                "GET /api/v1/admin/diagnostics. Use "
                "POST /api/v1/admin/repair:catalogue-stubs to insert "
                "missing parent rows; use "
                "POST /api/v1/admin/repair:close-stuck-jobs to flip "
                "dead `running` rows to `failed`. See DEPLOYMENT.md §44 "
                "for the full operator runbook."
            ),
        )


def _scalar_repr(v: Any) -> Any:
    """Coerce a row value to a JSON-friendly representation for the
    structured log payload. UUIDs become strings, datetimes become
    ISO strings, ints/floats/strs pass through unchanged."""
    from datetime import date, datetime
    from uuid import UUID

    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v
