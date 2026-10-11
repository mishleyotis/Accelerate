"""Politeness and self-protection for every outbound call the engine makes.

Why this module exists
----------------------
The engine talks to hosts that publish a fair-access rule (SEC EDGAR:
"current max request rate: 10 requests/second", DISCOVERY §4), to free
backends whose ceiling is unpublished and must be measured (Parallel
Search), to a SearXNG we run ourselves, and to a long tail of entity and
trade-press sites behind WAFs. The brief's section 6 fixes the limits the
engine must hold — a global 8 req/s on SEC (0.8 × the published ceiling),
1 req/s per fetched host, a per-source Parallel/SearXNG/arXiv rate — and
`config.Settings` carries the numbers ("limits (Section 6 of the brief)").
This module is the one place those numbers are ENFORCED, so no fetcher or
search client has its own sleep loop.

The three rules
---------------
1. **Rate** (`TokenBucket`): a bucket of `burst` tokens; a token taken
   returns `burst / rate_per_s` seconds later. That makes two guarantees at
   once: the sustained rate never exceeds `rate_per_s`, and no window of
   `burst / rate_per_s` seconds ever holds more than `burst` calls. For the
   SEC bucket (8/s, burst 8) the second guarantee is the one SEC measures:
   never more than 8 calls in any one second, the initial burst included —
   a classic refill-at-rate bucket would let the first second carry
   burst + rate = 16. `PerKeyBuckets` lazily keys buckets by host or source.
2. **Breaker** (`CircuitBreaker`): a source that answers 429, a captcha,
   three 403s in a row, five empty results in a row, or a 5xx is left alone
   for an exponential backoff — `settings.breaker_min_s` (30 s) doubling to
   `settings.breaker_max_s` (600 s) — or for its own `Retry-After` when that
   is longer. After the backoff ONE probe is allowed (half-open); a success
   closes and resets, a failure re-opens with the backoff doubled. The
   fetcher turns an open breaker into `breaker_open:<host>` without a
   request, and the search layer reroutes (`via: rerouted_from:<source>`).
3. **Coalescing** (`Coalescer`): identical in-flight calls (same cache
   key) share one upstream call — ten collectors asking for the same page
   in the same second cost the host one request. It does not cache; the
   store does.

Everything is injectable for tests: the clock (monotonic seconds) and the
sleep coroutine, so a hundred simulated acquires run in milliseconds and
deterministically. No network, no model, no disk.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .config import settings

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]

#: Failure kinds a breaker opens on (brief §6). `403` and `empty` are the
#: raw observations; they open only as the streaks `403_streak` (3 in a
#: row) and `empty_streak` (5 in a row).
FAILURE_KINDS = frozenset({"429", "captcha", "403_streak", "empty_streak", "5xx", "timeout_streak"})
RAW_KINDS = frozenset({"403", "empty", "timeout"})
STREAK_403 = 3
STREAK_EMPTY = 5
#: Measured 2026-10-10 (golden-set run 1): one own-domain host timed out on
#: every URL, each costing the full timeout, and a brief spent 70-170 s on
#: it. The second timeout opens the host for the backoff window so the rest
#: of the brief falls straight to the Wayback snapshot.
STREAK_TIMEOUT = 2

STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


# ── token bucket ───────────────────────────────────────────────────────────

class TokenBucket:
    """`burst` tokens; each token taken comes back `burst / rate_per_s`
    seconds later (a sliding window of `burst` calls).

    `acquire()` waits (via the injected `sleep`) until a token is free and
    then takes it; callers are served in arrival order because the wait
    happens under the lock. `try_acquire()` is the non-blocking form for
    synchronous callers and health checks.
    """

    def __init__(self, rate_per_s: float, burst: int = 1, *,
                 clock: Clock | None = None, sleep: Sleep | None = None,
                 name: str = "") -> None:
        if rate_per_s <= 0:
            raise ValueError("rate_per_s must be positive")
        if burst < 1:
            raise ValueError("burst must be at least 1")
        self.name = name
        self.rate_per_s = float(rate_per_s)
        self.burst = int(burst)
        #: seconds a taken token is out of the bucket
        self.window_s = self.burst / self.rate_per_s
        self._clock: Clock = clock or time.monotonic
        self._sleep: Sleep = sleep or asyncio.sleep
        self._taken: deque[float] = deque()      # timestamps of tokens out
        self._lock: asyncio.Lock | None = None
        self.acquired = 0                         # for tests and health

    # internal -----------------------------------------------------------
    def _expire(self, now: float) -> None:
        while self._taken and now - self._taken[0] >= self.window_s:
            self._taken.popleft()

    def _wait_needed(self, now: float) -> float:
        self._expire(now)
        if len(self._taken) < self.burst:
            return 0.0
        return self._taken[0] + self.window_s - now

    def _take(self, now: float) -> None:
        self._taken.append(now)
        self.acquired += 1

    # public -------------------------------------------------------------
    def try_acquire(self) -> bool:
        """Take a token now if one is free; never waits."""
        now = self._clock()
        if self._wait_needed(now) > 0:
            return False
        self._take(now)
        return True

    async def acquire(self) -> float:
        """Wait for a token, take it, and return the seconds waited."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            waited = 0.0
            while True:
                now = self._clock()
                wait = self._wait_needed(now)
                if wait <= 0:
                    self._take(now)
                    return waited
                await self._sleep(wait)
                waited += wait

    @property
    def available(self) -> int:
        self._expire(self._clock())
        return self.burst - len(self._taken)

    def snapshot(self) -> dict[str, Any]:
        return {"name": self.name, "rate_per_s": self.rate_per_s, "burst": self.burst,
                "available": self.available, "acquired": self.acquired}


