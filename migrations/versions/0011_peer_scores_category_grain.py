"""Expand peer_scores to the shipped category grain

The Backend Schema gives peer_scores subcap and pillar columns; the
shipped General-DMA Peer_Benchmarks tab is CATEGORY grain (16 rows,
five named peers). As with 0009, the shipped data wins: category_id
lands as a nullable column alongside the documented grains. Only
per-peer scores are stored — medians, quartiles and deltas recompute
downstream (counts are computed, never stored). Expand only.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-04
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE peer_scores ADD COLUMN category_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE peer_scores DROP COLUMN category_id")
