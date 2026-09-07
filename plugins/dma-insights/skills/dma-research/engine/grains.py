#!/usr/bin/env python3
"""The assessment stage's three tabs: the stated grains, and the rec list.

    python3 -m engine.grains show --run R [--root DIR]
    python3 -m engine.grains recompute --run R          # the two grains
    python3 -m engine.grains recommendations --run R    # from the report

WHY THIS EXISTS. The app READS all three — `parse_grain_summaries` for
Pillar_Summary and Category_Detail, `parse_recommendations` for
Recommendations — both land server-side, and both already back live gates:
the 0.05 grain tolerance reconciles served figures against the STATED grains,
and CG-39 reads `recommendations_raw`. Nothing ever WROTE them. Every package
this engine built therefore landed with zero recommendations and both stated
grains absent, and the app said so in an observation nobody was reading.

WHY THE GRAINS ARE STATED RATHER THAN DERIVED AT READ TIME. H4's grain lock
forbids recomputing a pillar or category score by averaging its subcaps: cap
logic, weighting and analyst override are applied when the figure is struck,
and an average taken afterwards silently undoes all three. So the workbook
STATES them, and the 0.05 tolerance exists to catch the two drifting apart.
This module computes them ONCE, at the moment the scores are struck, and
writes them down — which is what "stated" means. It is not a read-time
recomputation and must never be called as one.

WHY IT REFUSES AT THE RESEARCH STAGE. Column D is empty at the research stage
by contract rule 4. A grain computed from no scores is not a grain; it is a
column of nulls that reads like an assessment.
"""
from __future__ import annotations

# Runnable both ways: -m engine.grains, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import sys
from pathlib import Path

from . import contract as C
from . import runstate
from .workbook import RunWorkbook


class GrainRefused(SystemExit):
    pass


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def require_assessment(wb: RunWorkbook) -> str:
    stage = C.stage_of(wb.metadata())
    if stage != "assessment":
        raise GrainRefused(
            f"this workbook is at the {stage} stage, and the stated grains "
            f"belong to the assessment. Column D is empty at the research "
            f"stage by contract rule 4, so a grain computed here would be a "
            f"column of nulls that reads like an assessment. Set the stage "
            f"when the scores are struck: "
            f"`engine.grains stage --run <R> --to assessment`.")
    return stage


def scored_rows(wb: RunWorkbook) -> list[dict]:
    """Every subcap row that carries a score, across the four pillar sheets."""
    out = []
    for sheet in C.PILLAR_SHEETS:
        for r in wb.rows(sheet):
            cid = _clean(r.get("Category"))
            score = _num(r.get("Score"))
            if not cid or score is None:
                continue
            out.append({"subcap": _clean(r.get("SubCap_ID")),
                        "category": cid, "pillar": cid.split("C")[0],
                        "score": score})
    return out


def compute(wb: RunWorkbook) -> dict:
    """The two grains, from the scores as they stand.

    Simple means, DELIBERATELY. This engine applies no weighting and no
    analyst override of its own — it has none to apply — so a mean is the
    honest figure and the 0.05 tolerance is what catches a served figure
    that was struck differently. A weighting invented here would be a
    number with no authority behind it, which is worse than an average.
    """
    rows = scored_rows(wb)
    cats: dict[str, list[float]] = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r["score"])
    pillars: dict[str, list[float]] = {}
    for cid, scores in cats.items():
        pillars.setdefault(cid.split("C")[0], []).extend(scores)

    def mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else None

    return {
        "subcaps_scored": len(rows),
        "categories": [{"Category_ID": cid, "Category_Name": "",
                        "Pillar": cid.split("C")[0],
                        "Score": mean(scores), "Peer_Median": "",
                        "Priority_Score": "", "Priority_Tier": ""}
                       for cid, scores in sorted(cats.items())],
        "pillars": [{"Pillar": pid, "Pillar_Name": "",
                     "Score": mean(scores), "Weight_Pct": "",
                     "Peer_Median": ""}
                    for pid, scores in sorted(pillars.items())],
    }


def _replace(wb: RunWorkbook, sheet: str, rows: list[dict]) -> int:
    """Replace every data row of `sheet` — inside ONE transaction.

    Measured 2026-09-04 (the stage walk): the delete ran on the in-memory
    sheet, then the first `wb.append` opened its own transaction, which
    RELOADS the workbook from disk on entry — so the deletion was lost and
    the new rows landed after the old ones (`['P1','P2','P3','P4','OVERALL',
    'P1']`), which the gold gate then refused as duplicate grains. Holding
    the transaction across delete-and-append makes the replacement atomic
    and idempotent, like `assessment._replace` already was."""
    with wb.transaction(f"grains.replace {sheet}"):
        ws = wb._sheet(sheet)
        if ws.max_row > 1:
            ws.delete_rows(2, ws.max_row)
        for row in rows:
            wb.append(sheet, row, save=False)
        wb.save()
    return len(rows)


