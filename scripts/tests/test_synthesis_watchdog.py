"""A stalled synthesis session is detectable from outside, and this proves it.

Every stall seen so far has the same shape: a producer fans work out, the turn
ends, and dispatched subagents do not survive a turn boundary — so the
verdicts never arrive and the session sits holding a live claim with nothing
running inside it. From outside that is indistinguishable from a session
thinking hard, and it stayed that way until a human noticed. The one time
noticing took a while, the redo cost 2.1M output tokens.

The insight the watchdog rests on: a producer that is WORKING submits pages.
Progress is therefore observable from the connector alone, with no cooperation
from the session that has stopped — which matters, because a stalled session
cannot be relied on to report that it has stalled.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import synthesis_watchdog as w                                      # noqa: E402

T0 = 1_000_000.0
PAGES = w.PAGES


def progress(passed=(), promoted=(), live=True, blocking=0, promotable=None,
             subs=None):
    subs = subs or {}
    pages = {}
    for p in PAGES:
        if p in passed:
            pages[p] = {"status": "PASS",
                        "submission_id": subs.get(p, f"sub-{p}"),
                        "promoted_at": "2026-08-22T16:51:15Z" if p in promoted else None}
    return {
        "pages": pages,
        "blocking": [{"gate_id": "CG-01"}] * blocking,
        "promotable": (len(passed) == len(PAGES) and not blocking)
                      if promotable is None else promotable,
        "claim": {"held_by": "session-a", "live": live,
                  "expires_at": "2026-08-22T20:00:00Z"},
    }


# ── the stall ──


def test_a_live_claim_that_has_not_moved_is_stalled():
    p = progress(passed=("overview", "insights"))
    first = w.classify(p, None, T0)
    assert first["state"] == w.PROGRESSING, "first sight is never a stall"
    later = w.classify(p, {**first, "seen_at": T0}, T0 + w.STALL_SECONDS)
    assert later["state"] == w.STALLED
    assert later["stalled_for_seconds"] >= w.STALL_SECONDS


def test_a_short_pause_is_not_a_stall():
    """A page is minutes of work. Interrupting a slow producer mid-section
    costs more than waiting for it."""
    p = progress(passed=("overview",))
    first = w.classify(p, None, T0)
    later = w.classify(p, {**first, "seen_at": T0}, T0 + w.STALL_SECONDS - 1)
    assert later["state"] == w.PROGRESSING


def test_a_resubmitted_page_counts_as_progress():
    """Why the fingerprint is submission ids and not a count: repairing a
    failed page leaves the count unchanged, and calling that a stall would
    wake the one session that is actually working."""
    a = progress(passed=("overview",), subs={"overview": "sub-1"})
    b = progress(passed=("overview",), subs={"overview": "sub-2"})
    first = w.classify(a, None, T0)
    later = w.classify(b, {**first, "seen_at": T0}, T0 + w.STALL_SECONDS * 3)
    assert later["state"] == w.PROGRESSING


def test_a_new_page_counts_as_progress():
    first = w.classify(progress(passed=("overview",)), None, T0)
    later = w.classify(progress(passed=("overview", "heatmap")),
                       {**first, "seen_at": T0}, T0 + w.STALL_SECONDS * 3)
    assert later["state"] == w.PROGRESSING


# ── the finish line, unattended ──


def test_six_passing_pages_that_never_promoted_are_actionable():
    """The state T. Rowe Price sat in: everything produced, everything
    validated, nothing serving. No error was raised anywhere."""
    s = w.classify(progress(passed=PAGES), None, T0)
    assert s["state"] == w.READY_TO_PROMOTE
    assert s["promotable"] is True


def test_ready_to_promote_fires_even_when_the_claim_has_lapsed():
    """A lapsed claim is the likeliest way to reach this state — the session
    ran out of lease before it promoted. Requiring a live claim here would
    make the watchdog blindest exactly where it is most needed."""
    s = w.classify(progress(passed=PAGES, live=False), None, T0)
    assert s["state"] == w.READY_TO_PROMOTE


def test_a_fully_promoted_run_is_done_not_actionable():
    p = progress(passed=PAGES, promoted=PAGES, live=False)
    first = w.classify(p, None, T0)
    again = w.classify(p, {**first, "seen_at": T0}, T0 + w.STALL_SECONDS * 5)
    assert again["state"] == w.DONE
    assert again["state"] not in w.ACTIONABLE


def test_a_run_nobody_holds_is_the_queues_problem_not_this_ones():
    s = w.classify(progress(passed=("overview",), live=False), None, T0)
    assert s["state"] == w.UNCLAIMED
    assert s["state"] not in w.ACTIONABLE


def test_blocking_reasons_keep_a_run_off_the_promote_path():
    s = w.classify(progress(passed=PAGES, blocking=2, promotable=False), None, T0)
    assert s["state"] != w.READY_TO_PROMOTE
    assert s["blocking"] == 2


# ── what the resume actually says ──


@pytest.mark.parametrize("state,passed", [
    (w.STALLED, ("overview", "insights")),
    (w.READY_TO_PROMOTE, PAGES),
])
def test_the_resume_names_what_is_banked_before_what_is_missing(state, passed):
    """The expensive mistake is not the stall, it is the redo after it. A
    resume that says only "carry on" gets finished pages produced twice."""
    p = progress(passed=passed)
    prev = w.classify(p, None, T0)
    s = w.classify(p, {**prev, "seen_at": T0}, T0 + w.STALL_SECONDS)
    if s["state"] != state:
        pytest.skip("covered by another case")
    text = w.resume_text("7a6ad71c-6225-4e0b-80fb-135cfd04b2dd", "T. Rowe Price", s)
    assert "ALREADY BANKED" in text
    assert text.index("ALREADY BANKED") < text.index("still missing")
    assert "do NOT reproduce" in text


def test_the_resume_points_at_the_artifact_store():
    """The store exists precisely so a resume does not cost a re-run. A
    resume that does not mention it is a resume that will."""
    s = w.classify(progress(passed=PAGES), None, T0)
    text = w.resume_text("7a6ad71c-1111-2222-3333-444444444444", "X", s)
    assert "artifact_store.py find" in text
    assert "7a6ad71c" in text


def test_the_resume_tells_the_session_to_re_read_rather_than_trust_it():
    """The message is a snapshot and says so. A resume acted on as current
    truth is how two producers end up writing the same page."""
    s = w.classify(progress(passed=PAGES), None, T0)
    text = w.resume_text("r", "X", s)
    assert "call get_run_progress yourself" in text


def test_the_stall_message_names_the_turn_boundary_cause():
    """A producer told only "you stalled" re-dispatches and stalls again. Told
    that subagents do not survive a turn boundary, it changes what it does."""
    p = progress(passed=("overview",))
    prev = w.classify(p, None, T0)
    s = w.classify(p, {**prev, "seen_at": T0}, T0 + w.STALL_SECONDS)
    assert "do not survive a turn boundary" in w.resume_text("r", "X", s)


# ── the plan, end to end ──


def test_plan_carries_state_forward_so_the_second_look_can_see_a_stall():
    runs = [{"run_id": "r1", "entity_name": "One",
             "progress": progress(passed=("overview",))}]
    first = w.plan(runs, {}, T0)
    assert first[0]["state"] == w.PROGRESSING
    state = {s["run_id"]: s for s in first}
    second = w.plan(runs, state, T0 + w.STALL_SECONDS)
    assert second[0]["state"] == w.STALLED
    assert "resume" in second[0]


def test_only_actionable_entries_carry_a_resume():
    runs = [{"run_id": "r1", "progress": progress(passed=("overview",), live=False)}]
    assert "resume" not in w.plan(runs, {}, T0)[0]


def test_a_run_with_no_id_is_skipped_rather_than_crashing():
    assert w.plan([{"entity_name": "no id"}], {}, T0) == []


def test_the_actionable_set_is_exactly_the_states_a_routine_should_wake():
    assert set(w.ACTIONABLE) == {w.STALLED, w.READY_TO_PROMOTE, w.EXPIRING}
    assert w.PROGRESSING not in w.ACTIONABLE
    assert w.DONE not in w.ACTIONABLE
    assert w.UNCLAIMED not in w.ACTIONABLE
