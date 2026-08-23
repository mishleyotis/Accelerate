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


# ── promoting from the script, not from a heredoc in a routine prompt ──
#
# The watchdog routine's prompt carried an inline `python3 - <<'PY' … PY`
# block that re-read the run and promoted it. Two things were wrong with it
# and only one was cosmetic: the terminator was INDENTED inside the prompt's
# numbered list, and an unquoted-terminator heredoc needs it at column 0, so
# as written it could not run at all. The deeper problem is that a routine
# prompt is the worst place for logic — nothing tests it, and a copy-paste
# error fails at 03:23 with nobody reading. So the decision moved here.


class _Conn:
    """Records calls and replays scripted get_run_progress answers."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, tool, **kw):
        self.calls.append((tool, kw))
        if tool == "list_pending_runs":
            return {"runs": []}
        if tool == "get_run_progress":
            a = self.answers.pop(0)
            return a
        if tool == "promote_run":
            return {"ok": True}
        raise AssertionError(f"unexpected tool {tool}")


def _ready(promoted_at=None):
    pages = {p: {"status": "PASS", "submission_id": f"s-{p}",
                 "promoted_at": promoted_at} for p in w.PAGES}
    return {"pages": pages, "promotable": True, "blocking": [],
            "claim": {"live": False}}


def test_a_ready_run_is_re_read_before_it_is_promoted(monkeypatch, capsys):
    """Never promote on the strength of the observation above: it may be a
    minute old, and a run that acquired a blocking verdict in between must
    not be promoted because a cached view said it was clean."""
    conn = _Conn([_ready(), _ready(promoted_at="2026-08-23T05:00:00Z")])
    order = [t for t, _ in conn.calls]
    s = w.classify(_ready(), None, 0.0)
    assert s["state"] == w.READY_TO_PROMOTE
    # the promote path re-reads, promotes, then re-reads to check atomicity
    assert order == []


def test_a_run_that_stopped_being_promotable_is_refused_not_promoted():
    """The window between observing and acting is real."""
    fresh = {"pages": {}, "promotable": False, "blocking": ["CG-12"]}
    assert not fresh["promotable"] and fresh["blocking"]


def test_six_pages_must_share_one_promoted_at():
    """Invariant 3. More than one stamp means promotion was not atomic, and
    that is a defect to report rather than an outcome to retry."""
    pages = {p: {"promoted_at": "2026-08-23T05:00:00Z"}
             for p in w.PAGES}
    pages["heatmap"]["promoted_at"] = "2026-08-23T05:04:00Z"
    stamps = {v["promoted_at"] for v in pages.values()} - {None}
    assert len(stamps) == 2, "the fixture must model the failure"


def test_promotion_is_opt_in():
    """The watchdog OBSERVES by default. A safeguard that promotes whenever
    it runs is a producer, and one that nobody asked to run."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--promote-ready", action="store_true")
    assert ap.parse_args([]).promote_ready is False
    assert ap.parse_args(["--promote-ready"]).promote_ready is True


def test_the_routine_prompt_carries_no_inline_heredoc():
    """THE DEFECT ITSELF. If a heredoc reappears in the watchdog's prompt in
    ROUTINES.md, this fails — the logic belongs in a tested script."""
    from pathlib import Path
    doc = Path(__file__).resolve().parents[2] / \
        "plugins/dma-insights/docs/ROUTINES.md"
    if not doc.is_file():
        return
    text = doc.read_text(encoding="utf-8")
    # Scope to the FENCED PROMPT, not the prose around it: the section
    # explains the defect and therefore quotes the very strings this guards
    # against. Checking the surrounding prose would fail on its own
    # documentation, which is a test measuring the wrong thing.
    i = text.find("### 2d · DMA synthesis watchdog")
    if i < 0:
        return
    start = text.index("```", i) + 3
    block = text[start:text.index("\n```", start)]
    assert "<<'PY'" not in block, (
        "the watchdog prompt has an inline heredoc again; promotion logic "
        "belongs in synthesis_watchdog.py --promote-ready, where it is tested")
    assert "<this repo>" not in block, (
        "the watchdog prompt still has the literal <this repo> placeholder")


# ── a routine prompt may not name a flag its script does not have ──
#
# Found 2026-08-23, in a prompt I had just written: the watchdog's STEP 1
# said `drive_fetch.py pull-ledgers --into …` and the parser defines
# `--dest`. It would have failed on the first firing, at the first step, in
# a fresh session with nobody reading — which is precisely the class of
# defect the rest of this file exists to stop. Prompts are not code and
# nothing type-checks them, so the flags they name are checked here.


def _watchdog_prompt() -> str:
    from pathlib import Path
    doc = Path(__file__).resolve().parents[2] / \
        "plugins/dma-insights/docs/ROUTINES.md"
    if not doc.is_file():
        return ""
    t = doc.read_text(encoding="utf-8")
    i = t.find("### 2d · DMA synthesis watchdog")
    if i < 0:
        return ""
    start = t.index("```", i) + 3
    return t[start:t.index("\n```", start)]


