"""Vertex-backed insight explainer — the connector for deepen_narrative's
`set_insight_explainer` hook (D2, scope 2).

`deepen_narrative._deep_card` composes a deterministic, jargon-free,
opportunity-framed WHAT/WHY/SO-WHAT for every insight card. That template
is the regression-safe FALLBACK. When the ingest environment has Vertex
credentials it can inject a real LLM explainer via
`deepen_narrative.set_insight_explainer(make_vertex_insight_explainer())`,
which regenerates the three fields grounded in the card's own facts.

The contract (matching `deepen_narrative.InsightExplainer`):

    explain(*, client, name, pillar, score, peer, existing_what)
        -> tuple[str, str, str] | None

Returns the (what, why, so_what) triple, or **None** on any error,
empty response, or parse failure — so deepen keeps its template. deepen's
`_compose_insight` additionally runs `_valid_insight` (length + jargon
guard) and `_plain()` on whatever this returns, so the connector stays
thin: build prompt → stream Gemini → parse three labelled fields.

Offline (no creds / `DMA_DISABLE_VERTEX=1`) the lazy Vertex client raises
on first use; the broad `except` turns that into `None` → template. This
is why the connector is safe to wire unconditionally.

BOUNDED-HOT CONTRACT (2026-07-04 regen incident): deepen_narrative is a
HARD step in run_derive_chain with a per-step timeout; in the Vertex-HOT
regen container this connector fired one LIVE call per insight card with
no wall-clock bound, and the step was killed at the 300s budget — the
whole pack regeneration aborted. The connector is therefore bounded on
four axes, all of which degrade to the deterministic template (never an
error):

  - wall-clock budget (`DMA_EXPLAINER_BUDGET_SEC`, default 120): the
    clock starts on the FIRST call; once spent every later call returns
    None instantly. 120s keeps the default 300s step budget safe; the
    deploy pipeline raises both knobs together (cloudbuild ENV_ARGS).
  - per-call timeout (`DMA_EXPLAINER_CALL_TIMEOUT_SEC`, default 25):
    VertexClient.stream has NO deadline of its own, so one wedged call
    could otherwise eat the entire budget.
  - circuit breaker: 3 CONSECUTIVE failures trip the connector open for
    the rest of the run (a cold/broken Vertex should cost 3 fast
    failures, not 630 slow ones). A success resets the count.
  - in-run memo: identical (client, name, pillar, score, peer, what)
    inputs return the cached triple with no second call.

The read-path uplift is unaffected either way: enrich_corpus's
`insight_explanation` surface (synthesis-cache-backed, soft step with
full build budget) remains the primary Gemini rung for card prose.
"""
from __future__ import annotations

import asyncio
import os
import queue
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import structlog

from app.services.vertex_client import GeminiCall, get_vertex_client

log = structlog.get_logger()

InsightExplainer = Callable[..., "tuple[str, str, str] | None"]

# Consecutive-failure count that trips the breaker for the rest of the run.
_BREAKER_THRESHOLD = 3


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default

# Plain business label per pillar for the prompt (the prompt itself is
# internal; we still feed plain language so the model mirrors it back).
_PILLAR_LABEL = {
    "P1": "strategy and governance",
    "P2": "customer experience",
    "P3": "operations",
    "P4": "data and technology",
}

