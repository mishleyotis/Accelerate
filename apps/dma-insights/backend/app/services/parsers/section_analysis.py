"""D2 insight-card derivation platform (shared by ingest + DB re-derive).

Original scope: parse `section_analysis_#.json` → D2 insight cards.
These files (under `04_reports/`, `06_reports/research_analysis/`, or
`02_research_workbook/`) carry, per report section, a `top_findings[]`
list — structured, evidence-cited insight material:

    {id: "F-001", title, observation ("… [E-001:F3] …"),
     maturity ("P2C4 Personalization ceiling capped at M1-M2"),
     zennify ("Salesforce Sales Cloud — immediate deal opp")}

2026-07-02 (plan Part 5.1) this module became the SHARED derivation
platform for the whole D2 ladder so the ingest path
(`parsers/dma_package.py`) and the DB re-derive
(`scripts/derive_insights.py`) cannot drift:

    rung 1  insights_from_profile_findings   (Client Profile Research
            Report — 82/113 packages; previously fed ZERO cards)
    rung 2  parse_section_analyses           (6/113 packages)
    rung 3  insights_from_recommendations    (46/113 packages)
    rung 4  insights_from_category_gaps      (last resort, capped 4)
    plus    insights_from_zennify_opportunities (generated OPPORTUNITY
            cards from `client_knowledge_sections`
            artifact_kind='zennify_opportunity' rows — fully evidenced
            via their trigger_evidence E-IDs, or not emitted)

Interconnection helpers (`SubcapClassifier` multi-`affects[]`,
`counter_evidence_ids`, `combine_insight_rungs`, `basis_marker`) live
here too — both producers import them.

Card field mapping (unchanged contract):

    ic_id            = finding id (deduped across section files)
    title            = title
    what_text        = observation              (WHAT we found)
    why_text         = maturity                 (WHY — the capability ceiling)
    so_what_text     = zennify                  (SO-WHAT — the Zennify action)
    linked_subcap_id = P#C# parsed from maturity / observation  (NOT NULL)
    linked_e_ids     = E-NNN parsed from observation
    severity         = derived from the maturity M-band (M1→high … M4/5→low)

Pure / no DB. Returns [] when no parseable source exists.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.schemas.package import InsightCardRow
from app.services.parsers.package_recommendations import _rec_id
from app.services.startup_enrich import quote_span
from app.services.text_hygiene import plain as _plain_scrub

_E_ID_RE = re.compile(r"\bE-\d{1,4}\b")
_SUBCAP_RE = re.compile(r"\bP\d+C\d+(?:\.\d+)*\b")
_M_BAND_RE = re.compile(r"\bM([1-5])\b")
_VALID_SEVERITY = ("critical", "high", "medium", "low")


def _extract_e_ids(text: str) -> list[str]:
    # observation cites look like "[E-001:F3]" — keep just the E-NNN.
    return sorted(set(_E_ID_RE.findall(text or "")))


def _first_subcap(*texts: str) -> str | None:
    for t in texts:
        m = _SUBCAP_RE.search(t or "")
        if m:
            return m.group(0)
    return None


def _severity_from_maturity(maturity: str) -> str:
    """Lowest M-band mentioned → severity. A finding pinned at M1/M2 is a
    material gap (high/medium); M4/M5 is a strength claim (low)."""
    bands = [int(m) for m in _M_BAND_RE.findall(maturity or "")]
    if not bands:
        return "medium"
    lo = min(bands)
    if lo <= 1:
        return "high"
    if lo == 2:
        return "medium"
    return "low"  # M3+ — capability is at/above mid maturity


def _coerce(v: object) -> str:
    return str(v).strip() if v is not None else ""


_PILLAR_SUBCAP_RE = re.compile(r"P\d+C\d+(?:\.\d+)*")
# LOB-family leaf suffixes (Insurance Carrier IC / Brokerage IB / Credit Union
# CU / Retail Bank RB / Wealth Mgmt WM / Commercial Bank CB / Private Bank PB) —
# NO_EVIDENCE placeholder leaves; an anchor on one rolls up to its parent
# subcategory so the sibling-aware evidence matcher can resolve it (plan S5).
_LOB_LEAF_RE = re.compile(r"\.(?:IC|IB|CU|RB|WM|CB|PB)\d*$")


# Bot template/branding markers ("[[ZENNIFY]]: ..." prefix or
# "... [[ZENNIFY]]" suffix) leak into rec titles in a third of the
# corpus. Strip them at the SOURCE builder so ingest-created and
# DB-re-derived cards present identically (2026-06-10: the strip
# originally lived only in scripts/derive_insights.py and every
# re-ingest clobbered it back).
_TEMPLATE_MARKER_RE = re.compile(r"\s*\[\[[A-Z+ ]+\]\]\s*:?\s*")
# Single-bracket variant ("Hire Chief Data Officer [ZENNIFY]") — same
# bot branding, different delimiter. E-IDs ("[E-016]") are NOT markers.
_TEMPLATE_MARKER_SINGLE_RE = re.compile(r"\s*\[(?!E-)[A-Z+ ]{3,}\]\s*:?\s*")


def strip_template_markers(t: str | None) -> str:
    out = _TEMPLATE_MARKER_RE.sub(" ", t or "")
    out = _TEMPLATE_MARKER_SINGLE_RE.sub(" ", out)
    return out.strip(" :—-").strip()


# `insight_cards.linked_e_ids` is VARCHAR(16)[]. Several packages put
# whole fact strings in their evidence lists ("E-015:F2 Consent order
# cites BSA/AML…") — Bank of Utah's re-ingest aborted on the column
# overflow (2026-06-10). Keep only the leading E-ID (optionally with
# its :F# fact suffix); drop anything that doesn't start with one.
_E_ID_PREFIX_RE = re.compile(r"^(E-\d{1,4}(?::F\d{1,3})?)")


def normalize_e_ids(values: list) -> list[str]:
    out: list[str] = []
    for v in values or []:
        if not isinstance(v, str):
            continue
        m = _E_ID_PREFIX_RE.match(v.strip())
        if m:
            out.append(m.group(1)[:16])
    return out


def _severity_from_priority(priority: object) -> str:
    s = str(priority or "").strip().lower()
    if not s:
        return "medium"
    if any(k in s for k in ("p0", "h1", "critical", "crit", "urgent")) or s in ("high", "1"):
        return "high"
    if any(k in s for k in ("p2", "h3", "low")) or s == "3":
        return "low"
    return "medium"


def insights_from_recommendations(recs: list) -> list[InsightCardRow]:
    """DERIVE D2 insight cards from parsed recommendations (the plan's D2
    source) when no section_analysis top_findings shipped.

    Each recommendation carries the report's finding (root_cause) + the
    Zennify solution, so it maps onto an insight card's WHAT/WHY/SO-WHAT.
    Only recs that can be anchored to a P#C# subcap are promoted
    (linked_subcap_id is NOT NULL)."""
    out: list[InsightCardRow] = []
    seen: set[str] = set()
    for r in recs:
        d = r.model_dump() if hasattr(r, "model_dump") else {}
        rc = (getattr(r, "root_cause", None) or {}) if not isinstance(r, dict) else {}
        sol = (getattr(r, "solution", None) or {})
        # Find a subcap anchor across the rec's text/extra fields.
        blob = " ".join(str(d.get(k, "")) for k in (
            "priority_gap", "target_categories", "gaps", "capabilities_impacted",
            "priority_category", "category",
        ))
        blob += " " + str(rc.get("scoring_impact") or rc.get("finding") or "")
        m = _PILLAR_SUBCAP_RE.search(blob)
        if m is None:
            continue
        ic_id = f"INS-{getattr(r, 'id', '') or len(out) + 1}"[:16]
        if ic_id in seen:
            continue
        seen.add(ic_id)
        what = strip_template_markers(
            _coerce(rc.get("finding") or rc.get("gap_description"))
            or _coerce(getattr(r, "title", None)))
        if not what:
            continue
        evidence = d.get("evidence_ids") or d.get("evidence") or []
        # Never ship a blank WHY: when the rec carries no peer benchmark /
        # scoring impact, ground it in the anchored subcap rather than leaving
        # the card's WHY empty.
        why = _coerce(d.get("peer_benchmark") or d.get("peer_context")
                      or rc.get("scoring_impact"))
        if not why:
            why = (f"Anchored to {m.group(0)} — see the heatmap for the "
                   f"subcap-level maturity detail behind this recommendation.")
        out.append(InsightCardRow(
            ic_id=ic_id,
            severity=_severity_from_priority(getattr(r, "priority", None)),
            title=(strip_template_markers(getattr(r, "title", None))
                   or "(untitled)")[:500],
            what_text=what,
            why_text=why,
            so_what_text=strip_template_markers(_coerce(sol.get("description"))),
            linked_subcap_id=m.group(0)[:32],
            linked_e_ids=normalize_e_ids(evidence)[:20],
            # Faithful single link: this card is derived from exactly one rec.
            source_rec_id=(_rec_id(getattr(r, "id", "")) or None),
        ))
    return out


def insights_from_category_gaps(category_scores: list, *, cap: int = 4) -> list[InsightCardRow]:
    """Universal DERIVED last resort (plan Part 5.1 rung 4): turn the
    entity's own below-par category scores into insight cards. Faithful —
    every field is computed from EXTRACTED scores, nothing fabricated.

    2026-07-02 audit remediation: DEMOTED to last resort — the audit
    measured 74.6% of all 630 cards as category-gap restatements, so the
    default cap drops 12 → 4 and the copy rotates across distinct
    phrasings (template-family ceiling <10%). Used only when the
    profile-findings / section-analysis / recommendations rungs all
    produced nothing.

    A category is an insight when it is materially below the peer median
    (gap ≤ -0.5) or at low absolute maturity (< 2.0). Anchored to the
    category id (NOT NULL)."""
    scored: list[tuple[float, Any]] = []
    for c in category_scores:
        score = getattr(c, "score", None)
        if score is None:
            continue
        pm = getattr(c, "peer_median", None)
        gap = (score - pm) if pm is not None else None
        is_gap = (gap is not None and gap <= -0.5) or score < 2.0
        if is_gap:
            # rank by severity: bigger negative gap / lower score first.
            rank = gap if gap is not None else (score - 5.0)
            scored.append((rank, c))
    scored.sort(key=lambda t: t[0])

    # Relative-priority fallback: a high-maturity entity (e.g. CalPrivate)
    # can sit at/above the peer median on every category, so the strict
    # gap rule yields nothing and D2 renders empty — which reads as broken.
    # When that happens, surface the entity's own *relative-lowest* scored
    # categories (the legitimate "where to focus next" priorities) instead
    # of fabricating a gap. Honest: every field is the real score, and the
    # copy states the actual standing (at/above median) rather than calling
    # it a gap.
    relative_mode = False
    if not scored:
        ranked: list[tuple[float, Any]] = []
        for c in category_scores:
            score = getattr(c, "score", None)
            if score is None:
                continue
            pm = getattr(c, "peer_median", None)
            rank = (score - pm) if pm is not None else score
            ranked.append((rank, c))
        ranked.sort(key=lambda t: t[0])
        scored = ranked[:min(3, len(ranked))]
        relative_mode = True

    out: list[InsightCardRow] = []
    for idx, (_, c) in enumerate(scored[:cap]):
        cat = getattr(c, "category_id", None)
        if not cat:
            continue
        score = c.score
        pm = getattr(c, "peer_median", None)
        name = getattr(c, "category_name", None) or category_display_name(cat)
        delta = round(score - pm, 2) if pm is not None else None
        if relative_mode and (delta is None or delta >= 0):
            # At/above the peer median — a STRENGTH, not a gap. The strength is
            # carried entirely by the copy ("strength to extend", "at/above the
            # peer median"); the severity stays the LOWEST valid urgency ("low" →
            # the UI's neutral MONITOR pill), never a "medium" that reads like a
            # deficit (the 2026-06-23 corpus audit found these mislabeled).
            # Severity MUST be one of the four canonical values — the DB CHECK
            # `insight_cards_severity_chk` and the persist allowlist reject
            # anything else, which would silently drop every card of an
            # all-strength (high-maturity) entity and empty its Insights surface.
            standing = (
                f"at/above the peer median ({pm:.1f}, {delta:+.1f})"
                if delta is not None else "a leading internal capability"
            )
            what = f"{name} scores {score:.1f}/5 — {standing}."
            why_variants = (
                "A relative strength for this entity — already at or ahead of "
                "the peer cohort.",
                f"At {score:.1f}/5 this is one of the institution's strongest "
                f"categories relative to its cohort — a credibility anchor, "
                f"not a deficit.",
                (f"The cohort sits at {pm:.1f} here" if pm is not None
                 else "No cohort benchmark trails this category")
                + " — this category leads rather than lags.",
            )
            so_what_variants = (
                f"Extend the {name} strength: it already leads at "
                f"{score:.1f}/5 — reinforce it to widen the advantage while "
                f"peers catch up, and lean on it as a proof point in "
                f"conversations.",
                f"Extend {name} into adjacent categories: a proven {score:.1f}/5 "
                f"operating pattern is the cheapest lever for lifting the "
                f"weaker pillars around it.",
                f"Adopt {name} as the reference story in executive "
                f"conversations — it is the institution's demonstrated "
                f"{score:.1f}/5 proof point.",
            )
            why = why_variants[idx % len(why_variants)]
            so_what = so_what_variants[idx % len(so_what_variants)]
            severity = "low"
            title = f"{name}: strength to extend"
            ic_prefix = "STR"
        elif pm is not None and delta is not None and delta < 0:
            # Below the peer median — a genuine competitive gap. The copy
            # rotates across distinct honest phrasings (audit: one family
            # covered 74.6% of the corpus's cards) — every variant carries
            # the same real numbers, only the sentence shape differs.
            what = f"{name} scores {score:.1f}/5 vs a peer median of {pm:.1f} ({delta:+.1f})."
            severity = "high" if (delta <= -1.0 or score < 1.5) else "medium"
            pts = f"point{'s' if abs(delta) != 1 else ''}"
            why_variants = (
                f"{name} trails the peer cohort by {abs(delta):.1f} {pts} — a "
                f"competitive maturity gap that compounds across the capabilities it supports.",
                f"The cohort median for {name} is {pm:.1f}; at {score:.1f} this "
                f"institution operates {abs(delta):.1f} {pts} behind the peers it "
                f"competes with for the same customers.",
                f"Peers score {pm:.1f} on {name} against this institution's "
                f"{score:.1f} — the {abs(delta):.1f}-point shortfall shows up in "
                f"every sub-capability rolled into this category.",
                f"At {score:.1f}/5, {name} is the widest measured deficit vs the "
                f"peer median ({pm:.1f}) among this run's remaining categories.",
            )
            so_what_variants = (
                f"Close the {name} gap: sequence the lowest-scoring subcaps "
                f"here first to recover parity with peers — this is where "
                f"targeted investment moves the overall score most.",
                f"Prioritize {name}: recovering the {abs(delta):.1f}-point deficit "
                f"against the cohort moves overall maturity more than any "
                f"at-parity category can.",
                f"Start with {name} — a focused program here recovers peer parity "
                f"fastest and raises the floor for the capabilities around it.",
                f"Sequence {name} into the near-term roadmap: the {abs(delta):.1f}-"
                f"point peer gap is measurable, so progress is provable "
                f"quarter over quarter.",
            )
            why = why_variants[idx % len(why_variants)]
            so_what = so_what_variants[idx % len(so_what_variants)]
            title = (f"{name} trails peers by {abs(delta):.1f}"
                     if abs(delta) >= 0.1 else f"{name} below peer parity")
            ic_prefix = "GAP"
        else:
            # No peer benchmark — flag on low absolute maturity.
            what = f"{name} scores {score:.1f}/5 — early-stage maturity."
            severity = "high" if score < 1.5 else "medium"
            why_variants = (
                f"{name} sits at early-stage maturity; the foundational "
                f"capabilities here are not yet consistently in place.",
                f"A {score:.1f}/5 on {name} means the basics are still being "
                f"stood up — higher-order capability can't compound until "
                f"this floor is in place.",
                f"{name} is this run's least-established category at "
                f"{score:.1f}/5 — no peer benchmark exists for the cohort, "
                f"so the absolute maturity level is the honest signal.",
            )
            so_what_variants = (
                f"Stand up foundational {name} capability — at {score:.1f}/5 "
                f"the basics aren't established; target quick-win subcaps to "
                f"lift the floor before building higher-order capability.",
                f"Build the {name} floor first: pick the two lowest subcaps in "
                f"this category and close them before layering anything on top.",
                f"Pilot one contained {name} initiative to establish the "
                f"operating pattern, then extend it across the category.",
            )
            why = why_variants[idx % len(why_variants)]
            so_what = so_what_variants[idx % len(so_what_variants)]
            title = f"{name}: early-stage maturity"
            ic_prefix = "MAT"
        out.append(InsightCardRow(
            ic_id=f"{ic_prefix}-{cat}"[:16],
            severity=severity,
            title=title[:500],
            what_text=what,
            why_text=why,
            so_what_text=so_what,
            linked_subcap_id=cat[:32],
        ))
    return out


def parse_section_analyses(root: Path) -> list[InsightCardRow]:
    """Aggregate `top_findings` across every section_analysis_*.json in the
    package into insight-card rows. ic_ids are made unique per package."""
    files = sorted(root.glob("**/section_analysis_*.json"))
    out: list[InsightCardRow] = []
    seen_ids: set[str] = set()
    for fi, path in enumerate(files):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        cards_from_section_analysis_payload(data, fi, out, seen_ids)
    return out


def cards_from_section_analysis_payload(
    data: Any, fi: int, out: list[InsightCardRow], seen_ids: set[str],
) -> None:
    """One loaded section_analysis payload → cards appended onto ``out``.

    Shared by the path-glob ingest rung above AND the DB re-derive
    (`scripts/derive_insights.py` mines the same JSONs back out of the
    compressed ``raw_artifacts`` store) so the two paths cannot drift.
    """
    if isinstance(data, dict):
        protocol = data.get("pre_write_protocol") or data.get("pre_write_questions") or {}
        sec_why = _coerce(protocol.get("why_important_to_AE")) if isinstance(protocol, dict) else ""
        sec_sowhat = _coerce(protocol.get("zennify_implication")) if isinstance(protocol, dict) else ""
        for finding in data.get("top_findings") or []:
            if not isinstance(finding, dict):
                continue
            # Key drift across the corpus: title|finding|headline,
            # maturity|maturity_implication, zennify|zennify_relevance|
            # zennify_implication, evidence cites in-text OR evidence_ids|
            # evidence list.
            observation = _coerce(finding.get("observation") or finding.get("finding"))
            title = _coerce(
                finding.get("title") or finding.get("finding")
                or finding.get("headline"))
            maturity = _coerce(
                finding.get("maturity") or finding.get("maturity_implication"))
            if not observation or not title:
                continue
            subcap = _first_subcap(maturity, observation, title)
            if subcap is None:
                continue  # linked_subcap_id is NOT NULL — skip un-anchorable
            ic_id = _coerce(finding.get("id")) or f"F-{fi}-{len(out) + 1}"
            if ic_id in seen_ids:
                ic_id = f"S{fi + 1}-{ic_id}"
            ic_id = ic_id[:16]
            if ic_id in seen_ids:
                continue
            seen_ids.add(ic_id)
            ev = finding.get("evidence_ids") or finding.get("evidence") or []
            e_ids = _extract_e_ids(observation) or normalize_e_ids(ev)
            out.append(InsightCardRow(
                ic_id=ic_id,
                severity=_severity_from_maturity(maturity),
                title=title[:500],
                what_text=observation,
                why_text=maturity or sec_why,
                so_what_text=actionize_so_what(_coerce(
                    finding.get("zennify") or finding.get("zennify_relevance")
                    or finding.get("zennify_implication")) or sec_sowhat),
                linked_subcap_id=subcap[:32],
                linked_e_ids=e_ids[:20],
            ))

        # priority_/caution_capabilities variant (Penderfund): each entry is
        # already subcap-anchored via `cap_id`.
        for kind, items in (
            ("priority", data.get("priority_capabilities")),
            ("caution", data.get("caution_capabilities")),
        ):
            if not isinstance(items, list):
                continue
            for cap in items:
                if not isinstance(cap, dict):
                    continue
                cid = _coerce(cap.get("cap_id") or cap.get("subcap_id"))
                m = _SUBCAP_RE.search(cid) if cid else None
                if m is None:
                    continue
                name = _coerce(cap.get("name")) or m.group(0)
                ic_id = f"{kind[0].upper()}{fi}-{m.group(0)}"[:16]
                if ic_id in seen_ids:
                    continue
                seen_ids.add(ic_id)
                what = _coerce(
                    cap.get("notes") or cap.get("missing") or cap.get("guidance")
                ) or name
                out.append(InsightCardRow(
                    ic_id=ic_id,
                    # caution = a likely cap/gap (higher severity); priority =
                    # a confirmed strength to lead with (low).
                    severity="medium" if kind == "caution" else "low",
                    title=name[:500],
                    what_text=what,
                    why_text=_coerce(cap.get("likely_cap") or cap.get("confidence")),
                    so_what_text=actionize_so_what(_coerce(cap.get("guidance"))),
                    linked_subcap_id=m.group(0)[:32],
                ))


# ═══════════════════════════════════════════════════════════════════
# Part 5.1 shared D2 platform — profile-findings rung, zennify
# opportunities, subcap classifier, rung combiner, counter-evidence.
# Imported by BOTH parsers/dma_package.py (ingest) and
# scripts/derive_insights.py (DB re-derive) so the ladders can't drift.
# ═══════════════════════════════════════════════════════════════════

# Canonical v7 category display names — the DB fallback when
# `ccg_categories.name` is a placeholder (the loaded catalogue carries
# junk names for most versions; packages carry real ones at ingest).
# Curated from the corpus's own export_category_summary.csv modal names.
CATEGORY_FALLBACK_NAMES: dict[str, str] = {
    "P1C1": "Digital Strategy & Vision",
    "P1C2": "Governance & Risk",
    "P1C3": "Innovation & Investment",
    "P1C4": "Culture & Change",
    "P1C5": "ESG & Sustainability",
    "P2C1": "Digital Channels",
    "P2C2": "Customer Journeys & Servicing",
    "P2C3": "Segment & Line-of-Business CX",
    "P2C4": "CX & Personalization",
    "P2C5": "Advice & Wealth Experience",
    "P3C1": "Core Automation",
    "P3C2": "Operational Workflow & Risk",
    "P3C3": "Compliance & Surveillance",
    "P3C4": "Business Resilience & Third-Party Management",
    "P4C1": "Data Management & Governance",
    "P4C2": "Analytics & AI",
    "P4C3": "Architecture & Cloud",
    "P4C4": "Cybersecurity & Privacy",
    "P4C5": "Emerging Technology",
}


def category_display_name(cat_or_subcap_id: str | None) -> str:
    """Human name for a category (or a subcap's category); id when unknown."""
    cid = (cat_or_subcap_id or "").split(".")[0][:8]
    return CATEGORY_FALLBACK_NAMES.get(cid, cat_or_subcap_id or "")


def theme_for_anchor(anchor: str | None) -> str | None:
    """Short classification label for grouping/filters (insight_cards.theme)."""
    cid = (anchor or "").split(".")[0][:8]
    name = CATEGORY_FALLBACK_NAMES.get(cid)
    return name


@dataclass
class ProfileFinding:
    """One mined Client Profile Research Report finding.

    Produced by ``client_profile.mine_profile_findings`` (ingest) and by
    ``profile_finding_from_quote`` over persisted ``focus_areas`` rows
    (DB re-derive) — the same normalized shape either way.
    """

    title: str
    observation: str
    maturity: str = ""       # WHY raw — the report's ceiling/cap clause
    zennify: str = ""        # SO-WHAT raw — the report's Zennify play
    finding_id: str | None = None
    e_ids: list[str] = field(default_factory=list)
    subcap_refs: list[str] = field(default_factory=list)
    page: int | None = None
    # key_findings | strategic_priority | digital_evolution | tech_landscape
    source_kind: str = "key_findings"


_FINDING_ID_RE = re.compile(r"^[A-Z]{1,3}-?\d{1,4}$")
_MATURITY_HINT_RE = re.compile(
    r"ceiling|\bcapp?e?d?\b|\bM[1-5]\b|maturity|\bCRITICAL\b", re.I)
_OFFERING_HINT_RE = re.compile(
    r"salesforce|data\s+cloud|marketing\s+cloud|service\s+cloud|"
    r"financial\s+services\s+cloud|experience\s+cloud|sales\s+cloud|"
    r"mulesoft|tableau|databricks|twilio|ncino|agentforce|einstein|"
    r"zennify|slack|\bCRM\b|\bFSC\b|mosaic", re.I)
_PIPELINE_META_LIGHT_RE = re.compile(
    r"SECTION\s+\d+\s+COMPLETE|Assessment\s+ID\s+DMA-|Evidence\s+Mode:", re.I)
# Report-about-itself preambles ("Each finding includes a quantified
# observation…", "The following table summarizes…") — section furniture,
# never a client finding. Also revision-note rows ("[Updated: 1 gap
# Resolved…]", "[Revised with Explorium T1 validation…]") and register
# preambles ("All gaps below have been validated…").
_META_PROSE_RE = re.compile(
    r"^(?:each\s+(?:finding|row|entry)|the\s+following|this\s+(?:section|"
    r"table|report|document)|these\s+findings|below\s+(?:is|are)|"
    r"the\s+table\s+below|findings\s+are\s+(?:listed|ranked|ordered)|"
    r"all\s+(?:gaps|findings|items|rows)\s+below|"
    r"\[?\s*(?:updated|revised|note)\s*[:\]])",
    re.I,
)

# Action-cue detector matching the nlp.quality rubric's actionability
# dimension — a SO-WHAT without one gets the honest "Recommended play:"
# framing (it IS the analyst's recommended move).
_ACTION_CUE_RE = re.compile(
    r"\b(?:should|recommend(?:s|ed)?|next\s+steps?|prioriti[sz]e|must|"
    r"requires?|would\s+enable|we\s+suggest)\b"
    r"|^(?:Deploy|Implement|Launch|Consolidate|Migrate|Establish|Build|"
    r"Adopt|Pilot|Sequence|Start|Stand\s+up|Close|Extend|Modernize|"
    r"Recommended)\b",
    re.IGNORECASE,
)


def actionize_so_what(so_what: str) -> str:
    """Frame a SO-WHAT as the next move when it lacks an action cue.

    The analyst's zennify column often names the play without a verb
    ("Salesforce Sales Cloud — immediate deal opp"); prefixing
    "Recommended play:" is honest (it is literally the report's
    recommended play) and satisfies the AE-actionability rubric."""
    s = (so_what or "").strip()
    if not s or _ACTION_CUE_RE.search(s):
        return s
    if s[-1] not in ".!?":
        s += "."
    return f"Recommended play: {s}"
# Section headings that leak into the title slot ("2 Top Findings",
# "Key Findings with Zennify Relevance", "Strategic Priorities") — never
# a card title; the observation's own lead becomes the title instead.
_GENERIC_HEADING_RE = re.compile(
    r"^\d*\s*(?:top|key)\s+findings?\b|^critical\s+gaps?\b|"
    r"^strategic\s+(?:priorit|imperativ|objectiv)|^focus\s+areas?\b|"
    r"^digital\s+evolution\b|^technology\s+landscape\b|findings?\s+with\b",
    re.I,
)
_BRACKET_EID_RE = re.compile(r"\bE-?(\d{2,4})\b", re.I)


def _profile_e_ids(text: str) -> list[str]:
    """All E-IDs in profile prose, normalised ``E-###`` (E028 → E-028)."""
    out: list[str] = []
    for m in _BRACKET_EID_RE.finditer(text or ""):
        eid = f"E-{m.group(1)}"
        if eid not in out:
            out.append(eid)
    return out


def profile_finding_from_quote(
    title: str | None,
    quote: str | None,
    *,
    page: int | None = None,
    source_kind: str = "key_findings",
) -> ProfileFinding | None:
    """Normalize one Client Profile quote/row into a :class:`ProfileFinding`.

    Handles the corpus's structured 5-column findings-table rows
    (``F-001 | Title | Observation [E-027] | P1C1 ceiling M3+ | Zennify
    play``) AND plain narrative paragraphs. Never fabricates — returns
    None for pipeline metadata or sub-substantial text.
    """
    raw = re.sub(r"\s+", " ", (quote or "")).strip()
    if not raw or _PIPELINE_META_LIGHT_RE.search(raw):
        return None
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    finding_id: str | None = None
    observation = raw
    maturity = ""
    zennify = ""
    row_title = (title or "").strip()
    if len(parts) >= 3:
        # Structured row. Leading token may be the finding id.
        if _FINDING_ID_RE.match(parts[0]):
            finding_id = parts[0]
            parts = parts[1:]
        if len(parts) >= 2:
            row_title = parts[0][:200] if len(parts[0]) <= 200 else row_title
            observation = parts[1]
            for extra in parts[2:]:
                if not maturity and _MATURITY_HINT_RE.search(extra):
                    maturity = extra
                elif not zennify:
                    zennify = extra
                else:
                    zennify = f"{zennify} — {extra}"
        else:
            observation = parts[0]
    elif len(parts) == 2:
        row_title = parts[0][:200] if len(parts[0]) <= 120 else row_title
        observation = parts[1] if len(parts[0]) <= 120 else raw
    # Unstructured paragraphs often lead with the finding id and a titled
    # lead clause ("F-001: Acuity's agent-centric digital ecosystem …" /
    # "Data Governance Gap: No Chief Data Officer identified. …"). The
    # separator can also be a bare space ("F-004 GenAI Governance …").
    m_id = re.match(r"^([A-Z]{1,3}-\d{1,4})[:.\-]?\s+", observation)
    if m_id:
        finding_id = finding_id or m_id.group(1)
        observation = observation[m_id.end():].strip()
    generic_title = bool(
        not row_title
        or _FINDING_ID_RE.match(row_title)
        or len(row_title) > 120
        or _GENERIC_HEADING_RE.search(row_title)
        or not row_title[:1].isupper()
    )
    if not maturity and not zennify and generic_title:
        m_lead = re.match(r"^([A-Z][^:.]{8,90}):\s+\S", observation)
        if m_lead:
            row_title = m_lead.group(1).strip()
            generic_title = False
    if len(observation) < 24 or _META_PROSE_RE.match(observation):
        return None
    # Heading-shaped fragments ("Strategic Objective → Zennify Solution
    # Alignment") — no digit, no clause structure, under 10 words —
    # are section furniture, not findings.
    if (len(observation.split()) < 10
            and not re.search(r"\d|[:,;]|\bE-\d", observation)):
        return None
    if generic_title:
        # Section headings ("2 Top Findings") / id cells carry no meaning
        # as card titles — compress the observation itself (nlp.titlecraft
        # SVO core) so the card names the actual capability/system.
        from app.services.nlp.titlecraft import make_title
        row_title = make_title(observation, max_chars=90) or observation[:90]
        # A too-aggressive SVO core ("Acuity has given $28", "New client
        # onboarding reduced to") reads as a data bug — fall back to the
        # observation's own lead clause.
        if (len(row_title) < 24
                or re.search(r"[$€£]\s?\d+(?:\.\d+)?$", row_title)
                or re.search(r"\b(?:to|of|for|with|in|on|at|and|the|a|an|"
                             r"by|from|via|per)$", row_title, re.I)):
            lead = observation[:90]
            if len(observation) > 90:
                lead = lead.rsplit(" ", 1)[0] + "…"
            row_title = lead
    subcaps = list(dict.fromkeys(
        _SUBCAP_RE.findall(f"{raw}")))
    return ProfileFinding(
        title=row_title.strip()[:200],
        observation=observation.strip(),
        maturity=maturity.strip(),
        zennify=zennify.strip(),
        finding_id=finding_id,
        e_ids=_profile_e_ids(raw),
        subcap_refs=subcaps,
        page=page,
        source_kind=source_kind,
    )


# Curated FSI keyword anchors → category ids. The similarity classifier
# handles the long tail; these pin the domain vocabulary the audits saw
# most (cross-pillar affects on real profile text).
_KEYWORD_ANCHORS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rx, re.I), cat) for rx, cat in (
        (r"data\s+(?:governance|warehouse|lake|foundation|architecture|strategy)|"
         r"lakehouse|single\s+(?:customer|member)\s+view|customer\s+data\s+platform|"
         r"\bCDP\b|golden\s+record|master\s+data|data\s+silos?", "P4C1"),
        (r"analytics?|dashboards?|tableau|power\s*bi|reporting|business\s+intelligence|"
         r"\bAI\b|machine\s+learning|genai|generative\s+ai|decisioning|"
         r"next[- ]best[- ]action|agentforce|einstein|copilot|\bLLM\b", "P4C2"),
        (r"cloud\s+migration|core\s+(?:banking|system|conversion|migration|modernization)|"
         r"\bAPIs?\b|integration|middleware|mulesoft|architecture|mainframe|legacy\s+systems?", "P4C3"),
        (r"cyber|ransomware|breach|infosec|information\s+security|phishing|zero\s+trust", "P4C4"),
        (r"\bCRM\b|customer\s+360|member\s+360|financial\s+services\s+cloud|\bFSC\b|"
         r"relationship\s+management|salesforce", "P2C4"),
        (r"personali[sz]ation|cross[- ]sell|marketing\s+(?:automation|cloud)|"
         r"campaign|segmentation|journey\s+orchestration", "P2C4"),
        (r"mobile\s+(?:app|banking)|digital\s+channels?|online\s+banking|"
         r"self[- ]service|omnichannel|digital\s+(?:account\s+)?(?:opening|onboarding)", "P2C1"),
        (r"contact\s+cent(?:er|re)|call\s+cent(?:er|re)|service\s+cloud|servicing|"
         r"chatbot|\bIVR\b", "P2C2"),
        (r"loan\s+origination|underwriting|workflow|automation|straight[- ]through|"
         r"\bRPA\b|manual\s+process(?:es)?|\bSTP\b|back[- ]office", "P3C1"),
        (r"compliance|\bBSA\b|\bAML\b|\bKYC\b|regulatory|consent\s+order|"
         r"surveillance|\bfair\s+lending\b", "P3C3"),
        (r"vendor\s+risk|third[- ]party|business\s+continuity|resilien|\bTPRM\b|"
         r"disaster\s+recovery", "P3C4"),
        (r"digital\s+strategy|strategic\s+plan|transformation\s+roadmap|"
         r"board[- ]level|operating\s+model|vision", "P1C1"),
        (r"governance|risk\s+appetite|\bERM\b|enterprise\s+risk", "P1C2"),
        (r"talent|hiring|recruit|culture|change\s+management|upskill|training|"
         r"chief\s+(?:technology|digital|information|experience)\s+officer|"
         r"\bCTO\b|\bCIO\b|\bCXO\b|\bCDO\b", "P1C4"),
        (r"\bESG\b|sustainab|climate", "P1C5"),
    )
)


