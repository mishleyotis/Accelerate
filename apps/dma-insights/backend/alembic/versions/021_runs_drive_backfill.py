"""021 — expand runs.data_source CHECK constraint for DRIVE_BACKFILL.

Revision ID: 021_runs_drive_backfill
Revises: 020_job_executions

NOTE on revision-ID length: alembic's `alembic_version.version_num`
column is VARCHAR(32) by default. Revision IDs longer than 32 chars
are silently truncated by alembic at write time → `StringDataRight-
Truncation` failure → migration rolls back. The previous ID
`021_runs_data_source_drive_backfill` (35 chars) tripped this.
Keep every revision ≤ 32 chars — guarded by
`tests/test_migration_id_lengths.py`. The `alembic/env.py` pre-hook
also widens the column to VARCHAR(128) on every run as defence in depth.

The original constraint (migration 003) allowed only:
  DRIVE_PARSE | PROJECT_API | MANUAL_BACKFILL

`historical_backfill.py` correctly emits `DRIVE_BACKFILL` to distinguish
script-driven historical fills from the live `drive_crawler` worker
(`DRIVE_PARSE`) and ad-hoc operator uploads (`MANUAL_BACKFILL`).

The mismatch caused EVERY backfill INSERT to fail with:

  IntegrityError: new row for relation "runs" violates check constraint
  "runs_data_source_chk"

…which silently emptied the entire admin UI (no runs → no derived data →
no UI rows). User report on 2026-05-24 traced this to the constraint gap.

State-branch contract:
  drop_existing_constraint  → safe; ON CONFLICT-friendly via NOT VALID
  recreate_with_full_enum    → permanent fix; backfill commits now succeed
  no_existing_violators      → backfill couldn't INSERT before this fix,
                                so there are no in-table rows needing
                                back-cleanup (any pre-existing 'DRIVE_BACKFILL'
                                values would have been blocked at insert)
"""
from __future__ import annotations

from alembic import op

revision = "021_runs_drive_backfill"
down_revision = "020_job_executions"
branch_labels = None
depends_on = None


# Full enum of trigger sources writers may pass to runs.data_source.
# Add new values here when a new ingest path is introduced.
ALLOWED_DATA_SOURCES = (
    "DRIVE_PARSE",        # live drive_crawler worker (6-hour cadence)
    "DRIVE_BACKFILL",     # one-shot historical_backfill.py
    "PROJECT_API",        # Claude project posts to /ingest/assessment
    "MANUAL_BACKFILL",    # operator-driven /ingest/package
    "BOT_REQUEST",        # n8n bot bidirectional flow
)


def upgrade() -> None:
    # IF EXISTS so the migration is idempotent — useful if some prior
    # repair run already dropped the constraint manually.
    op.execute(
        "ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_data_source_chk"
    )
    values_csv = ", ".join(f"'{v}'" for v in ALLOWED_DATA_SOURCES)
    op.execute(
        f"ALTER TABLE runs ADD CONSTRAINT runs_data_source_chk "
        f"CHECK (data_source IN ({values_csv}))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_data_source_chk"
    )
    op.execute(
        "ALTER TABLE runs ADD CONSTRAINT runs_data_source_chk "
        "CHECK (data_source IN ('DRIVE_PARSE','PROJECT_API','MANUAL_BACKFILL'))"
    )
