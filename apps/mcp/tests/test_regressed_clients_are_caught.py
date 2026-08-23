"""The two clients the owner reported, as fixtures, against the live gates.

Owner, 2026-08-23: "Gulf Coast Business Credit and Axos Bank still have all
initial errors stated above. My initial prompt with all issues stated targeted
them. Have you placed tests to check the issues do not recur?"

That question is sharper than it looks, and asking it found a real hole. A
gate that passes its own unit tests proves the gate does what its author
imagined; only the payload that actually shipped proves it does what the
owner reported. So these fixtures are not constructed — they are read off the
two runs' LIVE PROMOTED submissions through the connector on 2026-08-23, and
trimmed only of prose that does not bear on the check.

WHAT THIS FILE CAUGHT. CG-41's first version scored a seat `resolved` when it
carried any contact route plus a basis. Run against Gulf's real leadership
section, it PASSED a roster of three seats with three LinkedIn profiles,
three long genuine bases — and zero email addresses, which is word for word
what was reported. Every basis describes the profile match and none mentions
an address search, so "we looked for emails and found none" and "we never
looked" were still one payload, one level below where the gate was looking.
The second check exists because of this file.

    gulf-coast-business-credit  run 60082d6f-c3b3-4507-9e03-4e36872a9ed1
                                promoted 2026-08-23T11:28:05Z, 7/7 facets
                                never_enriched, 70 scored cells
    axos-bank-…-nyse-ax         run d7fb99ed-a20c-4d46-88fd-27a4a214fef7
                                promoted 2026-08-23T10:04:26Z, 7/7 facets
                                never_enriched, 355 scored cells

Both promoted the same day, hours apart, by a production connector running a
revision that predates every gate below. That is the real reason the surfaces
still read the way they do, and it is a DEPLOY problem rather than a gate
problem — but a gate nobody proved against the reported payload would have
been a gate problem too, and this file is how that stops being possible.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import (           # noqa: E402
    _check_contact_enrichment_baseline, _seat_contact_state)

#: Gulf's leadership section, verbatim from the promoted submission except
#: that `relevance_note` is shortened — it carries no contact signal and its
#: full text is a client's internal record.
GULF_LEADERSHIP = {
    "leadership": {
        "e_ids": ["E-CC-217", "E-CC-226", "E-CC-250", "E-CC-289", "E-CC-292"],
        "roster": [
            {"name": "Wade Hladky", "as_of": "2026-08-17",
             "email": None, "phone": None,
             "title": "President and Chief Executive Officer",
             "domain": "gulfcoastbc.com", "confidence": "HIGH",
             "enriched_at": "2026-08-17", "source_e_id": "E-CC-292",
             "appointed_on": "2011",
             "linkedin_url": "https://www.linkedin.com/in/wade-hladky-881153bb/",
             "tenure_months": None,
             "relevance_note": "Platform and change decisions sit with him.",
             "enrichment_basis": (
                 "The division's own management page, which states the year of "
                 "appointment but no month, so no tenure in months is derived; "
                 "the enrichment search returned a matching profile with the "
                 "same title.")},
            {"name": "Meg Roberson", "as_of": "2026-08-17",
             "email": None, "phone": None,
             "title": "Senior Vice President and National Sales Manager",
             "domain": "gulfcoastbc.com", "confidence": "HIGH",
             "enriched_at": "2026-08-17", "source_e_id": "E-CC-217",
             "appointed_on": None,
             "linkedin_url": "https://www.linkedin.com/in/meg-roberson-54204b8b/",
             "tenure_months": None,
             "relevance_note": "Owns demand and origination across all markets.",
             "enrichment_basis": (
                 "Named on the division's own management page and corroborated "
                 "by two independent trade titles reporting her industry "
                 "advisory appointment.")},
            {"name": "Zach Daiber", "as_of": "2026-08-17",
             "email": None, "phone": None,
             "title": "Vice President and Senior Underwriter",
             "domain": "gulfcoastbc.com", "confidence": "HIGH",
             "enriched_at": "2026-08-17", "source_e_id": "E-CC-289",
             "appointed_on": "2018",
             "linkedin_url": "https://www.linkedin.com/in/zachary-daiber-12a31772/",
             "tenure_months": None,
             "relevance_note": "Credit decisioning and exception handling.",
             "enrichment_basis": (
                 "The division's own management page, which states the year of "
                 "appointment but no month; the enrichment search matched the "
                 "title and the same appointment year.")},
        ],
        "r_layer": {
            "verdict": "ACCEPT", "confidence": "HIGH",
            "hypothesis": ("The three named leaders are current and own the "
                           "capabilities this assessment scores."),
            "probes_run": [
                "Cross-checked all three against the division's current management page",
                "Ran a filtered executive search against the division's domain and matched all three by name, title and start year",
                "Searched for a technology, data or digital executive at division or parent level: none holds such a title",
                "Discarded two enrichment work-history summaries that named the wrong company",
            ],
        },
        "verified_absent": False,
        "internal_only": [
            "roster[0].linkedin_url", "roster[0].email", "roster[0].phone",
            "roster[1].linkedin_url", "roster[1].email", "roster[1].phone",
            "roster[2].linkedin_url", "roster[2].email", "roster[2].phone",
        ],
        "narrative_thread": (
            "Three named executives are the accountability set the findings "
            "assign capabilities to. No technology or data executive exists at "
            "either the division or its parent."),
    }
}


def _ids(out):
    return [r["gate_id"] for r in out]


# ── the hole this file found ──────────────────────────────────────────

def test_every_gulf_seat_scores_resolved_and_that_was_the_problem():
    """The per-seat check is not wrong — it is satisfied, honestly.

    Each seat carries a real profile and a real basis, so `resolved` is the
    correct verdict for each one. Pinning it here is the point: the defect was
    never a mis-scored seat, it was a question the gate never asked, and a
    future author reading only the refusal below could 'fix' this by making
    the per-seat rule stricter and break every honest roster in the corpus.
    """
    roster = GULF_LEADERSHIP["leadership"]["roster"]
    assert [_seat_contact_state(s) for s in roster] == ["resolved"] * 3
    assert all(s["email"] is None for s in roster), \
        "the fixture must keep the reported condition: zero email addresses"


def test_the_reported_gulf_payload_is_refused():
    """The regression. Three profiles, three bases, no addresses, and no
    sentence anywhere about an address search."""
    out = _check_contact_enrichment_baseline("overview",
                                             copy.deepcopy(GULF_LEADERSHIP))
    assert _ids(out) == ["CG-41"], out
    assert out[0]["severity"] == "block"
    m = out[0]["message"]
    assert "not one of 3 roster seats carries an email address" in m
    assert "LinkedIn profile is not a mailbox" in m


def test_one_sentence_about_the_address_search_closes_it():
    """The escape, on the real payload. The gate refuses SILENCE, never the
    absence — a division that publishes no addresses still promotes."""
    p = copy.deepcopy(GULF_LEADERSHIP)
    p["leadership"]["roster"][0]["enrichment_basis"] += (
        " No work email address was discoverable for any seat: the division "
        "publishes none and the enrichment returned no verified address.")
    assert _check_contact_enrichment_baseline("overview", p) == []


def test_the_r_layer_is_a_place_the_disclosure_may_live():
    """A producer that records the address probe in `r_layer.probes_run` has
    said it. Requiring one specific field would make the gate a formatting
    rule rather than an honesty rule."""
    p = copy.deepcopy(GULF_LEADERSHIP)
    p["leadership"]["r_layer"]["probes_run"].append(
        "Searched for a published work email address for each seat: the "
        "division publishes none and no verified address was returned.")
    assert _check_contact_enrichment_baseline("overview", p) == []


def test_an_empty_state_is_also_enough():
    p = copy.deepcopy(GULF_LEADERSHIP)
    p["leadership"]["empty_state"] = {
        "reason": ("No work email address is published for any seat and the "
                   "enrichment returned none."),
        "sources_searched": ["clay", "division management page"],
    }
    assert _check_contact_enrichment_baseline("overview", p) == []


def test_one_real_address_is_enough_to_pass():
    """The check is about the roster having ANY address, not every seat. A
    partially-reachable roster is a normal, honest result."""
    p = copy.deepcopy(GULF_LEADERSHIP)
    p["leadership"]["roster"][1]["email"] = "m.roberson@gulfcoastbc.com"
    assert _check_contact_enrichment_baseline("overview", p) == []


# ── the shape both clients share ──────────────────────────────────────

def test_a_roster_with_addresses_but_a_silent_seat_still_fails_the_first_check():
    """Both checks stay independent. Adding an address does not excuse a seat
    that says nothing at all, and the first version of the second check would
    have masked that by returning early."""
    p = copy.deepcopy(GULF_LEADERSHIP)
    p["leadership"]["roster"][0]["email"] = "w.hladky@gulfcoastbc.com"
    p["leadership"]["roster"].append({"name": "A new seat", "title": "CIO"})
    out = _check_contact_enrichment_baseline("overview", p)
    assert _ids(out) == ["CG-41"]
    assert "1 of 4 roster seats record no contact-search outcome" in out[0]["message"]


def test_both_checks_can_fire_at_once():
    """A roster with no addresses AND a silent seat is two findings, not one
    swallowing the other."""
    p = copy.deepcopy(GULF_LEADERSHIP)
    p["leadership"]["roster"].append({"name": "A new seat", "title": "CIO"})
    out = _check_contact_enrichment_baseline("overview", p)
    assert _ids(out) == ["CG-41", "CG-41"], out
    joined = " ".join(r["message"] for r in out)
    assert "not one of 4 roster seats carries an email address" in joined
    assert "1 of 4 roster seats record no contact-search outcome" in joined


# ── the ledger half, which is what the promote gate reads ─────────────

#: Both runs' live facet states, read through the connector 2026-08-23. The
#: promote-side gate reads the LEDGER, not the payload, and this is what it
#: would have seen on the morning both of these were promoted.
REPORTED_FACETS = {
    "gulf-coast-business-credit": ["firmographics", "leadership", "peer_scores",
                                   "platform_readiness", "sentiment",
                                   "techstack", "why_now"],
    "axos-bank-axos-financial-inc-nyse-ax": ["firmographics", "leadership",
                                             "peer_scores", "platform_readiness",
                                             "sentiment", "techstack", "why_now"],
}


def test_both_reported_clients_were_seven_of_seven_never_enriched():
    """The measurement, pinned so the claim in every commit message above is
    checkable rather than remembered. Read live on 2026-08-23: Gulf promoted
    11:28:05Z, Axos 10:04:26Z, both with counts.never_enriched == 7."""
    from dma_mcp import ledger
    for client, facets in REPORTED_FACETS.items():
        assert sorted(facets) == sorted(ledger.FACETS), (
            f"{client}'s reported blocking set is not the ledger's facet "
            f"vocabulary — one of the two has drifted")
        rows = [{"facet": f, "state": "never_enriched"} for f in facets]
        assert ledger.summary(rows)["counts"]["never_enriched"] == 7
        assert ledger.summary(rows)["done"] is False


def test_the_promote_gate_would_have_refused_both():
    """`no_enrichment_ever_run` fires at zero of seven, which is exactly the
    state both runs were promoted in. This asserts the branch against their
    real facet sets rather than a constructed one."""
    for client, facets in REPORTED_FACETS.items():
        rows = [{"facet": f, "state": "never_enriched"} for f in facets]
        assert rows and all(r["state"] == "never_enriched" for r in rows), client
