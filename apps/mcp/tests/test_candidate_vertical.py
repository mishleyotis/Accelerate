"""ET-06 — the candidate set is bounded by the entity's vertical.

Baxter Credit Union's promoted platform page carried six "considered and
set aside" cards. One of them was this, verbatim:

    {"platform": "Insurance policy administration and claims",
     "relevance": 0.15,
     "reason": "Out of vertical: its anchor cells belong to a carrier
                entity type and none of them are cells this credit-union
                assessment scores."}

The producer knew. It said so in the reason it wrote, and it listed the
platform anyway, because the contract named out-of-vertical as a DROP
rule and a drop rule produces a card. So a credit union's platform
surface spent one of six client-facing slots explaining why an insurance
carrier product does not apply to a credit union.

ET-05 already refuses a foreign CELL reaching a sentence. This is the
other half: a foreign PLATFORM reaching the shortlist. The vertical
bounds the candidate set before relevance is scored — a platform outside
it was never weighed, so it has no discard to render.

What must keep passing matters as much: a discard list is evidence of
judgement, and "why not X" is the question an AE gets asked. Every
discard that argues from adoption, coverage or the arithmetic stays.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from dma_mcp.gates import GATES
from dma_mcp.validation2 import _check_candidate_vertical

# verbatim from the promoted platform payload (run c1351d25, BCU)
PROMOTED_DISCARDS = [
    {"platform": "Salesforce Marketing Cloud", "relevance": 0.85,
     "reason": "Already deployed inside the nine-product estate, so the "
               "useful conversation is adoption depth rather than fit."},
    {"platform": "Financial Services Cloud", "relevance": 0.85,
     "reason": "Already deployed as part of the same estate; the industry "
               "data model is in place and the opportunity sits upstream "
               "of it."},
    {"platform": "Agentforce expansion", "relevance": 0.9,
     "reason": "Already in production for inbound service; expansion is "
               "sequenced behind the member-data layer it would read, so "
               "it is a phase rather than a fit claim."},
    {"platform": "Experience Cloud", "relevance": 0.4,
     "reason": "The member digital-banking layer is served by an incumbent "
               "platform, and replacing it is not a constraint this "
               "assessment surfaces."},
    {"platform": "Digital lending origination platform", "relevance": 0.8,
     "reason": "This layer is occupied and performing: digital origination "
               "is in production with measured identity, funding and "
               "conversion rates."},
    {"platform": "Insurance policy administration and claims",
     "relevance": 0.15,
     "reason": "Out of vertical: its anchor cells belong to a carrier "
               "entity type and none of them are cells this credit-union "
               "assessment scores."},
]


def _page(discards):
    return {"platform_story": {"platforms": [], "discarded": discards}}


def test_the_promoted_card_is_refused_and_only_that_one():
    out = _check_candidate_vertical("platform", _page(PROMOTED_DISCARDS), "CU")
    assert len(out) == 1, [r["path"] for r in out]
    reason = out[0]
    assert reason["gate_id"] == "ET-06"
    assert reason["severity"] == "block"
    assert reason["section"] == "platform_story"
    assert reason["path"] == "platform_story.discarded[5]"
    assert "Insurance policy administration and claims" in reason["message"]
    assert "credit unions" in reason["message"]


def test_the_verdict_says_remove_rather_than_re_score():
    """The wrong repair is lowering the relevance to 0.05 and keeping the
    card. The message has to close that door, because it is the cheaper
    move and it leaves the defect on the page."""
    (reason,) = _check_candidate_vertical("platform",
                                          _page(PROMOTED_DISCARDS), "CU")
    assert "not a candidate" in reason["message"]
    assert "before any relevance is scored" in reason["message"].lower()
    assert "remove the entry" in reason["message"].lower()


def test_a_legitimate_discard_passes():
    """Already deployed at that layer — the discard a client actually asks
    about, and the reason an AE needs in the room."""
    marketing = [{"platform": "Marketing Cloud", "relevance": 0.85,
                  "reason": "Already deployed — the conversation is adoption "
                            "depth, not fit."}]
    assert _check_candidate_vertical("platform", _page(marketing), "CU") == []


@pytest.mark.parametrize("reason", [
    "Already deployed at this layer; the conversation is adoption depth.",
    "Addresses two cells, below the three-cell floor for a tile.",
    "Relevance of 0.31 puts it below the line the arithmetic draws.",
    "The member digital-banking layer is served by an incumbent platform.",
    "Their insurance brokerage subsidiary already runs it, so the layer is "
    "occupied rather than open.",
    "Twilio Engage overlaps Marketing Cloud, which is already deployed.",
])
def test_discards_that_argue_from_the_estate_or_the_numbers_all_pass(reason):
    """The gate matches the vocabulary of BELONGING, not the mention of
    another industry. A credit union with an insurance brokerage subsidiary
    must still be able to say so in a discard reason."""
    page = _page([{"platform": "X", "relevance": 0.4, "reason": reason}])
    assert _check_candidate_vertical("platform", page, "CU") == []


@pytest.mark.parametrize("reason", [
    "Out of vertical: its anchor cells belong to a carrier entity type.",
    "Out-of-vertical for a credit union.",
    "This sits in a different vertical entirely.",
    "Anchor cells are from another sub-vertical.",
    "Outside the credit-union vertical.",
    "Built for a different entity type than this institution.",
    "The buyer is not a credit union but an insurance carrier.",
])
def test_every_way_of_saying_out_of_vertical_is_refused(reason):
    page = _page([{"platform": "X", "relevance": 0.15, "reason": reason}])
    out = _check_candidate_vertical("platform", page, "CU")
    assert len(out) == 1 and out[0]["gate_id"] == "ET-06"


def test_anchor_cells_refuse_a_discard_that_says_nothing_about_vertical():
    """The structural half. A producer that drops the give-away sentence
    and keeps the platform is still pointing at somebody else's cells."""
    page = _page([{"platform": "Policy administration", "relevance": 0.15,
                   "reason": "Addresses too few of this run's cells.",
                   "anchor_cells": ["P2C2.1.IC1", "P2C2.4.IC3"]}])
    out = _check_candidate_vertical("platform", page, "CU")
    assert len(out) == 1
    assert "P2C2.1.IC1" in out[0]["message"]
    assert "insurance carriers" in out[0]["message"]
    assert "credit unions" in out[0]["message"]