class SubcapClassifier:
    """Multi-``affects[]`` classifier (plan 5.1): similarity vs
    ``ccg_subcaps`` names + curated keyword anchors.

    ``subcap_names`` maps subcap_id → human name (placeholder "Subcap …"
    names are dropped). ``resolve_leaf`` optionally maps a category-grain
    anchor (``P4C1``) onto the run's most relevant leaf (its
    lowest-scoring subcap under that category) so affects chips navigate
    to a real heatmap cell. Pure/deterministic; offline (LexicalIndex).
    """

    def __init__(
        self,
        subcap_names: dict[str, str] | None = None,
        resolve_leaf: Callable[[str], str | None] | None = None,
    ) -> None:
        self._resolve_leaf = resolve_leaf
        self._index = None
        if subcap_names:
            docs = [
                (sid, name)
                for sid, name in subcap_names.items()
                if name and not name.lower().startswith("subcap ")
            ]
            if docs:
                from app.services.nlp.similarity import LexicalIndex
                idx = LexicalIndex()
                idx.fit(docs)
                self._index = idx

    def with_resolver(
        self, resolve_leaf: Callable[[str], str | None] | None,
    ) -> SubcapClassifier:
        """A per-run view sharing the (expensive) fitted name index.

        The TF-IDF index over ~4k catalogue names costs seconds to fit;
        the DB re-derive builds it ONCE and swaps only the run-specific
        category→weakest-leaf resolver per run."""
        clone = SubcapClassifier()
        clone._index = self._index
        clone._resolve_leaf = resolve_leaf
        return clone

    def _leaf(self, ref: str) -> str:
        if "." in ref or self._resolve_leaf is None:
            return ref
        return self._resolve_leaf(ref) or ref

    def affects_for(
        self,
        text: str,
        *,
        anchor: str | None = None,
        extra_refs: list[str] | None = None,
        k: int = 5,
        min_score: float = 0.22,
    ) -> list[str]:
        """Ordered, deduped multi-affects for a card's prose.

        Order: anchor → explicit subcap refs in the text → keyword-anchor
        hits → similarity hits vs catalogue subcap names. Category-grain
        refs are resolved to the run's weakest leaf when a resolver is
        wired. Capped at ``k`` + anchor.
        """
        out: list[str] = []

        def _add(ref: str) -> None:
            ref = ref.strip()
            if ref and ref not in out:
                out.append(ref)

        if anchor:
            _add(anchor)
        blob = text or ""
        for ref in _SUBCAP_RE.findall(blob):
            _add(ref)
        for ref in extra_refs or []:
            _add(ref)
        for rx, cat in _KEYWORD_ANCHORS:
            if len(out) >= k + 1:
                break
            if rx.search(blob):
                _add(self._leaf(cat))
        if self._index is not None and len(out) < k + 1:
            for sid, _score in self._index.top_k(blob, k=3, min_score=min_score):
                _add(str(sid))
                if len(out) >= k + 1:
                    break
        return out[: k + 1]


