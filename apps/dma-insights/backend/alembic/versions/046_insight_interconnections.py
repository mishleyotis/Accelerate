"""046 - insight_cards interconnection + classification fields (D2)

The 2026-06 insights audit measured 630 cards where `affects[]` /
`platforms[]` / `interconnections` / `theme` were absent entirely —
the InsightModal's cross-pillar chips, platform badges and "related"
tab had nothing to bind to. Producers are the rebuilt derivation
ladder in `derive_insights` + `deepen_narrative` (interconnection
mining: sibling cards sharing evidence, counter-evidence, related
recs, tech-stack absences); this migration adds only the columns:

  - ``affects``           — subcap_ids this card touches across pillars
    (multi-value; the legacy single `linked_subcap_id` stays the anchor).
  - ``platforms``         — implicated platform_ids (card badge + Linked tab).
  - ``interconnections``  — mined links [{kind, target_id, note, e_ids}]:
    counter-evidence, related recs, absences, sibling cards.
  - ``theme``             — short classification label for grouping/filters.

All NULL on legacy rows — `InsightCardOut` defaults keep the response
shape stable until re-derivation fills them.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "046_insight_interconnections"
down_revision = "045_deep_overview_surfaces"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("affects", "TEXT[]"),
    ("platforms", "TEXT[]"),
    ("interconnections", "JSONB"),
    ("theme", "VARCHAR(120)"),
)


def upgrade() -> None:
    for col, coltype in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='insight_cards' AND column_name='{col}'
                ) THEN
                    ALTER TABLE insight_cards ADD COLUMN {col} {coltype};
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for col, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE insight_cards DROP COLUMN IF EXISTS {col}")
