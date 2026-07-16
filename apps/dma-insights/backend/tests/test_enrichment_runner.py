"""Stress tests for services.enrichment_runner — the bounded-parallel,
wall-clock-budgeted, self-healing executor behind enrich_corpus and
enrich_empty_surfaces.

Every failure mode from the 2026-07-05 a52f723 build post-mortem is
pinned here with a fake Vertex client:
  - budget exhaustion stops scheduling and exits CLEANLY (the sweep can
    never again consume a step timeout, let alone the build deadline);
  - concurrency actually happens (the old sweeps serialized on the
    event loop) and stays under the cap;
  - priority tiers dispatch lowest-first so a budget cut lands on the
    least visible work;
  - a wedged stream is abandoned (daemon thread) without freezing the
    worker pool;
  - auth-class errors flip the GLOBAL cold flag (one cheap failure per
    remaining item, zero further Vertex calls);
  - per-surface breakers trip after N consecutive failures without
    touching other surfaces;
  - the --max-calls ceiling halts spend but not accounting;
  - a 200-item mixed-outcome storm completes with every item accounted.
"""
from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager

import pytest

from app.services.enrichment_runner import (
    BreakerOpenError,
    BudgetedEnrichmentRunner,
    CallCeilingError,
    ColdVertexError,
    EnrichItem,
    VertexGateway,
    drain_stream_sync,
)
from app.services.enrichment_triggers import Trigger

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── fakes ────────────────────────────────────────────────────────────────


class FakeCall:
    """Stands in for GeminiCall — the gateway never introspects it."""

    def __init__(self, tag: str = "t"):
        self.tag = tag


class FakeVertex:
    """Scriptable stand-in for VertexClient.stream()."""

    def __init__(self, *, delay: float = 0.0, fail_with: Exception | None = None,
                 hang: bool = False):
        self.delay = delay
        self.fail_with = fail_with
        self.hang = hang
        self.streams_started = 0

    async def stream(self, call):
        self.streams_started += 1
        if self.hang:
            await asyncio.sleep(60)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_with is not None:
            raise self.fail_with
        yield f"out:{getattr(call, 'tag', '?')}"


def fake_maker():
    """Session factory — the runner only needs an async context manager
    with a rollback() coroutine."""

    class _Session:
        async def rollback(self):
            return None

    @asynccontextmanager
    async def _cm():
        yield _Session()

    return _cm


def make_items(n: int, process, *, surface: str = "s", tier: int = 0,
               tiers: list[int] | None = None) -> list[EnrichItem]:
    return [
        EnrichItem(key=f"{surface}:{i}", surface=surface,
                   trigger=Trigger.G8_NEW_RUN,
                   tier=(tiers[i] if tiers else tier), process=process)
        for i in range(n)
    ]


# ── drain_stream_sync: the abandonable blocking bridge ──────────────────


def test_drain_collects_full_stream():
    out = drain_stream_sync(FakeVertex(), FakeCall("a"), timeout_sec=5)
    assert out == "out:a"


def test_drain_timeout_abandons_daemon_worker():
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        drain_stream_sync(FakeVertex(hang=True), FakeCall(), timeout_sec=0.2)
    assert time.monotonic() - t0 < 2.0, "timeout must not wait for the stream"
    # The abandoned worker must be a daemon — a non-daemon thread would
    # wedge interpreter exit (the deepen_narrative post-mortem class).
    strays = [t for t in threading.enumerate()
              if t.name == "enrich-stream" and t.is_alive()]
    assert all(t.daemon for t in strays)


def test_drain_relays_worker_exception():
    with pytest.raises(ValueError, match="boom"):
        drain_stream_sync(FakeVertex(fail_with=ValueError("boom")),
                          FakeCall(), timeout_sec=5)


# ── VertexGateway: breakers, cold-stop, ceiling ──────────────────────────


async def test_gateway_generates_and_counts():
    gw = VertexGateway(FakeVertex(), call_timeout_sec=5)
    assert await gw.generate("s", FakeCall("x")) == "out:x"
    assert gw.calls == 1 and not gw.cold


async def test_gateway_cold_error_stops_all_future_calls():
    fake = FakeVertex(fail_with=RuntimeError(
        "vertex_project_id unset — using deterministic fallback"))
    gw = VertexGateway(fake, call_timeout_sec=5)
    with pytest.raises(ColdVertexError):
        await gw.generate("s", FakeCall())
    assert gw.cold
    # Subsequent calls short-circuit — the client is NEVER touched again.
    with pytest.raises(ColdVertexError):
        await gw.generate("s", FakeCall())
    assert fake.streams_started == 1