def score_line_for_anchor(
    anchor: str | None,
    sub_scores: dict | None,
    peer_medians: dict | None = None,
) -> str:
    """The live score standing sentence for a card anchor.

    Exact subcap score when the anchor is a leaf; the category average
    across its scored leaves when the anchor is category-grain (the
    common case for profile findings, which cite ``P4C3``-style refs).
    The peer median rides along when the run carries one (AE-depth:
    peer deltas on every card). Empty string when the run carries no
    scores under the anchor."""
    if not anchor or not sub_scores:
        return ""
    # Anti-template (2026-07-13): "X scores N/5 against a peer median of N on
    # the current assessment." recurred on 63/94 clients. Seeded per anchor +
    # values, so identical inputs stay stable while the corpus varies.
    from app.services.nlp.stylebook import pick as _pick
    from app.services.nlp.stylebook import seeded as _seeded
    exact = sub_scores.get(anchor)
    if exact is not None:
        pm = (peer_medians or {}).get(anchor)
        _rng = _seeded(anchor, exact, pm, "score-line")
        # NEVER the raw subcap code as the sentence subject — the S1 jargon
        # scrub strips codes downstream, which orphaned the sentence into
        # "… opportunity. scores 1.5/5 on the current assessment." (2026-07-13
        # stress-test). "The linked capability" survives every scrub.
        if pm is not None:
            return _pick(_rng, (
                "The linked capability scores {s:.1f}/5 against a peer "
                "median of {p:.1f} on the current assessment.",
                "The current assessment reads the linked capability at "
                "{s:.1f}/5, with the peer median at {p:.1f}.",
                "The capability behind it stands at {s:.1f}/5 this "
                "assessment; peers hold a {p:.1f} median.",
                "On the current assessment the linked capability measures "
                "{s:.1f}/5 versus a {p:.1f} peer median.",
            ), s=float(exact), p=float(pm))
        return _pick(_rng, (
            "The linked capability scores {s:.1f}/5 on the current "
            "assessment.",
            "The current assessment reads the linked capability at "
            "{s:.1f}/5.",
            "The capability behind it stands at {s:.1f}/5 this assessment.",
        ), s=float(exact))

    def _avg_line(grain: str) -> str:
        leaves = [v for s, v in sub_scores.items()
                  if s.startswith(grain + ".") and v is not None]
        if not leaves:
            return ""
        avg = sum(leaves) / len(leaves)
        peers = [v for s, v in (peer_medians or {}).items()
                 if s.startswith(grain + ".") and v is not None]
        _rng = _seeded(grain, round(avg, 2), len(leaves), "avg-line")
        peer_avg = (sum(peers) / len(peers)) if peers else None
        if peer_avg is not None:
            return _pick(_rng, (
                "{g} averages {a:.1f}/5 across its {n} scored "
                "sub-capabilities (peer median ~ {p:.1f}) on the current "
                "assessment.",
                "Across {n} scored sub-capabilities, {g} averages {a:.1f}/5 "
                "this assessment against a ~{p:.1f} peer median.",
                "The current assessment puts {g} at a {a:.1f}/5 average over "
                "{n} scored sub-capabilities; the peer median runs ~{p:.1f}.",
            ), g=grain, a=avg, n=len(leaves), p=peer_avg)
        return _pick(_rng, (
            "{g} averages {a:.1f}/5 across its {n} scored sub-capabilities "
            "on the current assessment.",
            "Across {n} scored sub-capabilities this assessment, {g} "
            "averages {a:.1f}/5.",
        ), g=grain, a=avg, n=len(leaves))

    line = _avg_line(anchor)
    if line:
        return line
    # Unscored leaf anchor (catalogue-variant ids like P3C1.8.RIA2):
    # the category standing is the honest nearest grain.
    cat = anchor.split(".")[0]
    return _avg_line(cat) if cat != anchor else ""