class PerKeyBuckets:
    """Buckets keyed by host or source name, created on first use from a
    `(rate_per_s, burst)` factory (a callable of the key, so a host-specific
    override can live in one place)."""

    def __init__(self, factory: Callable[[str], tuple[float, int]], *,
                 clock: Clock | None = None, sleep: Sleep | None = None) -> None:
        self._factory = factory
        self._clock = clock
        self._sleep = sleep
        self._buckets: dict[str, TokenBucket] = {}

    def get(self, key: str) -> TokenBucket:
        key = (key or "").lower()
        b = self._buckets.get(key)
        if b is None:
            rate, burst = self._factory(key)
            b = TokenBucket(rate, burst, clock=self._clock, sleep=self._sleep, name=key)
            self._buckets[key] = b
        return b

    def __contains__(self, key: str) -> bool:
        return (key or "").lower() in self._buckets

    def keys(self) -> list[str]:
        return sorted(self._buckets)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {k: b.snapshot() for k, b in sorted(self._buckets.items())}


# ── circuit breaker ────────────────────────────────────────────────────────

class CircuitBreaker:
    """One per source or host. See the module docstring, rule 2.

    `allow()` is the gate every call passes; `record_success()` /
    `record_failure(kind, retry_after=)` are what the caller reports after.
    `snapshot()` is what provenance and the health log carry.
    """

    def __init__(self, name: str, *, min_s: float | None = None,
                 max_s: float | None = None, clock: Clock | None = None) -> None:
        s = settings()
        self.name = name
        self.min_s = float(min_s if min_s is not None else s.breaker_min_s)
        self.max_s = float(max_s if max_s is not None else s.breaker_max_s)
        self._clock: Clock = clock or time.monotonic
        self._state = STATE_CLOSED
        self._backoff_s = 0.0          # the backoff the current open period used
        self._open_until = 0.0
        self._probe_out = False        # a half-open probe has been handed out
        self._streak_403 = 0
        self._streak_empty = 0
        self._streak_timeout = 0
        self._failures = 0             # opens, lifetime
        self._last_kind: str | None = None
        self._last_retry_after: float | None = None
        self._last_failure_at: float | None = None
        self._opened_at: float | None = None

    # state --------------------------------------------------------------
    @property
    def state(self) -> str:
        if self._state == STATE_OPEN and self._clock() >= self._open_until:
            return STATE_HALF_OPEN
        return self._state

    @property
    def retry_in_s(self) -> float:
        """Seconds until a probe is allowed; 0 when closed or half-open."""
        if self._state != STATE_OPEN:
            return 0.0
        return max(0.0, self._open_until - self._clock())

    def allow(self) -> bool:
        """Closed: yes. Open: no until the backoff has elapsed, then exactly
        one probe (half-open); further callers wait for the probe's verdict."""
        if self._state == STATE_CLOSED:
            return True
        now = self._clock()
        if self._state == STATE_OPEN and now >= self._open_until:
            self._state = STATE_HALF_OPEN
            self._probe_out = False
        if self._state == STATE_HALF_OPEN:
            if self._probe_out:
                return False
            self._probe_out = True
            return True
        return False

    def record_success(self) -> None:
        self._state = STATE_CLOSED
        self._backoff_s = 0.0
        self._open_until = 0.0
        self._probe_out = False
        self._streak_403 = 0
        self._streak_empty = 0
        self._streak_timeout = 0
        self._last_retry_after = None

    def record_failure(self, kind: str, retry_after: float | None = None) -> bool:
        """Report a failure. Returns True when the breaker is now open.

        `403` and `empty` are counted as streaks and open the breaker only
        at `STREAK_403` / `STREAK_EMPTY` consecutive observations; the other
        kinds open it at once. `retry_after` (seconds, from the host's
        header) is honoured as `max(retry_after, backoff)`.
        """
        if kind == "403":
            self._streak_403 += 1
            if self._streak_403 < STREAK_403:
                return self.state == STATE_OPEN
            kind = "403_streak"
        elif kind == "empty":
            self._streak_empty += 1
            if self._streak_empty < STREAK_EMPTY:
                return self.state == STATE_OPEN
            kind = "empty_streak"
        elif kind == "timeout":
            self._streak_timeout += 1
            if self._streak_timeout < STREAK_TIMEOUT:
                return self.state == STATE_OPEN
            kind = "timeout_streak"
        if kind not in FAILURE_KINDS:
            raise ValueError(f"unknown failure kind {kind!r}; one of {sorted(FAILURE_KINDS | RAW_KINDS)}")

        now = self._clock()
        self._last_kind = kind
        self._last_failure_at = now
        self._last_retry_after = retry_after
        ra = float(retry_after) if retry_after else 0.0

        if self._state == STATE_OPEN and now < self._open_until:
            # a request that was already in flight when we opened: extend for
            # a longer Retry-After, never double (only a failed probe doubles)
            self._open_until = max(self._open_until, now + max(ra, self._backoff_s))
            return True

        if self._state == STATE_HALF_OPEN or (self._state == STATE_OPEN and self._backoff_s):
            # the probe failed: double, capped
            self._backoff_s = min(self._backoff_s * 2 or self.min_s, self.max_s)
        else:
            self._backoff_s = self.min_s
        wait = max(ra, self._backoff_s)
        self._state = STATE_OPEN
        self._open_until = now + wait
        self._opened_at = now
        self._probe_out = False
        self._failures += 1
        return True

    def snapshot(self) -> dict[str, Any]:
        now = self._clock()
        return {
            "name": self.name,
            "state": self.state,
            "backoff_s": self._backoff_s,
            "retry_in_s": round(max(0.0, self._open_until - now), 3) if self._state == STATE_OPEN else 0.0,
            "last_kind": self._last_kind,
            "last_retry_after": self._last_retry_after,
            "opens": self._failures,
            "streak_403": self._streak_403,
            "streak_empty": self._streak_empty,
            "streak_timeout": self._streak_timeout,
            "seconds_since_failure": (round(now - self._last_failure_at, 3)
                                      if self._last_failure_at is not None else None),
        }


