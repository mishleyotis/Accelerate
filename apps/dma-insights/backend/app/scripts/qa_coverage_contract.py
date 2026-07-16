"""Per-script x all-94 coverage CONTRACT (operator mandate 2026-06-24).

The user's safeguard directive: "ensure all 94 report outputs are considered to
refine each individual script involved." This module is the single source of
truth for WHICH script owns WHICH user-facing field, the well-formed assertion
for that field, and the EXPLICIT honest-null allowlist (so a legitimately-absent
value — a branchless asset manager's branch count, a private CU's ticker — is a
PASS, never a silent gap and never a fabricated value).

Two runners consume this contract:
  - `qa_startup_audit.py`  — stdlib-only, scans the committed `startup-data`
    snapshot (no DB); the fast baseline tracker, runnable in CI and locally.
  - `deploy_parity_gate.py` — the DB-side gate (extended) over every ACTIVE run.

Each `Check` maps a defect to its OWNING SCRIPT so a failure is actionable
("derive_financials left 7/94 clients without a derivable trend"). `fn` returns:
  True  → field present & well-formed (PASS)
  False → field missing/malformed though it SHOULD be present (DEFECT)
  None  → not applicable for this client (honest-null allowlist → neither)

`severity`:
  "hard" → deterministically fixable from already-persisted data; ANY defect
           fails the gate (boilerplate leak, broken SCQA, garbage name,
           derivable-but-missing trend/footprint, missing platforms[]/evidence).
  "soft" → depends on Vertex/Clay creds absent in offline runs (revenue mining,
           empty-roster Gemini leadership, thought-leadership); reported as a
           coverage % and WARNED, never fails the offline gate.

Pure / no imports beyond stdlib so the no-DB scanner stays dependency-free.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

try:
    from app.services import startup_enrich as se
except ImportError:  # pragma: no cover - direct-run fallback
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.services import startup_enrich as se

# ── Subvertical-aware honest-null allowlists ────────────────────────────────
# Export `entity.subvertical` codes (see entity_healing / heal.ts). Branch-less
# and non-ticker cohorts are enumerated, never guessed.
_BRANCHLESS_SUBV = {"AM", "RIA", "WEALTH_RIA", "ASSET_MANAGER", "REIT",
                    "FINTECH_SAAS", "FC", "IC", "IB", "INSURANCE_CARRIER",
                    "INSURANCE_BROKER", "CIB"}
_NON_TICKER_SUBV = {"CU", "FC", "MUTUAL"}  # credit unions / farm-credit / mutuals
_SUBCAP_ID_RE = re.compile(r"^[Pp]\d+C\d")
_BOILERPLATE_RE = re.compile(
    r"each finding includes|quantified observation, maturity implication|"
    r"solution relevance",
    re.I,
)
_RESTATE_RE = re.compile(
    r"(lowest|next-lowest)-scoring capability at [\d.]+ out of 5", re.I)
_TEMPLATE_FINDING_RE = re.compile(
    r"scores [\d.]+ out of 5.*?(lowest|next-lowest) capability area", re.I | re.S)
_BROKEN_SCQA_RE = re.compile(
    r"strengths:\s*\(\d|starting with\s*,|\(\d\.\d\)\s*,\s*\(\d|gaps[^.]*:\s*\(\d")
_TREND_HINT_RE = re.compile(
    r"accelerat|decelerat|\bstable\b|\bvariable\b|trend classification", re.I)


# ── Bundle accessors (the per-client JSON files, parsed) ─────────────────────
def _firm(b: dict) -> dict:
    return (b.get("overview") or {}).get("firmographics") or {}


def _subv(b: dict) -> str:
    return ((b.get("overview") or {}).get("entity") or {}).get("subvertical") or ""


def _fh_blob(b: dict) -> str:
    fh = _firm(b).get("financial_highlights") or {}
    return " ".join(fh.get("lines") or []) + " " + str(fh)


def _ev_map(b: dict) -> dict:
    """Offline subcap→E-ID map (the bound on what evidence can be grounded
    without the DB evidence_index). The deploy reparse grounds against the full
    index; offline we ground against the insight cards + financial-highlight
    E-IDs, and only require grounding where it is actually possible."""
    ins = (b.get("insights") or {}).get("items") or []
    fh = _firm(b).get("financial_highlights") or {}
    return se.subcap_evidence_map(ins, fh.get("lines"))


@dataclass
class Check:
    script: str
    field: str
    severity: str  # "hard" | "soft"
    fn: Callable[[dict], bool | None]


def _present(v: Any) -> bool:
    return v not in (None, "", [], {})


# ── derive_financials.py ─────────────────────────────────────────────────────
def _c_scale_metric(b: dict) -> bool | None:
    f = _firm(b)
    aum = f.get("aum_usd")
    if aum not in (None, "") and se.plausible_aum(aum, _subv(b)):
        return True
    if _present(f.get("revenue_usd")):
        return True
    # No PLAUSIBLE scale metric: a non-balance-sheet entity (payments FMI), or a
    # source value sanitized away as fabricated ($103T). Honest-null — the deploy
    # reparse with the correct basis fills it; we never show the garbage value.
    return None


def _c_trend(b: dict) -> bool | None:
    f = _firm(b)
    if _present(f.get("trend")):
        return True
    # Honest: defect only if the real extractor would yield a trend; else na.
    return False if se.derive_trend(f.get("financial_highlights") or {}) else None


def _c_footprint(b: dict) -> bool | None:
    f = _firm(b)
    if _present(f.get("footprint")):
        return True
    return False if _present(f.get("geography")) else None  # derivable→defect


def _c_branches(b: dict) -> bool | None:
    f = _firm(b)
    if _present(f.get("branches")):
        return True
    if _subv(b) in _BRANCHLESS_SUBV:
        return None
    # Derivable from financial_highlights but missing → hard defect; otherwise
    # honest-null (the count is not in the snapshot → Gemini/external in deploy).
    return False if se.derive_branches(f.get("financial_highlights") or {}) else None


def _c_revenue(b: dict) -> bool | None:  # soft: Gemini/honest-null
    f = _firm(b)
    if _present(f.get("revenue_usd")):
        return True
    return None if _present(f.get("aum_usd")) else False


# ── derive_leadership.py ─────────────────────────────────────────────────────
def _leaders(b: dict) -> list:
    return _firm(b).get("leadership") or []


def _c_lead_present(b: dict) -> bool | None:  # soft (needs creds for 24 empty)
    return bool(_leaders(b))


def _c_lead_no_garbage(b: dict) -> bool | None:  # hard
    for p in _leaders(b):
        nm = (p.get("name") or "").strip()
        if _SUBCAP_ID_RE.match(nm) or (nm and not any(c.isalpha() for c in nm)):
            return False
    return True


def _c_lead_flags(b: dict) -> bool | None:  # hard: deterministic from title+tenure
    ld = _leaders(b)
    if not ld:
        return None
    return all("critical_role" in p for p in ld)


def _c_lead_titles(b: dict) -> bool | None:  # hard
    ld = _leaders(b)
    if not ld:
        return None
    return all(_present(p.get("title")) for p in ld)


# ── thought_leadership — STRICTLY Clay-enrichment (operator mandate
#    2026-07-06): the panel is EMPTY until the Clay connector syncs it. It
#    is NOT derived from evidence/Gemini, so "present" is never required —
#    the check is neutral (None) rather than a coverage expectation. ──────────
def _c_thought(b: dict) -> bool | None:  # soft
    return None


# ── deepen_narrative.py — why-now ────────────────────────────────────────────
def _signals(b: dict) -> list:
    return (b.get("overview") or {}).get("why_now_signals") or []


def _c_wn_count(b: dict) -> bool | None:  # hard
    return len(_signals(b)) >= 3


def _c_wn_no_boilerplate(b: dict) -> bool | None:  # hard
    return not any(_BOILERPLATE_RE.search(s.get("text") or "") for s in _signals(b))


def _c_wn_evidence(b: dict) -> bool | None:  # hard, grounded-where-possible
    sigs = _signals(b)
    if not sigs:
        return False
    em = _ev_map(b)
    groundable = [s for s in sigs
                  if s.get("subcap_id") and se.eids_for([s["subcap_id"]], em)]
    if not groundable:
        return True if any(s.get("evidence") for s in sigs) else None
    return all(s.get("evidence") for s in groundable)


def _c_wn_not_restate(b: dict) -> bool | None:  # hard (not ALL restate)
    sigs = _signals(b)
    if not sigs:
        return None
    restate = sum(1 for s in sigs if _RESTATE_RE.search(s.get("text") or ""))
    return restate < len(sigs)


# ── deepen_narrative.py — top findings ───────────────────────────────────────
def _findings(b: dict) -> list:
    return (b.get("overview") or {}).get("top_findings") or []


def _c_tf_no_boilerplate(b: dict) -> bool | None:  # hard
    return not any(_BOILERPLATE_RE.search(f.get("body") or "") for f in _findings(b))


def _c_tf_evidence(b: dict) -> bool | None:  # hard, grounded-where-possible
    fs = _findings(b)
    if not fs:
        return False
    em = _ev_map(b)
    groundable = [f for f in fs
                  if f.get("subcap_id") and se.eids_for([f["subcap_id"]], em)]
    if not groundable:
        return True if any(f.get("evidence") for f in fs) else None
    return all(f.get("evidence") for f in groundable)


def _c_tf_platforms(b: dict) -> bool | None:  # hard (prototype requires platforms[])
    fs = _findings(b)
    if not fs:
        return False
    return any(f.get("platforms") for f in fs)


def _c_tf_not_template(b: dict) -> bool | None:  # hard (not ALL bare template)
    fs = _findings(b)
    if not fs:
        return None
    tmpl = sum(1 for f in fs if _TEMPLATE_FINDING_RE.search(f.get("body") or ""))
    return tmpl < len(fs)


# ── deepen_narrative.py / report_synthesis.py — SCQA ─────────────────────────
def _scqa(b: dict) -> str:
    return ((b.get("overview") or {}).get("narrative") or {}).get("scqa_md") or ""


def _c_scqa_not_broken(b: dict) -> bool | None:  # hard
    s = _scqa(b)
    return None if not s else not bool(_BROKEN_SCQA_RE.search(s))


def _c_scqa_depth(b: dict) -> bool | None:  # hard: ≥2 paragraphs / ≥400 real chars
    s = _scqa(b)
    if not s:
        return False
    paras = [p for p in re.split(r"\n\s*\n", s) if len(p.strip()) > 40]
    return len(paras) >= 2 and len(s) >= 400


# ── platform-opportunity composer ────────────────────────────────────────────
def _cards(b: dict) -> list:
    return (b.get("platforms") or {}).get("cards") or []


def _c_oss_opportunity(b: dict) -> bool | None:  # hard
    cards = _cards(b)
    if not cards:
        return False
    return all(_present(c.get("opportunity_md")) for c in cards
               if c.get("state") != "INSUFFICIENT_EVIDENCE")


def _c_oss_evidence(b: dict) -> bool | None:  # hard, grounded-where-possible
    cards = _cards(b)
    if not cards:
        return False
    em = _ev_map(b)
    if not em:
        return None  # no evidence available offline → deploy reparse grounds it
    groundable = [c for c in cards
                  if any(k[:2] == (c.get("pillar") or "~") for k in em)]
    if not groundable:
        return None
    return all(_present(c.get("evidence_ids")) for c in groundable)


# ── derive_insights.py / schemas.insights — InsightModal contract ────────────
def _items(b: dict) -> list:
    return (b.get("insights") or {}).get("items") or []


def _c_ins_pillar(b: dict) -> bool | None:  # hard (infer from linked_subcap_id)
    items = _items(b)
    if not items:
        return None
    return all(_present(i.get("pillar")) for i in items)


def _c_ins_flag(b: dict) -> bool | None:  # hard (map severity→flag)
    items = _items(b)
    if not items:
        return None
    return all(_present(i.get("flag")) for i in items)


# ── 2026-06-25 SEMANTIC checks (catch what structural checks cannot) ─────────
def _norm_cap(s: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


_GAP_LANG_RE = re.compile(
    r"most material capability gap|lowest[- ]scoring|least developed|"
    r"binding constraint|deepest gap|next-lowest", re.I)
_PLACEHOLDER_IN_TEXT = re.compile(r"capability dimension\s*\d+|\bsub-?cap\s*\d+\b", re.I)
_SENTINEL_REG = re.compile(r"^(role|n/?a|none|tbd|unknown|null)$", re.I)
_REAL_TRIGGER_RE = re.compile(
    r"\bmigration\b|\bhire[ds]?\b|\bhiring\b|posted|posting|consent order|go-live"
    r"|in flight|announced|launched|acquisition|merger|Q[1-4]\s*20\d\d|new C[TEDIO]O"
    r"|appointed|deadline|\bEOL\b|window|breach", re.I)


def _c_tf_title_body(b: dict) -> bool | None:  # hard: name matches body's capability
    fs = _findings(b)
    if not fs:
        return None
    for f in fs:
        name = f.get("name") or ""
        body = f.get("body") or ""
        # Coherent when the name is GROUNDED in the body (appears in it) — the name
        # is extracted from the body, so it should. This is robust to the body's
        # leading capability over-capturing past the name ("Data Quality Crisis
        # Confirmed — 'Incomplete Data'"). Fall back to the leading-capability
        # match only when the name isn't a literal substring.
        if name and _norm_cap(name) and _norm_cap(name) in _norm_cap(body):
            continue
        lead = se.leading_capability(body)
        if (lead and not se.is_placeholder_name(lead)
                and _norm_cap(lead) != _norm_cap(name)):
            return False
    return True


def _c_tf_gap_direction(b: dict) -> bool | None:  # hard: no at/above-peer "gap"
    fs = _findings(b)
    if not fs:
        return None
    for f in fs:
        if se.is_true_gap(f.get("score"), f.get("peer_median")) is False \
                and _GAP_LANG_RE.search(f.get("body") or ""):
            return False
    return True


def _c_no_placeholder_names(b: dict) -> bool | None:  # hard
    if any(se.is_placeholder_name(f.get("name")) for f in _findings(b)):
        return False
    return not any(_PLACEHOLDER_IN_TEXT.search(s.get("text") or "") for s in _signals(b))


def _c_scqa_no_scaffolding(b: dict) -> bool | None:  # hard
    s = _scqa(b)
    return None if not s else not se.scqa_has_scaffolding(s)


def _c_firmographics_plausible(b: dict) -> bool | None:  # hard
    f = _firm(b)
    aum = f.get("aum_usd")
    if aum not in (None, "") and not se.plausible_aum(aum, _subv(b)):
        return False
    reg = f.get("primary_regulator")
    return not (isinstance(reg, str) and (_SENTINEL_REG.match(reg.strip())
                                          or reg.count("(") != reg.count(")")))


def _c_source_attribution(b: dict) -> bool | None:  # hard: contamination must be badged
    """Wrong-entity (source-misattribution) contamination — the audit's
    beacon-bank case (identity 'Beacon Bank', but ticker/run-id/prose are
    BB&T/Berkshire). The correct content is only restorable by re-ingest, so the
    contract is not 'clean' but 'flagged': any entity whose snapshot carries
    convergent foreign signals MUST carry the data_quality.source_misattribution
    badge so a confidently-wrong assessment never renders unflagged. Clean → PASS;
    contaminated + badged → PASS; contaminated + unbadged → DEFECT."""
    ov = b.get("overview") or {}
    name = (ov.get("entity") or {}).get("name") or _firm(b).get("legal_name") or ""
    if not se.contamination_signals(json.dumps(ov), name)["tier"]:
        return True
    return bool((ov.get("data_quality") or {}).get("source_misattribution"))


def _c_lead_no_label_rows(b: dict) -> bool | None:  # hard: no colon/emoji/status names
    ld = _leaders(b)
    if not ld:
        return None
    for p in ld:
        nm = (p.get("name") or "").strip()
        if not nm:
            continue
        flags = se.leadership_flags(p.get("title"), p.get("tenure") or p.get("tenure_months"), nm)
        if not se.is_person_name(nm) and not flags["gap_flag"]:
            return False
    return True


def _c_wn_real_trigger(b: dict) -> bool | None:  # soft: >=1 time-bound trigger
    sigs = _signals(b)
    if not sigs:
        return None
    return any(_REAL_TRIGGER_RE.search(s.get("text") or "") for s in sigs)


CHECKS: list[Check] = [
    Check("derive_financials", "scale_metric (assets|revenue)", "hard", _c_scale_metric),
    Check("derive_financials", "firmographics_plausible", "hard", _c_firmographics_plausible),
    Check("dma_package", "source_attribution_badged", "hard", _c_source_attribution),
    Check("derive_financials", "trend", "hard", _c_trend),
    Check("derive_financials", "footprint", "hard", _c_footprint),
    Check("derive_financials", "branches", "hard", _c_branches),
    Check("derive_financials", "revenue_usd", "soft", _c_revenue),
    Check("derive_leadership", "roster_present", "soft", _c_lead_present),
    Check("derive_leadership", "no_garbage_names", "hard", _c_lead_no_garbage),
    Check("derive_leadership", "leader_titles", "soft", _c_lead_titles),
    Check("derive_leadership", "leader_flags", "hard", _c_lead_flags),
    Check("derive_leadership", "no_label_rows", "hard", _c_lead_no_label_rows),
    Check("derive_thought_leadership", "thought_leadership", "soft", _c_thought),
    Check("deepen_narrative", "why_now_count>=3", "hard", _c_wn_count),
    Check("deepen_narrative", "why_now_no_boilerplate", "hard", _c_wn_no_boilerplate),
    Check("deepen_narrative", "why_now_evidence", "hard", _c_wn_evidence),
    Check("deepen_narrative", "why_now_not_restate", "hard", _c_wn_not_restate),
    Check("deepen_narrative", "why_now_real_trigger", "soft", _c_wn_real_trigger),
    Check("deepen_narrative", "no_placeholder_names", "hard", _c_no_placeholder_names),
    Check("deepen_narrative", "findings_no_boilerplate", "hard", _c_tf_no_boilerplate),
    Check("deepen_narrative", "findings_evidence", "hard", _c_tf_evidence),
    Check("deepen_narrative", "findings_platforms", "hard", _c_tf_platforms),
    Check("deepen_narrative", "findings_not_template", "hard", _c_tf_not_template),
    Check("deepen_narrative", "findings_title_body_coherence", "hard", _c_tf_title_body),
    Check("deepen_narrative", "findings_gap_direction", "hard", _c_tf_gap_direction),
    Check("deepen_narrative", "scqa_not_broken", "hard", _c_scqa_not_broken),
    Check("deepen_narrative", "scqa_no_scaffolding", "hard", _c_scqa_no_scaffolding),
    Check("deepen_narrative", "scqa_depth>=2para", "hard", _c_scqa_depth),
    Check("platform_opportunity", "opportunity_md", "hard", _c_oss_opportunity),
    Check("platform_opportunity", "evidence_ids", "hard", _c_oss_evidence),
    Check("derive_insights", "insight_pillar", "hard", _c_ins_pillar),
    Check("derive_insights", "insight_flag", "hard", _c_ins_flag),
]


# ═════════════════════════════════════════════════════════════════════════════
# 2026-07-02 QA-GATES WORKSTREAM — Part 0.3 GLOBAL-ACCEPTANCE COUNTERS
#
# The Check registry above is boolean-per-client. The remediation plan's
# global acceptance gate (Part 0.3) is COUNTER-shaped: "SCQA template hits =
# 0", "why-now urgency window ≥80%", "starters P1C1.1.1-anchor ≤25%". Each
# CounterSpec below registers ONE such counter with its OWNING SCRIPT (same
# actionability contract as Check), a numeric target + direction, and the
# dotted path into the recorded baseline audit
# (`tests/fixtures/qa_baseline_2026-07-02.json`) that measured the same
# defect pre-remediation.
#
# Runner: `qa_startup_audit.py`. Aggregation is per-client contributions
# `{name: (num, den)}` merged across the corpus:
#     unit "pct"   → 100·Σnum/Σden      (Σden==0 → N/A, counts as PASS)
#     unit "avg"   → Σnum/Σden
#     otherwise    → Σnum               (clients / cards / rows / events)
# target == ALL_CLIENTS (-1) resolves to the number of clients audited.
#
# HARD counters gate the exit code; SOFT counters report only (they depend
# on Vertex/Clay/report availability). Under `--baseline`, a HARD failure
# whose value is at-or-better-than the recorded baseline is suppressed
# (BASELINE-KNOWN — the committed pack still carries pre-regen data); any
# value WORSE than baseline, or a failing counter with no recorded
# baseline, still fails. Post-regen the gate runs WITHOUT --baseline and
# every counter must meet its target outright.
# ═════════════════════════════════════════════════════════════════════════════

ALL_CLIENTS = -1.0  # sentinel target: value must reach the audited client count


@dataclass(frozen=True)
class CounterSpec:
    name: str
    script: str        # owning script (actionability, mirrors Check.script)
    target: float      # numeric target; ALL_CLIENTS → n audited clients
    direction: str     # "<=" | ">="
    unit: str          # "clients" | "pct" | "cards" | "rows" | "events" | "avg" | "bool" | "count"
    severity: str      # "hard" | "soft"
    baseline_path: str | None = None  # dotted path into the baseline JSON
    description: str = ""


# ── shared regexes (calibrated against the eight 2026-07 read-only audits) ──
# The audit's template families (insight why/so_what one-template class; also
# leaks into why-now/SCQA prose).
TEMPLATE_FAMILY_RES: tuple[re.Pattern, ...] = (
    re.compile(r"points to meaningful room", re.I),
    re.compile(r"points to significant room to mature", re.I),
    re.compile(r"clear headroom to move toward best practice", re.I),
    re.compile(r"targeted programme to close the gap", re.I),
)
# The 34-client SCQA fallback-composer family (startup_enrich.compose_scqa) —
# the audit's scqa.template=34 measured exactly this signature.
SCQA_TEMPLATE_RES: tuple[re.Pattern, ...] = (
    re.compile(r"The deepest capability gaps concentrate in"),
    re.compile(r"The most direct lever is to close"),
    re.compile(r"binding constraints on .{0,60}ability to operate as a coherent", re.S),
)
_EID_RE = re.compile(r"\bE-\d{1,4}\b")
_PAREN_COLON_RE = re.compile(r"\(:\s*\d")          # "(: 1.68" label-resolution bug
_F_MARKER_RE = re.compile(r"::F\d")                 # "::F1" marker leak
_PENDING_STUB_RE = re.compile(r"pending analyst synthesis", re.I)
# The OVERALL/entity maturity score claim: the number must be the direct object
# of an entity-level maturity phrase ("overall digital maturity at 1.8/5",
# "overall maturity of 2.5/5"). Per-capability/subcap gap scores ("deepest gap
# is Model Inventory at 2.2/5") are deliberately NOT matched — the number sits
# behind a capability name, never behind the maturity phrase, and the [^.\n]
# guard keeps each match inside its own sentence.
_OVERALL_SCORE_CLAIM_RE = re.compile(
    r"\bdigital maturity\b[^.\n]{0,14}?(\d\.\d{1,2})\s*(?:/\s*5|out of 5)"
    r"|(?:overall|composite|weighted|enterprise)[^.\n]{0,30}?\bmaturity\b"
    r"[^.\n]{0,14}?(\d\.\d{1,2})\s*(?:/\s*5|out of 5)",
    re.I,
)
# urgency window: explicit date / quarter / month-count / dated deadline
_WINDOW_RE = re.compile(
    r"Q[1-4][\s-]?20\d\d"
    r"|\b\d{1,2}[\s-]?(?:month|quarter|week)s?\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+20\d\d"
    r"|\bby (?:mid|end|early|late)[\s-]?20\d\d"
    r"|\bdeadline\b|\bEOL\b|\bgo-live\b",
    re.I,
)
# The prototype why-now contract: 14 fields on every signal (plan Part 4.4).
WHY_NOW_FIELDS: tuple[str, ...] = (
    "label", "category", "strength", "window", "confidence", "claim", "detail",
    "metric", "peer_context", "play", "risk", "evidence", "timeline", "impact",
)
_SENT_END = ".!?\"')]’”"  # noqa: RUF001
_GAP_TITLE_CAP_RE = re.compile(r"^(.*?)\s+(?:trails|scores|lags)\b|^(.*?)\s*(?:—|:)")
# Every deterministic so-what lead names the capability/category the card is
# about: the subcap-card form ("Make X a near-term focus") AND the GAP
# category-card forms ("Prioritize X:", "Close the X gap", "Start with X —",
# "Sequence X:"). Crediting all of them avoids false title↔body mismatches on
# GAP cards whose WHAT names an in-category subcap (2026-07-03).
_SOWHAT_CAP_RE = re.compile(
    r"\bMake (.+?) a near-term focus"
    r"|\bPrioriti[sz]e (.+?)\s*[:—]"
    r"|\bClose the (.+?) gap\b"
    r"|\bStart with (.+?)\s*[:—]"
    r"|\bSequence (.+?)\s*[:—]"
    r"|\bProtect and build on (.+?)\s*[:—]"
)
_WHAT_CAP_RE = re.compile(r"^(.+?) is one of")
# report-family ic_id prefixes (client-profile-derived cards, Part 5.1 ladder).
# CP-* = Client Profile Research Report findings (the mandate's canonical source,
# cards ship as "CP-F-001"); F-*/SEC-* = assessment-report section_analysis
# findings. INS-REC-* (recommendation-derived) is deliberately NOT counted.
_REPORT_IC_PREFIXES = ("CP-", "F-", "SEC-", "INS-RPT", "INS-CP", "INS-PROF")
# context title garbage (plan 8.2, recalibrated 2026-07-02): a title is garbage
# ONLY when it carries a structural defect — a subcap-ID prefix, an ALL-CAPS
# section-header prefix, a markdown marker, a raw file-path artifact, mid-word
# truncation, or is a raw multi-sentence excerpt. An intentional ellipsis clip
# ("…"), an inline prose slash ("Anchor Bancorp/Anchor Bank"), and a long but
# single clean sentence are NOT garbage (they over-flagged 559→0 on the pack).
_TITLE_SUBCAP_PREFIX_RE = re.compile(r"^\s*P\d+C\d+(?:\.\d+)*")
_TITLE_ALLCAPS_PREFIX_RE = re.compile(r"^\s*(?:[A-Z][A-Z&/]+\s+)+[A-Z][A-Z&/]+\s*[:\-—]")
_TITLE_MD_MARKER_RE = re.compile(r"\*\*|`|^#{1,6}\s|^\s*[-*]\s+|^\s*\d+\.\s+")
_TITLE_ARTIFACT_RE = re.compile(r"\.(?:md|json|csv|docx|xlsx|pdf|txt)\b", re.I)
_TITLE_MIDWORD_TRUNC_RE = re.compile(r"TRUNC|[A-Za-z][—–-]$")  # NOT a bare "…" clip  # noqa: RUF001
_TITLE_MULTI_SENT_RE = re.compile(r"[.!?](?:\s+[A-Z]|\s*$)")  # sentence boundary
_TITLE_NEG_RE = re.compile(r"\bNEGATIVE SEARCH\b|\bNO\s+(?:formal|evidence|M&A)\b|\bNOT\s+named\b|^no\b", re.I)
_PROSE_KEY_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|has|have|shows?|stands?|appears?|employs?|classifies|"
    r"reduced|lifted|grown|invested|shift)\b", re.I)
_ENTITY_FACT_RE = re.compile(r"\$[\d,.]+|\d+(?:\.\d+)?\s*%|\b(?:19|20)\d{2}\b")
_SUBCAP_TOKEN_RE = re.compile(r"\bP\d+C\d+(?:\.\d+)*(?:\.[A-Z]+\d+)?\b")
# financial metric keys that are actually prose sentences (snake_cased clauses)
_UNIT_LABEL_RE = re.compile(r"\((?:\$|%|#|x|bps|pts?|[A-Z$%]{1,4})[^)]*\)")

# Narrative fields scanned for cross-entity contamination. peer-context
# surfaces are deliberately EXCLUDED (naming peers there is correct), as are
# verbatim-evidence surfaces (timeline bodies quote market news).
CONTAMINATION_FIELDS: tuple[tuple[str, str], ...] = (
    # (page, dotted field description) — resolution in _contamination_texts
    ("overview", "narrative.scqa_md"),
    ("overview", "why_now_signals[].text"),
    ("overview", "why_now_signals[].detail"),
    ("overview", "why_now_signals[].play"),
    ("overview", "why_now_signals[].risk"),
    ("overview", "top_findings[].body"),
    ("overview", "top_findings[].what"),
    ("overview", "top_findings[].why"),
    ("overview", "top_findings[].so_what"),
    ("overview", "firmographics.narrative_md"),
    ("insights", "items[].what_text"),
    ("insights", "items[].why_text"),
    ("insights", "items[].so_what_text"),
    ("platforms", "cards[].opportunity_md"),
    ("platforms", "cards[].conversation_starters[]"),
)

Contribution = tuple[float, float | None]  # (numerator, denominator|None)


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _txt(v: object) -> str:
    return v if isinstance(v, str) else ""


# ── SCQA ─────────────────────────────────────────────────────────────────────
def scqa_text(b: dict) -> str:
    """The rendered executive narrative (narrative.scqa_md, else legacy scqa parts)."""
    ov = b.get("overview") or {}
    md = ((ov.get("narrative") or {}).get("scqa_md")) or ""
    if md:
        return md
    parts = ov.get("scqa") or {}
    if isinstance(parts, dict):
        return "\n\n".join(_txt(v) for v in parts.values() if _txt(v))
    return _txt(parts)


def scqa_hits_template(text: str) -> bool:
    return any(rx.search(text) for rx in TEMPLATE_FAMILY_RES + SCQA_TEMPLATE_RES)


def scqa_contradicts_score(text: str, overall: object, tol: float = 0.15) -> bool:
    """An OVERALL/entity-maturity 'N.N out of 5' claim that drifts >tol from the
    live score. Per-capability/subcap gap scores ("deepest gap is X at 1.3/5")
    legitimately differ from the composite and are NOT flagged — only a number
    asserted as the entity's overall digital maturity counts (verified against
    the pack: precise anchoring drops 37 false positives to the 1 real drift)."""
    o = _num(overall)
    if o is None or not text:
        return False
    for m in _OVERALL_SCORE_CLAIM_RE.finditer(text):
        claimed = float(m.group(1) or m.group(2))
        if abs(claimed - o) > tol:
            return True
    return False


def collect_scqa_counters(b: dict) -> dict[str, Contribution]:
    ov = b.get("overview") or {}
    s = scqa_text(b)
    return {
        "scqa_template_clients": (1.0 if s and scqa_hits_template(s) else 0.0, None),
        "scqa_zero_eid_clients": (1.0 if not _EID_RE.search(s) else 0.0, None),
        "scqa_len_gt4000_clients": (1.0 if len(s) > 4000 else 0.0, None),
        "scqa_paren_colon_clients": (1.0 if _PAREN_COLON_RE.search(s) else 0.0, None),
        "scqa_f_marker_clients": (1.0 if _F_MARKER_RE.search(s) else 0.0, None),
        "scqa_stub_clients": (1.0 if _PENDING_STUB_RE.search(s) else 0.0, None),
        "scqa_score_contradiction_clients": (
            1.0 if scqa_contradicts_score(s, ov.get("overall_score")) else 0.0, None),
    }


# ── why-now ──────────────────────────────────────────────────────────────────
def signal_has_14_fields(sig: dict) -> bool:
    # Schema completeness: the signal must carry all 14 keys (the deep why-now
    # shape). Whether an OPTIONAL field is populated on a given signal type is
    # measured separately — window population by why_now_window_pct, evidence by
    # why_now_evidence_pct. A positioning/growth signal legitimately has no
    # `window`, so requiring every field non-empty (the pre-2026-07-02 rule)
    # under-counted structurally-complete signals. The core-content fields must
    # still be non-empty; the rest need only be present.
    _CORE = ("label", "category", "strength", "detail", "claim", "play", "evidence")
    if not all(f in sig for f in WHY_NOW_FIELDS):
        return False
    return all(sig.get(f) not in (None, "", [], {}) for f in _CORE)


def signal_has_window(sig: dict) -> bool:
    blob = " ".join(_txt(sig.get(k)) for k in ("window", "text", "detail"))
    return bool(_WINDOW_RE.search(blob))


def signal_is_template(sig: dict) -> bool:
    blob = " ".join(_txt(sig.get(k)) for k in ("text", "detail"))
    return bool(_BOILERPLATE_RE.search(blob) or _RESTATE_RE.search(blob)
                or scqa_hits_template(blob))


def collect_why_now_counters(b: dict) -> dict[str, Contribution]:
    sigs = _signals(b)
    n = float(len(sigs))
    return {
        "why_now_ge3_clients": (1.0 if len(sigs) >= 3 else 0.0, None),
        "why_now_fields14_pct": (float(sum(signal_has_14_fields(s) for s in sigs)), n),
        "why_now_evidence_pct": (float(sum(bool(s.get("evidence")) for s in sigs)), n),
        "why_now_window_pct": (float(sum(signal_has_window(s) for s in sigs)), n),
        "why_now_template_pct": (float(sum(signal_is_template(s) for s in sigs)), n),
    }


# ── top findings ─────────────────────────────────────────────────────────────
def finding_is_truncated(f: dict) -> bool:
    """Mid-word truncation / too-short body (the audit's 60/378 class:
    'uneve—', 'consol—', ellipsis clips). Headline-style bodies without a
    terminal period are NOT flagged — only hard clip markers and shortness."""
    body = _txt(f.get("body")).rstrip()
    if not body:
        return True
    if len(body) < 80:
        return True
    return bool(re.search(r"(?:…|\.{3}|[A-Za-z][—–-])$", body))  # noqa: RUF001


def collect_findings_counters(b: dict) -> dict[str, Contribution]:
    fs = _findings(b)
    n = float(len(fs))
    wwsw = sum(all(_present(f.get(k)) for k in ("what", "why", "so_what")) for f in fs)
    scored = sum(all(f.get(k) is not None for k in ("score", "peer_median", "subcap_id"))
                 for f in fs)
    return {
        "findings_wwsw_pct": (float(wwsw), n),
        "findings_scored_pct": (float(scored), n),
        "findings_evidence_pct": (float(sum(bool(f.get("evidence")) for f in fs)), n),
        "findings_truncated_count": (float(sum(finding_is_truncated(f) for f in fs)), None),
    }


# ── insight cards ────────────────────────────────────────────────────────────
def insight_is_template(item: dict) -> bool:
    blob = " ".join(_txt(item.get(k)) for k in ("why_text", "so_what_text"))
    return scqa_hits_template(blob)


def insight_title_body_mismatch(item: dict) -> bool:
    """GAP-card LATERAL-join bug: title names capability X, body describes Y."""
    if not (_txt(item.get("ic_id")).startswith("GAP-")):
        return False
    title = _txt(item.get("title"))
    m = _GAP_TITLE_CAP_RE.match(title)
    title_cap = _norm_cap((m.group(1) or m.group(2)) if m else title)
    if not title_cap:
        return False
    body_caps = []
    sw = _SOWHAT_CAP_RE.search(_txt(item.get("so_what_text")))
    if sw:
        body_caps.append(_norm_cap(next((g for g in sw.groups() if g), "")))
    wh = _WHAT_CAP_RE.match(_txt(item.get("what_text")))
    if wh:
        body_caps.append(_norm_cap(wh.group(1)))
    if not body_caps:
        return False
    return all(title_cap != c and title_cap not in c and c not in title_cap
               for c in body_caps if c)


def collect_insight_counters(b: dict) -> dict[str, Contribution]:
    items = _items(b)
    n = float(len(items))
    tmpl = sum(insight_is_template(i) for i in items)
    zero_ev = sum(not (i.get("linked_e_ids") or i.get("evidence")) for i in items)
    affects = sum(len(i.get("affects") or []) for i in items)
    mism = sum(insight_title_body_mismatch(i) for i in items)
    report = sum(_txt(i.get("ic_id")).startswith(_REPORT_IC_PREFIXES) for i in items)
    return {
        "insights_template_pct": (float(tmpl), n),
        "insights_zero_evidence_pct": (float(zero_ev), n),
        "insights_affects_avg": (float(affects), n),
        "insights_title_body_mismatch_cards": (float(mism), None),
        "insights_report_sourced_pct": (float(report), n),
    }


# ── heatmap ──────────────────────────────────────────────────────────────────
def collect_heatmap_counters(b: dict) -> dict[str, Contribution]:
    hm = b.get("heatmap") or {}
    cells = hm.get("cells") or []
    n = float(len(cells))
    vc = (b.get("heatmap_value_chain") or {}).get("value_chain_buckets") \
        or hm.get("value_chain_buckets") or []
    narr = hm.get("narrative") or {}
    synth = narr.get("per_subcap_meta") or narr.get("per_subcap") or {}
    peer = sum(c.get("peer_median") is not None for c in cells)
    ev = sum(bool(c.get("enrichment_evidence_ids")) for c in cells)
    band = sum(_present(c.get("band")) for c in cells)
    cap = sum("cap_applied" in c for c in cells)
    return {
        "vc_buckets6_clients": (1.0 if len(vc) >= 6 else 0.0, None),
        "heatmap_subcap_synthesis_clients": (1.0 if synth else 0.0, None),
        "heatmap_peer_clients": (1.0 if peer else 0.0, None),
        "heatmap_peer_median_cells_pct": (float(peer), n),
        "heatmap_evidence_clients": (1.0 if ev else 0.0, None),
        "heatmap_evidence_cells_pct": (float(ev), n),
        "heatmap_band_pct": (float(band), n),
        "heatmap_cap_fields_pct": (float(cap), n),
    }


# ── stress-test probes: focus areas + per-subcap synthesis hygiene ───────────
# 2026-07-02 coordinator additions — each caught a REAL defect the unit
# fixtures missed during the D3 stress runs.
_FOCUS_TITLE_ID_RE = re.compile(r"^F-\d+$")
_SYNTH_GENERIC_RE = re.compile(r"capability dimension|\bSubcap \d+ \(P", re.I)
_SYNTH_SCORE_NOISE_RE = re.compile(
    r"\bE-\d{1,4}\b|\d+\.\d+|\bM[1-5]\b|\bout of 5\b|/\s*5\b")
_TIMELINE_ARTIFACT_RE = re.compile(
    r"[=*_#|]\s*$"                                  # dangling markup/table chars
    r"|^\s*(?:[-*•>]\s|\d+\.\s|#{1,6}\s|\*\*|__)")  # list-marker / md-emphasis lead


def _focus_quote(item: dict) -> str:
    g = item.get("grounding") or {}
    return _txt(g.get("representative_quote")) or _txt(item.get("verbatim_quote"))


def _focus_eids(item: dict) -> list:
    g = item.get("grounding") or {}
    return g.get("evidence_e_ids") or item.get("evidence_e_ids") or []


def collect_focus_counters(b: dict) -> dict[str, Contribution]:
    fa = b.get("focus_areas") or {}
    items = fa.get("items") if isinstance(fa, dict) else fa
    items = items or []
    bad_title = sum(
        1 for it in items
        if _FOCUS_TITLE_ID_RE.match(_txt(it.get("title")).strip())
        or len(_txt(it.get("title")).strip()) < 8)
    bad_grounding = sum(
        1 for it in items
        if "[E-" in _focus_quote(it) and not _focus_eids(it))
    return {
        "focus_title_hygiene": (float(bad_title), None),
        "focus_grounding_eids": (float(bad_grounding), None),
    }


def _synthesis_texts(b: dict) -> list[str]:
    narr = (b.get("heatmap") or {}).get("narrative") or {}
    per_subcap = narr.get("per_subcap") or {}
    out: list[str] = []
    for v in (per_subcap.values() if isinstance(per_subcap, dict) else per_subcap):
        if isinstance(v, dict):
            v = v.get("narrative_md") or v.get("text") or ""
        if _txt(v):
            out.append(v)
    return out


_VENDOR_TOKEN_CACHE: tuple[str, ...] | None = None


def _vendor_tokens() -> tuple[str, ...]:
    global _VENDOR_TOKEN_CACHE
    if _VENDOR_TOKEN_CACHE is None:
        from app.services.nlp import taxonomy
        names = set(taxonomy._CATALOGUE) | {v for v, _l in taxonomy._CATALOGUE.values()}
        _VENDOR_TOKEN_CACHE = tuple(n.lower() for n in names if len(n) >= 3)
    return _VENDOR_TOKEN_CACHE


def synthesis_lacks_substance(text: str) -> bool:
    """Evidence-bearing narrative with NOTHING from the evidence itself —
    no residual number and no catalogue-vendor token once E-IDs and
    score/peer/band numerics are stripped (citation theatre)."""
    if not _EID_RE.search(text):
        return False  # not evidence-bearing → other counters own it
    residue = _SYNTH_SCORE_NOISE_RE.sub("", text)
    if re.search(r"\d", residue):
        return False
    low = residue.lower()
    return not any(tok in low for tok in _vendor_tokens())


def collect_synthesis_counters(b: dict) -> dict[str, Contribution]:
    texts = _synthesis_texts(b)
    none_leak = sum(": None" in t for t in texts)
    generic = sum(bool(_SYNTH_GENERIC_RE.search(t)) for t in texts)
    hollow = sum(synthesis_lacks_substance(t) for t in texts)
    return {
        "synthesis_none_leak": (float(none_leak), None),
        "synthesis_generic_name": (float(generic), None),
        "synthesis_evidence_substance": (float(hollow), None),
    }


# ── platforms + roadmap ──────────────────────────────────────────────────────
def _starters(card: dict) -> list[str]:
    cs = card.get("conversation_starters")
    if isinstance(cs, list) and cs:
        return [_txt(s) if isinstance(s, str) else json.dumps(s) for s in cs]
    one = card.get("conversation_starter")
    return [_txt(one)] if one else []


def starter_names_entity_fact(card: dict, entity_name: str) -> bool:
    """A starter is entity-specific when it carries a real fact: a $ figure,
    a percentage, a year, or the entity's own name — not just subcap ids."""
    for s in _starters(card):
        no_subcaps = _SUBCAP_TOKEN_RE.sub("", s)
        no_fit = re.sub(r"fit \d+(?:\.\d+)?/100", "", no_subcaps)
        if _ENTITY_FACT_RE.search(no_fit):
            return True
        if entity_name and entity_name in s:
            return True
    return False


