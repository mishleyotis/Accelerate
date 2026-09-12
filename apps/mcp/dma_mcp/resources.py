"""The schemas an agent fills, as first-class MCP RESOURCES.

Until now every schema the connector serves was reachable only by CALLING a
read tool (`get_page_contract`, and the rest). The owner asked (2026-09-05)
for the gold-standard schemas to be availed AS RESOURCES too, so a producer
can enumerate them (`resources/list`) and read one (`resources/read`) the way
the MCP client surfaces any resource — alongside, not instead of, the tools.

This module is the pure content half: it imports no MCP SDK, opens no
database, and is fully testable offline. `server.py` registers each entry it
lists with `@mcp.resource`. Three families:

  contract://page/<page>   the page's section+field contract, byte-identical
                           to get_page_contract(<page>)
  contract://index         all six pages' sections, required flags, surfaces
  join://section-sources   the dual-source map — for every app section, the
                           workbook tab(s), report section(s), enrichment
                           source and disposition that feed it
  gold://web-app-requirements  what the deployed app SERVES for the gold
                           standard (served vs owner-excluded sections) and
                           how each is produced — the "does my content fit"
                           reference an agent checks before submitting

`section_sources.json` is a cross-service contract: it is generated into
`packages/shared/` (staged into this image as `shared/` by deploy.sh, exactly
as contracts_data.json and enrichment_register.json are) with a copy under
the plugin the agents read. The loader prefers the staged copy and falls back
to the repo layout so the module works in a checkout too.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from dma_mcp.contracts import PAGES, get_page_contract

_HERE = Path(__file__).resolve().parent               # apps/mcp/dma_mcp
_MCP = _HERE.parent                                    # apps/mcp

#: Where section_sources.json may live, in preference order: the staged copy
#: inside the image, the shared source of truth in a checkout, then the
#: plugin's own copy. The first that exists wins.
_SECTION_SOURCES_CANDIDATES = (
    _MCP / "shared" / "section_sources.json",
    _MCP.parent.parent / "packages" / "shared" / "section_sources.json",
    _MCP.parent.parent / "plugins" / "dma-insights" / "references"
    / "section_sources.json",
)


def _section_sources_path() -> Path | None:
    for p in _SECTION_SOURCES_CANDIDATES:
        if p.is_file():
            return p
    return None


@lru_cache(maxsize=1)
def section_sources() -> dict:
    """The generated dual-source map, or a stated-empty envelope if the file
    was not staged (fail-soft: a missing join is a thin resource, never a
    crashed connector)."""
    p = _section_sources_path()
    if p is None:
        return {"_unavailable": "section_sources.json was not staged into "
                "this image; run scripts/gen_recording_map.py and deploy",
                "sections": {}, "coverage": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def contract_index() -> dict:
    """Every page's sections with their required flag and surface id — the
    map from an app section to the schema resource that defines it."""
    pages = {}
    for page in PAGES:
        secs = get_page_contract(page).get("sections") or {}
        pages[page] = {
            name: {"required": bool((m or {}).get("required", True)),
                   "surface_id": (m or {}).get("surface_id")}
            for name, m in secs.items()
        }
    return {"pages": pages,
            "how_to_read_one": "resources/read contract://page/<page>"}


def cards() -> dict:
    """Every card the app renders, per section: its item keys, nested
    sub-cards, and card-grain source (workbook tab COLUMNS / report section /
    enrichment facet), plus floor and flags. The card-grain half of the map."""
    ss = section_sources()
    out = {}
    for sec, v in ss.get("sections", {}).items():
        if v.get("cards"):
            out[sec] = v["cards"]
    return {"_doc": "Every card array the app renders, keyed by page.section "
                    "then card field. `kind` is card | grid | object_nested; "
                    "`item_keys` come from the contract; `nested`/`nested_shapes` "
                    "are the sub-cards; `columns` are the workbook tab columns; "
                    "`connector_authored`/`computed_never_sent` mark what a "
                    "producer must NOT send.",
            "sections": out}


def drilldowns() -> dict:
    """The 15-panel atlas: every drawer, modal and inline expansion — its
    parent card, the section it renders, and whether it carries its own
    synthesis prompt (DD-1/2/3/4/7)."""
    ss = section_sources()
    return {"_doc": "Every drilldown panel. It renders its parent surface's "
                    "payload; five carry their own synthesis prompt.",
            "drilldowns": ss.get("drilldowns", [])}


def web_app_requirements() -> dict:
    """What the deployed app serves for the gold standard, and how each
    section is produced — derived from the dual-source map's own `served` and
    `disposition` fields, so it can never disagree with the join."""
    ss = section_sources()
    secs = ss.get("sections", {})
    served, excluded, how = {}, {}, {}
    for sec, v in secs.items():
        page, _, name = sec.partition(".")
        (served if v.get("served") else excluded).setdefault(page, []).append(name)
        how[sec] = v.get("disposition")
    # card-grain requirements: floors, and the cards a producer must NOT author
    floors, connector_authored, computed_never_sent = {}, [], {}
    for sec, v in secs.items():
        for field, c in (v.get("cards") or {}).items():
            key = f"{sec}.{field}"
            if c.get("floor"):
                floors[key] = c["floor"]
            if c.get("connector_authored"):
                connector_authored.append(key)
            if c.get("computed_never_sent"):
                computed_never_sent[key] = c["computed_never_sent"]
    return {
        "_doc": "The sections the deployed app SERVES for the gold-standard "
                "client, and how each is produced. A page promotes only when "
                "every required section holds a passing submission; a section "
                "under `excluded` is produced and audited but withheld from "
                "every audience by the redaction allowlist. Check a produced "
                "section's disposition here before submitting; check a card's "
                "floor and the do-not-author lists before authoring one.",
        "workbook_contract": ss.get("workbook_contract"),
        "served_sections": {k: sorted(v) for k, v in served.items()},
        "excluded_sections": {k: sorted(v) for k, v in excluded.items()},
        "how_produced": how,
        "card_floors": floors,
        "connector_authored_cards": sorted(connector_authored),
        "computed_never_sent": computed_never_sent,
        "coverage": ss.get("coverage", {}),
    }


def _index() -> list[dict]:
    """The registry `server.py` walks to register resources, and the answer
    to resources/list. One concrete resource per entry so every schema is
    discoverable, not hidden behind a template."""
    entries = []
    for page in PAGES:
        entries.append({
            "uri": f"contract://page/{page}",
            "name": f"{page} page contract",
            "description": f"Section and field contract for the {page} page — "
                           f"byte-identical to get_page_contract('{page}'). "
                           f"For a list-of-object field the item keys are in "
                           f"the field's `doc` string.",
            "mime_type": "application/json",
        })
    entries.append({
        "uri": "contract://index",
        "name": "all page contracts, indexed",
        "description": "Every page's sections with their required flag and "
                       "surface id — the section→schema map.",
        "mime_type": "application/json",
    })
    entries.append({
        "uri": "join://section-sources",
        "name": "dual-source section map",
        "description": "For every app section: the workbook tab(s), report "
                       "section(s), enrichment source and disposition that "
                       "feed it. The workbook is the primary source.",
        "mime_type": "application/json",
    })
    entries.append({
        "uri": "join://cards",
        "name": "card-grain source map",
        "description": "Every card the app renders (finding, insight, "
                       "recommendation, tile, bar, register row) with its item "
                       "keys, nested sub-cards, and the workbook tab COLUMNS / "
                       "report section / enrichment facet that feed it.",
        "mime_type": "application/json",
    })
    entries.append({
        "uri": "join://drilldowns",
        "name": "drilldown atlas",
        "description": "The 15 drawers/modals/expansions — each panel's parent "
                       "card, the section it renders, and whether it carries "
                       "its own synthesis prompt.",
        "mime_type": "application/json",
    })
    entries.append({
        "uri": "gold://web-app-requirements",
        "name": "gold-standard web-app requirements",
        "description": "What the deployed app serves for the gold standard "
                       "and how each section is produced — the reference an "
                       "agent checks before submitting.",
        "mime_type": "application/json",
    })
    return entries


def resource_index() -> list[dict]:
    return _index()


def _content(uri: str) -> dict:
    if uri == "contract://index":
        return contract_index()
    if uri == "join://section-sources":
        return section_sources()
    if uri == "join://cards":
        return cards()
    if uri == "join://drilldowns":
        return drilldowns()
    if uri == "gold://web-app-requirements":
        return web_app_requirements()
    prefix = "contract://page/"
    if uri.startswith(prefix):
        page = uri[len(prefix):]
        if page in PAGES:
            return get_page_contract(page)
    raise KeyError(uri)


def read_resource(uri: str) -> dict:
    """{uri, mime_type, text} for a registered resource; KeyError otherwise."""
    body = _content(uri)
    return {"uri": uri, "mime_type": "application/json",
            "text": json.dumps(body, indent=1, sort_keys=False)}
