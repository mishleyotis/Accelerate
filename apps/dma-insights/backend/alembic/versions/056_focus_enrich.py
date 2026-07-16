"""056 - focus-area enrichment: linked insights, KPI reasoning, provenance

The 2026-07 focus-heatmap grounding wave adds the persistence for three
producers in ``focus_area_synthesizer`` + the ``focus_grounding`` /
``focus_kpi_extraction`` / ``focus_linked_insights`` Gemini surfaces in
``enrichment_queries``:

  focus_areas:
  - ``linked_insights``          — layered link rows [{id, ic_id, title,
    severity, linked_subcap_id, bases:[{kind,detail}], e_ids, source}].
    The union of (affects∩FA subcaps) + evidence co-citation + prose
    similarity, each link carrying its BASIS so the FocusAreaView
    minicards can argue *why* the card belongs (deterministic tier) and
    Gemini adjudicates the residual empty cases (source='gemini').
  - ``enrichment_provenance``    — traceability envelope for the row's
    Gemini-derived fields {grounding:{...}, linked_insights:{...}}:
    {source:'vertex', surface, model_id, synthesized_at, evidence_e_ids}.

  focus_area_kpi_overrides (migration 025):
  - ``evidence_e_ids``           — the E-IDs a synthesized KPI row is
    grounded on (current from a DISCLOSED value + its E-ID).
  - ``rationale``                — the reasoning tying the disclosed
    current + the roadmap-uplift target together.
  - ``provenance``               — per-row {source_mode, model_id,
    evidence, surface, synthesized_at}; source_mode 'gemini_reasoned' |
    'disclosed' | 'public' names how the row was produced.

All NULL/empty on legacy rows — ``FocusAreaOut`` + the KPI read path keep
their defaults until re-derivation fills them.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ blocks.
"""
from alembic import op

revision = "056_focus_enrich"
down_revision = "055_issue_register_attribution"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("focus_areas", "linked_insights", "JSONB"),
    ("focus_areas", "enrichment_provenance", "JSONB"),
    ("focus_area_kpi_overrides", "evidence_e_ids", "TEXT[]"),
    ("focus_area_kpi_overrides", "rationale", "TEXT"),
    ("focus_area_kpi_overrides", "provenance", "JSONB"),
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
