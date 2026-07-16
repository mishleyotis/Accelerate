"""037 - widen ccg_loader_runs.status (catalogue-load blocker hotfix)

Migration 012 declared ``ccg_loader_runs.status VARCHAR(16)`` but its
own CHECK constraint admits ``AWAITING_APPROVAL`` (17 chars) -- the
status the loader writes on a clean parse with all validators green
(``workers/ccg_loader/main.py`` ``status_val``). The 17-char value
overflows the 16-char column with ``StringDataRightTruncationError``,
which aborts the *entire* loader transaction. Because
``ccg_catalog_versions`` / ``ccg_pillars`` / ``ccg_subcaps`` are all
inserted in that same transaction, a successful parse rolled back to
**zero catalogue rows** -- i.e. the v7.0 catalogue could never be
persisted.

Same failure class as 036 (a CHECK value wider than its column).
Widen ``status`` to ``VARCHAR(20)`` -- room for ``AWAITING_APPROVAL``
plus buffer; the CHECK constraint keeps the value set enforced.
"""
from alembic import op

revision = "037_widen_loader_run_status"
down_revision = "036_widen_data_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ccg_loader_runs "
        "ALTER COLUMN status TYPE VARCHAR(20)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ccg_loader_runs "
        "ALTER COLUMN status TYPE VARCHAR(16)"
    )
