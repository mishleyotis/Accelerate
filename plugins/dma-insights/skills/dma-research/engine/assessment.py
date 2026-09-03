#!/usr/bin/env python3
"""The SCORING stage — column D and the gold-standard tabs, through refusals,
into the one workbook, with a gate that says when scoring is DONE.

    python3 -m engine.assessment open      --run R            # flip to the assessment stage
    python3 -m engine.assessment score     --run R --subcap P1C1.1.1 --score 2.5 \\
            --confidence MEDIUM --rationale "…>=150 chars citing [E-012]…" \\
            --evidence-ceiling 4.0 --caps "none applied" \\
            --ai-applicability ASSISTIVE --data-dependency "member master, transactions" \\
            --data-readiness AMBER --ai-evidence NONE_FOUND --ai-blocker "no governed data catalogue" \\
            --peer-ai-signal UNVERIFIED --actor scoring-p1-producer
    python3 -m engine.assessment critique  --run R --pillar P1 --verdict PASS \\
            --actor scoring-critic --note "…>=80 chars…"
    python3 -m engine.assessment rollup    --run R --headline "<one line an executive reads first>"
    python3 -m engine.assessment solution  --run R --id REC-01 --name … --platform … --categories P4C1,P4C3
    python3 -m engine.assessment peer-adoption --run R --product … --peer … --verdict Y|N|UNKNOWN --basis … --source …
    python3 -m engine.assessment gate      --run R            # the SCORING gate: PASS or the list
    python3 -m engine.assessment state     --run R

WHY THIS EXISTS (owner, 2026-09-03, issues 2, 3, 5 and 6). "Report writing
starts without scoring happening." "The workbook always defaults to the wrong
structure … missing fields." "The reports and scoring workbook should … be a
clear workflow with clear gating requirements."

The engine researched into the workbook and stopped. Scoring belonged to the
dma-assessment SKILL, whose Phase 4 builds a SEPARATE 11-sheet workbook from a
JSON scratchpad — so a package either shipped the research workbook hand-scored
in place (goeasy: 380 blank scores, 656 blank names, no dashboard, no rollup,
no coverage disclosure) or shipped two half-workbooks neither of which the app
could serve alone (Bank of Travelers Rest: 20 + 23 tabs, eighteen of nineteen
runs with zero scored cells). And nothing anywhere said "scoring is finished",
so the report producers started on whatever column D held.

So the scoring stage is ENGINE commands over the same substrate:

  open       PRELIM closed + every category gated with synthesis (the same
             rule the handoff enforces) -> the stage flips, and the config
             tabs the report reads are written from the contract: the
             sub-vertical weight set, the M1..M5 rubric, the cap rules, the
             catalogue metadata, the capability definitions.
  score      one subcap: D E H I J on its pillar row, its Subcap_Scores row
             (with the six AI-and-data overlay columns the report's §5
             renders from), its Caps_Applied_Log row, and a Provenance row
             naming the scorer. REFUSED when: the row was never synthesised
             and never had its absence declared; its synthesis was not
             independently challenged (a score must reflect a CHALLENGED
             claim, not raw evidence); the score is off the 1-5 quarter-point
             scale or above the evidence ceiling the tiers allow; the
             rationale is under 150 characters, cites nothing the row carries,
             or is boilerplate; HIGH confidence rests on one source identity;
             an overlay column is blank or off-vocabulary.
  critique   the adversarial critic pass, per pillar, by an actor that scored
             none of that pillar's rows. Recorded as a SCORING_CRITIC gate row.
  rollup     the two stated grains (Pillar_Summary / Category_Detail, the
             app's names) and their gold twins (Pillar_Rollup / Category_Rollup,
             the report's names), Coverage_Map (Scored / Unknown / pct — the
             disclosure, GS-WB-COVERAGE) and the Executive_Summary dashboard.
             Means, weighted by the pinned pillar weights; stated ONCE here,
             which is what "stated grain" means.
  gate       every selected subcap scored and named; every scored evidenced
             row challenge-PASS; every rationale over its floor and cited; no
             score above its ceiling; every row in Subcap_Scores and
             Caps_Applied_Log; overlay complete; a critic verdict per pillar;
             rollups present and reconciling within 0.01; weights summing to
             1.00; no capability with every subcap at one identical score.
             Writes 07_qa/scoring.json and a Gate_Log SCORING row —
             `engine.narrative write --report assessment` reads that row and
             refuses to write a word of the assessment report until it says
             PASS.

Scores are struck by the scoring agents (one per pillar), never by this
module: it refuses what does not hold, and states what does.
"""
from __future__ import annotations

if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

from . import contract as C
from . import rubric
from . import ledger as L
from . import quality as Q
from . import runstate
from .workbook import RunWorkbook, _split_ids


class ScoringRefusal(ValueError):
    """A score refused before it landed, with the reason."""


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


CONFIDENCES = ("HIGH", "MEDIUM", "LOW")
RATIONALE_MIN = 150
#: The ceiling a row's best evidence tier allows (dma-assessment § Evidence
#: Tier System: Max Alone). No evidence at all cannot exceed M2.
TIER_CEILING = {"T1": 5.0, "T2": 5.0, "T3": 4.0, "T4": 2.5, "T5": 2.0}
NO_EVIDENCE_CEILING = 2.0
GENERIC_RATIONALE = re.compile(
    r"category-based scoring|based on public evidence analysis|"
    r"demonstrates capability|the institution should improve", re.I)


# ── stage ────────────────────────────────────────────────────────────────

