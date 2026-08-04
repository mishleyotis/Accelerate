"""Extensions, the four service roles, default-deny schema

Backend Schema, "Database roles" — created before any table exists so no
table is ever created without its grants (Implementation Plan 0.2):

  svc_api     SELECT on serving/catalogue/workflow; INSERT on annotations
              and alert_actions only. No grant of any kind on staging.
  svc_mcp     SELECT on ingested/catalogue; full DML on staging, serving,
              control and audit. The ONLY role that can write a serving table.
  svc_worker  Full DML on ingested and ingest-ops; SELECT on catalogue.
              No access to serving or staging.
  svc_migrate DDL. Used by migrations at deploy, never by a running service.

This revision creates the group roles and the default-deny posture; the
per-table grants land in the same revision that creates each table.

Revision ID: 0001
Revises:
Create Date: 2026-08-04
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SERVICE_ROLES = ("svc_api", "svc_mcp", "svc_worker", "svc_migrate")

# Cloud SQL IAM database users (also created locally by the docker-compose
# init script, so grants behave identically in both environments).
IAM_MEMBERS = {
    "svc_api": "dmai-api@digital-maturity-assessor.iam",
    "svc_mcp": "dmai-mcp@digital-maturity-assessor.iam",
    "svc_worker": "dmai-worker@digital-maturity-assessor.iam",
    "svc_migrate": "dmai-migrate@digital-maturity-assessor.iam",
}


def upgrade() -> None:
    # Extensions (TRD data platform): vector, citext, pg_trgm, pgcrypto.
    for ext in ("vector", "citext", "pg_trgm", "pgcrypto"):
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')

    # Group roles, NOLOGIN — identity arrives via IAM user membership.
    for role in SERVICE_ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
              END IF;
            END $$
            """
        )

    # Default-deny: nothing is grantable by accident. PUBLIC loses CREATE
    # (explicit, though PostgreSQL 15+ already restricts it) and the service
    # roles get USAGE only — table access arrives per-table, per-migration.
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute("REVOKE ALL ON DATABASE dma_insights FROM PUBLIC")
    for role in SERVICE_ROLES:
        op.execute(f"GRANT CONNECT ON DATABASE dma_insights TO {role}")
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    op.execute("GRANT CREATE ON SCHEMA public TO svc_migrate")

    # IAM user membership — conditional so the same file applies anywhere the
    # user exists (Cloud SQL always; local compose via pg-init).
    for role, member in IAM_MEMBERS.items():
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{member}') THEN
                GRANT {role} TO "{member}";
              END IF;
            END $$
            """
        )

    # Alembic's own version table must not be writable by the services.
    # (It is created by the connected migration user; nothing to grant.)


def downgrade() -> None:
    for role, member in IAM_MEMBERS.items():
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{member}') THEN
                REVOKE {role} FROM "{member}";
              END IF;
            END $$
            """
        )
    for role in SERVICE_ROLES:
        op.execute(f"REVOKE ALL ON SCHEMA public FROM {role}")
        op.execute(f"REVOKE ALL ON DATABASE dma_insights FROM {role}")
        op.execute(f"DROP ROLE IF EXISTS {role}")
    op.execute("GRANT CREATE ON SCHEMA public TO PUBLIC")
    # Extensions are left installed: other revisions' types may depend on them.
