"""L4 — the per-client storyline spine (cohesion, not a global template).

A client's surfaces must tell ONE story, derived from THAT client's own dominant
signals — never a shape stamped onto everyone. This module derives the entity
``Thesis``: the single transformation/competitive narrative that the exec summary
leads with, the findings are ordered to support, the cards' plays stay consistent
with, and the why-now ties its urgency to. Different inputs → different thesis
(FCMA's competitive-defense is not Regions' greenfield-at-largest-LOB is not
Alliant's post-M&A consolidation).

Priority of the spine:
  1. the analyst's OWN answer in ``scqa`` (their derived thesis — the richest,
     most human input; the plan ingests scqa.json as the spine), else
  2. a thesis derived from L1's RANKED signals — competitor footholds in the
     stack, M&A intensity, the dominant gap/strength pillar, the LOB mix.

The Thesis is GROUNDED (built from real names/figures + cited evidence) and
AUDITABLE (``signals`` records what drove the choice), so the storyline is
justifiable and never fabricated. The LLM narrator (nlp/refine) writes the prose
from this spine; the deterministic composer threads its ``through_line`` +
consistent ``play`` so even the offline floor is cohesive, not robotic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.nlp.entity_knowledge import Capability, EntityState

# Salesforce-COMPETING platforms only — CRM / service / experience / marketing /
# low-code workflow. A foothold HERE is a genuine defend-and-expand signal.
# Deliberately EXCLUDES: core-banking/insurance cores (Fiserv, Q2, FIS, Jack
# Henry, Temenos, Mambu, Guidewire, Duck Creek) — not CRM rivals; Salesforce ISVs
# / own products (nCino runs ON Salesforce; MuleSoft, Tableau); and data-infra
# (Snowflake, Databricks). Including those made "defend Salesforce" over-fire on
# 85/95 clients (corpus-measured) — a template, not a derivation.
_COMPETITORS = {
    "servicenow": "ServiceNow", "hubspot": "HubSpot", "pega": "Pega",
    "backbase": "Backbase", "microsoft dynamics": "Microsoft Dynamics",
    "dynamics 365": "Dynamics 365", "adobe experience": "Adobe Experience Cloud",
    "marketo": "Marketo", "oracle cx": "Oracle CX",
}
_MA_RE = re.compile(r"\bacquisition|\bacquired\b|\bmerger\b|\bM&A\b|"
                    r"\bportfolio compan|\broll-?up\b", re.I)
_PILLAR_DOMAIN = {
    "P1": "strategy and governance", "P2": "customer experience",
    "P3": "operations and process", "P4": "the data and technology foundation",
}


@dataclass
class Thesis:
    """The one per-client narrative spine, grounded and auditable."""
    kind: str                       # analyst | competitive_defense | post_ma |
    #                                 greenfield_lob | expand_strength | modernize
    headline: str                   # the thesis-first sentence the exec leads with
    through_line: str               # a short hook the surfaces weave for cohesion
    play: str                       # the consistent recommended play/system
    pillars: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)   # what drove the choice (audit)


def _pillar_of(caps: list[Capability]) -> str | None:
    """The pillar most represented among a ranked capability slice."""
    counts: dict[str, int] = {}
    for c in caps:
        counts[c.pillar] = counts.get(c.pillar, 0) + 1
    return max(counts, key=lambda p: counts[p]) if counts else None


def _competitor_footholds(state: EntityState) -> list[str]:
    hay = " ".join(str(t) for t in (state.tech_stack or [])).lower()
    return sorted({name for key, name in _COMPETITORS.items() if key in hay})


def _ma_intensity(state: EntityState) -> int:
    firm = state.firmographics or {}
    text = " ".join(str(firm.get(k) or "") for k in ("narrative_md",))
    pf = firm.get("parsed_facts") or {}
    n = len(_MA_RE.findall(text))
    for key in ("acquisitions", "acquisition_count", "ma_count"):
        v = pf.get(key)
        if isinstance(v, int):
            n = max(n, v)
        elif isinstance(v, list):
            n = max(n, len(v))
    return n


def _scqa_answer(state: EntityState) -> str:
    """The analyst's own answer/recommendation from scqa (the spine, if present)."""
    sc = state.scqa or {}
    if not isinstance(sc, dict):
        return ""
    for key in ("answer", "a", "recommendation", "so_what", "thesis"):
        v = sc.get(key)
        if isinstance(v, str) and len(v.strip()) >= 40:
            return v.strip()
    return ""


def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return (s[:n].rsplit(" ", 1)[0] + "…") if len(s) > n else s