def _severity_for_profile(finding: ProfileFinding, sub_scores: dict | None) -> str:
    blob = f"{finding.maturity} {finding.observation}"
    if re.search(r"\bCRITICAL\b", blob):
        return "critical"
    sev = _severity_from_maturity(finding.maturity)
    if finding.source_kind == "strategic_priority" and not finding.maturity:
        # The client's own stated priority: urgency comes from how weak
        # the linked capability actually is on the current assessment.
        anchor = finding.subcap_refs[0] if finding.subcap_refs else None
        score = (sub_scores or {}).get(anchor) if anchor else None
        return "high" if (score is not None and score < 2.5) else "medium"
    return sev


def _profile_why(finding: ProfileFinding, anchor: str | None,
                 sub_scores: dict | None,
                 peer_medians: dict | None = None) -> str:
    """WHY: the report's own ceiling clause + causal decomposition +
    the anchor's live score standing. Never a bare score echo."""
    from app.services.nlp import causal
    pieces: list[str] = []
    if finding.maturity:
        from app.services.nlp.stylebook import pick as _pick
        from app.services.nlp.stylebook import seeded as _seeded
        m = finding.maturity.strip().rstrip(".")
        pieces.append(_pick(_seeded(m, anchor, "maturity-pin"), (
            "The research report pins the maturity impact at: {m}.",
            "On maturity impact, the research report is specific: {m}.",
            "The report's own maturity read: {m}.",
        ), m=m))
    decomposed = causal.decompose(finding.observation)
    if decomposed.get("why"):
        pieces.append(decomposed["why"])
    score_line = score_line_for_anchor(anchor, sub_scores, peer_medians)
    if score_line:
        pieces.append(score_line)
    if not pieces:
        pieces.append(
            "Grounded in the Client Profile Research Report"
            + (f" (p. {finding.page})" if finding.page else "")
            + " — see the cited evidence for the underlying facts.")
    return " ".join(pieces)


