"""047 - timeline_events NLP event-pipeline fields (D5)

The 2026-06 context audit measured 1,097 timeline events with 88%
defaulted dates (one client: 26 events piled on a single fallback
date), 51% garbage titles, and polarity derived from `kind` instead
of the claim itself. The rebuilt NLP event pipeline (derive_context +
facts_extractor) emits per-event provenance this migration gives a
home to:

  - ``signal``          — polarity-classified event signal (e.g. POS/NEG/
    NEUTRAL), native to the claim, NOT inferred from kind.
  - ``date_precision``  — day | month | quarter | year | publish_fallback;
    the frontend jitters/clusters dots by precision so fallback-date
    pile-ups stop reading as real same-day bursts.
  - ``evidence_e_ids``  — multi-value evidence anchors (the legacy scalar
    ``e_id`` column stays for compatibility; the array supersedes it).
  - ``subcap_ids``      — capability links for cap-impact chips.

``body`` already exists (migration 006) so titlecraft's excerpt move
needs no schema change, and acquisitions richness rides these same
timeline rows (kind='acquisition') — no new table.

All NULL on legacy rows — `TimelineEventOut` defaults keep the
response shape stable until re-derivation fills them.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "047_timeline_nlp_fields"
down_revision = "046_insight_interconnections"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("signal", "VARCHAR(10)"),
    ("date_precision", "VARCHAR(20)"),
    ("evidence_e_ids", "TEXT[]"),
    ("subcap_ids", "TEXT[]"),
)


def upgrade() -> None:
    for col, coltype in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='timeline_events' AND column_name='{col}'
                ) THEN
                    ALTER TABLE timeline_events ADD COLUMN {col} {coltype};
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for col, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE timeline_events DROP COLUMN IF EXISTS {col}")
