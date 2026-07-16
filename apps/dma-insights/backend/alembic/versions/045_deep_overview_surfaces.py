"""045 - runs.{evidence_summary,coverage_stats,uncertainty_bands} for D1

The prototype's "Evidence & benchmarks" section (EvidenceTierCard /
CoverageByPillarCard / CeilingEstimateCard) had no backing data — the
2026-06 page audit measured 0/94 clients with any of the three
surfaces. The producer is the NEW `derive_evidence_surfaces` step
(wave 5 of run_derive_chain); this migration only adds the columns so
the data contract can land ahead of the derivation logic:

  - ``evidence_summary``   — tier/claim/signal histogram over the run's
    evidence_index rows: {total_items, total_facts, tiers{T1..T8},
    claims{}, signals{}, connectors{}}.
  - ``coverage_stats``     — scored-vs-catalogue coverage: {overall_pct,
    by_pillar[{pillar, pct, subcaps, scored}], gate_pct}.
  - ``uncertainty_bands``  — ceiling estimate + band + modifiers/
    rationale composed from real facts (issue caps, thin counts,
    confirmed platform absences).

All three default NULL — the overview endpoint emits them as-is and
the frontend keeps its honest-empty state until the deriver fills them.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "045_deep_overview_surfaces"
down_revision = "044_tech_stack_prototype_fields"
branch_labels = None
depends_on = None

_COLUMNS = ("evidence_summary", "coverage_stats", "uncertainty_bands")


def upgrade() -> None:
    for col in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='runs' AND column_name='{col}'
                ) THEN
                    ALTER TABLE runs ADD COLUMN {col} JSONB;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for col in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE runs DROP COLUMN IF EXISTS {col}")
