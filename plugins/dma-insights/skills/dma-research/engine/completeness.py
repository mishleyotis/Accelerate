#!/usr/bin/env python3
"""Every tab populated, or the reason it is not — checked, not hoped.

    python3 -m engine.completeness check   --run R [--json] [--strict]
    python3 -m engine.completeness declare --run R --sheet Peer_Benchmarks \
                                           --reason "…"
    python3 -m engine.completeness sheets

WHY THIS EXISTS. The Golden 1 workbook passed the contract validator, passed
the floors gate, and shipped with SIX of its nineteen tabs empty:
`Entity_Timeline`, `Tech_Register`, `Report_Narrative`, `Peer_Benchmarks`,
`Handoff_Lock` and half of `Coverage`. Nothing was wrong with it by any rule
that existed — the validator checks SHAPE (rule 1: the sheet is present;
rule 2: its headers match), and a sheet with correct headers and no rows is
perfectly shaped. "Workbook generation was never done" and "the workbook
validates" were both true at once, which is the definition of a gap in the
rules rather than a gap in the work.

So this measures the other half: is there anything IN it. A tab may be empty
for an honest reason — a single-category calibration slice builds no entity
timeline, an entity with no public peers has no peer set — and that reason
is RECORDED, per sheet, in `Run_Metadata.empty_sheet_reasons`. An empty tab
with a recorded reason is a disclosure. An empty tab without one blocks the
handoff and the package, which is what "not fully populated" should have
cost the first time.

The reason has a floor and a filler check, for the same cause every other
free-text field in this engine does: a rule that accepts "n/a" is a rule
that accepts anything.
"""
from __future__ import annotations

# Runnable both ways: -m engine.completeness, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import re
import sys
from pathlib import Path

from . import contract as C
from . import runstate
from .workbook import RunWorkbook

_MIN_REASON = 40
#: Matched as WHOLE WORDS, and deliberately short. An earlier version held
#: "none" and "empty" as substrings, which refused the sentence "no
#: institution timeline was researched and none is claimed" — a perfectly
#: good disclosure. A filler check that refuses honest prose trains people to
#: write around it, which is worse than not having one.
_BANNED = ("tbd", "todo", "placeholder", "lorem", "xxx", "n/a", "na",
           "not needed", "no data", "unknown")
_BANNED_RE = re.compile(
    r"(?<![\w/])(" + "|".join(re.escape(b) for b in _BANNED) + r")(?![\w/])",
    re.IGNORECASE)

#: Sheets whose emptiness is never a disclosure — the run does not exist
#: without them, so there is no reason that could excuse a blank.
NEVER_EMPTY = ("00_README", "DQ_Bank", "Evidence_Detail", "Coverage",
               "Search_Log", "Provenance", "Handoff_Lock", "Run_Metadata",
               "REF_Method",
               # Added 2026-08-30. Gate_Log was declarable while two
               # assessment-report sections read it as their only input, so
               # a declared-away Gate_Log took §2 and §8 down with it. A run
               # that gated nothing records a NOT_RUN gate row with the
               # reason — `ledger.append_gate` already requires one — which
               # is the disclosure the SG discipline mandates everywhere
               # else.
               "Gate_Log",
               # Added 2026-09-03 (contract v6). The Client Profile's §1 is
               # the identity anchor and `website` is load-bearing in the
               # app; a run with no firmographic row has no §1 and no O2
               # strip. `engine.profile firmographic` writes it in PRELIM.
               "Firmographics")

