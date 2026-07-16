"""Tab-09 graded QA rubric — the 100-point scoring instrument.

Training Specification v2.0 (Tab 09) grades every rendered surface instance
out of 100 across six weighted dimensions, with five hard-fail conditions that
zero the score regardless of marks, and four dispositions:

    GOLD >= 90 (ships; >=95 enters the gold training set)
    SHIP_WITH_NOTES 80-89
    REVISE 65-79 (auto-regenerate, max two cycles)
    REJECT < 65 (negative training set)

Dimensions and marks: Grounding and citations 25 · Specificity and client fit
20 · Value-led narrative 15 · Self-interrogation completeness 15 ·
Cross-surface consistency 15 · Peer and trend context 10.

The self-interrogation instrument is the per-surface-family ask-list
("Questions the system must ask before proceeding"): each question is a
deterministic predicate here, marks split evenly across the family's list
(Tab 09 §9.4). Question texts are transcribed verbatim from the spec on each
predicate.

Hard-fail conditions (Tab 09 §9.3): fabrication; internal-class content
reaching customer mode; score mutation; any uncited number in a narrative
field; a threat-toned forecast.

This module is pure (no DB, no LLM): it composes the existing L3 grader
primitives (G2 grounding / G6 verification), ``quality.rubric_score``, and the
pack- or DB-backed entity state.
"""
from __future__ import annotations

import itertools
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.services.nlp import grader, quality
from app.services.nlp.grader import Item

WEIGHTS = {
    "grounding": 25,
    "specificity": 20,
    "value_led": 15,
    "self_interrogation": 15,
    "consistency": 15,
    "peer_context": 10,
}

BANDS = (("GOLD", 90.0), ("SHIP_WITH_NOTES", 80.0), ("REVISE", 65.0))

_VENDOR_RE = re.compile(
    r"\b(Salesforce|Data Cloud|Agentforce|Databricks|Tableau|Twilio|nCino|"
    r"Snowflake|Microsoft|Oracle|SAP|AWS|ServiceNow|Temenos|MuleSoft|Qlik|"
    r"Einstein|Marketing Cloud|Experience Cloud|Power BI)\b")
_THREAT_RE = re.compile(
    r"you\s+will\s+lose|you\s+risk|or\s+else|falls?\s+behind\s+competitors|"
    r"will\s+inevitably|is\s+doomed|faces?\s+extinction|will\s+be\s+left\s+behind",
    re.I)
_LEAK_RE = re.compile(
    r"ERS\s+score|INT-AE|rescore\s+candidate|hard-fail|QA-[A-Z]{2}-\d|"
    r"subcap_id|claim_type=", re.I)
_PEER_RE = re.compile(r"\bpeer|\bcohort|\bmedian|industry\s+average", re.I)
_DATED_RE = re.compile(r"\b(19|20)\d{2}\b|\bQ[1-4]\b")
_EID_RE = re.compile(r"\bE-(?:INT-)?\d{1,4}\b")
_OVERCLAIM_RE = re.compile(r"\b(confirmed|proven)\b", re.I)
# maturity-score tokens (x.y in 0.0-5.0), excluding money/percent/version/year
_SCORE_TOKEN_RE = re.compile(r"(?<![\d.$])([0-5]\.\d)(?!\d)(?!\s*%)")
_SUBCAP_ID_RE = re.compile(r"\bP[1-4]C\d[\w.]*", re.I)
_GENERIC_FI_VOCAB = frozenset(
    "bank credit union farm financial insurance services federal national "
    "first community trust group corp inc the digital data customer member "
    "association mutual company january february march april may june july "
    "august september october november december".split())
_CAP_WORD_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")

# citation-bearing surface families (focus quotes are verbatim source material;
# roadmap metrics are run-computed; drilldown rationale carries its own E-IDs)
_CITED_FAMILIES = frozenset({"insight_card", "finding", "why_now", "exec",
                             "platform", "subcap_drilldown"})


@dataclass
class RubricScore:
    total: float
    band: str
    dims: dict[str, float]
    hard_fails: list[str] = field(default_factory=list)
    ask_marks: dict[str, bool] = field(default_factory=dict)
    repairs: dict[str, str] = field(default_factory=dict)


def band_for(total: float) -> str:
    for name, floor in BANDS:
        if total >= floor:
            return name
    return "REJECT"


