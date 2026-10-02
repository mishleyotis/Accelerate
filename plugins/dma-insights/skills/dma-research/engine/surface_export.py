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


# ── declared absences, projected — never written by hand ─────────────────
#
# Measured 28-09-2026 (QA audit F-CG15-016) on a staged heatmap: 61 of the
# first 102 cells were absences, carrying 34 distinct ladders (the largest
# shared by 5 cells) and 119 eight-word spans shared by three or more
# syntheses — "Within Governance & Risk Appetite, the evidenced cells" 22
# times. The 65 CG-15 refusals were earned: a producer writing 61 absences
# by hand wrote one absence 61 times. The record of each absence already
# exists, per cell, in the run — the Search_Log rows, the ladder the lane
# established, what it hunted, the proxy class it climbed, the artefact the
# catalogue says would settle it — and a deterministic projection of that
# record is per-cell exactly as far as the record is. Where two records are
# the same sentence with the cell id swapped, the projector OMITS both and
# says so, because the rulebook's own preference order puts "omitted" above
# "declared-and-identical" and the gate would refuse them anyway.

ABSENCES_NAME = "heatmap.cell_evidence.absences.json"


def _hunted_of(row: dict, dossier: dict | None) -> str:
    if dossier and dossier.get("hunted"):
        return str(dossier["hunted"]).strip()
    import re as _re
    m = _re.search(r"Searched and not found: (.*?)\. Volleys fired:",
                   str(row.get("What_We_Found") or ""), _re.S)
    return (m.group(1).strip() if m else
            str(row.get("Dominant_Claim") or "").split(";", 1)[-1].strip())


def _rung_lines(row: dict, searches: list[dict]) -> list[str]:
    """The ladder rungs first (rung name, tool, quoted query), then every
    other logged volley for the cell. Each line names a tool and quotes the
    query, which is what a reader could re-run."""
    try:
        ladder = json.loads(str(row.get("Negative_Ladder") or "[]"))
    except ValueError:
        ladder = []
    by_q = {}
    for s in searches:
        by_q.setdefault(" ".join(str(s.get("Query") or "").split()).lower(), s)
    out, seen = [], set()
    for r in ladder if isinstance(ladder, list) else []:
        q = str((r or {}).get("query") or "").strip()
        rung = str((r or {}).get("rung") or "").strip()
        if not q:
            continue
        s = by_q.get(" ".join(q.split()).lower(), {})
        tool = str(s.get("Tool") or "").strip() or "web_search"
        out.append(f"{rung} rung via {tool}, searched for: \"{q}\" — "
                   f"{s.get('Hits', 0) or 0} hits, {s.get('Kept', 0) or 0} kept")
        seen.add(" ".join(q.split()).lower())
    for s in searches:
        q = str(s.get("Query") or "").strip()
        key = " ".join(q.split()).lower()
        if not q or key in seen:
            continue
        seen.add(key)
        out.append(f"{s.get('Facet') or 'volley'} via {s.get('Tool') or 'web_search'}, "
                   f"searched for: \"{q}\" — {s.get('Hits', 0) or 0} hits, "
                   f"{s.get('Kept', 0) or 0} kept")
    return out


def _template_groups(texts: dict[str, str]) -> tuple[list[list[str]], str]:
    """Cells whose projected syntheses would be refused together as a
    template. The connector's own CG-15 when it is on the path (one
    owner); a local mirror of its two-term rule when it is not — and the
    answer says which."""
    keys = sorted(texts)
    try:
        p = str(REPO / "apps" / "mcp")
        if p not in sys.path:
            sys.path.insert(0, p)
        from dma_mcp import vacuity as V
        groups = V._check_templates("cell_evidence", {("synthesis", 0): [
            (k, texts[k]) for k in keys]}, declared=None)
        comps: dict[str, set] = {}
        import re as _re
        for r in groups:
            m = _re.search(r"The group is (.+?)(?:, …)?\. A per-item", r["message"])
            if not m:
                continue
            members = tuple(sorted(x.strip() for x in m.group(1).split(",")))
            comps.setdefault(members, set()).add(r["path"])
        out = sorted({tuple(sorted(v)) for v in comps.values()})
        return [list(g) for g in out], "dma_mcp.vacuity"
    except Exception:                                # noqa: BLE001
        pass
    import re as _re
    word = _re.compile(r"[a-z0-9$£€%./-]+")
    stop = set("a an and are as at be by for from has have in is it its of on or that the this to was with".split())

    def toks(t):
        return [w.strip(".-/") for w in word.findall(t.lower()) if w.strip(".-/")]

    def shingles(t, n=8):
        tk = toks(t)
        return {tuple(tk[i:i + n]) for i in range(len(tk) - n + 1)}

    def claim(t):
        return {w for w in toks(t) if w not in stop and not _re.match(r"^p\dc\d", w)
                and not _re.match(r"^\d", w)}

    def ov(a, b):
        return len(a & b) / min(len(a), len(b)) if a and b else 0.0
    sh = {k: shingles(texts[k]) for k in keys}
    cw = {k: claim(texts[k]) for k in keys}
    adj = {k: set() for k in keys}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            c = ov(cw[a], cw[b])
            measurable = min(len(cw[a]), len(cw[b])) >= 6
            if (measurable and c >= 0.50) or (ov(sh[a], sh[b]) >= 0.40
                                              and (not measurable or c >= 0.40)):
                adj[a].add(b)
                adj[b].add(a)
    seen, groups = set(), []
    for k in keys:
        if k in seen or not adj[k]:
            continue
        stack, comp = [k], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.append(x)
            stack.extend(adj[x] - seen)
        if len(comp) >= 3:
            groups.append(sorted(comp))
    return groups, "local mirror of CG-15 (8-gram 0.40 ∧ claim 0.40, or claim 0.50)"


