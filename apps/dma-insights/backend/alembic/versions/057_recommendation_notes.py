"""057 - recommendation_notes: durable per-recommendation AE note (D4)

Backs the RecommendationModal's "AE notes" textarea — a single shared
team note per (client, recommendation). The operator mandate is that
enhancements PERSIST across sessions AND across users, so the row is
keyed by ``UNIQUE(entity_id, rec_id)`` (NOT per-user): whichever AE last
saved wins, and every AE / session sees the same note on reload.

FLAGGED FOR FUTURE SYNTHESIS — this table is the persisted INPUT for a
future Gemini/ML recalibration pass. The note text is captured + stored
now; the recalibration of findings / maturity scores / roadmap in light
of the AE's note is deliberately NOT implemented in this change. Per the
operator guardrail, that recalibration must be a deep Gemini/ML impact
simulation, not a deterministic stub — so it is left for a later synthesis
producer to consume ``recommendation_notes`` as grounding.

Columns:
  - ``id``            — uuid pk (gen_random_uuid()).
  - ``entity_id``     — FK entities.id ON DELETE CASCADE, indexed. The
    note dies with the client.
  - ``rec_id``        — the human REC-id ("REC-04"), NOT the rec uuid, so
    the note survives re-ingest that mints a new recommendations.id.
  - ``note_md``       — the analyst note (markdown-ish free text).
  - ``author_email``  — stamped from the current user on each write (null
    only on rows written before auth wiring; always set going forward).
  - ``created_at`` / ``updated_at`` — timestamptz, default NOW().

A blank/whitespace note is a DELETE at the endpoint layer (no empty rows).
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "057_recommendation_notes"
down_revision = "056_focus_enrich"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_notes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "entity_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("rec_id", sa.String(32), nullable=False),
        sa.Column("note_md", sa.Text(), nullable=False),
        sa.Column("author_email", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "entity_id", "rec_id",
            name="uq_recommendation_notes_entity_rec",
        ),
    )
    op.execute(
        "CREATE INDEX ix_recommendation_notes_entity "
        "ON recommendation_notes (entity_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_recommendation_notes_entity", "recommendation_notes")
    op.drop_table("recommendation_notes")