def research_ready(wb: RunWorkbook, qa_dir: Path | None) -> list[str]:
    """What must hold before a single score is struck."""
    from . import floors_gate, handoff, prelim
    out = []
    try:
        prelim.require_complete(wb)
    except prelim.PrelimRefusal as e:
        out.append(f"PRELIM is open: {str(e)[:200]}")
    cats = sorted({c.split(".")[0] for c in wb.selected_subcaps()})
    gates = {}
    for cat in cats:
        v = floors_gate.read_verdict(qa_dir, cat) if qa_dir else None
        gates[cat] = ({"verdict": "NOT_RUN"} if v is None else
                      {"verdict": v.get("gate"), "blocking": v.get("blocking"),
                       "require_synthesis": bool(v.get("require_synthesis"))})
    try:
        handoff._assert_scoreable(gates)
    except SystemExit as e:
        out.append(str(e))
    unnamed = [str(r.get("SubCap_ID")) for r in wb.scoring_rows()
               if not _clean(r.get("SubCap_Name"))]
    if unnamed:
        out.append(f"{len(unnamed)} row(s) carry no SubCap_Name "
                   f"({unnamed[:5]}…): re-seed the names from the catalogue")
    return out


def open_stage(wb: RunWorkbook, qa_dir: Path | None, *, force: bool = False) -> dict:
    """Flip the workbook to the ASSESSMENT stage and write the config tabs."""
    pre = research_ready(wb, qa_dir)
    if pre and not force:
        raise ScoringRefusal(
            "the research is not ready to be scored — "
            + "\n  - ".join([""] + pre))
    md = wb.metadata()
    sv = str(md.get("sub_vertical") or "").strip()
    weights = C.PILLAR_WEIGHTS.get(sv, C.DEFAULT_PILLAR_WEIGHTS)
    set_id = f"{sv or 'DEFAULT'}_v1"
    tax = C.taxonomy()
    with wb.transaction("assessment.open"):
        for sheet in ("Pillar_Weights", "Maturity_Rubric", "Cap_Triggers",
                      "Catalogue_Meta", "Capability_Definitions"):
            ws = wb._sheet(sheet)
            if ws.max_row > 1:
                ws.delete_rows(2, ws.max_row)
        for pid in ("P1", "P2", "P3", "P4"):
            wb.append("Pillar_Weights", {
                "weight_set_id": set_id, "pillar_id": pid,
                "pillar_name": C.PILLAR_NAMES[pid],
                "weight": round(weights[pid] / 100, 2)}, save=False)
        wb.append("Pillar_Weights", {"weight_set_id": set_id, "pillar_id": "TOTAL",
                                     "pillar_name": "All pillars",
                                     "weight": round(sum(weights.values()) / 100, 2)},
                  save=False)
        for r in rubric.RUBRIC:
            wb.append("Maturity_Rubric", dict(zip(C.MATURITY_RUBRIC_COLUMNS, r)),
                      save=False)
        for r in C.CAP_TRIGGERS:
            wb.append("Cap_Triggers", dict(zip(C.CAP_TRIGGERS_COLUMNS, r)), save=False)
        for k, v in (
            ("catalogue_version", md.get("catalogue_version")),
            ("catalogue_hash", md.get("catalogue_hash")),
            ("catalogue_hash_short", str(md.get("catalogue_hash"))[:8]),
            ("pillar_count", tax.n_pillars), ("category_count", tax.n_categories),
            ("capability_count", tax.n_capabilities), ("subcap_count", tax.n_cells),
            ("subvertical_id", sv), ("evidence_mode", md.get("evidence_mode")),
            ("scope_mode", md.get("scope_mode")),
            ("served_cell_count", len(wb.selected_subcaps())),
            ("scored_cell_count", len(wb.selected_subcaps())),
            ("weight_set_id", set_id), ("tier_scheme_id", "T1-T5"),
            ("tier_count", 5), ("resolution_source", "WORKBOOK_META"),
            ("resolved_at", _utcnow()),
        ):
            wb.append("Catalogue_Meta", {"key": k, "value": v}, save=False)
        names = _category_names()
        for cat in tax.categories:
            wb.append("Capability_Definitions", {
                "category_id": cat, "category_name": names.get(cat, cat),
                "pillar": cat.split("C")[0],
                "assessed_through": (f"Subcapability scores for {names.get(cat, cat)} "
                                     f"against the M1-M5 rubric; "
                                     f"{len(tax.cells_in(cat))} catalogue cells")},
                      save=False)
        wb.set_metadata("stage", "assessment", save=False)
        wb.save()
    L.append_gate(wb, gate="SCORING_OPENED", scope="run", verdict="PASS",
                  detail=(f"weight set {set_id}; research gates held"
                          + (" (FORCED past: " + "; ".join(pre)[:200] + ")" if pre else "")),
                  blocking=False)
    return {"stage": "assessment", "weight_set": set_id, "weights": weights,
            "forced_past": pre}


def _category_names() -> dict[str, str]:
    """Category display names from the assessment skill's own criteria doc,
    the same table the research agent generator binds to."""
    p = Path(__file__).resolve().parents[2] / "dma-assessment" / "references" / \
        "capability_criteria.md"
    if not p.is_file():
        return {}
    return dict(re.findall(r"^### (P\dC\d): (.+?)\s*$", p.read_text(), re.M))


def require_stage(wb: RunWorkbook) -> None:
    if C.stage_of(wb.metadata()) != "assessment":
        raise ScoringRefusal(
            "the workbook is at the research stage. `engine.assessment open` "
            "first — it checks that every category is gated with synthesis "
            "and PRELIM is closed, then writes the weight set, rubric and "
            "cap rules the scores are struck against.")


# ── one score ────────────────────────────────────────────────────────────