def entity_swap_generic(text: str, entity_name: str,
                        donor_names: list[str] | None = None) -> bool:
    """Would this sentence ship unchanged for another institution?

    Strips the entity's own name (and any donor names), then looks for
    anything client-specific left behind: digits, E-ID citations, or a
    proper-noun bigram outside the generic FI vocabulary. Nothing specific
    left => the text fails the spec's entity-swap test (generic=True).
    """
    t = text or ""
    for name in [entity_name or "", *(donor_names or [])]:
        for tok in name.split():
            if len(tok) >= 3:
                t = re.sub(r"\b" + re.escape(tok) + r"\b", " ", t, flags=re.I)
    if any(ch.isdigit() for ch in t):
        return False
    if _EID_RE.search(t):
        return False
    caps = _CAP_WORD_RE.findall(t)
    for a, b in itertools.pairwise(caps):
        # a capitalized bigram beyond generic vocabulary = named system/place
        if ((a.lower() not in _GENERIC_FI_VOCAB
             or b.lower() not in _GENERIC_FI_VOCAB) and f"{a} {b}" in t):
            return False
    return True


def _first_clause(text: str, window: int = 60) -> str:
    head = (text or "").strip()[:window]
    for sep in (",", " \u2014 ", " \u2013 ", ";", ":"):
        if sep in head:
            head = head.split(sep)[0]
    return head


def _vendor_first(text: str) -> bool:
    clause = _first_clause(text)
    m = _VENDOR_RE.search(clause)
    if not m:
        return False
    verb = grader._ACTION_VERB_RE.search(clause)
    return verb is None or m.start() < verb.start()


def _as_float(token: str) -> float | None:
    core = token.strip("$%BMK,").replace(",", "")
    try:
        return float(core)
    except ValueError:
        return None


def _verify_numbers(item: Item, state, computed: set[str]) -> tuple[float, list[str]]:
    """Spec-faithful number check: a figure is legitimate when it is quoted by
    a cited excerpt OR computed live from the run (scores, medians, gaps,
    aggregates, fit scores, counts). E-ID citations are stripped before
    extraction so "E-049" never reads as the number 049.
    Returns (supported_fraction, offenders)."""
    prose = _SUBCAP_ID_RE.sub(" ", _EID_RE.sub(" ", item.prose))
    nums = grader._numbers(prose)
    if not nums:
        return 1.0, []
    hay = " ".join(state.evidence_excerpt(e) or "" for e in (item.e_ids or []))
    cap = state.capability(item.anchor_subcap)
    if cap is not None:
        hay += " " + (cap.rationale or "")
    hay += " " + " ".join(
        str(sig.get(k) or "") for sig in (state.why_now_signals or [])
        if isinstance(sig, dict)
        for k in ("so_what", "trigger", "headline", "title", "metric", "detail", "text"))
    hay_nums: set[str] = set(grader._numbers(hay))
    known_vals: set[float] = set()
    for v in getattr(state, "all_score_values", set()):
        hay_nums.add(f"{v:g}")
        known_vals.add(round(float(v), 2))
    for c in computed:
        hay_nums.add(str(c))
        cv = _as_float(str(c))
        if cv is not None:
            known_vals.add(round(cv, 2))
    hay_nums |= {"5", "100"}  # scale denominators (x/5 maturity, y/100 fit)

    def _ok(token: str) -> bool:
        if grader._num_in(token, hay_nums, hay):
            return True
        val = _as_float(token)
        if val is None:
            return False
        return any(abs(val - k) <= 0.05 for k in known_vals)

    supported = [n for n in nums if _ok(n)]
    offenders = [n for n in nums if n not in supported]
    return len(supported) / len(nums), offenders


# ── ask-lists (Tab 03-08 "Questions the system must ask before proceeding") ──
def _sent_ge(text: str, n: int) -> bool:
    return len(grader._sentences(text or "")) >= n


def _ask_insight_card(item: Item, state) -> dict[str, bool]:
    full = item.full
    return {
        # ASK-IC1-1 · Does the causal-chain test pass — would deleting any
        # block weaken the others?
        "ASK-IC1-1": bool(item.what and item.why and item.so_what
                          and _sent_ge(item.what, 2) and _sent_ge(item.so_what, 1)),
        # ASK-IC1-2 · Does the SO WHAT lead with the client outcome and carry
        # peer proof where the cohort offers it?
        "ASK-IC1-2": bool(item.so_what) and not _vendor_first(item.so_what),
        # ASK-IC1-3 · Is any block claiming beyond its evidence class
        # (a HYPOTHESIS reading as FACT)?
        "ASK-IC1-3": not _OVERCLAIM_RE.search(full) or bool(_EID_RE.search(full)),
        # ASK-IC1-4 · Do Affects chips match the count and route correctly?
        # (deterministic proxy: every cited E-ID resolves in the state)
        "ASK-IC1-4": all(state.evidence_excerpt(e) for e in (item.e_ids or [])),
    }


