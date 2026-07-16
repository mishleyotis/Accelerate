"""016 — AI layer: chat sessions/messages/feedback, ai_enrichments,
peer_archetypes, system_config, chat_learning_signals.

This migration lands the persistence backbone for the DMA Insights AI layer:

  - **chat_sessions / chat_messages / chat_feedback** — every RAG /answer
    interaction is recorded so we can (a) resume a conversation across
    page reloads, (b) collect thumbs-up/down feedback per assistant
    message, and (c) capture user-supplied "better_answer" text as the
    adversarial-network signal that re-ranks future retrievals.

  - **chat_learning_signals** — nightly rollup of feedback grouped by
    KMeans clusters of question embeddings. Each row stores an
    `effectiveness` score the next-prompt selector uses to bias
    retrieval ordering toward patterns historical users approved of.

  - **ai_enrichments** — every LLM-generated narrative text (subcap
    rationale, insight explanation, platform story) lands here with
    `grounding_evidence_ids` so the UI can render "AI-enriched (grounded
    on E-101, E-204)" provenance chips. Supersede chain via
    `superseded_by` keeps the audit trail when catalogue versions
    bump or a re-run replaces a prior enrichment.

  - **peer_archetypes** — output of the cross-DMA pattern recognition
    worker. KMeans on (entity × subcap-score-vector) per subvertical
    yields N maturity archetypes ("compliance-first", "experience-first",
    "agentic-pilot"). The /entities/{id}/archetype endpoint reads from
    here to surface the "Closest archetype: …" chip on D3.

  - **system_config** — key/value scratchpad for admin-tunable knobs
    (vertex monthly budget, validator strictness, …). One row per key.

Plan reference: §⑫ (grounding validators), Deliverable #2 (chat
persistence + adversarial learning), Deliverable #3 (enrichment with
evidence IDs), Deliverable #6 (cross-DMA pattern recognition).

Revision ID: 016_ai_layer
Revises: 015_runs_parser_warnings
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "016_ai_layer"
down_revision = "015_runs_parser_warnings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. chat_sessions — one row per (user, surface, entity?) thread.
    #    A "global" chat (Dashboard) has entity_id=NULL.
    # ------------------------------------------------------------------
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("surface", sa.String(64), nullable=False),
        sa.Column("page_context", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("catalogue_version", sa.String(16), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_message_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index(
        "ix_chat_sessions_user_recent",
        "chat_sessions",
        ["user_id", sa.text("last_message_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_chat_sessions_entity",
        "chat_sessions",
        ["entity_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------
    # 2. chat_messages — append-only conversation log. Stores the
    #    retrieval_bundle JSONB so the adversarial-learning worker can
    #    replay the (prompt, retrieval, response) triple later.
    # ------------------------------------------------------------------
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content_markdown", sa.Text, nullable=False),
        sa.Column("cited_evidence_ids", postgresql.ARRAY(sa.String(16))),
        sa.Column("cited_subcap_ids", postgresql.ARRAY(sa.String(32))),
        sa.Column("retrieval_bundle", postgresql.JSONB),
        sa.Column("model", sa.String(32)),
        sa.Column("tokens_in", sa.Integer),
        sa.Column("tokens_out", sa.Integer),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("validators_passed", sa.Boolean),
        sa.Column("hallucination_flags", postgresql.JSONB),
        sa.Column("embedding", Vector(768)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "role IN ('user','assistant','system')", name="chat_messages_role_chk",
        ),
    )
    op.create_index("ix_chat_messages_session", "chat_messages",
                    ["session_id", "created_at"])
    op.execute(
        "CREATE INDEX ix_chat_messages_embedding "
        "ON chat_messages USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists=50)"
    )

    # ------------------------------------------------------------------
    # 3. chat_feedback — per-message thumbs/free-text/better_answer.
    #    The `better_answer` column is the explicit adversarial signal:
    #    user-supplied "what should it have said" lets the next-prompt
    #    selector contrast against the served text.
    # ------------------------------------------------------------------
    op.create_table(
        "chat_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("rating", sa.SmallInteger, nullable=False),
        sa.Column("unhelpful_reason", sa.String(64)),
        sa.Column("free_text", sa.Text),
        sa.Column("better_answer", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint("rating IN (-1, 0, 1)", name="chat_feedback_rating_chk"),
        sa.CheckConstraint(
            "unhelpful_reason IS NULL OR unhelpful_reason IN ("
            "'too_verbose','hallucinated','wrong_subcap','no_evidence',"
            "'irrelevant','other')",
            name="chat_feedback_reason_chk",
        ),
    )
    op.create_index("ix_chat_feedback_message", "chat_feedback", ["message_id"])
    op.create_index("ix_chat_feedback_user", "chat_feedback", ["user_id"])

    # ------------------------------------------------------------------
    # 4. chat_learning_signals — nightly rollup. One row per
    #    (surface, prompt_cluster) keyed by catalogue_version.
    # ------------------------------------------------------------------
    op.create_table(
        "chat_learning_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("surface", sa.String(64), nullable=False),
        sa.Column("prompt_cluster_id", postgresql.UUID(as_uuid=True)),
        sa.Column("prompt_centroid", Vector(768)),
        sa.Column("exemplar_question", sa.Text),
        sa.Column("retrieval_quality", sa.Numeric(4, 3)),
        sa.Column("response_quality", sa.Numeric(4, 3)),
        sa.Column("effectiveness", sa.Numeric(4, 3)),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("preferred_evidence_ids", postgresql.ARRAY(sa.String(16))),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index(
        "ix_chat_learning_surface_eff",
        "chat_learning_signals",
        ["surface", sa.text("effectiveness DESC")],
    )

    # ------------------------------------------------------------------
    # 5. ai_enrichments — every LLM narrative artifact lands here so the
    #    UI can render the grounding-chip provenance. Idempotent via
    #    superseded_by: a re-run flips the prior row's pointer instead
    #    of deleting it (full audit trail).
    # ------------------------------------------------------------------
    op.create_table(
        "ai_enrichments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("surface", sa.String(64), nullable=False),
        sa.Column("enrichment_text", sa.Text, nullable=False),
        sa.Column("grounding_evidence_ids", postgresql.ARRAY(sa.String(16)),
                  nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("grounding_subcap_ids", postgresql.ARRAY(sa.String(32))),
        sa.Column("model", sa.String(32), nullable=False),
        sa.Column("catalogue_version", sa.String(16), nullable=False),
        sa.Column("validators_passed", sa.Boolean, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "target_kind IN ('subcap_score','insight_card','recommendation','entity')",
            name="ai_enrichments_target_chk",
        ),
    )
    op.create_index(
        "ix_ai_enrichments_target_active",
        "ai_enrichments",
        ["target_kind", "target_id"],
        postgresql_where=sa.text("superseded_by IS NULL"),
    )
    op.create_index(
        "ix_ai_enrichments_catalogue",
        "ai_enrichments",
        ["catalogue_version"],
    )

    # ------------------------------------------------------------------
    # 6. peer_archetypes — cross-DMA pattern recognition output.
    # ------------------------------------------------------------------
    op.create_table(
        "peer_archetypes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("subvertical", sa.String(8), nullable=False),
        sa.Column("catalogue_version", sa.String(16), nullable=False),
        sa.Column("archetype_label", sa.String(64), nullable=False),
        sa.Column("centroid_vector", postgresql.ARRAY(sa.Numeric)),
        sa.Column("defining_subcap_ids", postgresql.ARRAY(sa.String(32))),
        sa.Column("entity_ids_in_archetype", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("silhouette_score", sa.Numeric(4, 3)),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "subvertical", "catalogue_version", "archetype_label",
            name="uq_peer_archetypes_sv_ver_label",
        ),
    )
    op.create_index(
        "ix_peer_archetypes_sv_ver",
        "peer_archetypes",
        ["subvertical", "catalogue_version"],
    )

    # ------------------------------------------------------------------
    # 7. system_config — admin-tunable knobs.
    # ------------------------------------------------------------------
    op.create_table(
        "system_config",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    # Seed the monthly Vertex budget. 100 USD is a placeholder — admin
    # bumps it from the UI when usage warrants.
    op.execute(
        "INSERT INTO system_config (key, value) "
        "VALUES ('vertex_budget_monthly_usd', '100'::jsonb)"
    )

    # ------------------------------------------------------------------
    # 8. parent_request_id versioning chain — add the FK back to
    #    runs.request_id (self-reference). NOT VALID so existing rows
    #    don't have to back-fill. The chain endpoint reads through
    #    request_id, not the FK, so NOT VALID is safe.
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE runs ADD CONSTRAINT runs_parent_request_id_fkey "
        "FOREIGN KEY (parent_request_id) REFERENCES runs(request_id) "
        "ON DELETE SET NULL NOT VALID"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_parent_request_id_fkey")
    op.drop_table("system_config")
    op.drop_index("ix_peer_archetypes_sv_ver", table_name="peer_archetypes")
    op.drop_table("peer_archetypes")
    op.drop_index("ix_ai_enrichments_catalogue", table_name="ai_enrichments")
    op.drop_index("ix_ai_enrichments_target_active", table_name="ai_enrichments")
    op.drop_table("ai_enrichments")
    op.drop_index("ix_chat_learning_surface_eff", table_name="chat_learning_signals")
    op.drop_table("chat_learning_signals")
    op.drop_index("ix_chat_feedback_user", table_name="chat_feedback")
    op.drop_index("ix_chat_feedback_message", table_name="chat_feedback")
    op.drop_table("chat_feedback")
    op.execute("DROP INDEX IF EXISTS ix_chat_messages_embedding")
    op.drop_index("ix_chat_messages_session", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_entity", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_user_recent", table_name="chat_sessions")
    op.drop_table("chat_sessions")
