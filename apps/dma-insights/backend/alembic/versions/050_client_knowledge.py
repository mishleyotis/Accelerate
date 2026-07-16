"""050 - client_knowledge_sections + knowledge_section_embeddings

The "great array" gap: `document_sections` covers only the two DOCX
report kinds, so RAG retrieval never spans the rest of the corpus
(profiles, workbooks, financial JSON, governance CSVs...). This pair
of tables sections EVERY material artifact so the per-client knowledge
layer is continuous:

  - ``client_knowledge_sections`` — one row per mined section of any
    material artifact: artifact_kind (structural pattern that matched),
    source_path + page + sha256 (exact provenance back to the
    raw_artifacts row, migration 049), heading/body, and a `provenance`
    JSONB for parser-specific anchors.
  - ``knowledge_section_embeddings`` — Vector(768) twin, one row per
    section (mirrors evidence_/section_embeddings, migrations 010/017),
    joined into the /rag/answer retrieval bundle alongside the existing
    embedding tables.

State-branch contract (mirrors 017):
  - empty      → sections not yet mined / embedder cold → retrieval
                 falls back to evidence + insight + section bundles.
  - populated  → whole-corpus retrieval joins via cosine similarity.

Idempotent: CREATE TABLE/INDEX IF NOT EXISTS.
"""
from alembic import op

revision = "050_client_knowledge"
down_revision = "049_raw_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS client_knowledge_sections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_id UUID NOT NULL
                REFERENCES entities(id) ON DELETE CASCADE,
            run_id UUID
                REFERENCES runs(id) ON DELETE SET NULL,
            artifact_kind VARCHAR(48) NOT NULL,
            source_path TEXT NOT NULL,
            sha256 CHAR(64),
            heading TEXT,
            body TEXT NOT NULL,
            page INTEGER,
            provenance JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_sections_entity_kind "
        "ON client_knowledge_sections (entity_id, artifact_kind)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_section_embeddings (
            section_id UUID PRIMARY KEY
                REFERENCES client_knowledge_sections(id) ON DELETE CASCADE,
            embedding vector(768) NOT NULL,
            model VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_section_embeddings_vec "
        "ON knowledge_section_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists=50)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_section_embeddings")
    op.execute("DROP TABLE IF EXISTS client_knowledge_sections")
