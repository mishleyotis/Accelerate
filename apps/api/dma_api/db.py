"""One connection factory, for the service and for the Job that ships in the
same image.

`main.py` had this inline. It moved here when `refresh_job.py` needed the same
connection under a different DB identity: two copies of the Cloud SQL
connector setup is two places for `ip_type` or IAM auth to drift, and a Job
that connects differently from the service it deploys beside is a difference
nobody notices until one of them cannot reach the database.

The identity is NOT hardcoded: `DB_USER` is whatever the deployment sets, and
that is the whole point of the split — the API runs as `dmai-api` (svc_api,
SELECT on the serving tier) and the refresh Job runs as `dmai-worker`
(svc_worker, the only role granted INSERT on `refresh_requests`). Same code,
different grants, enforced by the database rather than by discipline.
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
                                    host=host, port=5432, database="dma_insights")
    from google.cloud.sql.connector import Connector
    connector = _POOL.setdefault("connector", Connector())
    return connector.connect(
        os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
        user=os.environ["DB_USER"], db=os.environ["DB_NAME"],
        enable_iam_auth=True, ip_type="PRIVATE")


def close() -> None:
    if "connector" in _POOL:
        _POOL.pop("connector").close()