async def test_gateway_credential_error_is_cold():
    class DefaultCredentialsError(Exception):
        pass

    fake = FakeVertex(fail_with=DefaultCredentialsError(
        "Could not automatically determine credentials"))
    gw = VertexGateway(fake, call_timeout_sec=5)
    with pytest.raises(ColdVertexError):
        await gw.generate("s", FakeCall())
    assert gw.cold


async def test_gateway_breaker_trips_per_surface_only():
    fake = FakeVertex(fail_with=ValueError("schema drift"))
    gw = VertexGateway(fake, call_timeout_sec=5, breaker_threshold=3)
    for _ in range(3):
        with pytest.raises(ValueError):
            await gw.generate("bad_surface", FakeCall())
    assert gw.breaker_open("bad_surface")
    with pytest.raises(BreakerOpenError):
        await gw.generate("bad_surface", FakeCall())
    assert fake.streams_started == 3, "breaker must stop client calls"
    # Other surfaces are unaffected (transient 500s on one template must
    # not freeze the whole sweep — that was the old vertex_cold=True).
    assert not gw.breaker_open("good_surface")


async def test_gateway_success_resets_breaker_count():
    boom = FakeVertex(fail_with=ValueError("x"))
    ok = FakeVertex()

    gw = VertexGateway(boom, call_timeout_sec=5, breaker_threshold=3)
    for _ in range(2):
        with pytest.raises(ValueError):
            await gw.generate("s", FakeCall())
    gw._client = ok  # recovery
    await gw.generate("s", FakeCall())
    gw._client = boom
    for _ in range(2):
        with pytest.raises(ValueError):
            await gw.generate("s", FakeCall())
    assert not gw.breaker_open("s"), "consecutive count must reset on success"


async def test_gateway_max_calls_ceiling():
    fake = FakeVertex()
    gw = VertexGateway(fake, call_timeout_sec=5, max_calls=3)
    for _ in range(3):
        await gw.generate("s", FakeCall())
    with pytest.raises(CallCeilingError):
        await gw.generate("s", FakeCall())
    assert fake.streams_started == 3


async def test_gateway_call_timeout_frees_slot():
    gw = VertexGateway(FakeVertex(hang=True), call_timeout_sec=0.2)
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        await gw.generate("s", FakeCall())
    assert time.monotonic() - t0 < 2.0


# ── BudgetedEnrichmentRunner: scheduling, budget, accounting ─────────────


def _runner(gw=None, **kw) -> BudgetedEnrichmentRunner:
    return BudgetedEnrichmentRunner(
        session_maker=fake_maker(),
        gateway=gw or VertexGateway(FakeVertex(), call_timeout_sec=5),
        **kw)


async def test_all_items_complete_and_are_counted():
    async def proc(sess, gw):
        return "synthesized"

    res = await _runner(budget_sec=30, concurrency=4).run(
        make_items(25, proc))
    assert res.counts == {"synthesized": 25}
    assert res.remaining == 0 and not res.budget_exhausted


async def test_budget_exhaustion_stops_cleanly_with_remaining():
    async def slow(sess, gw):
        await asyncio.sleep(0.1)
        return "synthesized"

    t0 = time.monotonic()
    res = await _runner(budget_sec=0.35, concurrency=2).run(
        make_items(100, slow))
    elapsed = time.monotonic() - t0
    assert res.budget_exhausted
    assert res.remaining > 0, "most of the queue must be left over"
    assert res.counts.get("synthesized", 0) + res.remaining == 100
    assert elapsed < 3.0, "budget stop must not drain the whole queue"


async def test_concurrency_cap_respected_and_actually_used():
    gauge = {"now": 0, "max": 0}

    async def tracked(sess, gw):
        gauge["now"] += 1
        gauge["max"] = max(gauge["max"], gauge["now"])
        await asyncio.sleep(0.05)
        gauge["now"] -= 1
        return "synthesized"

    res = await _runner(budget_sec=30, concurrency=4).run(
        make_items(24, tracked))
    assert res.counts["synthesized"] == 24
    assert gauge["max"] <= 4, "cap breached"
    assert gauge["max"] >= 2, "no actual parallelism happened"


