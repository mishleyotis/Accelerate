"""Ops read grants: svc_api reads the scan ledger.

The admin Import & jobs page renders REAL executions of the package
scan (import_scans) instead of a mock job history. svc_api gets SELECT
on the two ingest-ops ledgers only — content tables stay connector-only
(invariant 2 concerns writes; reads here are operational metadata, no
client narrative content).
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON import_scans TO svc_api")
    op.execute("GRANT SELECT ON import_files TO svc_api")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON import_files FROM svc_api")
    op.execute("REVOKE SELECT ON import_scans FROM svc_api")
