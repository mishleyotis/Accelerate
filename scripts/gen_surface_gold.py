#!/usr/bin/env python3
"""Cut the shape-only gold for the six app pages: fixtures/surface_gold.json.

WHY (RC-01, SWBC gold audit 2026-10-04). Producers were told to match "the
gold standard", and for the six app pages no measurable gold existed: the one
gold doc covered the workbook and the two reports, the rulebook's "positive
pattern" was prose, `fixtures/reference_surface_keys.json` held key names
only, and `fixtures/parity/` held a four-section placeholder. Nothing carried
per-section row counts, a stated-value share or a per-audience disposition,
so "in line with gold" could not be checked by anyone — and the run that
prompted the audit fell short of a target that did not exist.

WHAT IT WRITES. For each gold run, every page reduced by
`dma_mcp.parity.page_shape`: keys, list lengths and per-row null patterns —
NO values, no names (owner decision 2026-10-04: shape-only gold fixtures may
be committed). Beside them:

  dispositions  per page.section x audience — served / withheld /
                never_served / page_withheld — generated from
                apps/api/dma_api/redaction.py, so it cannot disagree with what
                the API actually does (a test re-derives and compares);
  summary       per page.section — which gold runs fill it, and per list the
                min/max row count and min stated-value share across them: the
                numbers GOLD-STANDARD-APP-PAGES.md quotes.

It writes the same bytes to apps/mcp/dma_mcp/surface_gold.json, the copy the
connector's promote path reads (CG-PAR) — `scripts/` and `fixtures/` are not
in the connector's image. A test asserts the two are identical.

INPUT is staged payloads, one directory per gold run holding <page>.json as
`scripts/fetch_staged_fixtures.py` reassembles them (gitignored: they are
client content). Regenerating needs connector credentials; the committed
output is the record of the gold at the time it was cut.

    python3 scripts/fetch_staged_fixtures.py 40971653-aa3e-4373-9163-a967c57a9305 --slug gold-40971653
    python3 scripts/fetch_staged_fixtures.py c1351d25-a612-4dbe-b498-127bccaf6810 --slug gold-c1351d25
    python3 scripts/fetch_staged_fixtures.py d7ed1d90-d406-4e8e-9ab0-75f91a0c15bb --slug gold-d7ed1d90
    python3 scripts/gen_surface_gold.py \\
        gold-40971653:CU=fixtures/staged_runs/gold-40971653 \\
        gold-c1351d25:CU=fixtures/staged_runs/gold-c1351d25 \\
        gold-d7ed1d90:CU=fixtures/staged_runs/gold-d7ed1d90

EVERY GOLD RUN CARRIES ITS SUB-VERTICAL (owner decision B, 2026-10-04).
CG-PAR prefers gold of the target's sub-vertical and falls back to the
other gold for structure only, so a gold run without one cannot be placed:
`LABEL:SV=DIR` names it (or GOLD_META below already does), and the script
refuses a run whose sub-vertical is missing or not a catalogue code.

`--dispositions-only` rewrites the dispositions from redaction.py and keeps
the committed shapes — the regeneration a redaction change needs, with no
client content and no credentials.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_mcp import parity  # noqa: E402

PAGES = ("overview", "heatmap", "insights", "platform", "context", "techstack")
OUT = ROOT / "fixtures" / "surface_gold.json"
MCP_COPY = ROOT / "apps" / "mcp" / "dma_mcp" / "surface_gold.json"

#: What each gold run is. Run ids are the promoted gold the owner named
#: (Golden 1 40971653, Baxter c1351d25, Logix d7ed1d90). The sub-vertical is
#: the entity's binding as get_platform_fit reports it (all three CU,
#: measured 2026-10-04) — CG-PAR's sub-vertical tier and its leave-one-out
#: read `sub_vertical` and `run_id_prefix` from here.
GOLD_META = {
    "gold-40971653": {"run_id_prefix": "40971653", "sub_vertical": "CU"},
    "gold-c1351d25": {"run_id_prefix": "c1351d25", "sub_vertical": "CU"},
    "gold-d7ed1d90": {"run_id_prefix": "d7ed1d90", "sub_vertical": "CU"},
}


def dispositions(section_keys) -> dict:
    """page.section -> {internal, customer}, from redaction.py's own sets.

    `reduced` is a section the customer receives through a projection
    (redaction.CUSTOMER_PROJECTIONS) — owner decision 1's sentiment card:
    bars and themes, no cell codes, internal sources, cap vocabulary or
    r_layer. Served, but not the internal record."""
    from dma_api import redaction as R
    projected = set(getattr(R, "CUSTOMER_PROJECTIONS", {}) or {})
    out = {}
    for key in sorted(section_keys):
        page, _, name = key.partition(".")
        ps = (page, name)
        if ps in R.NEVER_SERVED:
            out[key] = {"internal": "never_served", "customer": "never_served"}
            continue
        if page in R.CUSTOMER_WITHHELD_PAGES:
            cust = "page_withheld"
        elif ps in R.CUSTOMER_WITHHELD:
            cust = "withheld"
        elif ps in projected:
            cust = "reduced"
        else:
            cust = "served"
        out[key] = {"internal": "served", "customer": cust}
    return out


def _lists(node, prefix=""):
    """Every list node in a shape, by dotted path."""
    if not isinstance(node, dict):
        return
    if "o" in node:
        for k, v in node["o"].items():
            yield from _lists(v, f"{prefix}{k}" if not prefix else f"{prefix}.{k}")
        return
    if "n" in node:
        yield prefix, node
        for k, v in (node.get("nested") or {}).items():
            yield from _lists(v, f"{prefix}[].{k}")


def summary(runs: dict) -> dict:
    out = {}
    for label, pages in sorted(runs.items()):
        for page, shp in pages.items():
            for name, sec in shp["sections"].items():
                if not parity.node_filled(sec.get("data")):
                    continue
                slot = out.setdefault(f"{page}.{name}",
                                      {"filled_by": [], "lists": {}})
                slot["filled_by"].append(label)
                for path, node in _lists(sec["data"]):
                    lst = slot["lists"].setdefault(path, {"n": {}})
                    lst["n"][label] = node.get("n", 0)
                    st = parity._stated(node)
                    if st is not None:
                        lst.setdefault("stated_share", {})[label] = round(st, 3)
    for slot in out.values():
        for lst in slot["lists"].values():
            ns = list(lst["n"].values())
            lst["min_n"], lst["max_n"] = min(ns), max(ns)
            if "stated_share" in lst:
                lst["min_stated_share"] = min(lst["stated_share"].values())
    return dict(sorted(out.items()))


def contract_sections() -> set:
    """Every page.section today's contract declares — the disposition table
    covers all of them, not only the ones a gold run happened to fill."""
    from dma_mcp.contracts import PAGES as CPAGES, sections
    return {f"{p}.{s}" for p in CPAGES for s in sections(p)}


def build(runs: dict, meta: dict | None = None) -> dict:
    keys = contract_sections() | {
        f"{p}.{s}" for pages in runs.values() for p, shp in pages.items()
        for s in shp["sections"]}
    return {
        "_doc": ("Shape-only gold for the six app pages (RC-01). Keys, list "
                 "lengths and per-row null patterns of the promoted gold "
                 "runs — no values, no names. GENERATED by "
                 "scripts/gen_surface_gold.py; never edit. Read by "
                 "scripts/gate_j_surface_parity.py --gold and by the "
                 "connector's promote path (CG-PAR) through its byte-"
                 "identical copy apps/mcp/dma_mcp/surface_gold.json. "
                 "plugins/dma-insights/docs/GOLD-STANDARD.md quotes it. "
                 "Owner decision B (2026-10-04): only structural gaps "
                 "block; counts and fill ratios against these shapes are "
                 "warnings; a gold run is compared leave-one-out, and gold "
                 "of the target's sub-vertical (runs.*.sub_vertical) is "
                 "preferred."),
        "shape_version": parity.SHAPE_VERSION,
        # Owner decision B (2026-10-04): the floors measure WARNINGS only.
        "floors": {"list": parity.LIST_FLOOR, "item": parity.ITEM_FLOOR,
                   "blocking": False},
        "dispositions": dispositions(keys),
        "summary": summary(runs),
        "runs": {label: {**GOLD_META.get(label, {}),
                         **(meta or {}).get(label, {}),
                         "pages": _strip_target_only(pages)}
                 for label, pages in sorted(runs.items())},
    }


def _strip_target_only(pages: dict) -> dict:
    """`named` (the keys a TARGET's empty_state names) is read off the run
    being checked, never off the gold; it is not part of the gold shape."""
    for shp in pages.values():
        for sec in (shp.get("sections") or {}).values():
            sec.pop("named", None)
    return pages


def check_meta(runs: dict, meta: dict) -> list:
    """Every gold run records a catalogue sub-vertical code."""
    bad = []
    for label in sorted(runs):
        sv = {**GOLD_META.get(label, {}), **meta.get(label, {})}.get(
            "sub_vertical")
        if sv not in parity.SUB_VERTICALS:
            bad.append(f"{label}: sub_vertical {sv!r}")
    return bad


def write(doc: dict) -> None:
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    OUT.write_text(text)
    MCP_COPY.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)} and {MCP_COPY.relative_to(ROOT)} "
          f"({len(text):,} bytes, {len(doc['runs'])} gold run(s))")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*",
                    help="LABEL[:SUB_VERTICAL]=DIR of staged <page>.json")
    ap.add_argument("--dispositions-only", action="store_true")
    a = ap.parse_args()
    if a.dispositions_only:
        doc = json.loads(OUT.read_text())
        runs = {lb: r["pages"] for lb, r in doc["runs"].items()}
        meta = {lb: {k: v for k, v in r.items() if k != "pages"}
                for lb, r in doc["runs"].items()}
        bad = check_meta(runs, meta)
        if bad:
            print("every gold run needs its sub-vertical: " + "; ".join(bad),
                  file=sys.stderr)
            return 1
        write(build(runs, meta))
        return 0
    if not a.runs:
        ap.error("name at least one LABEL=DIR, or --dispositions-only")
    runs, meta = {}, {}
    for spec in a.runs:
        label, _, d = spec.partition("=")
        label, _, sv = label.partition(":")
        if sv:
            meta[label] = {"sub_vertical": sv}
        pages = {}
        for page in PAGES:
            p = Path(d) / f"{page}.json"
            if not p.exists():
                print(f"  {label}: {page}.json missing — the gold must be "
                      "whole; fetch it first", file=sys.stderr)
                return 1
            pages[page] = parity.page_shape(json.loads(p.read_text()))
        runs[label] = pages
    bad = check_meta(runs, meta)
    if bad:
        print("every gold run needs its sub-vertical (LABEL:SV=DIR): "
              + "; ".join(bad), file=sys.stderr)
        return 1
    write(build(runs, meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
