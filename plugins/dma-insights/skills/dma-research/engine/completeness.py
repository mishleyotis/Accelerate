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
               "REF_Method")

#: Sheets filled by a phase, with the command that fills each. A refusal
#: that names the fix is one an unattended session can act on.
FILLED_BY = {
    "Entity_Timeline": "engine.prelim timeline --date … --event … --signal …",
    "Peer_Benchmarks": "engine.prelim peers --peer … --rule …",
    "Tech_Register": "engine.cli techscan record …",
    "Report_Narrative": "engine.prelim narrate --section … --body …",
    "Gate_Log": "engine.cli gate --category … --require-synthesis",
    "Challenge_Log": "the finding-challenger, via record_challenge",
    "Evidence_Detail": "engine.cli evidence …",
    "Search_Log": "engine.cli search …",
    "DQ_Bank": "engine.cli kg build",
    "Handoff_Lock": "written at workbook creation; a blank one is corruption",
    "Coverage": "recomputed on every synthesis; a blank one means none landed",
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


def _rowcount(wb: RunWorkbook, sheet: str) -> int:
    return len([r for r in wb.rows(sheet)
                if any(_clean(v) for v in r.values())])


def check(wb: RunWorkbook) -> dict:
    """Every tab, its row count, and its verdict."""
    md = wb.metadata()
    declared = reasons(wb)
    selected = wb.selected_subcaps()
    pillars_in_scope = {s.split("C")[0] for s in selected if s}
    rows, blocking, disclosed = [], [], []

    for sheet in C.SHEETS:
        n = _rowcount(wb, sheet)
        if sheet in PILLAR_SHEETS:
            pillar = sheet.split("_")[0]
            if pillar not in pillars_in_scope:
                rows.append({"sheet": sheet, "rows": n, "verdict": "OUT_OF_SCOPE",
                             "detail": f"{pillar} carries no selected subcap "
                                       f"in this run's scope"})
                continue
            want = len([s for s in selected if s.startswith(pillar)])
            verdict = "POPULATED" if n >= want else "SHORT"
            detail = f"{n} of {want} selected subcap row(s)"
            rows.append({"sheet": sheet, "rows": n, "verdict": verdict,
                         "detail": detail})
            if verdict == "SHORT":
                blocking.append(f"{sheet}: {detail}")
            continue
        if n > 0:
            rows.append({"sheet": sheet, "rows": n, "verdict": "POPULATED",
                         "detail": f"{n} row(s)"})
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


def require(wb: RunWorkbook) -> dict:
    out = check(wb)
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