def _ask_finding(item: Item, state) -> dict[str, bool]:
    return {
        # ASK-OV6-1 · Is each headline tied to a named strategic objective,
        # and does it survive the entity-swap test?
        "ASK-OV6-1": bool(item.title) and item.title.lower()
        not in state.catalogue_subcap_names,
        # ASK-OV6-2 · Does each What run >=2 sentences with >=2 citations and
        # close on cited peer or industry context?
        "ASK-OV6-2": _sent_ge(item.what, 2) and len(set(_EID_RE.findall(item.full))
                                                    | set(item.e_ids or [])) >= 2,
        # ASK-OV6-3 · Is the Why a mechanism rather than a restated symptom?
        "ASK-OV6-3": bool(item.why) or _sent_ge(item.what, 3),
        # ASK-OV6-4 · Does each So What name platform, action, and a bounded
        # expected result in value-led order?
        "ASK-OV6-4": bool(item.so_what and grader._ACTION_VERB_RE.search(item.so_what)),
        # ASK-OV6-5 · Is every magnitude tag reproducible from the workbook?
        "ASK-OV6-5": _verify_numbers(item, state, set())[0] >= 1.0,
    }


def _ask_why_now(item: Item, state) -> dict[str, bool]:
    full = item.full
    return {
        # ASK-OV3-1 · Does every urgency claim tie to a stated objective?
        "ASK-OV3-1": bool(item.what),
        # ASK-OV3-2 · Is every signal dated within 12 months and checked for
        # contradicting evidence?
        "ASK-OV3-2": bool(_DATED_RE.search(full)),
        # ASK-OV3-3 · What bounds the window, and is that bound cited rather
        # than assumed?
        "ASK-OV3-3": bool(grader._TIME_TOKEN_RE.search(full)),
        # ASK-OV3-4 · What is the peer cohort doing on this exact question?
        "ASK-OV3-4": bool(_PEER_RE.search(full)),
        # ASK-OV3-5 · Does the Play equal argmax OSS including AE-note effects?
        "ASK-OV3-5": bool(item.so_what),
        # ASK-OV3-6 · Are assumptions listed, is the projection a range, would
        # a client reading it feel advised or threatened?
        "ASK-OV3-6": not _THREAT_RE.search(full),
        # ASK-OV3-7 · What must the first call ask — rendered as discovery?
        "ASK-OV3-7": bool(item.e_ids) or bool(_EID_RE.search(full)),
    }


def _ask_exec(item: Item, state) -> dict[str, bool]:
    full = item.full
    return {
        # ASK-OV4-1 · Is every Situation clause cited, and does the timeline
        # reconcile with the single timeline of record?
        "ASK-OV4-1": len(set(_EID_RE.findall(full))) >= 2,
        # ASK-OV4-2 · Is claim class preserved in the prose?
        "ASK-OV4-2": _sent_ge(full, 3),
        # ASK-OV4-3 · Zero contradictions with Top Findings and the Heatmap?
        "ASK-OV4-3": bool(state.name.split()
                          and state.name.split()[0].lower() in full.lower()),
        # ASK-OV4-4 · Does the Answer follow the value-led pattern?
        "ASK-OV4-4": _verify_numbers(item, state, set())[0] >= 1.0,
    }


def _ask_platform(item: Item, state) -> dict[str, bool]:
    full = item.full
    return {
        # ASK-PL1-1 · Does the first clause describe the client's outcome or
        # pain, in the client's numbers?
        "ASK-PL1-1": not _vendor_first(item.what or item.title),
        # ASK-PL1-2 · Is every quantitative claim cited or computed live, and
        # every peer precedent dated and verifiable?
        "ASK-PL1-2": _verify_numbers(item, state, set())[0] >= 1.0,
        # ASK-PL1-3 · Are prerequisites read from the category CSV?
        "ASK-PL1-3": bool(item.e_ids) or bool(_EID_RE.search(full)),
        # ASK-PL1-4 · Is any account note pinning or excluding a lead honored?
        "ASK-PL1-4": bool(item.what),
        # ASK-PL1-5 · Has any AE note contradicted a starter line?
        "ASK-PL1-5": not _THREAT_RE.search(full),
    }


def _ask_focus(item: Item, state) -> dict[str, bool]:
    return {
        # ASK-FC-1 · Is the title opportunity-framed (non-accusatory)?
        "ASK-FC-1": not (grader._ACC_RE.search(item.title or "")
                         and not grader._ACC_ALLOW_RE.search(item.title or "")),
        # ASK-FC-2 · Is the verbatim quote clean source material?
        "ASK-FC-2": bool((item.what or "").strip()) and " | " not in (item.what or ""),
        # ASK-FC-3 · Are the KPIs present and complete?
        "ASK-FC-3": bool(item.siblings),
    }


