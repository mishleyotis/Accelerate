"""052 - focus_areas grounding/weights + KPI-override delta (D3)

The 2026-06 heatmap audit found synthesized focus areas ground
nothing (page_number NULL, quote = generated paragraph), pillar
weights are a frontend count-share proxy, and the KPI strip renders
no delta. Producers are `focus_area_synthesizer` (grounding +
pillars_weight) and its new `derive_focus_area_kpis` pass (delta);
this migration adds only the columns:

  focus_areas:
  - ``grounding``      — {representative_quote, evidence_e_ids,
    source_kind: docx|gemini|heuristic}; synthesized rows finally
    carry real anchors instead of a fake quote.
  - ``financial_ref``  — quantities match against the financial series
    (the wireframe SOURCE block's financial reference). NOTE: the
    unused 011-era ``financial_reference`` column was dropped by
    migration 023; this is the plan-named re-introduction, now with a
    producer.
  - ``pillars_weight`` — server-computed catalogue-weight share per
    pillar (replaces the FE count-share proxy).

  focus_area_kpi_overrides (migration 025):
  - ``delta``          — computed current→target delta label for the
    CustomizableKpiStrip.

All NULL on legacy rows — `FocusAreaOut` defaults keep the response
shape stable until re-derivation fills them.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "052_focus_area_grounding"
down_revision = "051_subcap_narratives"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("focus_areas", "grounding", "JSONB"),
    ("focus_areas", "financial_ref", "TEXT"),
    ("focus_areas", "pillars_weight", "JSONB"),
    ("focus_area_kpi_overrides", "delta", "VARCHAR(40)"),
)


def upgrade() -> None:
    for table, col, coltype in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='{table}' AND column_name='{col}'
                ) THEN
                    ALTER TABLE {table} ADD COLUMN {col} {coltype};
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for table, col, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")
