"""How the connector reaches its database — and how often it asks Google.

WHY THIS IS A MODULE. It used to be eight lines inside `server.py`, which
cannot be imported without the MCP SDK, a database and an embedding model.
So the one piece of infrastructure every tool call goes through was the one
piece no test could execute; `test_documented_tool_counts.py` says as much
in its own docstring, and reads the file as text instead. A defect here is
invisible to the suite by construction — and one lived here for months.

THE DEFECT. `_conn()` read:

    from google.cloud.sql.connector import Connector
    c = Connector().connect(...)

A NEW Connector on every tool call. Two faults:

  1. A fresh Connector has an EMPTY instance-metadata cache, so its first
     connect calls the Cloud SQL ADMIN API endpoint `connectSettings` — one
     request per tool call, against a per-minute quota.
  2. It was never closed. Every discarded Connector kept a refresh alive that
     went on calling that same endpoint, so the burn rate grew with the
     instance's UPTIME and not only with its traffic.

Measured 2026-08-31, a producer pushing a 1.5 MB heatmap as ~53 serial parts:

    Error executing tool open_payload: 429, message='Too Many Requests',
    url='https://sqladmin.googleapis.com/sql/v1beta4/projects/
         digital-maturity-assessor/instances/dmai-pg/connectSettings'

Read which call took it: `open_payload`, the FIRST of the sequence, before a
single part had been sent. The quota was already spent — that is fault (2),
not the volume in (1). And note what the endpoint is: the database was never
rate-limiting anything. The refusal comes from an Admin API the client uses
to look up how to REACH the database, which is why this reads from outside as
"the database rate-limiter" and is nothing of the kind.

THE FIX. The library is built to be constructed once and reused; its cache
and refresh exist so that N connections cost ONE metadata fetch. So: one
Connector for the life of the process, behind a double-checked lock.

`refresh_strategy="lazy"` because this runs on Cloud Run, which throttles CPU
between requests. The default background refresher assumes a process that is
always scheduled; starved, it wakes late and stampedes the very endpoint this
exists to stop hammering. Lazy refreshes on demand when the metadata is
actually stale, which is the documented setting for serverless.

The SOCKET stays per call. Sharing metadata is the fix; sharing a connection
would be a worse bug than the one being repaired — `promote_run` holds
`SELECT … FOR UPDATE` on its own transaction (invariant 3).
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager

_CONNECTOR = None
_CONNECTOR_LOCK = threading.Lock()

#: Injected by the tests. Production leaves it None and imports the real
#: library lazily, so importing this module never needs Google installed.
_CONNECTOR_FACTORY = None


def _make_connector():
    if _CONNECTOR_FACTORY is not None:
        return _CONNECTOR_FACTORY(refresh_strategy="lazy")
    from google.cloud.sql.connector import Connector
    return Connector(refresh_strategy="lazy")


def cloud_sql_connector():
    """The process's one Connector, built on first use."""
    global _CONNECTOR
    if _CONNECTOR is None:
        with _CONNECTOR_LOCK:
            if _CONNECTOR is None:        # re-checked under the lock: two
                _CONNECTOR = _make_connector()   # threads racing the first
    return _CONNECTOR                     # call must not build two caches


def reset_connector():
    """Drop the cached Connector. For tests, and for a process that wants to
    re-authenticate; production never calls it."""
    global _CONNECTOR
    with _CONNECTOR_LOCK:
        c, _CONNECTOR = _CONNECTOR, None
    if c is not None and hasattr(c, "close"):
        try:
            c.close()
        except Exception:
            pass


@contextmanager
def connect():
    """One database connection for one unit of work, closed on the way out."""
    if os.environ.get("LOCAL_DATABASE_URL"):
        import pg8000.dbapi
        url = os.environ["LOCAL_DATABASE_URL"]
        host = url.split("@")[1].split(":")[0]
        c = pg8000.dbapi.connect(user="dmai-mcp@digital-maturity-assessor.iam",
                                 password="local", host=host, port=5432,
                                 database="dma_insights")
    else:
        c = cloud_sql_connector().connect(
            os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
            user=os.environ["DB_USER"], db=os.environ["DB_NAME"],
            enable_iam_auth=True, ip_type="PRIVATE")
    try:
        yield c
    finally:
        c.close()
