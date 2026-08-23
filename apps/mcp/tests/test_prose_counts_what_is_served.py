"""CG-47 — why_now's summary prose counts the signals it serves.

Invariant 8: counts are computed, never stored where a source of truth
exists. A count written into a sentence IS a stored count, and it stops
agreeing with its own list the moment an item is added or dropped.

MEASURED ON BOTH PROMOTED RUNS, 2026-08-23, IN BOTH DIRECTIONS:

  · gulf-coast-business-credit lost WN-1 when ET-04 refused its evidence id
    — an ingested row carrying an empty excerpt, so the chip would have
    opened onto nothing. Two signals remained, and the synthesis still read
    "the three signals describe a business whose volume is rising faster
    than its systems are connecting", still describing the dropped one.

  · axos-bank gained WN-04 in a later repair. Four signals served, and the
    synthesis still read "Taken together the three dates describe a bank".

Removal and addition, same defect, neither caught, both promoted.

THE SCOPE IS THE DESIGN, AND MOST OF THIS FILE DEFENDS IT. The first version
covered thirteen sections. Run against every promoted page of both runs
before shipping, it produced three true findings on why_now and FOUR FALSE
ones on techstack and issue_register — each on prose better than the rule
judging it. Those four are pinned below as passing cases, because the way
this gate fails in future is somebody widening it back.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dma_mcp.validation2 as V2         # noqa: E402
from dma_mcp.validation2 import (        # noqa: E402
    COUNTED_SECTIONS, _WHOLE_SET_ADJECTIVES, _stated_counts,
)


def run(page, section, body):
    return V2._check_prose_counts_what_is_served(page, {section: body})


def ids(out):
    return [r["gate_id"] for r in out]


def sig(n):
    return [{"wn_id": f"WN-{i}"} for i in range(n)]


# ── the two measured defects ──────────────────────────────────────────

def test_gulfs_three_signals_over_two_served_is_refused():
    """Gulf's synthesis, verbatim, over the list a reader counts."""
    out = run("overview", "why_now", {
        "signals": sig(2),
        "synthesis": "Taken together the three signals describe a business "
                     "whose volume is rising faster than its systems are "
                     "connecting."})
    assert ids(out) == ["CG-47"], out
    m = out[0]["message"]
    assert "'three signals'" in m and "serves 2" in m
    assert out[0]["path"] == "overview.why_now.synthesis"
    assert out[0]["severity"] == "block"


def test_axos_three_dates_over_four_served_is_refused():
    """The other direction: a signal was ADDED and the prose never recounted."""
    out = run("overview", "why_now", {
        "signals": sig(4),
        "synthesis": "Taken together the three dates describe a bank adding "
                     "AI capability faster than the controls around it."})
    assert ids(out) == ["CG-47"]
    assert "serves 4" in out[0]["message"]


def test_gulfs_narrative_thread_is_read_too():
    out = run("overview", "why_now", {
        "signals": sig(2),
        "narrative_thread": "Three dated signals build the case the "
                            "executive summary opens on."})
    assert ids(out) == ["CG-47"]
    assert out[0]["path"] == "overview.why_now.narrative_thread"


def test_the_verdict_says_the_repair_may_be_the_signal_not_the_sentence():
    """A gate that only says 'change the number' teaches a producer to paper
    over a dropped card. Gulf's real repair was both — the sentence also
    still described the signal that had gone."""
    out = run("overview", "why_now",
              {"signals": sig(2), "synthesis": "the three signals describe"})
    m = out[0]["message"]
    assert "the repair is the signal - not the sentence" in m
    assert "still describes what it lost" in m


def test_correcting_the_number_clears_it():
    assert run("overview", "why_now", {
        "signals": sig(2),
        "synthesis": "Taken together the two signals describe."}) == []


def test_writing_it_without_a_number_clears_it():
    assert run("overview", "why_now", {
        "signals": sig(2),
        "synthesis": "Taken together the signals describe a business."}) == []


# ── the four false positives that set the scope ───────────────────────
#
# Each of these is real promoted prose the thirteen-section version refused.
# They pass now because of scope, and they are pinned so a later widening
# has to break a test that says exactly why it existed.

def test_a_category_slice_of_a_register_is_not_a_register_count():
    """axos techstack: 'three automation products' over a 30-row register."""
    assert run("techstack", "techstack", {
        "items": [{}] * 30,
        "narrative_thread": "What it shows is not a thin estate but a "
                            "duplicated one - three business-intelligence "
                            "platforms, two marketing stacks, three "
                            "automation products, four source-control "
                            "systems."}) == []


def test_a_prior_state_of_another_register_is_not_this_sections_count():
    """gulf techstack: 'Twenty-four rows where the promoted register carried
    four'. The four is a previous state, not a claim about this list."""
    assert run("techstack", "techstack", {
        "items": [{}] * 24,
        "narrative_thread": "Twenty-four rows where the promoted register "
                            "carried four."}) == []


def test_candidates_found_and_excluded_are_not_the_registers_contents():
    """axos issue_register: 'tested the two matters it found ... Neither
    survives that test', over a register that correctly serves zero."""
    assert run("context", "issue_register", {
        "issues": [],
        "narrative_thread": "This register tested the two matters it found "
                            "against the assessed entity's own boundary. "
                            "Neither survives that test."}) == []


