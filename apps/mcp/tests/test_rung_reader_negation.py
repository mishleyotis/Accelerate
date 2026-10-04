"""The rung reader — negation, case, and the owner's failover default.

Review of fix/mcp-gates-contract (2026-10-04) measured three ways the RC-05
rung reader (validation.rung_outcome) read a ladder wrongly:

  * FAIL-OPEN on negation. The terminal tokens were matched case-sensitively
    and nothing negated them, so 'EDGAR: NOT CONFIRMED' read as terminal —
    the exact escape hatch RC-05 set out to close. 'not resolved',
    'unresolved', 'no result', a plain 'refused' and an HTTP 403 are not
    terminal successes either.
  * CASE. Honest registry rungs written in sentence case ('No enforcement
    actions found', 'Texas DOI: No orders found', 'SEC: verified absent')
    read as having NO outcome, and CG-40 refused them as silent.
  * FAILOVER. 'Exa NOT_RUN (credit); fell back to WebSearch: resolved, 3
    hits' read as OPEN, against the owner default of 2026-10-04: WebSearch /
    WebFetch is an accepted failover when Exa/Tavily credit is exhausted, so
    the failover's own outcome is the rung's outcome.

Case-insensitivity must not open a new hole of its own: an ordinary English
word that happens to be a status token ('negative news screening',
'confirmed peers') is not an outcome unless it sits where an outcome sits.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from dma_mcp.validation2 import (  # noqa: E402
    _check_c3_regulator_family, _check_depth_floors, _check_worked_absent_ladder,
    rung_outcome,
)


# ── negated outcomes are not terminal successes ──────────────────────────
@pytest.mark.parametrize("rung", [
    "EDGAR: NOT CONFIRMED",
    "EDGAR — not confirmed",
    "SEC adviser registry — Not Confirmed: page timed out",
    "Texas Department of Insurance orders — not resolved",
    "NMLS Consumer Access — UNRESOLVED: the search form returned an error",
    "Missouri DOI — unconfirmed",
    "BBB profile — not verified absent; the page did not load",
    "Exa search for the CFO's appointment — no result",
    "Tavily — no results",
    "Exa — 0 results returned",
    "Glassdoor — refused",
    "Glassdoor overview page — HTTP 403",
    "Indeed company page — 403 Forbidden",
    "Exa — credit exhausted",
    {"route": "EDGAR", "outcome": "not confirmed"},
    {"route": "BBB", "outcome": "Unresolved"},
])
def test_negated_outcomes_are_not_terminal(rung):
    assert rung_outcome(rung) == "open", rung


# ── outcomes are read in any case ────────────────────────────────────────
@pytest.mark.parametrize("rung", [
    "No enforcement actions found",
    "Texas DOI: No orders found",
    "SEC: verified absent",
    "FINRA BrokerCheck — resolved: two disclosures found",
    "CFPB complaint database — Resolved, 213 complaints",
    "NCUA administrative orders index, searched by name: no action recorded",
    "Apple App Store — Verified_Absent",
    {"route": "BBB", "outcome": "resolved"},
    {"route": "CFPB", "outcome": "Verified absent"},
])
def test_outcomes_are_read_in_any_case(rung):
    assert rung_outcome(rung) == "terminal", rung


# ── the owner's failover default ─────────────────────────────────────────
@pytest.mark.parametrize("rung", [
    "Exa NOT_RUN (credit); fell back to WebSearch: resolved, 3 hits",
    "Exa and Tavily: credit exhausted; WebSearch: RESOLVED, 2 hits",
    "Exa NOT_RUN (credit exhausted 2026-10-01); WebFetch of the BBB profile: "
    "VERIFIED ABSENT",
    "Tavily refused (HTTP 402); failover to WebSearch — verified absent",
    "Glassdoor — REFUSED (HTTP 403) + ALTERNATE TRIED: Indeed connector "
    "get_company_data — RESOLVED 3.1 of 5 on 97 reviews",
    "REFUSED + ALTERNATE_TRIED",
])
def test_a_failover_that_finished_is_terminal(rung):
    assert rung_outcome(rung) == "terminal", rung


@pytest.mark.parametrize("rung", [
    "Exa NOT_RUN (credit); fell back to WebSearch: NOT RUN",
    "Exa NOT_RUN (credit); fell back to WebSearch: not confirmed",
    "Exa NOT_RUN (credit); fell back to WebSearch: no results",
    "Exa NOT_RUN (credit); fell back to WebSearch",
])
def test_a_failover_that_did_not_finish_is_open(rung):
    assert rung_outcome(rung) == "open", rung


def test_a_finished_primary_is_not_reopened_by_an_unneeded_failover():
    assert rung_outcome("Exa: RESOLVED, 3 hits; WebSearch not run") \
        == "terminal"


# ── case-insensitivity does not make words into outcomes ─────────────────
@pytest.mark.parametrize("rung", [
    "Negative news screening via Exa — NOT_RUN",
    "negative news search — not run",
    "confirmed peer list for the cohort — pending",
    "rejected applications report — BLOCKED",
])
def test_status_words_used_as_words_are_not_outcomes(rung):
    assert rung_outcome(rung) == "open", rung


def test_a_status_word_used_as_a_word_with_no_outcome_states_none():
    assert rung_outcome("negative news screening for the CEO") is None


# ── the gates that read the ladder ───────────────────────────────────────
_FAMILY_RUNGS = [
    "Apple App Store and Google Play — VERIFIED ABSENT: no app",
    "Glassdoor — RESOLVED 3.4 of 5",
    "Indeed company page — RESOLVED via connector",
    "CFPB complaint database — RESOLVED: 213 complaints",
    "BBB profile — VERIFIED ABSENT: no rated profile",
    "Trustpilot — VERIFIED ABSENT: no page for the entity",
]


def _sentiment(rungs):
    return {"sentiment": {"bars": [{"rating": 4.0}], "empty_state": {
        "reason": "one rated line exists", "sources_searched": rungs}}}


def test_cg40_refuses_a_family_marked_not_confirmed():
    rungs = list(_FAMILY_RUNGS)
    rungs[1] = "Glassdoor — NOT CONFIRMED"
    out = _check_depth_floors("overview", _sentiment(rungs))
    assert len(out) == 1 and out[0]["gate_id"] == "CG-40"
    assert "Glassdoor" in out[0]["message"]


def test_cg40_accepts_a_websearch_failover():
    rungs = list(_FAMILY_RUNGS)
    rungs[4] = ("BBB — Exa NOT_RUN (credit exhausted); fell back to "
                "WebSearch: verified absent, no BBB profile for the entity")
    assert _check_depth_floors("overview", _sentiment(rungs)) == []


def test_cg40_accepts_sentence_case_registry_rungs():
    rungs = list(_FAMILY_RUNGS)
    rungs[3] = "CFPB complaint database: No complaints found"
    assert _check_depth_floors("overview", _sentiment(rungs)) == []


def test_et05b_refuses_a_doi_rung_that_was_not_confirmed():
    ladder = ["Texas Department of Insurance commissioner orders: NOT "
              "CONFIRMED — the search page timed out"]
    payload = {"regulatory_standing": {"absence_of_enforcement": {
        "verified": False, "sources_searched": ladder}}}
    out = _check_c3_regulator_family("context", payload, "IB")
    assert [r["gate_id"] for r in out] == ["ET-05b"]


def test_cg40b_refuses_a_not_run_tier_whose_failover_also_failed():
    alert = {"subcap_id": "P1C1.2.1", "state": "WORKED_ABSENT",
             "queries_run": ["SWBC digital roadmap"],
             "sources_searched": [
                 "Exa NOT_RUN (credit); fell back to WebSearch: NOT RUN"]}
    out = _check_worked_absent_ladder("heatmap",
                                      {"alerts": {"alerts": [alert]}})
    assert [r["gate_id"] for r in out] == ["CG-40b"]


# SWBC writes the failover as two rungs: the paid tier names the hand-over,
# and the WebSearch rung beside it carries the outcome. That is the owner's
# "valid next rung" — but only when that next rung actually finished.
_SWBC_HANDOVER = ("Exa/Tavily/Firecrawl connector rung: NOT_RUN — credit "
                  "exhausted (2026-10-01); built-in web search ran in its "
                  "place")


def _wa(ladder):
    alert = {"subcap_id": "P1C1.2.1", "state": "WORKED_ABSENT",
             "queries_run": ["SWBC multi-year roadmap"],
             "sources_searched": ladder}
    return _check_worked_absent_ladder("heatmap",
                                       {"alerts": {"alerts": [alert]}})


def test_cg40b_accepts_a_handover_whose_websearch_rung_finished():
    assert _wa(["Web search 'SWBC multi-year roadmap': VERIFIED ABSENT "
                "(search) — no SWBC artefact", _SWBC_HANDOVER]) == []


def test_cg40b_refuses_a_handover_whose_websearch_rung_did_not_finish():
    out = _wa(["Web search 'SWBC multi-year roadmap': not confirmed",
               _SWBC_HANDOVER])
    assert [r["gate_id"] for r in out] == ["CG-40b"]


def test_cg40b_refuses_a_handover_with_no_websearch_rung_at_all():
    out = _wa(["Package evidence index — RESOLVED: one row, not a roadmap",
               _SWBC_HANDOVER])
    assert [r["gate_id"] for r in out] == ["CG-40b"]


def test_cg40b_accepts_a_not_run_tier_whose_websearch_failover_finished():
    alert = {"subcap_id": "P1C1.2.1", "state": "WORKED_ABSENT",
             "queries_run": ["SWBC digital roadmap"],
             "sources_searched": [
                 "Exa NOT_RUN (credit); fell back to WebSearch: verified "
                 "absent"]}
    assert _check_worked_absent_ladder(
        "heatmap", {"alerts": {"alerts": [alert]}}) == []


# ── review of fix2/gates: negators inside the word, and `be` before the
#    participle, still read TERMINAL ─────────────────────────────────────
@pytest.mark.parametrize("rung", [
    "NMLS Consumer Access: cannot be confirmed (Cloudflare challenge)",
    "BrokerCheck — could not be resolved",
    "AM Best: can't be verified without a subscription",
    "Texas DOI orders: couldn't be located behind the search box",
    "Form ADV: has not been confirmed",
    "Glassdoor: was not reached",
    "Indeed — won't be established until the connector is granted",
])
def test_negated_participles_are_open_not_terminal(rung):
    assert rung_outcome(rung) == "open", rung


def test_a_ladder_of_only_open_rungs_is_not_proposed_as_worked_absent():
    """'We did not look' must never be proposed as 'we looked and found
    nothing'. Before the fix every NOT_RUN rung counted as an outcome."""
    from dma_mcp.validation import _proposed_tile_state
    tile = {"sources_searched": ["Exa: NOT_RUN credit exhausted",
                                 "Glassdoor: NOT RUN",
                                 "Indeed: cannot be confirmed"]}
    assert _proposed_tile_state(tile) == "UNWORKED"


def test_a_ladder_with_a_terminal_rung_is_proposed_as_worked_absent():
    from dma_mcp.validation import _proposed_tile_state
    tile = {"sources_searched": ["Glassdoor: HTTP 403 refused",
                                 "CareerBliss: REACHED — 4.1 of 5 on 7 ratings"]}
    assert _proposed_tile_state(tile) == "WORKED_ABSENT"
