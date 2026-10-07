"""The customer scope the api serves and the connector's CG-52 checks is one
definition (packages/shared/internal_ids.py), and its excluded key classes
agree with serve_classes.json, the file the customer allowlist is generated
from. A second copy of either is how a submit gate and a serve rule drift."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import internal_ids as I  # noqa: E402


def test_excluded_keys_cover_every_serve_class():
    classes = json.loads((HERE.parent / "serve_classes.json").read_text())
    keys = {k for name, c in classes.items() if not name.startswith("_")
            for k in c["keys"]}
    assert keys <= I.CUSTOMER_EXCLUDED_KEYS, sorted(keys - I.CUSTOMER_EXCLUDED_KEYS)


def test_a_tool_name_in_a_cell_synthesis_is_a_customer_hit():
    body = {"cells": [{"subcap_id": "P1C1.1.1",
                       "synthesis": "An Exa search of the newsroom found no strategy."},
                      {"subcap_id": "P1C1.1.2", "synthesis": "The plan names three goals."}]}
    assert I.customer_prose_hits("heatmap", "cell_evidence", body) == [
        ("cells[0].synthesis", "Exa")]


def test_what_no_customer_is_served_is_not_a_hit():
    body = {"cells": [{"synthesis": "Plain prose.",
                       "sources_searched": ["Exa search, 2026-10-07"],
                       "provenance": "Tavily"}],
            "r_layer": {"counter": "Clay scan NOT_RUN"},
            "narrative_thread": "The grid reads low across the estate."}
    assert I.customer_prose_hits("heatmap", "cell_evidence", body) == []
    # withheld sections and pages
    assert I.customer_prose_hits("heatmap", "alerts", {"x": "Exa"}) == []
    assert I.customer_prose_hits("context", "timeline", {"x": "Exa"}) == []
    assert I.customer_prose_hits("overview", "ceilings", {"x": "Exa"}) == []


def test_internal_only_markings_are_honoured_at_their_own_grain():
    body = {"cells": [{"synthesis": "Exa one"}, {"synthesis": "Tavily two"}]}
    assert I.customer_prose_hits("heatmap", "cell_evidence", body,
                                 ["cells[0].synthesis"]) == [("cells[1].synthesis", "Tavily")]
    assert I.customer_prose_hits("heatmap", "cell_evidence", body,
                                 [{"path": "cells[*].synthesis", "why": "x"}]) == []


def test_safeguard_gates_may_say_not_run_and_names_are_people():
    assert I.customer_prose_hits("heatmap", "safeguard_gates",
                                 {"gates": [{"detail": "NOT_RUN because no scan"}]}) == []
    assert I.customer_prose_hits("heatmap", "focus_areas",
                                 {"focus_areas": [{"name": "Clay"}]}) == []


def test_key_limit_scopes_other_pages_to_narrative_and_empty_state():
    body = {"narrative_thread": "Tavily found the CEO quote.",
            "findings": [{"body": "An Exa search shows…"}],
            "empty_state": {"reason": "NOT_RUN in this run", "sources_searched": ["Exa"]}}
    hits = I.customer_prose_hits("overview", "findings", body,
                                 keys={"narrative_thread", "empty_state"})
    assert sorted(hits) == [("empty_state.reason", "NOT_RUN"),
                            ("narrative_thread", "Tavily")]


SEARCH_LOG_PROSE = [
    "three Exa queries (ESG materiality assessment, criticism) returned only the annual reports.",
    "web_search 'First Tech net zero' (10 hits) and Exa 'First Tech carbon neutral' (3 hits) "
    "returned no target. Tavily returned HTTP 432 and was unusable.",
    "Counter-reading: NOT_RUN: web_search budget exhausted and Tavily plan limit hit (HTTP 432); "
    "only Exa volleys ran, no dedicated facet query.",
    "searched web_search ERM and cyber queries plus Exa CRO governance query; came back empty.",
    "sustainability content in annual reports and firsttechfed.com articles (Exa); came back with two.",
    "Queries on Clay and Exa for competitor marketing monitoring found one report.",
    "Clay's Tech Stack scan was NOT_RUN for lack of connector credit; RRF k=60 ranked it in the hot band.",
]


def test_neutralised_prose_never_names_a_pipeline_term():
    for text in SEARCH_LOG_PROSE:
        out = I.neutralise_pipeline_terms(text)
        assert I.names_pipeline_term(out) is None, (text, out)
        assert out and out[-1] in ".?!", out


def test_neutralising_keeps_what_the_search_established():
    out = I.neutralise_pipeline_terms(SEARCH_LOG_PROSE[1])
    assert "returned no target" in out and "HTTP" not in out and "unusable" not in out


def test_names_and_ordinary_words_are_left_alone():
    for text in ("Clay Thompson, CFO, approved the plan.", "the clay soil of the campus",
                 "an exact example", None):
        assert I.neutralise_pipeline_terms(text) == text


def test_a_registered_source_name_is_the_stores_not_the_producers():
    body = {"evidence": [{"e_id": "E-1", "source_name": "Clay technographic scan",
                          "excerpt": "x" * 60}]}
    assert I.customer_prose_hits("heatmap", "evidence", body) == []
