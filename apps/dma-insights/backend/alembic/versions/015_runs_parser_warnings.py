"""015 — runs.parser_warnings JSONB + entity hard-delete guard

Two changes:

1. Add `runs.parser_warnings` JSONB to persist ingest-time warnings
   (e.g., subcap IDs from an old DMA that have no alias bridge to the
   current v7.0 catalogue). Without this, AEs can't see which subcaps
   were dropped silently — a real auditability gap for old-DMA ingest.

2. Add a CHECK constraint preventing physical deletion of entities with
   `status='ACTIVE'`. The cascade chain on `runs.entity_id → CASCADE`
   means a stray `DELETE FROM entities` would nuke ALL evidence /
   insights / recs / scores in one shot — this guard makes that
   accident structurally impossible. Hard deletes still work for
   `status='ARCHIVED'` (intentional admin action).

Revision ID: 015_runs_parser_warnings
Revises: 014_build_qa_gates
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "015_runs_parser_warnings"
down_revision = "014_build_qa_gates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. parser_warnings JSONB on runs.
    op.add_column(
        "runs",
        sa.Column(
            "parser_warnings",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # 2. Hard-delete guard: prevent physical deletion of ACTIVE entities.
    # Postgres CHECK constraints can't reference NEW row state during
    # DELETE, so we use a trigger function instead.
    #
    # We avoid `RAISE EXCEPTION 'msg %% % %%', a, b` (the % placeholder
    # form) because the source-`%%` → psycopg-`%` → SQLAlchemy-text
    # → server pipeline can double-escape in some configurations,
    # producing `%%%%` in the SQL Postgres receives. PL/pgSQL then
    # interprets `%%%%` as two literal `%%` (no placeholders), the
    # arg count mismatches, and the function fails to compile with
    # `too many parameters specified for RAISE`. Using string
    # concatenation in the USING clause sidesteps the issue entirely.
    #
    # Drop first so re-running this migration after a failed partial
    # apply doesn't error on "already exists".
    op.execute("DROP TRIGGER IF EXISTS trg_protect_active_entity_delete ON entities;")
    op.execute("DROP FUNCTION IF EXISTS protect_active_entity_delete();")
    op.execute(
        """
        CREATE FUNCTION protect_active_entity_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.status = 'ACTIVE' THEN
                RAISE EXCEPTION
                    USING MESSAGE = 'cannot DELETE entity ' || COALESCE(OLD.name, '?')
                                    || ' (id=' || OLD.id::text
                                    || ') while status=ACTIVE — archive it first '
                                    || '(UPDATE entities SET status=''ARCHIVED'' WHERE id=' || OLD.id::text || ')',
                          ERRCODE = 'restrict_violation';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_protect_active_entity_delete
        BEFORE DELETE ON entities
        FOR EACH ROW EXECUTE FUNCTION protect_active_entity_delete();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_protect_active_entity_delete ON entities;")
    op.execute("DROP FUNCTION IF EXISTS protect_active_entity_delete();")
    op.drop_column("runs", "parser_warnings")