def opportunity_signature(md: object) -> str:
    """Skeleton signature: strip entity-variant tokens (bold names, parens,
    subcap ids, numbers, AND Title-Case name runs), keep the full template
    bones. Reproduces the audit's one-skeleton measurement on the committed
    pack.

    2026-07-06 (platform v3): the prior gate KEPT Title-Case subcap names in
    prose ('led by Competitive Analysis. Competitive Analysis scores …'), so
    swapping one subcap name for another read as a distinct signature and the
    48.6% structural collapse hid at 0.9% dominant. Collapsing runs of ≥1
    Title-Case word to <NM> makes the collapse measurable again."""
    t = _txt(md)
    t = re.sub(r"\*\*[^*]+\*\*", "<B>", t)
    t = re.sub(r"\([^)]*\)", "()", t)
    t = re.sub(r"\bP\d+C?\d*(?:\.\d+)*\b", "<S>", t)
    t = re.sub(r"\d+(?:\.\d+)?", "<N>", t)
    # Collapse Title-Case NAME runs (subcap / product / peer names) — runs of
    # one-or-more Capitalised words, kept AFTER the number sub so 'M4'-style
    # tokens are already <N>. Sentence-leading capitals collapse too, which is
    # fine: the template bones ('addresses', 'scores', 'is the next surface')
    # are lower-case and survive.
    t = re.sub(r"\b[A-Z][A-Za-z&'.-]+(?:\s+[A-Z][A-Za-z&'.-]+)*", "<NM>", t)
    return re.sub(r"\s+", " ", t).strip()


