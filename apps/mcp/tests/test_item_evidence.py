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
                     "new_evidence_ids": [], "sources_searched": ["ncua.gov", 'query: "x"'],
                     "queries_run": ["q"]}
    bare = {"subcap_id": "P2C2.x.9", "state": "WORKED_ABSENT",
            "new_evidence_ids": []}
    assert _asserts_nothing(worked_absent) is True
    assert _asserts_nothing(bare) is False
    assert _ag03("heatmap", {"alerts": {"alerts": [worked_absent]}}) == []
    assert len(_ag03("heatmap", {"alerts": {"alerts": [bare]}})) == 1


def test_ag03_is_bound_to_the_item_shape_so_an_invented_key_buys_nothing():
    """The Frost hole, measured: 394 of 697 `cell_evidence.cells` carried
    `state` + `sources_searched`, neither of them in H2's item shape. CG-04
    sweeps SECTION keys only so they validated; no writer binds them so
    promotion dropped them — and in between they bought this exemption. The
    exemption is a contract route or it is nothing."""
    from dma_mcp.vacuity import item_keys
    cells = item_keys("heatmap", "cell_evidence", "cells")
    alerts = item_keys("heatmap", "alerts", "alerts")
    invented = {"subcap_id": "P2C2.x.7", "state": "WORKED_ABSENT",
                "sources_searched": ["ncua.gov", 'query: "x"']}
    assert _asserts_nothing(invented, alerts) is True     # alerts declares it
    assert _asserts_nothing(invented, cells) is False     # cell_evidence does not
    # unbound (declared=None) stays permissive — callers with no shape in hand
    assert _asserts_nothing(invented) is True


def test_the_declared_cell_absence_trio_is_exempt_and_thin_alone_is_not():
    """0041: the TRD's cell-grain protocol — thin + sources_searched +
    closure_condition — now has storage and is declared, so AG-03 honours it.
    `thin` on its own marks a cell short of evidence that still owes its
    argument; honouring that alone would be a switch, not a gate."""
    from dma_mcp.vacuity import item_keys
    cells = item_keys("heatmap", "cell_evidence", "cells")
    full = {"subcap_id": "P2C2.x.7", "e_ids": [], "thin": True,
            "sources_searched": ["sec.gov filings", 'query: "case routing"'],
            "closure_condition": "A dated artefact naming this capability."}
    assert _asserts_nothing(full, cells) is True
    assert _asserts_nothing({**full, "closure_condition": ""}, cells) is False
    assert _asserts_nothing({"subcap_id": "P2C2.x.8", "thin": True}, cells) is False
    assert _ag03("heatmap", {"cell_evidence": {"cells": [full]}}) == []
    bare = {"subcap_id": "P2C2.x.8", "e_ids": [], "thin": True,
            "synthesis": "The capability is not visible in this corpus."}
    reasons = _ag03("heatmap", {"cell_evidence": {"cells": [bare]}})
    assert len(reasons) == 1
    # the verdict names the route this shape HAS, so nobody has to invent one
    assert "thin + sources_searched + closure_condition" in reasons[0]["message"]


def test_a_state_asserting_a_find_with_no_id_is_a_contradiction():
    """WORKED_FOUND with an empty id list is not an empty state."""
    payload = {"alerts": {"alerts": [
        {"subcap_id": "P2C1.x.4", "state": "WORKED_FOUND",
         "new_evidence_ids": [], "sources_searched": ["ncua.gov"], "queries_run": ['"q"']}]}}
    reasons = _ag03("heatmap", payload)
    assert len(reasons) == 1
    assert "contradiction" in reasons[0]["message"]


# ── AG-04 · a technographic claim about a named peer carries its source ──────
from dma_mcp.validation2 import _check_peer_research  # noqa: E402


def _ts(item):
    # The payload is keyed by SECTION name; on this page the section is also
    # called "techstack", so the body nests under it.
    return {"techstack": {"items": [
        {"ts_id": "TS-101", "product": "Symitar Episys",
         "status": "CONFIRMED", "e_ids": ["E-1"], **item}]}}


def test_a_share_with_no_breakdown_is_refused():
    # The version this replaces derived the per-peer verdict from
    # hashCode(ts_id + peerName), so "deployed" beside a real credit union was a
    # function of an id's characters.
    r = _check_peer_research("techstack", _ts({"peer_coverage": 0.6}))
    assert len(r) == 1 and r[0]["gate_id"] == "AG-04"
    assert "no per-peer breakdown" in r[0]["message"]


