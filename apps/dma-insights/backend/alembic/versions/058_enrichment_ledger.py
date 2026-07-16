"""058 - enrichment_ledger: durable per-gap tracking for deploy-time enrichment

The Gemini enrichment of data-UNAVAILABILITY gaps must be RESILIENT across
deploys: every empty single-datum surface is tracked, a gap that got no usable
answer (Vertex cold, a transient error, an insufficient reply) is RE-PROBED on a
later deploy with backoff, and a resolved gap is never needlessly re-queried —
so no surface is silently left un-enriched while others succeed.

This table is that log. One row per (entity, field); the runner reads it to
decide what to (re)probe and writes the outcome of every attempt back.

status values:
  - ``pending``  — discovered, not yet attempted.
  - ``enriched`` — a sufficient, sourced answer was written (terminal).
  - ``absent``   — the model reliably reported the datum does not exist
                   (terminal until a long re-probe window elapses).
  - ``deferred`` — Vertex was cold/offline this deploy; retry next deploy.
  - ``failed``   — an error/insufficient loop; retry after ``next_probe_after``.

Columns:
  - ``entity_id``          FK entities ON DELETE CASCADE.
  - ``run_id``             the active run at last attempt (nullable).
  - ``field`` / ``surface`` the gap key + its surface tag.
  - ``status``             the 5-state machine above.
  - ``attempts``           total probe attempts across all deploys.
  - ``rounds``             iterative follow-up rounds used on the last attempt.
  - ``confidence``         last sufficient-answer confidence.
  - ``evidence_e_id``      the E-GEM citation written on success.
  - ``value_preview``      short preview of the acquired value (audit).
  - ``last_error``         last error/insufficiency reason (audit).
  - ``next_probe_after``   backoff gate; NULL ⇒ eligible now.
  - ``first_seen_at`` / ``last_attempt_at`` / ``updated_at``.

UNIQUE(entity_id, field) — the runner UPSERTs per gap.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "058_enrichment_ledger"
down_revision = "057_recommendation_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrichment_ledger",
        sa.Column(
            "id", postgresql.UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "entity_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("surface", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("rounds", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_e_id", sa.String(32), nullable=True),
        sa.Column("value_preview", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_probe_after", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("entity_id", "field",
                            name="uq_enrichment_ledger_entity_field"),
    )
    op.execute(
        "CREATE INDEX ix_enrichment_ledger_status "
        "ON enrichment_ledger (status, next_probe_after)"
    )
    op.execute(
        "CREATE INDEX ix_enrichment_ledger_entity "
        "ON enrichment_ledger (entity_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_enrichment_ledger_entity", "enrichment_ledger")
    op.drop_index("ix_enrichment_ledger_status", "enrichment_ledger")
    op.drop_table("enrichment_ledger")
