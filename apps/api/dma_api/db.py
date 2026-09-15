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

THE CONNECTOR IS NOT BUILT HERE ANY MORE, and the reason is an outage.

This module held `_POOL.setdefault("connector", Connector())` — one Connector
per process. `packages/shared/cloudsql.py` was written on 2026-08-31 to give
the other three services the same thing, and it cites this file by name as
the copy that "already had it right". One per process WAS right. The refresh
strategy was not, and nobody looked at it, because the file that got it wrong
was the file being held up as the example — the scan that enforces the rule
even carried `allowed = {"apps/api/dma_api/db.py"}`.

`Connector()` defaults to a BACKGROUND refresh: an asyncio timer on the
connector's own thread that re-fetches instance metadata and the ephemeral
certificate before they expire. `infra/deploy.sh` deploys dmai-api with
--min-instances=1 and no --no-cpu-throttling, so between requests the
instance is throttled to almost no CPU and that timer does not advance.

MEASURED 2026-09-01 in production, on dmai-api-00122-lnv: the service
answered normally at 15:08–15:13, idled, and from 16:31 every
database-backed route hung for the full 300-second Cloud Run request timeout
and returned 504 — /v1/directory, /v1/catalogue and /v1/ops/import-scans
alike — while /healthz, which touches nothing, answered in 0.4s and
`num_backends` on dma_insights sat at 0–2 the whole afternoon. The requests
never reached the database. They were blocked inside a refresh a throttled
instance could not finish, and the blocked threads never returned, so the
instance stayed dead and Cloud Run kept routing to it. The web BFF calls this
API server-side, so the browser saw an error on every page. dmai-mcp — same
VPC, same database, same instance, same CPU throttling — served normally
throughout, on the shared module's lazy strategy. dmai-worker, a Job with CPU
always allocated, connected fine at 16:30.

So: the shared module, which refreshes ON DEMAND when the cached metadata is
actually expired and needs no scheduler that a throttled instance cannot run.
Nothing else about the connection changes — same driver, same IAM auth, same
PRIVATE ip_type, same DB_USER-from-the-environment identity.
"""
from __future__ import annotations

# The staged-shared loader, repo first and image second, with the argument for
# that order in its own docstring. `redaction.py` reaches for it the same way;
# a second copy here would be the drift this module's own docstring warns
# about, one directory down.
from .evidence import _put_shared_on_path

_put_shared_on_path()

# Imported hard, never in a try. `infra/deploy.sh` treats a missing
# packages/shared/cloudsql.py as FATAL at stage time for the same reason: a
# service that silently falls back to building its own Connector is the
# outage above, arriving again with nothing in the logs to name it.
from cloudsql import close as _shared_close  # noqa: E402
from cloudsql import connect as _shared_connect  # noqa: E402


def connect():
    """A DBAPI connection as `DB_USER`, through the process-wide Connector.

    `LOCAL_DATABASE_URL` still keeps docker-compose off Cloud SQL entirely —
    that escape hatch moved into the shared module with everything else, so
    the four services cannot drift on it either.
    """
    return _shared_connect()


def close() -> None:
    """Release the Connector on shutdown. Never per request: closing and
    rebuilding costs exactly what never caching costs."""
    _shared_close()