def _profile_so_what(finding: ProfileFinding, anchor: str | None = None) -> str:
    """SO-WHAT: the report's own Zennify play, framed as the next move."""
    from app.services.nlp import causal
    z = finding.zennify.strip().rstrip(".")
    if z:
        z = re.sub(r"^(?:PRIMARY|SECONDARY)\s*[:\-]\s*", "", z)
        return f"Recommended play: {z}."
    decomposed = causal.decompose(finding.observation)
    if decomposed.get("so_what"):
        return actionize_so_what(decomposed["so_what"])
    # No Zennify column and no action clause in the observation — compose the
    # IMPLICATION (the move) from the finding's polarity + capability theme, not
    # a generic "discovery conversation — documented in the report" line, which
    # made ~120 profile cards read as summaries, not insights (2026-07-09 QA).
    # The live score/gap already lives in the WHY; the SO-WHAT states the play.
    from app.services.nlp.polarity import signal as _polarity
    subject = (theme_for_anchor(anchor) if anchor else None) or "this capability"
    if finding.source_kind == "strategic_priority":
        return (f"Lead with {subject} in discovery — it is the client's own "
                f"stated strategic priority, so the engagement maps directly "
                f"to their agenda.")
    pol = _polarity(finding.observation or "")
    if pol == "positive":
        return (f"The client is already moving on {subject}; the play is to "
                f"accelerate it toward peer-leading maturity while the window "
                f"is open.")
    if pol == "negative":
        return (f"Left unaddressed, {subject} holds the client below the peer "
                f"benchmark — a near-term remediation play for the engagement.")
    return (f"{subject} is a documented opening to raise maturity toward the "
            f"peer benchmark — a concrete play for the roadmap.")


