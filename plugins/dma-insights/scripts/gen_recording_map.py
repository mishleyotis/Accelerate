#!/usr/bin/env python3
"""Generate the recording map: which workbook tab feeds which page section.

## The question this answers

Owner, 2026-09-03: "revise the agents to ensure each knows where to record on
each template while doing the assessment as well as how to submit the
findings concurrently to the mcp while going through the process such that
when the assessment is done, the client page is live on the app."

An assessment agent writes into workbook TABS. The connector accepts page
SECTIONS. Nothing in the repo joined those two vocabularies, so an agent
filling `Entity_Timeline` had no way to know it was the only input to
`context.timeline`, and no way to know that finishing it made a page
submittable. The join existed only in people's heads, which is why ingestion
was an afterthought: you cannot submit as you go if you cannot tell what
"done" means for any one page.

Both halves are already declared in code:

    _TAB_TARGET          tab   -> the surface it feeds   (worker parser)
    get_page_contract    page  -> its sections, and which are required

This walks both and writes the join. GENERATED, never hand-edited: a
hand-written map is one refactor away from being confidently wrong, and this
one is checked in precisely so agents can read it without a connector call.

    gen_recording_map.py [--out references/tab_recording_map.json]

Run it after any change to `_TAB_TARGET` or a page contract; the file it
writes is the one the skill points agents at.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "apps" / "worker"))

from dma_worker.workbook_parser import _TAB_TARGET          # noqa: E402

PAGES = ("heatmap", "overview", "insights", "platform", "context", "techstack")


def contract(page: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"page": page}, fh)
        path = fh.name
    try:
        r = subprocess.run(
            [sys.executable, str(HERE / "mcp_raw.py"), "call",
             "get_page_contract", "--args-file", path],
            capture_output=True, text=True, timeout=300)
        return json.loads(r.stdout)
    finally:
        os.unlink(path)


def _surface(v) -> str:
    return str(v[0] if isinstance(v, (tuple, list)) else v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path,
                    default=REPO / "plugins" / "dma-insights" / "references"
                    / "tab_recording_map.json")
    a = ap.parse_args(argv)

    pages = {}
    for p in PAGES:
        secs = contract(p).get("sections") or {}
        if not secs:
            print(f"{p}: contract unreadable — refusing to write a partial map")
            return 1
        pages[p] = {n: bool(m.get("required", True)) if isinstance(m, dict) else True
                    for n, m in secs.items()}

    # `_TAB_TARGET[tab]` is `(surface, confidence)` — confidence being
    # `verified` where the mapping was checked field-by-field against
    # `get_page_contract`, `proposed` where it was read off the tab's shape.
    # Carrying that through matters: an agent should know which bindings are
    # a promise and which are a reading.
    rows = []
    for tab, val in sorted(_TAB_TARGET.items()):
        surface = _surface(val)
        confidence = (val[1] if isinstance(val, (tuple, list)) and len(val) > 1
                      else "unstated")
        page = section = None

        # The dotted form names both: "techstack.techstack.items",
        # "platform.recommendations.recommendations".
        m = re.match(r"([a-z_]+)\.([a-z_]+)", surface)
        if m and m.group(1) in pages and m.group(2) in pages[m.group(1)]:
            page, section = m.group(1), m.group(2)
        else:
            # The prose form names the page only: "context", "heatmap cells",
            # "insights (H1 focus areas)". Bind the page; leave the section
            # null rather than guess, and keep the prose as the hint it is.
            for cand in pages:
                if re.match(rf"{re.escape(cand)}\b", surface):
                    page = cand
                    break

        rows.append({"tab": tab, "records": surface, "confidence": confidence,
                     "page": page, "section": section,
                     "required": (pages[page][section]
                                  if page and section else None)})

    # section -> the tabs that feed it, so an agent can see what "done" needs
    by_section: dict[str, dict] = {}
    for page, secs in pages.items():
        for sec, req in secs.items():
            by_section[f"{page}.{sec}"] = {
                "required": req,
                "fed_by_tabs": sorted(r["tab"] for r in rows
                                      if r["page"] == page and r["section"] == sec),
            }

    doc = {
        "_readme": [
            "GENERATED by scripts/gen_recording_map.py — do not hand-edit.",
            "",
            "Two vocabularies joined: the workbook TABS an assessment agent",
            "writes into, and the page SECTIONS the connector accepts. The",
            "join is what makes concurrent submission possible — a page whose",
            "required sections all have their tabs filled is submittable NOW,",
            "without waiting for the rest of the assessment.",
            "",
            "`records` is the worker parser's own note of what the tab feeds,",
            "and `confidence` is its own assessment of that note: `verified`",
            "was checked field-by-field against get_page_contract,",
            "`proposed` was read off the tab's shape, and",
            "`not_client_facing` feeds run config or provenance rather than",
            "any page. Read a `proposed` binding as a good guess about where",
            "your work lands, not a promise.",
            "A row with page: null is a tab the app reads for run config or",
            "provenance rather than for one page's section.",
            "",
            "Ship with: ship_page.py <run> all --sections DIR --incremental",
            "which asks the connector which sections a page requires and",
            "submits every page that has them.",
        ],
        "tabs": rows,
        "sections": by_section,
        "counts": {
            "tabs_the_app_reads": len(rows),
            "tabs_bound_to_a_page": sum(1 for r in rows if r["page"]),
            "tabs_bound_to_a_section": sum(1 for r in rows if r["section"]),
            "verified_bindings": sum(1 for r in rows
                                     if r["confidence"] == "verified"),
            "proposed_bindings": sum(1 for r in rows
                                     if r["confidence"] == "proposed"),
            # Run config, provenance and gate logs: read by the app, but
            # feeding no client surface, so they have no page section to
            # bind to and their absence from the table is not a gap.
            "not_client_facing": sum(1 for r in rows
                                     if r["confidence"] == "not_client_facing"),
            "page_sections": len(by_section),
            "required_page_sections": sum(1 for v in by_section.values()
                                          if v["required"]),
        },
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    c = doc["counts"]
    print(f"wrote {a.out}")
    print(f"  {c['tabs_the_app_reads']} tabs the app reads — "
          f"{c['tabs_bound_to_a_page']} bound to a page, "
          f"{c['tabs_bound_to_a_section']} to a named section, "
          f"{c['verified_bindings']} verified")
    print(f"  {c['page_sections']} page sections, "
          f"{c['required_page_sections']} required")
    unbound = [r["tab"] for r in rows if not r["page"]]
    if unbound:
        print(f"  run-config / provenance tabs (no single page): "
              f"{', '.join(unbound[:10])}"
              + (f" +{len(unbound) - 10}" if len(unbound) > 10 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