#: Sheets filled by a phase, with the command that fills each. A refusal
#: that names the fix is one an unattended session can act on.
FILLED_BY = {
    "Entity_Timeline": ("engine.prelim timeline --date … --event … "
                        "--signal POSITIVE|NEUTRAL|NEGATIVE --kind …"),
    "Peer_Benchmarks": "engine.prelim peers --peer … --rule …",
    "Tech_Register": ("engine.cli techscan clay-plan, then "
                      "import-explorium / record --provider …"),
    "Pillar_Summary": ("the ASSESSMENT stage's rollup — "
                       "engine.cli grains recompute"),
    "Category_Detail": ("the ASSESSMENT stage's rollup — "
                        "engine.cli grains recompute"),
    "Recommendations": ("projected from the assessment report's REC-NN cards "
                        "(the pinned Doc's §8) — engine.cli grains recommendations"),
    "Tech_Peer_Deployments": ("engine.cli techscan peer-record --ts … "
                              "--peer … --deployed|--not-deployed|--unknown "
                              "--basis …"),
    # TWO different things live in this tab and they have different
    # commands. Naming only the first told an unattended session to write
    # PRELIM rows when what was missing was a report section.
    "Report_Narrative": ("engine.prelim narrate --section … --body … "
                         "(the PRELIM rows); engine.narrative write --report "
                         "… --section … (the sixteen report sections)"),
    "Gate_Log": "engine.cli gate --category … --require-synthesis",
    "Challenge_Log": "the finding-challenger, via record_challenge",
    "Evidence_Detail": "engine.cli evidence …",
    "Search_Log": "engine.cli search …",
    "DQ_Bank": "engine.cli kg build",
    "Handoff_Lock": "written at workbook creation; a blank one is corruption",
    "Financial_Trends": ("engine.profile financial --metric … --fy FY20NN "
                         "--value … --unit … --evidence E-NNNN (≥5 fiscal "
                         "years × ≥3 metrics, the Golden 1 depth), or "
                         "engine.completeness declare --sheet Financial_Trends "
                         "--reason … for an institution that publishes fewer"),
    "Coverage": "recomputed on every synthesis; a blank one means none landed",
    # v6 — the client's own facts, written in PRELIM / by the profile writers
    "Firmographics": ("engine.profile firmographic --field website --value … "
                      "--as-of … --evidence E-… (or --state ABSENT --reason … "
                      "--route …), for every must-present field"),
    "Focus_Areas": ("engine.profile focus --id FA-01 --title … --quote '<verbatim "
                    "50-400 chars>' --document … --page … --cells … --evidence …"),
    "Issue_Register": ("engine.profile issue --id I-001 --type … --severity … "
                       "--status … --description … --cells … --evidence … ; or "
                       "declare it with the negative-search ladder"),
    "Enrichment_Needed": ("engine.profile enrichment-needed --area … --field … "
                          "--status … --closes …; or declare it when nothing is "
                          "outstanding"),
    # v6 — the scoring stage
    "Executive_Summary": "engine.assessment rollup (after every subcap is scored)",
    "Subcap_Scores": "engine.assessment score --subcap … (one row per scored cell)",
    "Pillar_Rollup": "engine.assessment rollup",
    "Category_Rollup": "engine.assessment rollup",
    "Pillar_Weights": "engine.assessment stage --to assessment (writes the sub-vertical weight set)",
    "Maturity_Rubric": "engine.assessment stage --to assessment",
    "Catalogue_Meta": "engine.assessment stage --to assessment",
    "Cap_Triggers": "engine.assessment stage --to assessment",
    "Caps_Applied_Log": "engine.assessment score (one row per scored cell)",
    "Coverage_Map": "engine.assessment rollup",
    "Capability_Definitions": "engine.assessment stage --to assessment",
    "Solution_Catalogue": "engine.assessment solution --id … --name … --platform …",
    "Platform_Peer_Adoption": ("engine.assessment peer-adoption --product … --peer … "
                               "--verdict … --basis … --source …; or declare it"),
}

#: The four pillar sheets are scoped: a run selects subcaps in some pillars
#: and not others, and an unselected pillar's sheet is empty BY the scope,
#: which the workbook already records. Checked against the selection rather
#: than against zero.
PILLAR_SHEETS = C.PILLAR_SHEETS