_STORY_FACT_RE = re.compile(
    r"\$\s?\d|\b(?:19|20)\d{2}\b|\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?/5|peer median"
    r"|\b[A-Z][A-Za-z]+ (?:platform|Cloud|Core|CRM|API)\b")
_STORY_CITE_RE = re.compile(r"\[[^\]]*E-[A-Za-z0-9]")


def story_facts_ok(story_md: object) -> bool:
    """A real dossier story carries ≥1 bracketed E-ID citation AND ≥1 concrete
    fact (named-system 'X platform/Cloud/Core', a score-vs-peer, a %, a
    $-figure, or a year) — the mandate's 'narratives heavy on data and
    evidence (non-fabricated)'. Mirrors platform_dossier.story_facts_ok."""
    t = _txt(story_md)
    if not t:
        return False
    return bool(_STORY_CITE_RE.search(t)) and bool(_STORY_FACT_RE.search(t))


def _roadmap_recs(b: dict) -> list[dict]:
    rm = b.get("platforms_roadmap") or {}
    out: list[dict] = []
    for ph in rm.get("phases") or []:
        out.extend(ph.get("recommendations") or [])
    return out


def collect_platform_counters(b: dict, entity_name: str = "") -> dict[str, Contribution]:
    cards = _cards(b)
    n = float(len(cards))
    fb = sum(_present(c.get("fit_breakdown")) for c in cards)
    ready = sum(c.get("state") == "READY" for c in cards)
    red_hot = sum(
        1 for c in cards
        if c.get("readiness_index") == "red" and (_num(c.get("fit_score")) or 0) >= 80)
    anchored = sum(
        1 for c in cards
        if _starters(c) and "P1C1.1.1" in _starters(c)[0])
    facts = sum(starter_names_entity_fact(c, entity_name) for c in cards if _starters(c))
    with_starters = float(sum(bool(_starters(c)) for c in cards))
    zero_ev = sum(not c.get("evidence_ids") for c in cards)
    # Platform v3 dossier gates: story_md must ship (never the cache-cold null
    # the audit found on 470/470) and carry real facts (≥1 bracketed E-ID +
    # ≥1 named-system / score-vs-peer / %-or-year concrete fact).
    story_present = sum(bool(_txt(c.get("story_md"))) for c in cards)
    with_story = [c for c in cards if _txt(c.get("story_md"))]
    story_facts = sum(story_facts_ok(c.get("story_md")) for c in with_story)
    # 2026-07-14 skew-audit gates: (a) the absent term must never again
    # INFLATE a zero-peer-coverage family past its graded ceiling
    # (0.08 x 0.45 x 100 = 3.6 pts — the regression tripwire on the
    # fused boost ladder; a hot card led by opportunity is legitimate),
    # (b) a hot (fit≥60) card must never be an out-of-vertical family,
    # (c) an integrate-lens card's prose must never argue the greenfield
    # frame.
    zero_peer_hot = 0
    out_of_vertical_hot = 0
    incumbent_greenfield_prose = 0
    hot_unbacked = 0
    for c in cards:
        bd = c.get("fit_breakdown") if isinstance(c.get("fit_breakdown"), dict) else {}
        fac = bd.get("factors") or {}
        ab = fac.get("absent_boost") or {}
        fit_v = _num(c.get("fit_score")) or 0
        if (bd.get("absent_families")
                and _num(ab.get("peer_coverage")) == 0.0
                and (_num(ab.get("points")) or 0) > 3.7):
            zero_peer_hot += 1
        vr = fac.get("vertical_relevance") or {}
        if fit_v >= 60 and (_num(vr.get("value")) or 1.0) < 1.0:
            out_of_vertical_hot += 1
        lens = str(((ab.get("stack_lens") or {}).get("lens")) or "")
        if lens == "integrate":
            prose = " ".join(_txt(c.get(k)) for k in ("story_md", "opportunity_md"))
            if _GREENFIELD_FRAME_RE.search(prose):
                incumbent_greenfield_prose += 1
        # W4 (soft/report-only): a hot card the analyst report never
        # recommended — tracked, not gated (the engine legitimately surfaces
        # data-driven finds the analyst didn't write up).
        # analyst_backing lives at the breakdown top level (not under factors).
        if fit_v >= 60 and not (bd.get("analyst_backing") or {}).get("backed", True):
            hot_unbacked += 1
    recs = _roadmap_recs(b)
    rn = float(len(recs))
    root = sum(bool(r.get("root_cause_e_ids") or r.get("root_cause")) for r in recs)
    outc = sum(_present(r.get("outcomes")) for r in recs)
    lift_null = sum(r.get("maturity_lift") is None for r in recs)
    phases = (b.get("platforms_roadmap") or {}).get("phases") or []
    return {
        "platform_fit_breakdown_pct": (float(fb), n),
        "platform_state_ready_pct": (float(ready), n),
        "platform_red_fit80_cards": (float(red_hot), None),
        "starters_p1c111_anchor_pct": (float(anchored), with_starters),
        "starters_entity_fact_pct": (float(facts), with_starters),
        "platform_cards_zero_evidence": (float(zero_ev), None),
        "platform_story_present_pct": (float(story_present), n),
        "platform_story_facts_pct": (float(story_facts), float(len(with_story)) or None),
        "roadmap_single_phase_clients": (1.0 if len(phases) == 1 else 0.0, None),
        "roadmap_rec_root_cause_pct": (float(root), rn),
        "roadmap_rec_outcomes_pct": (float(outc), rn),
        "roadmap_maturity_lift_null_pct": (float(lift_null), rn),
        "platform_zero_peer_hot_absent_cards": (float(zero_peer_hot), None),
        "platform_out_of_vertical_hot_cards": (float(out_of_vertical_hot), None),
        "platform_incumbent_greenfield_prose_cards": (
            float(incumbent_greenfield_prose), None),
        "platform_hot_unbacked_cards": (float(hot_unbacked), None),
    }


