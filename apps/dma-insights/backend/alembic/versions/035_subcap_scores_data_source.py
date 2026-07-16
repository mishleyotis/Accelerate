"""035 - subcap_scores.data_source + parent_category_id (Batch 3)

Per the 2026-06-07 v2-QA Batch 3 finding: 14 packages in the live
corpus emit ``SubCap_ID`` at CATEGORY depth (``P1C1``, ``P2C3``, ...)
rather than canonical subcap depth (``P1C1.1.1``, ``P2C3.2.4``).
``CatalogueResolver.resolve_subcap`` correctly returns
``SubcapNotFound`` for every such row -- the v7.0 catalogue has 1236
subcap-level rows; none match. Result: 0 ``subcap_scores`` rows
persist, and the overview + heatmap endpoints render the empty
skeleton (the 28 FAIL cells in ``qa_render_matrix.tsv``).

Resolution is a SHALLOW CATALOGUE ALIAS BRIDGE: when the resolver
returns SubcapNotFound AND the parsed id is category-shaped
(``^P[1-4]C[1-9]$``), persist one ``subcap_scores`` row PER catalogue
child of that category, broadcasting the parent's score. The UI
surfaces the disclosure via ``data_source="shallow_broadcast"`` so an
AE never mistakes a broadcast cell for a directly-scored one.

This migration adds:

  - ``data_source`` VARCHAR(16) NOT NULL DEFAULT 'direct' with a
    CHECK constraint over the four documented sources:
      * ``direct``           -- parser emitted this subcap row as-is
      * ``shallow_broadcast`` -- broadcast from a category-level
                                source via the alias bridge (Batch 3)
      * ``llm_extracted``    -- subcap_narrative_extractor's Vertex
                                Pro structured-output pulled this row
                                from a pillar deep-dive section
      * ``heuristic_fallback`` -- LLM unavailable; template-fill from
                                the parent's rationale
  - ``parent_category_id`` VARCHAR(16) NULL -- the category id that
    sourced a broadcast row (e.g. ``P1C1``). NULL when
    ``data_source='direct'``.
  - Index on ``(run_id, data_source)`` for cheap admin-panel
    filtering ("show me all rows still broadcast for re-emit
    candidacy").

Idempotent: ADD COLUMN IF NOT EXISTS guards.
"""
from alembic import op

revision = "035_subcap_scores_data_source"
down_revision = "034_runs_artifact_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='subcap_scores'
                  AND column_name='data_source'
            ) THEN
                ALTER TABLE subcap_scores
                  ADD COLUMN data_source VARCHAR(16) NOT NULL
                    DEFAULT 'direct';
                ALTER TABLE subcap_scores
                  ADD CONSTRAINT subcap_scores_data_source_chk
                    CHECK (data_source IN (
                      'direct', 'shallow_broadcast',
                      'llm_extracted', 'heuristic_fallback'
                    ));
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='subcap_scores'
                  AND column_name='parent_category_id'
            ) THEN
                ALTER TABLE subcap_scores
                  ADD COLUMN parent_category_id VARCHAR(16);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_subcap_scores_run_data_source
          ON subcap_scores (run_id, data_source)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_subcap_scores_run_data_source")
    op.execute(
        "ALTER TABLE subcap_scores "
        "DROP CONSTRAINT IF EXISTS subcap_scores_data_source_chk"
    )
    op.execute("ALTER TABLE subcap_scores DROP COLUMN IF EXISTS data_source")
    op.execute(
        "ALTER TABLE subcap_scores DROP COLUMN IF EXISTS parent_category_id"
    )