def ceiling_for(wb: RunWorkbook, row: dict) -> tuple[float, str]:
    """The evidence ceiling the row's tiers allow, and why."""
    register = wb.evidence_index()
    eids = [i.split(":")[0] for i in _split_ids(row.get("Evidence_IDs"))
            if i and i != C.NO_EVIDENCE]
    tiers = [str(register[e].get("Tier") or "") for e in eids if e in register]
    if not tiers:
        return NO_EVIDENCE_CEILING, "no evidence: capped at M2 (CAP-T5 shape)"
    best = min(tiers, key=lambda t: C.TIERS.index(t) if t in C.TIERS else 99)
    ceil = TIER_CEILING.get(best, NO_EVIDENCE_CEILING)
    idents = set()
    for e in eids:
        r = register.get(e) or {}
        url = str(r.get("Source_URL") or "")
        idents.add(url.split("//")[-1].split("/")[0].lower()
                   or str(r.get("Source_Name") or "").lower())
    idents.discard("")
    why = f"best tier {best} allows {ceil}"
    if len(idents) < 2 and ceil > 3.0:
        ceil, why = 3.0, why + "; single source caps at M3 (CAP-SS)"
    return ceil, why


def score(wb: RunWorkbook, subcap: str, *, score, confidence: str, rationale: str,
          actor: str, evidence_ceiling=None, caps: str = "",
          ai_applicability: str, data_dependency: str, data_readiness: str,
          ai_evidence: str = "NONE_FOUND", ai_blocker: str = "NONE",
          peer_ai_signal: str = "UNVERIFIED") -> dict:
    require_stage(wb)
    row = wb.scoring_row(subcap)
    if row is None:
        raise ScoringRefusal(f"{subcap} is not in this run's engagement set")
    problems: list[str] = []
    if not _clean(actor):
        raise ScoringRefusal("a score records who struck it (--actor)")

    synthesised = bool(_clean(row.get("Dominant_Claim")))
    eids = [i.split(":")[0] for i in _split_ids(row.get("Evidence_IDs"))
            if i and i != C.NO_EVIDENCE]
    declared = _clean(row.get("Absence_Claimed")).upper() in ("YES", "TRUE", "1")
    if eids and not synthesised:
        problems.append("the row holds evidence and no synthesis (volleyed): a "
                        "score on raw evidence is the defect the research → "
                        "synthesis → challenge → score order exists to stop")
    if not eids and not declared:
        problems.append("the row holds no evidence and its absence was never "
                        "declared (`engine.cli absence …` with the volley ladder); "
                        "an unresearched cell cannot be scored, only a searched one")
    if eids and _clean(row.get("Challenge_Verdict")).upper() != "PASS":
        problems.append(f"Challenge_Verdict is {_clean(row.get('Challenge_Verdict')) or 'empty'}: "
                        f"a score reflects a claim that SURVIVED an independent "
                        f"challenge, never one that failed or was never challenged")

    sc = _num(score)
    if sc is None or not (1.0 <= sc <= 5.0):
        problems.append(f"score {score!r} is not on the 1.0-5.0 scale")
    elif abs(sc * 4 - round(sc * 4)) > 1e-9:
        problems.append(f"score {sc} is not a quarter-point (x.00 / x.25 / x.50 / x.75)")
    ceil, why = ceiling_for(wb, row)
    ec = _num(evidence_ceiling)
    if ec is None:
        ec = ceil
    elif ec > ceil + 1e-9:
        problems.append(f"--evidence-ceiling {ec} exceeds what the row's evidence "
                        f"allows ({ceil}: {why})")
    if sc is not None and sc > ec + 1e-9:
        problems.append(f"score {sc} is above the evidence ceiling {ec} ({why}); "
                        f"the ceiling is the score's cap, not a note beside it")

    conf = _clean(confidence).upper()
    if conf not in CONFIDENCES:
        problems.append(f"confidence {confidence!r} not in {CONFIDENCES}")
    if not eids and conf != "LOW":
        problems.append("a row with no evidence carries LOW confidence and nothing else")
    if conf == "HIGH":
        register = wb.evidence_index()
        idents = {(str((register.get(e) or {}).get("Source_URL") or "")
                   .split("//")[-1].split("/")[0].lower()) for e in eids}
        idents.discard("")
        if len(idents) < 2:
            problems.append("HIGH confidence requires two source identities; "
                            "single-source caps at MEDIUM")

    rat = _clean(rationale)
    if len(rat) < RATIONALE_MIN:
        problems.append(f"rationale is {len(rat)} chars; {RATIONALE_MIN} is the floor "
                        f"— evidence, maturity match, gap to next level, counter, "
                        f"ceiling, so-what")
    cited = set(re.findall(r"\bE-\d+", rat))
    if eids and not (cited & set(eids)):
        problems.append(f"the rationale cites none of the row's own evidence "
                        f"({', '.join(eids[:4])}); a rationale that cites nothing "
                        f"the row carries is prose about a different row")
    if not eids and not re.search(r"(?i)no evidence|absence|searched|ladder|proxy", rat):
        problems.append("a no-evidence rationale states the searches and the "
                        "ladder that established the absence")
    if GENERIC_RATIONALE.search(rat) or Q.is_boilerplate(rat):
        problems.append("the rationale is generic — it could appear unchanged for "
                        "a different institution")

    aa = _clean(ai_applicability).upper()
    if aa not in C.AI_APPLICABILITY:
        problems.append(f"ai_applicability {ai_applicability!r} not in {C.AI_APPLICABILITY}")
    dr = _clean(data_readiness).upper()
    if dr not in C.DATA_READINESS:
        problems.append(f"data_readiness {data_readiness!r} not in {C.DATA_READINESS}")
    if not _clean(data_dependency):
        problems.append("data_dependency is blank — name the data domains the "
                        "subcapability consumes, or NONE")
    aie = _clean(ai_evidence) or "NONE_FOUND"
    if aie.upper() != "NONE_FOUND":
        register = wb.evidence_index()
        dead = [e for e in _split_ids(aie) if e.split(":")[0] not in register]
        if dead:
            problems.append(f"ai_evidence_ids {dead} do not resolve")
    pas = _clean(peer_ai_signal) or "UNVERIFIED"
    if not (pas.upper() in ("SCAN", "UNVERIFIED") or re.fullmatch(r"E-\d+", pas)):
        problems.append("peer_ai_signal is an E-ID, SCAN or UNVERIFIED")
    if problems:
        raise ScoringRefusal(f"{subcap}: score refused — " + "; ".join(problems))

    caps_txt = _clean(caps) or ("no evidence: capped at 2.0" if not eids else "none applied")
    with wb.transaction("assessment.score"):
        wb.set_scoring(subcap, {"Score": sc, "Confidence": conf,
                                "Evidence_Ceiling": ec, "Caps_Applied": caps_txt,
                                "Rationale": rat}, save=False)
        srow = {"subcap_id": subcap, "subcap_name": row.get("SubCap_Name"),
                "category": row.get("Category"),
                "source_cell": f"{subcap[:2]}_Subcap_Scoring!{subcap}",
                "score": sc, "confidence": conf,
                "evidence_ids": ", ".join(eids) or C.NO_EVIDENCE,
                "source_urls": row.get("Source_URLs"), "evidence_ceiling": ec,
                "caps_applied": caps_txt, "rationale": rat,
                "ai_applicability": aa, "data_dependency": _clean(data_dependency),
                "data_readiness": dr, "ai_evidence_ids": aie,
                "ai_blocker": _clean(ai_blocker) or "NONE", "peer_ai_signal": pas}
        if any(_clean(r.get("subcap_id")) == subcap for r in wb.rows("Subcap_Scores")):
            wb.update_row("Subcap_Scores", "subcap_id", subcap, srow, save=False)
        else:
            wb.append("Subcap_Scores", srow, save=False)
        crow = {"subcap_id": subcap, "category": row.get("Category"),
                "final_score": sc, "evidence_ceiling": ec, "caps_applied": caps_txt}
        if any(_clean(r.get("subcap_id")) == subcap for r in wb.rows("Caps_Applied_Log")):
            wb.update_row("Caps_Applied_Log", "subcap_id", subcap, crow, save=False)
        else:
            wb.append("Caps_Applied_Log", crow, save=False)
        wb.save()
    L.record_provenance(wb, subcap, "score", actor, f"{sc} {conf} ceiling {ec}")
    return {"subcap": subcap, "score": sc, "confidence": conf,
            "evidence_ceiling": ec, "caps_applied": caps_txt, "level": rubric.maturity_level(sc)}