_PROMPT = (
    "You are a digital maturity expert for Zennify. Rewrite this insight "
    "card for a financial-services executive in plain business language. "
    "Rules: opportunity-framed, never deficit language (no 'slipping "
    "behind', 'erodes', 'lags', 'left unaddressed'); no internal jargon (no "
    "maturity-band codes like M3, no capability codes like P2C3, never the "
    "word 'subcap').\n"
    "MINIMAL SCORES: use the maturity score AT MOST ONCE across all three "
    "sections, and only as a single anchor — never repeat 'X out of 5' or "
    "'X points below the peer median' section after section. Everywhere "
    "else describe the standing in words ('well behind peers', 'a working "
    "strength', 'still developing').\n"
    "ANALYZE THE EVIDENCE CONTENT: when evidence findings are listed "
    "below, the card must state what the researchers actually documented "
    "— the systems named, the practices observed, the concrete findings "
    "— and synthesize what they MEAN for the business. A card that merely "
    "narrates the score is wrong. Cite each finding you use by its id in "
    "square brackets exactly as shown; never invent ids.\n\n"
    "Capability: {name}\n"
    "Business area: {pillar_label}\n"
    "Client: {client}\n"
    "Score: {score_str}\n"
    "Peer benchmark: {peer_str}\n"
    "Evidence findings (the observed state — the ONLY citable ids):\n"
    "{facts_block}\n"
    "Current description: {existing_what}\n\n"
    "Return EXACTLY three labelled sections, each 1-3 sentences, no other "
    "text:\n"
    "WHAT: <what the evidence shows about this capability today>\n"
    "WHY: <why the observed gaps matter to the business>\n"
    "SO WHAT: <the recommended near-term action, grounded in the observed state>\n"
)

_TRIPLE_RE = re.compile(
    r"WHAT:\s*(?P<what>.+?)\s*"
    r"WHY:\s*(?P<why>.+?)\s*"
    r"SO[\s-]*WHAT:\s*(?P<sowhat>.+)\Z",
    re.IGNORECASE | re.DOTALL,
)


def _score_phrase(v: float | None) -> str:
    return f"{v:.1f} out of 5" if isinstance(v, int | float) else "not separately scored"


def _peer_phrase(v: float | None) -> str:
    return (
        f"{v:.1f} out of 5 at comparable institutions"
        if isinstance(v, int | float)
        else "no peer benchmark available"
    )


def _facts_block(facts: tuple[tuple[str, str], ...] | None) -> str:
    """Evidence findings as citable prompt lines ('- [E-014] …'). The card's
    linked-evidence excerpts are what the model must ANALYZE — absent facts
    the block says so and the model falls back to the description."""
    lines = [f"- [{eid}] {fact}".strip()
             for eid, fact in (facts or ()) if eid and fact][:3]
    return "\n".join(lines) or "(none supplied)"


def _build_prompt(
    *, client: str, name: str, pillar: str | None,
    score: float | None, peer: float | None, existing_what: str,
    facts: tuple[tuple[str, str], ...] = (),
) -> str:
    return _PROMPT.format(
        name=name or "this capability",
        pillar_label=_PILLAR_LABEL.get((pillar or "").upper(), "digital capability"),
        client=client or "the institution",
        score_str=_score_phrase(score),
        peer_str=_peer_phrase(peer),
        facts_block=_facts_block(facts),
        existing_what=(existing_what or "").strip()[:1200] or "(none supplied)",
    )


def parse_triple(raw: str) -> tuple[str, str, str] | None:
    """Extract the WHAT / WHY / SO-WHAT sections from a Gemini response.

    Returns None when the response is empty or doesn't carry all three
    labelled sections (deepen then keeps its deterministic template).
    """
    if not raw or not raw.strip():
        return None
    m = _TRIPLE_RE.search(raw.strip())
    if not m:
        return None
    what, why, sowhat = (m.group("what").strip(), m.group("why").strip(),
                         m.group("sowhat").strip())
    if not (what and why and sowhat):
        return None
    return what, why, sowhat