# Greenfield-frame vocabulary that must not survive on an integrate-lens
# card (the incumbent occupies the layer; the argument is integration).
_GREENFIELD_FRAME_RE = re.compile(
    r"greenfield|open ground|blank slate|no incumbent to unwind|"
    r"lands? on open ground|net-new introduction",
    re.I,
)


# ── context ──────────────────────────────────────────────────────────────────
def event_date_defaulted(ev: dict) -> bool:
    prec = ev.get("date_precision")
    if prec is not None:
        return prec == "publish_fallback"
    # pre-migration pack: the fallback writer pinned events to month starts
    d = _txt(ev.get("event_date"))
    return (not d) or d.endswith("-01")


def title_is_garbage(title: object) -> bool:
    """A timeline title is garbage only when structurally malformed — see the
    `_TITLE_*` regex block. An intentional ellipsis clip, an inline prose slash,
    and a long single clean sentence are all legitimate NLP titles."""
    t = _txt(title).strip()
    if not t:
        return True
    if _TITLE_SUBCAP_PREFIX_RE.match(t):
        return True
    if _TITLE_ALLCAPS_PREFIX_RE.match(t):
        return True
    if _TITLE_MD_MARKER_RE.search(t) or _TITLE_ARTIFACT_RE.search(t):
        return True
    if _TITLE_MIDWORD_TRUNC_RE.search(t):
        return True
    return len(_TITLE_MULTI_SENT_RE.findall(t)) >= 2  # raw multi-sentence excerpt