# ── the critic ───────────────────────────────────────────────────────────

def critique(wb: RunWorkbook, *, pillar: str, verdict: str, actor: str,
             note: str) -> dict:
    """The adversarial critic pass on one pillar's scores, by somebody else."""
    require_stage(wb)
    pillar = _clean(pillar).upper()
    if pillar not in ("P1", "P2", "P3", "P4"):
        raise ScoringRefusal(f"pillar {pillar!r} must be P1..P4")
    if _clean(verdict).upper() not in ("PASS", "FAIL"):
        raise ScoringRefusal("verdict is PASS or FAIL")
    if len(_clean(note)) < 80:
        raise ScoringRefusal("a critic note under 80 characters is a rubber stamp — "
                             "say which scores you re-derived, which differentiation "
                             "check you ran, and what you would move")
    scorers = {_clean(r.get("Actor")).lower() for r in wb.rows("Provenance")
               if _clean(r.get("Step")) == "score"
               and str(r.get("SubCap_ID") or "").startswith(pillar)}
    if _clean(actor).lower() in scorers:
        raise ScoringRefusal(f"{actor} struck scores on {pillar} and cannot be its "
                             f"critic; the critic is independent by record")
    scored = [r for r in wb.rows(f"{pillar}_Subcap_Scoring") if _num(r.get("Score")) is not None]
    if not scored:
        raise ScoringRefusal(f"{pillar} carries no scores yet; there is nothing to criticise")
    L.append_gate(wb, gate="SCORING_CRITIC", scope=pillar, verdict=_clean(verdict).upper(),
                  detail=f"{actor}: {_clean(note)[:400]}", blocking=True)
    return {"pillar": pillar, "verdict": _clean(verdict).upper(), "critic": actor,
            "scored_rows": len(scored)}


# ── rollup ───────────────────────────────────────────────────────────────

def _weights(wb: RunWorkbook) -> dict[str, float]:
    out = {}
    for r in wb.rows("Pillar_Weights"):
        pid = _clean(r.get("pillar_id"))
        if pid in ("P1", "P2", "P3", "P4"):
            out[pid] = float(r.get("weight") or 0)
    if not out:
        sv = str(wb.metadata().get("sub_vertical") or "")
        out = {k: v / 100 for k, v in C.PILLAR_WEIGHTS.get(sv, C.DEFAULT_PILLAR_WEIGHTS).items()}
    return out


def _peer_medians(wb: RunWorkbook) -> dict[str, float]:
    out = {}
    for r in wb.rows("Peer_Benchmarks"):
        cat = _clean(r.get("Category_ID"))
        med = _num(r.get("Peer_Median"))
        if cat and med is not None:
            out[cat] = med
    return out