class CompletenessRefusal(ValueError):
    """A tab is empty and nobody said why."""


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def _is_filler(text: str) -> bool:
    t = _clean(text)
    return len(t) < _MIN_REASON or bool(_BANNED_RE.search(t))


def reasons(wb: RunWorkbook) -> dict[str, str]:
    raw = _clean(wb.metadata().get("empty_sheet_reasons"))
    if not raw:
        return {}
    try:
        got = json.loads(raw)
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in (got or {}).items()}


def declare(wb: RunWorkbook, sheet: str, reason: str) -> dict:
    """Record why THIS sheet is legitimately empty in THIS run."""
    if sheet not in C.SHEETS:
        raise CompletenessRefusal(
            f"{sheet!r} is not a contract sheet; one of "
            f"{', '.join(sorted(C.SHEETS))}")
    if sheet in NEVER_EMPTY:
        raise CompletenessRefusal(
            f"{sheet} cannot be declared empty. "
            + FILLED_BY.get(sheet, "The run does not exist without it."))
    if _is_filler(reason):
        raise CompletenessRefusal(
            f"the reason for an empty {sheet} is {reason!r}. Say what was "
            f"looked for and did not exist — the scope that excludes it, or "
            f"the search that came back empty (>= {_MIN_REASON} chars, no "
            f"filler). An empty tab is either a finding or an omission, and "
            f"the reason is how a reader tells which.")
    have = reasons(wb)
    have[sheet] = _clean(reason)
    wb.set_metadata("empty_sheet_reasons", json.dumps(have, sort_keys=True))
    return {"sheet": sheet, "reason": have[sheet], "declared": len(have)}


#: The smallest row count that means the work behind a tab actually
#: happened. A plain `n > 0` was vacuous for the timeline, whose own PRELIM
#: section declares a three-event floor that the tab did not inherit.
CONTENT_FLOORS = {
    "Entity_Timeline": (
        3, "PRELIM's own floor for a timeline that says anything"),
}


def _report_sections(wb: RunWorkbook) -> tuple[int, int]:
    """(written report sections, sections the two specs declare).

    Report_Narrative holds two different things — the PRELIM rows (see
    `prelim.SECTIONS`, which grew from six to seven when the technographic
    scan and the contact pass moved into the phase) and the sixteen report
    sections — and `engine.cli start` writes one of the
    PRELIM rows unconditionally. So the tab can never be empty, and a bare
    row count said POPULATED over sixteen unwritten sections. It is not
    BLOCKED here (that is `narrative.require_ready`, which the renderer
    calls, and duplicating a gate is how two gates drift apart) — but the
    verdict says what is actually in the tab, which is the whole job of a
    completeness report.
    """
    from . import report_spec as RS
    want = {(k, str(sec.id)) for k, spec in RS.SPECS.items()
            for sec in spec.sections}
    got = {(_clean(r.get("Report")), _clean(r.get("Section_ID")))
           for r in wb.rows("Report_Narrative")}
    return len(want & got), len(want)


def _researched(wb: RunWorkbook, sheet: str) -> int:
    """Rows on a pillar sheet that carry RESEARCH, not just a seed."""
    n = 0
    for r in wb.rows(sheet):
        if not _clean(r.get("SubCap_ID")):
            continue
        eids = _clean(r.get("Evidence_IDs"))
        if _clean(r.get("Dominant_Claim")) or (eids and eids != C.NO_EVIDENCE):
            n += 1
    return n


def _rowcount(wb: RunWorkbook, sheet: str) -> int:
    return len([r for r in wb.rows(sheet)
                if any(_clean(v) for v in r.values())])


#: Tabs that are PROJECTED FROM the assessment report after it is written
#: (`engine.grains recommendations` reads the report's REC cards into the
#: Recommendations tab). A gate that runs BEFORE the report is written must
#: not demand them: it would be asking the report for its own output as a
#: precondition of starting, and nothing could ever pass it.
REPORT_DERIVED = ("Recommendations",)


