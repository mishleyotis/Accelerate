"""SQLAlchemy model for ``recommendation_notes`` — the durable AE note that
backs the D4 RecommendationModal's "AE notes" textarea.

One shared team note per (client, recommendation): the row is keyed by
``UNIQUE(entity_id, rec_id)``, NOT per user. Per the operator mandate the
note PERSISTS across sessions AND across users — every AE who opens the
same recommendation for the same client sees (and overwrites) the same
note. ``rec_id`` is the HUMAN id ("REC-04"), not the recommendations.id
uuid, so the note survives a re-ingest that mints a fresh recommendation
row for the same logical rec.

FLAGGED FOR FUTURE SYNTHESIS
---------------------------
This table is the persisted INPUT for a FUTURE Gemini/ML recalibration
pass. The AE's note is captured + persisted here now; the recalibration
of findings / maturity scores / roadmap in light of that note is
DELIBERATELY NOT implemented in this change. Per the operator guardrail,
that recalibration must be a deep Gemini/ML impact simulation (a real
synthesis producer consuming these rows as grounding), not a
deterministic stub — so it is intentionally left for later. Nothing here
mutates scores; this module only defines where the note lives.

This ``Table`` is a SQLAlchemy Core artifact attached to a standalone
``MetaData`` (the repo uses ``target_metadata = None`` and hand-writes
migrations — see ``alembic/versions/057_recommendation_notes.py``, which
is the schema source of truth). The endpoints in
``app.routers.recommendations`` read/write via ``text()`` SQL per the
repo convention; this definition documents the shape in typed code.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Standalone metadata — intentionally NOT wired into alembic autogenerate
# (env.py keeps target_metadata = None). Inert w.r.t. migrations.
metadata = sa.MetaData()

recommendation_notes = sa.Table(
    "recommendation_notes",
    metadata,
    sa.Column(
        "id",
        postgresql.UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    sa.Column(
        "entity_id",
        postgresql.UUID(as_uuid=False),
        sa.ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # The human REC-id ("REC-04"), not the recommendations.id uuid.
    sa.Column("rec_id", sa.String(32), nullable=False),
    sa.Column("note_md", sa.Text(), nullable=False),
    sa.Column("author_email", sa.String(255), nullable=True),
    sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("NOW()"),
    ),
    sa.Column(
        "updated_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("NOW()"),
    ),
    # One shared team note per (client, recommendation).
    sa.UniqueConstraint(
        "entity_id", "rec_id", name="uq_recommendation_notes_entity_rec",
    ),
)
