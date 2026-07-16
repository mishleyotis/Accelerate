"""D2 (scope 2): the Vertex insight-explainer connector + its integration
with deepen_narrative's `set_insight_explainer` hook.

No live Vertex/creds: a fake client streams a canned response. Verifies
the connector parses the 3 labelled fields, returns None on error, and
that deepen's `_compose_insight` adopts a clean Vertex triple but falls
back to the deterministic template when the response leaks jargon.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.scripts.deepen_narrative import (
    _compose_insight,
    _deep_card,
    set_insight_explainer,
)
from app.services.insight_explainer import (
    _build_prompt,
    make_vertex_insight_explainer,
    parse_triple,
)


class _FakeVertex:
    """Stand-in for VertexClient.stream — yields a canned text in 2 chunks.

    Counts calls (bounded-hot contract tests) and can simulate a wedged
    stream via `hang_sec` (VertexClient.stream has no deadline of its own,
    so the connector's per-call timeout is what must cut it off).
    """

    def __init__(self, text: str = "", *, raise_exc: bool = False,
                 hang_sec: float = 0.0) -> None:
        self._text = text
        self._raise = raise_exc
        self._hang = hang_sec
        self.calls = 0

    async def stream(self, call: object) -> AsyncIterator[str]:
        self.calls += 1
        if self._raise:
            raise RuntimeError("vertex disabled — using deterministic fallback")
        if self._hang:
            import asyncio
            await asyncio.sleep(self._hang)
        mid = len(self._text) // 2
        yield self._text[:mid]
        yield self._text[mid:]


_GOOD = (
    "WHAT: Loan Origination is one of the bank's developing capabilities, "
    "scoring 2.5 out of 5 and shaping how quickly the institution can serve "
    "borrowers across every channel.\n"
    "WHY: It matters because faster, more reliable origination directly "
    "improves the customer experience and the bank's competitiveness.\n"
    "SO WHAT: Reaching the 3.3 typical at comparable institutions would add "
    "about 0.8 points; make it a near-term focus for the year ahead.\n"
)

# Long enough to pass _valid_insight's length gate, but leaks jargon so the
# jargon gate (not length) is what triggers the template fallback.
_JARGON = (
    "WHAT: This P2C3 capability is one of the bank's developing areas and it "
    "shapes how the institution serves its customers across every channel.\n"
    "WHY: It scores M2 today, which means there is meaningful room to grow "
    "and strengthen the wider operation over the coming year ahead.\n"
    "SO WHAT: Improve the subcap soon and lift the overall result so the "
    "bank can compete more effectively against its closest peers.\n"
)


def test_parse_triple_extracts_three_sections() -> None:
    out = parse_triple(_GOOD)
    assert out is not None
    what, why, sowhat = out
    assert what.startswith("Loan Origination")
    assert "customer experience" in why
    assert "near-term focus" in sowhat


def test_parse_triple_rejects_malformed() -> None:
    assert parse_triple("") is None
    assert parse_triple("prose with no labels at all") is None
    assert parse_triple("WHAT: only what\nWHY: only why") is None  # no SO WHAT


def test_connector_returns_triple_on_good_response() -> None:
    explain = make_vertex_insight_explainer(_FakeVertex(_GOOD))
    out = explain(client="Bank", name="Loan Origination", pillar="P3",
                  score=2.5, peer=3.3, existing_what="origination")
    assert out is not None and len(out) == 3


def test_prompt_carries_evidence_facts_and_analysis_directive() -> None:
    """2026-07-06 mandate: the explainer prompt must direct Gemini to
    analyze the EVIDENCE CONTENT (systems, practices, findings) with the
    score as supporting context — never score narration — and list the
    card's own findings as the only citable ids."""
    prompt = _build_prompt(
        client="Bank", name="Digital Marketing Strategy", pillar="P2",
        score=1.4, peer=3.2, existing_what="x",
        facts=(("E-004", "Marketing relies on a single shared inbox"),
               ("E-011", "No marketing automation platform is in place")),
    )
    assert "- [E-004] Marketing relies on a single shared inbox" in prompt
    assert "- [E-011] No marketing automation platform is in place" in prompt
    assert "ANALYZE THE EVIDENCE CONTENT" in prompt
    assert "never narrates the score" in prompt.lower() \
        or "merely narrates the score" in prompt.lower()
    assert "never invent ids" in prompt.lower()


def test_prompt_facts_block_honest_when_absent() -> None:
    prompt = _build_prompt(client="Bank", name="Cap", pillar="P3",
                           score=2.5, peer=3.3, existing_what="x")
    assert "(none supplied)" in prompt


def test_connector_accepts_facts_kwarg_and_memoises_on_it() -> None:
    fake = _FakeVertex(_GOOD)
    explain = make_vertex_insight_explainer(fake, budget_sec=60.0)
    base = {"client": "Bank", "name": "Cap", "pillar": "P3", "score": 2.5,
            "peer": 3.3, "existing_what": "x"}
    assert explain(**base, facts=(("E-1", "finding one"),)) is not None
    # same facts → memo hit, no second stream
    explain(**base, facts=(("E-1", "finding one"),))
    assert fake.calls == 1
    # different facts → distinct memo key → a new call
    explain(**base, facts=(("E-2", "finding two"),))
    assert fake.calls == 2


def test_connector_returns_none_on_vertex_error() -> None:
    explain = make_vertex_insight_explainer(_FakeVertex(raise_exc=True))
    assert explain(client="Bank", name="Cap", pillar="P3", score=2.5,
                   peer=3.3, existing_what="x") is None


async def test_connector_works_inside_running_loop() -> None:
    # Exercises the worker-thread bridge (deepen runs in an async main).
    explain = make_vertex_insight_explainer(_FakeVertex(_GOOD))
    out = explain(client="Bank", name="Loan Origination", pillar="P3",
                  score=2.5, peer=3.3, existing_what="x")
    assert out is not None and len(out) == 3


def test_compose_insight_adopts_clean_vertex_triple() -> None:
    explain = make_vertex_insight_explainer(_FakeVertex(_GOOD))
    try:
        set_insight_explainer(explain)
        out = _compose_insight("Bank", "Loan Origination", "P3", 2.5, 3.3,
                               "origination")
        template = _deep_card("Bank", "Loan Origination", "P3", 2.5, 3.3,
                              "origination")
        assert "Loan Origination" in out[0]
        assert out != template  # the Vertex output won
    finally:
        set_insight_explainer(None)


def test_compose_insight_falls_back_when_vertex_leaks_jargon() -> None:
    explain = make_vertex_insight_explainer(_FakeVertex(_JARGON))
    try:
        set_insight_explainer(explain)
        out = _compose_insight("Bank", "Cap", "P2", 2.0, 3.0, "")
        assert out == _deep_card("Bank", "Cap", "P2", 2.0, 3.0, "")
    finally:
        set_insight_explainer(None)


# ── Bounded-hot contract (2026-07-04 regen step-timeout incident) ──────


def test_budget_exhausted_returns_none_without_calling_vertex() -> None:
    fake = _FakeVertex(_GOOD)
    explain = make_vertex_insight_explainer(fake, budget_sec=0.0)
    assert explain(client="Bank", name="Cap", pillar="P3", score=2.5,
                   peer=3.3, existing_what="x") is None
    assert fake.calls == 0  # never reached Vertex — instant template path


def test_breaker_trips_after_three_consecutive_failures() -> None:
    fake = _FakeVertex(raise_exc=True)
    explain = make_vertex_insight_explainer(fake, budget_sec=60.0)
    for _ in range(3):
        assert explain(client="Bank", name="Cap", pillar="P3", score=2.5,
                       peer=3.3, existing_what="x") is None
    assert fake.calls == 3
    # Breaker now open: the 4th call short-circuits without touching Vertex.
    assert explain(client="Bank", name="Cap", pillar="P3", score=2.5,
                   peer=3.3, existing_what="x") is None
    assert fake.calls == 3


def test_memo_caches_identical_inputs() -> None:
    fake = _FakeVertex(_GOOD)
    explain = make_vertex_insight_explainer(fake, budget_sec=60.0)
    kwargs = {"client": "Bank", "name": "Loan Origination", "pillar": "P3",
              "score": 2.5, "peer": 3.3, "existing_what": "origination"}
    first = explain(**kwargs)
    second = explain(**kwargs)
    assert first is not None and second == first
    assert fake.calls == 1  # second call served from the in-run memo


def test_per_call_timeout_cuts_off_a_wedged_stream() -> None:
    import threading
    import time

    fake = _FakeVertex(_GOOD, hang_sec=5.0)
    explain = make_vertex_insight_explainer(
        fake, budget_sec=60.0, call_timeout_sec=0.2)
    t0 = time.monotonic()
    assert explain(client="Bank", name="Cap", pillar="P3", score=2.5,
                   peer=3.3, existing_what="x") is None
    elapsed = time.monotonic() - t0
    assert fake.calls == 1  # the call fired but was killed at the deadline
    # ABANDONMENT contract (2026-07-04 review): the caller must return at
    # the deadline, NOT wait out the 5s wedge — a blocking join (e.g. a
    # ThreadPoolExecutor context manager) would push elapsed past hang_sec.
    assert elapsed < 2.0, f"caller blocked {elapsed:.1f}s on a wedged stream"
    # The abandoned worker must be a DAEMON: concurrent.futures' atexit
    # hook JOINS non-daemon workers at interpreter shutdown, so a wedged
    # SDK call would stall process exit until the chain's subprocess
    # timeout killed it — the exact regen incident this bounds.
    stranded = [t for t in threading.enumerate()
                if t.name.startswith("insight-explainer-stream")]
    assert stranded, "expected the abandoned worker to still be alive"
    assert all(t.daemon for t in stranded), "abandoned worker must be daemon"


def test_success_resets_breaker_count() -> None:
    # 2 failures, then a success, then 2 more failures: breaker must NOT
    # trip (only CONSECUTIVE failures count).
    class _Flaky:
        def __init__(self) -> None:
            self.calls = 0

        async def stream(self, call: object) -> AsyncIterator[str]:
            self.calls += 1
            if self.calls != 3:
                raise RuntimeError("transient")
            yield _GOOD

    flaky = _Flaky()
    explain = make_vertex_insight_explainer(flaky, budget_sec=60.0)
    for i in range(1, 6):
        out = explain(client="Bank", name=f"Cap{i}", pillar="P3", score=2.5,
                      peer=3.3, existing_what="x")
        assert (out is not None) == (i == 3)
    assert flaky.calls == 5  # all five reached Vertex — breaker never opened