async def test_tier_priority_dispatch_order():
    started: list[str] = []

    async def proc(sess, gw):
        return "synthesized"

    items = []
    for i, tier in enumerate([3, 0, 2, 1, 0, 3, 1, 2]):
        async def _p(sess, gw, i=i, tier=tier):
            started.append(f"t{tier}")
            return "synthesized"
        items.append(EnrichItem(key=f"i{i}", surface="s", tier=tier,
                                trigger=Trigger.G8_NEW_RUN,
                                process=_p))
    await _runner(budget_sec=30, concurrency=1).run(items)
    assert started == sorted(started), f"tiers out of order: {started}"


async def test_cold_vertex_skips_remaining_fast():
    fake = FakeVertex(fail_with=RuntimeError(
        "vertex disabled via DMA_DISABLE_VERTEX — using deterministic fallback"))
    gw = VertexGateway(fake, call_timeout_sec=5)

    async def proc(sess, gateway):
        return await gateway.generate("s", FakeCall()) and "synthesized"

    t0 = time.monotonic()
    res = await _runner(gw, budget_sec=30, concurrency=4).run(
        make_items(50, proc))
    assert res.counts["vertex_cold"] == 50
    # In-flight workers may each probe once before the first cold error
    # lands, but the stop is global: never more probes than workers.
    assert fake.streams_started <= 4, "cold-stop must halt further probes"
    assert time.monotonic() - t0 < 5.0


async def test_item_exception_does_not_kill_worker():
    seen = {"n": 0}

    async def flaky(sess, gw):
        seen["n"] += 1
        if seen["n"] % 3 == 0:
            raise RuntimeError("item blew up")
        return "synthesized"

    res = await _runner(budget_sec=30, concurrency=2).run(
        make_items(30, flaky))
    assert res.counts["synthesized"] + res.counts["error"] == 30
    assert res.remaining == 0


async def test_mixed_outcome_storm_all_items_accounted():
    """200 items, 8 workers, randomized-by-index outcomes (success /
    failure / timeout / cache-hit) — the sweep must terminate with every
    item in exactly one bucket."""

    class RoutingVertex:
        """Hangs or answers based on the call's tag — safe under
        concurrent workers (no shared-state mutation)."""

        async def stream(self, call):
            if call.tag == "hang":
                await asyncio.sleep(60)
            yield "ok"

    gw = VertexGateway(RoutingVertex(), call_timeout_sec=0.15,
                       breaker_threshold=999)

    def make(i: int):
        async def _p(sess, gateway):
            m = i % 5
            if m == 0:
                return "hit"
            if m == 1:
                raise ValueError("validator refused")
            if m == 2:
                await gateway.generate("storm", FakeCall("hang"))
                return "synthesized"
            await gateway.generate("storm", FakeCall("ok"))
            return "synthesized"
        return _p

    items = [EnrichItem(key=f"i{i}", surface="storm", tier=0,
                        trigger=Trigger.G8_NEW_RUN,
                        process=make(i)) for i in range(200)]
    res = await BudgetedEnrichmentRunner(
        session_maker=fake_maker(), gateway=gw,
        budget_sec=60, concurrency=8).run(items)
    assert sum(res.counts.values()) == 200
    assert res.remaining == 0
    assert res.counts["hit"] == 40
    assert res.counts["error"] == 40          # the ValueError bucket
    assert res.counts["call_timeout"] == 40   # the wedged-stream bucket
    assert res.counts["synthesized"] == 80


async def test_summary_mentions_budget_exhaustion():
    async def slow(sess, gw):
        await asyncio.sleep(0.05)
        return "synthesized"

    res = await _runner(budget_sec=0.1, concurrency=1).run(
        make_items(50, slow))
    assert "BUDGET-EXHAUSTED" in res.summary()
    assert "remaining=" in res.summary()


async def test_budget_clamped_under_chain_step_timeout(monkeypatch):
    """Inside run_derive_chain the step is SIGKILLed at
    DERIVE_STEP_TIMEOUT_SEC — the runner must clamp its budget under
    that cap so the sweep exits 0 with counters instead of dying
    mid-flight (post-deploy refresh runs the chain at the 300s default)."""
    monkeypatch.setenv("DERIVE_STEP_TIMEOUT_SEC", "300")
    r = _runner(budget_sec=1200)
    assert r.budget_sec == 200.0
    # An explicit budget already under the cap is untouched.
    r2 = _runner(budget_sec=150)
    assert r2.budget_sec == 150.0
    monkeypatch.delenv("DERIVE_STEP_TIMEOUT_SEC")
    r3 = _runner(budget_sec=1200)
    assert r3.budget_sec == 1200.0
