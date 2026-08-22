"""Grant the worker write access to the evidence dedup audit

Stage 1.3's persist step records package-time content-hash dedups in
evidence_dedup_audit (the same ledger the connector's register_evidence
uses at synthesis time). 0007 granted the table to svc_mcp only — at that
point no worker path deduped. The worker inserts audit rows but never
reads, updates or deletes them; grants stay that narrow.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-04
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT INSERT ON evidence_dedup_audit TO svc_worker")
    op.execute("GRANT USAGE ON SEQUENCE evidence_dedup_audit_id_seq TO svc_worker")


def downgrade() -> None:
    op.execute("REVOKE INSERT ON evidence_dedup_audit FROM svc_worker")
    op.execute("REVOKE USAGE ON SEQUENCE evidence_dedup_audit_id_seq FROM svc_worker")
