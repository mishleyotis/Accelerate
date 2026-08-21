"""The ops endpoints over real HTTP, because the audience is decided there.

WHY THIS FILE EXISTS AT THE HTTP LAYER. `test_cadence` already proves
`refresh_queue(cur, audience="customer")` raises 403. That is the function's
contract, and it was never the thing that broke. What broke was the step
BEFORE it: the endpoint's default-deny, where an OMITTED `audience` resolves to
`customer` (invariant 5) — so a caller that simply forgot the parameter got a
403 it had no reason to expect, and read it as a permissions problem.

That is not hypothetical. `plugins/dma-insights/scripts/run_gate.py` called
`GET /v1/ops/refresh-queue` bare. Every call 403'd, the refresh queue was never
consulted, and the gate skipped every serving client — including clients a
human had explicitly asked to refresh. The request was recorded, the queue
named it, and nothing ever produced it. It took a claim audit to notice,
because a queue that is never read looks exactly like a queue that is empty.

No test could have caught that from inside the function, and no test in
`apps/api/tests` went through HTTP at all. So this one does: it drives the real
ASGI app with a fake connection, and pins the three answers a caller can get.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

pytest.importorskip("httpx", reason="fastapi.testclient needs httpx")
from fastapi.testclient import TestClient                      # noqa: E402

from dma_api import main                                       # noqa: E402


class _Conn:
    """Enough of a connection to reach the audience check and no further.

    Records every statement, so the 403 path can be asserted to touch no SQL —
    a default-deny that queries first is a default-deny that leaks timing and
    load to an unauthenticated audience.
    """

    def __init__(self):
        self.statements = []

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.statements.append(sql)
        self._out = []

    def fetchall(self):
        return self._out

    def fetchone(self):
        # The undatable-clients count. 0 is a real answer here: no serving
        # client is missing a due date in this fixture.
        return (0,)

    def close(self):
        pass


@pytest.fixture()
def conn(monkeypatch):
    c = _Conn()
    monkeypatch.setattr(main, "_connect", lambda: c)
    return c


@pytest.fixture()
def client():
    return TestClient(main.app)


# ── the default-deny, which is the bug that happened ──


def test_the_refresh_queue_403s_when_the_audience_is_omitted(client, conn):
    """The exact call run_gate made. It is a 403, it is CORRECT, and it reads
    like a broken permission — which is why the caller has to be explicit."""
    r = client.get("/v1/ops/refresh-queue")
    assert r.status_code == 403
    assert r.json()["error"] == "audience_forbidden"
    assert conn.statements == [], "default-deny must refuse before it queries"


def test_the_refresh_queue_403s_for_the_customer_audience(client, conn):
    r = client.get("/v1/ops/refresh-queue", params={"audience": "customer"})
    assert r.status_code == 403
    assert r.json()["error"] == "audience_forbidden"


def test_an_unknown_audience_denies_rather_than_falling_back(client, conn):
    """`normalise_audience` resolves anything it does not recognise DOWN to
    customer, never up to internal. A typo must not open the queue."""
    r = client.get("/v1/ops/refresh-queue", params={"audience": "intrenal"})
    assert r.status_code == 403


def test_the_refresh_queue_serves_the_internal_audience(client, conn):
    """The half that proves the 403s above are about the audience and not
    about the endpoint being broken."""
    r = client.get("/v1/ops/refresh-queue", params={"audience": "internal"})
    assert r.status_code == 200
    body = r.json()
    assert "requested" in body and "due" in body, (
        "the two lists are deliberately unmerged and both must be present")
    assert conn.statements, "the internal path does read"


# ── the caller that got it wrong ──


def test_run_gate_asks_for_the_internal_audience():
    """The gate is the caller that 403'd silently for the life of the queue.

    Asserted over the source rather than by mocking `api_get`, because the
    existing unit tests DO mock it — with a lambda that ignores the path — and
    passed throughout. A mock that discards the argument cannot see an argument
    that is missing.
    """
    src = (ROOT / "plugins" / "dma-insights" / "scripts"
           / "run_gate.py").read_text(encoding="utf-8")
    assert "/v1/ops/refresh-queue?audience=internal" in src
    assert 'api_get("/v1/ops/refresh-queue")' not in src
