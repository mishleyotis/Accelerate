"""Brief §6 limits, enforced: the bucket never exceeds its rate, the
breaker backs off exponentially and honours Retry-After, identical in-flight
calls coalesce. All on a fake clock; no network, no real sleep."""
from __future__ import annotations

import asyncio

import pytest

from evidence_engine import ratelimit
from evidence_engine.ratelimit import CircuitBreaker, Coalescer, PerKeyBuckets, TokenBucket


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s

    async def sleep(self, s: float) -> None:
        self.t += s


@pytest.fixture(autouse=True)
def _reset_registry():
    ratelimit.reset()
    yield
    ratelimit.reset()


# ── token bucket ───────────────────────────────────────────────────────────

def test_bucket_never_exceeds_rate_100_acquires_at_8_per_second():
    clock = FakeClock()
    bucket = TokenBucket(8.0, 8, clock=clock, sleep=clock.sleep)
    stamps: list[float] = []

    async def run():
        for _ in range(100):
            await bucket.acquire()
            stamps.append(clock())

    asyncio.run(run())
    assert len(stamps) == 100
    assert stamps[-1] - stamps[0] >= 11.5
    # no one-second window holds more than 8 acquires (SEC measures per second)
    for i, t in enumerate(stamps):
        in_window = sum(1 for u in stamps[i:] if u < t + 1.0)
        assert in_window <= 8, f"{in_window} acquires in the second starting at {t}"
    assert bucket.acquired == 100


def test_bucket_try_acquire_is_non_blocking_and_refills():
    clock = FakeClock()
    bucket = TokenBucket(1.0, 1, clock=clock)
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False
    clock.advance(0.5)
    assert bucket.try_acquire() is False
    clock.advance(0.5)
    assert bucket.try_acquire() is True
    assert bucket.available == 0


def test_bucket_rejects_bad_parameters():
    with pytest.raises(ValueError):
        TokenBucket(0, 1)
    with pytest.raises(ValueError):
        TokenBucket(1, 0)


def test_per_key_buckets_are_lazy_and_case_insensitive():
    clock = FakeClock()
    seen: list[str] = []

    def factory(key: str):
        seen.append(key)
        return (1.0, 1)

    buckets = PerKeyBuckets(factory, clock=clock, sleep=clock.sleep)
    a = buckets.get("Example-FCU.test")
    b = buckets.get("example-fcu.test")
    assert a is b
    assert seen == ["example-fcu.test"]
    assert "example-fcu.test" in buckets and buckets.keys() == ["example-fcu.test"]


# ── circuit breaker ────────────────────────────────────────────────────────

def test_breaker_opens_on_429_and_honours_retry_after():
    clock = FakeClock(100.0)
    br = CircuitBreaker("searxng", min_s=30, max_s=600, clock=clock)
    assert br.state == "closed" and br.allow()
    assert br.record_failure("429", retry_after=90) is True
    assert br.state == "open"
    assert br.allow() is False
    assert br.snapshot()["retry_in_s"] == 90.0        # max(Retry-After 90, backoff 30)
    clock.advance(89)
    assert br.allow() is False
    clock.advance(1)
    assert br.state == "half_open"
    assert br.allow() is True                           # exactly one probe
    assert br.allow() is False
    br.record_success()
    assert br.state == "closed" and br.allow()
    assert br.snapshot()["backoff_s"] == 0.0


def test_breaker_half_opens_after_backoff_and_doubles_to_the_cap():
    clock = FakeClock()
    br = CircuitBreaker("parallel", min_s=30, max_s=600, clock=clock)
    expected = [30, 60, 120, 240, 480, 600, 600]
    for backoff in expected:
        br.record_failure("5xx")
        snap = br.snapshot()
        assert snap["state"] == "open" and snap["backoff_s"] == backoff
        clock.advance(backoff - 1)
        assert br.allow() is False
        clock.advance(1)
        assert br.allow() is True                       # the probe
    br.record_success()
    assert br.state == "closed"
    br.record_failure("captcha")
    assert br.snapshot()["backoff_s"] == 30            # reset after a close


def test_breaker_retry_after_is_max_of_header_and_backoff():
    clock = FakeClock()
    br = CircuitBreaker("sec", min_s=30, max_s=600, clock=clock)
    br.record_failure("429", retry_after=5)
    assert br.snapshot()["retry_in_s"] == 30.0         # backoff wins over a short Retry-After
    clock.advance(30)
    assert br.allow()
    br.record_failure("429", retry_after=1000)
    assert br.snapshot()["retry_in_s"] == 1000.0       # the header wins over 60