def check(wb: RunWorkbook, *, exclude=()) -> dict:
    """Every tab, its row count, and its verdict. `exclude` names tabs this
    caller has a stated reason not to judge (see REPORT_DERIVED)."""
    md = wb.metadata()
    declared = reasons(wb)
    selected = wb.selected_subcaps()
    pillars_in_scope = {s.split("C")[0] for s in selected if s}
    rows, blocking, disclosed = [], [], []

    stage = C.stage_of(md)
    for sheet in C.SHEETS:
        if sheet in exclude:
            continue
        n = _rowcount(wb, sheet)
        # A sheet that belongs to the OTHER stage is neither populated nor
        # an omission: there is nothing at this stage that could fill it.
        # The three scored grains are the case — column D is empty at the
        # research stage by contract rule 4, so a research run asked for a
        # Pillar_Summary would be asked for something it is forbidden to
        # produce. A row that arrives anyway is reported, because a research
        # workbook carrying assessment scores is a different problem.
        want_stage = C.SHEET_STAGE.get(sheet)
        if want_stage and want_stage != stage:
            rows.append({
                "sheet": sheet, "rows": n,
                "verdict": "OUT_OF_STAGE" if not n else "AHEAD_OF_STAGE",
                "detail": (f"belongs to the {want_stage} stage; this "
                           f"workbook is at {stage}"
                           if not n else
                           f"{n} row(s) on a {want_stage}-stage sheet in a "
                           f"{stage}-stage workbook — the stage says this "
                           f"cannot have been produced yet")})
            if n:
                blocking.append(f"{sheet}: {rows[-1]['detail']}")
            continue
        if sheet in PILLAR_SHEETS:
            pillar = sheet.split("_")[0]
            if pillar not in pillars_in_scope:
                rows.append({"sheet": sheet, "rows": n, "verdict": "OUT_OF_SCOPE",
                             "detail": f"{pillar} carries no selected subcap "
                                       f"in this run's scope"})
                continue
            want = len([s for s in selected if s.startswith(pillar)])
            # SEEDED IS NOT RESEARCHED. `create` writes a row per selected
            # cell with NO_EVIDENCE / NOT_RUN in it, and a plain row count is
            # therefore satisfied before a single search has run. Count the
            # rows that carry research instead.
            done = _researched(wb, sheet)
            verdict = "POPULATED" if done >= want else "SHORT"
            detail = (f"{done} of {want} selected subcap row(s) carry "
                      f"research ({n} row(s) present, the rest seeded)")
            rows.append({"sheet": sheet, "rows": n, "verdict": verdict,
                         "detail": detail})
            if verdict == "SHORT":
                blocking.append(f"{sheet}: {detail}")
            continue
        floor, why = CONTENT_FLOORS.get(sheet, (0, ""))
        # Only for a tab that has SOME rows. A tab with none falls through
        # to the declaration path, where an empty timeline is a disclosure
        # with a ladder; a HALF-filled one cannot be declared away and is
        # what this floor is for.
        if n and floor and n < floor:
            # A row count is not content. `engine.cli start` writes one
            # Report_Narrative row unconditionally, so that tab could never
            # be empty and its check could never fire — a POPULATED verdict
            # on sixteen unwritten sections. These floors are the smallest
            # count that means the work happened.
            detail = f"{n} of {floor} row(s) — {why}"
            rows.append({"sheet": sheet, "rows": n, "verdict": "SHORT",
                         "detail": detail})
            blocking.append(f"{sheet}: {detail}")
            continue
        if n > 0:
            detail = f"{n} row(s)"
            if sheet == "Report_Narrative":
                done, want = _report_sections(wb)
                detail = (f"{n} row(s) — {done} of {want} report section(s) "
                          f"written; the PRELIM rows are the rest. "
                          f"`engine.narrative state` is the blocking gate on "
                          f"the sections, and the renderer calls it.")
            rows.append({"sheet": sheet, "rows": n, "verdict": "POPULATED",
                         "detail": detail})
            continue
        if sheet in declared and sheet in NEVER_EMPTY:
            # `declare` refuses these; the metadata key can still be written
            # by hand. A forged declaration is worse than a missing one and
            # must read that way, not quieter.
            detail = (f"{sheet} is in NEVER_EMPTY and cannot be declared "
                      f"empty, but empty_sheet_reasons carries a reason for "
                      f"it: {declared[sheet]!r}. That key was written around "
                      f"the refusal. " + FILLED_BY.get(sheet, ""))
            rows.append({"sheet": sheet, "rows": 0,
                         "verdict": "ILLEGAL_DECLARATION", "detail": detail})
            blocking.append(f"{sheet}: {detail}")
            continue
        if sheet in declared and not _is_filler(declared[sheet]):
            rows.append({"sheet": sheet, "rows": 0, "verdict": "DECLARED_EMPTY",
                         "detail": declared[sheet]})
            disclosed.append(sheet)
            continue
        fix = FILLED_BY.get(sheet)
        detail = ("empty, and no reason recorded"
                  + (f" — fill it with: {fix}" if fix else ""))
        rows.append({"sheet": sheet, "rows": 0, "verdict": "EMPTY", "detail": detail})
        blocking.append(f"{sheet}: {detail}")

    return {
        "run_id": md.get("run_id"), "entity": md.get("entity_name"),
        "complete": not blocking,
        "blocking": blocking,
        "declared_empty": disclosed,
        "sheets": rows,
        "populated": sum(1 for r in rows if r["verdict"] == "POPULATED"),
        "total": len(rows),
    }


