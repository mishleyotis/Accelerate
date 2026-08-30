"""CG-40 — a section whose value is its depth reaches a floor, or says why not.

Owner, 2026-08-23, on promoted runs:

  · "Sentiment overview on most clients have only 1 parameter and are not
     reflective of what is on the overview page"
  · "For some clients, the evolution timeline spans 1 year? At least 3 years
     should be covered. Enrichment should pick this up."
  · "Explorium technographic scans and Clay technology enrichments should be
     used. I expect at least 15 technology stack items through recursive
     searches."
  · "Gulf has less than 3 historical news. Is this logical? This is a
     crosscutting issue insinuating less rigor around enrichment."

Every one of these floors was ALREADY IN THE CONTRACT and enforced by nothing.
The sentiment field doc says, in as many words, "A single displayed line is
not a sentiment picture". why_now's doc asks for three to six trigger cards
and defines thin=true below two.

THE ESCAPE IS LOAD-BEARING AND IS TESTED HARDEST. A client with eight
detectable products has eight, and refusing that run would be the
reject-rather-than-triage failure this system has already paid for — three
packages refused in one firing, all three producible once the checkers were
fixed. The floor is a floor on EFFORT. What CG-40 refuses is SILENCE: a thin
section that never says it searched.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dma_mcp.gates import GATES  # noqa: E402
from dma_mcp.validation2 import (  # noqa: E402
    DEPTH_FLOORS, WHY_NOW_SPAN_DAYS, _check_depth_floors as check,
)


def ids(out):
    return [(r["gate_id"], r["path"]) for r in out]


# ── the three measured cases ──────────────────────────────────────────────

def test_one_sentiment_line_and_no_search_blocks():
    """The owner's first sentence, exactly."""
    out = check("overview", {"sentiment": {"bars": [{"source": "Google Play"}],
                                           "displayed_lines": 1}})
    assert len(out) == 1 and out[0]["gate_id"] == "CG-40"
    assert "1 rating lines against a floor of 2" in out[0]["message"]
    assert "not a sentiment picture" in out[0]["message"], (
        "the contract's own words come back to the producer")


def test_two_sentiment_lines_pass():
    assert check("overview", {"sentiment": {
        "bars": [{"source": "Google Play"}, {"source": "Glassdoor"}]}}) == []


def test_fourteen_techstack_products_and_no_search_blocks():
    body = {"techstack": {"items": [{"ts_id": f"TS-{i}"} for i in range(14)]}}
    out = check("techstack", body)
    assert len(out) == 1
    assert "14 products against a floor of 15" in out[0]["message"]


def test_fifteen_techstack_products_pass():
    body = {"techstack": {"items": [{"ts_id": f"TS-{i}"} for i in range(15)]}}
    assert check("techstack", body) == []


def test_a_one_year_why_now_span_is_no_longer_a_finding():
    """MOVED, and the move is the point. The three-year reach-back floor lived
    here for a day; the owner then read the run that satisfied it and asked
    "Why Now signals seem stale. Why quote something from 2015?" — because the
    cheapest way to clear a span floor on why_now is to date a signal to an old
    event. Two signals seven months apart is a GOOD why-now.

    The reach-back rule now sits on context.timeline, which is the "evolution
    timeline" the owner was reading, and why_now carries a STALENESS ceiling
    instead. Both are pinned in
    test_why_now_is_recent_and_the_timeline_reaches_back.py.
    """
    assert check("overview", {"why_now": {"signals": [
        {"wn_id": "WN-1", "date": "2026-01-15"},
        {"wn_id": "WN-2", "date": "2026-08-01"}]}}) == []


def test_the_reach_back_floor_now_answers_on_the_timeline():
    out = check("context", {"timeline": {"events": [
        {"event_date": "2026-01-15"}, {"event_date": "2026-08-01"}]}})
    assert len(out) == 1
    assert "three years" in out[0]["message"]
    assert out[0]["path"] == "context.timeline.events"


# ── the escape, tested hardest ────────────────────────────────────────────

