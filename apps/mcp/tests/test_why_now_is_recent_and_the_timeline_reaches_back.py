"""CG-40's two date rules pull in opposite directions, one per surface.

Owner, 2026-08-23 morning: "the evolution timeline spans 1 year? At least 3
years should be covered."
Owner, 2026-08-23 evening, reading the run that satisfied it: "Why Now
signals for Gulf seem stale. Why quote something from 2015… is it still
relevant?"

Both are right, and the first fix caused the second. The three-year floor was
put on `overview.why_now`, so the cheapest way to satisfy it was to date a
signal to an old event — and Gulf's WN-1 duly led with a vendor acquisition
from July 2015, eleven years before the page was written. The gate called
that compliant, because eleven years clears a three-year floor comfortably.

The rules are about different things and now live on different surfaces:

    context.timeline   must REACH BACK      — a history starting this year
                                              is a snapshot, not an evolution
    overview.why_now   must be RECENT       — a trigger is an argument for
                                              acting NOW; an old event can be
                                              DURATION inside one, never the
                                              trigger itself

Staleness is measured against the section's own `produced_at`, not the wall
clock, so a verdict is deterministic and a run re-validated next year does
not fail merely for having aged. The question asked is the producer's own:
on the day you wrote this, how old was your freshest reason to act?
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import (          # noqa: E402
    TIMELINE_SPAN_DAYS, WHY_NOW_STALE_DAYS, _check_date_reach,
    _check_depth_floors, _timeline_span_days, _why_now_staleness_days)

#: Gulf's WN-1 as promoted, with the two signals that were already current.
GULF_REPORTED = {
    "produced_at": "2026-08-23T00:00:00Z",
    "signals": [{"wn_id": "WN-1", "dated_on": "2015-07-01"},
                {"wn_id": "WN-2", "dated_on": "2026-03-31"},
                {"wn_id": "WN-3", "dated_on": "2026-05-19"}],
}
#: …and the shape that made it reportable: nothing newer than the old event.
ALL_STALE = {
    "produced_at": "2026-08-23T00:00:00Z",
    "signals": [{"wn_id": "WN-1", "dated_on": "2015-07-01"},
                {"wn_id": "WN-2", "dated_on": "2016-01-01"}],
}


def ids(out):
    return [(r["gate_id"], r["path"]) for r in out]


# ── why_now: recent, not long ─────────────────────────────────────────

def test_a_why_now_built_only_from_old_events_is_refused():
    out = _check_depth_floors("overview", {"why_now": ALL_STALE})
    assert ids(out) == [("CG-40", "overview.why_now.signals")], out
    m = out[0]["message"]
    assert "3887 days" in m and "10y" in m
    assert "2015" in m


def test_the_refusal_says_an_old_event_may_still_be_duration():
    """The repair is to RE-DATE, not to delete the history — the 2013/2015
    platform record is real and belongs in the trigger's prose and in the
    technology register. A gate that reads as 'drop your history' would push
    a producer the wrong way."""
    out = _check_depth_floors("overview", {"why_now": ALL_STALE})
    m = out[0]["message"]
    assert "DURATION" in m
    assert "cannot be the trigger" in m


def test_one_current_signal_beside_an_old_one_passes():
    """Gulf as promoted: WN-1 was stale but WN-2 and WN-3 were this year, and
    the section is judged on its FRESHEST reason to act. This is why the gate
    did not catch the reported card — and it is the right behaviour, because
    a section carrying one current trigger is arguing for now."""
    assert _why_now_staleness_days(GULF_REPORTED) == 96
    assert _check_depth_floors("overview", {"why_now": GULF_REPORTED}) == []


def test_the_repaired_gulf_signal_is_days_old_not_years():
    repaired = {"produced_at": "2026-08-23T00:00:00Z",
                "signals": [{"wn_id": "WN-1", "dated_on": "2026-08-13"},
                            {"wn_id": "WN-2", "dated_on": "2026-03-31"},
                            {"wn_id": "WN-3", "dated_on": "2026-05-19"}]}
    assert _why_now_staleness_days(repaired) == 10
    assert _check_depth_floors("overview", {"why_now": repaired}) == []


def test_the_ceiling_is_eighteen_months():
    assert WHY_NOW_STALE_DAYS == 548
    # `_check_date_reach` rather than the whole gate: a one-signal fixture
    # also trips the DEPTH floor, which is a different rule and would mask
    # which boundary this test is actually pinning.
    at = {"produced_at": "2026-08-23", "signals": [{"dated_on": "2025-02-21"}]}
    assert _why_now_staleness_days(at) == 548
    assert _check_date_reach("overview", "why_now", at) == []
    over = {"produced_at": "2026-08-23", "signals": [{"dated_on": "2025-02-20"}]}
    assert _why_now_staleness_days(over) == 549
    assert _check_date_reach("overview", "why_now", over)


def test_staleness_is_measured_against_the_payload_not_the_clock():
    """A run validated years later must not fail for having aged. The same
    payload answers the same way whenever it is re-read."""
    old = {"produced_at": "2019-01-01", "signals": [{"dated_on": "2018-12-01"}]}
    assert _why_now_staleness_days(old) == 31
    assert _check_date_reach("overview", "why_now", old) == []


def test_a_section_that_says_what_it_searched_still_promotes():
    """The escape every CG-40 rule keeps: an entity with genuinely no recent
    event promotes by saying so. The floor is on EFFORT, never on the world."""
    said = dict(ALL_STALE)
    said["r_layer"] = {"probes_run": [
        "Searched filings, trade press and the entity's own newsroom for any "
        "event after 2016 bearing on digital capability: none found."]}
    assert _check_depth_floors("overview", {"why_now": said}) == []


# ── timeline: long, not recent ────────────────────────────────────────

def test_a_one_year_evolution_timeline_is_refused():
    """The owner's original words, on the surface they were about."""
    tl = {"events": [{"event_date": "2026-01-26"}, {"event_date": "2026-07-30"}]}
    out = _check_depth_floors("context", {"timeline": tl})
    assert ids(out) == [("CG-40", "context.timeline.events")], out
    assert "185 days" in out[0]["message"]
    assert "evolution timeline spans 1 year" in out[0]["message"]