def require(wb: RunWorkbook, *, exclude=()) -> dict:
    out = check(wb, exclude=exclude)
    if not out["complete"]:
        raise CompletenessRefusal(
            f"{len(out['blocking'])} tab(s) are empty with no reason "
            f"recorded. A workbook that validates and carries nothing is the "
            f"Golden 1 shape: shape-correct, content-empty.\n  - "
            + "\n  - ".join(out["blocking"])
            + "\n\nEither fill them, or record why each is legitimately "
              "empty:\n    engine.completeness declare --sheet <Sheet> "
              "--reason '…'")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.completeness",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="every tab, its rows, its verdict")
    c.add_argument("--run", required=True); c.add_argument("--root")
    c.add_argument("--json", action="store_true")
    d = sub.add_parser("declare", help="why this tab is legitimately empty")
    d.add_argument("--run", required=True); d.add_argument("--root")
    d.add_argument("--sheet", required=True); d.add_argument("--reason",
                                                             required=True)
    sub.add_parser("sheets", help="the contract's sheets and who fills each")

    a = ap.parse_args(argv)
    if a.cmd == "sheets":
        for s in C.SHEETS:
            mark = "!" if s in NEVER_EMPTY else " "
            print(f" {mark} {s:<22} {FILLED_BY.get(s, '')}")
        print("\n ! = may never be declared empty")
        return 0
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    if a.cmd == "declare":
        try:
            print(json.dumps(declare(wb, a.sheet, a.reason), indent=2))
        except CompletenessRefusal as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        return 0
    out = check(wb)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        note = (f", {len(out['declared_empty'])} declared empty"
                if out["declared_empty"] else "")
        print(f"{'COMPLETE' if out['complete'] else 'INCOMPLETE'} — "
              f"{out['populated']}/{out['total']} tabs populated{note}")
        for r in out["sheets"]:
            mark = {"POPULATED": "✓", "DECLARED_EMPTY": "·",
                    "OUT_OF_SCOPE": "–", "EMPTY": "✗", "SHORT": "✗"}[r["verdict"]]
            print(f"  {mark} {r['sheet']:<22} {r['detail']}")
    return 0 if out["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
