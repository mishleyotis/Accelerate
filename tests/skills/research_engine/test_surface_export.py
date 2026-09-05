"""engine.surface_export — the section router and the format/validate half.

Owner, 2026-09-05: stop re-synthesising (and re-challenging) content the
research and report stages already produced, and make it visible WHICH
sections those are. These tests pin the route every section takes and that
the scaffolder assembles exactly the payload the MCP resource requires,
refusing a shape the contract would refuse — offline, no connector.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from engine import surface_export as SX

_REPO = Path(__file__).resolve().parents[3]
for _p in (_REPO / "apps" / "mcp", _REPO / "packages" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def test_plan_routes_every_section_exactly_once():
    p = SX.plan()
    n = len(p["sections"])
    assert n >= 34
    assert len(p["convert"]) + len(p["produce"]) + len(p["server"]) == n
    # no section is in two buckets
    buckets = p["convert"] + p["produce"] + p["server"]
    assert len(buckets) == len(set(buckets)) == n


def test_route_follows_disposition():
    rows = SX.plan()["sections"]
    for sec, r in rows.items():
        if r["disposition"] in ("workbook", "report"):
            assert r["route"] == "convert", sec
        elif r["disposition"] in ("enrichment", "synthesis"):
            assert r["route"] == "produce", sec
        elif r["disposition"] == "server":
            assert r["route"] == "server", sec


def test_the_value_chain_is_the_server_section():
    assert SX.plan()["server"] == ["heatmap.value_chain"]


def test_only_a_handful_need_a_producer():
    """The point of the change: most sections are formatting, not synthesis."""
    produce = SX.plan()["produce"]
    # leadership/sentiment/thought_leadership (enrichment) + cohort_patterns
    assert set(produce) == {
        "overview.leadership", "overview.sentiment",
        "overview.thought_leadership", "heatmap.cohort_patterns"}


def test_scaffold_assembles_a_valid_section():
    p = SX.scaffold(
        "overview", "scores",
        {"composite": 2.7, "pillars": [{"pillar": "P1"}], "posture": "Building",
         "posture_basis": "raw composite 2.7", "framing": "x",
         "claim_label": "FACT", "confidence": "medium", "narrative_thread": "t"},
        e_ids=["E-CC-1"], producer_version="test@1")
    assert p["produced_at"] and p["producer_version"] == "test@1"
    assert p["e_ids"] == ["E-CC-1"] and p["internal_only"] == []


def test_scaffold_refuses_a_missing_required_field():
    with pytest.raises(ValueError):
        SX.scaffold("overview", "scores", {"composite": 2.7},
                    e_ids=[], producer_version="t")


def test_scaffold_refuses_an_unknown_field():
    with pytest.raises(ValueError):
        SX.scaffold("heatmap", "value_chain", {"bogus": 1},
                    e_ids=[], producer_version="t")


def test_scaffold_accepts_a_reasoned_empty_state():
    p = SX.scaffold("heatmap", "cohort_patterns", {}, e_ids=[],
                    producer_version="t",
                    empty_state={"reason": "cohort < 5",
                                 "sources_searched": ["x"],
                                 "closure_condition": "y"})
    assert p["empty_state"]["reason"]


def test_cards_routes_every_card_with_a_source():
    c = SX.cards()
    assert len(c) >= 43
    for key, r in c.items():
        assert r["route"] in ("convert", "produce", "server", "connector")
        # a routed card names a source, or is connector/computed/synthesis
        assert (r["tab"] or r["report_sections"] or r["enrichment_facet"]
                or r["connector_authored"] or r["route"] in ("produce", "server")), key


def test_connector_authored_card_routes_connector():
    c = SX.cards("heatmap.safeguard_gates")
    assert c["heatmap.safeguard_gates.gates"]["route"] == "connector"
    assert c["heatmap.safeguard_gates.gates"]["connector_authored"] is True


def test_scaffold_card_accepts_valid_and_rejects_unknown_key():
    ok = SX.scaffold_card("overview", "findings", "findings",
                          {"f_id": "F1", "title": "x", "body": "y"})
    assert ok["f_id"] == "F1"
    with pytest.raises(ValueError):
        SX.scaffold_card("overview", "findings", "findings",
                         {"f_id": "F1", "not_a_contract_key": 1})
    with pytest.raises(KeyError):
        SX.scaffold_card("overview", "findings", "no_such_card", {})


def test_drawers_is_the_full_atlas():
    dd = SX.drawers()
    assert len(dd) == 15
    assert {d["dd"] for d in dd if d["has_synthesis_prompt"]} == {
        "DD-1", "DD-2", "DD-3", "DD-4", "DD-7"}


def test_server_section_carries_the_page_thread_and_passes_pass1():
    from dma_mcp.validation import validate_pass1
    thread = ("The heatmap opens on the workbook grid, tracks the thin-evidence "
              "alerts against the cells that raised them and closes on the value "
              "chain where those cells sit, in render order across the page.")
    vc = SX.server_section("heatmap", "value_chain",
                           producer_version="engine.surface_export@1",
                           narrative_thread=thread)
    reasons = validate_pass1("heatmap", {"value_chain": vc})
    assert not [r for r in reasons if "value_chain" in json.dumps(r)]
