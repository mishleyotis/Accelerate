"""022 — backfill_quarantine: per-folder backfill outcomes for retry.

Revision ID: 022_backfill_quarantine
Revises: 021_runs_drive_backfill

Problem this solves
====================
The 2026-05-28 historical backfill processed 115 Drive folders. The
final state was: 5/115 ingested, ~50/115 skipped (no DMA report DOCX
files / malformed packages), ~60/115 failed (FK violations and other
real errors). The operator wants to retry ONLY the failures after
fixing the underlying issues — without re-processing the 5 that
already succeeded or the 50 that are legitimately empty.

Pre-migration: the only outcome signal was stdout log lines, and
re-running the backfill re-processed every folder regardless.

This migration adds `backfill_quarantine` — one row per (run_id,
drive_folder_id) where `run_id` is the `job_executions.id` of the
backfill run and `drive_folder_id` is the Drive folder ID processed.
Each row captures:

  - outcome: 'ok' / 'skipped_no_report' / 'skipped_already_ingested' /
             'failed_parse' / 'failed_persist' / 'failed_other'
  - reason: short string (e.g. "no DMA package detected")
  - folder_name: human-readable for the admin UI
  - error_message: full error if outcome started with 'failed_'

The `--retry-failed-only` flag on `historical_backfill.py` reads the
MOST RECENT row per (drive_folder_id) and only re-processes folders
whose latest outcome was a 'failed_*' or 'skipped_no_report' state.

State branches (locked by tests):
  ok                         → never retried by --retry-failed-only
  skipped_already_ingested   → never retried (idempotent skip)
  skipped_no_report          → RETRIED (operator may have fixed the folder)
  failed_*                   → RETRIED

Re-running is idempotent: every backfill writes new rows, and the
"latest outcome per folder" rule keeps the row count proportional to
distinct folders × runs (not pathological growth).

Index: (drive_folder_id, processed_at DESC) for the "latest outcome
per folder" SELECT.
"""

import sqlalchemy as sa
from alembic import op

revision = "022_backfill_quarantine"
down_revision = "021_runs_drive_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS backfill_quarantine (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id              UUID NOT NULL,
            drive_folder_id     VARCHAR(64) NOT NULL,
            folder_name         TEXT NOT NULL,
            outcome             VARCHAR(32) NOT NULL,
            reason              TEXT,
            error_message       TEXT,
            ingested_run_id     UUID,
            processed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT ck_backfill_quarantine_outcome
                CHECK (outcome IN (
                    'ok',
                    'skipped_no_report',
                    'skipped_already_ingested',
                    'failed_parse',
                    'failed_persist',
                    'failed_other'
                ))
        );

        -- "Latest outcome per folder" — the dominant query for
        -- --retry-failed-only and the admin UI quarantine list.
        CREATE INDEX IF NOT EXISTS ix_backfill_quarantine_folder_recency
            ON backfill_quarantine (drive_folder_id, processed_at DESC);

        -- Per-run rollup for the admin UI's job_executions drill-in.
        CREATE INDEX IF NOT EXISTS ix_backfill_quarantine_run_id
            ON backfill_quarantine (run_id);

        -- We DO NOT add an FK from backfill_quarantine.run_id → job_executions.id.
        -- The historical_backfill worker writes quarantine rows before
        -- the job_executions row is finalised, and may also be invoked
        -- via gcloud CLI where no job_executions row exists. The
        -- quarantine table needs to stand alone in those scenarios.
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_backfill_quarantine_run_id;
        DROP INDEX IF EXISTS ix_backfill_quarantine_folder_recency;
        DROP TABLE IF EXISTS backfill_quarantine;
    """)
