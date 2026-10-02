#!/usr/bin/env python3
"""The heatmap's evidence surfaces, built from the workbook AS research runs.

WHY (J-14, measured 2026-10-01 on a multi-LOB HYBRID run). `heatmap.evidence`
and `heatmap.cell_evidence` are routed `convert` — "format, no re-synthesis"
(section_sources.json) — yet nothing formatted them. They were written by LLM
page producers at PAGES_A, after SCORING, INGEST_A and REPORTS: hours after the
last research write, and as a re-transcription of ~760 cells and ~430 evidence
rows that research had already linked both ways. So the linkage the research
built was never rendered, never checked against the page contract while it was
being built, and finally copied by hand into JSON, where a dropped id is a
broken drawer.

This module is the format step as code. It runs at any time — the driver calls
it at every research handoff — and writes:

  sections/heatmap.evidence.json          the full index, contract-validated
                                          (surface_export.scaffold refuses a
                                          shape the connector would refuse)
  sections/heatmap.cell_evidence.skeleton.json
                                          every cell's deterministic fields —
                                          items, e_ids, grounded_on, thin, and
                                          for a declared absence the
                                          sources_searched/closure_condition
                                          pair — with `synthesis` null: the one
                                          field that needs the score and the
                                          peer median, so the page producer
                                          writes prose and copies nothing
  07_qa/heatmap_live.json                 the linkage census per category

    python3 -m engine.heatmap_live build --run R --root ROOT [--json]
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
from pathlib import Path

from . import contract as C
from . import floors_gate, runstate, surface_export
from .ledger import EXCERPT_MAX, EXCERPT_MIN, placeholder_date
from .workbook import _split_ids

PRODUCER = "engine.heatmap_live@2026-10-01"
SECTIONS_DIR = "sections"
SKELETON = "heatmap.cell_evidence.skeleton.json"
CENSUS = "heatmap_live.json"
#: Fewer linked items than this and the cell is thin (cell_evidence contract:
#: "Below three linked items, mark the cell thin").
THIN_BELOW = 3
#: Paths the customer audience never sees: the tier and the minting actor are
#: internal-shaped (exclusion-boundary rules); the served reference keys omit
#: both.
EVIDENCE_INTERNAL = ["evidence[*].tier", "evidence[*].discovered_by"]


def _cells_of(ev: dict) -> list[str]:
    return [i.strip().split(":")[0] for i in _split_ids(ev.get("SubCap_IDs")) if i.strip()]


def _eids_of(row: dict) -> list[str]:
    return [i.split(":")[0] for i in _split_ids(row.get("Evidence_IDs"))
            if i and i != C.NO_EVIDENCE]


def evidence_section(wb) -> dict:
    """heatmap.evidence from Evidence_Detail, one item per registered row."""
    items = []
    for eid, ev in sorted(wb.evidence_index().items(),
                          key=lambda kv: int(kv[0].split("-")[-1])
                          if kv[0].split("-")[-1].isdigit() else 0):
        items.append({
            "e_id": eid,
            "source_name": str(ev.get("Source_Name") or "") or None,
            "url": str(ev.get("Source_URL") or "") or None,
            "excerpt": str(ev.get("Excerpt") or ""),
            "claim_type": str(ev.get("Claim_Type") or "") or None,
            "tier": str(ev.get("Tier") or "") or None,
            # Stored as written (a month, quarter or year IS a date — the app
            # resolves it); empty stays null, never a sentinel (invariant 9).
            "published_date": str(ev.get("Date_Published") or "") or None,
            "discovered_by": "claude-code",
            "supports_subcap_ids": _cells_of(ev),
            "surfaces": ["H2", "H6"] if _cells_of(ev) else ["H6"],
        })
    return surface_export.scaffold(
        "heatmap", "evidence", {"evidence": items},
        e_ids=[i["e_id"] for i in items], producer_version=PRODUCER,
        internal_only=list(EVIDENCE_INTERNAL))


def cell_evidence_skeleton(wb) -> dict:
    """Every scoring row's deterministic cell_evidence fields; synthesis null."""
    register = wb.evidence_index()
    searches: dict[str, list[str]] = {}
    for s in wb.rows("Search_Log"):
        cell = str(s.get("SubCap_ID") or "").strip()
        q = str(s.get("Query") or "").strip()
        if cell and q:
            line = f"{s.get('Tool') or 'web_search'}: {q}"[:160]
            if line not in searches.setdefault(cell, []):
                searches[cell].append(line)
    cells, linked = [], 0
    for r in wb.scoring_rows():
        cell = str(r.get("SubCap_ID") or "").strip()
        if not cell:
            continue
        eids = _eids_of(r)
        items = []
        for e in eids:
            ev = register.get(e)
            if not ev or cell not in _cells_of(ev):
                continue                     # one-way: the census reports it
            items.append({"e_id": e, "tier": ev.get("Tier"),
                          "claim_label": ev.get("Claim_Type"),
                          "recency": ev.get("Recency"),
                          "source_title": ev.get("Source_Name"),
                          "publisher": ev.get("Source_Name"),
                          "excerpt": ev.get("Excerpt")})
        linked += bool(items)
        absent = str(r.get("Absence_Claimed") or "").upper() in ("YES", "TRUE", "1")
        row = {"subcap_id": cell, "e_ids": [i["e_id"] for i in items],
               "items": items, "grounded_on": len(items),
               "thin": len(items) < THIN_BELOW, "synthesis": None,
               "reach_note": (f"{len(items)} linked item(s)" if items else
                              "no evidence reached this cell")}
        if absent and not items:
            # The TRD's absence trio: thin, sources_searched, closure_condition.
            row["sources_searched"] = searches.get(cell, [])[:8]
            row["closure_condition"] = (str(r.get("Discovery_Questions") or "").strip()
                                        or None)
        cells.append(row)
    return {"cells": cells,
            "linking_stats": {"cells_scored": len(cells), "cells_linked": linked,
                              "rows_unlinkable": sum(1 for ev in register.values()
                                                     if not _cells_of(ev))},
            "synthesis_owed": sum(1 for c in cells if c["items"])}