def compute(wb: RunWorkbook) -> dict:
    """Category and pillar means from column D; the overall weighted by the
    pinned weights. Simple means within a pillar, deliberately: this engine
    applies no analyst override of its own, and a weighting invented here
    would be a number with no authority behind it."""
    cats: dict[str, list[float]] = {}
    evid: dict[str, list[bool]] = {}
    for r in wb.scoring_rows():
        cid = _clean(r.get("Category"))
        sc = _num(r.get("Score"))
        if not cid:
            continue
        eids = [i for i in _split_ids(r.get("Evidence_IDs")) if i and i != C.NO_EVIDENCE]
        evid.setdefault(cid, []).append(bool(eids))
        if sc is not None:
            cats.setdefault(cid, []).append(sc)
    weights = _weights(wb)
    peers = _peer_medians(wb)
    names = _category_names()

    def mean(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    categories = []
    for cid in sorted(evid):
        scores = cats.get(cid, [])
        n = len(evid[cid]); ev = sum(evid[cid])
        m = mean(scores)
        med = peers.get(cid)
        categories.append({
            "category_id": cid, "category_name": names.get(cid, cid),
            "pillar_id": cid.split("C")[0], "score": m,
            "peer_median": med,
            "gap": round(m - med, 2) if (m is not None and med is not None) else None,
            "level": rubric.maturity_level(m), "coverage": f"{ev}/{n}",
            "subcaps": n, "evidenced": ev, "scored": len(scores),
        })
    pillars = []
    overall_num = overall_den = 0.0
    for pid in ("P1", "P2", "P3", "P4"):
        mine = [c for c in categories if c["pillar_id"] == pid]
        scores = [s for c in mine for s in cats.get(c["category_id"], [])]
        m = mean(scores)
        meds = [c["peer_median"] for c in mine if c["peer_median"] is not None]
        med = round(sum(meds) / len(meds), 2) if meds else None
        w = weights.get(pid, 0.0)
        if m is not None:
            overall_num += m * w; overall_den += w
        pillars.append({"pillar_id": pid, "pillar_name": C.PILLAR_NAMES[pid],
                        "score": m, "weight": w,
                        "weighted_contribution": round(m * w, 4) if m is not None else None,
                        "peer_median": med,
                        "gap": round(m - med, 2) if (m is not None and med is not None) else None,
                        "level": rubric.maturity_level(m), "subcaps_scored": len(scores)})
    overall = round(overall_num / overall_den, 2) if overall_den else None
    pmeds = [p["peer_median"] for p in pillars if p["peer_median"] is not None]
    peer_overall = round(sum(pmeds) / len(pmeds), 2) if pmeds else None
    return {"categories": categories, "pillars": pillars, "overall": overall,
            "peer_overall": peer_overall,
            "gap_overall": (round(overall - peer_overall, 2)
                            if overall is not None and peer_overall is not None else None),
            "weights": weights,
            "subcaps": sum(c["subcaps"] for c in categories),
            "scored": sum(c["scored"] for c in categories),
            "evidenced": sum(c["evidenced"] for c in categories)}


def _replace(wb: RunWorkbook, sheet: str, rows: list[dict]) -> int:
    ws = wb._sheet(sheet)
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row)
    for row in rows:
        wb.append(sheet, row, save=False)
    return len(rows)


