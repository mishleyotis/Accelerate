"""The first connection is opened at startup, not on a user's request.

MEASURED 2026-09-01 on dmai-api-00123-25m, the revision that fixed the
connector's refresh strategy. Its first four requests took 150s, 140s, 128s
and 99s, then settled to 0.4s. Every one returned 200 — nothing failed, the
browser simply span for two and a half minutes. `num_backends` on the
database was flat throughout, so the time was not a query: it was the first
connection being established on an instance whose CPU is throttled outside a
request.

`run.googleapis.com/startup-cpu-boost` was already true and did not help,
because boost covers container startup and the connection was first made on
the first request. Opening it in the lifespan moves the cost inside the
boosted window, before uvicorn accepts anything.

The three properties that matter are the three tests below: it happens
before serving, a failure does not stop the service, and it cannot hang the
container.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import main  # noqa: E402


class _Cursor:
    def __init__(self, log):
        self.log = log

    def execute(self, q):
        self.log.append(("execute", q))

    def fetchone(self):
        return (1,)


class _Conn:
    def __init__(self, log):
        self.log = log
        self.closed = False

    def cursor(self):
        return _Cursor(self.log)

    def close(self):
        self.closed = True
        self.log.append(("close",))


def test_the_connection_is_open_before_the_app_serves(monkeypatch):
    """THE POINT. Inside the lifespan — which is where uvicorn starts
    accepting — a connection has already been made, exercised and closed."""
    log, made = [], []

    def _fake():
        log.append(("connect",))
        c = _Conn(log)
        made.append(c)
        return c

    monkeypatch.setattr(main, "_connect", _fake)
    monkeypatch.setattr(main, "db_close", lambda: None)

    async def run():
        async with main._lifespan(main.app):
            assert ("connect",) in log, "no connection was opened at startup"
            assert ("execute", "SELECT 1") in log, "opened but never used"
            assert made[0].closed, "the warm-up leaked its connection"

    asyncio.run(run())


def test_a_failed_warm_up_still_starts_the_service(monkeypatch):
    """Never fatal. A database that refuses at startup must not turn a slow
    first request into a revision that never goes live — the routes still
    work and pay the cost once, which is exactly the old behaviour."""
    def _boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(main, "_connect", _boom)
    monkeypatch.setattr(main, "db_close", lambda: None)
    served = []

    async def run():
        async with main._lifespan(main.app):
            served.append(True)

    asyncio.run(run())
    assert served == [True], "a failed warm-up stopped the service starting"


def test_a_hanging_warm_up_cannot_hang_the_container(monkeypatch):
    """Bounded, for the same reason. This is the failure the whole day was
    made of — a connection attempt that never returns — so the warm-up is
    not allowed to reproduce it one layer earlier."""
    import time

    def _hang():
        time.sleep(3)                       # far past the bound set below
        raise AssertionError("unreachable")

    monkeypatch.setattr(main, "_connect", _hang)
    monkeypatch.setattr(main, "db_close", lambda: None)
    monkeypatch.setattr(main, "WARMUP_TIMEOUT_S", 0.2)
    served = []

    async def run():
        t0 = time.monotonic()
        async with main._lifespan(main.app):
            served.append(time.monotonic() - t0)

    asyncio.run(run())
    assert served and served[0] < 5, (
        f"startup waited {served[0]:.1f}s on a hanging warm-up; the bound "
        f"is meant to stop that")
