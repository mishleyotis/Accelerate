"""The due date gets a writer.

0031 computed refresh_due_date and 0032 built refresh_requests with an
origin of 'cadence' — and then nothing ever raised one: the queue endpoint
listed due entities and no writer existed, so a client past its six-month
date sat silent until a human noticed. The writer now lives in the hourly
enrichment loop (apps/worker/dma_worker/enrichment.py:sweep_refresh_due),
and this revision carries the grant that loop is owed: svc_worker reads
run_manifest to derive each promoted run's assessment date through
run_assessment_date(), the same function the serving directory uses, so
the worker and the directory can never disagree about when a client is due.

Grants ship in the same revision as the consumer (working discipline):
an existing table with a NEW consumer is owed a grant no create-table
revision covers — the enrichment loop itself once scanned 287 runs and
exited on `permission denied for table submissions` for exactly this
omission.
"""
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON run_manifest TO svc_worker")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON run_manifest FROM svc_worker")
