#!/usr/bin/env python3
"""The brief a section's writer receives BEFORE authoring — bound to that
section's own declared inputs.

    python3 -m engine.authoring brief   --report assessment --section 5 [--run R --root ROOT]
    python3 -m engine.authoring preflight --report assessment  --run R --root ROOT
    python3 -m engine.authoring antipatterns [--json]

WHY THIS EXISTS. Measured 2026-09-06 on a delivered pair of reports that passed
every gate the build then had: the assessment carried 50 tables against the
Golden 1 reference's 92 and the research report 26 against 39, while paragraph
words ran 1.57x the reference in both. The gates counted words and citations and
could not see SHAPE — and because more prose raises a word count, the defect was
not merely uncaught, it was rewarded. The owner's report was blunt: "the 2
reports lack depth ... do not adhere to template requirements eg where tables
are, I see paragraphs."

A gate that fires after rendering is the wrong end of the loop for this class of
defect: by then the section has been written, reviewed and merged, and the
repair is a rewrite. So the same rules the gate enforces are handed to the
writer first, as obligations naming THIS section's declared inputs — which
sheets it must state as tables, and which of those sheets currently carry no
rows and would therefore render nothing at all.

The register lives in references/templates/report_antipatterns.json; this module
is the join between it, the pinned section spec, and the run's own workbook.
"""
from __future__ import annotations

if __package__ in (None, ""):  # noqa: E402  (must precede the relative imports)
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
from . import report_spec as RS
from . import template as T

#: Sheets a section may declare as an input without owing a rendered table —
#: they are the section's own prose source or a per-cell working area. Mirrors
#: reports._NO_TABLE, which decides what actually renders.
_NO_TABLE = frozenset({"Report_Narrative", "Search_Log"})


def antipatterns() -> list[dict]:
    """The register, verbatim. Empty list when the file cannot be read — a
    brief without its anti-patterns is still worth issuing, and the test suite
    asserts the file parses."""
    p = T.TEMPLATES_DIR / "report_antipatterns.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("antipatterns", [])
    except (OSError, ValueError):
        return []


def table_inputs(sec) -> list[str]:
    """The sheets THIS section owes as tables — its declared inputs, minus the
    ones that render as prose rather than a table. This is the same filter
    `reports._tables_for` applies, so the obligation a writer is given is the
    table the renderer will actually look for."""
    return [n for n in sec.inputs
            if n not in _NO_TABLE and n != "Evidence_Detail" and n in C.SHEETS]


def section_obligations(report: str, section_id: str, wb=None) -> dict:
    """What one section owes: its blocks, its table inputs, and — when a
    workbook is supplied — which of those inputs carry no rows and would
    therefore render nothing."""
    spec = RS.SPECS[report]
    sec = next((s for s in spec.sections if str(s.id) == str(section_id)), None)
    if sec is None:
        raise KeyError(f"{report} has no section {section_id!r}; "
                       f"sections are {[s.id for s in spec.sections]}")
    owed = table_inputs(sec)
    empty = []
    if wb is not None:
        empty = [n for n in owed if not wb.rows(n)]
    return {
        "report": report, "section": str(sec.id), "heading": sec.heading,
        "kind": sec.kind, "blocks": list(sec.blocks or ()),
        "requires_citation": bool(sec.requires_citation),
        "min_words": sec.min_words,
        "tables_owed": owed, "tables_empty": empty,
        "tables_that_will_render": [n for n in owed if n not in empty],
    }


def preflight(report: str, wb=None) -> dict:
    """Every section's obligations at once, with the report-level totals a
    producer needs before starting: how many tables the report will render as
    things stand, and which declared inputs are empty."""
    spec = RS.SPECS[report]
    secs = [section_obligations(report, s.id, wb) for s in spec.sections]
    empty = sorted({n for s in secs for n in s["tables_empty"]})
    return {
        "report": report,
        "sections": secs,
        "tables_declared": sum(len(s["tables_owed"]) for s in secs),
        "tables_that_will_render": sum(len(s["tables_that_will_render"])
                                       for s in secs),
        "empty_declared_inputs": empty,
    }


