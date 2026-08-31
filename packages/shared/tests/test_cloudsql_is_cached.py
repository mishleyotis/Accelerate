"""One Connector per process, or the Admin API says 429.

MEASURED 2026-08-31, from a live intake firing:

    Error executing tool get_client_state: 429, message='Too Many Requests',
    url='https://sqladmin.googleapis.com/sql/v1beta4/projects/
         digital-maturity-assessor/instances/dmai-pg/connectSettings'

Not the database refusing a query — the Cloud SQL ADMIN API refusing a
metadata lookup. `Connector()` fetches connectSettings when constructed;
`apps/mcp/server.py` constructed one inside a per-call context manager, so
every MCP tool call spent one Admin API request and dropped the Connector
without closing it. Three worker modules did the same. `apps/api` alone had
it right, and its own docstring had already warned why four copies is the
problem: "two places for `ip_type` or IAM auth to drift".
"""
import sys
import types
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHARED))
import cloudsql  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    cloudsql._STATE.clear()
    yield
    cloudsql._STATE.clear()


class _FakeConnector:
    made = 0
    #: Construction kwargs of the most recent one. The real Connector takes
    #: several (refresh_strategy among them), so a fake with a bare __init__
    #: fails on any of them and reads as a defect in the module rather than
    #: a gap in the double.
    last_kwargs: dict = {}

    def __init__(self, **kw):
        type(self).made += 1
        type(self).last_kwargs = kw
        self.closed = False

    def connect(self, *a, **k):
        return ("conn", a, k)

    def close(self):
        self.closed = True


def _patch(monkeypatch):
    _FakeConnector.made = 0
    mod = type(sys)("google.cloud.sql.connector")
    mod.Connector = _FakeConnector
    monkeypatch.setitem(sys.modules, "google.cloud.sql.connector", mod)
    monkeypatch.setenv("DB_INSTANCE_CONNECTION_NAME", "p:r:i")
    monkeypatch.setenv("DB_USER", "dmai-mcp@example.iam")
    monkeypatch.setenv("DB_NAME", "dma_insights")
    monkeypatch.delenv("LOCAL_DATABASE_URL", raising=False)


def test_many_connections_build_exactly_one_connector(monkeypatch):
    """THE WHOLE POINT. 50 connections used to be 50 Admin API requests."""
    _patch(monkeypatch)
    for _ in range(50):
        cloudsql.connect()
    assert _FakeConnector.made == 1


def test_the_connector_survives_between_calls(monkeypatch):
    _patch(monkeypatch)
    cloudsql.connect()
    assert cloudsql.is_cached()
    cloudsql.connect()
    assert _FakeConnector.made == 1


def test_iam_auth_and_private_ip_are_not_negotiable(monkeypatch):
    """The two settings db.py's docstring says drift when copied."""
    _patch(monkeypatch)
    _, _, kwargs = cloudsql.connect()
    assert kwargs["enable_iam_auth"] is True
    assert kwargs["ip_type"] == "PRIVATE"


def test_the_identity_is_the_callers_and_never_hardcoded(monkeypatch):
    """api runs as dmai-api, mcp as dmai-mcp, worker as dmai-worker — same
    code, different grants, enforced by the database."""
    _patch(monkeypatch)
    _, _, kwargs = cloudsql.connect(user="dmai-worker@example.iam")
    assert kwargs["user"] == "dmai-worker@example.iam"
    _, _, kwargs = cloudsql.connect()
    assert kwargs["user"] == "dmai-mcp@example.iam", "falls back to DB_USER"


def test_close_releases_it_and_a_later_call_rebuilds(monkeypatch):
    _patch(monkeypatch)
    cloudsql.connect()
    cloudsql.close()
    assert not cloudsql.is_cached()
    cloudsql.connect()
    assert _FakeConnector.made == 2, "close must release, not permanently kill"


