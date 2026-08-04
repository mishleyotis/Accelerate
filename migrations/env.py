"""Alembic environment — runs as svc_migrate, never as a running service.

Connection resolution order:
1. LOCAL_DATABASE_URL           — docker-compose parity (any driver)
2. Cloud SQL Python Connector   — DB_INSTANCE_CONNECTION_NAME + DB_USER,
                                  automatic IAM auth (no password exists)

After revision 0001 exists, every connection SET ROLEs to svc_migrate so
objects are owned by the group role, not the individual login.
"""
import os

from alembic import context
from sqlalchemy import create_engine, text

config = context.config
target_metadata = None  # DDL is hand-written per the Backend Schema doc


def _engine():
    local_url = os.environ.get("LOCAL_DATABASE_URL")
    if local_url:
        return create_engine(local_url)

    instance = os.environ["DB_INSTANCE_CONNECTION_NAME"]
    user = os.environ.get("DB_USER", "dmai-migrate@digital-maturity-assessor.iam")
    db = os.environ.get("DB_NAME", "dma_insights")
    ip_type = os.environ.get("DB_IP_TYPE", "PRIVATE")

    from google.cloud.sql.connector import Connector, IPTypes

    connector = Connector(
        ip_type=IPTypes.PRIVATE if ip_type.upper() == "PRIVATE" else IPTypes.PUBLIC
    )

    def creator():
        return connector.connect(instance, "pg8000", user=user, db=db,
                                 enable_iam_auth=True)

    return create_engine("postgresql+pg8000://", creator=creator)


def run_migrations_offline() -> None:
    raise SystemExit("Offline mode is unsupported: grants depend on live role checks.")


def run_migrations_online() -> None:
    engine = _engine()
    with engine.connect() as connection:
        has_role = connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'svc_migrate'")
        ).scalar()
        if has_role:
            connection.execute(text("SET ROLE svc_migrate"))
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        # The pre-flight role check above began this connection's transaction,
        # so Alembic joined rather than owned it — commit is ours to do.
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