def is_prose_metric_key(key: object) -> bool:
    """Snake-cased sentence fragments masquerading as metric names
    ('workforce_scale_stands_at_approximately_750')."""
    k = _txt(key)
    if _UNIT_LABEL_RE.search(k):
        return False  # explicitly unit-labeled → a real metric
    words = [w for w in re.split(r"[_\s]+", k) if w]
    return len(words) >= 4 and bool(_PROSE_KEY_VERB_RE.search(" ".join(words)))


def sentiment_is_structured(sent: object) -> bool:
    # D5 context_extras.sentiment_view contract: {sources: [{source, kind,
    # value, max, n, polarity, themes[], drilldown, evidence_e_id}]} —
    # value may be honest-None, but the KEY must exist on every row.
    if isinstance(sent, dict) and isinstance(sent.get("sources"), list) and sent["sources"]:
        return all(isinstance(r, dict) and _present(r.get("source"))
                   and ("value" in r or "score" in r)
                   for r in sent["sources"])
    if isinstance(sent, dict) and (
            isinstance(sent.get("employee"), list) or isinstance(sent.get("customer"), list)):
        return True
    if isinstance(sent, list) and sent:
        return all(isinstance(r, dict) and _present(r.get("source"))
                   and (r.get("value") is not None or r.get("score") is not None)
                   for r in sent)
    return False


def _fin_series(fin: dict) -> tuple[list[dict], int]:
    """(labeled-candidate series rows, total series count).

    D5 financials_view contract: ``series_labeled`` = [{metric, unit, fy[],
    values[]}] is the Part 8.4 shape (legacy ``years``/``series`` kept in
    parallel for older consumers). A legacy block WITHOUT a labeled twin
    counts as one unlabeled series."""
    labeled = fin.get("series_labeled")
    if isinstance(labeled, list) and labeled:
        rows = [s for s in labeled if isinstance(s, dict)]
        return rows, len(labeled)
    series = fin.get("series")
    if isinstance(series, list) and series:  # experimental pre-D5 shape
        return [s for s in series if isinstance(s, dict)], len(series)
    if fin.get("years") or series:  # legacy unlabeled block only
        return [], 1
    return [], 0


def collect_context_counters(b: dict) -> dict[str, Contribution]:
    ctx = b.get("context") or {}
    events = ctx.get("timeline_events") or []
    n = float(len(events))
    defaulted = sum(event_date_defaulted(e) for e in events)
    garbage = sum(title_is_garbage(e.get("title")) for e in events)
    artifacts = sum(bool(_TIMELINE_ARTIFACT_RE.search(_txt(e.get("title")).rstrip()))
                    for e in events)
    neg = sum(bool(_TITLE_NEG_RE.search(_txt(e.get("title")))) for e in events)
    no_eid = sum(not (e.get("e_id") or e.get("evidence_e_ids")) for e in events)
    seen: set[tuple[str, str]] = set()
    dupes = 0
    for e in events:
        key = (_norm_cap(e.get("title")), _txt(e.get("event_date")))
        if key[0] and key in seen:
            dupes += 1
        seen.add(key)
    acqs = ctx.get("acquisitions") or []
    an = float(len(acqs))
    framed = sum(bool(_present(a.get("acquirer")) or _present(a.get("target")))
                 for a in acqs)
    fin = ctx.get("financials") or {}
    prose_keys = sum(is_prose_metric_key(k) for k in (fin.get("metrics") or {}))
    series, series_total = _fin_series(fin)
    labeled = sum(_present(s.get("metric")) and _present(s.get("unit")) for s in series)
    firm = ctx.get("firmographics") or {}
    sent = ctx.get("sentiment") if ctx.get("sentiment") is not None else firm.get("sentiment")
    has_sent = sent not in (None, "", [], {})
    lic = bool(_present(firm.get("license_type")) or _present(firm.get("charter"))) \
        and _present(firm.get("jurisdictions"))
    leaders = firm.get("leadership") or []
    ln = float(len(leaders))
    tenure = sum(p.get("tenure_months") is not None or _present(p.get("tenure"))
                 for p in leaders)
    narr = ctx.get("narrative") or {}
    return {
        "context_defaulted_date_pct": (float(defaulted), n),
        "context_title_garbage_pct": (float(garbage), n),
        "timeline_title_artifacts": (float(artifacts), None),
        "context_negation_title_pct": (float(neg), n),
        "context_event_no_eid_pct": (float(no_eid), n),
        "context_duplicate_events": (float(dupes), None),
        "acq_structured_pct": (float(framed), an),
        "fin_prose_keys": (float(prose_keys), None),
        "fin_series_labeled_pct": (float(labeled), float(series_total)),
        "sentiment_structured_pct": (
            1.0 if sentiment_is_structured(sent) else 0.0,
            1.0 if has_sent else 0.0),
        "context_license_jurisdiction_clients": (1.0 if lic else 0.0, None),
        "context_leadership_tenure_pct": (float(tenure), ln),
        "context_trend_md_missing_clients": (
            0.0 if _present(narr.get("trend_md")) else 1.0, None),
    }


