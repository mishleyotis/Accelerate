"""Bounded-parallel, wall-clock-budgeted, self-healing executor for the
corpus Gemini enrichment sweeps (enrich_corpus, enrich_empty_surfaces).

WHY THIS EXISTS (2026-07-05 build post-mortem)
  Both sweeps were fully sequential — one Vertex stream at a time — and
  unbudgeted. On the first Gemini-hot regen (a52f723) each burned its
  entire 1500s DERIVE_STEP_TIMEOUT_SEC as a SIGKILLed soft step, then the
  explicit `enrich_corpus --surfaces all` warm step (which has no step
  timeout of its own) ran until Cloud Build's GLOBAL deadline killed the
  whole build ("ERROR: context deadline exceeded"). ~650 calls x ~10s
  sequential can never fit a 1500s window; the fix is structural, not a
  bigger timeout.

THE CONTRACT
  * Bounded parallelism — `concurrency` asyncio workers, each with its
    OWN AsyncSession; Vertex calls are drained in short-lived daemon
    threads (`vertexai`'s generate_content is blocking — task-level
    concurrency alone would serialize on the event loop).
  * Wall-clock budget — no new item starts after `budget_sec` elapses;
    in-flight items drain (bounded by `call_timeout_sec`), the sweep
    exits 0 with a `remaining` count. Combined with fingerprint
    cache-resume (a re-run fast-skips every already-synthesized item)
    successive invocations CONVERGE instead of redoing work: chain wave
    -> explicit warm step -> post-deploy refresh -> next deploy.
  * Per-call timeout — a wedged stream is abandoned (daemon thread),
    the worker slot is freed, the sweep continues.
  * Self-healing breakers — `breaker_threshold` CONSECUTIVE failures on
    one surface stop that surface only (quota storm, bad template);
    other surfaces keep going. Auth-class errors (no ADC, IAM deny,
    Vertex disabled) flip the GLOBAL cold flag: every remaining call is
    skipped instantly and honestly reported, exactly like the old
    sequential `vertex_cold` behavior.
  * Priority tiers — items run tier-ascending so a budget cut lands on
    the least-visible work (e.g. why_now before rank-4 platform_story).

ENV KNOBS (CLI flags override)
  DMA_ENRICH_BUDGET_SEC        wall-clock budget per sweep (default 1200
                               — sized UNDER the 1500s step timeout)
  DMA_ENRICH_CONCURRENCY       parallel workers (default 6)
  DMA_ENRICH_CALL_TIMEOUT_SEC  per-Vertex-call cap (default 120)
  DMA_ENRICH_BREAKER_THRESHOLD consecutive failures to trip a surface
                               breaker (default 4)

Pure scheduling/plumbing — validation, persistence and honesty gates
stay in the calling scripts. `tests/test_enrichment_runner.py` stress-
tests budget exhaustion, concurrency caps, breakers, cold-stop, call
timeouts and tier ordering with a fake Vertex client.
"""
from __future__ import annotations

import asyncio
import os
import queue as _queue
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.enrichment_triggers import Trigger, log_defect

__all__ = [
    "BreakerOpenError",
    "BudgetedEnrichmentRunner",
    "CallCeilingError",
    "ColdVertexError",
    "EnrichItem",
    "VertexGateway",
    "drain_stream_sync",
    "env_float",
    "env_int",
]


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


class ColdVertexError(RuntimeError):
    """Vertex is unreachable for auth/config reasons — nothing else this
    sweep will succeed, so every remaining call is skipped instantly."""


class BreakerOpenError(RuntimeError):
    """This surface tripped its consecutive-failure breaker."""


class CallCeilingError(RuntimeError):
    """--max-calls ceiling reached — no further Vertex spend allowed."""


# Auth/config failure signatures ⇒ GLOBAL cold (mirrors the sequential
# scripts' vertex_cold, but narrowed: a transient 500/timeout on ONE call
# no longer freezes the whole sweep — that's what breakers are for).
_COLD_MARKERS = (
    "vertex disabled",            # DMA_DISABLE_VERTEX guard
    "vertex_project_id unset",    # settings guard
    "not installed",              # aiplatform import failure
    "credential",                 # google.auth DefaultCredentialsError
    "unauthenticated",
    "permission",                 # IAM deny (roles/aiplatform.user missing)
    " 401 ",
    " 403 ",
    "metadata service",           # no metadata server (off-network)
)