def insights_from_profile_findings(
    findings: list[ProfileFinding],
    *,
    sub_scores: dict | None = None,
    peer_medians: dict | None = None,
    classifier: SubcapClassifier | None = None,
    cap: int = 12,
) -> list[InsightCardRow]:
    """PRIMARY rung (plan 5.1): Client Profile Research Report findings →
    insight cards. WHAT = the report's own observation (verbatim, inline
    E-ID citations kept), WHY = ceiling clause + causal decomposition +
    live score, SO-WHAT = the report's Zennify play. Cards without any
    resolvable subcap anchor are skipped (NOT NULL contract)."""
    out: list[InsightCardRow] = []
    seen: set[str] = set()
    seq = 0
    for finding in findings:
        # Anchor ladder: leaf ref → category ref → classifier top hit.
        leaf_refs = [r for r in finding.subcap_refs if "." in r]
        cat_refs = [r for r in finding.subcap_refs if "." not in r]
        # Prefer a non-LOB-family leaf; a LOB-family leaf (.IC1/.RB1/.CU1…) is a
        # NO_EVIDENCE placeholder whose evidence sits on numeric siblings, so an
        # LOB-only anchor rolls up to its parent subcategory (plan S5).
        non_lob_leaf = next(
            (r for r in leaf_refs if not _LOB_LEAF_RE.search(r)), None)
        anchor = non_lob_leaf or (leaf_refs[0] if leaf_refs else None) or (
            cat_refs[0] if cat_refs else None)
        if anchor is None and classifier is not None:
            hits = classifier.affects_for(
                f"{finding.title}. {finding.observation}", k=1)
            anchor = hits[0] if hits else None
        # Roll ANY LOB-family leaf (from refs OR the classifier) up to its
        # parent subcategory so no card anchors on a NO_EVIDENCE placeholder.
        if anchor and _LOB_LEAF_RE.search(anchor):
            anchor = anchor.rsplit(".", 1)[0]
        if anchor is None:
            continue
        seq += 1
        prefix = {"strategic_priority": "CP-S", "digital_evolution": "CP-D",
                  "tech_landscape": "CP-T"}.get(finding.source_kind, "CP-F")
        base_id = (f"CP-{finding.finding_id}" if finding.finding_id
                   else f"{prefix}-{seq:03d}")[:16]
        ic_id = base_id
        if ic_id in seen:
            ic_id = f"{prefix}-{seq:03d}"[:16]
        if ic_id in seen:
            continue
        seen.add(ic_id)
        out.append(InsightCardRow(
            ic_id=ic_id,
            severity=_severity_for_profile(finding, sub_scores),
            title=strip_template_markers(finding.title)[:500],
            what_text=finding.observation[:4000],
            why_text=_profile_why(finding, anchor, sub_scores,
                                  peer_medians)[:4000],
            so_what_text=_profile_so_what(finding, anchor)[:4000],
            linked_subcap_id=anchor[:32],
            linked_e_ids=[e[:16] for e in finding.e_ids][:20],
        ))
        if len(out) >= cap:
            break
    return out


def _priority_severity(priority: str) -> str:
    p = (priority or "").strip().lower()
    if p in ("critical", "p0", "urgent"):
        return "critical"
    if p in ("high", "h1", "p1", "1"):
        return "high"
    if p in ("low", "p3", "3"):
        return "low"
    return "medium"


