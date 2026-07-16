"""017 — section_embeddings table for narrative-style RAG retrieval

Revision ID: 017_section_embeddings
Revises: 016_ai_layer

Adds a per-document-section embedding store so the /rag/answer endpoint
can pull narrative-style content (e.g. "what did the analyst say about
retail banking maturity?") into the retrieval bundle alongside
evidence_embeddings + insight_embeddings.

State-branch contract:
  - empty            → no rows for a run → narrative-style RAG falls
                        back to evidence + insight bundles.
  - populated        → rows present → narrative bundle joins via similarity.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "017_section_embeddings"
down_revision = "016_ai_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS section_embeddings (
            section_id UUID PRIMARY KEY
                REFERENCES document_sections(id) ON DELETE CASCADE,
            run_id UUID NOT NULL
                REFERENCES runs(id) ON DELETE CASCADE,
            entity_id UUID NOT NULL
                REFERENCES entities(id) ON DELETE CASCADE,
            section_kind VARCHAR(32) NOT NULL,
            embedding vector(768) NOT NULL,
            embedded_text TEXT NOT NULL,
            model_version VARCHAR(32) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_section_embeddings_run "
        "ON section_embeddings (run_id, section_kind)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_section_embeddings_vec "
        "ON section_embeddings USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists=50)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS section_embeddings")
