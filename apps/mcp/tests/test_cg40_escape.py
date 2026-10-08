"""CG-40 — a thin section passes on a COMPLETED ladder, not on prose about one.

RC-05 (SWBC gold audit, 2026-10-04; slices S-05, S-07; D-06). The depth floor
had an escape hatch wider than the floor: `_says_it_searched` returned True for
any `empty_state.reason`, any empty_state string of 40+ characters, or any
`r_layer.probes_run` — and r_layer is mandatory on every section, so the
sentiment floor of 2 could never bite. SWBC promoted ONE company-reported bar
with Glassdoor, Indeed, BBB and Trustpilot recorded as "NOT FETCHED" and five
more families "not retrieved; neither found nor ruled out", and CG-40 passed.

The rule now:
  * the ladder is `sources_searched` (on empty_state or the section); r_layer,
    a bare reason, a thin flag and free prose are not a ladder;
  * every rung states an outcome; at least one is TERMINAL — RESOLVED,
    VERIFIED_ABSENT, REACHED/REJECTED/EXCLUDED/NEGATIVE, or
    REFUSED + ALTERNATE_TRIED — and "not retrieved", "neither found nor ruled
    out", NOT_RUN, NOT FETCHED and BLOCKED are not;
  * every MANDATORY FAMILY the contract declares for the section
    (`mandatory_families`; O9: app stores, Glassdoor, Indeed, CFPB, BBB,
    Trustpilot/Google) is covered by a terminal rung.
A client with one genuine rating still passes — by showing the families were
worked to an outcome.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import sections  # noqa: E402
from dma_mcp.validation2 import (  # noqa: E402
    _check_depth_floors as check, rung_outcome,
)

# SWBC overview.sentiment as promoted (run 7968492e): rung shapes verbatim in
# outcome, abridged in detail.
SWBC_RUNGS = [
    "Google reviews rating for SWBC — REACHED VIA RELAY: a review site states "
    "SWBC says it has over 1,000 Google reviews averaging 4.9 of 5",
    "Apple App Store search for SWBC, SWBC Mortgage and SWIVEL — VERIFIED "
    "ABSENT of a SWBC-published consumer app",
    "Google Play search q=SWBC — VERIFIED ABSENT in results for that query",
    "Consumer Financial Protection Bureau complaint database — RESOLVED: 213 "
    "complaints, 187 mortgage",
    "CareerBliss employer reviews — REACHED: 4.1 of 5 on 7 ratings, no date",
    "Glassdoor, Indeed, Blind, BBB, Trustpilot and WalletHub — NOT FETCHED: "
    "these sites refused automated retrieval (HTTP 403), so this is a source "
    "not reached and not an absence",
    "Great Place To Work, Comparably, J.D. Power and any self-published Net "
    "Promoter Score — not retrieved for SWBC; neither found nor ruled out",
]
SWBC = {
    "bars": [{"source": "Google reviews, company-reported", "rating": 4.9,
              "audience": "customer"}],
    "r_layer": {"probes_run": ["Bar decision E-CC-1434: ...",
                               "CX Disconnect probe: ..."],
                "verdict": "ACCEPT"},
    "empty_state": {
        "reason": "One rated line is available: SWBC reports a 4.9 of 5 "
                  "Google rating relayed by a mortgage review site.",
        "sources_searched": SWBC_RUNGS,
        "closure_condition": "A second rated source."},
}


def test_swbc_sentiment_is_refused():
    out = check("overview", {"sentiment": SWBC})
    assert len(out) == 1 and out[0]["gate_id"] == "CG-40"
    msg = out[0]["message"]
    for fam in ("Glassdoor", "Indeed", "BBB"):
        assert fam in msg, (fam, msg)


def test_probes_run_alone_is_not_a_ladder():
    body = {"bars": [{"rating": 4.0}],
            "r_layer": {"probes_run": ["app-store sweep"]}}
    assert len(check("overview", {"sentiment": body})) == 1


def test_a_bare_reason_is_not_a_ladder():
    body = {"bars": [{"rating": 4.0}],
            "empty_state": {"reason": "one rated source exists for this "
                                      "institution and it is drawn"}}
    assert len(check("overview", {"sentiment": body})) == 1


def test_a_completed_ladder_passes_on_one_bar():
    """The escape stays open for the honest case: the families were worked to
    an outcome and the world has one rating."""
    body = {"bars": [{"rating": 4.0}], "empty_state": {
        "reason": "one rated line exists",
        "sources_searched": [
            "Apple App Store and Google Play — VERIFIED ABSENT: no app",
            "Glassdoor — REFUSED (HTTP 403) + ALTERNATE TRIED: Indeed "
            "connector get_company_data — RESOLVED 3.1 of 5 on 97 reviews",
            "Indeed company page — RESOLVED via connector",
            "CFPB complaint database — RESOLVED: 213 complaints",
            "BBB profile — VERIFIED ABSENT: no rated profile",
            "Trustpilot — VERIFIED ABSENT: no page for the entity",
        ]}}
    assert check("overview", {"sentiment": body}) == []


def test_every_rung_must_state_an_outcome():
    body = {"bars": [{"rating": 4.0}], "empty_state": {
        "reason": "x", "sources_searched": [
            "Apple App Store and Google Play — VERIFIED ABSENT",
            "Glassdoor and Indeed — RESOLVED",
            "CFPB — RESOLVED", "BBB — VERIFIED ABSENT",
            "Trustpilot — VERIFIED ABSENT",
            "Comparably"]}}
    out = check("overview", {"sentiment": body})
    assert len(out) == 1 and "Comparably" in out[0]["message"]


def test_rung_outcomes():
    assert rung_outcome("CFPB — RESOLVED: 213") == "terminal"
    assert rung_outcome("App Store — VERIFIED ABSENT") == "terminal"
    assert rung_outcome("X — VERIFIED_ABSENT") == "terminal"
    assert rung_outcome("Glassdoor — NOT FETCHED: HTTP 403") == "open"
    assert rung_outcome("Form 5500 — not retrieved; neither found nor ruled "
                        "out") == "open"
    assert rung_outcome("Exa connector rung: NOT_RUN — credit exhausted") \
        == "open"
    assert rung_outcome("Exa connector rung: NOT_RUN — credit exhausted "
                        "(2026-10-01); built-in web search ran in its place: "
                        "VERIFIED ABSENT") == "terminal"
    assert rung_outcome("EDGAR — RESOLVED, three points; 2020 not "
                        "retrieved") == "terminal"
    assert rung_outcome("Comparably") is None
    assert rung_outcome({"route": "BBB", "outcome": "VERIFIED_ABSENT"}) \
        == "terminal"
    assert rung_outcome({"route": "BBB", "outcome": "NOT_RUN"}) == "open"


def test_the_families_are_contract_data():
    fams = sections("overview")["sentiment"]["mandatory_families"]
    names = {f["family"] for f in fams}
    assert names == {"app stores", "Glassdoor", "Indeed", "CFPB", "BBB",
                     "Trustpilot or Google reviews"}
