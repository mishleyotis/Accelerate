"""One Cloud SQL Connector per process, for every service that has one.

WHY THIS EXISTS. On 2026-08-31 a live intake firing called
`get_client_state` and got, from the MCP connector:

    429 Too Many Requests
    https://sqladmin.googleapis.com/sql/v1beta4/projects/
      digital-maturity-assessor/instances/dmai-pg/connectSettings

That URL is the giveaway: it is not the database refusing a query, it is
the Cloud SQL ADMIN API refusing a metadata lookup. `Connector()` fetches
`connectSettings` when it is constructed and then keeps it warm with a
background refresh — so ONE Connector per process makes roughly one Admin
API call per hour, and a NEW Connector per connection makes one per
connection. `apps/mcp/server.py` did the latter:

    c = Connector().connect(...)        # inside a per-call context manager

Every tool call built a Connector, fetched connectSettings, opened one
connection, and dropped the Connector on the floor without closing it —
which also leaks its refresh task. A routine that walks the queue, checks a
client, reads evidence and opens a payload makes dozens of those in a
minute, against a per-project Admin API quota, so the 429 arrives on
whichever call happens to be unlucky. Nothing about the failure points at
the caller, which is why it read as a database problem.

`apps/api/dma_api/db.py` already had it right — `_POOL.setdefault(
"connector", Connector())` — and its own docstring says why this file now
exists: "two copies of the Cloud SQL connector setup is two places for
`ip_type` or IAM auth to drift". There were four.

THE POOL DOES NOT SAVE YOU HERE, and that is worth stating because it is
the intuition that hides this bug. The services run `NullPool` behind the
Cloud SQL pooler (TRD §: asyncpg/pg8000 behind managed connection pooling,
`statement_cache_size=0`), so SQLAlchemy deliberately does NOT hold
connections open — every checkout is a real new connection. That is
correct for the pooler and it is exactly what turns a per-call Connector
into a per-call Admin API request.

    from cloudsql import connect          # staged into each image
    conn = connect(user=os.environ["DB_USER"])

The identity is never hardcoded: each service passes the DB_USER its
deployment sets, which is the whole point of the split — `dmai-api` reads
the serving tier, `dmai-mcp` writes content, `dmai-worker` parses. Same
code, different grants, enforced by the database rather than by discipline.
"""
from __future__ import annotations

import os
import threading

#: Process-wide, and guarded: two threads racing to build the first
#: Connector would each fetch connectSettings, which is the very call this
#: module exists to make rare.
_LOCK = threading.Lock()
_STATE: dict = {}


def _connector():
    c = _STATE.get("connector")
    if c is not None:
        return c
    with _LOCK:
        if "connector" not in _STATE:
            from google.cloud.sql.connector import Connector
            # LAZY, because these run on Cloud Run with CPU THROTTLED between
            # requests — `infra/deploy.sh` sets no --no-cpu-throttling, so
            # outside a request the instance gets close to none. The default
            # background refresh is an asyncio task on a ~55-minute timer, and
            # a timer that only advances while a request happens to be in
            # flight is not a timer: it wakes late, finds the metadata stale,
            # and every starved instance goes to `connectSettings` at once —
            # the same endpoint, and the same 429, this module exists to make
            # rare. Lazy refreshes ON DEMAND when the cached metadata is
            # actually expired, which is the documented setting for
            # serverless and needs no scheduler.
            _STATE["connector"] = Connector(refresh_strategy="lazy")
        return _STATE["connector"]


def connect(*, user: str | None = None, db: str | None = None,
            driver: str = "pg8000", ip_type: str = "PRIVATE",
            local_user: str | None = None):
    """A DBAPI connection, through the cached Connector.

    `LOCAL_DATABASE_URL` keeps docker-compose working without Cloud SQL at
    all — the same escape hatch every service already had, kept here so the
    four copies of it cannot drift either.
    """
    if os.environ.get("LOCAL_DATABASE_URL"):
        import pg8000.dbapi
        url = os.environ["LOCAL_DATABASE_URL"]
        host = url.split("@")[1].split(":")[0]
        return pg8000.dbapi.connect(
            user=local_user or "postgres", password="local", host=host,
            port=5432, database=db or "dma_insights")
    return _connector().connect(
        os.environ["DB_INSTANCE_CONNECTION_NAME"], driver,
        user=user or os.environ["DB_USER"],
        db=db or os.environ["DB_NAME"],
        enable_iam_auth=True, ip_type=ip_type)


def close() -> None:
    """Release the Connector and its background refresh.

    Called on shutdown. Never called per request — closing and rebuilding
    is the same Admin API cost as never caching at all.
    """
    with _LOCK:
        c = _STATE.pop("connector", None)
    if c is not None:
        c.close()


def is_cached() -> bool:
    """Whether a Connector is currently held. For tests and the doctor."""
    return _STATE.get("connector") is not None