def _drain_stream_sync(
    vertex_client: Any, call: GeminiCall, *, timeout_sec: float | None = None,
) -> str:
    """Run an async GeminiCall stream to a single string, synchronously.

    Always executes in a dedicated DAEMON thread with its own event loop:
    deepen_narrative's card loop runs inside an async main (a bare
    `asyncio.run` would raise "cannot be called from a running event
    loop"), and the thread is ALSO what makes `timeout_sec` enforceable —
    VertexClient.stream drives the BLOCKING SDK `generate_content` call,
    which no event-loop cancellation can interrupt, so the deadline lives
    on the calling side (queue.get(timeout=...)). On expiry the worker is
    ABANDONED and, being a daemon, never blocks interpreter shutdown —
    a ThreadPoolExecutor here would re-wedge the process at exit because
    concurrent.futures registers an atexit hook that JOINS its non-daemon
    workers, so one black-holed SDK call would stall deepen_narrative
    AFTER its commit until the chain's subprocess timeout killed it (the
    exact incident this module guards against). TimeoutError propagates
    to the caller's fallback path.
    """
    async def _collect() -> str:
        chunks: list[str] = []
        # GROUNDING NOTE: this stream output is NOT run through the DB-backed
        # `validate_response` — the explainer is sync + session-less and the
        # card WHAT/WHY/SO-WHAT are narrative prose with no evidence citations
        # to ground. Validation is instead deepen_narrative._valid_insight
        # (rejects jargon / thin output) + _plain() (strips residual codes) +
        # the deterministic _deep_card template fallback — the CLAUDE.md
        # "validator + template-fill on any flag" hard rule. Allow-listed in
        # tests/test_grounding_no_bypass.py::_DOCUMENTED_EXCEPTIONS.
        async for chunk in vertex_client.stream(call):
            chunks.append(chunk)
        return "".join(chunks)

    result: queue.Queue = queue.Queue(maxsize=1)

    def _runner() -> None:
        try:
            result.put(("ok", asyncio.run(_collect())))
        except BaseException as exc:  # re-raised on the caller side
            result.put(("err", exc))

    worker = threading.Thread(
        target=_runner, daemon=True, name="insight-explainer-stream")
    worker.start()
    try:
        kind, payload = result.get(timeout=timeout_sec)
    except queue.Empty:
        raise TimeoutError(
            f"insight-explainer stream exceeded {timeout_sec}s — worker "
            "abandoned (daemon)") from None
    if kind == "err":
        raise payload
    return payload


def make_vertex_insight_explainer(
    vertex_client: Any = None,
    *,
    budget_sec: float | None = None,
    call_timeout_sec: float | None = None,
) -> InsightExplainer:
    """Build a SYNC insight explainer for `deepen_narrative.set_insight_explainer`.

    `vertex_client` is injectable for tests; in production it defaults to
    the lazy `get_vertex_client()`. Any failure (no creds, transient
    error, unparseable response) returns None so deepen keeps the
    deterministic template.

    Bounded-hot contract (module docstring): `budget_sec` caps the total
    wall clock spent across ALL calls (default env
    `DMA_EXPLAINER_BUDGET_SEC`, 120s — safe inside the 300s default
    derive-chain step budget); `call_timeout_sec` caps each stream
    (default env `DMA_EXPLAINER_CALL_TIMEOUT_SEC`, 25s). Repeated
    consecutive failures trip a circuit breaker; identical inputs are
    memoised for the life of this explainer instance.
    """
    budget = _env_float("DMA_EXPLAINER_BUDGET_SEC", 120.0) \
        if budget_sec is None else budget_sec
    per_call = _env_float("DMA_EXPLAINER_CALL_TIMEOUT_SEC", 25.0) \
        if call_timeout_sec is None else call_timeout_sec
    state = {"deadline": None, "failures": 0, "tripped": False,
             "exhausted_logged": False, "calls": 0}
    memo: dict[tuple, tuple[str, str, str] | None] = {}

    def explain(
        *, client: str, name: str, pillar: str | None,
        score: float | None, peer: float | None, existing_what: str,
        facts: tuple[tuple[str, str], ...] = (),
    ) -> tuple[str, str, str] | None:
        if state["tripped"]:
            return None
        now = time.monotonic()
        if state["deadline"] is None:
            state["deadline"] = now + budget  # clock starts on first use
        if now >= state["deadline"]:
            if not state["exhausted_logged"]:
                state["exhausted_logged"] = True
                log.info(
                    "insight_explainer.budget_exhausted",
                    budget_sec=budget, calls_made=state["calls"],
                )
            return None
        facts = tuple(facts or ())
        key = (client, name, pillar, score, peer,
               (existing_what or "")[:1200], facts)
        if key in memo:
            return memo[key]
        try:
            vc = vertex_client if vertex_client is not None else get_vertex_client()
            call = GeminiCall(
                surface="insight_explanation",
                model="flash",
                prompt=_build_prompt(
                    client=client, name=name, pillar=pillar,
                    score=score, peer=peer, existing_what=existing_what,
                    facts=facts,
                ),
                max_output_tokens=1024,
                temperature=0.2,
            )
            state["calls"] += 1
            out = parse_triple(
                _drain_stream_sync(vc, call, timeout_sec=per_call))
        except Exception:
            state["failures"] += 1
            if state["failures"] >= _BREAKER_THRESHOLD:
                state["tripped"] = True
                log.info(
                    "insight_explainer.breaker_tripped",
                    consecutive_failures=state["failures"],
                    calls_made=state["calls"],
                )
            return None
        state["failures"] = 0
        memo[key] = out
        return out

    return explain


