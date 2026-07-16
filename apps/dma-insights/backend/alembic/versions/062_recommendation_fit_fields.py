"""062 - recommendation fit fields (analyst-recommendation-driven platform fit)

2026-07-15 platform-fit rework. The fit engine is being inverted from a
deterministic catalogue enumeration to a READ of the analyst's own
recommendations. The engine + D4 cards + exec summary + roadmap need three
per-recommendation fields the parser did not previously persist:

  zennify_product      the SPECIFIC product the analyst named (Financial
                       Services Cloud, Data Cloud, MuleSoft, …) — extracted via
                       services.platform_products from the rec title/description.
                       The prior platform_id collapsed every SF-family product
                       into one "salesforce" bucket; this keeps the specificity.
  priority_rank        the analyst's priority normalised to a sortable int
                       (P0/CRITICAL/NOW = 0 … lower = more urgent) so cards +
                       the exec-summary lead order the analyst's own priority.
  strategic_objectives the client strategic objectives the rec serves (the
                       strategic-objective-alignment fit factor).

The integration-effort factor (effort_band) and evidence (root_cause_e_ids)
reuse columns that already exist on the table but were never populated.

Idempotent: ADD COLUMN IF NOT EXISTS throughout; no data migration.
"""
from alembic import op

revision = "062_recommendation_fit_fields"
down_revision = "061_ae_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE recommendations
            ADD COLUMN IF NOT EXISTS zennify_product VARCHAR(48),
            ADD COLUMN IF NOT EXISTS priority_rank SMALLINT,
            ADD COLUMN IF NOT EXISTS strategic_objectives JSONB
        """
    )
    # Hot path: the fit engine groups a run's recs by product.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_recommendations_run_product
            ON recommendations (run_id, zennify_product)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_recommendations_run_product")
    op.execute(
        """
        ALTER TABLE recommendations
            DROP COLUMN IF EXISTS zennify_product,
            DROP COLUMN IF EXISTS priority_rank,
            DROP COLUMN IF EXISTS strategic_objectives
        """
    )