def brief(report: str, section_id: str, wb=None) -> str:
    """The text handed to the agent writing this section, before it writes.

    Names the section's own table obligations first, because that is the part
    a general rule cannot carry: "state your registers as tables" is advice,
    while "this section declares Issue_Register and Cap_Triggers and both are
    empty, so it will render two fewer tables than the template specifies" is
    an instruction the writer can act on.
    """
    ob = section_obligations(report, section_id, wb)
    L: list[str] = []
    L.append(f"AUTHORING BRIEF — {ob['report']} §{ob['section']} "
             f"{ob['heading']}")
    L.append("")
    L.append(f"Kind: {ob['kind']} · minimum {ob['min_words']} words · "
             f"citation required: {'yes' if ob['requires_citation'] else 'no'}")
    if ob["blocks"]:
        L.append("Blocks, in this order, each as a '## <name>' line in Body:")
        for b in ob["blocks"]:
            L.append(f"  - {b}")
    L.append("")
    # What the Golden 1 reference actually carries in THIS section — the
    # target a writer aims at, not just the declared-input floor. Some of
    # these tables are AUTHORED in the body (findings, gaps, why-now cards,
    # scorecards, the per-recommendation contract), not derived from a sheet;
    # the renderer turns a markdown pipe-table in Body into a real table.
    try:
        from . import gold_standard as _GS
        anat = _GS.section_floors(report)
        ref_n = anat["section_reference"].get(str(section_id))
        floor_n = anat["section_floors"].get(str(section_id))
        if ref_n:
            L.append(f"GOLDEN 1 CARRIES {ref_n} TABLE(S) IN THIS SECTION — this "
                     f"run owes at least {floor_n}. Some are derived from a")
            L.append("declared sheet (below); the rest are AUTHORED in Body as")
            L.append("markdown pipe-tables (| col | col |), each with an Evidence")
            L.append("column: findings, gaps, why-now cards, scorecards, the")
            L.append("per-recommendation conditions/rebuttal/impact contract.")
            L.append("")
    except Exception:            # noqa: BLE001 — the brief must still issue
        pass
    L.append("TABLES THIS SECTION OWES — the pinned Doc states these as tables,")
    L.append("and the renderer emits one table per declared input:")
    if ob["tables_owed"]:
        for n in ob["tables_owed"]:
            mark = "  EMPTY — renders NOTHING as things stand" \
                if n in ob["tables_empty"] else ""
            L.append(f"  - {n}{mark}")
    else:
        L.append("  (none — this section is prose and its cited evidence table)")
    if ob["tables_empty"]:
        L.append("")
        L.append("Those empty inputs are the defect to fix BEFORE writing: a")
        L.append("paragraph describing what the table would have said is the")
        L.append("anti-pattern this brief exists to prevent. Populate the sheet,")
        L.append("or have the section's spec stop declaring it.")
    L.append("")
    L.append("ANTI-PATTERNS — each names the gate that will refuse it:")
    for a in antipatterns():
        L.append(f"  [{a.get('id')}] gate {a.get('gate')}")
        L.append(f"      {a.get('what')}")
        L.append(f"      REPAIR: {a.get('repair')}")
        if a.get("not_the_repair"):
            L.append(f"      NOT the repair: {a['not_the_repair']}")
    L.append("")
    L.append("Depth is measured against the Golden 1 reference, not against a")
    L.append("word count alone: `engine.gold_standard report <docx>` checks the")
    L.append("table count and the prose/table split as well as words and")
    L.append("citations. More prose does not clear a structure finding.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief")
    b.add_argument("--report", required=True, choices=sorted(RS.SPECS))
    b.add_argument("--section", required=True)
    b.add_argument("--run"); b.add_argument("--root")
    p = sub.add_parser("preflight")
    p.add_argument("--report", required=True, choices=sorted(RS.SPECS))
    p.add_argument("--run"); p.add_argument("--root")
    p.add_argument("--json", action="store_true")
    a_ = sub.add_parser("antipatterns"); a_.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    wb = None
    if getattr(a, "run", None):
        from . import runstate
        wb = runstate.locate(a.run, Path(a.root) if a.root else None).open()

    if a.cmd == "antipatterns":
        pats = antipatterns()
        if a.json:
            print(json.dumps(pats, indent=2))
        else:
            for x in pats:
                print(f"[{x['id']}] gate {x['gate']}\n  {x['what']}\n"
                      f"  REPAIR: {x['repair']}\n")
        return 0
    if a.cmd == "brief":
        print(brief(a.report, a.section, wb))
        return 0
    out = preflight(a.report, wb)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"{out['report']}: {out['tables_that_will_render']} of "
              f"{out['tables_declared']} declared tables will render")
        if out["empty_declared_inputs"]:
            print(f"  empty declared inputs: {out['empty_declared_inputs']}")
        for s in out["sections"]:
            flag = "  <-- EMPTY INPUTS" if s["tables_empty"] else ""
            print(f"  §{s['section']:>3} {s['heading'][:40]:<40} "
                  f"{len(s['tables_that_will_render'])}/{len(s['tables_owed'])}"
                  f"{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
