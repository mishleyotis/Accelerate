"""CG-14 — a linked cell exists on this run.

A tech row's `linked_subcap_ids` and a why-now's `linked_subcap_ids` are
navigation: the card renders each as a chip that opens the cell drawer. A
cell the run does not carry opens onto nothing, and stays invisible until
somebody clicks it — which is why it needs the same fail-closed posture
as an evidence id rather than a render-time guard.

Existence, not score: a cell the run carries with a null score is still a
cell (a null score is a legitimate reading, and refusing a link to one
would refuse the thin-evidence case the heatmap exists to show).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import _check_cell_linkage

RUN_CELLS = {"P4C3.1.1", "P4C3.1.2", "P2C4.1.1", "P2C4.1.3", "P2C3.1.6"}


def test_a_tech_rows_link_to_a_cell_the_run_lacks_is_refused():
    payload = {"techstack": {"items": [
        {"ts_id": "TS-205", "product": "Salesforce Marketing Cloud",
         "linked_subcap_ids": ["P2C4.1.1", "P2C4.9.9"]}]}}
    out = _check_cell_linkage("techstack", payload, RUN_CELLS)
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "CG-14" and r["severity"] == "block"
    assert r["path"] == "techstack.items[0].linked_subcap_ids[1]"
    assert "P2C4.9.9" in r["message"] and "linked_subcap_ids" in r["message"]
    assert "opens the cell drawer onto nothing" in r["message"]


def test_a_why_nows_link_is_held_to_the_same_rule():
    payload = {"why_now": {"signals": [
        {"wn_id": "WN-1", "linked_subcap_ids": ["P4C3.1.1", "P9C9.9.9"]}]}}
    out = _check_cell_linkage("overview", payload, RUN_CELLS)
    assert len(out) == 1 and out[0]["path"].endswith("linked_subcap_ids[1]")


def test_the_corrected_lists_pass():
    payload = {
        "techstack": {"items": [{"ts_id": "TS-101",
                                 "linked_subcap_ids": ["P4C3.1.2"]}]},
        "why_now": {"signals": [{"wn_id": "WN-1",
                                 "linked_subcap_ids": ["P4C3.1.1",
                                                       "P4C3.1.2"]}]},
    }
    assert _check_cell_linkage("techstack", payload, RUN_CELLS) == []


def test_an_empty_link_list_asserts_nothing():
    payload = {"issue_register": {"issues": [
        {"issue_id": "ISS-002", "linked_subcap_ids": []}]}}
    assert _check_cell_linkage("context", payload, RUN_CELLS) == []


def test_a_run_with_no_cells_at_all_refuses_nothing():
    """An unscored run cannot tell a bad link from an unloaded workbook,
    and the empty-run case is the ingest gates' to catch."""
    payload = {"techstack": {"items": [
        {"linked_subcap_ids": ["P2C4.9.9"]}]}}
    assert _check_cell_linkage("techstack", payload, set()) == []


def test_one_verdict_per_cell_per_section_not_one_per_occurrence():
    """The same missing cell repeated across forty rows is one repair, and
    forty verdicts would bury the other reasons in the same submission."""
    payload = {"techstack": {"items": [
        {"linked_subcap_ids": ["P2C4.9.9"]},
        {"linked_subcap_ids": ["P2C4.9.9"]},
        {"linked_subcap_ids": ["P2C4.9.9"]}]}}
    assert len(_check_cell_linkage("techstack", payload, RUN_CELLS)) == 1


def test_the_keys_that_are_not_spelled_subcap_id_are_still_cell_links():
    """A timeline event's `capability_ids`, a value chain's `subcaps` and an
    insight card's singular `linked_subcap_id` are the same navigation as a
    tech row's `linked_subcap_ids`: a chip a reader clicks. A predicate
    written from the two commonest spellings read none of them, so a card
    could point at a cell the run does not carry and no gate would say so.
    """
    payload = {
        "timeline": {"events": [
            {"title": "Core conversion", "capability_ids": ["P4C3.1.1",
                                                            "P2C4.9.9"]}]},
        "value_chain": {"chains": [
            {"stage": "Serve", "subcaps": ["P2C3.1.6", "P9C9.9.9"]}]},
        "insights": {"cards": [
            {"ic_id": "IC-8", "linked_subcap_id": "P2C4.9.8"}]},
    }
    out = _check_cell_linkage("context", payload, RUN_CELLS)
    assert {r["path"] for r in out} == {
        "timeline.events[0].capability_ids[1]",
        "value_chain.chains[0].subcaps[1]",
        "insights.cards[0].linked_subcap_id",
    }
    assert all(r["gate_id"] == "CG-14" and r["severity"] == "block"
               for r in out)


def test_a_cell_key_carrying_prose_contributes_nothing():
    """The id regex decides what counts, so widening the key predicate
    cannot turn a sentence into a citation."""
    payload = {"value_chain": {"chains": [
        {"stage": "Serve", "subcaps": ["not a cell id", "P4C3.1.1"]}]}}
    assert _check_cell_linkage("heatmap", payload, RUN_CELLS) == []


def test_an_insight_cards_affects_list_is_held_to_the_same_rule():
    """`affects` was the fourth spelling and the predicate could not see it.

    Measured 2026-08-18 against a PROMOTED run whose insights page carries 32
    cell ids under `cards[*].affects`: injecting P1C1.3.BK1 — a retail-bank
    variant cell, so ET-05 territory as well — and P1C9.9.9, which exists in
    no catalogue, drew ZERO blocking reasons from this gate and zero from the
    local checker. The same two ids in `focus_areas[*].involved_subcap_ids`
    drew two refusals from each. Every one of the 32 real ids was correct,
    which is exactly what made it worth fixing: the field's green check could
    not have been red, so it was evidence about nothing.
    """
    payload = {"insights": {"cards": [
        {"ic_id": "IC-1", "affects": ["P2C3.1.6", "P1C9.9.9"]}]}}
    out = _check_cell_linkage("insights", payload, RUN_CELLS)
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "CG-14" and r["severity"] == "block"
    assert r["path"] == "insights.cards[0].affects[1]"
    assert "affects" in r["message"] and "P1C9.9.9" in r["message"]


def test_an_affects_list_the_run_carries_passes():
    payload = {"insights": {"cards": [
        {"ic_id": "IC-1", "affects": ["P2C3.1.6", "P4C3.1.1"]}]}}
    assert _check_cell_linkage("insights", payload, RUN_CELLS) == []