def derive_thesis(state: EntityState) -> Thesis:
    """Derive the per-client storyline spine from the analyst's scqa (preferred)
    or, absent that, from the ranked signals. Always grounded + auditable."""
    strengths = state.ranked_strengths[:6]
    gaps = state.ranked_gaps[:6]
    anchors = state.evidenced_anchors[:6]
    ev = [e for c in anchors for e in (c.evidence_ids or [])][:6]
    competitors = _competitor_footholds(state)
    ma = _ma_intensity(state)
    strength_pillar = _pillar_of(strengths)
    gap_pillar = _pillar_of(gaps)
    signals = {"competitors": competitors, "ma_intensity": ma,
               "strength_pillar": strength_pillar, "gap_pillar": gap_pillar,
               "n_strengths": len(state.ranked_strengths),
               "n_gaps": len(state.ranked_gaps)}

    # 1) the analyst's own thesis is the richest spine when present
    answer = _scqa_answer(state)
    if answer:
        return Thesis(
            kind="analyst", headline=_clip(answer, 240),
            through_line="the roadmap the assessment lays out",
            play="the analyst's sequenced platform roadmap",
            pillars=sorted({c.pillar for c in anchors}), evidence_ids=ev,
            signals={**signals, "source": "scqa"})

    # 2) SCORE each narrative from the ranked signals; the STRONGEST wins, so no
    # single kind is stamped on everyone. competitive-defense needs a real
    # SF-competitor foothold (tight set) AND a customer-facing pillar in play —
    # it no longer fires on any vendor mention (that skewed 85/95 to defense).
    p4_gaps = sum(1 for g in gaps if g.pillar == "P4")
    cust_facing = (gap_pillar in {"P1", "P2", "P4"}) or (strength_pillar in {"P1", "P2"})
    scores = {
        "competitive_defense": (2 * len(competitors)) if (competitors and cust_facing) else 0,
        "post_ma": 3 if ma >= 3 else 0,
        "greenfield_lob": 3 if (gap_pillar == "P4" and p4_gaps >= 2) else 0,
        "expand_strength": 3 if (strength_pillar and len(strengths) >= max(2, len(gaps))) else 0,
        "modernize": 1,
    }
    # tie-break order does NOT favour competitive_defense (counters the old skew)
    order = ["post_ma", "greenfield_lob", "expand_strength", "competitive_defense", "modernize"]
    kind = max(order, key=lambda k: (scores[k], -order.index(k)))
    signals["scores"] = scores

    if kind == "competitive_defense":
        names = ", ".join(competitors[:2])
        dom = _PILLAR_DOMAIN.get(gap_pillar or strength_pillar or "P2", "the estate")
        return Thesis(
            kind="competitive_defense",
            headline=(f"{state.name} must expand its Salesforce layer in {dom} "
                      f"before {names} hardens a competing foothold"),
            through_line=f"defending and expanding the platform against {names}",
            play=f"prove Salesforce Agentforce and Einstein parity where {names} is gaining ground",
            pillars=[p for p in (strength_pillar, gap_pillar) if p], evidence_ids=ev,
            signals=signals)
    if kind == "post_ma":
        return Thesis(
            kind="post_ma",
            headline=(f"{state.name} can unify the estate that {ma}+ acquisitions "
                      f"left fragmented, then layer experience and AI on one core"),
            through_line="consolidating the post-acquisition estate onto one layer",
            play="stand up MuleSoft as the integration backbone, then Data Cloud",
            pillars=["P4"], evidence_ids=ev, signals=signals)
    if kind == "greenfield_lob":
        return Thesis(
            kind="greenfield_lob",
            headline=(f"{state.name}'s widest opportunity is a unified "
                      f"{_PILLAR_DOMAIN['P4']} — a greenfield to build from"),
            through_line="building the unified data and technology foundation",
            play="establish Salesforce Data Cloud as the unified data layer the others inherit",
            pillars=["P4"], evidence_ids=ev, signals=signals)
    if kind == "expand_strength":
        dom = _PILLAR_DOMAIN.get(strength_pillar, "its strongest area")
        return Thesis(
            kind="expand_strength",
            headline=(f"{state.name} can lead from proven strength in {dom} and "
                      f"extend that credibility into the adjacent gaps"),
            through_line=f"expanding from the proven strength in {dom}",
            play=f"scale the {dom} strength on the Salesforce core into adjacent capabilities",
            pillars=[p for p in (strength_pillar, gap_pillar) if p], evidence_ids=ev,
            signals=signals)
    dom = _PILLAR_DOMAIN.get(gap_pillar or "P1", "the binding gap")
    return Thesis(
        kind="modernize",
        headline=(f"{state.name}'s near-term priority is to close the binding "
                  f"gap in {dom} and the capabilities that build on it"),
        through_line=f"closing the binding gap in {dom}",
        play=f"sequence the {dom} modernization on Salesforce first",
        pillars=[gap_pillar] if gap_pillar else [], evidence_ids=ev, signals=signals)