def _is_cold_error(exc: BaseException) -> bool:
    s = f" {type(exc).__name__}: {exc} ".lower()
    return any(m in s for m in _COLD_MARKERS)


def drain_stream_sync(vertex_client: Any, call: Any,
                      *, timeout_sec: float) -> str:
    """Collect a full Vertex stream in an ABANDONABLE daemon thread.

    `vertexai`'s generate_content(stream=True) blocks; running it on the
    event loop would serialize every "concurrent" call. The daemon
    thread + bounded queue is the same wedge-proof pattern as
    insight_explainer._drain_stream_sync: on timeout the worker is
    abandoned (never joined — daemon ⇒ can't wedge interpreter exit)
    and the caller moves on.
    """
    q: _queue.Queue[tuple[str, Any]] = _queue.Queue(maxsize=1)

    def _run() -> None:
        try:
            async def _collect() -> str:
                chunks: list[str] = []
                async for ch in vertex_client.stream(call):
                    chunks.append(ch)
                return "".join(chunks)

            q.put(("ok", asyncio.run(_collect())))
        except BaseException as exc:
            q.put(("err", exc))

    t = threading.Thread(target=_run, daemon=True, name="enrich-stream")
    t.start()
    try:
        kind, val = q.get(timeout=timeout_sec)
    except _queue.Empty:
        raise TimeoutError(
            f"vertex call exceeded {timeout_sec:.0f}s — stream abandoned"
        ) from None
    if kind == "err":
        raise val
    return str(val)


class VertexGateway:
    """All Vertex spend goes through here: per-call timeout, per-surface
    breakers, the global cold flag and the --max-calls ceiling.

    Single-threaded use from the event loop (workers are asyncio tasks;
    only the stream drain leaves the loop), so plain ints/dicts are safe.
    """

    def __init__(self, vertex_client: Any, *,
                 call_timeout_sec: float | None = None,
                 max_calls: int | None = None,
                 breaker_threshold: int | None = None) -> None:
        self._client = vertex_client
        self.call_timeout_sec = (
            call_timeout_sec if call_timeout_sec is not None
            else env_float("DMA_ENRICH_CALL_TIMEOUT_SEC", 120.0))
        self.max_calls = max_calls
        self.breaker_threshold = (
            breaker_threshold if breaker_threshold is not None
            else env_int("DMA_ENRICH_BREAKER_THRESHOLD", 4))
        self.calls = 0
        self.cold = False
        self.cold_reason = ""
        self._consecutive_fails: dict[str, int] = {}
        self._tripped: set[str] = set()

    def breaker_open(self, surface: str) -> bool:
        return surface in self._tripped

    async def generate(self, surface: str, call: Any) -> str:
        """One budgeted Vertex call. Raises ColdVertexError /
        BreakerOpenError / CallCeilingError / TimeoutError / the
        underlying SDK error — callers count, never crash."""
        if self.cold:
            raise ColdVertexError(self.cold_reason or "vertex cold")
        if surface in self._tripped:
            raise BreakerOpenError(
                f"surface '{surface}' breaker open "
                f"({self.breaker_threshold} consecutive failures)")
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise CallCeilingError(f"max-calls ceiling ({self.max_calls})")
        self.calls += 1  # counted at dispatch: abandoned calls still spent
        try:
            text = await asyncio.to_thread(
                drain_stream_sync, self._client, call,
                timeout_sec=self.call_timeout_sec)
        except Exception as exc:
            if _is_cold_error(exc):
                self.cold = True
                self.cold_reason = f"{type(exc).__name__}: {exc}"
                raise ColdVertexError(self.cold_reason) from exc
            n = self._consecutive_fails.get(surface, 0) + 1
            self._consecutive_fails[surface] = n
            if n >= self.breaker_threshold:
                self._tripped.add(surface)
            raise
        self._consecutive_fails[surface] = 0
        return text