# ── tech stack ───────────────────────────────────────────────────────────────
def collect_techstack_counters(b: dict) -> dict[str, Contribution]:
    # nlp.taxonomy is the audit's own deny-list source (Part 9.1). Lazy import
    # keeps the contract importable in stripped environments.
    from app.services.nlp import taxonomy
    items = (b.get("techstack") or {}).get("items") or []
    n = float(len(items))
    lang = noise = 0
    for it in items:
        kind = taxonomy.classify(_txt(it.get("product_name") or it.get("product")))["kind"]
        if kind == "engineering_signal":
            lang += 1
        elif kind == "noise":
            noise += 1
    absent = sum(it.get("status") == "ABSENT" for it in items)
    peer_cov = sum(it.get("peer_coverage") is not None for it in items)
    # techstack_read 4-state enum + CONFIRMED_REMOVED (decommissioned)
    valid = sum(it.get("status") in ("CONFIRMED", "INFERRED", "CLAIMED", "ABSENT",
                                     "CONFIRMED_REMOVED")
                for it in items)
    return {
        "tech_language_os_rows": (float(lang), None),
        "tech_noise_rows": (float(noise), None),
        "tech_disallowed_rows": (float(lang + noise), None),
        "tech_absent_row_clients": (1.0 if absent else 0.0, None),
        "tech_peer_coverage_clients": (1.0 if peer_cov else 0.0, None),
        "tech_status_valid_pct": (float(valid), n),
    }


# ── firmographics (the audit's 15-field null matrix + provenance) ────────────
FIRM_FIELDS: tuple[str, ...] = (
    "revenue_usd", "thought_leadership", "website", "ticker", "cagr", "hq",
    "trend", "founded", "branches", "size_tier", "geography", "footprint",
    "leadership", "sentiment", "aum_usd",
)
# fields derived by NLP/Gemini that must carry provenance (a companion
# *_basis/*_source key or an embedded derived_from/source marker)
_PROVENANCED_FIELDS: tuple[str, ...] = (
    "trend", "cagr", "website", "footprint", "thought_leadership", "revenue_usd",
    "aum_usd",
)


def field_has_provenance(firm: dict, field: str) -> bool:
    stems = {field, field.removesuffix("_usd")}  # aum_usd → aum_basis (pack shape)
    for stem in stems:
        for suffix in ("_basis", "_source", "_derived_from", "_provenance"):
            if _present(firm.get(f"{stem}{suffix}")):
                return True
    v = firm.get(field)
    if isinstance(v, dict) and (v.get("derived_from") or v.get("source") or v.get("basis")):
        return True
    return bool(isinstance(v, list) and v and all(
        isinstance(x, dict) and (x.get("derived_from") or x.get("source")) for x in v))


# ── Firmographics DEPLOY-COVERAGE FLOOR (operator safeguard 2026-07-06) ──────
# Operator report: "Still majority clients have empty firmographics state not
# enriched during deployment. What safeguards are there for this to ensure this
# never happens again?" This gate is that guarantee. For each ENRICHABLE
# firmographics field it pins the MAXIMUM number of clients (of 94) that may
# ship the field EMPTY *and* without a legitimate honest-null basis. A value is
# SATISFIED when it is present, OR legitimately absent for the entity's
# subvertical (a branch-less asset manager's branch count, a private/mutual
# institution's public ticker) — never a fabricated value. The DEPLOY gate
# (`qa_startup_audit` run WITHOUT `--baseline`, after the Vertex-warm regen
# fires `enrich_empty_surfaces.firmographics_extraction`) FAILS the deploy when
# a field exceeds its floor, so a pack that ships majority-empty firmographics
# can never deploy again.
#
# Floors are calibrated for the Vertex-WARM deploy — the Vertex-cold local regen
# cannot reach them, which is expected and is why the pre-regen tracker runs
# WITH `--baseline` (suppresses a HARD miss at-or-better-than the recorded null
# line). HARD fields are structurally recoverable for (almost) every FSI from
# its own report material; SOFT fields (ticker, employees) are honest-null-
# dominant (private / undisclosed) and report-only, never gating the exit code.
#     field:            (max_empty_clients, severity, why)
_FIRM_COVERAGE_FLOOR: dict[str, tuple[int, str, str]] = {
    "website":          (6,  "hard", "every operating FSI has an own-domain website"),
    "founded":          (12, "hard", "every institution has a founding/charter year"),
    "hq":               (16, "hard", "every institution has a headquarters location"),
    "geography":        (14, "hard", "every institution states an operating geography"),
    "cagr":             (22, "hard", "growth rate; honest-null when no multi-year series"),
    "branches":         (20, "hard", "branch count; honest-null for branch-less models"),
    "ticker":           (40, "soft", "public ticker; honest-null for private/mutual"),
    "employees_approx": (45, "soft", "headcount; honest-null when undisclosed/member-scale"),
}


def _firm_field_present(firm: dict, field: str) -> bool:
    """Present when the flattened firmographics carries the field. Headcount is
    exposed under either the ``employees_approx`` parsed-fact or the typed
    ``headcount`` column."""
    if field == "employees_approx":
        return _present(firm.get("employees_approx")) or _present(firm.get("headcount"))
    return _present(firm.get(field))


def _firm_field_honest_null(firm: dict, subv: str, field: str) -> bool:
    """True when an EMPTY value is LEGITIMATE for this entity — a PASS, never
    counted against the deploy floor. Subvertical-aware and never guessed
    (reuses the same honest-null allowlists as the Check registry)."""
    s = (subv or "").upper()
    if field in ("branches", "footprint"):
        return s in _BRANCHLESS_SUBV
    if field == "ticker":
        return s in _NON_TICKER_SUBV
    if field == "cagr":
        # a CAGR needs a multi-year financial series; a client whose corpus
        # carries none (no highlight lines, no trend) cannot honestly state one.
        fh = firm.get("financial_highlights") or {}
        lines = fh.get("lines") if isinstance(fh, dict) else None
        return not (lines or _present(firm.get("trend")))
    if field == "employees_approx":
        # a member (CU) / branch scale fact stands in for an undisclosed headcount
        return _present(firm.get("members")) or _present(firm.get("branches"))
    return False


def firm_field_shipped_empty(firm: dict, subv: str, field: str) -> bool:
    """The exact condition the deploy floor bounds: the field shipped EMPTY and
    its emptiness is NOT a legitimate honest-null."""
    if _firm_field_present(firm, field):
        return False
    return not _firm_field_honest_null(firm, subv, field)


def collect_firmographic_counters(b: dict) -> dict[str, Contribution]:
    firm = _firm(b)
    subv = _subv(b)
    out: dict[str, Contribution] = {}
    for f in FIRM_FIELDS:
        out[f"firm_null_{f}"] = (0.0 if _present(firm.get(f)) else 1.0, None)
    # Deploy-coverage floor: enrichable-empty (honest-null-credited) per field.
    for f in _FIRM_COVERAGE_FLOOR:
        out[f"firm_empty_{f}"] = (
            1.0 if firm_field_shipped_empty(firm, subv, f) else 0.0, None)
    present_derived = [f for f in _PROVENANCED_FIELDS if _present(firm.get(f))]
    out["firm_provenance_pct"] = (
        float(sum(field_has_provenance(firm, f) for f in present_derived)),
        float(len(present_derived)))
    return out


# ── cross-file value parity ──────────────────────────────────────────────────
def _pillar_map(v: object) -> dict[str, float]:
    if isinstance(v, dict):
        return {k: n for k, x in v.items() if (n := _num(x)) is not None}
    if isinstance(v, list):
        return {r.get("pillar_id") or r.get("id"): n for r in v
                if isinstance(r, dict) and (n := _num(r.get("score"))) is not None}
    return {}


def score_parity_mismatch(b: dict, eps: float = 0.011) -> bool:
    """overview ↔ clients/{id}.json ↔ scores.json ↔ dashboard card, ε .01.

    The committed pack rounds some copies to 2dp, so the effective epsilon
    adds one ulp of that rounding (.011) — a real drift (the audit's 19
    clients) is orders larger.
    """
    ov = b.get("overview") or {}
    overalls = [_num(ov.get("overall_score")),
                _num(((b.get("client_scores") or {}).get("scores") or {}).get("overall")),
                _num((b.get("scores_row") or {}).get("overall")),
                _num((b.get("dashboard_card") or {}).get("overall_score"))]
    known = [x for x in overalls if x is not None]
    if known and max(known) - min(known) > eps:
        return True
    sources = [_pillar_map(ov.get("pillar_scores")),
               _pillar_map(((b.get("client_scores") or {}).get("scores") or {}).get("pillars")),
               _pillar_map((b.get("scores_row") or {}).get("pillars"))]
    for pid in {k for s in sources for k in s}:
        vals = [s[pid] for s in sources if pid in s]
        if vals and max(vals) - min(vals) > eps:
            return True
    return False


def collect_parity_counters(b: dict) -> dict[str, Contribution]:
    return {"score_parity_mismatch_clients": (1.0 if score_parity_mismatch(b) else 0.0, None)}


