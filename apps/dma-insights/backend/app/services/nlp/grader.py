"""L3 — the deterministic rubric grader (the measurable gold bar).

Every composed surface item (insight card / finding / focus / platform / issue)
is scored 0-100 against the G0-G8 rubric + the C1-C6 consultant-grade writing
checks (docs/GOLD_STANDARD_SPEC.md, docs/LANGUAGE_GUIDELINES.md). HARD gates must
all pass or the item CANNOT render; weighted params drive the numeric grade and
the surface pass-bar. Each failing parameter carries a repair hint the refine
loop (nlp/refine.py) consumes.

No LLM: G2 grounding-support reuses the L2 :meth:`EntityKnowledge.challenge`
primitive (drop a cited E-ID that doesn't topically support the capability); G6
verification checks every figure in the prose is quoted by a cited excerpt.

The grader is the single source of truth for "is this gold?" — the composer
writes to it, the countercheck aggregates it across all 94, and the pre-redeploy
gate reads it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.services.nlp.knowledge import Claim

if TYPE_CHECKING:
    from app.services.nlp.entity_knowledge import EntityState


@dataclass
class Item:
    """A normalized surface item the grader scores. The composer emits this."""
    surface: str                       # insight_card | finding | focus | platform | issue
    title: str
    what: str
    why: str = ""
    so_what: str = ""
    anchor_subcap: str | None = None    # the capability the item is about
    e_ids: list[str] = field(default_factory=list)
    siblings: list[str] = field(default_factory=list)  # sibling item subjects (G3)
    is_top: bool = True                 # top-ranked (bar 3/3) vs supporting (2/3)
    # Aggregation surfaces (exec) thread SEVERAL findings, so their citations
    # belong to several capabilities. G2 judges each citation against ANY of
    # these anchors (falling back to anchor_subcap alone when empty).
    anchor_subcaps: list[str] = field(default_factory=list)

    @property
    def prose(self) -> str:
        return " ".join(t for t in (self.what, self.why, self.so_what) if t).strip()

    @property
    def full(self) -> str:
        return " ".join(t for t in (self.title, self.what, self.why, self.so_what) if t).strip()


@dataclass
class Grade:
    passed: bool
    grade: float
    hard_fails: list[str] = field(default_factory=list)
    weighted: dict[str, bool] = field(default_factory=dict)
    repairs: dict[str, str] = field(default_factory=dict)  # param -> hint


# ── lexicons ──────────────────────────────────────────────────────────────
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# A standalone figure — NOT a digit embedded in a code token (P2C4, E-016, M4).
_NUM_RE = re.compile(r"(?<![A-Za-z0-9])\$?\d[\d,]*(?:\.\d+)?%?[BMK]?")
_ACTION_VERB_RE = re.compile(
    r"\b(deploy|stand\s+up|build|unify|consolidat|expand|launch|migrat|modernize|"
    r"wire|integrat|prove|defend|mount|close|lift|sequence|prioritiz|extend|"
    r"activate|position|accelerat|replace|roll\s+out|implement|"
    # the sales-motion composer's directive leads (v3 doctrine; parity
    # with quality._IMPERATIVE_LEAD_RE which already credits them)
    r"make|open|anchor)\w*", re.I)
_TIME_TOKEN_RE = re.compile(
    r"\b(before|ahead of|by\s+(?:Q[1-4]|20\d{2}|year-end|H[12])|within\s+\d|"
    r"near-term|now|today|this\s+(?:quarter|year|cycle)|while|until|"
    r"20\d{2}|Q[1-4]\s*20\d{2}|GA\b|effective\s+\w+\s+\d|hardens?|window)", re.I)
# a raw dump / roster / enumerated-list lead the thesis check rejects
_RAW_DUMP_RE = re.compile(
    r"quote:\s*['\"]|\(1\).{0,40}\(2\)|Executive Committee|10-K Glossary|"
    r"careers page|OFFICIAL BIO|Indiana\s+\d+\.\d+%|consolidated assets of approximately", re.I)
# named systems / platforms the so-what must reference (G4/behavior 3)
_SYSTEM_RE = re.compile(
    r"\b(Salesforce|Data Cloud|Agentforce|Einstein|MuleSoft|Experience Cloud|"
    r"Marketing Cloud|Tableau|Databricks|Snowflake|nCino|ServiceNow|Now Assist|"
    r"Twilio|Temenos|FSC|Financial Services Cloud|CDP|Qlik|Azure|AWS|Banking Advisor|"
    r"Data Lake|Customer 360|RCLIQ|Copilot|SAS|Power BI)\b")
# punctuation debris (C5)
_PUNCT_DEBRIS_RE = re.compile(
    r"\[\s*[,;]|[,;]\s*\]|\(\s*[,;]|\.\.(?!\.)|[\u2014\u2013]\s*,|,\s*,|"
    r"\[E-[^\]]*$|:\s*$|\s[\u2014\u2013-]\s*$|\s[,;]")
# accusatory-absence tone (C6 / language corpus) — clean-posture allow-listed
_ACC_RE = re.compile(
    r"(?:^|[\s|\u2014\u2013-])(?:no|zero|lacks?|lacking|absent|missing|fails?\s+to|"
    r"failing\s+to|cannot|unable\s+to|without)\b", re.I)
_ACC_ALLOW_RE = re.compile(
    r"breach|incident|enforcement|consent|litigation|lawsuit|violation|penalt|"
    r"sanction|default|complaint|regulatory\s+record|fraud|outage|data\s+loss|"
    r"m&a|acquisition|\binterest\b|appetite|\bplans?\b|intention|"
    r"net-zero|zero-trust|zero-copy|zero-day", re.I)
_PILLAR_RE = re.compile(r"\bP[1-4]C\d+", re.I)
# Rehearsed template skeletons (G8/C3) — kept in sync with countercheck_pack's
# TEMPLATE_RES. Defined locally so the grader never imports that script module
# (which runs a scan at import time).
_TEMPLATE_RES = [
    re.compile(r"make .{1,60}? a near-term focus", re.I),
    re.compile(r"is one of .{1,40}? least developed", re.I),
    re.compile(r"prioriti[sz]e .{1,40}? in the next phase", re.I),
    re.compile(r"a clear opportunity to close the gap", re.I),
    re.compile(r"sequencing it first lifts", re.I),
    re.compile(r"scoped investment here would lift it", re.I),
    re.compile(r"against a peer median of .{1,20}? on the latest assessment", re.I),
]


def _sentences(text: str) -> list[str]:
    return [s for s in _SENT_SPLIT.split((text or "").strip()) if len(s.strip()) > 3]


def _numbers(text: str) -> list[str]:
    return [m.group(0) for m in _NUM_RE.finditer(text or "") if any(ch.isdigit() for ch in m.group(0))]


# ── the checks (each returns (ok, repair_hint)) ─────────────────────────────
def _g0_in_scope(item: Item, state: EntityState) -> tuple[bool, str]:
    if item.anchor_subcap and not state.in_scope(item.anchor_subcap):
        return False, f"anchor {item.anchor_subcap} is out-of-scope (NA); re-anchor on an in-scope ranked gap"
    return True, ""


def _g1_thesis_first(item: Item, state: EntityState) -> tuple[bool, str]:
    title = (item.title or "").strip()
    if not title:
        return False, "empty title; derive a client-specific thesis headline"
    if title.lower() in state.catalogue_subcap_names:
        return False, f"title '{title}' is a bare catalogue capability name; retitle as a client-specific thesis"
    lead = _sentences(item.what)[:1]
    lead_txt = lead[0] if lead else item.what
    if _RAW_DUMP_RE.search(lead_txt or ""):
        return False, "lead is a raw-quote/roster/geography dump; open on a client-specific key message"
    # must have a predicate (a verb) tying the entity to the claim
    if not re.search(r"\b(is|are|has|have|scores?|leads?|runs?|lacks?|gives?|"
                     r"generates?|operates?|trails?|holds?|shows?|carries?)\b", lead_txt or "", re.I):
        return False, "lead has no predicate about the entity; state what the client IS/HAS/DOES"
    return True, ""


def capability_text(cap: object, item: Item | None = None) -> str:
    """The stable capability-description string used to support-check a
    citation — the catalogue name + score rationale (NOT the derived title,
    which would let a misattributed title 'justify' its own wrong citation).
    Composer and grader MUST use this same text so the G2 support check is
    consistent between compose-time and grade-time."""
    name = getattr(cap, "name", "") or ""
    rationale = getattr(cap, "rationale", "") or ""
    text = f"{name} {rationale}".strip()
    return text or (item.title if item else "") or getattr(cap, "subcap_id", "") or ""


def _g2_grounding(item: Item, state: EntityState) -> tuple[float, str]:
    cited = [e for e in (item.e_ids or []) if e]
    if not cited:
        return 0.0, "no evidence cited; anchor on support-checked E-IDs from the capability"
    anchor = state.capability(item.anchor_subcap)
    kept: set[str] = set()
    if item.surface == "exec":
        # The exec summary THREADS the top findings, so its citations span
        # multiple capabilities by design (compose_exec merges the top-3
        # findings' e_ids). Support-check each citation against the capability
        # that DECLARES it, falling back to the anchor — the anchor-only check
        # structurally hard-failed every exec whose findings span two
        # capabilities (2026-07-10 redeployment QA). Non-exec surfaces keep
        # the single batched anchor check below (unchanged behaviour).
        for eid in cited:
            cap = next(
                (c for c in state.capabilities if eid in (c.evidence_ids or [])),
                None,
            ) or anchor
            cap_text = capability_text(cap, item)
            claim = Claim(text=item.prose or item.title, capability=cap_text, e_ids=[eid])
            state.knowledge.challenge(claim, min_support=0.30)
            kept.update(claim.e_ids)
    else:
        cap_text = capability_text(anchor, item)
        claim = Claim(text=item.prose or item.title, capability=cap_text, e_ids=list(cited))
        state.knowledge.challenge(claim, min_support=0.30)
        kept = set(claim.e_ids)
    frac = len(kept) / len(cited) if cited else 0.0
    if frac < 1.0:
        dropped = [e for e in cited if e not in kept]
        return frac, f"citations {dropped} don't topically support the capability; drop/replace with A3-aligned evidence"
    return 1.0, ""


# The human pillar-DOMAIN phrases the composer writes into prose (codes are
# scrubbed by plain(), so G3 must recognise the words, not the P#C# tokens) —
# two distinct domains in one item IS a cross-pillar link.
_DOMAIN_RE = re.compile(
    r"strategy and governance|customer experience|operations and process|"
    r"data and technology", re.I)


def _g3_cross_link(item: Item, state: EntityState) -> tuple[bool, str]:
    pillars = {m.group(0)[:2].upper() for m in _PILLAR_RE.finditer(item.full)}
    if len(pillars) >= 2:
        return True, ""
    if len({m.group(0).lower() for m in _DOMAIN_RE.finditer(item.full)}) >= 2:
        return True, ""
    if item.siblings and any(sib and sib.lower() in item.full.lower() for sib in item.siblings):
        return True, ""
    # a second named system OR an LOB/financial fact also counts as a cross-link
    if len(set(_SYSTEM_RE.findall(item.full))) >= 2:
        return True, ""
    return False, "no cross-link; connect a sibling capability, a 2nd pillar/LOB, or a P&L fact"


def _g4_so_what(item: Item, state: EntityState) -> tuple[bool, str]:
    sw = item.so_what or ""
    has_verb = bool(_ACTION_VERB_RE.search(sw))
    has_system = bool(_SYSTEM_RE.search(sw))
    has_time = bool(_TIME_TOKEN_RE.search(sw))
    if has_verb and has_system and has_time:
        return True, ""
    missing = [n for n, ok in (("action-verb", has_verb), ("named-system", has_system),
                               ("time/urgency", has_time)) if not ok]
    return False, f"so-what missing {missing}; name the play + system + urgency window"


def _g5_contradiction(item: Item, state: EntityState) -> tuple[bool, str]:
    # a resolved regulatory/negative fact must not be surfaced raw as a live risk
    from app.services.nlp.polarity import signal as _polarity
    if _polarity(item.prose) == "negative" and re.search(
            r"\b(terminated|resolved|lifted|waived|paid|cleared|closed)\b", item.prose, re.I):
        return False, "surfaces a negative that the corpus resolves; reconcile to the current true state"
    return True, ""


def _g6_verification(item: Item, state: EntityState) -> tuple[float, str]:
    nums = _numbers(item.prose)
    if not nums:
        return 1.0, ""   # no figures to verify (G4/C4 handle the has-a-figure bar)
    cited_excerpts = " ".join(state.evidence_excerpt(e) or "" for e in (item.e_ids or []))
    cap = state.capability(item.anchor_subcap)
    # The why-now signals are grounded dated triggers — a legitimate source for a
    # so-what urgency date (e.g. "before the 2026 core conversion").
    why_now_txt = " ".join(
        str(s.get(k) or "") for s in (state.why_now_signals or []) if isinstance(s, dict)
        for k in ("so_what", "trigger", "headline", "title", "metric"))
    hay = " ".join([cited_excerpts, (cap.rationale if cap else ""), why_now_txt])
    hay_nums = set(_numbers(hay))
    # The anchor's assessment score / peer-median / gap are structured, verified-
    # by-construction figures (not prose that must be quoted from an excerpt).
    if cap is not None:
        for v in (cap.score, cap.peer_median, cap.peer_gap):
            if v is not None:
                hay_nums.add(f"{v:g}")
                hay_nums.add(f"{abs(v):g}")
    supported = sum(1 for n in nums if _num_in(n, hay_nums, hay))
    frac = supported / len(nums)
    if frac < 1.0:
        bad = [n for n in nums if not _num_in(n, hay_nums, hay)]
        return frac, f"figures {bad[:4]} not quoted by a cited excerpt; attach _verification or null them"
    return 1.0, ""


def _num_in(token: str, hay_nums: set[str], hay: str) -> bool:
    if token in hay_nums or token in hay:
        return True
    core = token.strip("$%BMK,")
    return bool(core) and core in hay


def _g8_distinct(item: Item, state: EntityState) -> tuple[bool, str]:
    # per-item proxy for the cohort anti-force-fit gate: the banned rehearsed
    # template skeletons (the cohort recurrence check lives in countercheck_pack).
    if any(rx.search(item.full) for rx in _TEMPLATE_RES):
        return False, "uses a rehearsed template skeleton; rewrite specific to this client's evidence"
    return True, ""


def _c1_paragraph(item: Item, state: EntityState) -> tuple[bool, str]:
    if len(_sentences(item.what)) >= 3:
        return True, ""
    return False, "WHAT is a one-liner; write a 3-5 sentence evidence-grounded paragraph"


def _c5_punctuation(item: Item, state: EntityState) -> tuple[bool, str]:
    for f in (item.title, item.what, item.why, item.so_what):
        if f and _PUNCT_DEBRIS_RE.search(f):
            return False, "punctuation debris (stray bracket/dangling separator); clean the prose"
    return True, ""


def _c6_tone(item: Item, state: EntityState) -> tuple[bool, str]:
    for f in (item.title, item.what, item.why, item.so_what):
        if f and _ACC_RE.search(f) and not _ACC_ALLOW_RE.search(f):
            return False, "accusatory absence phrasing; reframe the gap as an opportunity"
    return True, ""


# ── per-surface rubric config ───────────────────────────────────────────────
# HARD gates all must pass; WEIGHTED count toward the bar (top items 3/3 of the
# core three, supporting 2/3). insight_card is the reference surface.
_SURFACE_CFG: dict[str, dict] = {
    "insight_card": {"hard": ["G0", "G2", "G5", "G6", "G7", "C1", "C5", "C6"],
                     "weighted_core": ["G1", "G3", "G4"], "extra_weighted": ["G8"]},
    "finding":      {"hard": ["G0", "G2", "G5", "G6", "G7", "C5", "C6"],
                     "weighted_core": ["G1", "G3", "G4"], "extra_weighted": ["G8", "C1"]},
    "focus":        {"hard": ["G0", "G5", "G6", "G7", "C5", "C6"],
                     "weighted_core": ["G1", "G4"], "extra_weighted": ["G8"]},
    "platform":     {"hard": ["G0", "G2", "G5", "G6", "G7", "C5", "C6"],
                     "weighted_core": ["G1", "G4"], "extra_weighted": ["G8"]},
    "why_now":      {"hard": ["G0", "G2", "G5", "G6", "G7", "C5", "C6"],
                     "weighted_core": ["G1", "G4"], "extra_weighted": ["G8"]},
    # the exec summary is a STORY, graded on substance (grounded, true, in-tone),
    # thesis-first + distinctive — NOT on the per-capability so-what format
    # (G3/G4/C1 are soft here, so cohesive prose is never force-fit to a template).
    "exec":         {"hard": ["G0", "G2", "G5", "G6", "G7", "C5", "C6"],
                     "weighted_core": ["G1"], "extra_weighted": ["G8"]},
}
_DEFAULT_CFG = _SURFACE_CFG["insight_card"]


def grade(item: Item, state: EntityState) -> Grade:
    """Score one composed item. Returns pass/fail, 0-100 grade, the HARD gates
    that failed, and a repair hint per failing parameter (for nlp/refine.py)."""
    cfg = _SURFACE_CFG.get(item.surface, _DEFAULT_CFG)
    repairs: dict[str, str] = {}
    results: dict[str, bool] = {}

    # HARD ≥ 1.0 fractional gates
    g2, g2_hint = _g2_grounding(item, state)
    g6, g6_hint = _g6_verification(item, state)
    results["G2"] = g2 >= 1.0
    results["G6"] = g6 >= 1.0
    if g2_hint:
        repairs["G2"] = g2_hint
    if g6_hint:
        repairs["G6"] = g6_hint
    # G7 no-fabrication is the conjunction of G2 (support) + G6 (verification)
    results["G7"] = results["G2"] and results["G6"]
    if not results["G7"]:
        repairs.setdefault("G7", "a value lacks a supporting quote; null it or cite support")

    boolean_checks = {
        "G0": _g0_in_scope, "G1": _g1_thesis_first, "G3": _g3_cross_link,
        "G4": _g4_so_what, "G5": _g5_contradiction, "G8": _g8_distinct,
        "C1": _c1_paragraph, "C5": _c5_punctuation, "C6": _c6_tone,
    }
    for code, fn in boolean_checks.items():
        ok, hint = fn(item, state)
        results[code] = ok
        if not ok:
            repairs[code] = hint

    hard = cfg["hard"]
    hard_fails = [c for c in hard if not results.get(c, True)]
    core = cfg["weighted_core"]
    extra = cfg.get("extra_weighted", [])
    core_pass = sum(1 for c in core if results.get(c))
    bar = len(core) if item.is_top else max(1, len(core) - 1)
    weighted_ok = core_pass >= bar
    passed = (not hard_fails) and weighted_ok

    weighted_all = core + extra
    weighted_score = sum(1 for c in weighted_all if results.get(c)) / max(1, len(weighted_all))
    grade_val = round(100.0 * (0 if hard_fails else 1) * weighted_score, 1)

    return Grade(
        passed=passed, grade=grade_val, hard_fails=hard_fails,
        weighted={c: results.get(c, False) for c in weighted_all},
        repairs=repairs,
    )
