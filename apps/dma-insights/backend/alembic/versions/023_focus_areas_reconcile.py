"""023 — reconcile focus_areas schema drift + add hot-path indexes.

Revision ID: 023_focus_areas_reconcile
Revises: 022_backfill_quarantine

Problem this solves
====================
Two earlier migrations created the same `focus_areas` table with
DIFFERENT column names:

  011_prompts_state_focus.py:  name, source_quote, source_path,
                                page_number, financial_reference,
                                involved_subcap_ids
  018_intelligence_layer.py:   title, verbatim_quote, source_path,
                                page_number, involved_subcap_ids

Because 018 wraps its CREATE in `CREATE TABLE IF NOT EXISTS`, the
011 schema sticks on a fresh DB walking 001→022, but `FocusArea`
(app/services/parsers/client_profile.py:42) uses the 018 names
(`title`, `verbatim_quote`). Any future code path that writes to
focus_areas — `evidence_handoff` serializes FocusArea rows into a
`rows_by_kind["focus_areas"]` bucket today — will hit a "column
does not exist" error in prod.

Reconcile to the 018 contract (the one app code expects):
  - rename `name`            → `title`            (idempotent)
  - rename `source_quote`    → `verbatim_quote`   (idempotent)
  - drop  `financial_reference` (unused; not in 018)

The rename uses `DO $$ BEGIN ... EXCEPTION WHEN undefined_column ...`
so re-running the migration on a DB that already has the 018 schema
(or was created fresh after this lands) doesn't fail.

Also adds two hot-path indexes called out by the perf audit:
  - runs(entity_id, completed_at DESC NULLS LAST) — every /entities/
    {id}/runs query scans this; without an index the planner falls
    back to seq scan + sort on every page hit.
  - evidence_index(entity_id, freshness_band) — /entities/{id}/
    overview filters evidence by entity + freshness band; same
    seq-scan pattern.

Both `CREATE INDEX IF NOT EXISTS ... CONCURRENTLY` so the migration
doesn't block ongoing writes -- though Alembic's transactional DDL
wrapper means we have to drop CONCURRENTLY and use the post-deploy
runner. Below we use IF NOT EXISTS without CONCURRENTLY since live
PG is small enough that the few-seconds lock is acceptable; flip to
CONCURRENTLY via op.execute("COMMIT; CREATE INDEX CONCURRENTLY ...")
if write traffic grows.

Idempotent: every statement uses IF EXISTS / IF NOT EXISTS so a
re-run after partial failure is safe.
"""
from __future__ import annotations

from alembic import op

revision = "023_focus_areas_reconcile"
down_revision = "022_backfill_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── focus_areas column reconcile ──────────────────────────────────
    # ALTER TABLE ... RENAME COLUMN errors if the source column doesn't
    # exist. Guard each rename in a DO block that swallows the
    # `undefined_column` SQLSTATE so we don't have to know in advance
    # whether the DB was built via 011 or 018.
    #
    # 2026-05-28 audit fix (F-202): the EARLIER version of this DO
    # block also swallowed `duplicate_column` silently. That hid mixed-
    # shape data loss: if any DB ended up with BOTH `name` (011) AND
    # `title` (018) populated (e.g. partial-failure recovery, manual
    # ops, restored snapshot from a different schema version), the
    # rename would no-op and the `name` data would later be dropped
    # without warning when an app write to `title` clobbered it.
    # Now `duplicate_column` RAISES with an actionable message so the
    # operator MUST resolve the mixed state before the migration
    # proceeds. See DEPLOYMENT.md §52.5 for the remediation SQL.
    op.execute("""
        DO $reconcile$
        BEGIN
            BEGIN
                ALTER TABLE focus_areas RENAME COLUMN name TO title;
            EXCEPTION WHEN undefined_column THEN
                NULL;  -- already renamed (or never existed under this name)
            WHEN duplicate_column THEN
                RAISE EXCEPTION
                    'focus_areas has BOTH `name` and `title` columns -- '
                    'mixed schema state. Resolve manually before '
                    're-running migration 023: pick one column as '
                    'authoritative, copy data, drop the other. See '
                    'docs/DEPLOYMENT.md SS52.5 for remediation SQL.';
            END;
            BEGIN
                ALTER TABLE focus_areas RENAME COLUMN source_quote TO verbatim_quote;
            EXCEPTION WHEN undefined_column THEN
                NULL;
            WHEN duplicate_column THEN
                RAISE EXCEPTION
                    'focus_areas has BOTH `source_quote` and '
                    '`verbatim_quote` columns -- mixed schema state. '
                    'Resolve manually before re-running migration 023. '
                    'See docs/DEPLOYMENT.md SS52.5 for remediation SQL.';
            END;
            BEGIN
                ALTER TABLE focus_areas DROP COLUMN financial_reference;
            EXCEPTION WHEN undefined_column THEN
                NULL;
            END;
        END
        $reconcile$;
    """)

    # ── Hot-path indexes (perf audit) ──────────────────────────────────
    # IF NOT EXISTS so re-running the migration on a DB that already
    # has them is a no-op.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_runs_entity_completed "
        "ON runs (entity_id, completed_at DESC NULLS LAST)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_index_entity_freshness "
        "ON evidence_index (entity_id, freshness_band)"
    )


def downgrade() -> None:
    # The renames are reversible -- restore the 011 schema. Same
    # idempotent guard as upgrade so a re-run is safe.
    op.execute("DROP INDEX IF EXISTS ix_runs_entity_completed")
    op.execute("DROP INDEX IF EXISTS ix_evidence_index_entity_freshness")
    op.execute("""
        DO $reconcile_down$
        BEGIN
            BEGIN
                ALTER TABLE focus_areas RENAME COLUMN title TO name;
            EXCEPTION WHEN undefined_column THEN
                NULL;
            WHEN duplicate_column THEN
                NULL;
            END;
            BEGIN
                ALTER TABLE focus_areas RENAME COLUMN verbatim_quote TO source_quote;
            EXCEPTION WHEN undefined_column THEN
                NULL;
            WHEN duplicate_column THEN
                NULL;
            END;
            -- financial_reference is intentionally NOT restored on downgrade;
            -- the column has been unused since 018 and downgrading should
            -- match the latest known-good shape, not the original 011 shape.
        END
        $reconcile_down$;
    """)