# ── markdown lint over every *_md field ──────────────────────────────────────
def _walk_md_fields(node: object, path: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            if isinstance(v, str) and str(k).endswith("_md") and v:
                out.append((p, v))
            else:
                out.extend(_walk_md_fields(v, p))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(_walk_md_fields(v, f"{path}[{i}]"))
    return out


def collect_markdown_counters(b: dict) -> dict[str, Contribution]:
    from app.services.nlp import quality
    flagged = 0
    for page in ("overview", "insights", "heatmap", "heatmap_value_chain",
                 "platforms", "platforms_roadmap", "context", "health",
                 "focus_areas"):
        for _path, text in _walk_md_fields(b.get(page) or {}):
            if quality.markdown_lint(text):
                flagged += 1
    return {"markdown_lint_flagged_fields": (float(flagged), None)}


# ── cross-entity contamination ───────────────────────────────────────────────
def _contamination_texts(b: dict) -> list[str]:
    out: list[str] = []
    ov = b.get("overview") or {}
    out.append(scqa_text(b))
    out.append(_txt((ov.get("firmographics") or {}).get("narrative_md")))
    for s in _signals(b):
        out.extend(_txt(s.get(k)) for k in ("text", "detail", "play", "risk"))
    for f in _findings(b):
        out.extend(_txt(f.get(k)) for k in ("body", "what", "why", "so_what"))
    for i in _items(b):
        out.extend(_txt(i.get(k)) for k in ("what_text", "why_text", "so_what_text"))
    for c in _cards(b):
        out.append(_txt(c.get("opportunity_md")))
        out.extend(_starters(c))
    return [t for t in out if t]


# A foreign name inside an explicit peer/corporate-lineage clause is analytic
# content, not contamination ("below FCS peer median (Compeer …)", "subsidiary
# of CI Financial Corp.", "Compeer Financial, PCA d/b/a ProPartners").
_PEER_CUE_RE = re.compile(
    r"\bpeer|\bbenchmark|\bmedian\b|\bcohort\b|d/b/a|\bdba\b|\bsubsidiar|"
    r"\bparent\b|\baffiliate|\bcompetitor|\bcomparable|\bacqui[sr]|\bmerger\b|"
    r"\bselected\b|\bdivision\b", re.I)


def foreign_name_hits(b: dict, own_name: str, foreign_names: Iterable[str]) -> list[str]:
    """Case-sensitive full-name scan for OTHER clients' entity names inside
    this client's derived narratives. Peer-context surfaces are excluded by
    construction (see CONTAMINATION_FIELDS); names ≤3 chars (CCU/TII/VNO
    ticker-like) and own-name super/substrings are skipped; a name whose
    every occurrence sits in a peer/lineage clause (_PEER_CUE_RE within
    ±120 chars) is peer framing, not contamination."""
    texts = _contamination_texts(b)
    hits: list[str] = []
    for name in foreign_names:
        if not name or len(name) <= 3 or name == own_name:
            continue
        if name in own_name or own_name in name:
            continue
        # word-ish boundaries: possessives ("Langley FCU's") and sentence
        # punctuation after the name still count as full-name mentions
        rx = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")
        cued = raw = False
        for t in texts:
            for m in rx.finditer(t):
                window = t[max(0, m.start() - 120): m.end() + 120]
                if _PEER_CUE_RE.search(window):
                    cued = True
                else:
                    raw = True
        if raw and not cued:
            hits.append(name)
    return hits


def collect_contamination_counters(
        b: dict, own_name: str, foreign_names: Iterable[str]) -> dict[str, Contribution]:
    return {"contamination_hits": (float(len(foreign_name_hits(b, own_name, foreign_names))), None)}


# ── surfaces present ─────────────────────────────────────────────────────────
PAGE_FILES: tuple[str, ...] = (
    "overview", "insights", "heatmap", "heatmap_pillar", "platforms",
    "platforms_roadmap", "context", "health", "techstack", "runs",
)
# New D3 surfaces the exporter bakes at regen (tolerated-absent pre-regen,
# counted): focus_areas (default-view data), heatmap_value_chain (VC zoom),
# heatmap_category (category-grain names — kills the cold-serve label bug),
# evidence (full per-run evidence_index list — the EvidenceDrawer's pack-first
# source; 2026-07-06 remediation).
OPTIONAL_PAGE_FILES: tuple[str, ...] = (
    "focus_areas", "heatmap_value_chain", "heatmap_category", "evidence",
)


def collect_surface_counters(b: dict) -> dict[str, Contribution]:
    files = b.get("_files") or {}
    loaded = sum(files.get(p) == "ok" for p in PAGE_FILES)
    fa = b.get("focus_areas") or {}
    fa_items = fa.get("items") if isinstance(fa, dict) else fa
    ev = b.get("evidence") or {}
    ev_items = ev.get("items") if isinstance(ev, dict) else ev
    return {
        "pages_loaded_10_clients": (1.0 if loaded == len(PAGE_FILES) else 0.0, None),
        "surface_focus_areas_clients": (1.0 if fa_items else 0.0, None),
        "surface_value_chain_clients": (
            1.0 if files.get("heatmap_value_chain") == "ok" else 0.0, None),
        "surface_heatmap_category_clients": (
            1.0 if files.get("heatmap_category") == "ok" else 0.0, None),
        "surface_evidence_clients": (1.0 if ev_items else 0.0, None),
    }


# ── dashboard (corpus-level, called once) ────────────────────────────────────
def collect_dashboard_counters(dashboard: dict, n_clients: int) -> dict[str, Contribution]:
    dash = (dashboard or {}).get("dashboard") or {}
    rc = dash.get("recent_completions")
    if isinstance(rc, list):
        distinct = {r.get("display_id") or r.get("entity_id") for r in rc if isinstance(r, dict)}
        rc_ok = len(distinct) == n_clients
    else:
        rc_ok = False
    return {
        "dashboard_recent_completions_match": (1.0 if rc_ok else 0.0, None),
        "dashboard_catalogue_version": (
            1.0 if _present(dash.get("catalogue_version")) else 0.0, None),
    }


def collect_client_counters(
        b: dict, *, entity_name: str = "",
        foreign_names: Iterable[str] = ()) -> dict[str, Contribution]:
    """Every per-client counter contribution for one bundle (pure)."""
    out: dict[str, Contribution] = {}
    out.update(collect_surface_counters(b))
    out.update(collect_parity_counters(b))
    out.update(collect_scqa_counters(b))
    out.update(collect_why_now_counters(b))
    out.update(collect_findings_counters(b))
    out.update(collect_insight_counters(b))
    out.update(collect_heatmap_counters(b))
    out.update(collect_focus_counters(b))
    out.update(collect_synthesis_counters(b))
    out.update(collect_platform_counters(b, entity_name))
    out.update(collect_context_counters(b))
    out.update(collect_techstack_counters(b))
    out.update(collect_firmographic_counters(b))
    out.update(collect_markdown_counters(b))
    out.update(collect_contamination_counters(b, entity_name, foreign_names))
    return out


def _cs(name: str, script: str, target: float, direction: str, unit: str,
        severity: str = "hard", baseline: str | None = None, desc: str = "") -> CounterSpec:
    return CounterSpec(name, script, target, direction, unit, severity, baseline, desc)


_FIRM_NULL_TARGETS = {  # Part 0.3 pins 4 fields; the rest hold the measured line
    # thought_leadership is Clay-only (2026-07-06): all-null is CORRECT
    # until Clay syncs — the card must never be derive-filled.
    "website": 8, "cagr": 26, "thought_leadership": 94, "leadership": 5,
    "revenue_usd": 44, "ticker": 66, "hq": 49, "trend": 46, "founded": 38,
    "branches": 34, "size_tier": 32, "geography": 20, "footprint": 20,
    "sentiment": 4, "aum_usd": 1,
}

COUNTERS: list[CounterSpec] = [
    # surfaces / loader (export_startup_pages)
    _cs("pages_loaded_10_clients", "export_startup_pages", ALL_CLIENTS, ">=", "clients",
        baseline="counters.pages_loaded_10_clients"),
    _cs("surface_focus_areas_clients", "export_startup_pages", ALL_CLIENTS, ">=", "clients",
        baseline="heatmap.focus_areas_in_pack"),
    _cs("surface_value_chain_clients", "export_startup_pages", ALL_CLIENTS, ">=", "clients",
        baseline="heatmap.value_chain_buckets"),
    _cs("surface_heatmap_category_clients", "export_startup_pages", ALL_CLIENTS, ">=",
        "clients", baseline="counters.surface_heatmap_category_clients"),
    _cs("surface_evidence_clients", "export_startup_pages", ALL_CLIENTS, ">=",
        "clients", baseline="counters.surface_evidence_clients"),
    # cross-file value parity (export_startup_data)
    _cs("score_parity_mismatch_clients", "export_startup_data", 0, "<=", "clients",
        baseline="pack_integrity.score_drift_clients"),
    # SCQA (deepen_narrative)
    _cs("scqa_template_clients", "deepen_narrative", 0, "<=", "clients",
        baseline="overview.scqa.template"),
    _cs("scqa_zero_eid_clients", "deepen_narrative", 0, "<=", "clients",
        baseline="overview.scqa.zero_eids"),
    _cs("scqa_len_gt4000_clients", "deepen_narrative", 0, "<=", "clients",
        baseline="counters.scqa_len_gt4000_clients"),
    _cs("scqa_paren_colon_clients", "deepen_narrative", 0, "<=", "clients",
        baseline="overview.scqa.broken_subcap_label"),
    _cs("scqa_f_marker_clients", "deepen_narrative", 0, "<=", "clients",
        baseline="overview.scqa.f_markers"),
    _cs("scqa_stub_clients", "deepen_narrative", 0, "<=", "clients",
        baseline="overview.scqa.pending_stub"),
    _cs("scqa_score_contradiction_clients", "deepen_narrative", 0, "<=", "clients",
        baseline="pack_integrity.scqa_score_contradiction_clients"),
    # why-now (deepen_narrative)
    _cs("why_now_ge3_clients", "deepen_narrative", ALL_CLIENTS, ">=", "clients",
        baseline="counters.why_now_ge3_clients"),
    _cs("why_now_fields14_pct", "deepen_narrative", 100, ">=", "pct",
        baseline="counters.why_now_fields14_pct"),
    _cs("why_now_evidence_pct", "deepen_narrative", 100, ">=", "pct",
        baseline="overview.why_now.evidence_populated_pct"),
    _cs("why_now_window_pct", "deepen_narrative", 80, ">=", "pct",
        baseline="overview.why_now.urgency_language_pct"),
    _cs("why_now_template_pct", "deepen_narrative", 0, "<=", "pct",
        baseline="overview.why_now.template_pct"),
    # top findings (startup_enrich)
    _cs("findings_wwsw_pct", "startup_enrich", 100, ">=", "pct",
        baseline="counters.findings_wwsw_pct"),
    _cs("findings_scored_pct", "startup_enrich", 100, ">=", "pct",
        baseline="counters.findings_scored_pct"),
    _cs("findings_evidence_pct", "startup_enrich", 95, ">=", "pct",
        baseline="overview.top_findings.evidence_pct"),
    _cs("findings_truncated_count", "startup_enrich", 0, "<=", "count",
        baseline="overview.top_findings.short_or_truncated"),
    # insight cards (derive_insights)
    _cs("insights_template_pct", "derive_insights", 10, "<=", "pct",
        baseline="insights.template_so_what_pct"),
    _cs("insights_zero_evidence_pct", "derive_insights", 5, "<=", "pct",
        baseline="insights.zero_evidence_pct"),
    _cs("insights_affects_avg", "derive_insights", 2, ">=", "avg",
        baseline="insights.affects_present"),
    _cs("insights_title_body_mismatch_cards", "derive_insights", 0, "<=", "count",
        baseline="counters.insights_title_body_mismatch_cards"),
    _cs("insights_report_sourced_pct", "derive_insights", 40, ">=", "pct", "soft",
        baseline="insights.report_sourced_pct",
        desc="report-presence is per-package (82/113) — soft until manifests land"),
    # heatmap (export_startup_pages / subcap_synthesis / broadcast_peer_medians)
    _cs("vc_buckets6_clients", "ccg_loader", ALL_CLIENTS, ">=", "clients",
        baseline="heatmap.value_chain_buckets"),
    _cs("heatmap_subcap_synthesis_clients", "derive_subcap_narratives", ALL_CLIENTS, ">=",
        "clients", baseline="heatmap.per_subcap_synthesis"),
    _cs("heatmap_peer_clients", "broadcast_peer_medians", ALL_CLIENTS, ">=", "clients",
        baseline="heatmap.cells_with_peer_median"),
    _cs("heatmap_peer_median_cells_pct", "broadcast_peer_medians", 50, ">=", "pct", "soft",
        baseline="heatmap.cells_with_peer_median"),
    _cs("heatmap_evidence_clients", "export_startup_pages", ALL_CLIENTS, ">=", "clients",
        baseline="heatmap.cells_with_enrichment_evidence"),
    _cs("heatmap_evidence_cells_pct", "export_startup_pages", 50, ">=", "pct", "soft",
        baseline="heatmap.cells_with_enrichment_evidence"),
    _cs("heatmap_band_pct", "export_startup_pages", 100, ">=", "pct",
        baseline="counters.heatmap_band_pct"),
    _cs("heatmap_cap_fields_pct", "export_startup_pages", 100, ">=", "pct",
        baseline="counters.heatmap_cap_fields_pct"),
    # stress-test probes (2026-07-02 — each caught a real defect in D3 runs)
    _cs("focus_title_hygiene", "focus_area_synthesizer", 0, "<=", "areas",
        baseline="counters.focus_title_hygiene",
        desc="titles that are bare F-N ids or <8 chars"),
    _cs("focus_grounding_eids", "focus_area_synthesizer", 0, "<=", "areas",
        baseline="counters.focus_grounding_eids",
        desc="[E- cited in quote but grounding.evidence_e_ids empty"),
    _cs("synthesis_none_leak", "derive_subcap_narratives", 0, "<=", "cells",
        baseline="counters.synthesis_none_leak",
        desc="per-subcap narrative containing ': None'"),
    _cs("synthesis_generic_name", "derive_subcap_narratives", 0, "<=", "cells",
        baseline="counters.synthesis_generic_name",
        desc="'capability dimension' / 'Subcap N (P' placeholder leak"),
    _cs("synthesis_evidence_substance", "derive_subcap_narratives", 0, "<=", "cells",
        baseline="counters.synthesis_evidence_substance",
        desc="evidence-bearing narrative w/o any fact beyond score numerics"),
    _cs("timeline_title_artifacts", "derive_context", 0, "<=", "events",
        baseline="counters.timeline_title_artifacts",
        desc="titles with trailing markup chars or list/markdown lead-ins"),
    # platforms (platform_fit / platform_story / startup_enrich)
    _cs("platform_fit_breakdown_pct", "recompute_platform_fit", 100, ">=", "pct",
        baseline="platform.fit_breakdown"),
    _cs("platform_state_ready_pct", "recompute_platform_fit", 95, "<=", "pct",
        baseline="counters.platform_state_ready_pct"),
    _cs("platform_red_fit80_cards", "recompute_platform_fit", 0, "<=", "cards",
        baseline="platform.red_but_fit80"),
    _cs("starters_p1c111_anchor_pct", "platform_story", 25, "<=", "pct",
        baseline="platform.starters_same_anchor_pct"),
    _cs("starters_entity_fact_pct", "platform_story", 100, ">=", "pct",
        baseline="counters.starters_entity_fact_pct"),
    _cs("opportunity_md_dominant_skeleton_pct", "startup_enrich", 30, "<=", "pct",
        baseline="platform.opportunity_md_one_skeleton_pct"),
    _cs("platform_cards_zero_evidence", "recompute_platform_fit", 0, "<=", "cards",
        baseline="platform.cards_zero_evidence"),
    _cs("platform_story_present_pct", "platform_story", 100, ">=", "pct",
        baseline="platform.story_present_pct",
        desc="story_md non-null on every card (dossier floor, never cache-cold)"),
    _cs("platform_story_facts_pct", "platform_story", 95, ">=", "pct",
        baseline="platform.story_facts_pct",
        desc="story_md carries ≥1 E-ID citation + ≥1 concrete fact"),
    _cs("roadmap_single_phase_clients", "derive_recommendations", 10, "<=", "clients", "soft",
        baseline="platform.roadmap_single_phase_clients",
        desc="multi-phase only where recs span bands — soft"),
    _cs("roadmap_rec_root_cause_pct", "derive_recommendations", 100, ">=", "pct",
        baseline="platform.recs_root_cause_eids"),
    _cs("roadmap_rec_outcomes_pct", "derive_recommendations", 100, ">=", "pct",
        baseline="platform.recs_outcomes"),
    _cs("roadmap_maturity_lift_null_pct", "derive_recommendations", 20, "<=", "pct",
        baseline="platform.maturity_lift_null_pct"),
    _cs("platform_zero_peer_hot_absent_cards", "recompute_platform_fit", 0, "<=", "cards",
        baseline="platform.zero_peer_hot_absent_cards",
        desc="absent term inflated past its graded cov=0 ceiling (3.6 pts)"),
    _cs("platform_out_of_vertical_hot_cards", "recompute_platform_fit", 0, "<=", "cards",
        baseline="platform.out_of_vertical_hot_cards",
        desc="fit≥60 card for a family outside the entity's subvertical"),
    _cs("platform_incumbent_greenfield_prose_cards", "platform_story", 0, "<=", "cards",
        baseline="platform.incumbent_greenfield_prose_cards",
        desc="integrate-lens card whose prose still argues the greenfield frame"),
    _cs("platform_hot_unbacked_cards", "recompute_platform_fit", 999, "<=", "cards", "soft",
        baseline="platform.hot_unbacked_cards",
        desc="report-only: fit≥60 cards the analyst report did not recommend"),
    # context (derive_context / facts_extractor / context_extras)
    _cs("context_defaulted_date_pct", "derive_context", 10, "<=", "pct",
        baseline="context.dates_defaulted_pct"),
    _cs("context_title_garbage_pct", "derive_context", 0, "<=", "pct",
        baseline="context.garbage_titles_pct"),
    _cs("context_negation_title_pct", "derive_context", 0, "<=", "pct",
        baseline="counters.context_negation_title_pct"),
    _cs("context_event_no_eid_pct", "derive_context", 10, "<=", "pct", "soft",
        baseline="context.no_eid_pct"),
    _cs("context_duplicate_events", "derive_context", 0, "<=", "events",
        baseline="context.duplicates"),
    _cs("acq_structured_pct", "derive_context", 95, ">=", "pct",
        baseline="counters.acq_structured_pct"),
    _cs("fin_prose_keys", "package_financials", 0, "<=", "count",
        baseline="context.financial_prose_keys"),
    _cs("fin_series_labeled_pct", "derive_financials", 100, ">=", "pct",
        baseline="counters.fin_series_labeled_pct"),
    _cs("sentiment_structured_pct", "derive_sentiment", 90, ">=", "pct",
        baseline="context.sentiment_structured"),
    _cs("context_license_jurisdiction_clients", "derive_context", 85, ">=", "clients",
        baseline="context.license_jurisdictions_present"),
    _cs("context_leadership_tenure_pct", "derive_leadership", 50, ">=", "pct", "soft",
        baseline="context.leadership_tenure_nonnull"),
    _cs("context_trend_md_missing_clients", "derive_context", 5, "<=", "clients", "soft",
        baseline="context.trend_md_missing"),
    # tech stack (package_techstack / clean_techstack)
    _cs("tech_disallowed_rows", "clean_techstack", 0, "<=", "rows",
        baseline="techstack.noise_rows"),
    _cs("tech_language_os_rows", "clean_techstack", 0, "<=", "rows", "soft",
        baseline="counters.tech_language_os_rows"),
    _cs("tech_noise_rows", "clean_techstack", 0, "<=", "rows", "soft",
        baseline="counters.tech_noise_rows"),
    _cs("tech_absent_row_clients", "clean_techstack", ALL_CLIENTS, ">=", "clients",
        baseline="techstack.absent_gap_rows"),
    _cs("tech_peer_coverage_clients", "clean_techstack", ALL_CLIENTS, ">=", "clients",
        baseline="techstack.peer_coverage_present"),
    _cs("tech_status_valid_pct", "clean_techstack", 100, ">=", "pct",
        baseline="counters.tech_status_valid_pct"),
    # dashboard (export_startup_data)
    _cs("dashboard_recent_completions_match", "export_startup_data", 1, ">=", "bool",
        baseline="counters.dashboard_recent_completions_match"),
    _cs("dashboard_catalogue_version", "export_startup_data", 1, ">=", "bool",
        baseline="counters.dashboard_catalogue_version"),
    # cross-entity contamination (dma_package / scrub_committed_snapshots)
    _cs("contamination_hits", "scrub_committed_snapshots", 0, "<=", "count",
        baseline="counters.contamination_hits"),
    # markdown lint (nlp.quality over every *_md)
    _cs("markdown_lint_flagged_fields", "deepen_narrative", 0, "<=", "count",
        baseline="counters.markdown_lint_flagged_fields"),
    # firmographics provenance
    _cs("firm_provenance_pct", "entity_healing", 100, ">=", "pct",
        baseline="counters.firm_provenance_pct"),
] + [
    _cs(f"firm_null_{f}", "entity_healing", _FIRM_NULL_TARGETS[f], "<=", "clients",
        baseline=f"overview.firmographics_null.{f}")
    for f in FIRM_FIELDS
] + [
    # DEPLOY-COVERAGE FLOOR (operator safeguard 2026-07-06): fails the deploy
    # when too many clients ship an enrichable-empty firmographics field beyond
    # the honest-null floor. Owned by enrich_empty_surfaces (the deploy-time
    # Gemini fill). baseline maps to the recorded null line so the pre-regen
    # --baseline tracker suppresses (honest-null-credited value <= raw null),
    # while the post-regen no-baseline deploy gate enforces the floor outright.
    _cs(f"firm_empty_{f}", "enrich_empty_surfaces", _FIRM_COVERAGE_FLOOR[f][0],
        "<=", "clients", _FIRM_COVERAGE_FLOOR[f][1],
        baseline=f"overview.firmographics_null.{f}",
        desc=f"deploy floor: ≤{_FIRM_COVERAGE_FLOOR[f][0]} clients may ship "
             f"enrichable-empty {f} — {_FIRM_COVERAGE_FLOOR[f][2]}")
    for f in _FIRM_COVERAGE_FLOOR
]

COUNTER_INDEX: dict[str, CounterSpec] = {c.name: c for c in COUNTERS}
