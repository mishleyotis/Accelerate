"""AG-14 / AG-13 — recommendations are stress-tested, and a first place won
on breadth or sequencing argues for itself.

Owner, 2026-10-05: "most just seem to be prioritizing MuleSoft just because
there are many systems. The recommendations are not rebutted to ensure
stress testing." On Cross Insurance Agency, Addressable opportunity read
0.987-0.991 on all five cards, so interconnect and a declared dependency put
the integration hub first, and no card recorded how its counter was settled.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from dma_mcp import gates as G  # noqa: E402
from dma_mcp import validation2 as V  # noqa: E402

COUNTER = ("Consolidating onto one agency management system could come first "
           "and make an integration layer smaller than this card assumes; a "
           "buyer could reasonably extend the existing Salesforce organisation "
           "with native connectors and defer the middleware decision a year.")
REBUTTAL = ("Rebuttal: consolidation was weighed against the CIO's statement "
            "that both agency systems stay in service through 2027 "
            "[E-CROSSINS-015]; the counter does not hold for this client.")


def _card(name, rank, opp, inter, sub, basis="fit", probes=None,
          counter=COUNTER):
    return {"platform": name, "rank": rank, "fit_score": round(sub * 62, 1),
            "subtotal": sub, "rank_basis": basis,
            "factors": [
                {"name": "Addressable opportunity", "value": opp,
                 "contribution": 0.66 * opp},
                {"name": "Catalogue interconnect", "value": inter,
                 "contribution": 0.26 * inter},
                {"name": "Greenfield family", "value": 0.0, "contribution": 0.0},
                {"name": "Strategic alignment", "value": 0.0, "contribution": 0.0}],
            "r_layer": {"hypothesis": "h", "counter": counter, "verdict": "SHIP",
                        "probes_run": list(probes if probes is not None
                                           else [REBUTTAL])}}


def _page(cards, recs=()):
    return {"platform_story": {"platforms": cards,
                               "discarded": [{"platform": "Snowflake / Power BI"}]},
            "recommendations": {"recommendations": list(recs)}}


HUB = _card("MuleSoft Anypoint Platform", 1, 0.987, 0.34,
            0.66 * 0.987 + 0.26 * 0.34, basis="sequenced: Data Cloud waits on it")
DC = _card("Salesforce Data Cloud", 2, 0.989, 0.25, 0.66 * 0.989 + 0.26 * 0.25)


def test_both_gates_are_registered_and_block():
    for g in ("AG-14", "AG-13"):
        assert G.GATES[g][-1] == "block"


# ── AG-14 ──────────────────────────────────────────────────────────────

def test_a_fought_rebuttal_passes():
    assert V._check_rebuttals("platform", _page([copy.deepcopy(DC)])) == []


def test_a_counter_naming_no_alternative_is_refused():
    vague = ("This might not work for every client and there are risks "
             "involved in any programme of this size, so confidence is held "
             "low until discovery confirms the scope, the budget and the team "
             "that would own it day to day.")
    out = V._check_rebuttals("platform", _page([_card("Salesforce Data Cloud",
                                                      1, .9, .2, .7,
                                                      counter=vague)]))
    assert out and out[0]["gate_id"] == "AG-14"
    assert "names no specific alternative" in out[0]["message"]


def test_a_discarded_platform_named_by_its_part_counts_as_an_alternative():
    c = ("Snowflake already holds the analytics data the client reports from, "
         "so extending that warehouse with its own marketplace connectors "
         "could deliver the unified view without a second data platform, at "
         "lower cost and with a team that already knows the tooling well.")
    assert V._check_rebuttals("platform", _page([_card("Salesforce Data Cloud",
                                                       1, .9, .2, .7,
                                                       counter=c)])) == []


def test_a_rebuttal_with_no_resolution_probe_is_refused():
    out = V._check_rebuttals("platform", _page([_card("Salesforce Data Cloud",
                                                      1, .9, .2, .7,
                                                      probes=[])]))
    assert "Rebuttal:" in out[0]["message"]


def test_a_rebuttal_probe_must_cite_what_settled_it():
    out = V._check_rebuttals("platform", _page([_card(
        "Salesforce Data Cloud", 1, .9, .2, .7,
        probes=["Rebuttal: considered and rejected."])]))
    assert out and out[0]["gate_id"] == "AG-14"


def test_a_short_counter_is_refused():
    out = V._check_rebuttals("platform", _page([_card(
        "Salesforce Data Cloud", 1, .9, .2, .7, counter="Consolidate first.")]))
    assert "words" in out[0]["message"]


def test_recommendations_are_held_to_the_same_rule():
    rec = {"rec_id": "REC-01", "l3_area": "[L3-MS-ANYPOINT] MuleSoft",
           "r_layer": {"counter": "Too short.", "verdict": "SHIP",
                       "probes_run": []}}
    out = V._check_rebuttals("platform", _page([copy.deepcopy(DC)], [rec]))
    assert [r["path"] for r in out] == \
        ["recommendations.recommendations[0].r_layer"]


def test_other_pages_are_untouched():
    assert V._check_rebuttals("overview", _page([_card("X", 1, .9, .2, .7,
                                                       probes=[])])) == []


# ── AG-13 ──────────────────────────────────────────────────────────────

def test_a_sequenced_hub_on_saturated_opportunity_must_pass_a_lead_test():
    out = V._check_lead_is_earned("platform", _page([copy.deepcopy(HUB),
                                                     copy.deepcopy(DC)]))
    assert out and out[0]["gate_id"] == "AG-13"
    assert "count of systems is not a constraint" in out[0]["message"]


def test_an_interconnect_led_hub_is_caught_without_a_declared_sequence():
    hub = copy.deepcopy(HUB)
    hub["rank_basis"] = "fit"
    out = V._check_lead_is_earned("platform", _page([hub, copy.deepcopy(DC)]))
    assert out and "Catalogue interconnect" in out[0]["message"]


def test_a_lead_test_citing_client_evidence_clears_it():
    hub = copy.deepcopy(HUB)
    hub["r_layer"]["probes_run"].append(
        "Lead test: the client's renewal team re-keys every policy between "
        "the two agency systems [E-CROSSINS-041], so integration is the "
        "constraint the later cards wait on.")
    assert V._check_lead_is_earned("platform",
                                   _page([hub, copy.deepcopy(DC)])) == []


def test_a_lead_won_on_opportunity_needs_no_lead_test():
    lead = _card("Salesforce Data Cloud", 1, 0.95, 0.1, 0.66 * .95 + .026)
    nxt = _card("MuleSoft Anypoint Platform", 2, 0.70, 0.3, 0.66 * .7 + .078)
    assert V._check_lead_is_earned("platform", _page([lead, nxt])) == []


def test_unsaturated_opportunity_needs_no_lead_test():
    hub = copy.deepcopy(HUB)
    hub["factors"][0]["value"] = 0.90
    assert V._check_lead_is_earned("platform",
                                   _page([hub, copy.deepcopy(DC)])) == []