# ── Vertex-backed EXECUTIVE-SUMMARY (SCQA) composer ─────────────────────
# deepen_narrative composes the exec summary deterministically (report
# section OR a scores/recs template). That template is the regression-safe
# FALLBACK, but it makes every client's exec summary read the same shape.
# When Vertex creds are present the ingest env injects this composer via
# `deepen_narrative.set_scqa_composer(make_vertex_scqa_composer())`, which
# reads THIS client's own pillar findings + evidence + scores and writes a
# genuinely varied Situation/Complication/Question/Answer — no fixed
# skeleton. deepen validates the result (>=2 real E-IDs, >=4 source
# families, rubric, no scaffolding) and falls back to the template on any
# miss, so the composer stays thin. Same bounded-hot contract as the
# insight explainer (shared budget/breaker knobs).

SCQAComposer = Callable[..., "str | None"]

_SCQA_PROMPT = """You are writing the EXECUTIVE SUMMARY for {client} in a \
digital-maturity assessment. Write for an enterprise account executive who \
may be meeting this client for the first time — someone who needs to grasp \
the STORY in one read, not decode a scorecard.

Write ONE cohesive narrative in four short markdown sections with these \
exact headers:
## 1. Situation
## 2. Complication
## 3. Question
## 4. Answer

Each section is flowing prose that builds on the last, so the four read as a \
single argument: who this client is and where they are headed, the tension \
holding them back, the decision it forces, and the recommended path with the \
reason it compounds. A newcomer should finish knowing the client, the core \
problem, and what to do first — and WHY.

HARD STYLE RULES:
- SYNTHESIZE, do not list. Connect facts into cause and effect; never staple \
one fact after another ("The register adds X. The file also carries Y."). \
Explain what the pattern MEANS for the business.
- MINIMAL numbers. Use AT MOST ONE maturity score in the whole summary, and \
only if it anchors the single most important point. Everywhere else describe \
standing in words ("well behind peers", "a genuine strength", "still early"). \
Do NOT recite score-versus-peer for multiple capabilities — describe the \
pattern instead. A firmographic number (assets, growth rate) is fine when it \
sets context.
- Ground every claim in the findings below; invent nothing.
- RELEVANCE, NOT COUNT: cite the SINGLE most-relevant evidence id for each \
claim — the one id whose excerpt actually backs that sentence. NEVER stack \
multiple ids on one sentence (e.g. "[E-001, E-002, E-003]") — that is a tier \
dump, not evidence; pick the best one. A summary naturally ends up citing a few \
ids because it makes a few points, one per point. Never decorate a sentence \
with an id that does not back it, and never add a filler sentence whose only \
purpose is to carry an id. If an excerpt is the key proof, say what it SHOWS \
and why it matters, THEN cite it — do not just name the id and move on. (You \
will cite at least two ids total across the whole summary, but only because you \
make at least two evidenced points — not to hit a quota.)
- TELL THE STORY: build one argument with a beginning (who they are / where \
they're headed), a middle (the tension and what the evidence reveals about it), \
and an end (the move and why it compounds). It must read as a narrative a \
newcomer follows, not a findings list.
- Vary to THIS client; no fixed sentence pattern. Plain business English — \
never raw taxonomy codes (P2C1), band shorthand (M3/L2), or the words \
"sub-cap", "pillar", "peer-cohort". 180-320 words total.

CLIENT: {client}
OVERALL DIGITAL MATURITY: {overall}
KEY FACTS: {facts}
BIGGEST GAPS (capability — describe qualitatively, do not quote every score): {gaps}
PRIORITY MOVES: {recs}
EVIDENCE (id — excerpt): {evidence}
ANALYST FINDINGS (verbatim excerpts from the report):
{deep_dives}
"""


