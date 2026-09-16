"""CG-12 — a face field is a label, not a paragraph.

Two measured failures, one class. A 20-40-word `window` clause was put in
a chip on the why-now card face and destroyed the strip's layout; a
150-character `detection_basis` was put in the tech register's right-hand
badge and overflowed every row. The renderer has since moved both to
where prose belongs; this is the other half of the repair, so the next
surface to put one on a face has a bounded string to put there.

The defective value here is verbatim: TS-201's 634-character,
three-sentence detection_basis, which the contract states as ONE CLAUSE.
The repair is never "cut words" — it is "move the argument to the field
that renders it", and the verdict says which one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import _check_face_budgets

# verbatim from the promoted run — 634 characters across three sentences
TS_201 = ("BCU's chief executive states a long-standing Lumin Digital "
          "partnership in the vendor's March 2025 release; BCU's own Elevate "
          "page describes the same upgraded platform. CONTRADICTION RESOLVED: "
          "the March 2026 technographic scan reports Alkami on bcu.org, which "
          "is the PREDECESSOR platform — BCU selected Alkami's ORB in February "
          "2016 (E-CC-009) and the member-facing platform was already Lumin by "
          "November 2022 (E-BCU-051), confirmed by the chief executive in "
          "March 2025 (E-CC-007). The scan's detection is a residual "
          "fingerprint on the domain, not a second live platform; both are "
          "dated, so this is a chronology rather than a conflict.")

# the same row's basis as ONE CLAUSE — 118 characters
TS_201_FIXED = ("The vendor's March 2025 release and the credit union's own "
                "Elevate page both place the platform in this estate.")


def _items(basis):
    return {"items": [{"ts_id": "TS-201", "vendor": "Lumin Digital",
                       "product": "Lumin Digital Banking", "layer": "CUST",
                       "status": "CONFIRMED", "detection_basis": basis}]}


def test_the_promoted_634_character_basis_is_refused():
    out = _check_face_budgets("techstack", "techstack", _items(TS_201))
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "CG-12" and r["severity"] == "block"
    assert r["path"] == "techstack.items[0].detection_basis"
    assert "634 characters" in r["message"]
    # the verdict names the slot and where the long form belongs
    assert "register row" in r["message"] and "dma_impact" in r["message"]


def test_the_one_clause_repair_passes():
    assert _check_face_budgets("techstack", "techstack",
                               _items(TS_201_FIXED)) == []


def test_a_second_sentence_is_refused_even_inside_the_character_budget():
    two = ("The vendor's release names the product. The scan corroborates it "
           "on the domain.")
    out = _check_face_budgets("techstack", "techstack", _items(two))
    assert len(out) == 1 and "2 sentences" in out[0]["message"]


def test_the_window_clause_holds_its_contract_budget_both_ways():
    """20-40 words. The promoted clause (25 words) passes; a paragraph
    pushed into the same field does not, and neither does a stub."""
    promoted = ("The opening runs from announcement to the start of "
                "systems-integration planning; no dated close is established "
                "yet, so the window is the pre-integration design phase.")
    body = {"signals": [{"wn_id": "WN-1", "window": promoted}]}
    assert _check_face_budgets("overview", "why_now", body) == []

    body["signals"][0]["window"] = promoted + " " + promoted
    out = _check_face_budgets("overview", "why_now", body)
    assert len(out) == 1 and "words against a budget of 40" in out[0]["message"]

    body["signals"][0]["window"] = "Closes at conversion."
    out = _check_face_budgets("overview", "why_now", body)
    assert len(out) == 1 and "under the stated floor of 20" in out[0]["message"]


def test_a_client_visible_gate_label_stays_a_sentence():
    body = {"gates": [{"gate_id": "SG-S8", "result": "PASS",
                       "plain_label": "Sentiment rests on more than one line"}]}
    assert _check_face_budgets("heatmap", "safeguard_gates", body) == []
    body["gates"][0]["plain_label"] = "Thin"
    out = _check_face_budgets("heatmap", "safeguard_gates", body)
    assert len(out) == 1 and out[0]["gate_id"] == "CG-12"


def test_a_nested_chip_is_reachable_at_two_star_levels():
    """The registry has to reach `tiles[*].addressable_cells[*].field` —
    a path walker that stopped at one level would police nothing on the
    surfaces that nest, and say nothing about it."""
    body = {"tiles": [{"addressable_cells": [
        {"subcap_id": "P4C3.1.1",
         "feature_that_addresses_it": "Reusable APIs for merger data "
                                      "conversion"},
        {"subcap_id": "P4C3.1.2",
         "feature_that_addresses_it": "An integration backbone that also "
                                      "carries the merger conversion, the "
                                      "member 360 and the servicing history"},
    ]}]}
    out = _check_face_budgets("overview", "opportunity", body)
    assert len(out) == 1
    assert out[0]["path"] == \
        "opportunity.tiles[0].addressable_cells[1].feature_that_addresses_it"


def test_a_section_with_no_registered_face_field_is_untouched():
    assert _check_face_budgets("context", "timeline",
                               {"events": [{"body": "x" * 900}]}) == []


# ── the prerequisite status chip ─────────────────────────────────────────
#
# Measured on Golden 1, run 40971653, promoted 2026-09-02T14:35:12Z. The
# recommendation panel renders `prerequisites[*].basis` as a pill beside the
# condition sentence. Eleven of the run's twelve prerequisites carried a
# 206-291 character paragraph there; it overflowed the pill, clipped
# mid-sentence, and overlapped the row beneath. The twelfth read "Evidenced"
# and rendered correctly — the payload stated the slot's real shape itself.
#
# `platform.recommendations` had no budget registered at all, which is why
# CG-12 was silent on a defect it was built for. Both values below are
# verbatim from that promoted payload.

REC_01_BASIS = (
    "Golden 1's own July 2024 enterprise discovery is the record here, and "
    "it registers no future-state data architecture; what would settle it is "
    "an authored target-state architecture with a named owner, which the "
    "served Enterprise Data Architecture figure of 3.0 against a 3.5 minimum "
    "reflects.")


def _prereq(basis):
    return {"recommendations": [{
        "rec_id": "REC-01",
        "prerequisites": [
            {"condition": "A future-state enterprise reference architecture "
                          "is authored and owned.",
             "basis": basis,
             "note": "What is already true is the substrate."},
        ]}]}


def test_the_promoted_291_character_prerequisite_basis_is_refused():
    out = _check_face_budgets("platform", "recommendations",
                              _prereq(REC_01_BASIS))
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "CG-12" and r["severity"] == "block"
    assert r["path"] == \
        "recommendations.recommendations[0].prerequisites[0].basis"
    assert "291 characters" in r["message"]
    # the verdict names the slot and where the displaced prose belongs
    assert "status chip" in r["message"] and "`note`" in r["message"]


def test_the_short_status_label_that_already_rendered_passes():
    """The twelfth prerequisite. It was always correct and must stay so."""
    assert _check_face_budgets("platform", "recommendations",
                               _prereq("Evidenced")) == []


def test_a_two_sentence_label_is_refused_inside_the_character_budget():
    """A label is one clause. Two short sentences fit 60 characters and are
    still a paragraph in a pill."""
    out = _check_face_budgets("platform", "recommendations",
                              _prereq("Not evidenced. An audit would settle."))
    assert len(out) == 1 and "2 sentences" in out[0]["message"]


def test_every_prerequisite_in_the_promoted_run_is_swept():
    """Item grain, not section grain: the defect hid in an array inside an
    array, which is where CG-13's own history says these things hide."""
    body = {"recommendations": [
        {"rec_id": "REC-01", "prerequisites": [
            {"basis": "Evidenced"}, {"basis": REC_01_BASIS}]},
        {"rec_id": "REC-02", "prerequisites": [{"basis": REC_01_BASIS}]},
    ]}
    out = _check_face_budgets("platform", "recommendations", body)
    assert len(out) == 2
    assert [r["path"] for r in out] == [
        "recommendations.recommendations[0].prerequisites[1].basis",
        "recommendations.recommendations[1].prerequisites[0].basis"]