def offering_platform_family(offering: str | None) -> str | None:
    """Map a Zennify offering string onto one of the five scored platform
    families via the shared tech linker keyword map."""
    if not offering:
        return None
    from app.services.parsers.tech_linker import SCORED_PLATFORM_FAMILIES
    for fid, _name, rx in SCORED_PLATFORM_FAMILIES:
        if rx.search(offering):
            return fid
    # Salesforce-family products that the family regex may not name.
    if re.search(r"data\s+cloud|marketing\s+cloud|service\s+cloud|sales\s+cloud|"
                 r"experience\s+cloud|financial\s+services\s+cloud|\bFSC\b|"
                 r"mulesoft|agentforce|einstein|slack", offering, re.I):
        return "salesforce"
    if re.search(r"mosaic", offering, re.I):
        return "databricks"
    return None


def insights_from_zennify_opportunities(
    opportunities: list[dict],
    *,
    sub_scores: dict | None = None,
    peer_medians: dict | None = None,
    family_leafs: dict[str, str] | None = None,
    evidence_excerpts: dict[str, tuple[str, str]] | None = None,
    classifier: SubcapClassifier | None = None,
) -> list[InsightCardRow]:
    """Generated OPPORTUNITY cards from `client_knowledge_sections`
    artifact_kind='zennify_opportunity' provenance rows (plan 5.1 —
    "each fully evidenced or not emitted").

    ``opportunities``: the normalized provenance dicts
    ``{opportunity_id, opportunity, priority, trigger_evidence,
    zennify_offering, pillar_alignment, entry_point, e_ids, pillar_refs}``.
    ``family_leafs`` maps a scored platform family → the run's
    weakest subcap carrying that family's platform_tag (the smartest
    anchor when the row names no pillar). ``evidence_excerpts`` maps
    E-ID → (excerpt, source_name) so WHAT can quote the actual trigger
    fact instead of a bare id list.
    """
    out: list[InsightCardRow] = []
    seen: set[str] = set()
    for i, opp in enumerate(opportunities, start=1):
        if not isinstance(opp, dict):
            continue
        name = (opp.get("opportunity") or "").strip()
        offering = (opp.get("zennify_offering") or "").strip()
        if not (name or offering):
            continue
        e_ids = [e for e in (opp.get("e_ids") or [])
                 if isinstance(e, str) and e.startswith("E-")]
        if not e_ids:
            e_ids = _profile_e_ids(str(opp.get("trigger_evidence") or ""))
        if not e_ids:
            continue  # fully evidenced or not emitted
        pillar_refs = [str(r) for r in (opp.get("pillar_refs") or [])]
        leaf_refs = [r for r in pillar_refs if "." in r]
        cat_refs = [r for r in pillar_refs
                    if re.fullmatch(r"P[1-4]C\d+", r)]
        # The family cue can live in the offering ("MuleSoft") OR the
        # opportunity name ("MuleSoft Integration Layer").
        family = offering_platform_family(f"{offering} {name}")
        anchor = (
            (leaf_refs[0] if leaf_refs else None)
            or (cat_refs[0] if cat_refs else None)
            or ((family_leafs or {}).get(family) if family else None)
        )
        if anchor is None and classifier is not None:
            hits = classifier.affects_for(f"{name}. {offering}", k=1)
            anchor = hits[0] if hits else None
        if anchor is None:
            continue
        opp_id = str(opp.get("opportunity_id") or f"OPP-{i:03d}")
        ic_id = f"Z-{opp_id}"[:16]
        if ic_id in seen:
            continue
        seen.add(ic_id)
        # WHAT: the opportunity + the actual trigger fact (quoted).
        lead = (name or offering).strip()
        if lead and lead[-1] not in ".!?":
            lead += "."
        what_bits = [lead]
        quoted = None
        for eid in e_ids:
            hit = (evidence_excerpts or {}).get(eid)
            if hit and (hit[0] or "").strip():
                # Verbatim-quote mandate (2026-07-06): quote the trigger
                # excerpt as written — claim-boundary truncation with an
                # ellipsis only; an unquotable excerpt falls through to
                # the next cited row (never a silent mid-claim cut).
                excerpt = quote_span(hit[0], 280)
                if not excerpt:
                    continue
                quoted = f'The research recorded: "{excerpt}" [{eid}]'
                break
        if quoted:
            what_bits.append(quoted)
        else:
            what_bits.append(
                "Trigger evidence: " + ", ".join(e_ids[:6]) + ".")
        # WHY: analyst priority + entry-point signal + live score standing.
        why_bits = []
        priority = str(opp.get("priority") or "").strip()
        if priority:
            why_bits.append(
                f"The analyst's opportunity map rates this {priority} priority.")
        entry = str(opp.get("entry_point") or "").strip()
        if entry:
            # "its" ties the signal back to the rated priority before it
            # (cohesion sweep: disconnected)
            why_bits.append(f"Its entry-point signal: {entry}.")
        alignment = str(opp.get("pillar_alignment") or "").strip()
        if alignment:
            why_bits.append(f"Its pillar alignment: {alignment}.")
        score_line = score_line_for_anchor(anchor, sub_scores, peer_medians)
        if score_line:
            why_bits.append(
                score_line.rstrip(".")
                + " — the gap this opportunity addresses.")
        if not why_bits:
            # Plain-language anchor (raw P#C# codes are internal jargon)
            # + bracketed citations so serve-time scrubs keep the chips.
            theme = theme_for_anchor(anchor)
            why_bits.append(
                (f"Anchored to the {theme} capability" if theme
                 else "Anchored to the capability this opportunity maps to")
                + f"; grounded on [{', '.join(e_ids[:6])}].")
        so_what = (f"Recommended play: open the {offering} conversation — "
                   f"the trigger evidence is already on file."
                   if offering else
                   "Recommended play: raise this opportunity in the next "
                   "client conversation — the trigger evidence is on file.")
        out.append(InsightCardRow(
            ic_id=ic_id,
            severity=_priority_severity(priority),
            title=(f"{name} — {offering}" if name and offering
                   else (name or offering))[:500],
            what_text=" ".join(what_bits)[:4000],
            why_text=" ".join(why_bits)[:4000],
            so_what_text=so_what[:4000],
            linked_subcap_id=anchor[:32],
            linked_e_ids=[e[:16] for e in e_ids][:20],
        ))
    return out


def combine_insight_rungs(
    *rungs: list[InsightCardRow],
    dedup_threshold: float = 0.82,
) -> list[InsightCardRow]:
    """Concatenate ladder rungs in priority order, dropping ic_id
    collisions and near-duplicate cards (lemma-TF-IDF cosine over
    title+WHAT) — the earlier (higher-priority) rung always wins."""
    merged: list[InsightCardRow] = []
    seen_ids: set[str] = set()
    for rung in rungs:
        for card in rung or []:
            if card.ic_id in seen_ids:
                continue
            seen_ids.add(card.ic_id)
            merged.append(card)
    if len(merged) < 2:
        return merged
    from app.services.nlp.similarity import near_duplicates
    dupes = near_duplicates(
        merged, key=lambda c: f"{c.title} {c.what_text}",
        threshold=dedup_threshold,
    )
    drop: set[int] = set()
    for i, j, _score in dupes:
        drop.add(max(i, j))  # later (lower-priority) card loses
    return [c for idx, c in enumerate(merged) if idx not in drop]


# Counter-signal detection (plan 5.1 interconnection mining): same-subcap
# evidence whose claim polarity OPPOSES the card's headline.
_POSITIVE_CLAIMS = frozenset({"positive", "strength", "win", "fact_positive"})
_NEGATIVE_CLAIMS = frozenset({
    "negative", "risk", "gap", "weakness", "concern", "contradictory", "mixed",
})