def test_a_timeline_reaching_five_years_passes():
    tl = {"events": [{"event_date": "2021-08-02"},
                     {"event_date": "2025-09-22"},
                     {"event_date": "2026-07-30"}]}
    assert _timeline_span_days(tl) == 1823
    assert _check_depth_floors("context", {"timeline": tl}) == []


def test_the_floor_is_three_years():
    assert TIMELINE_SPAN_DAYS == 1095
    at = {"events": [{"event_date": "2023-08-24"}, {"event_date": "2026-08-23"}]}
    assert _timeline_span_days(at) == 1095
    assert _check_depth_floors("context", {"timeline": at}) == []


def test_the_timeline_rule_is_not_hidden_behind_the_depth_floor_guard():
    """The bug this nearly shipped with. `timeline` has no DEPTH_FLOORS entry,
    so the loop's `if not floor: continue` skipped the reach-back check and
    the gate reported nothing at all on a one-year history — silence read as
    a pass, which is the defect class this whole family exists for."""
    from dma_mcp.validation2 import DEPTH_FLOORS
    assert ("context", "timeline") not in DEPTH_FLOORS, \
        "if timeline gains a depth floor, this test stops proving anything"
    tl = {"events": [{"event_date": "2026-01-01"}, {"event_date": "2026-02-01"}]}
    assert _check_depth_floors("context", {"timeline": tl}), \
        "the reach-back check is behind the depth-floor guard again"


# ── the two rules do not police each other's surface ──────────────────

def test_a_recent_why_now_is_never_asked_to_reach_back():
    """The regression that produced the 2015 card. Three signals inside four
    months is a GOOD why-now and must pass cleanly."""
    wn = {"produced_at": "2026-08-23",
          "signals": [{"dated_on": "2026-05-19"}, {"dated_on": "2026-07-07"},
                      {"dated_on": "2026-08-13"}]}
    assert _check_depth_floors("overview", {"why_now": wn}) == []


def test_an_old_timeline_is_never_called_stale():
    """A history whose newest entry is years back is a history, not a stale
    trigger. Applying the why-now ceiling here would refuse every entity that
    stopped publishing."""
    tl = {"produced_at": "2026-08-23",
          "events": [{"event_date": "2013-11-01"}, {"event_date": "2020-06-08"}]}
    assert _check_depth_floors("context", {"timeline": tl}) == []


def test_neither_rule_touches_a_section_it_does_not_own():
    for page, section in (("overview", "sentiment"), ("techstack", "techstack"),
                          ("context", "issue_register"), ("platform", "roadmap")):
        assert _check_date_reach(page, section,
                                 {"events": [{"event_date": "2026-01-01"}],
                                  "signals": [{"dated_on": "2015-01-01"}],
                                  "produced_at": "2026-08-23"}) == []


# ── undatable is not a verdict ────────────────────────────────────────

def test_an_undatable_section_returns_none_and_blocks_nothing():
    """Honest ignorance stays honest: the contract's own 'an undated signal is
    dropped' and the depth floor cover that case, and inventing a verdict here
    would be the check-never-ran-reads-as-a-number defect pointing the other
    way."""
    assert _why_now_staleness_days({"signals": [{"wn_id": "X"}],
                                    "produced_at": "2026-08-23"}) is None
    assert _why_now_staleness_days({"signals": [{"dated_on": "2026-01-01"}]}) is None
    assert _timeline_span_days({"events": [{"title": "no date"}]}) is None
    assert _timeline_span_days({"events": [{"event_date": "2026-01-01"}]}) is None
    assert _check_depth_floors("context", {"timeline": {"events": []}}) == []


def test_a_non_dict_row_does_not_crash_either_rule():
    assert _timeline_span_days(
        {"events": ["x", None, {"event_date": "2021-01-01"},
                    {"event_date": "2026-01-01"}]}) == 1826
    assert _why_now_staleness_days(
        {"signals": ["x", None, {"dated_on": "2026-08-01"}],
         "produced_at": "2026-08-23"}) == 22
