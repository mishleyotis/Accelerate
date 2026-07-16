"""L3 — the compose → grade → repair → re-grade loop (refine-before-render).

The primary author is the deterministic composer. Each drafted item is graded;
if it fails, the targeted repair for each failing parameter is applied and it is
re-graded, up to K iterations. Only a PASS renders. If the loop cannot reach the
bar after K, the item is escalated to the Gemini fallback (the rubric is the
prompt contract) — persisted + re-graded like any other; if that too fails a HARD
gate the best deterministic draft is kept and FLAGGED for review, never shipped
as if gold.

Telemetry (which repair fixed which failing parameter, iteration count, whether
Gemini was needed) is returned for the L6 strategy-memory + the pre-redeploy
scorecard's falling-iteration/Gemini-rate metrics.
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from app.services.nlp.composer import _PILLAR_DOMAIN, _platform_for, compose_card
from app.services.nlp.grader import Grade, Item, grade

if TYPE_CHECKING:
    from app.services.nlp.entity_knowledge import Capability, EntityState
    from app.services.nlp.storyline import Thesis


def _repair(item: Item, g: Grade, state: EntityState) -> Item:
    """Apply the targeted repair for each failing parameter (deterministic)."""
    # G2 — drop citations that don't support the capability; re-pick supported ones
    if "G2" in g.repairs:
        cap = state.capability(item.anchor_subcap)
        cap_text = f"{cap.name} {cap.rationale}".strip() if cap else (item.title or "")
        hits = state.supporting_evidence(cap_text, k=4, min_score=0.30)
        item.e_ids = [eid for eid, _ in hits]
    # G4 — inject play + named system + urgency into the so-what, polarity-aware
    # (a strength expands; a gap closes) and naming the capability's own domain,
    # mirroring compose_card so the repair reads like the primary author.
    if "G4" in g.repairs:
        from app.services.nlp.composer import _urgency_clause
        cap = state.capability(item.anchor_subcap)
        is_strength = bool(cap and (cap.peer_gap or 0) > 0)
        domain = _PILLAR_DOMAIN.get(cap.pillar, "this capability area") if cap \
            else "this capability area"
        verb = "expand" if is_strength else "close the gap with"
        platform = _platform_for(state, item.anchor_subcap) or "Salesforce"
        item.so_what = (f"Deploy {platform} to {verb} {domain} "
                        f"{_urgency_clause(state)}.").strip()
    # G3 — inject a sibling / second-pillar link
    if "G3" in g.repairs and item.siblings:
        # co-coverage is verifiable (both are in this run's scope); a
        # 'connection' between arbitrary siblings is not
        item.why = (f"{item.why} A single program can cover it alongside "
                    f"{item.siblings[0]}.").strip()
    # C1 — a one-liner WHAT gains the grounded implication sentence
    if "C1" in g.repairs and len(item.what.split(".")) < 3:
        item.what = (f"{item.what.rstrip('.')}. Closing it modernizes the "
                     f"capability and raises the floor for the ones around "
                     f"it.").strip()
    return item


def refine_card(
    state: EntityState, cap: Capability, *, siblings: list[Capability] | None = None,
    is_top: bool = True, k: int = 3,
) -> tuple[Item | None, Grade | None, dict[str, Any]]:
    """Compose + refine one insight card. Returns (item|None, grade|None,
    telemetry). item is None when the anchor cannot be grounded (skip it)."""
    draft = compose_card(state, cap, siblings=siblings, is_top=is_top)
    if draft is None:
        return None, None, {"skipped": "unevidenced_anchor", "subcap": cap.subcap_id}
    telemetry: list[dict] = []
    g = grade(draft, state)
    for i in range(k):
        telemetry.append({"iter": i, "grade": g.grade, "passed": g.passed,
                          "hard_fails": list(g.hard_fails), "repaired": list(g.repairs)})
        if g.passed:
            return draft, g, {"path": "deterministic", "iters": i + 1, "telemetry": telemetry}
        draft = _repair(draft, g, state)
        g = grade(draft, state)
    telemetry.append({"iter": k, "grade": g.grade, "passed": g.passed,
                      "hard_fails": list(g.hard_fails)})
    if g.passed:
        return draft, g, {"path": "deterministic", "iters": k + 1, "telemetry": telemetry}
    # Deterministic loop exhausted → the async Gemini fallback (gemini_rescue) is
    # the next tier, invoked by the async derive layer. Here we return the best
    # draft FLAGGED so the caller escalates or holds it for review — never gold.
    return draft, g, {"path": "needs_gemini", "iters": k, "telemetry": telemetry,
                      "flag": "sub_bar", "hard_fails": list(g.hard_fails)}


# ── the Gemini fallback (the rubric IS the prompt contract) ──────────────────
# Only reached when the deterministic loop cannot pass K iterations. Gemini output
# is re-graded like any other draft; it renders only if it PASSES, else the best
# deterministic draft is kept + flagged. Async because the Vertex client streams.

_GEMINI_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"}, "what": {"type": "string"},
        "why": {"type": "string"}, "so_what": {"type": "string"},
    },
    "required": ["title", "what"],
}


def _gemini_prompt(state: EntityState, cap: Capability, draft: Item, g: Grade) -> str:
    """The rubric as a prompt contract: entity + capability + the SUPPORT-CHECKED
    evidence (the only figures Gemini may quote) + the parameters the
    deterministic draft failed, and a strict-JSON output demand."""
    excerpts = []
    for e in (draft.e_ids or [])[:4]:
        ex = state.evidence_excerpt(e)
        if ex:
            excerpts.append(f"[{e}] {ex[:400]}")
    ev_block = "\n".join(excerpts) or "(no evidence excerpts available)"
    domain = _PILLAR_DOMAIN.get(cap.pillar, "this capability area")
    pm = f"{cap.peer_median:g}" if cap.peer_median is not None else "n/a"
    failing = ", ".join(sorted(g.repairs)) or "distinctiveness / consultant-grade quality"
    return (
        f"You are a Zennify consultant writing ONE {draft.surface.replace('_', ' ')} "
        f"for {state.name}. Capability: \"{cap.name}\" in {domain} "
        f"(assessment score {cap.score:g} vs a {pm} peer benchmark).\n\n"
        f"Evidence — cite ONLY these E-IDs; every figure, name, and date you use "
        f"MUST appear verbatim in one of them (no fabrication):\n{ev_block}\n\n"
        f"The deterministic draft failed these rubric parameters: {failing}. Fix them.\n\n"
        f"Return STRICT JSON with keys title, what, why, so_what where:\n"
        f"- title: a client-specific thesis headline, NOT the bare capability name.\n"
        f"- what: 3-5 sentences grounded ONLY in the evidence above, quoting its "
        f"figures verbatim, varied sentence structure.\n"
        f"- why: connect the capability to a SECOND pillar or capability (a "
        f"cross-link), so one program advances both.\n"
        f"- so_what: an action verb + a named platform/system + a time/urgency "
        f"window.\n"
        f"Frame any gap as an opportunity (never \"no X\", \"lacks X\", \"missing\"). "
        f"If a figure is not in the evidence, do not state it."
    )


def _parse_gemini(raw: str) -> dict[str, str] | None:
    """Parse Gemini's JSON (tolerating markdown fences / prose wrapping). Returns
    the field dict, or None when the response is unparseable or empty (the
    offline-fallback string is not JSON → None → keep the deterministic draft)."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict) or not (obj.get("title") and obj.get("what")):
        return None
    return {k: str(obj.get(k) or "") for k in ("title", "what", "why", "so_what")}


