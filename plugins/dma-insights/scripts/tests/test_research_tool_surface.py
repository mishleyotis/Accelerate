"""The research layer's tool surface (owner, 2026-10-11: "avoid generic
names, split by functionality … as per gold standard requirements. Ensure
clear description of tools").

Pins: every surfaced tool maps to an upstream tool the snapshot lists; every
full name fits the API's 64 characters; no generic upstream name leaks
through; presets are fixed by the proxy and hidden from the agent; every
card-returning tool tells the agent which gold Evidence_Detail columns its
output fills; the hooks' copies of the names equal the surface's.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
PLUGIN = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "hooks"))

import research_tool_surface as S  # noqa: E402

SNAPSHOT = json.loads((PLUGIN / "references" / "research_layer_tools.json").read_text())
#: Evidence_Detail columns a card fills or the ledger computes, by the gold
#: workbook's own header names (engine/contract.py EVIDENCE_HEADERS).
GOLD_COLUMNS = ("Source_Name", "Source_URL", "Tier", "Date_Published", "Claim_Type", "SubCap_IDs",
                "Excerpt", "E_ID", "ERS", "Recency", "Retrieved_At", "Access_Status")
GENERIC = {"fetch", "research_brief", "crawl_entity", "filings_evidence", "expand_context", "verify_cards",
           "coverage_report", "searxng_web_search", "web_url_read", "get_company_facts", "get_financials"}


def test_every_surfaced_tool_has_an_upstream_the_snapshot_lists():
    for svc in S.SERVICES:
        listed = {t["name"] for t in SNAPSHOT[svc]}
        for e in S.entries(svc):
            assert e["upstream"] in listed, (svc, e["name"], e["upstream"])
        assert len(S.present(svc, SNAPSHOT[svc])) == len(S.entries(svc))


def test_names_are_specific_unique_and_fit_the_api_limit():
    seen = set()
    for svc in S.SERVICES:
        for n in S.names(svc):
            full = S.full_name(svc, n)
            assert len(full) <= S.MAX_TOOL_NAME, full
            assert re.fullmatch(r"[a-z0-9_]+", n), n
            assert n not in GENERIC, n
            assert full not in seen
            seen.add(full)


def test_no_upstream_tool_leaks_through_unnamed():
    for svc in S.SERVICES:
        names = {t["name"] for t in S.present(svc, SNAPSHOT[svc])}
        assert names == set(S.names(svc))
        # an upstream tool the surface does not name (insider-trading reads) is hidden
        assert not names & {"get_insider_transactions", "analyze_insider_sentiment"}


def test_presets_are_fixed_and_hidden_from_the_schema():
    tools = {t["name"]: t for t in S.present("evidence", SNAPSHOT["evidence"])}
    reg = tools["find_regulator_evidence"]
    assert "source_classes" not in reg["inputSchema"]["properties"]
    assert "run_id" in reg["inputSchema"]["required"]
    crawl = tools["read_entity_careers"]
    assert "path_focus" not in crawl["inputSchema"]["properties"]
    # the caller cannot override a preset
    out = S.to_upstream("evidence", {"name": "find_regulator_evidence",
                                     "arguments": {"run_id": "R", "source_classes": ["news"]}})
    assert out == {"name": "research_brief", "arguments": {"run_id": "R", "source_classes": ["regulator"]}}
    out = S.to_upstream("searxng", {"name": "keyword_search_news",
                                    "arguments": {"query": "q", "engines": "google"}})
    assert out == {"name": "searxng_web_search", "arguments": {"query": "q", "categories": "news"}}
    # an unknown (or upstream) name passes through untouched
    assert S.to_upstream("evidence", {"name": "research_brief", "arguments": {"a": 1}}) == \
        {"name": "research_brief", "arguments": {"a": 1}}


def test_per_class_presets_are_engine_source_types():
    sys.path.insert(0, str(PLUGIN.parents[1] / "apps" / "evidence-engine"))
    from evidence_engine.contract import FACETS, SOURCE_TYPES
    for e in S.entries("evidence"):
        for c in (e.get("preset") or {}).get("source_classes", []):
            assert c in SOURCE_TYPES, (e["name"], c)
        f = (e.get("preset") or {}).get("facet")
        assert f is None or f in FACETS


def test_card_tools_name_the_gold_columns_they_fill():
    for svc in S.SERVICES:
        for e in S.entries(svc):
            text = S.description(e)
            assert len(e["description"]) >= 120, e["name"]
            if e.get("appendix") == "cards":
                for col in GOLD_COLUMNS:
                    assert col in text, (e["name"], col)
                assert "verbatim" in text and "50–500" in text
                assert "never the retrieval date" in text
    gold = set(json.loads(json.dumps(GOLD_COLUMNS)))
    sys.path.insert(0, str(PLUGIN / "skills" / "dma-research"))
    from engine import contract
    assert gold <= set(contract.EVIDENCE_COLUMNS)


def test_search_tools_say_a_snippet_is_not_an_excerpt():
    for n in ("keyword_search_web_pages", "keyword_search_news", "keyword_search_papers"):
        e = next(x for x in S.entries("searxng") if x["name"] == n)
        assert "never register it as an Excerpt" in S.description(e)


def test_hook_copies_equal_the_surface():
    import deny_whole_page_fetch as D
    import search_order as O
    briefs = S.full_names("evidence", kinds=("brief",))
    assert O.BRIEFS[:len(briefs)] == briefs
    for n in ("read_web_page_markdown",):
        assert S.full_name("fetch", n) in D.FETCHERS
    assert S.full_name("searxng", "read_web_page_section") in D.FETCHERS
    for n in S.names("searxng", kinds=("search",)):
        assert S.full_name("searxng", n) in D.SEARCHERS
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    post = " ".join(h.get("matcher", "") for h in hooks["hooks"]["PostToolUse"])
    pre = " ".join(h.get("matcher", "") for h in hooks["hooks"]["PreToolUse"])
    for svc in S.SERVICES:
        for full in S.full_names(svc):
            assert full in post, full                     # source_health logs every call
    for full in briefs:
        assert full in post                               # search_order counts every brief
    for full in D.FETCHERS + D.SEARCHERS:
        assert full in pre, full                          # the page guard actually fires


def test_the_evidence_server_instructions_name_the_surfaced_tools():
    """Measured 2026-10-12 in a resumed session: the tools bound under the
    surfaced names while the server instructions still said `research_brief`,
    `expand_context`, `verify_cards` — the engine's own initialize text."""
    text = S.instructions("evidence")
    for n in ("find_evidence_all_sources", "expand_card_context", "verify_evidence_cards"):
        assert n in text
    for old in ("research_brief", "expand_context ", "verify_cards"):
        assert old not in text
    got = S.with_instructions("evidence", {"serverInfo": {"name": "dmai-evidence"}, "instructions": "Call research_brief first"})
    assert got["instructions"] == text and got["serverInfo"] == {"name": "dmai-evidence"}
    assert S.with_instructions("fetch", {"instructions": "x"}) == {"instructions": "x"}


def test_find_registrant_covers_every_sub_vertical_not_only_sec_filers():
    """Owner, 2026-10-12: "The tool is supposed to be find registrant as we
    deal with 9 subverticals in US and Canada." EDGAR's company search is no
    longer the registrant lookup; the evidence server's find_registrant is,
    and its description names the registry for each kind of institution."""
    e = next(x for x in S.entries("evidence") if x["name"] == "find_registrant")
    assert e["upstream"] == "find_registrant" and e["kind"] == "registry"
    text = S.description(e)
    for reg in ("NCUA", "FDIC", "FINRA", "Farm Credit", "OSFI", "EDGAR", "NAIC", "provincial"):
        assert reg in text, reg
    for code in ("CU", "RB", "CL", "CIB", "AM", "RIA", "IC", "IB", "FC"):
        assert code in text, code
    for col in ("Firmographics", "Regulator", "Source_URL", "T1", "ET gates"):
        assert col in text, col
    assert "search_companies" not in {x["upstream"] for x in S.entries("edgar")}
    assert "find_sec_registrant" not in S.names("edgar")
