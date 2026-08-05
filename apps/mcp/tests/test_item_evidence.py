"""AG-03 — every claim-bearing item cites evidence, inferences included.

The section envelope's e_ids were not enough: a reader drills into the
ITEM, and a why-now signal or a ceiling row that cites nothing renders to
a client with no way back to a source. These assert the gate fires on the
claim and stays silent on the two honest non-claims — a null-valued row
and a recorded absence carrying the ladder that established it.

The requirement is read from each field's own item schema (the doc text),
so a section that gains an evidence key gains its enforcement with it;
these tests pin that derivation as well as the verdict.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import sections
from dma_mcp.validation2 import (_asserts_nothing, _check_item_evidence,
                                 _declared_ev_keys)


def _ag03(page, payload):
    return [r for r in _check_item_evidence(page, payload)
            if r["gate_id"] == "AG-03"]


def test_contract_declares_the_evidence_key_per_item():
    """The gate derives its rule from the contract, not a hand-list."""
    wn = sections("overview")["why_now"]["fields"]["signals"]
    assert "e_ids" in _declared_ev_keys(wn)
    cards = sections("insights")["insights"]["fields"]["cards"]
    assert "supporting_e_ids" in _declared_ev_keys(cards)
    # a field with no item schema declares nothing and is not policed
    assert _declared_ev_keys({"doc": "A single prose paragraph."}) == ()


def test_uncited_signal_blocks_and_the_reason_names_the_path():
    payload = {"why_now": {"signals": [
        {"wn_id": "WN-1", "trigger": "A dated thing changed in June 2026.",
         "linked_subcap_ids": ["P4C3.1.1"], "claim_label": "FACT"}]}}
    reasons = _ag03("overview", payload)
    assert len(reasons) == 1
    r = reasons[0]
    assert r["path"] == "why_now.signals[0].e_ids"
    assert r["severity"] == "block"
    assert "cites no evidence" in r["message"]


def test_a_cited_signal_passes():
    payload = {"why_now": {"signals": [
        {"wn_id": "WN-1", "trigger": "A dated thing changed.",
         "e_ids": ["E-BCU-046"]}]}}
    assert _ag03("overview", payload) == []


def test_inference_still_needs_an_id():
    """'Inferences should also have evidence' — a claim_label of
    INFERENCE buys no exemption; it changes the tier, not the duty."""
    payload = {"overview": {}, "findings": {"findings": [
        {"f_id": "F-1", "title": "An inferred gap", "claim_label": "INFERENCE"}]}}
    assert len(_ag03("overview", payload)) == 1


def test_null_valued_row_asserts_nothing():
    """A firmographic with no figure makes no claim (derived-or-null)."""
    payload = {"firmographics": {"fields": [
        {"field": "roa", "value": None, "recency_band": "UNVERIFIED"},
        {"field": "assets", "value": 6.5e9, "source_e_id": "E-CC-006"}]}}
    assert _ag03("overview", payload) == []


def test_recorded_absence_is_exempt_but_a_bare_absence_is_not():
    worked_absent = {"subcap_id": "P2C2.x.7", "state": "WORKED_ABSENT",
                     "new_evidence_ids": [], "sources_searched": ["a", "b"],
                     "queries_run": ["q"]}
    bare = {"subcap_id": "P2C2.x.9", "state": "WORKED_ABSENT",
            "new_evidence_ids": []}
    assert _asserts_nothing(worked_absent) is True
    assert _asserts_nothing(bare) is False
    assert _ag03("heatmap", {"alerts": {"alerts": [worked_absent]}}) == []
    assert len(_ag03("heatmap", {"alerts": {"alerts": [bare]}})) == 1


def test_a_state_asserting_a_find_with_no_id_is_a_contradiction():
    """WORKED_FOUND with an empty id list is not an empty state."""
    payload = {"alerts": {"alerts": [
        {"subcap_id": "P2C1.x.4", "state": "WORKED_FOUND",
         "new_evidence_ids": [], "sources_searched": ["a"], "queries_run": ["q"]}]}}
    reasons = _ag03("heatmap", payload)
    assert len(reasons) == 1
    assert "contradiction" in reasons[0]["message"]