@dataclass
class EnrichItem:
    """One unit of enrichment work. `process(session, gateway)` does the
    WHOLE item — context build, cache check, Vertex call via
    `gateway.generate`, validation, persistence — and returns an outcome
    label ('hit' / 'synthesized' / 'validator_blocked' / ...) that the
    runner counts. tier: lower runs first (budget cuts hit high tiers)."""
    key: str
    surface: str
    process: Callable[[Any, VertexGateway], Awaitable[str]]
    tier: int = 0
    trigger: Any | None = None   # enrichment_triggers.Trigger — required by
                                 # the G1-G10 gate unless DMA_ENRICH_LEGACY=1


@dataclass
class RunnerResult:
    counts: dict[str, int] = field(default_factory=dict)
    remaining: int = 0
    elapsed_sec: float = 0.0
    budget_exhausted: bool = False

    def summary(self) -> str:
        parts = " ".join(f"{k}={v}" for k, v in sorted(self.counts.items()))
        tail = " BUDGET-EXHAUSTED (resumable — cache fast-skips done work)" \
            if self.budget_exhausted else ""
        return (f"{parts} remaining={self.remaining} "
                f"elapsed={self.elapsed_sec:.0f}s{tail}")


class BudgetedEnrichmentRunner:
    """Tier-ordered work queue drained by `concurrency` asyncio workers,
    each holding its own AsyncSession, under a wall-clock budget."""

    def __init__(self, *, session_maker: Any, gateway: VertexGateway,
                 budget_sec: float | None = None,
                 concurrency: int | None = None) -> None:
        self._maker = session_maker
        self.gateway = gateway
        self.budget_sec = (budget_sec if budget_sec is not None
                           else env_float("DMA_ENRICH_BUDGET_SEC", 1200.0))
        # When running INSIDE run_derive_chain, the chain SIGKILLs the
        # step at DERIVE_STEP_TIMEOUT_SEC — a budget at/over that cap
        # would die mid-flight instead of exiting 0 with counters (e.g.
        # post-deploy refresh runs the chain at the 300s default). Clamp
        # under the cap so the sweep ALWAYS ends on its own terms.
        step_cap = env_float("DERIVE_STEP_TIMEOUT_SEC", 0.0)
        if step_cap > 0 and self.budget_sec >= step_cap:
            self.budget_sec = max(60.0, step_cap - 100.0)
        self.concurrency = max(1, (
            concurrency if concurrency is not None
            else env_int("DMA_ENRICH_CONCURRENCY", 6)))

    async def run(self, items: list[EnrichItem],
                  *, verbose: bool = False) -> RunnerResult:
        t0 = time.monotonic()
        deadline = t0 + self.budget_sec
        # Stable tier sort: within a tier, submission order is preserved
        # (surface-major submission ⇒ broad coverage under budget cuts).
        work: deque[EnrichItem] = deque(sorted(items, key=lambda i: i.tier))
        counts: dict[str, int] = {}
        result = RunnerResult()

        def _bump(label: str) -> None:
            counts[label] = counts.get(label, 0) + 1

        async def _worker() -> None:
            async with self._maker() as session:
                while work:
                    if time.monotonic() >= deadline:
                        result.budget_exhausted = True
                        return
                    item = work.popleft()
                    if not isinstance(item.trigger, Trigger):
                        if os.environ.get("DMA_ENRICH_LEGACY") == "1":
                            log_defect(item.key, item.surface, legacy=True)
                        else:
                            _bump("defect_no_trigger")
                            log_defect(item.key, item.surface)
                            continue
                    try:
                        _bump(await item.process(session, gateway_ref))
                    except ColdVertexError:
                        _bump("vertex_cold")
                    except BreakerOpenError:
                        _bump("breaker_skipped")
                    except CallCeilingError:
                        _bump("ceiling_skipped")
                    except TimeoutError:
                        _bump("call_timeout")
                        if verbose:
                            print(f"  timeout {item.key}", flush=True)
                    except Exception as exc:
                        _bump("error")
                        if verbose:
                            print(f"  error {item.key}: "
                                  f"{type(exc).__name__}: {exc}", flush=True)
                        # Defensive: an item that raised mid-transaction
                        # must not poison the session for the next item.
                        try:
                            await session.rollback()
                        except Exception:
                            return  # session unusable — retire the worker

        gateway_ref = self.gateway
        workers = [asyncio.create_task(_worker())
                   for _ in range(self.concurrency)]
        await asyncio.gather(*workers)
        result.counts = counts
        result.remaining = len(work)
        result.elapsed_sec = time.monotonic() - t0
        return result
