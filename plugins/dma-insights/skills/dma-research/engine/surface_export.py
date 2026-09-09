#!/usr/bin/env python3
"""Route each app section to how it is produced, and format the ones that are
a matter of formatting rather than synthesis.

WHY THIS EXISTS (owner, 2026-09-05). Two things had to stop happening at the
same time. First, surface production re-SYNTHESISED content the research and
report stages had already written and already challenged — a second author
and a second challenge for a section that was only ever a matter of shape.
Second, nobody could say from the outside WHICH sections those were. The
dual-source map (`section_sources.json`) now records, per app section, its
workbook tab(s), its report section(s), its enrichment source and a
`disposition`; this turns that record into an executable route:

    disposition   route        who writes the section JSON
    ----------    ---------    ---------------------------------------------
    server        server       this script — the envelope only; the app joins
                               the arrangement server-side (H9)
    workbook      convert      a script/producer FORMATS the workbook tab(s)
    report        convert      a script/producer FORMATS a challenged report
                               section — never re-synthesised, never re-challenged
    enrichment    produce      a per-surface producer, after enrichment is
                               registered as evidence
    synthesis     produce      a per-surface producer writes genuinely new
                               client-specific content

`scaffold` is the format half a report agent's script calls: hand it the
section's field values and it assembles the exact payload the MCP resource
requires — universal envelope included — and REFUSES the shape the contract
would refuse, before `ship_page.py` ever spends a submission. It reads the
page contract with no connector (offline, over contracts_data.json).

    python3 -m engine.surface_export plan [--page P] [--json]

`scaffold` / `server_section` / `write_section` are the programmatic half a
report agent's script imports. Nothing here writes to the connector; it shapes
`DIR/<page>.<section>.json` files on disk and `ship_page.py` remains the only
writer.
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
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[3]
REPO = PLUGIN.parent.parent

#: The six app pages (stable; also in dma_mcp.contracts.PAGES). Named here so
#: `plan` — which reads only section_sources.json — works in an engine runtime
#: that does not carry the connector package on its path. The contract itself
#: (get_page_contract) is imported lazily only where scaffolding needs it.
PAGES = ("heatmap", "overview", "insights", "platform", "context", "techstack")


def _get_page_contract(page: str) -> dict:
    """Lazy, so importing this module for `plan` never requires apps/mcp."""
    p = str(REPO / "apps" / "mcp")
    if p not in sys.path:
        sys.path.insert(0, p)
    from dma_mcp.contracts import get_page_contract
    return get_page_contract(page)


_SECTION_SOURCES = (
    PLUGIN / "references" / "section_sources.json",
    REPO / "packages" / "shared" / "section_sources.json",
)

#: disposition -> the route the pipeline takes for it.
ROUTE = {
    "server": "server",        # envelope only; this script writes it
    "workbook": "convert",     # format the workbook tab(s); no re-synthesis
    "report": "convert",       # format a challenged report section; no re-challenge
    "enrichment": "produce",   # a per-surface producer, after enrichment
    "synthesis": "produce",    # a per-surface producer writes it new
}


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_sources() -> dict:
    for p in _SECTION_SOURCES:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise SystemExit("section_sources.json not found — run "
                     "scripts/gen_recording_map.py")


def plan(page: str | None = None) -> dict:
    """Per section: route, disposition, sources, served. The machine-readable
    answer to 'which sections need re-synthesis and which are formatting'."""
    ss = _load_sources()["sections"]
    rows = {}
    for sec, v in ss.items():
        if page and not sec.startswith(f"{page}."):
            continue
        disp = v.get("disposition", "synthesis")
        rows[sec] = {
            "route": ROUTE.get(disp, "produce"),
            "disposition": disp,
            "served": v.get("served", True),
            "required": v.get("required", True),
            "workbook_tabs": v.get("workbook_tabs", []),
            "report_sections": v.get("report_sections", []),
            "enrichment_sources": v.get("enrichment_sources", []),
        }
    convert = sorted(s for s, r in rows.items() if r["route"] == "convert")
    produce = sorted(s for s, r in rows.items() if r["route"] == "produce")
    server = sorted(s for s, r in rows.items() if r["route"] == "server")
    return {
        "sections": rows,
        "convert": convert,       # formatted from workbook/report — no producer
        "produce": produce,       # needs a per-surface producer (+ enrichment)
        "server": server,         # envelope only
        "summary": {"convert": len(convert), "produce": len(produce),
                    "server": len(server)},
    }


def _fields(page: str, section: str) -> dict:
    c = _get_page_contract(page)
    if "error" in c:
        raise KeyError(f"unknown page {page!r}")
    secs = c.get("sections", c)
    if section not in secs:
        raise KeyError(f"{page} has no section {section!r}")
    return secs[section]["fields"]


def scaffold(page: str, section: str, fields: dict | None = None, *,
             e_ids: list[str] | None = None, producer_version: str,
             internal_only: list[str] | None = None,
             empty_state: dict | None = None,
             narrative_thread: str | None = None,
             r_layer: dict | None = None) -> dict:
    """Assemble the exact payload the MCP resource requires for one section —
    the universal envelope plus the caller's field values — and refuse a shape
    the contract would refuse (a missing required field with no empty_state, or
    an unknown field), before a submission is spent.

    This is the 'convert to the format required by the MCP resource' step a
    report agent's script runs; it does NOT invent content — it shapes and
    validates what the caller supplies."""
    spec = _fields(page, section)
    payload: dict = dict(fields or {})
    payload["produced_at"] = payload.get("produced_at") or _utcnow()
    payload["producer_version"] = producer_version
    payload["e_ids"] = list(e_ids or payload.get("e_ids") or [])
    payload["internal_only"] = list(internal_only
                                    if internal_only is not None
                                    else payload.get("internal_only") or [])
    if empty_state is not None:
        payload["empty_state"] = empty_state
    if narrative_thread is not None and "narrative_thread" in spec:
        payload["narrative_thread"] = narrative_thread
    if r_layer is not None and "r_layer" in spec:
        payload["r_layer"] = r_layer

    known = set(spec)
    unknown = [k for k in payload if k not in known]
    if unknown:
        raise ValueError(f"{page}.{section}: unknown field(s) the contract "
                         f"does not declare: {unknown}")
    has_empty = isinstance(payload.get("empty_state"), dict) and \
        payload["empty_state"].get("reason")
    # The contract's structural pass is satisfied by a field being PRESENT and
    # not None (an empty list is a value — internal_only "may be empty, never
    # absent"). Whether a present-but-vacuous content field passes is CG-15's
    # call at submit, not this scaffolder's — over-enforcing here would refuse
    # a valid envelope-only section (H9 ships e_ids: []).
    missing = [f for f, m in spec.items()
               if m.get("required") and f != "empty_state"
               and (f not in payload or payload.get(f) is None)]
    # An explicit, reasoned empty_state stands in for the required CONTENT
    # fields (the envelope is still required); mirror the contract's own rule.
    envelope = {"produced_at", "producer_version", "e_ids", "internal_only"}
    if has_empty:
        missing = [f for f in missing if f in envelope]
    if missing:
        raise ValueError(f"{page}.{section}: required field(s) missing and no "
                         f"empty_state: {missing}")
    return payload


def write_section(out_dir: Path, page: str, section: str, payload: dict) -> Path:
    # The filename is built from page.section, so neither may carry a path
    # component. Both come from the trusted page contract today; the guard
    # keeps a mistaken caller from writing outside out_dir rather than
    # trusting that they never will.
    if page not in PAGES:
        raise ValueError(f"unknown page {page!r}; not one of {PAGES}")
    if not section or any(c in section for c in ("/", "\\")) or ".." in section:
        raise ValueError(f"illegal section name {section!r}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{page}.{section}.json"
    p.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return p


def card_route(card: dict) -> str:
    """How ONE card is produced: connector (the connector writes it at submit,
    the agent must not), else the same routes as a section."""
    if card.get("connector_authored"):
        return "connector"
    return ROUTE.get(card.get("disposition", "synthesis"), "produce")


def cards(section: str | None = None) -> dict:
    """Every card the app renders, per section, with its route and source —
    the card-grain counterpart to `plan`."""
    ss = _load_sources()["sections"]
    out = {}
    for sec, v in ss.items():
        if section and sec != section:
            continue
        for field, card in (v.get("cards") or {}).items():
            out[f"{sec}.{field}"] = {
                "route": card_route(card),
                "kind": card.get("kind"),
                "disposition": card.get("disposition"),
                "item_keys": card.get("item_keys", []),
                "nested": sorted((card.get("nested") or {}).keys()),
                "nested_shape_count": len(card.get("nested_shapes") or []),
                "tab": card.get("tab"),
                "columns": card.get("columns", []),
                "report_sections": card.get("report_sections", []),
                "enrichment_facet": card.get("enrichment_facet"),
                "floor": card.get("floor"),
                "connector_authored": bool(card.get("connector_authored")),
                "computed_never_sent": card.get("computed_never_sent", []),
            }
    return out


def drawers() -> list[dict]:
    """The 15-panel drilldown atlas (drawers, modals, inline expansions)."""
    return _load_sources().get("drilldowns", [])


def scaffold_card(page: str, section: str, field: str, item: dict, *,
                  strict_unknown: bool = True) -> dict:
    """Validate ONE card's item against the contract card's item keys before
    it is assembled into the section payload — reject a key the contract card
    does not declare (a render-derived or invented field). The card-grain
    counterpart to `scaffold`; the section still goes through `scaffold`."""
    sec = f"{page}.{section}"
    card = ((_load_sources()["sections"].get(sec) or {}).get("cards") or {}).get(field)
    if not card:
        raise KeyError(f"{sec} has no card field {field!r}")
    keys = set(card.get("item_keys", []))
    unknown = [k for k in item if k not in keys]
    if unknown and strict_unknown:
        raise ValueError(f"{sec}.{field}: item carries key(s) the contract card "
                         f"does not declare: {unknown}")
    return item


def server_section(page: str, section: str, *, producer_version: str,
                   narrative_thread: str, e_ids: list[str] | None = None,
                   internal_only: list[str] | None = None) -> dict:
    """A `server` section's submission body: the content is `fields: {}` (the
    app joins the arrangement server-side), but the section still rides page
    assembly and carries the page's narrative_thread — H9 is the heatmap
    page-thread holder, so an envelope with no thread fails CG-23. The page
    producer calls this last, once the thread is written from what the page
    actually produced."""
    return scaffold(page, section, {}, e_ids=e_ids,
                    producer_version=producer_version,
                    internal_only=internal_only,
                    narrative_thread=narrative_thread)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.surface_export",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan", help="route every section (convert/produce/server)")
    pl.add_argument("--page", choices=PAGES)
    pl.add_argument("--json", action="store_true")
    cd = sub.add_parser("cards", help="route every CARD, with its source columns")
    cd.add_argument("--section", help="page.section, e.g. overview.findings")
    cd.add_argument("--json", action="store_true")
    dr = sub.add_parser("drawers", help="the 15-panel drilldown atlas")
    dr.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "cards":
        c = cards(a.section)
        if a.json:
            print(json.dumps(c, indent=2))
            return 0
        for key, r in c.items():
            src = (f"{r['tab']}[{len(r['columns'])} cols]" if r["tab"]
                   else ", ".join(r["report_sections"]) or r["enrichment_facet"]
                   or r["disposition"])
            flags = " ⚙connector" if r["connector_authored"] else ""
            flags += f" ⚙computed={r['computed_never_sent']}" if r["computed_never_sent"] else ""
            nested = (f" +nested{r['nested']}" if r["nested"]
                      else f" +{r['nested_shape_count']} sub-cards"
                      if r["nested_shape_count"] else "")
            print(f"  {key:<40} {r['route']:<9} <- {src}{nested}{flags}")
        print(f"  {len(c)} cards")
        return 0

    if a.cmd == "drawers":
        dd = drawers()
        if a.json:
            print(json.dumps(dd, indent=2))
            return 0
        for d in dd:
            p = "PROMPT" if d["has_synthesis_prompt"] else "renders parent"
            print(f"  {d['dd']:<6} {d['name']:<26} {d['shell']:<7} "
                  f"{d['renders_section'] or '—':<28} {p}")
        return 0

    if a.cmd == "plan":
        p = plan(a.page)
        if a.json:
            print(json.dumps(p, indent=2))
            return 0
        print(f"convert (format, no re-synthesis, no re-challenge): "
              f"{p['summary']['convert']}")
        for s in p["convert"]:
            r = p["sections"][s]
            src = r["workbook_tabs"] or r["report_sections"]
            print(f"  {s:<32} {r['disposition']:<9} <- {', '.join(src)}")
        print(f"produce (per-surface producer + enrichment): "
              f"{p['summary']['produce']}")
        for s in p["produce"]:
            r = p["sections"][s]
            print(f"  {s:<32} {r['disposition']}")
        print(f"server (envelope + page thread, written at page assembly): "
              f"{p['summary']['server']}")
        for s in p["server"]:
            print(f"  {s}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