def _clip(s: object, n: int) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def _build_scqa_prompt(
    *, client: str, overall: object, facts: str, gaps: str,
    recs: str, evidence: str, deep_dives: str,
) -> str:
    return _SCQA_PROMPT.format(
        client=client or "the institution",
        overall=(f"{float(overall):.1f}/5" if isinstance(overall, int | float)
                 else "(not scored)"),
        facts=_clip(facts, 600) or "(none)",
        gaps=_clip(gaps, 500) or "(none)",
        recs=_clip(recs, 500) or "(none)",
        evidence=_clip(evidence, 1600) or "(none)",
        deep_dives=_clip(deep_dives, 3000) or "(none)",
    )


def make_vertex_scqa_composer(
    vertex_client: Any = None,
    *,
    budget_sec: float | None = None,
    call_timeout_sec: float | None = None,
) -> SCQAComposer:
    """Build a SYNC exec-summary composer for `deepen_narrative.set_scqa_composer`.

    Returns the composed SCQA markdown, or **None** on any error / empty /
    offline (`DMA_DISABLE_VERTEX=1`) so deepen keeps its deterministic
    composition. Same bounded-hot contract as `make_vertex_insight_explainer`
    (budget/per-call timeout/breaker/memo) — the exec summary is one call per
    client (<=94), so it sits comfortably inside the derive-chain step budget.
    """
    budget = _env_float("DMA_EXPLAINER_BUDGET_SEC", 120.0) \
        if budget_sec is None else budget_sec
    per_call = _env_float("DMA_EXPLAINER_CALL_TIMEOUT_SEC", 25.0) \
        if call_timeout_sec is None else call_timeout_sec
    state = {"deadline": None, "failures": 0, "tripped": False,
             "exhausted_logged": False, "calls": 0}
    memo: dict[tuple, str | None] = {}

    def compose(
        *, client: str, overall: object = None, facts: str = "",
        gaps: str = "", recs: str = "", evidence: str = "", deep_dives: str = "",
    ) -> str | None:
        if state["tripped"]:
            return None
        now = time.monotonic()
        if state["deadline"] is None:
            state["deadline"] = now + budget
        if now >= state["deadline"]:
            if not state["exhausted_logged"]:
                state["exhausted_logged"] = True
                log.info("scqa_composer.budget_exhausted",
                         budget_sec=budget, calls_made=state["calls"])
            return None
        key = (client, str(overall), facts[:400], gaps[:200], evidence[:400])
        if key in memo:
            return memo[key]
        try:
            vc = vertex_client if vertex_client is not None else get_vertex_client()
            call = GeminiCall(
                surface="insight_explanation",
                model="flash",
                prompt=_build_scqa_prompt(
                    client=client, overall=overall, facts=facts,
                    gaps=gaps, recs=recs, evidence=evidence, deep_dives=deep_dives),
                max_output_tokens=1200,
                temperature=0.3,
            )
            state["calls"] += 1
            raw = _drain_stream_sync(vc, call, timeout_sec=per_call)
        except Exception:
            state["failures"] += 1
            if state["failures"] >= _BREAKER_THRESHOLD:
                state["tripped"] = True
                log.info("scqa_composer.breaker_tripped",
                         consecutive_failures=state["failures"],
                         calls_made=state["calls"])
            return None
        state["failures"] = 0
        out = (raw or "").strip()
        # Require all four SCQA headers, else let deepen keep its composition.
        if not out or not all(
            re.search(rf"(?im)^\s*##\s*{n}\.", out)
            for n in (1, 2, 3, 4)
        ):
            memo[key] = None
            return None
        memo[key] = out
        return out

    return compose