def census(wb) -> dict:
    """Per category: cells, two-way linked, thin, declared absent, open, and
    the linkage defects the contract would refuse at PAGES_A."""
    register = wb.evidence_index()
    out: dict[str, dict] = {}
    for r in wb.scoring_rows():
        cell = str(r.get("SubCap_ID") or "").strip()
        if not cell:
            continue
        c = out.setdefault(cell.split(".")[0], {
            "cells": 0, "linked": 0, "thin": 0, "absent": 0, "open": 0,
            "one_way": 0, "unresolved": 0})
        c["cells"] += 1
        eids = _eids_of(r)
        two_way = [e for e in eids if e in register and cell in _cells_of(register[e])]
        c["unresolved"] += sum(1 for e in eids if e not in register)
        c["one_way"] += sum(1 for e in eids if e in register and e not in two_way)
        if floors_gate.cell_evidenced(cell, eids, register):
            c["linked"] += 1
            c["thin"] += len(two_way) < THIN_BELOW
        elif str(r.get("Absence_Claimed") or "").upper() in ("YES", "TRUE", "1"):
            c["absent"] += 1
        elif not str(r.get("Dominant_Claim") or "").strip():
            c["open"] += 1
    rows = list(register.values())
    tot = {k: sum(v[k] for v in out.values())
           for k in ("cells", "linked", "thin", "absent", "open", "one_way", "unresolved")}
    tot.update({
        "evidence_rows": len(rows),
        "excerpt_out_of_range": sum(1 for e in rows if not (
            EXCERPT_MIN <= len(str(e.get("Excerpt") or "").strip()) <= EXCERPT_MAX)),
        "undated": sum(1 for e in rows if not str(e.get("Date_Published") or "").strip()),
        "date_placeholder": sum(1 for e in rows if str(e.get("Origin") or "public") == "public"
                                and placeholder_date(e.get("Date_Published"),
                                                     e.get("Retrieved_At"),
                                                     e.get("Excerpt"),
                                                     e.get("Anchor_Quote"))),
    })
    return {"by_category": out, "total": tot}


def build(run) -> dict:
    wb = run.open()
    sec_dir = run.root / SECTIONS_DIR
    sec_dir.mkdir(parents=True, exist_ok=True)
    problems = []
    try:
        p = surface_export.write_section(sec_dir, "heatmap", "evidence",
                                         evidence_section(wb))
        ev_file = str(p)
    except ValueError as e:                  # the contract refused the shape
        ev_file, problems = None, [f"heatmap.evidence: {e}"]
    sk = cell_evidence_skeleton(wb)
    (sec_dir / SKELETON).write_text(json.dumps(sk, indent=1) + "\n", encoding="utf-8")
    cen = census(wb)
    out = {"run_id": run.run_id, "evidence_section": ev_file,
           "skeleton": str(sec_dir / SKELETON), "problems": problems,
           "linking_stats": sk["linking_stats"], "synthesis_owed": sk["synthesis_owed"],
           **cen}
    run.qa_dir.mkdir(parents=True, exist_ok=True)
    (run.qa_dir / CENSUS).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def summary_line(out: dict) -> str:
    t = out["total"]
    return (f"{t['linked']}/{t['cells']} cells linked both ways ({t['thin']} thin), "
            f"{t['absent']} declared absent, {t['open']} open; {t['evidence_rows']} "
            f"evidence rows ({t['undated']} undated, {t['date_placeholder']} placeholder-dated, "
            f"{t['excerpt_out_of_range']} excerpt out of range); {t['one_way']} one-way, "
            f"{t['unresolved']} unresolved citation(s)"
            + (f"; CONTRACT: {'; '.join(out['problems'])}" if out["problems"] else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.heatmap_live",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--run", required=True)
    b.add_argument("--root", required=True)
    b.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = build(runstate.locate(a.run, Path(a.root)))
    print(json.dumps(out, indent=1) if a.json else summary_line(out))
    return 1 if out["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
