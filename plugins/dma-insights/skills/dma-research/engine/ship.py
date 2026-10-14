#!/usr/bin/env python3
"""Which of the app's six pages could be produced from THIS workbook, now.

    python3 -m engine.ship state --run R [--root DIR] [--json]

WHY THIS EXISTS (owner, 2026-09-03, issue 7): "The current mechanism leads to
token bleed in promoting the DMA to the web app. As research and assessment
progresses, please ensure that the agents submit the results to the MCP
connector verifying at each step that everything is okay, such that when the
assessment ends, the promotion is already done."

Two facts bound the design, and both are invariants rather than preferences:
content enters the app only through the connector against a run the package
scan has INGESTED (invariant 2), and promotion is atomic across all six pages
(invariant 3). So "submit as you go" cannot mean pushing half a workbook to
the intake tree every hour — every re-scan of a changed workbook is a run
version, and eighteen of one client's nineteen runs landed with zero scored
cells exactly that way. It means:

  1. the research and scoring stages CHECKPOINT the package to the client
     folder at their two natural boundaries (scoring gate PASS; reports
     READY), so the scan ingests a scored run while the reports are still
     being written and page production can begin on it — see
     `engine.assemble checkpoint`;
  2. the surface producers ship each PAGE the moment its sections exist
     (`ship_page.py … --incremental`), from disk, never retyped, so the
     transport cost is paid once per page and the gate refusals arrive while
     the producer can still act on them;
  3. THIS command answers, from the workbook alone, which pages are
     producible right now — the join of `references/tab_recording_map.json`
     (which tab feeds which page section) with what the tabs actually hold —
     so the conductor dispatches page producers in dependency order as tabs
     fill, instead of after the whole assessment.

Nothing here writes to the connector. It reads the workbook and the recording
map and says what is ready; the surface-producer remains the only writer.
"""
from __future__ import annotations

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

PLUGIN = Path(__file__).resolve().parents[3]
RECORDING_MAP = PLUGIN / "references" / "tab_recording_map.json"

PAGES = ("heatmap", "overview", "insights", "platform", "context", "techstack")

#: What each page needs IN THE WORKBOOK before a producer can write it
#: honestly — the tabs its sections read, per the recording map and the
#: surface routing table. Scores gate every page that renders a figure;
#: the reports gate the pages that render prose written FROM them.
PAGE_NEEDS = {
    "heatmap": {"tabs": ("Subcap_Scores", "Pillar_Rollup", "Category_Rollup",
                         "Evidence_Detail", "Focus_Areas", "Coverage_Map"),
                "gates": ("SCORING",)},
    "techstack": {"tabs": ("Tech_Register",), "gates": ()},
    "context": {"tabs": ("Entity_Timeline", "Issue_Register", "Firmographics"),
                "gates": ()},
    "overview": {"tabs": ("Executive_Summary", "Pillar_Rollup", "Firmographics",
                          "Peer_Benchmarks", "Coverage_Map"),
                 "gates": ("SCORING",), "reports": ("assessment",)},
    "insights": {"tabs": ("Tech_Register", "Report_Narrative"),
                 "gates": ("SCORING",), "reports": ("client_research",)},
    "platform": {"tabs": ("Recommendations", "Solution_Catalogue", "Pillar_Rollup"),
                 "gates": ("SCORING",), "reports": ("assessment",)},
}
#: Pages that must be produced before another (the routing table's four
#: ordered pairs, at page grain): techstack before insights (T1 before T2),
#: overview before context (O9 before C4).
PAGE_AFTER = {"insights": ("techstack",), "context": ("overview",)}


def _rows(wb: RunWorkbook, sheet: str) -> int:
    if sheet not in C.SHEETS:
        return 0
    return len([r for r in wb.rows(sheet) if any(str(v or "").strip() for v in r.values())])


def _gate_passed(wb: RunWorkbook, gate: str) -> bool:
    last = None
    for g in wb.rows("Gate_Log"):
        if str(g.get("Gate") or "").strip() == gate:
            last = str(g.get("Verdict") or "").strip().upper()
    return last == "PASS"


def state(wb: RunWorkbook) -> dict:
    from . import narrative as N
    md = wb.metadata()
    reports_ready = {}
    try:
        st = N.state(wb)
        reports_ready = {k: v["ready"] for k, v in st["reports"].items()}
    except Exception as e:                       # noqa: BLE001
        reports_ready = {"_error": str(e)[:200]}
    recmap = {}
    if RECORDING_MAP.is_file():
        for t in json.loads(RECORDING_MAP.read_text()).get("tabs", []):
            if t.get("page"):
                recmap.setdefault(t["page"], []).append(t["tab"])
    pages = {}
    for page in PAGES:
        need = PAGE_NEEDS[page]
        empty = [t for t in need["tabs"] if _rows(wb, t) == 0]
        gates = [g for g in need["gates"] if not _gate_passed(wb, g)]
        reps = [r for r in need.get("reports", ()) if not reports_ready.get(r)]
        after = [p for p in PAGE_AFTER.get(page, ()) if not pages.get(p, {}).get("ready")]
        waiting = ([f"tab {t} empty" for t in empty]
                   + [f"gate {g} not PASS" for g in gates]
                   + [f"report {r} not READY" for r in reps]
                   + [f"page {p} first" for p in after])
        pages[page] = {"ready": not waiting, "waiting_on": waiting,
                       "recording_map_tabs": recmap.get(page, [])}
    ready = [p for p in PAGES if pages[p]["ready"]]
    return {
        "run_id": md.get("run_id"), "stage": C.stage_of(md),
        "scoring_gate": _gate_passed(wb, "SCORING"),
        "reports_ready": reports_ready,
        "pages": pages, "ready_pages": ready,
        "dispatch_now": [f"{p}-surface-producer" for p in ready],
        "then": ("ship each produced page with `ship_page.py <run_id> all "
                 "--sections sections/ --incremental`; promote only when all "
                 "six report PASS — promotion is atomic (invariant 3)"),
        "checkpoint": ("`engine.assemble checkpoint --run <R> --push` after the "
                       "SCORING gate PASSes and again when both reports read "
                       "READY, so the scan ingests a scored run while the "
                       "reports are still being written"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.ship",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("state")
    st.add_argument("--run", required=True); st.add_argument("--root")
    st.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    out = state(run.open())
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"{out['run_id']} — stage {out['stage']}, scoring gate "
              f"{'PASS' if out['scoring_gate'] else 'not passed'}")
        for p in PAGES:
            row = out["pages"][p]
            print(f"  {'READY  ' if row['ready'] else 'WAITING'} {p:10s} "
                  + ("" if row["ready"] else "; ".join(row["waiting_on"])))
        if out["ready_pages"]:
            print(f"\ndispatch now: {', '.join(out['dispatch_now'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