def recompute(wb: RunWorkbook) -> dict:
    """State both grains. Refuses a workbook with no scores at all.

    ONE WRITER (2026-09-04). Until now this wrote Pillar_Summary /
    Category_Detail itself — pillars in scope only, weights and peer medians
    blank — while `engine.assessment rollup` wrote the same two sheets with
    all four pillars, OVERALL, the weight set and the peer figures. Two
    writers, two shapes, and the gold gate (GS-WB-GRAINS: "pillars not all
    present"; GS-WB-EMPTY) refused whichever ran second. The stated grains
    are the assessment stage's; this command now delegates to its writer and
    keeps only the refusals that were its own."""
    require_assessment(wb)
    got = compute(wb)
    if not got["subcaps_scored"]:
        raise GrainRefused(
            "no subcapability carries a score, so there is no grain to "
            "state. An assessment-stage workbook with an empty column D is "
            "the thing the stage key exists to make visible.")
    from . import assessment as A
    try:
        A.rollup(wb)
    except A.ScoringRefusal as e:
        if "headline" in str(e).lower():
            raise GrainRefused(
                "the stated grains are written by `engine.assessment rollup`, and "
                "the Executive_Summary has no headline yet — run "
                "`engine.assessment rollup --run <R> --root <ROOT> --headline "
                "'<one institution-specific line, 40+ chars>'` once; recompute "
                "re-derives from it after that") from None
        raise GrainRefused(str(e)) from None
    return {"pillars": len([r for r in wb.rows("Pillar_Summary") if _clean(r.get("Pillar"))]),
            "categories": len([r for r in wb.rows("Category_Detail")
                               if _clean(r.get("Category_ID"))]),
            "subcaps_scored": got["subcaps_scored"],
            "writer": "engine.assessment rollup"}


def recommendations(wb: RunWorkbook) -> dict:
    """Project the assessment report's REC cards into the tab the app reads.

    The recommendations already exist — one Report_Narrative row per REC-NN
    card of the pinned template's recommendation section (§8 of the Doc),
    written through `engine.narrative write --card`, each carrying the
    section's declared blocks (Root cause · Cost of inaction · Solution ·
    Platform readiness contract · Rebuttal · …). This does not author anything; it puts
    them where `parse_recommendations` looks, so the app stops landing every
    package with zero of them.
    """
    require_assessment(wb)
    from . import report_spec as RS

    sec = next(s for s in RS.SPECS["assessment"].sections
               if s.kind == "recommendation")
    rows = [r for r in wb.rows("Report_Narrative")
            if _clean(r.get("Report")) == "assessment"
            and _clean(r.get("Section_ID")) == str(sec.id)
            and _clean(r.get("Body"))]
    if not rows:
        raise GrainRefused(
            f"the assessment report's §{sec.id} '{sec.heading}' carries no "
            f"rows, so there is nothing to project. Write them first: "
            f"`engine.narrative write --report assessment --section {sec.id} "
            f"--card <id>`.")
    out = []
    for i, r in enumerate(rows, 1):
        body = _clean(r.get("Body"))
        card = _clean(r.get("Card_ID")) or f"{i:03d}"
        out.append({
            "Rec_ID": card if card.upper().startswith("REC-")
                      else f"REC-{card}",
            # The heading a reader sees, which is the card's first block.
            "Title": _clean(r.get("Heading")) or sec.heading,
            "Category_ID": "", "Priority": i, "Horizon": "", "Owner": "",
            # The whole argument, so the tab is not a weaker copy of the
            # report — the app stores the payload verbatim.
            "Rationale": body[:2000],
        })
    return {"rows": _replace(wb, "Recommendations", out),
            "from_section": str(sec.id)}


def set_stage(wb: RunWorkbook, to: str) -> dict:
    if to not in C.STAGES:
        raise GrainRefused(f"stage {to!r} is not one of {C.STAGES}")
    was = C.stage_of(wb.metadata())
    if to == "assessment" and not scored_rows(wb):
        raise GrainRefused(
            "a workbook with no scored subcapability is not at the "
            "assessment stage, whatever it is told. Column D is what the "
            "stage means. To BEGIN scoring, `engine.assessment open` flips "
            "the stage after checking the research gates and writes the "
            "weight set, rubric and cap rules the scores are struck against.")
    wb.set_metadata("stage", to)
    return {"stage": to, "was": was}


def state(wb: RunWorkbook) -> dict:
    md = wb.metadata()
    got = compute(wb)
    return {
        "stage": C.stage_of(md),
        "subcaps_scored": got["subcaps_scored"],
        "stated": {s: len([r for r in wb.rows(s) if any(_clean(v)
                                                        for v in r.values())])
                   for s in ("Pillar_Summary", "Category_Detail",
                             "Recommendations")},
        "computed_pillars": got["pillars"],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.grains",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "recompute", "recommendations", "stage"):
        s = sub.add_parser(name)
        s.add_argument("--run", required=True)
        s.add_argument("--root")
        if name == "stage":
            s.add_argument("--to", required=True, choices=C.STAGES)
    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    try:
        if a.cmd == "show":
            print(json.dumps(state(wb), indent=2, default=str))
        elif a.cmd == "recompute":
            print(json.dumps(recompute(wb), indent=2))
        elif a.cmd == "recommendations":
            print(json.dumps(recommendations(wb), indent=2))
        else:
            print(json.dumps(set_stage(wb, a.to), indent=2))
        return 0
    except GrainRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