def _ask_subcap_drilldown(item: Item, state) -> dict[str, bool]:
    """Tab 05 synthesis drawer: institution-specific rationale with E-IDs,
    cap/thin logic, gap-to-next-level, and peer context (ASK-HM1-3)."""
    text = item.what or ""
    return {
        # ASK-HM1-3a · rationale present at workbook depth (>=150 chars)
        "ASK-HM1-3a": len(text.strip()) >= 150,
        # ASK-HM1-3b · cites resolving evidence
        "ASK-HM1-3b": bool(_EID_RE.search(text)),
        # ASK-HM1-3c · names the gap / next-level direction
        "ASK-HM1-3c": bool(re.search(
            r"gap|trails?|to reach|next level|\bM[1-5]\b|widest|direction",
            text, re.I)),
        # ASK-HM1-3d · peer context on the cell
        "ASK-HM1-3d": bool(_PEER_RE.search(text)),
    }


def _ask_evidence_segment(item: Item, state) -> dict[str, bool]:
    """Tab 04 §4.3 evidence segment: every citation resolves with tier and
    excerpt; corroboration state truthful (ASK-IC2-1..3 proxies)."""
    e_ids = item.e_ids or []
    resolved = [e for e in e_ids if state.evidence_excerpt(e)]
    tiers = set()
    for e in e_ids:
        ev = getattr(state.knowledge, "by_id", {}).get(e)
        if ev is not None and getattr(ev, "tier", None):
            tiers.add(ev.tier)
    return {
        # ASK-IC2-1 · every cited item resolves to a stored excerpt
        "ASK-IC2-1": bool(e_ids) and len(resolved) == len(e_ids),
        # ASK-IC2-2 · corroboration truthful: >=2 sources of >=2 tier types
        # (single-source cards must queue G3, not claim corroboration)
        "ASK-IC2-2": len(resolved) >= 2 and len(tiers) >= 2,
        # ASK-IC2-3 · excerpts are substantive (minimal verbatim spans)
        "ASK-IC2-3": all(len(state.evidence_excerpt(e) or "") >= 40
                         for e in resolved) if resolved else False,
    }


def _ask_roadmap(item: Item, state) -> dict[str, bool]:
    """Tab 06 §6.2 roadmap: phased, recommendation-backed, customer-impact
    narrated, modelled targets explicit (ASK-PL2-1..3 proxies).
    siblings carry the parsed phase dict via item.siblings."""
    text = item.full
    return {
        # ASK-PL2-1 · every phase names its producing recommendations
        "ASK-PL2-1": bool(item.e_ids),   # rec ids threaded through e_ids
        # ASK-PL2-2 · sequencing states duration and order
        "ASK-PL2-2": bool(re.search(r"phase|month|duration", text, re.I)),
        # ASK-PL2-3 · modelled target explicit and customer impact narrated
        "ASK-PL2-3": bool(re.search(r"\u2192|->|target|toward", text))
        and bool(item.why),
    }


ASK_LISTS: dict[str, Callable[[Item, object], dict[str, bool]]] = {
    "insight_card": _ask_insight_card,
    "finding": _ask_finding,
    "why_now": _ask_why_now,
    "exec": _ask_exec,
    "platform": _ask_platform,
    "focus": _ask_focus,
    "subcap_drilldown": _ask_subcap_drilldown,
    "evidence_segment": _ask_evidence_segment,
    "roadmap": _ask_roadmap,
}

_REPAIR_HINTS = {
    "grounding": "cite resolving E-IDs for every factual clause; drop unsupported citations",
    "specificity": "replace swappable sentences with named systems, dates, and quantities",
    "value_led": "lead with the client outcome in the client's numbers; platform second, proof third",
    "self_interrogation": "answer the surface ask-list: causal chain, dated signals, peer motion, honest unknowns",
    "consistency": "quote only scores that exist in the run's score set",
    "peer_context": "cite the peer median or cohort motion with a dated signal",
}


