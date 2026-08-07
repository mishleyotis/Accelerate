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