def test_a_deployed_row_needs_a_source_and_a_date():
    r = _check_peer_research("techstack", _ts({
        "peer_coverage": 0.5,
        "peer_deployments": [
            {"peer": "Alliant Credit Union", "deployed": True},
            {"peer": "CEFCU", "deployed": False},
        ]}))
    msgs = " ".join(x["message"] for x in r)
    assert "Alliant Credit Union" in msgs
    assert "source_url" in msgs and "as_of" in msgs


def test_a_peer_that_could_not_be_established_is_legal_as_null():
    # This is the whole point: 2 of 5 with 3 unknowns must be expressible.
    r = _check_peer_research("techstack", _ts({
        "peer_coverage": 0.4,
        "peer_deployments": [
            {"peer": "Alliant Credit Union", "deployed": True,
             "source_url": "https://example.org/a", "as_of": "2026-03-01"},
            {"peer": "CEFCU", "deployed": True,
             "source_url": "https://example.org/b", "as_of": "2025-11-14"},
            {"peer": "Consumers Credit Union", "deployed": None},
            {"peer": "GreenState Credit Union", "deployed": None},
            {"peer": "Lake Michigan Credit Union", "deployed": None},
        ]}))
    assert r == []


def test_a_share_that_disagrees_with_its_own_breakdown_is_named():
    r = _check_peer_research("techstack", _ts({
        "peer_coverage": 0.9,
        "peer_deployments": [
            {"peer": "A", "deployed": True, "source_url": "https://x", "as_of": "2026-01-01"},
            {"peer": "B", "deployed": False},
            {"peer": "C", "deployed": False},
        ]}))
    assert len(r) == 1
    assert "disagrees with its own breakdown" in r[0]["message"]
    assert "1 of 3" in r[0]["message"]


def test_one_peer_of_tolerance_so_a_scoped_share_passes():
    # Scoping the share to the established subset is legitimate; being wrong by
    # more than one peer is not.
    body = _ts({"peer_coverage": 1.0, "peer_deployments": [
        {"peer": "A", "deployed": True, "source_url": "https://x", "as_of": "2026-01-01"},
        {"peer": "B", "deployed": None},
    ]})
    assert _check_peer_research("techstack", body) == []


def test_a_row_with_neither_field_is_untouched():
    assert _check_peer_research("techstack", _ts({})) == []


# ── ET-08 · a cell-link field carries a cell id ──────────────────────────
def test_a_capability_name_in_a_cell_link_field_is_refused():
    """The gap every other cell gate shares: they skip a value they cannot
    parse as an id, so a NAME in a cell-link field is invisible to all of
    them at once. Measured on the reference client — five platform
    starters naming their gap 'Technology Architecture & Integration.1.2'
    — refused by nothing, rendering a chip that opens onto no drawer."""
    from dma_mcp.validation2 import check_cell_id_shape
    payload = {"starters": {"starters": [
        {"rank": 1, "text": "An opener.",
         "named_gap_subcap_id": "Technology Architecture & Integration.1.2"},
        {"rank": 2, "text": "Another.", "named_gap_subcap_id": "P4C3.1.2"},
    ]}}
    out = check_cell_id_shape("platform", payload)
    assert len(out) == 1
    assert out[0]["gate_id"] == "ET-08"
    assert out[0]["path"] == "starters.starters[0].named_gap_subcap_id"
    assert "not a catalogue cell id" in out[0]["message"]


def test_et08_catches_the_grain_error_one_level_up():
    """A CATEGORY id where a cell id belongs is the same defect: P1C4 is a
    real catalogue id and not a cell, so the drawer it points at is a
    grain that has none."""
    from dma_mcp.validation2 import check_cell_id_shape
    payload = {"sentiment": {"themes": [
        {"theme": "service", "mapped_subcap_ids": ["P1C4", "P2C3.1.2"]}]}}
    out = check_cell_id_shape("overview", payload)
    assert [r["path"] for r in out] == ["sentiment.themes[0].mapped_subcap_ids[0]"]


def test_et08_is_silent_on_empty_and_on_well_formed_ids():
    """Deliberately narrow. An empty value is CG-02's business and a
    missing key is the contract's; a gate that fired on those would be
    three gates disagreeing about one field."""
    from dma_mcp.validation2 import check_cell_id_shape
    payload = {"starters": {"starters": [
        {"named_gap_subcap_id": ""}, {"named_gap_subcap_id": None},
        {"named_gap_subcap_id": "P3C3.4.RIA1"}, {"rank": 4},
        {"linked_subcap_ids": ["P1C1.1.1", "P2C2.3.2"]},
    ]}}
    assert check_cell_id_shape("platform", payload) == []
