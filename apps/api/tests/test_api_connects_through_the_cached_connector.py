"""dmai-api's database connection, and the outage that proved it needed one.

MEASURED 2026-09-01 on dmai-api-00122-lnv. The service answered normally at
15:08-15:13, idled, and from 16:31 every database-backed route hung for the
full 300-second Cloud Run request timeout and returned 504 —
/v1/directory, /v1/catalogue and /v1/ops/import-scans alike — while
/healthz, which touches no database, answered in 0.4s and `num_backends` on
dma_insights sat at 0-2 all afternoon. The requests never reached the
database. dmai-mcp, on the same VPC and the same instance and equally
CPU-throttled, served throughout.

The difference was one keyword. `dma_api/db.py` built its own
`Connector()` — once per process, which is what the shared module was
written to give everyone else, so the scan in
packages/shared/tests/test_cloudsql_is_cached.py carried
`allowed = {"apps/api/dma_api/db.py"}` and never looked at it again. The
default refresh strategy is a background asyncio timer, and `deploy.sh`
sets no --no-cpu-throttling, so between requests the instance has no CPU to
advance it with.

These tests exist because nothing in the api suite touched db.py at all: it
had no import test and no behaviour test, so the module that opens every
connection this service makes was carried by the deploy alone.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

import cloudsql  # noqa: E402
from dma_api import db  # noqa: E402


class _FakeConnector:
    made = 0
    last_kwargs: dict = {}

    def __init__(self, **kw):
        type(self).made += 1
        type(self).last_kwargs = kw

    def connect(self, *a, **k):
        return ("conn", a, k)

    def close(self):
        pass


@pytest.fixture
def cloud(monkeypatch):
    cloudsql._STATE.clear()
    _FakeConnector.made = 0
    mod = type(sys)("google.cloud.sql.connector")
    mod.Connector = _FakeConnector
    monkeypatch.setitem(sys.modules, "google.cloud.sql.connector", mod)
    monkeypatch.setenv("DB_INSTANCE_CONNECTION_NAME", "p:r:i")
    monkeypatch.setenv("DB_USER", "dmai-api@example.iam")
    monkeypatch.setenv("DB_NAME", "dma_insights")
    monkeypatch.delenv("LOCAL_DATABASE_URL", raising=False)
    yield
    cloudsql._STATE.clear()


def test_db_module_imports_at_all():
    """The cheapest test in the file and the one that was missing.

    `ast.parse` proves syntax, not name resolution — a module-scope
    NameError is a runtime error that kills the container, and one took a
    deploy down on 2026-08-31. db.py now imports a staged shared module at
    module scope, so a staging path that stops resolving must fail here and
    not at the first request in production.
    """
    assert callable(db.connect) and callable(db.close)


def test_the_refresh_is_lazy_or_a_throttled_instance_hangs(cloud):
    """The 504s, in one assertion.

    A background refresh needs a scheduler. `infra/deploy.sh` deploys this
    service with --min-instances=1 and no --no-cpu-throttling, so between
    requests there is no CPU to be a scheduler with.
    """
    db.connect()
    assert _FakeConnector.last_kwargs.get("refresh_strategy") == "lazy"


def test_one_connector_serves_every_request(cloud):
    """Under NullPool behind the Cloud SQL pooler every checkout is a real
    new connection, so a per-connection Connector is one Cloud SQL Admin API
    request per checkout — the 429 on connectSettings measured 2026-08-31."""
    for _ in range(50):
        db.connect()
    assert _FakeConnector.made == 1


def test_the_identity_is_the_deployments_and_not_hardcoded(cloud):
    """Same code, different grants: api reads the serving tier as dmai-api,
    the refresh Job in this same image writes as dmai-worker."""
    _, _, kwargs = db.connect()
    assert kwargs["user"] == "dmai-api@example.iam"
    assert kwargs["enable_iam_auth"] is True
    assert kwargs["ip_type"] == "PRIVATE"
    assert kwargs["db"] == "dma_insights"


def test_close_releases_the_connector_on_shutdown(cloud):
    db.connect()
    assert cloudsql.is_cached()
    db.close()
    assert not cloudsql.is_cached()


def test_local_development_still_never_touches_cloud_sql(cloud, monkeypatch):
    """docker-compose parity: the escape hatch moved into the shared module
    with everything else, and it has to still be there."""
    monkeypatch.setenv("LOCAL_DATABASE_URL",
                       "postgresql://postgres:local@localhost:5432/dma_insights")
    seen = {}
    fake = type(sys)("pg8000.dbapi")

    def _c(**kw):
        seen.update(kw)
        return "local"
    fake.connect = _c
    pkg = type(sys)("pg8000")
    pkg.dbapi = fake
    monkeypatch.setitem(sys.modules, "pg8000", pkg)
    monkeypatch.setitem(sys.modules, "pg8000.dbapi", fake)
    assert db.connect() == "local"
    assert seen["user"] == "postgres"
    assert seen["database"] == "dma_insights"
    assert _FakeConnector.made == 0