def test_local_development_never_touches_cloud_sql(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setenv("LOCAL_DATABASE_URL",
                       "postgresql://u@localhost:5432/dma_insights")
    fake = type(sys)("pg8000.dbapi")
    seen = {}

    def _c(**kw):
        seen.update(kw)
        return "local"
    fake.connect = _c
    pkg = type(sys)("pg8000")
    pkg.dbapi = fake            # `import pg8000.dbapi` then `pg8000.dbapi.x`
    monkeypatch.setitem(sys.modules, "pg8000", pkg)
    monkeypatch.setitem(sys.modules, "pg8000.dbapi", fake)
    assert cloudsql.connect(local_user="dmai-mcp@example.iam") == "local"
    assert seen["user"] == "dmai-mcp@example.iam"
    assert _FakeConnector.made == 0, "no Admin API call in docker-compose"


def test_no_service_constructs_its_own_connector_any_more():
    """The regression that matters: this bug is one `Connector()` away from
    coming back, in any of four files."""
    import re
    root = SHARED.parents[1]

    # SOURCE ONLY — never what a build staged. `infra/deploy.sh` copies this
    # very module into apps/api/shared/ and apps/mcp/shared/ so each image
    # carries it, and those copies are gitignored build artifacts. An rglob
    # finds them and reports cloudsql.py itself as a service constructing its
    # own Connector, which is both false and confusing: measured the first
    # time anyone ran deploy.sh in a checkout that then ran this test.
    # `apps/<svc>/shared/` is staged FROM packages/shared — both of its
    # .gitignores say so on their first line — so nothing in it is service
    # code, whether or not a given file happens to be tracked. (They differ:
    # mcp ignores *.py, api ignores only *.json, so four staged modules are
    # committed under apps/api/shared. That asymmetry is a separate finding;
    # this scan is correct either way by excluding the directory itself.)
    files = [f for f in (root / "apps").rglob("*.py")
             if "shared" not in f.relative_to(root / "apps").parts]

    offenders = []
    for f in files:
        if "tests" in f.parts or f.name.startswith("test_"):
            continue
        if not f.is_file():
            continue
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if re.search(r"\bConnector\(\)", line.split("#")[0]):
                offenders.append(f"{f.relative_to(root)}:{i}")
    allowed = {"apps/api/dma_api/db.py"}
    offenders = [o for o in offenders if o.rsplit(":", 1)[0] not in allowed]
    assert not offenders, (
        f"a per-call Connector is back: {offenders}. Use "
        f"packages/shared/cloudsql.connect() — one per process.")


# ── two properties the first pass did not pin ────────────────────────────

def test_concurrent_first_calls_still_build_only_one(monkeypatch):
    """The lock has a re-check inside it. Without one, two threads racing the
    very FIRST call each construct a Connector and each spends a
    connectSettings request — the same defect this module exists to end,
    reached at low volume instead of high. A cold Cloud Run instance taking
    two requests at once is exactly that race, and it is the common shape at
    --min-instances=1 with --concurrency=80.
    """
    import threading
    built = []

    class _C:
        def __init__(self, **kw):
            built.append(kw)

        def connect(self, *a, **kw):
            return object()

        def close(self):
            pass

    fake = types.ModuleType("google.cloud.sql.connector")
    fake.Connector = _C
    monkeypatch.setitem(sys.modules, "google.cloud.sql.connector", fake)
    monkeypatch.delenv("LOCAL_DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_INSTANCE_CONNECTION_NAME", "p:r:i")
    monkeypatch.setenv("DB_USER", "svc@p.iam")
    monkeypatch.setenv("DB_NAME", "dma_insights")
    cloudsql.close()

    barrier = threading.Barrier(8)

    def go():
        barrier.wait()
        cloudsql.connect()

    ts = [threading.Thread(target=go) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(built) == 1, (
        f"{len(built)} Connectors from 8 concurrent first calls — the "
        f"membership check is not repeated inside the lock")
    cloudsql.close()


def test_the_refresh_is_lazy_because_cloud_run_throttles_cpu(monkeypatch):
    """`infra/deploy.sh` sets no --no-cpu-throttling, so between requests the
    instance gets close to no CPU. The default background refresh is an
    asyncio task on a ~55-minute timer, and a timer that only advances while
    a request is in flight wakes late, finds the metadata stale, and sends
    every starved instance to `connectSettings` at once — the same endpoint
    and the same 429 this module exists to make rare."""
    built = []

    class _C:
        def __init__(self, **kw):
            built.append(kw)

        def connect(self, *a, **kw):
            return object()

        def close(self):
            pass

    fake = types.ModuleType("google.cloud.sql.connector")
    fake.Connector = _C
    monkeypatch.setitem(sys.modules, "google.cloud.sql.connector", fake)
    monkeypatch.delenv("LOCAL_DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_INSTANCE_CONNECTION_NAME", "p:r:i")
    monkeypatch.setenv("DB_USER", "svc@p.iam")
    monkeypatch.setenv("DB_NAME", "dma_insights")
    cloudsql.close()
    cloudsql.connect()
    assert built[0].get("refresh_strategy") == "lazy", (
        f"constructed with {built[0]!r}; on Cloud Run the refresh has to be "
        f"lazy or it is scheduled on CPU the instance does not get")
    cloudsql.close()
