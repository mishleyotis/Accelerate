"""Category display names, lifted from the capability map

The v7.0 workbook's 2_Capability_Map carries the category's display name
on every row ('Strategy Foundation & Alignment' for P1C1); the loader
never stored it, so category labels could only echo their ids. One small
table at the category grain — names come from the catalogue, never from
report prose (the assessment's own labels stay per-run in the stated
grains). Expand only; the loader populates it on the next load.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-04
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ccg_categories (
          version     TEXT,
          category_id TEXT,
          pillar_id   TEXT,
          name        TEXT,
          PRIMARY KEY (version, category_id)
        )
        """
    )
    op.execute("GRANT SELECT ON ccg_categories TO svc_api, svc_mcp, svc_worker")


def downgrade() -> None:
    op.execute("DROP TABLE ccg_categories")
