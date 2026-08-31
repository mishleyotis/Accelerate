"""One Cloud SQL Connector per process, not one per tool call.

WHAT IT COST. Measured 2026-08-31, from a producer pushing a 1.5 MB heatmap
as ~53 serial parts:

    Error executing tool open_payload: 429, message='Too Many Requests',
    url='https://sqladmin.googleapis.com/sql/v1beta4/projects/
         digital-maturity-assessor/instances/dmai-pg/connectSettings'

`connectSettings` is the Cloud SQL ADMIN API — the lookup the Python
Connector does to learn how to reach the instance. The database itself was
never rate-limiting anything, which is why the symptom reads as a database
problem and is not one.

`_conn()` read `Connector().connect(...)`: a NEW Connector every tool call.
Two faults, and the second is the one that bit hardest.

  1. A fresh Connector has an empty metadata cache, so its first connect
     calls the Admin API. One quota unit per tool call.
  2. It was never closed, so every discarded Connector kept a refresh alive
     that went on calling the same endpoint. The burn rate grew with the
     instance's UPTIME, not just its traffic — which is why `open_payload`,
     the very FIRST call of the sequence, took the 429 before a single part
     had been sent.

The library is designed to be constructed once and reused; the cache exists
so N connections cost ONE metadata fetch.

WHY THE TESTS COUNT CONSTRUCTIONS. A test that grepped for the word
"singleton", or asserted the module has a `_CONNECTOR` attribute, would pass
against a module that still built one per call. So these substitute a
counting fake for the library's Connector and drive `_conn()` repeatedly. The
number of constructions is the property; everything else is decoration.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp import db                                        # noqa: E402

SERVER_SRC = (ROOT / "apps" / "mcp" / "server.py").read_text()


class _FakeConn:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeConnector:
    """Counts constructions. The number is the whole property under test."""
    constructed = 0
    kwargs_seen: list = []

    def __init__(self, **kw):
        type(self).constructed += 1
        type(self).kwargs_seen.append(kw)

    def connect(self, *a, **kw):
        return _FakeConn()

    def close(self):
        pass


@pytest.fixture()
def cloud(monkeypatch):
    """Force the Cloud SQL branch with a counting Connector in place of the
    real library — no Google credentials, no MCP SDK, no database, so this
    runs everywhere rather than skipping into a silent pass."""
    _FakeConnector.constructed = 0
    _FakeConnector.kwargs_seen = []
    monkeypatch.delenv("LOCAL_DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_INSTANCE_CONNECTION_NAME", "proj:region:inst")
    monkeypatch.setenv("DB_USER", "dmai-mcp@proj.iam")
    monkeypatch.setenv("DB_NAME", "dma_insights")
    monkeypatch.setattr(db, "_CONNECTOR_FACTORY", _FakeConnector)
    db.reset_connector()
    yield db
    db.reset_connector()


def test_fifty_three_calls_construct_one_connector(cloud):
    """THE DEFECT, at the shape that produced it: a 53-part upload."""
    for _ in range(53):
        with cloud.connect():
            pass
    assert _FakeConnector.constructed == 1, (
        f"{_FakeConnector.constructed} Connectors for 53 calls — each one is "
        f"an Admin API connectSettings request against a per-minute quota, "
        f"and each is left running a refresh that keeps making more")


def test_concurrent_first_calls_still_build_only_one(cloud):
    """Double-checked locking, or two threads racing the very first call each
    build one — the same defect, reached at low volume instead of high."""
    barrier = threading.Barrier(8)

    def go():
        barrier.wait()
        with cloud.connect():
            pass

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _FakeConnector.constructed == 1, (
        f"{_FakeConnector.constructed} Connectors from 8 concurrent first "
        f"calls — the None check is not repeated inside the lock")


def test_every_call_still_gets_its_own_socket(cloud):
    """The fix shares METADATA, not the connection. A shared socket across
    tool calls would be worse than the bug being fixed: `promote_run` holds
    SELECT … FOR UPDATE on its own transaction (invariant 3)."""
    seen = []
    for _ in range(3):
        with cloud.connect() as c:
            seen.append(id(c))
    assert len(set(seen)) == 3, "connections are being shared between calls"


def test_the_connection_is_closed_after_each_call(cloud):
    conns = []
    for _ in range(3):
        with cloud.connect() as c:
            conns.append(c)
    assert all(c.closed for c in conns), "a socket outlived its tool call"


def test_a_raising_body_still_closes_the_socket(cloud):
    """A tool that throws must not leak its connection; the leak is how a
    pool runs out under exactly the error conditions that need it most."""
    held = {}
    with pytest.raises(ValueError):
        with cloud.connect() as c:
            held["c"] = c
            raise ValueError("tool blew up")
    assert held["c"].closed


def test_it_is_built_for_a_serverless_refresh(cloud):
    """Cloud Run throttles CPU between requests, so the default background
    refresher can be starved, wake late, and stampede the same endpoint this
    fix exists to stop hammering."""
    with cloud.connect():
        pass
    assert _FakeConnector.kwargs_seen[0].get("refresh_strategy") == "lazy", (
        f"constructed with {_FakeConnector.kwargs_seen[0]!r}; on Cloud Run "
        f"the refresh has to be lazy")


def test_the_local_branch_needs_no_connector(cloud, monkeypatch):
    """A developer database must not reach for Google at all."""
    monkeypatch.setenv("LOCAL_DATABASE_URL",
                       "postgresql+pg8000://postgres:local@localhost:5432/x")
    try:
        with cloud.connect():
            pass
    except Exception:
        pass                      # no local server here; the point is below
    assert _FakeConnector.constructed == 0


def test_the_server_holds_no_second_connection_path():
    """One implementation. A second inline `Connector()` anywhere in
    server.py would be a second cache and a second quota burn, invisible to
    every test above."""
    assert "Connector(" not in SERVER_SRC, (
        "server.py constructs a Connector again — the factory lives in "
        "dma_mcp/db.py so it can be tested; a copy here cannot be")
    assert "_conn = db_mod.connect" in SERVER_SRC, (
        "server.py no longer delegates its connections to dma_mcp.db")
