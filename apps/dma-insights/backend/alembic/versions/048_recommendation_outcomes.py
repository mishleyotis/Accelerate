"""048 - recommendations feature/phase/root-cause/outcomes fields (D4)

The 2026-06 platform audit found the RecommendationModal's richest
inputs never persisted: `recommendations_detail.json` + per-REC
`REC-NN.json` files (46/113 packages) carry feature, phase, root-cause
evidence and quantified outcomes, but the `recommendations` table had
no columns for them — the modal lost its evidence tab and the roadmap
collapsed to 1 phase for 91/94 clients. Producers are the extended
package_json parser + `derive_recommendations` (fill-if-empty); this
migration adds only the columns:

  - ``feature``            — the concrete platform feature the rec ships
    (distinct from the free-text title).
  - ``phase``              — sequencing phase from the source rec files;
    feeds the multi-phase roadmap (effort-band bucketing stays the
    fallback for rows without it).
  - ``root_cause_e_ids``   — E-IDs grounding the rec's root cause (the
    modal's restored "Root-cause evidence" tab).
  - ``outcomes``           — quantified expected outcomes JSONB with the
    shape {time, effort, metric, peer}.

``prerequisite_rec_ids`` already exists (migration 042) — NOT re-added.

All NULL on legacy rows — `RecommendationDetail` defaults keep the
response shape stable until re-ingest fills them.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "048_recommendation_outcomes"
down_revision = "047_timeline_nlp_fields"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("feature", "VARCHAR(120)"),
    ("phase", "SMALLINT"),
    ("root_cause_e_ids", "TEXT[]"),
    ("outcomes", "JSONB"),
)


def upgrade() -> None:
    for col, coltype in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='recommendations' AND column_name='{col}'
                ) THEN
                    ALTER TABLE recommendations ADD COLUMN {col} {coltype};
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for col, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE recommendations DROP COLUMN IF EXISTS {col}")