def test_breaker_403_streak_rule_three_consecutive():
    clock = FakeClock()
    br = CircuitBreaker("example-fcu.test", min_s=30, max_s=600, clock=clock)
    assert br.record_failure("403") is False
    assert br.record_failure("403") is False
    assert br.state == "closed"
    br.record_success()                                  # a success breaks the streak
    assert br.record_failure("403") is False
    assert br.record_failure("403") is False
    assert br.record_failure("403") is True
    assert br.state == "open" and br.snapshot()["last_kind"] == "403_streak"


def test_breaker_empty_streak_rule_five_consecutive():
    clock = FakeClock()
    br = CircuitBreaker("searxng", min_s=30, max_s=600, clock=clock)
    for _ in range(4):
        assert br.record_failure("empty") is False
    assert br.record_failure("empty") is True
    assert br.snapshot()["last_kind"] == "empty_streak"


def test_breaker_failure_while_open_does_not_double():
    clock = FakeClock()
    br = CircuitBreaker("x", min_s=30, max_s=600, clock=clock)
    br.record_failure("5xx")
    br.record_failure("5xx")                             # an in-flight request answered late
    assert br.snapshot()["backoff_s"] == 30


def test_breaker_rejects_unknown_kind():
    br = CircuitBreaker("x", clock=FakeClock())
    with pytest.raises(ValueError):
        br.record_failure("teapot")


def test_breaker_defaults_come_from_settings():
    br = CircuitBreaker("x", clock=FakeClock())
    assert br.min_s == 30.0 and br.max_s == 600.0


# ── coalescing ─────────────────────────────────────────────────────────────

def test_coalescer_three_concurrent_callers_one_upstream_call():
    co = Coalescer()
    calls = 0

    async def upstream():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"n": calls}

    async def run():
        results = await asyncio.gather(*(co.get("k", upstream) for _ in range(3)))
        assert all(r == {"n": 1} for r in results)
        assert calls == 1 and co.upstream_calls == 1 and co.joined == 2
        assert co.inflight() == 0
        # not a cache: a repeat after completion runs upstream again
        again = await co.get("k", upstream)
        assert again == {"n": 2} and calls == 2
        # a different key is its own call
        await co.get("other", upstream)
        assert calls == 3

    asyncio.run(run())


def test_coalescer_shares_the_exception_and_drops_the_key():
    co = Coalescer()

    async def boom():
        await asyncio.sleep(0)
        raise RuntimeError("upstream down")

    async def run():
        results = await asyncio.gather(*(co.get("k", boom) for _ in range(3)), return_exceptions=True)
        assert all(isinstance(r, RuntimeError) for r in results)
        assert co.upstream_calls == 1 and co.inflight() == 0

    asyncio.run(run())


# ── registry ───────────────────────────────────────────────────────────────

def test_limits_registry_matches_settings():
    lim = ratelimit.limits()
    assert set(lim.sources) == {"sec", "parallel", "searxng", "arxiv"}
    sec = lim.source("sec")
    assert sec.rate_per_s == 8.0 and sec.burst == 8
    assert lim.source("arxiv").rate_per_s == pytest.approx(1 / 3)
    host = lim.host("www.example-fcu.test")
    assert host.rate_per_s == 1.0 and host.burst == 1
    assert lim.host("WWW.EXAMPLE-FCU.TEST") is host
    with pytest.raises(KeyError):
        lim.source("bing")
    assert ratelimit.limits() is lim


def test_breakers_registry_and_health_snapshot():
    clock = FakeClock()
    ratelimit.configure(clock=clock, sleep=clock.sleep)
    br = ratelimit.breakers().get("searxng")
    assert br.state == "closed"
    br.record_failure("captcha")
    h = ratelimit.health()
    assert h["open"] == ["searxng"]
    assert h["breakers"]["searxng"]["last_kind"] == "captcha"
    assert "sec" in h["limits"]["sources"]
    ratelimit.reset()
    assert ratelimit.breakers().get("searxng").state == "closed"


def test_archive_hosts_take_the_slower_lane():
    RL.reset()
    try:
        lim = RL.limits()
        assert lim.host("web.archive.org").rate_per_s == 0.5 == lim.host("archive.org").rate_per_s
        assert lim.host("example-fcu.test").rate_per_s == 1.0
    finally:
        RL.reset()