class PerKeyBreakers:
    """Breakers keyed by source or host, created closed on first use."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, key: str) -> CircuitBreaker:
        key = (key or "").lower()
        b = self._breakers.get(key)
        if b is None:
            b = CircuitBreaker(key, clock=self._clock)
            self._breakers[key] = b
        return b

    def __contains__(self, key: str) -> bool:
        return (key or "").lower() in self._breakers

    def keys(self) -> list[str]:
        return sorted(self._breakers)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {k: b.snapshot() for k, b in sorted(self._breakers.items())}

    def open_sources(self) -> list[str]:
        return [k for k, b in sorted(self._breakers.items()) if b.state != STATE_CLOSED]


# ── request coalescing ─────────────────────────────────────────────────────

class Coalescer:
    """Identical in-flight keys share one upstream call.

    `await coalescer.get(key, factory)`: the first caller for `key` runs
    `factory()` (a coroutine function); concurrent callers with the same key
    await the same future and receive the same result (or the same
    exception). The key is dropped as soon as the call completes — this is
    coalescing, not caching: a later caller runs upstream again.
    """

    def __init__(self) -> None:
        self._inflight: dict[Any, asyncio.Future] = {}
        self.upstream_calls = 0
        self.joined = 0

    def inflight(self) -> int:
        return len(self._inflight)

    async def get(self, key: Any, factory: Callable[[], Awaitable[Any]]) -> Any:
        fut = self._inflight.get(key)
        if fut is not None:
            self.joined += 1
            return await asyncio.shield(fut)
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        # The leader re-raises to its own caller; when no waiter joined, the
        # shared future's exception would otherwise be "never retrieved" and
        # logged at garbage collection. Mark it retrieved.
        fut.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        self._inflight[key] = fut
        self.upstream_calls += 1
        try:
            result = await factory()
        except asyncio.CancelledError:
            if not fut.done():
                fut.cancel()
            raise
        except BaseException as exc:  # noqa: BLE001 — propagate to every waiter
            if not fut.done():
                fut.set_exception(exc)
            raise
        else:
            if not fut.done():
                fut.set_result(result)
            return result
        finally:
            self._inflight.pop(key, None)


# ── registry ───────────────────────────────────────────────────────────────

#: Burst per named source (the rate comes from settings).
SOURCE_BURST = {"sec": 8, "parallel": 2, "searxng": 4, "arxiv": 1}
HOST_BURST = 1


@dataclass
class Limits:
    """The configured buckets: `sources[name]` for the named backends and
    `hosts.get(host)` for every fetched host (brief §6)."""
    sources: dict[str, TokenBucket]
    hosts: PerKeyBuckets

    def source(self, name: str) -> TokenBucket:
        try:
            return self.sources[name]
        except KeyError:
            raise KeyError(f"no rate limit configured for source {name!r}; "
                           f"one of {sorted(self.sources)}") from None

    def host(self, host: str) -> TokenBucket:
        return self.hosts.get(host)

    def snapshot(self) -> dict[str, Any]:
        return {"sources": {k: b.snapshot() for k, b in sorted(self.sources.items())},
                "hosts": self.hosts.snapshot()}


@dataclass
class _Registry:
    clock: Clock | None = None
    sleep: Sleep | None = None
    limits: Limits | None = None
    breakers: PerKeyBreakers | None = None
    coalescer: Coalescer = field(default_factory=Coalescer)


_REG = _Registry()


def _source_rates() -> dict[str, float]:
    s = settings()
    return {"sec": s.sec_rps, "parallel": s.parallel_rps,
            "searxng": s.searxng_rps, "arxiv": s.arxiv_rps}


def configure(*, clock: Clock | None = None, sleep: Sleep | None = None) -> None:
    """Tests: install a fake clock/sleep for every bucket and breaker the
    registry creates from now on (call `reset()` first to drop old ones)."""
    _REG.clock = clock
    _REG.sleep = sleep
    _REG.limits = None
    _REG.breakers = None


def _is_archive_host(host: str) -> bool:
    h = (host or "").lower()
    return h == "archive.org" or h.endswith(".archive.org")


def limits() -> Limits:
    """The process-wide buckets, built once from settings."""
    if _REG.limits is None:
        s = settings()
        sources = {name: TokenBucket(rate, SOURCE_BURST[name], clock=_REG.clock,
                                     sleep=_REG.sleep, name=name)
                   for name, rate in _source_rates().items()}
        hosts = PerKeyBuckets(lambda host: ((s.archive_rps if _is_archive_host(host) else s.host_rps), HOST_BURST),
                              clock=_REG.clock, sleep=_REG.sleep)
        _REG.limits = Limits(sources=sources, hosts=hosts)
    return _REG.limits


def breakers() -> PerKeyBreakers:
    """The process-wide breakers, one per source or host on first use."""
    if _REG.breakers is None:
        _REG.breakers = PerKeyBreakers(clock=_REG.clock)
    return _REG.breakers


def coalescer() -> Coalescer:
    return _REG.coalescer


def reset() -> None:
    """Tests: drop every bucket, breaker and in-flight key, and the clock."""
    global _REG
    _REG = _Registry()


def health() -> dict[str, Any]:
    """One dict for `/health` and the store's `source_health.jsonl`."""
    return {"limits": limits().snapshot(), "breakers": breakers().snapshot(),
            "open": breakers().open_sources(),
            "coalescer": {"inflight": _REG.coalescer.inflight(),
                          "upstream_calls": _REG.coalescer.upstream_calls,
                          "joined": _REG.coalescer.joined}}