async def gemini_rescue(
    state: EntityState, cap: Capability, draft: Item, g: Grade,
    *, client: Any = None, model: str = "pro",
) -> tuple[Item, Grade, dict[str, Any]] | None:
    """Escalate a sub-bar item to Gemini and re-grade. Returns (item, grade,
    telemetry) ONLY when Gemini's output PASSES the rubric; None otherwise (the
    caller keeps the best deterministic draft + review flag). Fail-safe: a
    missing client / creds / unparseable response all resolve to None."""
    try:
        from app.services.vertex_client import GeminiCall
        if client is None:
            from app.services.vertex_client import get_vertex_client
            client = get_vertex_client()
        prompt = _gemini_prompt(state, cap, draft, g)
        chunks: list[str] = []
        async for part in client.stream(GeminiCall(
                surface=draft.surface, model=model, prompt=prompt,
                response_schema=_GEMINI_SCHEMA, max_output_tokens=1024)):
            chunks.append(part)
        parsed = _parse_gemini("".join(chunks))
    except Exception:
        return None
    if not parsed:
        return None
    item = Item(
        surface=draft.surface, title=parsed["title"], what=parsed["what"],
        why=parsed.get("why", ""), so_what=parsed.get("so_what", ""),
        anchor_subcap=draft.anchor_subcap, e_ids=list(draft.e_ids),
        siblings=list(draft.siblings), is_top=draft.is_top,
    )
    gg = grade(item, state)
    if gg.passed:
        return item, gg, {"path": "gemini", "model": model, "grade": gg.grade}
    return None