@pytest.mark.parametrize("disclosure", [
    {"thin": True, "empty_state": {"sources_searched": ["Google Play", "G2"]}},
    {"thin": True, "r_layer": {"probes_run": ["app-store sweep"]}},
    {"empty_state": {"reason": "one rated source exists for this institution"}},
    {"empty_state": "Searched Google Play, Trustpilot, G2 and Glassdoor; only "
                    "Google Play publishes a rating for this institution."},
    {"r_layer": {"searches": ["trustpilot", "g2"]}},
])
def test_a_thin_section_that_says_what_it_searched_passes(disclosure):
    """A CLIENT WITH EIGHT PRODUCTS HAS EIGHT. Refusing the run would be the
    reject-rather-than-triage failure this system has already paid for."""
    body = {"sentiment": {"bars": [{"source": "Google Play"}], **disclosure}}
    assert check("overview", body) == [], (
        f"a documented thin result must pass: {disclosure}")


def test_a_bare_thin_flag_is_not_a_disclosure():
    """`thin: true` alone is an assertion, not a search. The empty-state
    discipline the rest of the payload keeps is that an absence NAMES its
    search and its closure condition."""
    out = check("overview", {"sentiment": {"bars": [], "thin": True}})
    assert len(out) == 1, "a bare boolean does not clear the floor"


def test_a_two_word_empty_state_is_not_a_disclosure():
    out = check("overview", {"sentiment": {"bars": [], "empty_state": "none"}})
    assert len(out) == 1


def test_a_thin_techstack_that_documents_itself_passes():
    body = {"techstack": {"items": [{"ts_id": f"TS-{i}"} for i in range(8)],
                          "thin": True,
                          "empty_state": {"sources_searched":
                                          ["Explorium", "Clay", "job posts"]}}}
    assert check("techstack", body) == []


# ── it must not fire where it has no business ─────────────────────────────

def test_the_producers_own_counter_is_honoured():
    """`displayed_lines` is the producer's count of the same thing. Take the
    larger, so a section cannot be called thin by miscounting itself."""
    assert check("overview", {"sentiment": {"bars": [],
                                            "displayed_lines": 4}}) == []


def test_undatable_signals_do_not_trip_the_span():
    """A span that cannot be measured is not a short span. Two signals clear
    the count floor; with no dates there is nothing to compare."""
    assert check("overview", {"why_now": {"signals": [
        {"wn_id": "WN-1"}, {"wn_id": "WN-2"}]}}) == []


@pytest.mark.parametrize("page,section", [
    ("overview", "findings"), ("heatmap", "cell_evidence"),
    ("platform", "starters"), ("insights", "cards"),
])
def test_sections_with_no_floor_are_untouched(page, section):
    assert check(page, {section: {"items": []}}) == []


@pytest.mark.parametrize("bad", [None, [], "x", 42,
                                 {"sentiment": "not-a-dict"},
                                 {"sentiment": {"bars": "no"}}])
def test_a_malformed_payload_does_not_raise(bad):
    check("overview", bad)


def test_floors_apply_only_on_their_own_page():
    """techstack.techstack has a floor of 15; the same section name on
    another page is a different thing and must not inherit it."""
    assert check("overview", {"techstack": {"items": []}}) == []


# ── the contract of the gate itself ───────────────────────────────────────

def test_the_floors_are_the_owners_numbers():
    assert DEPTH_FLOORS[("overview", "sentiment")][0] == 2
    assert DEPTH_FLOORS[("techstack", "techstack")][0] == 15
    assert DEPTH_FLOORS[("overview", "why_now")][0] == 2
    assert WHY_NOW_SPAN_DAYS == 3 * 365


def test_cg40_is_registered_and_names_the_escape():
    assert "CG-40" in GATES
    entry = GATES["CG-40"]
    assert entry[-1] == "block"
    why = " ".join(str(x) for x in entry)
    assert "floor on EFFORT" in why or "floor on\n              EFFORT" in why \
        or "EFFORT" in why, "the registry says what the floor is a floor ON"
    assert "reject-rather-than-triage" in why, (
        "and why the escape exists, so nobody tightens it away later")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
