"""Auth tier: users, session_log (Backend Schema §03)

Grants land in the same revision that creates each table (working
discipline). The role matrix (§03) doesn't mention the auth tables
explicitly; the API performs the OIDC token exchange and re-verifies the
role claim on every request (TRD auth row), so svc_api gets read/upsert
on users and append/read on session_log — no DELETE anywhere, and the
other services get nothing (default-deny). Tighten at stage 4.1 if the
auth flow lands differently.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-04
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
          id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          email        CITEXT UNIQUE,          -- Workspace address; domain restricted at the OAuth client
          google_sub   TEXT UNIQUE,            -- stable OIDC subject: the join key, not the email
          display_name TEXT,
          role         user_role_t,
          is_active    BOOLEAN,                -- soft disable without deleting audit history
          created_at   TIMESTAMPTZ DEFAULT now(),
          last_seen_at TIMESTAMPTZ             -- updated on token refresh, not per request
        )
        """
    )
    op.execute(
        """
        CREATE TABLE session_log (
          id            BIGSERIAL PRIMARY KEY,
          user_id       UUID REFERENCES users(id),
          event         TEXT,                  -- login · logout · refresh · denied
          role_at_event user_role_t,           -- role as it was; a later change does not rewrite history
          ip            INET,
          user_agent    TEXT,
          occurred_at   TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON users TO svc_api")
    op.execute("GRANT SELECT, INSERT ON session_log TO svc_api")
    op.execute("GRANT USAGE ON SEQUENCE session_log_id_seq TO svc_api")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_log")
    op.execute("DROP TABLE IF EXISTS users")
