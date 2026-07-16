"""051 - subcap_narratives: a durable home for per-subcap synthesis

The intelligence audit found `subcap_narrative_extractor` output has
NO durable table — the extractor's Vertex structured-output rows land
only in `vertex_synthesis_cache` (fingerprint-keyed, invalidatable),
so the D3 SynthesisDrawer's per-subcap rationale reached 1/94 clients
and the pack exporter had nothing stable to bake. This table persists
the winning narrative per (run, subcap):

  - ``meta``            — 'llm' (validator-passed Vertex output) or
    'heuristic' (deterministic composer floor); mirrors the heatmap
    cell's data-source chip.
  - ``evidence_e_ids``  — the E-IDs the narrative is grounded on
    ("AI synthesis on the N items above" in the drawer).
  - ``model``           — model id for llm rows (provenance mandate);
    NULL for heuristic rows.
  - UNIQUE(run_id, subcap_id) — writers UPSERT; the Gemini rung
    replaces the heuristic floor row when it validates.

Producers: extended `subcap_narrative_extractor` (deploy-hot Gemini)
+ the deterministic composer in `startup_enrich`. Readers: heatmap
subcap endpoint + pack writer (per_subcap_meta).

Idempotent: CREATE TABLE/INDEX IF NOT EXISTS.
"""
from alembic import op

revision = "051_subcap_narratives"
down_revision = "050_client_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS subcap_narratives (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL
                REFERENCES runs(id) ON DELETE CASCADE,
            subcap_id VARCHAR(24) NOT NULL,
            narrative_md TEXT NOT NULL,
            meta VARCHAR(16) NOT NULL DEFAULT 'heuristic'
                CHECK (meta IN ('llm', 'heuristic')),
            evidence_e_ids TEXT[],
            model VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (run_id, subcap_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS subcap_narratives")
