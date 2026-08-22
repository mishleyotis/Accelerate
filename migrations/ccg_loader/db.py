"""Connection for the catalogue loader — the migrate identity only.

LOCAL_DATABASE_URL (docker-compose / native parity) or the Cloud SQL
Python Connector with automatic IAM auth (the Cloud Run Job path).
Either way the session SET ROLEs to svc_migrate: the catalogue's only
writer is its owner.
"""
import os
import re

import pg8000.dbapi


def connect():
    url = os.environ.get("LOCAL_DATABASE_URL")
    if url:
        m = re.match(r".*://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(\w+)", url)
        user, password, host, port, db = m.groups()
        conn = pg8000.dbapi.connect(user=user, password=password, host=host,
                                    port=int(port or 5432), database=db)
    else:
        from google.cloud.sql.connector import Connector, IPTypes
        connector = Connector(ip_type=IPTypes.PRIVATE)
        conn = connector.connect(
            os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
            user=os.environ.get("DB_USER", "dmai-migrate@digital-maturity-assessor.iam"),
            db=os.environ.get("DB_NAME", "dma_insights"),
            enable_iam_auth=True,
        )
    cur = conn.cursor()
    cur.execute("SET ROLE svc_migrate")
    return conn