def rollup(wb: RunWorkbook, *, headline: str | None = None) -> dict:
    require_stage(wb)
    got = compute(wb)
    if not got["scored"]:
        raise ScoringRefusal("no subcapability carries a score; there is no grain to state")
    md = wb.metadata()
    prior = {_clean(r.get("Field")): r.get("Value") for r in wb.rows("Executive_Summary")}
    head = _clean(headline) or _clean(prior.get("Headline"))
    if len(head) < 40:
        raise ScoringRefusal("--headline: the one line an executive reads first "
                             "(>=40 chars, institution-specific), e.g. 'Modern rails, "
                             "unbuilt member-relationship layer: sits ~1 band below "
                             "digital-leader peers'")
    unknown = got["subcaps"] - got["evidenced"]
    def pct(a, b):
        return round(100 * a / b, 1) if b else None
    with wb.transaction("assessment.rollup"):
        _replace(wb, "Pillar_Rollup", [{k: p.get(k) for k in C.PILLAR_ROLLUP_COLUMNS}
                                      for p in got["pillars"]]
                 + [{"pillar_id": "OVERALL", "pillar_name": md.get("entity_name"),
                     "score": got["overall"], "weight": round(sum(got["weights"].values()), 2),
                     "weighted_contribution": got["overall"],
                     "peer_median": got["peer_overall"], "gap": got["gap_overall"],
                     "level": rubric.maturity_level(got["overall"])}])
        _replace(wb, "Category_Rollup", [{k: c.get(k) for k in C.CATEGORY_ROLLUP_COLUMNS}
                                        for c in got["categories"]])
        _replace(wb, "Pillar_Summary",
                 [{"Pillar": p["pillar_id"], "Pillar_Name": p["pillar_name"],
                   "Score": p["score"], "Weight_Pct": round(p["weight"] * 100),
                   "Peer_Median": p["peer_median"], "Gap_to_Peer": p["gap"],
                   "Maturity": p["level"]} for p in got["pillars"]]
                 + [{"Pillar": "OVERALL", "Pillar_Name": md.get("entity_name"),
                     "Score": got["overall"], "Weight_Pct": 100,
                     "Peer_Median": got["peer_overall"], "Gap_to_Peer": got["gap_overall"],
                     "Maturity": rubric.maturity_level(got["overall"])}])
        _replace(wb, "Category_Detail",
                 [{"Category_ID": c["category_id"], "Category_Name": c["category_name"],
                   "Pillar": c["pillar_id"], "Score": c["score"],
                   "Peer_Median": c["peer_median"],
                   "Priority_Score": (round(-c["gap"], 2) if c["gap"] is not None else None),
                   "Priority_Tier": (("HIGH" if c["gap"] <= -0.8 else
                                      "MED" if c["gap"] <= -0.4 else "LOW")
                                     if c["gap"] is not None else ""),
                   "Gap_to_Peer": c["gap"], "Maturity": c["level"],
                   "Coverage": c["coverage"]} for c in got["categories"]])
        _replace(wb, "Coverage_Map",
                 [{"category_id": c["category_id"], "category_name": c["category_name"],
                   "subcaps": c["subcaps"], "evidenced": c["evidenced"],
                   "evidence_gap": c["subcaps"] - c["evidenced"],
                   "coverage_pct": pct(c["evidenced"], c["subcaps"]),
                   "confidence_posture": ("STRONG" if (pct(c["evidenced"], c["subcaps"]) or 0) >= 80
                                          else "MODERATE" if (pct(c["evidenced"], c["subcaps"]) or 0) >= 60
                                          else "THIN")} for c in got["categories"]])
        peer_names = str(wb.handoff_lock().get("locked_peer_set") or "").replace("|", ", ")
        fields = [
            ("Institution", md.get("entity_name")),
            ("Sub-Vertical", md.get("sub_vertical")),
            ("Evidence Mode", md.get("evidence_mode")),
            ("Overall Maturity", f"{got['overall']} ({rubric.maturity_level(got['overall'])})"),
            ("Peer Median (est.)", (f"{got['peer_overall']} — locked peer set: {peer_names}"
                                    if got["peer_overall"] is not None else
                                    "not established: Peer_Benchmarks carries no median")),
            ("Gap to Peer", got["gap_overall"] if got["gap_overall"] is not None
             else "not established: no peer median"),
            ("Subcaps Scored", f"{got['evidenced']} evidenced of {got['subcaps']} "
                               f"({pct(got['evidenced'], got['subcaps'])}% coverage); "
                               f"{got['scored']} scored"),
            ("Evidence Gaps (Unknown)", unknown),
        ]
        for p in got["pillars"]:
            fields.append((f"{p['pillar_id']} {p['pillar_name']}",
                           f"{p['score']} ({p['level']})" if p["score"] is not None
                           else "not in scope"))
        fields.append(("Headline", head))
        _replace(wb, "Executive_Summary", [{"Field": f, "Value": v} for f, v in fields])
        wb.save()
    return {"overall": got["overall"], "peer_overall": got["peer_overall"],
            "gap": got["gap_overall"], "scored": got["scored"], "subcaps": got["subcaps"],
            "evidenced": got["evidenced"], "unknown": unknown,
            "pillars": [(p["pillar_id"], p["score"], p["level"]) for p in got["pillars"]]}


# ── catalogue tabs ───────────────────────────────────────────────────────

def solution(wb: RunWorkbook, *, sol_id: str, name: str, platform: str,
             categories, rec_id: str = "") -> dict:
    require_stage(wb)
    sol_id = _clean(sol_id).upper()
    if not re.fullmatch(r"(REC|SOL)-\d{2}", sol_id):
        raise ScoringRefusal("solution id is REC-NN or SOL-NN")
    if len(_clean(name)) < 12:
        raise ScoringRefusal("a solution carries a name a reader can act on (>=12 chars)")
    cats = [c for c in (list(categories) if isinstance(categories, (list, tuple, set))
                        else _split_ids(categories)) if c]
    tax = C.taxonomy()
    bad = [c for c in cats if c not in tax.categories]
    if bad:
        raise ScoringRefusal(f"categories {bad} are not catalogue categories")
    row = {"solution_id": sol_id, "solution_name": _clean(name),
           "platform": _clean(platform), "categories": ", ".join(cats),
           "rec_id": _clean(rec_id).upper() or sol_id}
    if any(_clean(r.get("solution_id")).upper() == sol_id for r in wb.rows("Solution_Catalogue")):
        wb.update_row("Solution_Catalogue", "solution_id", sol_id, row)
    else:
        wb.append("Solution_Catalogue", row)
    return {"solution": sol_id, "rows": len(wb.rows("Solution_Catalogue"))}


def peer_adoption(wb: RunWorkbook, *, product: str, peer: str, verdict: str,
                  basis: str, source: str, as_of: str = "") -> dict:
    require_stage(wb)
    v = _clean(verdict).upper()
    if v not in ("Y", "N", "UNKNOWN"):
        raise ScoringRefusal("verdict is Y, N or UNKNOWN")
    if v != "UNKNOWN" and (len(_clean(basis)) < 20 or not _clean(source)):
        raise ScoringRefusal("a Y/N deployment verdict carries a basis (>=20 chars) "
                             "and a source; a technographic claim about a named "
                             "institution carries a research finding's burden")
    if v == "UNKNOWN" and len(_clean(basis)) < 20:
        raise ScoringRefusal("UNKNOWN carries what was searched and came back empty")
    wb.append("Platform_Peer_Adoption", {
        "Product / Layer": _clean(product), "Peer": _clean(peer), "Verdict": v,
        "Basis": _clean(basis), "Source": _clean(source) or "not established",
        "As at": _clean(as_of) or _utcnow()[:10]})
    return {"rows": len(wb.rows("Platform_Peer_Adoption"))}


# ── the gate ─────────────────────────────────────────────────────────────