def score_item(item: Item, state, *, surface: str,
               siblings: dict | None = None) -> RubricScore:
    siblings = siblings or {}
    q = quality.rubric_score(
        item.full,
        evidence_ids=item.e_ids or (),
        evidence_excerpts={e: state.evidence_excerpt(e) or ""
                           for e in (item.e_ids or [])},
    )
    qs = q.get("scores") or {}
    full = item.full
    requires_citations = surface in _CITED_FAMILIES
    dims: dict[str, float] = {}
    hard_fails: list[str] = []

    computed = {str(c) for c in siblings.get("computed_numbers", ())}

    # ── grounding /25 ──────────────────────────────────────────────────
    g2, _ = grader._g2_grounding(item, state)
    g6, _offenders = _verify_numbers(item, state, computed)
    if requires_citations and not (item.e_ids or _EID_RE.search(full)):
        dims["grounding"] = 0.0
    else:
        dims["grounding"] = round(
            WEIGHTS["grounding"] * (0.4 * g2 + 0.3 * g6
                                    + 0.3 * float(qs.get("grounding", 0.0))), 2)

    # ── specificity /20 ────────────────────────────────────────────────
    spec = WEIGHTS["specificity"] * float(qs.get("specificity", 0.0))
    if entity_swap_generic(full, state.name):
        spec = min(spec, 8.0)
    spec -= 4.0 * sum(1 for rx in grader._TEMPLATE_RES if rx.search(full))
    dims["specificity"] = round(max(spec, 0.0), 2)

    # ── value_led /15 ──────────────────────────────────────────────────
    value = float(WEIGHTS["value_led"])
    for lead_text in (item.what, item.so_what):
        if lead_text and _vendor_first(lead_text):
            value -= 5.0
    threat_hits = len(_THREAT_RE.findall(full))
    value -= 5.0 * threat_hits
    if item.so_what and not grader._ACTION_VERB_RE.search(item.so_what):
        value = min(value, 10.0)
    dims["value_led"] = round(max(value, 0.0), 2)

    # ── self_interrogation /15 ─────────────────────────────────────────
    ask_fn = ASK_LISTS.get(surface, _ask_insight_card)
    ask_marks = ask_fn(item, state)
    if surface == "focus" and "kpis" in siblings:
        ask_marks["ASK-FC-3"] = bool(siblings["kpis"])
    passed = sum(1 for ok in ask_marks.values() if ok)
    dims["self_interrogation"] = round(
        WEIGHTS["self_interrogation"] * passed / max(len(ask_marks), 1), 2)

    # ── consistency /15 ────────────────────────────────────────────────
    known: set[float] = set(getattr(state, "all_score_values", set()))
    for extra in siblings.get("scores", ()):
        if isinstance(extra, int | float):
            known.add(round(float(extra), 2))
    cap = state.capability(item.anchor_subcap)
    if cap is not None:
        for v in (cap.score, cap.peer_median, cap.peer_gap):
            if isinstance(v, int | float):
                known.add(round(abs(float(v)), 2))
    violations = 0
    scan_text = _SUBCAP_ID_RE.sub(" ", _EID_RE.sub(" ", full))
    for m in _SCORE_TOKEN_RE.finditer(scan_text):
        tail = scan_text[m.end():m.end() + 24].lower()
        head = scan_text[max(m.start() - 24, 0):m.start()].lower()
        ctx = head + " " + tail
        if not re.search(r"/\s*5|score|median|maturity|\bvs\b", ctx):
            continue
        val = round(float(m.group(1)), 2)
        if known and not any(abs(val - k) <= 0.05 for k in known):
            violations += 1
    dims["consistency"] = round(max(WEIGHTS["consistency"] - 5.0 * violations, 0.0), 2)
    if violations:
        hard_fails.append("score_mutation")

    # ── peer_context /10 ───────────────────────────────────────────────
    if surface == "focus":
        dims["peer_context"] = float(WEIGHTS["peer_context"])
    else:
        has_peer = bool(_PEER_RE.search(full))
        has_date = bool(_DATED_RE.search(full))
        dims["peer_context"] = float(WEIGHTS["peer_context"]) if (has_peer and has_date) \
            else (WEIGHTS["peer_context"] / 2.0 if (has_peer or has_date) else 0.0)

    # ── hard fails ─────────────────────────────────────────────────────
    if requires_citations and g6 < 1.0:
        hard_fails.append("uncited_number")
        if g2 < 1.0:
            hard_fails.append("fabrication")

    if _LEAK_RE.search(full):
        hard_fails.append("internal_leakage")
    if _THREAT_RE.search(full):
        hard_fails.append("threat_tone")

    total = round(min(sum(dims.values()), 100.0), 2)
    if hard_fails:
        total = 0.0
    band = band_for(total) if not hard_fails else "REJECT"

    repairs = {d: _REPAIR_HINTS[d] for d, marks in dims.items()
               if marks < 0.7 * WEIGHTS[d]}
    return RubricScore(total=total, band=band, dims=dims,
                       hard_fails=hard_fails, ask_marks=ask_marks,
                       repairs=repairs)