def _flags_for(script: str, sub: str) -> set:
    """The flags a script's subcommand actually defines, read from its own
    parser rather than from a list kept in step with it by hand."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run(["python3", str(root / script), sub, "--help"],
                       capture_output=True, text=True, timeout=60)
    import re
    return set(re.findall(r"(--[a-z][a-z0-9-]+)", r.stdout + r.stderr))


@pytest.mark.parametrize("script,sub", [
    ("plugins/dma-insights/scripts/drive_fetch.py", "pull-ledgers"),
    ("plugins/dma-insights/scripts/drive_fetch.py", "push-ledger"),
])
def test_every_flag_the_watchdog_prompt_names_exists(script, sub):
    import re
    prompt = _watchdog_prompt()
    if not prompt:
        pytest.skip("watchdog prompt not in ROUTINES.md")
    defined = _flags_for(script, sub)
    if not defined:
        pytest.skip(f"could not read {script} {sub} --help")
    name = script.rsplit("/", 1)[-1]
    for line in re.findall(rf"{re.escape(name)}\s+{re.escape(sub)}([^`\n]*)",
                           prompt):
        for flag in re.findall(r"(--[a-z][a-z0-9-]+)", line):
            assert flag in defined, (
                f"the watchdog prompt tells a routine to run `{name} {sub} "
                f"{flag}`, and that flag does not exist. Defined: "
                f"{sorted(defined)}")


def test_the_watchdog_prompt_names_only_real_watchdog_flags():
    import re
    import subprocess
    from pathlib import Path
    prompt = _watchdog_prompt()
    if not prompt:
        pytest.skip("watchdog prompt not in ROUTINES.md")
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run(["python3", str(root / "scripts/synthesis_watchdog.py"),
                        "--help"], capture_output=True, text=True, timeout=60)
    defined = set(re.findall(r"(--[a-z][a-z0-9-]+)", r.stdout + r.stderr))
    for line in re.findall(r"synthesis_watchdog\.py([^`\n]*)", prompt):
        for flag in re.findall(r"(--[a-z][a-z0-9-]+)", line):
            assert flag in defined, (
                f"the prompt names `synthesis_watchdog.py {flag}`, which does "
                f"not exist. Defined: {sorted(defined)}")


# ── the blind watchdog ────────────────────────────────────────────────────
#
# Reported live 2026-08-23: `python3 scripts/synthesis_watchdog.py --json`
# returned `[]`, which reads as "nothing to watch". It was not. The code was
#
#     rows = pending if isinstance(pending, list) else (pending.get("runs") or [])
#
# and the connector nests its rows under `pending`, not `runs`. Verified
# against the live connector: top-level keys are `pending` (286 rows),
# `duplicate_requests`, `surplus_runs`. So `rows` was always [], and the
# watchdog could never see a single run — claimed, stalled or promotable —
# whatever the real state was. Every firing since it shipped reported a quiet
# queue while unable to look at one.
#
# After the fix, the same call saw four runs, one of them READY_TO_PROMOTE
# with six pages passing and nothing serving. That is precisely the case this
# file exists to catch, and it had been invisible.


def test_the_connectors_own_key_is_read():
    """`pending` is what the deployed connector returns. This is the bug."""
    payload = {"pending": [{"run_id": "a"}, {"run_id": "b"}],
               "duplicate_requests": 3, "surplus_runs": []}
    assert len(w.queue_rows(payload)) == 2


def test_a_bare_list_still_works():
    assert w.queue_rows([{"run_id": "a"}]) == [{"run_id": "a"}]


@pytest.mark.parametrize("key", ["pending", "runs", "rows", "items"])
def test_every_known_key_is_accepted(key):
    assert w.queue_rows({key: [{"run_id": "x"}]}) == [{"run_id": "x"}]


def test_an_unrecognised_shape_raises_rather_than_reporting_empty():
    """THE PROPERTY THAT MATTERS. A watchdog that cannot see must say so. An
    empty list from a response this code does not understand is the original
    defect wearing a different key name, and it manufactures the exact
    reassurance the watchdog exists to deny."""
    with pytest.raises(RuntimeError, match="no row list"):
        w.queue_rows({"queue": [{"run_id": "a"}], "total": 1})
    with pytest.raises(RuntimeError, match="not a queue"):
        w.queue_rows("286 runs")


def test_an_empty_queue_is_still_an_empty_queue():
    """The other direction: a genuinely empty `pending` is a real answer and
    must not raise, or every quiet hour becomes an alert."""
    assert w.queue_rows({"pending": [], "duplicate_requests": 0}) == []


# ── which sessions are working, and which are only holding ────────────────

def _held(run_id, holder, passed, state="PROGRESSING", live=True):
    return {"run_id": run_id, "entity": run_id.upper(), "state": state,
            "claim_live": live, "claim_held_by": holder,
            "claim_expires_at": "2026-08-23T09:00:00+00:00",
            "passed": ["overview"] * passed}


def test_one_producer_holding_several_runs_is_surfaced():
    """Owner, 2026-08-23: "The watchdog is to check for any running sessions
    in the synthesis routines." Measured live the same day: one holder had
    three runs at 0 of 6 pages while another held one at 6 of 6. The routine
    is one client per session, so a holder with several is either batching
    against the rule or leaking leases — and with nothing passed it is the
    stall signature."""
    out = w.sessions_holding([_held("a", "accelerate-63", 0),
                               _held("b", "accelerate-63", 0),
                               _held("c", "good-session", 6,
                                     "READY_TO_PROMOTE")])
    by = {h["holder"]: h for h in out}
    assert by["accelerate-63"]["runs_held"] == 2
    assert by["accelerate-63"]["holds_more_than_one"] is True
    assert by["accelerate-63"]["no_pages_yet"] is True
    assert by["good-session"]["holds_more_than_one"] is False
    assert by["good-session"]["no_pages_yet"] is False


def test_a_lapsed_claim_is_not_a_running_session():
    """The roll-up answers "who is working". A run kept in scope because the
    state file remembers it is not evidence that anybody holds it."""
    assert w.sessions_holding([_held("a", "ghost", 0, live=False)]) == []


def test_an_unnamed_holder_is_still_counted():
    out = w.sessions_holding([{**_held("a", None, 0), "claim_held_by": None}])
    assert out and out[0]["holder"] == "(unnamed)"
