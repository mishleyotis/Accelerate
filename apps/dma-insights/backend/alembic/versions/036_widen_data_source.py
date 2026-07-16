"""036 - widen subcap_scores.data_source / parent_category_id (Batch 3 hotfix)

Migration 035 declared ``data_source VARCHAR(16)`` but the
canonical values include ``shallow_broadcast`` (17 chars) and
``heuristic_fallback`` (18 chars) which overflow the column on
INSERT with ``StringDataRightTruncationError`` and abort every
re-ingest that hits the bridge.

Widen both columns to ``VARCHAR(24)`` (room for future labels like
``vertex_pro_rewrite`` for Batch 6 + buffer); the CHECK constraint
keeps the value set documented + enforced.
"""
from alembic import op

revision = "036_widen_data_source"
down_revision = "035_subcap_scores_data_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subcap_scores "
        "ALTER COLUMN data_source TYPE VARCHAR(24)"
    )
    # parent_category_id stays VARCHAR(16) -- category IDs are
    # P[1-4]C[1-9] (max 4 chars); but bump to 24 for symmetry.
    op.execute(
        "ALTER TABLE subcap_scores "
        "ALTER COLUMN parent_category_id TYPE VARCHAR(24)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE subcap_scores "
        "ALTER COLUMN parent_category_id TYPE VARCHAR(16)"
    )
    op.execute(
        "ALTER TABLE subcap_scores "
        "ALTER COLUMN data_source TYPE VARCHAR(16)"
    )