def gate(wb: RunWorkbook, qa_dir: Path | None = None) -> dict:
    """Is scoring DONE? Every term measured, the verdict recorded twice."""
    md = wb.metadata()
    f: dict[str, list] = {k: [] for k in (
        "unscored", "unnamed", "rationale_short", "rationale_uncited",
        "score_above_ceiling", "score_off_scale", "unchallenged_scored",
        "unresearched_scored", "confidence_invalid", "caps_log_missing",
        "subcap_scores_missing", "overlay_incomplete", "critic_missing",
        "critic_failed", "rollup_missing", "rollup_drift", "weights_sum",
        "dashboard_incomplete", "no_differentiation", "low_differentiation",
        "stage_not_assessment")}
    if C.stage_of(md) != "assessment":
        f["stage_not_assessment"].append(C.stage_of(md))
    register = wb.evidence_index()
    ss = {_clean(r.get("subcap_id")): r for r in wb.rows("Subcap_Scores")}
    cl = {_clean(r.get("subcap_id")) for r in wb.rows("Caps_Applied_Log")}
    by_cap: dict[str, list[float]] = {}
    for r in wb.scoring_rows():
        cell = _clean(r.get("SubCap_ID"))
        if not cell:
            continue
        if not _clean(r.get("SubCap_Name")):
            f["unnamed"].append(cell)
        sc = _num(r.get("Score"))
        if sc is None:
            f["unscored"].append(cell)
            continue
        if not (1.0 <= sc <= 5.0):
            f["score_off_scale"].append(cell)
        by_cap.setdefault(cell.rsplit(".", 1)[0], []).append(sc)
        eids = [i.split(":")[0] for i in _split_ids(r.get("Evidence_IDs"))
                if i and i != C.NO_EVIDENCE]
        declared = _clean(r.get("Absence_Claimed")).upper() in ("YES", "TRUE", "1")
        if eids and _clean(r.get("Challenge_Verdict")).upper() != "PASS":
            f["unchallenged_scored"].append(cell)
        if not eids and not declared:
            f["unresearched_scored"].append(cell)
        rat = _clean(r.get("Rationale"))
        if len(rat) < RATIONALE_MIN:
            f["rationale_short"].append(cell)
        if eids and not (set(re.findall(r"\bE-\d+", rat)) & set(eids)):
            f["rationale_uncited"].append(cell)
        ec = _num(r.get("Evidence_Ceiling"))
        if ec is not None and sc > ec + 1e-9:
            f["score_above_ceiling"].append(cell)
        if _clean(r.get("Confidence")).upper() not in CONFIDENCES:
            f["confidence_invalid"].append(cell)
        if cell not in cl:
            f["caps_log_missing"].append(cell)
        srow = ss.get(cell)
        if srow is None:
            f["subcap_scores_missing"].append(cell)
        else:
            if (_clean(srow.get("ai_applicability")).upper() not in C.AI_APPLICABILITY
                    or _clean(srow.get("data_readiness")).upper() not in C.DATA_READINESS
                    or not _clean(srow.get("data_dependency"))
                    or not _clean(srow.get("ai_evidence_ids"))
                    or not _clean(srow.get("ai_blocker"))
                    or not _clean(srow.get("peer_ai_signal"))):
                f["overlay_incomplete"].append(cell)
    for cap, scores in sorted(by_cap.items()):
        if len(scores) >= 3:
            top = Counter(scores).most_common(1)[0][1]
            if top == len(scores):
                f["no_differentiation"].append(cap)
            elif top / len(scores) > 0.6:
                f["low_differentiation"].append(cap)
    pillars_in_scope = sorted({c[:2] for c in wb.selected_subcaps()})
    critics = {}
    for g in wb.rows("Gate_Log"):
        if _clean(g.get("Gate")) == "SCORING_CRITIC":
            critics[_clean(g.get("Scope"))] = _clean(g.get("Verdict")).upper()
    for p in pillars_in_scope:
        if p not in critics:
            f["critic_missing"].append(p)
        elif critics[p] != "PASS":
            f["critic_failed"].append(p)
    got = compute(wb)
    stated = {_clean(r.get("pillar_id")): _num(r.get("score")) for r in wb.rows("Pillar_Rollup")}
    if not stated or not wb.rows("Category_Rollup") or not wb.rows("Pillar_Summary"):
        f["rollup_missing"].append("Pillar_Rollup / Category_Rollup / Pillar_Summary")
    else:
        for p in got["pillars"]:
            if p["score"] is not None and stated.get(p["pillar_id"]) is not None \
                    and abs(stated[p["pillar_id"]] - p["score"]) > 0.01:
                f["rollup_drift"].append(f"{p['pillar_id']}: stated {stated[p['pillar_id']]} "
                                         f"vs recomputed {p['score']}")
        if got["overall"] is not None and stated.get("OVERALL") is not None \
                and abs(stated["OVERALL"] - got["overall"]) > 0.01:
            f["rollup_drift"].append(f"OVERALL: stated {stated['OVERALL']} vs "
                                     f"recomputed {got['overall']}")
    wsum = round(sum(_weights(wb).values()), 3)
    if abs(wsum - 1.0) > 0.001:
        f["weights_sum"].append(f"weights sum to {wsum}")
    fields = {_clean(r.get("Field")) for r in wb.rows("Executive_Summary")}
    for want in C.EXECUTIVE_SUMMARY_FIELDS:
        if not any(want.casefold() in have.casefold() for have in fields):
            f["dashboard_incomplete"].append(want)
    if not wb.rows("Coverage_Map"):
        f["rollup_missing"].append("Coverage_Map")

    blocking = [k for k in (
        "stage_not_assessment", "unscored", "unnamed", "rationale_short",
        "rationale_uncited", "score_above_ceiling", "score_off_scale",
        "unchallenged_scored", "unresearched_scored", "confidence_invalid",
        "caps_log_missing", "subcap_scores_missing", "overlay_incomplete",
        "critic_missing", "critic_failed", "rollup_missing", "rollup_drift",
        "weights_sum", "dashboard_incomplete", "no_differentiation") if f[k]]
    verdict = "PASS" if not blocking else "FAIL"
    out = {"gate": verdict, "run_id": md.get("run_id"), "stage": C.stage_of(md),
           "subcaps": len(wb.selected_subcaps()), "scored": got["scored"],
           "overall": got["overall"], "blocking": sorted(blocking),
           "advisory": [k for k in ("low_differentiation",) if f[k]],
           "finding_keys": sorted(f), **f}
    if qa_dir is not None:
        Path(qa_dir).mkdir(parents=True, exist_ok=True)
        (Path(qa_dir) / "scoring.json").write_text(json.dumps(out, indent=2, sort_keys=True))
        out["written_to"] = str(Path(qa_dir) / "scoring.json")
    L.append_gate(wb, gate="SCORING", scope="run", verdict=verdict,
                  detail=("; ".join(f"{k}={len(f[k])}" for k in sorted(blocking))
                          or f"all terms met; {got['scored']} scored, overall {got['overall']}"),
                  blocking=True)
    return out