def absence_rows(wb, *, run=None) -> dict:
    """Every DECLARED absence in the run, as an H2 `cells[]` row."""
    from . import contract as C
    from . import ledger as L
    declared = sorted(L.declared_absences(wb))
    dossiers = L.read_gap_dossiers(run) if run is not None else {}
    names = C.subcap_names()
    settles = C.settling_artefacts()
    proxies = C.proxy_classes()
    searches = wb.rows("Search_Log")
    prov = {}
    for r in wb.rows("Provenance"):
        if str(r.get("Step") or "") == "absence":
            prov[str(r.get("SubCap_ID") or "").strip()] = r
    cells, texts = {}, {}
    for cell in declared:
        row = wb.scoring_row(cell) or {}
        mine = [s for s in searches if str(s.get("SubCap_ID") or "").strip() == cell]
        d = dossiers.get(cell)
        name = names.get(cell) or cell
        hunted = _hunted_of(row, d)
        proxy_log = str(row.get("Proxy_Log") or "").strip()
        artefact = settles.get(cell)
        inferable = (d or {}).get("inferable") or None
        rigour = (d or {}).get("rigour") or ("REDUCED" if "REDUCED RIGOUR" in
                                              str(row.get("Triangulation") or "") else "FULL")
        parts = [f"{name}: {hunted.rstrip('.')}."]
        if proxy_log:
            parts.append(f"On the {proxies.get(cell) or 'proxy'} rung, {proxy_log.rstrip('.')}.")
        if inferable:
            parts.append(f"INFERENCE — {str(inferable['claim']).rstrip('.')}; "
                         f"to validate: {inferable['validation_question']}")
        elif (d or {}).get("not_determinable"):
            parts.append(f"Not determinable from public sources: "
                         f"{str(d['not_determinable']).rstrip('.')}.")
        synthesis = " ".join(parts)
        closure = (inferable["validation_question"] if inferable else
                   (f"An internal artefact would settle it: {artefact.rstrip('.')}."
                    if artefact else "An internal artefact from the client would settle it."))
        p = prov.get(cell, {})
        cells[cell] = {
            "subcap_id": cell, "e_ids": [], "items": [],
            "reach_note": (f"declared absence at {rigour} rigour — {len(mine)} logged "
                           f"searches, volleys "
                           + ", ".join(f"{f} x{n}" for f, n in
                                       ((d or {}).get("facets_status") and
                                        [(f, v['fired']) for f, v in d['facets_status'].items()]
                                        or [])) if d else
                           f"declared absence at {rigour} rigour — {len(mine)} logged searches"),
            "synthesis": synthesis, "grounded_on": 0,
            "provenance": {"grade": "declared", "actor": str(p.get("Actor") or ""),
                           "at": str(p.get("At") or ""), "projected_by":
                           "engine.surface_export absence"},
            "thin": True,
            "sources_searched": _rung_lines(row, mine),
            "closure_condition": closure,
        }
        texts[cell] = synthesis
    groups, checker = _template_groups(texts)
    omitted = []
    for g in groups:
        for cell in g:
            cells.pop(cell, None)
            omitted.append({"subcap_id": cell, "group": g,
                            "reason": ("the lane's hunted/proxy text for these cells "
                                       "is one sentence with the cell name substituted; "
                                       "a projection of it would be refused by CG-15 and "
                                       "the rulebook ranks omitted above declared-and-"
                                       "identical. Re-declare each with what THIS cell's "
                                       "artefact is and where it was looked for")})
    return {"cells": [cells[c] for c in sorted(cells)],
            "declared": len(declared), "projected": len(cells),
            "omitted_identical": omitted, "checker": checker,
            "produced_at": _utcnow(), "producer": "engine.surface_export absence"}


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
    ab = sub.add_parser("absence", help="project every DECLARED absence into "
                                        "H2 cells[] rows from the run's own record")
    ab.add_argument("--run", required=True)
    ab.add_argument("--root")
    ab.add_argument("--out", help=f"write {ABSENCES_NAME} into this directory")
    ab.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "absence":
        from . import runstate
        run = runstate.locate(a.run, Path(a.root) if a.root else None)
        out = absence_rows(run.open(), run=run)
        if a.out:
            p = Path(a.out) / ABSENCES_NAME
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(out, indent=2), encoding="utf-8")
            out["path"] = str(p)
        if a.json or not a.out:
            print(json.dumps(out, indent=2))
        else:
            print(f"{out['path']}: {out['projected']} of {out['declared']} declared "
                  f"absences projected, {len(out['omitted_identical'])} omitted as "
                  f"identical ({out['checker']})")
        return 0 if not out["omitted_identical"] else 3

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