def counter_evidence_ids(
    anchor: str,
    severity: str,
    supporting: list[str],
    evidence_rows: list[dict],
    *,
    k: int = 5,
) -> list[str]:
    """E-IDs on the card's subcap whose polarity opposes the headline.

    ``evidence_rows``: ``[{e_id, claim_type, excerpt, subcap_ids, tier}]``.
    For a gap card (critical/high) a POSITIVE same-subcap claim counters;
    for a strength/monitor card a NEGATIVE one does. Claim-type labels
    are checked first; the nlp polarity signal over the excerpt catches
    rows whose claim_type is a neutral label (EVIDENCE/FACT — 40% of the
    corpus). Supporting E-IDs are excluded; strongest tier first.
    """
    from app.services.nlp import polarity
    if not anchor:
        return []
    is_gap = (severity or "").lower() in ("critical", "high")
    supporting_set = set(supporting or [])
    hits: list[tuple[int, str]] = []
    for row in evidence_rows or []:
        e_id = row.get("e_id")
        if not e_id or e_id in supporting_set:
            continue
        subcaps = row.get("subcap_ids") or []
        on_subcap = any(
            s == anchor or s.startswith(anchor + ".") or anchor.startswith(s + ".")
            for s in subcaps
        )
        if not on_subcap:
            continue
        claim = str(row.get("claim_type") or "").strip().lower()
        excerpt = str(row.get("excerpt") or "")
        if claim in _POSITIVE_CLAIMS:
            row_polarity = "positive"
        elif claim in _NEGATIVE_CLAIMS:
            row_polarity = "negative"
        else:
            row_polarity = polarity.signal(excerpt)
        opposes = (row_polarity == "positive") if is_gap else (
            row_polarity == "negative")
        if opposes:
            hits.append((int(row.get("tier") or 9), str(e_id)))
    hits.sort(key=lambda t: (t[0], t[1]))  # best (lowest) tier first
    return [e for _t, e in hits[:k]]


# The pre-2026-07-06 static counter-evidence note — a label, not analysis.
# Kept as a constant so the read path can recognize and upgrade legacy rows.
LEGACY_COUNTER_NOTE = "same-subcap evidence with opposing polarity"

_COUNTER_JARGON_RE = re.compile(r"P[1-4]C\d|\bM[1-5]\b|sub-?cap", re.I)


def counter_evidence_note(
    counter_rows: list[dict],
    severity: str,
    *,
    max_quotes: int = 2,
) -> str:
    """AE-facing ANALYSIS of a card's counter-evidence — what the opposing
    rows actually show, never a bare-chip stub (2026-07-06 mandate: the
    "But also…" section must analyze content like WHAT/WHY do).

    ``counter_rows``: ``[{e_id, excerpt, ...}]`` for the E-IDs
    `counter_evidence_ids` selected (strongest tier first). Load-bearing
    findings are quoted VERBATIM (claim-boundary truncation with ellipsis
    only — `quote_span`) with their E-ID attribution; rows whose excerpt
    cannot be quoted faithfully (unquotable cut, taxonomy jargon, or text
    a scrub layer would rewrite) are still cited honestly as chips.
    Returns '' when there is nothing to say (caller keeps no entry).
    """
    is_gap = (severity or "").lower() in ("critical", "high")
    quoted: list[str] = []
    cited: list[str] = []
    for row in counter_rows or []:
        e_id = str((row or {}).get("e_id") or "").strip()
        if not e_id:
            continue
        q = quote_span(str((row or {}).get("excerpt") or ""), 200)
        if (len(quoted) < max_quotes and len(q) >= 45
                and not _COUNTER_JARGON_RE.search(q)
                and _plain_scrub(q) == q):
            quoted.append(f"“{q}” [{e_id}]")
        else:
            cited.append(e_id)
    if not quoted and not cited:
        return ""
    lead = ("The picture is not one-sided: on this same capability the "
            "researchers also recorded "
            if is_gap else
            "Weigh the counter-signals on this same capability: the "
            "researchers recorded ")
    parts: list[str] = []
    if quoted:
        parts.append(lead + " and ".join(quoted) +
                     (" — working practice that cuts against the headline "
                      "and should shape how the gap is framed."
                      if is_gap else
                      " — a weakness that tempers the headline strength."))
    if cited:
        parts.append(
            ("Further counter-signals on file: " if quoted else
             "Same-capability evidence with opposing polarity is on file: ")
            + f"[{', '.join(cited[:5])}]"
            + " — open each item to weigh it against the headline.")
    return " ".join(parts)


def basis_marker(note: str = "scores + peer benchmark") -> dict:
    """The interconnections entry a zero-evidence card must carry (plan
    5.1 evidence ladder, final rung): the UI renders it as a chip so the
    AE knows exactly what the card stands on."""
    return {"kind": "basis", "target_id": None, "note": note, "e_ids": []}


def similarity_attach_evidence(
    cards: list[InsightCardRow],
    evidence_rows: list[dict],
    *,
    k: int = 3,
    min_score: float = 0.18,
    min_links: int = 3,
) -> int:
    """Evidence-ladder rung 4 (before the basis chip): lexical-similarity
    attachment for cards still thin after the inline-citation / subcap /
    category-roll-up rungs.

    23 of the corpus's runs carry evidence_index rows with NO
    ``linked_subcap_ids`` at all — the structural rungs can never fire
    there even though the run has real, relevant evidence. This rung
    links the card's own prose to the closest evidence excerpts
    (lemma-TF-IDF cosine, 0.18 floor so stopword overlap never
    fabricates a link) and TOPS UP cards below ``min_links`` supporting
    items (grounding density — a long report-derived WHAT with a single
    citation reads under-evidenced). Existing citations always keep
    their leading positions. Returns the number of cards touched.
    """
    from app.services.nlp.segment import sentences as _sentences

    def _needed(c: InsightCardRow) -> int:
        # Grounding density scales with claim count: a 12-sentence card
        # with one citation reads under-evidenced (the nlp.quality
        # rubric's grounding dimension). Clamp [min_links, 6].
        n_sents = len(_sentences(
            f"{c.title}. {c.what_text} {c.why_text} {c.so_what_text}"))
        return min(6, max(min_links, (n_sents + 3) // 4))

    pending = [c for c in cards if len(c.linked_e_ids or []) < _needed(c)]
    if not pending or not evidence_rows:
        return 0
    from app.services.nlp.similarity import LexicalIndex
    docs = [
        (row["e_id"],
         f"{row.get('excerpt') or ''} {row.get('source_name') or ''}".strip())
        for row in evidence_rows
        if row.get("e_id") and (row.get("excerpt") or "").strip()
    ]
    if not docs:
        return 0
    idx = LexicalIndex()
    idx.fit(docs)
    attached = 0
    for c in pending:
        need = _needed(c)
        query = f"{c.title}. {c.what_text}"
        hits = idx.top_k(query, k=max(k, need), min_score=min_score)
        if len(hits) < need - len(c.linked_e_ids or []):
            # Relaxed second phase for the score-prose card class
            # (gap/rec cards whose WHAT is mostly numbers): fill the
            # remaining slots at a 0.10 floor — still above the
            # module's 0.08 stopword-fabrication floor.
            relaxed = idx.top_k(query, k=need + 2, min_score=0.10)
            seen_ids = {e for e, _s in hits}
            hits = hits + [h for h in relaxed if h[0] not in seen_ids]
        if not hits:
            continue
        merged = list(dict.fromkeys(
            [*(c.linked_e_ids or []), *(str(e)[:16] for e, _s in hits)]))
        if merged != list(c.linked_e_ids or []):
            c.linked_e_ids = merged[:max(need, k)]
            attached += 1
    return attached


def attach_evidence_ladder(
    cards: list[InsightCardRow],
    evidence_by_subcap: dict[str, list[str]],
) -> None:
    """Evidence-ladder rungs 2+3, shared by ingest and the DB re-derive:
    subcap-linked evidence → category roll-up (both directions: a
    category anchor unions its leaves; an unlinked leaf inherits its
    category's pool). Honest — only links the package itself asserted.
    Cards keep any inline-citation E-IDs they already carry, topped up
    to 8."""
    for c in cards:
        if len(c.linked_e_ids or []) >= 8:
            continue
        anchor = c.linked_subcap_id
        hits = list(evidence_by_subcap.get(anchor, []))
        if not hits and "." not in anchor:
            for sid, eids in evidence_by_subcap.items():
                if sid.startswith(anchor + "."):
                    hits.extend(eids)
        if not hits and "." in anchor:
            cat = anchor.split(".")[0]
            for sid, eids in evidence_by_subcap.items():
                if sid == cat or sid.startswith(cat + "."):
                    hits.extend(eids)
        merged = list(dict.fromkeys([*(c.linked_e_ids or []), *hits]))
        c.linked_e_ids = merged[:8]