def _exec_brief(state: EntityState, thesis: Thesis, findings: list[Item]) -> str:
    """The grounded brief the LLM narrates the exec summary FROM: the derived
    thesis, the top findings with their own facts, and the evidence excerpts —
    the only figures it may quote."""
    beats = []
    for f in findings[:4]:
        ev = ", ".join((f.e_ids or [])[:3])
        beats.append(f"- {f.title} [{ev}]: {(f.what or '')[:300]}")
    excs = []
    seen: set[str] = set()
    for f in findings[:4]:
        for e in (f.e_ids or [])[:3]:
            if e in seen:
                continue
            seen.add(e)
            ex = state.evidence_excerpt(e)
            if ex:
                excs.append(f"[{e}] {ex[:280]}")
    return (
        f"You are a Zennify consultant writing the EXECUTIVE SUMMARY for "
        f"{state.name}. The assessment's storyline thesis is:\n"
        f"  \"{thesis.headline}\"\n"
        f"Recommended play: {thesis.play}. Through-line: {thesis.through_line}.\n\n"
        f"Top findings (each already grounded):\n" + "\n".join(beats) + "\n\n"
        "Evidence — quote ONLY these, verbatim (no fabrication):\n"
        + "\n".join(excs) + "\n\n"
        "Write a cohesive 4-6 sentence executive summary that OPENS with the "
        "thesis, then weaves the findings into ONE arc (not a list), quoting "
        "their figures, and closes on the play + why now. Natural, varied, "
        "consultant prose — never robotic or templated. Frame gaps as "
        "opportunities. Return STRICT JSON with keys title (the thesis headline), "
        "what (the summary narrative), why (the one-arc rationale), so_what (the "
        "sequenced play + urgency)."
    )


async def narrate_exec(
    state: EntityState, thesis: Thesis, findings: list[Item],
    *, client: Any = None, model: str = "pro",
) -> Item | None:
    """The LLM writes the cohesive exec narrative FROM the grounded brief, re-
    graded on the 'exec' substance bar; returned only on PASS. The deterministic
    compose_exec is the floor the caller keeps when this returns None. Fail-safe:
    missing client / creds / unparseable → None."""
    if not findings:
        return None
    try:
        from app.services.vertex_client import GeminiCall
        if client is None:
            from app.services.vertex_client import get_vertex_client
            client = get_vertex_client()
        chunks: list[str] = []
        async for part in client.stream(GeminiCall(
                surface="exec", model=model, prompt=_exec_brief(state, thesis, findings),
                response_schema=_GEMINI_SCHEMA, max_output_tokens=1024)):
            chunks.append(part)
        parsed = _parse_gemini("".join(chunks))
    except Exception:
        return None
    if not parsed:
        return None
    e_ids = list(dict.fromkeys(e for f in findings[:4] for e in (f.e_ids or [])))[:6]
    item = Item(
        surface="exec", title=parsed["title"], what=parsed["what"],
        why=parsed.get("why", ""), so_what=parsed.get("so_what", ""),
        anchor_subcap=findings[0].anchor_subcap, e_ids=e_ids, siblings=[], is_top=True,
        # multi-anchor: the narrative threads several findings — G2 judges
        # each citation against ANY of their capabilities (see grader.Item)
        anchor_subcaps=list(dict.fromkeys(
            f.anchor_subcap for f in findings[:4] if f.anchor_subcap)),
    )
    return item if grade(item, state).passed else None
