"""Cloud SQL connection for the corpus Jobs, IAM auth over Direct VPC egress.

Same shape as `apps/api/dma_api/db.py` and deliberately a separate file: this
image ships no application code, so importing across deployables would mean
building the api image to run a nightly export. The identity is whatever
`DB_USER` names — both Jobs run as `dmai-mcp`, which is the only account that
already holds the serving-tier SELECT the pack needs and the `gate_results`
DML the scanner needs.
"""
from __future__ import annotations

import os

_POOL: dict = {}


def connect():
    if os.environ.get("LOCAL_DATABASE_URL"):
        import pg8000.dbapi
        url = os.environ["LOCAL_DATABASE_URL"]
        host = url.split("@")[1].split(":")[0]
        return pg8000.dbapi.connect(user="postgres", password="local",
                                    host=host, port=5432,
                                    database=os.environ.get("DB_NAME", "dma_insights"))
    from google.cloud.sql.connector import Connector
    connector = _POOL.setdefault("connector", Connector())
    return connector.connect(
        os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
        user=os.environ["DB_USER"], db=os.environ["DB_NAME"],
        enable_iam_auth=True, ip_type="PRIVATE")


def close() -> None:
    if "connector" in _POOL:
        _POOL.pop("connector").close()
