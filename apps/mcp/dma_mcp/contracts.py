"""Contract registry (stage 2.1) — all 34 sections across 6 pages.

This registry is the single source of truth that the contract tool
serves, the validator reads and the writers target — one definition,
four consumers. Field data lives in contracts_data.json beside this
module (page → section → {surface_id, required, fields}); this module
adds the universal envelope, the serving-table map and the accessors.

The `doc` string on every field is part of the contract, not
documentation: for a list-of-object field it is the only place the item
keys are stated, and get_page_contract returns it verbatim.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).parent
_DATA = _HERE / "contracts_data.json"

PAGES = ("heatmap", "overview", "insights", "platform", "context", "techstack")

# The universal envelope on every section (Implementation Plan 2.1).
ENVELOPE = {
    "produced_at": {
        "required": True, "type": "string", "item_type": None,
        "doc": "ISO-8601 instant this section was produced.",
    },
    "producer_version": {
        "required": True, "type": "string", "item_type": None,
        "doc": "Producer identity and version, e.g. 'surface-synthesis@2026-08-01'. "
               "Every promoted row carries it non-null.",
    },
    "e_ids": {
        "required": True, "type": "list", "item_type": "string",
        "doc": "Every evidence id this section cites, bare (no brackets — the "
               "chip owns the brackets). Where a surface declares its "
               "grounding, the number is len(e_ids): computed, never asserted.",
    },
    "internal_only": {
        "required": True, "type": "list", "item_type": "string",
        "doc": "JSON paths within this section the serve layer strips for the "
               "customer audience. Marking is the producer's duty: a path you "
               "do not mark reaches the client. May be empty, never absent.",
    },
    "empty_state": {
        "required": False, "type": "object", "item_type": None,
        "doc": "Explicit empty state: {reason, sources_searched[], "
               "closure_condition}. An empty surface is a value, not an "
               "omission — a missing required field fails the contract; an "
               "explicit empty state passes and renders. An absence with no "
               "recorded search (sources_searched) is rejected.",
    },
}

# page.section -> serving table (0008; heatmap.evidence serves from the
# ingested evidence_index — Backend Schema: "also the serving table for
# heatmap.evidence").
SERVING_TABLES = {
    ("overview", "scores"): "overview_scores",
    ("overview", "firmographics"): "overview_firmographics",
    ("overview", "why_now"): "overview_why_now",
    ("overview", "exec_summary"): "overview_exec_summary",
    ("overview", "opportunity"): "overview_opportunity",
    ("overview", "findings"): "overview_findings",
    ("overview", "leadership"): "overview_leadership",
    ("overview", "financial_series"): "overview_financial_series",
    ("overview", "sentiment"): "overview_sentiment",
    ("overview", "ceilings"): "overview_ceilings",
    ("overview", "evidence_coverage"): "overview_evidence_coverage",
    ("overview", "thought_leadership"): "overview_thought_leadership",
    ("insights", "insights"): "insight_cards",
    ("insights", "landscape"): "insights_landscape",
    ("heatmap", "workbook_scores"): "heatmap_workbook_scores",
    ("heatmap", "focus_areas"): "heatmap_focus_areas",
    ("heatmap", "cell_evidence"): "heatmap_cell_evidence",
    ("heatmap", "evidence"): "evidence_index",
    ("heatmap", "value_chain"): "heatmap_value_chain",
    ("heatmap", "alerts"): "heatmap_alerts",
    ("heatmap", "safeguard_gates"): "heatmap_safeguard_gates",
    ("heatmap", "evidence_age"): "heatmap_evidence_age",
    ("heatmap", "cohort_patterns"): "heatmap_cohort_patterns",
    ("platform", "platform_story"): "platform_story",
    ("platform", "recommendations"): "platform_recommendations",
    ("platform", "starters"): "platform_starters",
    ("platform", "roadmap"): "platform_roadmap",
    ("platform", "stairstep"): "platform_stairstep",
    ("context", "timeline"): "context_timeline",
    ("context", "issue_register"): "context_issue_register",
    ("context", "regulatory_standing"): "context_regulatory_standing",
    ("context", "context_sentiment"): "context_sentiment",
    ("context", "acquisitions"): "context_acquisitions",
    ("techstack", "techstack"): "techstack_items",
}


#: Section metadata the WRITER binds with a `section:` source but which no
#: surface contract lists as a field. Accepted per section, and only where that
#: section's writer actually binds the column — so a section with nowhere to
#: store one still refuses it, which is right: a field that promotes into
#: nothing is the defect this whole registry exists to prevent.
#:
#: Without this, CG-04 refused the two fields the charter REQUIRES. AG-01 blocks
#: a ranked or causal claim carrying no `r_layer`, and every page owes a
#: `narrative_thread` — yet a producer sending either got
#: "field 'r_layer' is not in the overview.scores contract". That is why a real
#: promoted run had `r_layer` null on 30 of 34 sections and `narrative_thread`
#: null on 32 of 34: not producer laziness, a gate refusing its own requirement.
#: Optional, because 6 of the 34 writers bind r_layer at ITEM grain instead
#: (an insight card carries its own), and a required-everywhere field would then
#: fail the sections that legitimately have none.
SECTION_META = {
    "r_layer": {
        "required": False, "type": "object", "item_type": None,
        "doc": "The recorded reasoning for this section's ranked or causal "
               "claims: {hypothesis, counter, domain_test, probes_run[], "
               "verdict, confidence}. AG-01 blocks a ranked or causal claim "
               "without one. Where the claims are per item (an insight card, a "
               "recommendation), the item carries its own and this stays null.",
    },
    "narrative_thread": {
        "required": False, "type": "string", "item_type": None,
        "doc": "45-75 words tracing the line through this page's surfaces in "
               "render order, written last from what was actually produced. A "
               "page is not a container for surfaces; if the thread cannot be "
               "written, the surfaces are not yet a page.",
    },
}


@lru_cache(maxsize=1)
def _section_bound_meta() -> dict:
    """(page, section) -> the SECTION_META keys that section's writer binds.

    Read straight from writer_spec.json rather than through promote, which
    imports this module — the derivation must not create an import cycle, and
    reading the spec is the same single source of truth either way.
    """
    spec = json.loads((_HERE / "writer_spec.json").read_text())
    out = {}
    for page_spec in spec["specs"]:
        for w in page_spec["writers"]:
            bound = {c["source"].partition(":")[2] for c in w["columns"]
                     if c["source"].startswith("section:")}
            out[(page_spec["page"], w["section"])] = bound
    return out


def _section_meta_for(page: str, name: str) -> dict:
    """Which SECTION_META keys this section's writer can actually store."""
    bound = _section_bound_meta().get((page, name), set())
    return {k: v for k, v in SECTION_META.items() if k in bound}