def state(wb: RunWorkbook) -> dict:
    got = compute(wb)
    last = None
    for g in wb.rows("Gate_Log"):
        if _clean(g.get("Gate")) == "SCORING":
            last = {"verdict": g.get("Verdict"), "detail": g.get("Detail"), "at": g.get("Timestamp")}
    return {"stage": C.stage_of(wb.metadata()), "subcaps": got["subcaps"],
            "scored": got["scored"], "evidenced": got["evidenced"],
            "overall": got["overall"], "pillars": got["pillars"],
            "last_scoring_gate": last,
            "critic_verdicts": {_clean(g.get("Scope")): _clean(g.get("Verdict"))
                                for g in wb.rows("Gate_Log")
                                if _clean(g.get("Gate")) == "SCORING_CRITIC"}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.assessment",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        return p

    o = common(sub.add_parser("open"))
    o.add_argument("--force", action="store_true",
                   help="flip the stage even though a research gate is open; "
                        "recorded on the SCORING_OPENED row, never silent")
    sc = common(sub.add_parser("score"))
    sc.add_argument("--subcap", required=True); sc.add_argument("--score", required=True)
    sc.add_argument("--confidence", required=True); sc.add_argument("--rationale", required=True)
    sc.add_argument("--actor", required=True)
    sc.add_argument("--evidence-ceiling"); sc.add_argument("--caps", default="")
    sc.add_argument("--ai-applicability", required=True)
    sc.add_argument("--data-dependency", required=True)
    sc.add_argument("--data-readiness", required=True)
    sc.add_argument("--ai-evidence", default="NONE_FOUND")
    sc.add_argument("--ai-blocker", default="NONE")
    sc.add_argument("--peer-ai-signal", default="UNVERIFIED")
    cr = common(sub.add_parser("critique"))
    cr.add_argument("--pillar", required=True); cr.add_argument("--verdict", required=True)
    cr.add_argument("--actor", required=True); cr.add_argument("--note", required=True)
    ru = common(sub.add_parser("rollup")); ru.add_argument("--headline")
    so = common(sub.add_parser("solution"))
    so.add_argument("--id", required=True); so.add_argument("--name", required=True)
    so.add_argument("--platform", required=True); so.add_argument("--categories", required=True)
    so.add_argument("--rec-id", default="")
    pa = common(sub.add_parser("peer-adoption"))
    pa.add_argument("--product", required=True); pa.add_argument("--peer", required=True)
    pa.add_argument("--verdict", required=True); pa.add_argument("--basis", required=True)
    pa.add_argument("--source", default=""); pa.add_argument("--as-of", default="")
    common(sub.add_parser("gate"))
    common(sub.add_parser("state"))
    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    try:
        if a.cmd == "open":
            out = open_stage(wb, run.qa_dir, force=a.force)
        elif a.cmd == "score":
            out = score(wb, a.subcap, score=a.score, confidence=a.confidence,
                        rationale=a.rationale, actor=a.actor,
                        evidence_ceiling=a.evidence_ceiling, caps=a.caps,
                        ai_applicability=a.ai_applicability,
                        data_dependency=a.data_dependency,
                        data_readiness=a.data_readiness, ai_evidence=a.ai_evidence,
                        ai_blocker=a.ai_blocker, peer_ai_signal=a.peer_ai_signal)
        elif a.cmd == "critique":
            out = critique(wb, pillar=a.pillar, verdict=a.verdict, actor=a.actor, note=a.note)
        elif a.cmd == "rollup":
            out = rollup(wb, headline=a.headline)
        elif a.cmd == "solution":
            out = solution(wb, sol_id=a.id, name=a.name, platform=a.platform,
                           categories=a.categories, rec_id=a.rec_id)
        elif a.cmd == "peer-adoption":
            out = peer_adoption(wb, product=a.product, peer=a.peer, verdict=a.verdict,
                                basis=a.basis, source=a.source, as_of=a.as_of)
        elif a.cmd == "gate":
            out = gate(wb, run.qa_dir)
            print(json.dumps(out, indent=2, sort_keys=True, default=str))
            return 0 if out["gate"] == "PASS" else 1
        else:
            out = state(wb)
        print(json.dumps(out, indent=2, default=str))
        return 0
    except ScoringRefusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
