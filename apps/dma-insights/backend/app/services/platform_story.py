"""Deterministic 'conversation starter' composer for D4 Platform cards.

Wireframe contract (DMA Insights · Standalone, 06/2026):
  Each PlatformCard on the D4 Platform page renders a "Conversation
  starters" card alongside Recommendations. Each starter is template-
  fill / evidence-cited and surfaced as numbered AE-actionable prompts.

Per CLAUDE.md "Synthesis persistence + decision gates", surfaces that
are fully derivable from parsed CSV/DOCX inputs are zero-token by design
(the orchestrator's `parsed_skipped_llm` gate). The conversation starter
is exactly that: every input value (platform, pillar, fit score,
addressable subcaps, prereq statuses, readiness) is already loaded in the
platforms router from `runs` + `subcap_scores` + `platform_scores`. We
compose deterministically here; the heavier `intelligence_builder.
platform_story` Vertex surface remains available for the
"Deeper · Pro" expansion the IntelligencePanel offers.

Returns ``None`` when there are zero addressable subcaps so the
``INSUFFICIENT_EVIDENCE`` PlatformCard state stays the single source of
truth for that branch — the wireframe hides the starters card in that
case.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.readiness_index import PrereqCheck, ReadinessLight
from app.services.text_hygiene import plain

_READINESS_TEXT: dict[str, str] = {
    "green": "ready to land now",
    "amber": "near-ready (one or two prereqs to close)",
    "red": "not ready (prerequisites block deployment)",
}

# Bare pillar code ('P2') -> readable label. plain()/scrub_md() strip `P#C#…`
# subcap codes but NOT bare `P#` pillar codes, so composers that weave the
# card's raw `pillar` into prose must convert it here first, or an "…scoped to
# P2." tail leaks the code and breaks cohesion (2026-07-15 platform-name audit).
_PILLAR_PROSE: dict[str, str] = {
    "P1": "strategy and governance", "P2": "customer experience",
    "P3": "operations", "P4": "data and technology",
}


def _pillar_prose(pillar_code: object) -> str:
    """Readable pillar label, or '' when unknown (never leak the raw code)."""
    return _PILLAR_PROSE.get(str(pillar_code or "").strip().upper(), "")


@dataclass
class StarterFacts:
    """Entity-specific grounding for the starter composer (Part 7.1).

    The audit measured 98.9% of starters anchored on the sorted-first
    subcap (P1C1.1.1) with ZERO entity facts. The router now feeds the
    fit engine's TOP-OPPORTUNITY subcap (from `fit_breakdown.top_subcaps`
    — not sorted[0]) plus real peer names, quantified metrics mined from
    the subcap's evidence excerpts (nlp.quantities), and E-ID citations.
    """
    entity_name: str
    top_subcap_id: str
    top_subcap_name: str | None = None
    top_score: float | None = None
    top_peer_median: float | None = None
    top_e_ids: list[str] = field(default_factory=list)
    # "loan cycle 12 days", "efficiency ratio 58.2%" … each optionally
    # suffixed with its citing E-ID by the caller.
    metric_phrases: list[str] = field(default_factory=list)
    peer_names: list[str] = field(default_factory=list)
    absent_families: list[str] = field(default_factory=list)
    sequence_after: list[str] = field(default_factory=list)  # platform names


def _cite(e_ids: list[str], limit: int = 2) -> str:
    ids = [e for e in e_ids if e][:limit]
    return f" [{', '.join(ids)}]" if ids else ""


def _anchor_phrase(facts: StarterFacts) -> str:
    label = (
        f"{facts.top_subcap_name} ({facts.top_subcap_id})"
        if facts.top_subcap_name else facts.top_subcap_id
    )
    if facts.top_score is not None and facts.top_peer_median is not None:
        gap = facts.top_peer_median - facts.top_score
        # ONE score reading; the peer relation is described, not a second
        # "{peer_median:.1f}" number (2026-07-14 operator mandate: cut the
        # score recital, keep the meaning).
        vs = ("below the peer median" if gap > 0.05
              else "above the peer median" if gap < -0.05
              else "in line with the peer median")
        return (
            f"{facts.entity_name} scores {facts.top_score:.1f} on {label} — {vs}"
            f"{_cite(facts.top_e_ids)}"
        )
    if facts.top_score is not None:
        return (
            f"{facts.entity_name} scores {facts.top_score:.1f} on {label}"
            f"{_cite(facts.top_e_ids)}"
        )
    return f"{facts.entity_name}'s weakest addressable capability is {label}{_cite(facts.top_e_ids)}"


def compose_conversation_starters(
    *,
    platform_name: str,
    pillar: str,
    fit_score: float,
    addressable_subcap_ids: list[str],
    prereq_checks: list[PrereqCheck],
    readiness: ReadinessLight,
    facts: StarterFacts | None = None,
) -> list[str]:
    """The prototype's THREE distinct starters (08_pages_d.js:206-218).

    v2 contract (Part 7.1): the anchor is the platform's HIGHEST-
    OPPORTUNITY subcap (``facts.top_subcap_id`` from the fit breakdown,
    never sorted[0]) and every starter carries ≥1 entity-specific fact —
    a real score vs peer, a quantified metric from the entity's own
    evidence, a named peer, or a confirmed-absent platform family, each
    E-ID-cited where evidence exists.

    Returns [] when un-anchorable (no addressable subcaps) so the
    INSUFFICIENT_EVIDENCE card state stays the single source of truth.
    Without ``facts`` (legacy callers) it degrades to the v1 template so
    old snapshots keep rendering.
    """
    if not addressable_subcap_ids:
        return []
    if facts is None:
        return [plain(s) for s in _compose_starters_v1(
            platform_name=platform_name, pillar=pillar, fit_score=fit_score,
            addressable_subcap_ids=addressable_subcap_ids,
            prereq_checks=prereq_checks, readiness=readiness,
        )]

    n = len(addressable_subcap_ids)
    ready = _READINESS_TEXT.get(readiness, "in evaluation")
    failing = next((c for c in prereq_checks if c.status in ("UNMET", "MISSING")), None)
    partial = next((c for c in prereq_checks if c.status == "PARTIAL"), None)
    pain = failing or partial

    # 1 — Discovery, anchored on the top-opportunity subcap + entity fact.
    s1 = (
        f"{_anchor_phrase(facts)}. Ask who owns it today, what tooling backs "
        f"it, and what the review cadence is — {platform_name} addresses "
        f"{n} linked subcap{'s' if n != 1 else ''} here and is {ready} "
        f"(fit {fit_score:.0f}/100)."
    )
    if facts.absent_families:
        s1 += (
            f" {'/'.join(facts.absent_families)} is confirmed absent from "
            f"their detected stack — a greenfield entry."
        )
    starters: list[str] = [s1]

    # 2 — Pain/proof: a quantified entity metric + the concrete prereq gap.
    metric = facts.metric_phrases[0] if facts.metric_phrases else None
    if pain is not None:
        score_str = (
            f"{pain.current_score:.1f}" if pain.current_score is not None
            else "no score recorded"
        )
        s2 = (
            f"Probe the blocker first: '{pain.name}' "
            f"({pain.required_subcap_id}) sits at {score_str}, under the "
            f"readiness threshold ({pain.status})."
        )
        # The metric is mined from the ANCHOR subcap's evidence, not the prereq
        # blocker's, so present it as an ADDITIONAL entity fact — never as "the
        # cost" of the prereq (that false causal bind was a 2026-07-09 QA
        # misattribution: subcap A's figure captioned as subcap B's gap).
        s2 += (
            f" Their own evidence also surfaces {metric}."
            if metric else
            f" That gap is what keeps {facts.entity_name} from landing "
            f"{platform_name} now."
        )
    else:
        top_now = (
            f" (currently {facts.top_score:.1f}/5)"
            if facts.top_score is not None else _cite(facts.top_e_ids)
        )
        s2 = (
            "Prerequisites are MET, so move to value: "
            + (f"their own evidence shows {metric} — "
               if metric else "")
            + f"confirm {facts.entity_name}'s appetite to close the "
            f"{facts.top_subcap_name or facts.top_subcap_id} gap"
            f"{top_now} this fiscal year and open scoping."
        )
    starters.append(s2)

    # 3 — Peer/sequence framing with named peers from the run's peer set.
    peers = [p for p in facts.peer_names if p][:2]
    if peers:
        peer_txt = " and ".join(peers)
        s3 = (
            f"Peer framing: {peer_txt} "
            f"{'are' if len(peers) > 1 else 'is'} in "
            f"{facts.entity_name}'s benchmark cohort"
        )
        if facts.top_peer_median is not None:
            # State the cohort median as its OWN fact — do NOT claim these
            # specific named peers hold it (peers are top-by-overall-score; the
            # median is a per-subcap cohort statistic — conflating them was a
            # 2026-07-09 QA misattribution).
            s3 += (
                f". The cohort median on "
                f"{facts.top_subcap_name or facts.top_subcap_id} is "
                f"{facts.top_peer_median:.1f}"
            )
        elif facts.top_score is not None:
            s3 += (
                f" while {facts.entity_name} sits at {facts.top_score:.1f} "
                f"on {facts.top_subcap_name or facts.top_subcap_id}"
                f"{_cite(facts.top_e_ids)}"
            )
        s3 += (
            f". Sequence {platform_name}"
            + (f" after {' → '.join(facts.sequence_after)}"
               if facts.sequence_after else "")
            + f"; next step is a {platform_name} workshop scoped to {_pillar_prose(pillar) or 'the target capability area'}."
        )
    else:
        s3 = (
            f"Sequence: start at {facts.top_subcap_name or facts.top_subcap_id}"
            + (
                f" ({facts.top_score:.1f}/5 today)"
                if facts.top_score is not None else ""
            )
            + f"{_cite(facts.top_e_ids)} and extend across the "
            f"{n}-subcap surface"
            + (f" — after {' → '.join(facts.sequence_after)}"
               if facts.sequence_after else "")
            + f"; next step is a {platform_name} workshop scoped to {_pillar_prose(pillar) or 'the target capability area'}."
        )
    starters.append(s3)
    # Language cleanse at the composition boundary: plain() strips raw taxonomy
    # codes ("(P2C1.1.1)") and bare E-ID tokens + markdown emphasis while
    # PRESERVING the bracketed "[E-040, E-045]" evidence chips (deliberate
    # grounding). Starters previously reached the AE with raw codes (2026-07-09
    # QA) because this module never cleansed them.
    return [plain(s) for s in starters]


def _compose_starters_v1(
    *,
    platform_name: str,
    pillar: str,
    fit_score: float,
    addressable_subcap_ids: list[str],
    prereq_checks: list[PrereqCheck],
    readiness: ReadinessLight,
) -> list[str]:
    """v1 template pool — retained ONLY as the facts-less fallback for
    legacy callers/snapshots (the audit's sorted-first anchor lives here,
    quarantined)."""
    top = addressable_subcap_ids[0]
    n = len(addressable_subcap_ids)
    others = max(n - 1, 0)
    ready = _READINESS_TEXT.get(readiness, "in evaluation")

    failing = next(
        (c for c in prereq_checks if c.status in ("UNMET", "MISSING")),
        None,
    )
    partial = next(
        (c for c in prereq_checks if c.status == "PARTIAL"),
        None,
    )
    pain = failing or partial

    starters: list[str] = [
        (
            f"Discovery: ask how they handle {top} today — what tool, "
            f"what owner, what review cadence. {platform_name} (pillar "
            f"{pillar}) addresses {n} subcap{'s' if n != 1 else ''} and "
            f"is {ready} (fit {fit_score:.0f}/100)."
        ),
    ]

    if pain is not None:
        score_str = (
            f"{pain.current_score:.1f}"
            if pain.current_score is not None
            else "no score recorded"
        )
        starters.append(
            f"Pain: probe on {pain.required_subcap_id} (prereq "
            f"'{pain.name}': current {score_str} vs. threshold "
            f"{pain.threshold:.1f}, status {pain.status})."
        )
    else:
        starters.append(
            "Value: confirm appetite to close the gap this fiscal year — "
            "prerequisites are MET, so the call can move to scoping."
        )

    if others > 0:
        starters.append(
            f"Sequence: outline a {n}-subcap roadmap starting at {top} "
            f"and extending to {others} additional subcap"
            f"{'s' if others != 1 else ''}; next step is a "
            f"{platform_name} workshop scoped to {_pillar_prose(pillar) or 'the target capability area'}."
        )
    else:
        starters.append(
            f"Action: scope a {platform_name} workshop for the single "
            f"high-impact subcap {top}."
        )
    return starters


def opportunity_areas_from_breakdown(
    breakdown: dict | None,
    category_names: dict[str, str] | None = None,
    *,
    max_areas: int = 3,
) -> list[dict]:
    """Ranked Zennify opportunity areas for one entity x platform card.

    Groups the fit breakdown's top contributing subcaps by category
    (P4C1-style prefix), sums their engine opportunity contributions and
    carries the driving subcap ids + E-IDs — the per-entity opportunity
    map the 2026-07-06 mandate asks for. Pure; [] when the breakdown has
    no top subcaps (INSUFFICIENT_EVIDENCE cards stay honest)."""
    import re as _re

    category_names = category_names or {}
    tops = list((breakdown or {}).get("top_subcaps") or [])
    by_cat: dict[str, dict] = {}
    for t in tops:
        sid = str(t.get("subcap_id") or "")
        m = _re.match(r"^(P[1-4]C\d+)", sid)
        if not m:
            continue
        cat = m.group(1)
        acc = by_cat.setdefault(cat, {
            "category_id": cat,
            "name": category_names.get(cat),
            "opportunity": 0.0,
            "subcap_ids": [],
            "subcap_names": [],
            "e_ids": [],
        })
        acc["opportunity"] += float(t.get("opportunity") or 0.0)
        acc["subcap_ids"].append(sid)
        if t.get("name"):
            acc["subcap_names"].append(str(t["name"]))
        for e in t.get("e_ids") or []:
            if e and e not in acc["e_ids"]:
                acc["e_ids"].append(str(e))
    ranked = sorted(
        by_cat.values(), key=lambda a: (-a["opportunity"], a["category_id"]),
    )[:max_areas]
    for a in ranked:
        a["opportunity"] = round(a["opportunity"], 4)
        a["subcap_ids"] = a["subcap_ids"][:4]
        a["subcap_names"] = a["subcap_names"][:4]
        a["e_ids"] = a["e_ids"][:4]
    return ranked


def compose_platform_narrative(
    *,
    entity_name: str,
    platform_name: str,
    fit_score: float,
    readiness: ReadinessLight,
    state: str,
    breakdown: dict | None,
    excerpts_by_e_id: dict[str, str] | None = None,
    category_names: dict[str, str] | None = None,
) -> str | None:
    """Evidence-rich card narrative: where the entity stands on this
    platform, in verbatim-quoted, E-ID-cited facts (2026-07-06 mandate —
    the card must carry a narrative, not just scores).

    Deterministic (zero-token; the orchestrator's parsed_skipped_llm
    class): every sentence is assembled from engine state + the entity's
    own evidence excerpts. Quotes go through quote_span — verbatim or
    ellipsis-marked whole-clause truncation, never a mid-claim cut.
    Returns None when there is nothing grounded to say (no addressable
    surface), so INSUFFICIENT_EVIDENCE stays the card's single voice.
    """
    from app.services.startup_enrich import quote_span

    bd = breakdown or {}
    tops = list(bd.get("top_subcaps") or [])
    if not tops:
        return None
    excerpts_by_e_id = excerpts_by_e_id or {}

    lines: list[str] = []

    # 1 — standing: the top-opportunity subcap anchors the story.
    top = tops[0]
    # Name only — no raw `(P#C#…)` code parenthetical or bare-id fallback in
    # narrative prose (2026-07-15 cohesion audit; the code is an internal id,
    # not client-facing copy).
    label = str(top.get("name") or "").strip() or "the leading capability gap"
    n = int(bd.get("n_addressable") or len(tops))
    ready_txt = _READINESS_TEXT.get(readiness, "in evaluation")
    # ONE maturity reading (the anchor score) plus the platform's own fit
    # metric; the peer relation is stated in words, not a second number
    # (2026-07-14 operator mandate — the card must read as narrative, not a
    # scorecard opening on three figures).
    s1 = f"{entity_name} scores {top.get('score')} on {label}"
    if top.get("peer_median") is not None:
        try:
            _d = float(top.get("peer_median")) - float(top.get("score"))
        except (TypeError, ValueError):
            _d = 0.0
        _rel = ("below the peer median" if _d > 0.05
                else "ahead of the peer median" if _d < -0.05
                else "in line with the peer median")
        s1 += f", {_rel}"
    s1 += (
        f" — the largest of {n} capability gap"
        f"{'s' if n != 1 else ''} {platform_name} addresses. "
        f"Fit is {fit_score:.0f}/100 and the platform is {ready_txt}."
    )
    lines.append(s1)

    # 2 — stack position from the entity's own evidence (verbatim).
    signals = list(bd.get("stack_signals") or [])
    in_use = next((s for s in signals if s.get("polarity") == "in_use"), None)
    absent_sig = next((s for s in signals if s.get("polarity") == "absent"), None)
    planned = next((s for s in signals if s.get("polarity") == "planned"), None)
    if in_use and in_use.get("excerpt"):
        q = quote_span(in_use["excerpt"], 220)
        if q:
            lines.append(
                f"Their own evidence places {platform_name} in the stack: "
                f"\"{q}\" [{in_use.get('e_id')}]."
            )
    elif bd.get("absent_families"):
        s2 = f"{platform_name} is absent from the detected tech stack — a greenfield entry"
        if absent_sig and absent_sig.get("excerpt"):
            q = quote_span(absent_sig["excerpt"], 200)
            if q:
                s2 += f"; the research corroborates it: \"{q}\" [{absent_sig.get('e_id')}]"
        s2 += "."
        lines.append(s2)
    if planned and planned.get("excerpt"):
        q = quote_span(planned["excerpt"], 200)
        if q:
            lines.append(
                f"Forward motion is already documented: \"{q}\" "
                f"[{planned.get('e_id')}]."
            )

    # 3 — the gap itself, in the evidence's own words.
    quoted = 0
    used_e_ids = {s.get("e_id") for s in signals}
    for t in tops[:3]:
        for e in t.get("e_ids") or []:
            ex = excerpts_by_e_id.get(str(e))
            if not ex or e in used_e_ids:
                continue
            q = quote_span(ex, 220)
            if not q:
                continue
            tlabel = str(t.get("name") or "").strip() or "this capability"
            lines.append(f"On {tlabel}, the record states: \"{q}\" [{e}].")
            used_e_ids.add(e)
            quoted += 1
            break
        if quoted >= 2:
            break

    # 4 — scale context, when known.
    scale = bd.get("scale") or {}
    if scale.get("band") and scale.get("basis"):
        lines.append(
            f"Sizing context: {scale['basis']} — a {scale['band']}-scale "
            "institution, which the greenfield weighting reflects."
        )

    # 5 — the prioritized Zennify opportunity areas.
    areas = opportunity_areas_from_breakdown(bd, category_names)
    if areas:
        # Category NAMES only — never the raw category_id or the `(P#C#…)`
        # subcap-id parenthetical in prose (2026-07-15 cohesion audit).
        _area_names = [str(a.get("name") or "").strip() for a in areas[:2]]
        _area_names = [x for x in _area_names if x]
        if _area_names:
            lines.append(f"Nearest Zennify opportunity: {'; '.join(_area_names)}.")

    if state == "INSUFFICIENT_EVIDENCE":
        lines.append(
            "Evidence coverage on the driving capabilities is thin — treat "
            "this read as directional until research closes the gap."
        )
    return " ".join(lines) if lines else None


def compose_conversation_starter(
    *,
    platform_name: str,
    pillar: str,
    fit_score: float,
    addressable_subcap_ids: list[str],
    prereq_checks: list[PrereqCheck],
    readiness: ReadinessLight,
) -> str | None:
    """Legacy single-string form, byte-compatible with the original
    header + numbered steps + Next-step layout (the contract tests in
    test_platform_story.py and the frontend's fallback line parser both
    pin it). New UIs should prefer ``conversation_starters``."""
    if not addressable_subcap_ids:
        return None

    top = addressable_subcap_ids[0]
    n = len(addressable_subcap_ids)
    others = max(n - 1, 0)
    ready = _READINESS_TEXT.get(readiness, "in evaluation")
    failing = next(
        (c for c in prereq_checks if c.status in ("UNMET", "MISSING")), None)
    partial = next(
        (c for c in prereq_checks if c.status == "PARTIAL"), None)
    pain = failing or partial

    lines: list[str] = [
        (
            f"{platform_name} (pillar {pillar}) addresses {n} subcap"
            f"{'s' if n != 1 else ''}, starting with {top}; "
            f"fit is {fit_score:.0f}/100 and the platform is {ready}."
        ),
        (
            f"1. Discovery: ask how they handle {top} today — what tool, "
            "what owner, what review cadence."
        ),
    ]
    if pain is not None:
        score_str = (
            f"{pain.current_score:.1f}"
            if pain.current_score is not None
            else "no score recorded"
        )
        lines.append(
            f"2. Pain: probe on {pain.required_subcap_id} (prereq "
            f"'{pain.name}': current {score_str} vs. threshold "
            f"{pain.threshold:.1f}, status {pain.status})."
        )
    else:
        lines.append(
            "2. Value: confirm appetite to close the gap this fiscal year — "
            "prerequisites are MET, so the call can move to scoping."
        )
    if others > 0:
        lines.append(
            f"3. Sequence: outline a {n}-subcap roadmap starting at {top} "
            f"and extending to {others} additional subcap"
            f"{'s' if others != 1 else ''}."
        )
    else:
        lines.append(
            f"3. Action: scope a {platform_name} workshop for the single "
            f"high-impact subcap {top}."
        )
    lines.append(
        f"Next step: book a {platform_name} workshop scoped to {pillar}, "
        f"covering the {n}-subcap addressable surface."
    )
    return "\n".join(lines)