def test_per_item_sequencing_prose_is_not_an_array_index():
    """axos WN-01: 'It comes first because the standard has to exist before
    the estate it governs arrives' — the recommended sequence, not the
    position in the list. Reading item prose fired on this immediately."""
    assert run("overview", "why_now", {
        "signals": [{"wn_id": "WN-04",
                     "why_this_sequence": "It is the earliest of the four."},
                    {"wn_id": "WN-01",
                     "why_this_sequence": "It comes first because the "
                                          "standard has to exist before the "
                                          "estate it governs arrives."}]}) == []


def test_the_scope_is_one_section_and_that_is_deliberate():
    assert list(COUNTED_SECTIONS) == [("overview", "why_now")], (
        "widening this map is what produced four false refusals on prose "
        "better than the rule judging it — see the module docstring")


# ── the guards ────────────────────────────────────────────────────────

def test_a_year_is_not_a_count():
    """axos's own prose: 'read alone, each 2026 signal looks like a one-off'.
    Firing here would train producers to strip real dates out."""
    assert run("overview", "why_now", {
        "signals": sig(4),
        "synthesis": "Read alone, each 2026 signal looks like a one-off "
                     "rather than a five-year pattern."}) == []


def test_a_partitions_numerator_is_skipped():
    assert run("overview", "why_now", {
        "signals": sig(5),
        "synthesis": "Three of the five signals are regulatory."}) == []


def test_a_partitions_denominator_is_still_a_count_claim():
    """"three of the five signals" asserts five signals exist. Skipping the
    whole phrase would let the most confident sentence go unchecked."""
    out = run("overview", "why_now",
              {"signals": sig(4),
               "synthesis": "Three of the five signals are regulatory."})
    assert ids(out) == ["CG-47"]
    assert "serves 4" in out[0]["message"]


def test_a_narrowing_adjective_makes_it_a_subset_claim():
    for adj in ("regulatory", "competitive", "automation", "market"):
        assert run("overview", "why_now", {
            "signals": sig(4),
            "synthesis": f"Two {adj} signals sit behind this."}) == [], adj


def test_a_whole_set_adjective_still_counts_the_whole_set():
    """'dated' describes every signal rather than selecting some, which is
    what lets 'Three dated signals' stay checkable."""
    for adj in sorted(_WHOLE_SET_ADJECTIVES):
        out = run("overview", "why_now",
                  {"signals": sig(2), "synthesis": f"Three {adj} signals."})
        assert ids(out) == ["CG-47"], adj


def test_numbers_about_the_clients_world_are_not_counts():
    """The gate must not read the business. Gulf's own trigger prose."""
    assert run("overview", "why_now", {
        "signals": sig(2),
        "synthesis": "The parent's total assets grew from 2.82 billion "
                     "dollars in 2021 to 3.71 billion by 31 March 2026, a "
                     "6.49 per cent compound annual rate over four years, "
                     "across five states and thirty thousand debtors."}) == []


def test_a_number_far_from_the_noun_is_not_modifying_it():
    assert run("overview", "why_now", {
        "signals": sig(2),
        "synthesis": "Three offices opened in states where the division "
                     "already funds receivables, and the signals below say "
                     "why that matters now."}) == []


# ── the extractor on its own ──────────────────────────────────────────

@pytest.mark.parametrize("text,want", [
    ("Three dated signals build the case", [3]),
    ("the three signals describe", [3]),
    ("Taken together the three dates describe", [3]),
    ("2 signals", [2]),
    ("each 2026 signal", []),
    ("three of the five signals", [5]),
    ("three automation signals", []),
    ("", []),
    (None, []),
    (42, []),
])
def test_the_extractor_reads_exactly_what_it_should(text, want):
    got = [n for _p, n in _stated_counts(text, ("signals", "signal", "dates"))]
    assert got == want, (text, got)


def test_a_noun_that_is_a_substring_of_a_longer_word_is_not_matched():
    assert _stated_counts("three signalling protocols", ("signal",)) == []


# ── safety ────────────────────────────────────────────────────────────

def test_a_section_whose_list_field_is_absent_is_untouched():
    """Nothing to count against is not a wrong count."""
    assert run("overview", "why_now", {"synthesis": "three signals"}) == []
    assert run("overview", "why_now",
               {"signals": "not-a-list", "synthesis": "three signals"}) == []


def test_an_unmapped_section_is_untouched():
    assert run("overview", "exec_summary",
               {"signals": sig(2), "synthesis": "three signals"}) == []


@pytest.mark.parametrize("bad", [None, [], "x", 42,
                                 {"why_now": "not-a-dict"},
                                 {"why_now": {"signals": None}}])
def test_malformed_payloads_do_not_raise(bad):
    V2._check_prose_counts_what_is_served("overview", bad)


def test_the_finding_list_is_bounded():
    body = {"signals": sig(2)}
    for k in ("narrative_thread", "synthesis", "storyline"):
        body[k] = "nine signals and nine dates and nine signals"
    assert len(run("overview", "why_now", body)) <= 6


def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-47" in GATES
    assert GATES["CG-47"][-1] == "block"
    why = GATES["CG-47"][3].lower()
    assert "invariant 8" in why
    assert "gulf" in why and "axos" in why
    assert "false" in why, (
        "the registry records that a wider version produced false refusals, "
        "so nobody widens it back without meeting that measurement")


def test_it_runs_inside_pass_two():
    import inspect
    src = inspect.getsource(V2.validate_pass2)
    assert "_check_prose_counts_what_is_served" in src, \
        "CG-47 is defined but never dispatched"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