def _load() -> dict:
    with open(_DATA) as f:
        data = json.load(f)
    for page, sections in data.items():
        for name, sec in sections.items():
            if name.startswith("_"):
                continue
            # envelope fields are appended to every section, never redefined
            overlap = set(sec["fields"]) & set(ENVELOPE)
            if overlap:
                raise ValueError(f"{page}.{name} redefines envelope: {overlap}")
            # A section that declares one of these ITSELF keeps its own
            # definition — `overview.scores` names narrative_thread in the
            # contract, which is exactly why it was one of the only two
            # sections that ever promoted one. The contract wins; the meta
            # fills in for the 32 sections whose contract is silent.
            meta = {k: v for k, v in _section_meta_for(page, name).items()
                    if k not in sec["fields"]}
            sec["fields"] = {**sec["fields"], **ENVELOPE, **meta}
    return data


_REGISTRY = None


def registry() -> dict:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _load()
    return _REGISTRY


def sections(page: str) -> dict:
    return {k: v for k, v in registry()[page].items() if not k.startswith("_")}


def all_sections() -> list:
    return [(p, s) for p in PAGES for s in sections(p)]


def get_page_contract(page: str) -> dict:
    """The get_page_contract tool's response body: shapes plus verbatim
    doc text (TRD §"Exchange contracts")."""
    if page not in PAGES:
        return {"error": "unknown_page", "pages": list(PAGES)}
    out = {}
    for name, sec in sections(page).items():
        out[name] = {
            "surface_id": sec.get("surface_id"),
            "required": sec.get("required", True),
            "fields": {
                f: {"required": spec["required"], "type": spec["type"],
                    **({"item_type": spec["item_type"]} if spec.get("item_type") else {}),
                    "doc": spec["doc"]}
                for f, spec in sec["fields"].items()
            },
        }
    return {"page": page, "sections": out}