def test_a_discard_anchored_on_base_and_own_variant_cells_passes():
    page = _page([{"platform": "Experience Cloud", "relevance": 0.4,
                   "reason": "The layer is occupied by an incumbent.",
                   "anchor_cells": ["P2C2.1.1", "P2C2.7.CU1", "P1C2.7.BK1"]}])
    assert _check_candidate_vertical("platform", page, "CU") == []


def test_the_overview_tiles_discard_list_is_reached_too():
    """O-page tiles carry the same discard rule and the same defect class;
    the gate is keyed on the list, not on the page."""
    page = {"tiles": {"tiles": [], "discarded": [
        {"platform": "Policy administration",
         "reason": "Out of vertical — a carrier product."}]}}
    out = _check_candidate_vertical("overview", page, "CU")
    assert len(out) == 1 and out[0]["section"] == "tiles"


def test_an_unknown_sub_vertical_refuses_nothing():
    """The same one-sided choice ET-05 and the API's `serves` make: not
    knowing who you are is not grounds for refusing anything."""
    assert _check_candidate_vertical("platform",
                                     _page(PROMOTED_DISCARDS), None) == []


def test_the_gate_is_in_the_registry_and_blocks():
    name, plain_label, checks, why, on_failure = GATES["ET-06"]
    assert on_failure == "block"
    assert plain_label is None          # ET is not a client-visible safeguard
    assert "vertical" in name.lower()
    assert "candidate" in checks.lower() or "candidate" in name.lower()
