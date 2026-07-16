"""019 — vertex_synthesis_cache: unified persistence layer for every
Vertex/Gemini synthesis output, with decision-gate audit + lifecycle.

Revision ID: 019_vertex_synthesis_cache
Revises: 018_intelligence_layer

Replaces the four disparate caches (`gemini_cache`, `ai_enrichments`,
`customer_intelligence_profiles.intelligence_summary_md`, in-memory
dicts) behind ONE table with a hard contract: once Vertex interprets
information, the output is persisted; subsequent reads consume zero
tokens until the input fingerprint changes.

State-transition contract for `decision_gate`:
  parsed_skipped_llm        — surface fully derivable from parsed
                              CSV/DOCX — no Vertex call; no row
                              inserted (audit only via audit_log).
  cache_hit                 — active row, fingerprint match, not
                              expired, not invalidated.
  cache_miss_synthesized    — no row matching fingerprint; new row
                              inserted with synthesis output.
  invalidated_re_synthesized — row exists but invalidated_at NOT
                              NULL or expires_at < NOW(); new row
                              inserted, prior row's superseded_by set.
  user_regenerate           — explicit force_regenerate=True; new
                              row written; prior superseded.
  feedback_invalidated      — feedback (👎 hallucinated) invalidated
                              the row; next equivalent read re-synthesizes.
  rerun_invalidate_all      — entire run produced a fresh ingest;
                              entity's prior cache rows superseded
                              lazily on next read.
  catalogue_bump_invalidate — catalogue_version bump invalidates rows
                              keyed under the prior version.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "019_vertex_synthesis_cache"
down_revision = "018_intelligence_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vertex_synthesis_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("surface", sa.String(64), nullable=False),
        sa.Column("model", sa.String(32), nullable=False),
        # Input fingerprint
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "prompt_template_version", sa.String(16), nullable=False
        ),
        sa.Column("grounding_bundle_hash", sa.String(64), nullable=False),
        sa.Column("catalogue_version", sa.String(16), nullable=False),
        # Output
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("output_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "cited_evidence_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "cited_subcap_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
        ),
        sa.Column("validators_passed", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        # Token accounting
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        # Lifecycle
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("access_count", sa.Integer(), server_default="0"),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "invalidated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "invalidation_reason", sa.String(64), nullable=True
        ),
        sa.Column(
            "superseded_by",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        sa.Column("decision_gate", sa.String(48), nullable=False),
        sa.UniqueConstraint(
            "target_kind",
            "target_id",
            "surface",
            "input_fingerprint",
            name="uq_vertex_synth_fp",
        ),
    )
    # Hot read path: active rows by (target_kind, target_id, surface)
    op.execute(
        "CREATE INDEX ix_vertex_synth_active "
        "ON vertex_synthesis_cache (target_kind, target_id, surface) "
        "WHERE invalidated_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_vertex_synth_fingerprint "
        "ON vertex_synthesis_cache (input_fingerprint) "
        "WHERE invalidated_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_vertex_synth_catalogue_surface "
        "ON vertex_synthesis_cache (catalogue_version, surface)"
    )

    # Seed per-surface TTL config (plan §⑫). system_config.value is JSONB.
    op.execute(
        """
        INSERT INTO system_config (key, value, updated_at)
        VALUES
          ('vertex_synth_ttl_rag_answer_sec', '900'::jsonb, NOW()),
          ('vertex_synth_ttl_subcap_narrative_sec', '604800'::jsonb, NOW()),
          ('vertex_synth_ttl_platform_story_sec', '259200'::jsonb, NOW()),
          ('vertex_synth_ttl_insight_explanation_sec', '259200'::jsonb, NOW()),
          ('vertex_synth_ttl_meeting_prep_sec', '86400'::jsonb, NOW()),
          ('vertex_synth_ttl_why_now_sec', '86400'::jsonb, NOW()),
          ('vertex_synth_ttl_intelligence_summary_sec', '604800'::jsonb, NOW()),
          ('vertex_synth_ttl_recommendation_explainer_sec', '259200'::jsonb, NOW()),
          ('vertex_synth_gc_retention_days', '90'::jsonb, NOW())
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("vertex_synthesis_cache")
    op.execute(
        """
        DELETE FROM system_config
        WHERE key LIKE 'vertex_synth_%'
        """
    )
