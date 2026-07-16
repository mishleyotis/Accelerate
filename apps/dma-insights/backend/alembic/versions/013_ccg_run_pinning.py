"""013 — pin runs + subcap_scores + peer_benchmarks to a catalogue version FK

Revision ID: 013_ccg_run_pinning
Revises: 012_ccg_catalogue
"""
from __future__ import annotations

from alembic import op

revision = "013_ccg_run_pinning"
down_revision = "012_ccg_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The runs.ccg_catalog_version column already exists from 003 (with default
    # 'v7.0'). We add the FK now that ccg_catalog_versions exists. Without this,
    # bootstrapping fails because the v7.0 row may not yet be loaded; we use NOT
    # VALID + a guard in the loader to validate later.
    op.execute(
        "ALTER TABLE runs ADD CONSTRAINT runs_ccg_catalog_version_fkey "
        "FOREIGN KEY (ccg_catalog_version) "
        "REFERENCES ccg_catalog_versions(version) NOT VALID"
    )
    op.execute(
        "ALTER TABLE peer_benchmarks ADD CONSTRAINT peer_benchmarks_ccg_version_fkey "
        "FOREIGN KEY (ccg_catalog_version) "
        "REFERENCES ccg_catalog_versions(version) NOT VALID"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE peer_benchmarks DROP CONSTRAINT IF EXISTS peer_benchmarks_ccg_version_fkey")
    op.execute("ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_ccg_catalog_version_fkey")
