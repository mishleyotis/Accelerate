"""scripts/goal_status.py — the standing goal's state, measured not remembered.

WHY THE TOOL EXISTS. The owner's standing goal has several parts and the
answer to "is it done" kept living in a chat transcript. A transcript cannot
be re-run, goes stale the moment anything changes, and a session resuming on
a fresh container has no access to it — which happened in this build, and the
whole state had to be recovered from the remote.

WHY THESE TESTS EXIST, which is a sharper point. The first version of the
tool reported `dma-rectification-weekly`'s trigger id as the synthesis
routine's, because a dotall match walked past the section boundary and took
the next trigger id it found. A status tool that is confidently wrong is
worse than no status tool: it launders a guess into a measurement. So the
identifiers it prints are pinned here against the document it reads.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "goal_status.py"
ROUTINES = ROOT / "plugins" / "dma-insights" / "docs" / "ROUTINES.md"


def _load():
    spec = importlib.util.spec_from_file_location("goal_status", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GS = _load()


# ── the identifiers it prints must be the ones the document declares ───

def test_it_reads_each_routines_trigger_from_that_routines_own_section():
    """The regression that produced these tests: a document-wide dotall match
    returned the NEXT trigger id after the heading, which belonged to a
    different routine entirely."""
    GS.results.clear()
    GS.check_routines(offline=True)
    line = next(d for p, _s, d in GS.results if "are declared" in p)
    text = ROUTINES.read_text()
    for lane, marker in (("a", "8 */12 * * *"), ("b", "18 */12 * * *")):
        trig = next(t for t in _trigs_in(line) if _lane_of(text, t) == lane)
        assert marker in _section_for(text, trig), (
            f"lane {lane} reported {trig}, whose section does not carry the "
            f"cron {marker} — that is a different routine")


def _trigs_in(line: str) -> list[str]:
    """The ids the tool printed, without the punctuation around them."""
    import re
    return re.findall(r"\btrig_[A-Za-z0-9]+", line)


def _section_for(text: str, trig: str) -> str:
    i = text.index(trig)
    start = text.rfind("\n### ", 0, i)
    end = text.find("\n### ", i)
    return text[start: end if end > 0 else len(text)]


def _lane_of(text: str, trig: str) -> str:
    sec = _section_for(text, trig)
    return "a" if "dma-synthesis-sequence-a" in sec.split("\n")[1] else "b"


def test_it_finds_exactly_the_two_synthesis_routines():
    GS.results.clear()
    GS.check_routines(offline=True)
    line = next(d for p, _s, d in GS.results if "are declared" in p)
    trigs = _trigs_in(line)
    assert len(trigs) == 2, trigs
    assert len(set(trigs)) == 2, "the two lanes must not share a trigger id"


def test_a_missing_routine_is_a_failure_not_a_pass():
    """The tool must not report green because it could not find something."""
    GS.results.clear()
    real = GS.ROOT
    try:
        GS.ROOT = Path("/nonexistent")
        GS.check_routines(offline=True)
    finally:
        GS.ROOT = real
    state = next(s for p, s, _d in GS.results if "are declared" in p)
    assert state == GS.FAIL


# ── an unrun check must never read as a passing one ────────────────────

@pytest.mark.parametrize("fn", ["check_backlog", "check_corpus"])
def test_offline_checks_report_unknown_rather_than_pass(fn):
    GS.results.clear()
    getattr(GS, fn)(offline=True)
    assert GS.results, fn
    assert all(s == GS.UNKNOWN for _p, s, _d in GS.results), GS.results


def test_the_states_are_distinct_and_only_failing_exits_nonzero():
    """OPEN and UNKNOWN are states of the world, not defects in it. A status
    tool that exits 1 because a permission is missing teaches people to stop
    running it."""
    assert len({GS.OK, GS.FAIL, GS.OPEN, GS.UNKNOWN}) == 4
    src = TOOL.read_text()
    assert "return 1 if counts[FAIL] else 0" in src


# ── the failure-rate check must not repeat the mistakes it was born from ──

def test_the_refusal_count_never_reads_the_exit_code_or_greps_the_word():
    """Both were done once and produced a false 23-of-26 refusal rate: exit 1
    documents 'findings that need a decision', and the word REFUSE appears in
    the script's own explanatory footer on every run. MEM-0221."""
    src = TOOL.read_text()
    assert 'startswith("[REFUSE]")' in src
    assert "MEM-0221" in src, "and the tool says why, where a reader will see it"


def test_absent_packages_are_unknown_not_zero_refusals():
    GS.results.clear()
    real = GS.PKGS
    try:
        GS.PKGS = Path("/nonexistent/packages")
        GS.check_failure_rate(offline=False)
    finally:
        GS.PKGS = real
    assert next(s for _p, s, _d in GS.results) == GS.UNKNOWN


# ── it runs ────────────────────────────────────────────────────────────

def test_the_tool_runs_offline_and_reports_every_part():
    r = subprocess.run([sys.executable, str(TOOL), "--offline"],
                       capture_output=True, text=True, cwd=ROOT, timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    for part in ("routines", "failure rate", "backlog", "corpus", "headless",
                 "model"):
        assert part in out, part
    assert "passing ·" in out


# ── the two defects that kept CI red for six commits ──────────────────
#
# Neither was in a check. Both were in the machinery that REPORTS the
# checks, which is worse: the report stayed tidy, the counts stayed right,
# and one whole part quietly stopped being covered.


def test_an_unreadable_package_dir_is_not_the_same_answer_as_an_absent_one():
    """`Path.is_dir()` swallows ENOENT, ENOTDIR, EBADF and ELOOP and
    RE-RAISES everything else — EACCES included. On a CI runner /root is
    0700 and root-owned, so the probe raised where it looked like it would
    return False. Absent and unreadable are different claims."""
    class Denied:
        """Stands in for the path: Path is not subclassable before 3.12, and
        the check only ever calls is_dir() and formats the value."""
        def is_dir(self):
            raise PermissionError(13, "Permission denied")

        def __str__(self):
            return "/root/.dma/packages"

    GS.results.clear()
    old = GS.PKGS
    try:
        GS.PKGS = Denied()
        GS.check_failure_rate(offline=True)
    finally:
        GS.PKGS = old
    (part, state, detail), = GS.results
    assert part.startswith("failure rate"), \
        "the part keeps its own name even when its probe cannot run"
    assert state == GS.UNKNOWN
    assert "cannot be read" in detail and "NOT the same as absent" in detail


def test_an_absent_package_dir_still_says_absent():
    """The other half: the fix must not turn every miss into 'unreadable'."""
    GS.results.clear()
    old = GS.PKGS
    try:
        GS.PKGS = Path("/nonexistent-corpus-root/packages")
        GS.check_failure_rate(offline=True)
    finally:
        GS.PKGS = old
    (_part, state, detail), = GS.results
    assert state == GS.UNKNOWN and "is not present" in detail


def test_a_crashed_check_is_still_findable_under_its_own_name():
    """main()'s fallback reported `fn.__name__`, so "failure rate" vanished
    from a report that still printed a tidy 3-passing count. A reader
    scanning for a part concludes the tool does not cover it."""
    prog = (
        "import sys; sys.path.insert(0, %r); import goal_status as g\n"
        "def boom(offline): raise RuntimeError('boom')\n"
        "boom.__name__ = 'check_failure_rate'\n"
        "g.check_failure_rate = boom\n"
        "sys.argv = ['goal_status', '--offline']; g.main()\n"
        % str(ROOT / "scripts"))
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                       text=True, cwd=ROOT, timeout=900)
    assert "failure rate" in r.stdout, r.stdout[-600:] + r.stderr[-600:]
    assert "CHECK CRASHED" in r.stdout
    assert "RuntimeError: boom" in r.stdout
    assert "a crash is not a pass and not a fail" in r.stdout


def test_every_check_has_a_name_to_fall_back_to():
    """A check added without a PART entry would crash the crash handler."""
    import inspect
    named = re.findall(r"\bcheck_\w+", inspect.getsource(GS.main))
    assert named, "could not find the check list in main()"
    for fn in named:
        assert fn in GS.PART, f"{fn} has no name to report a crash under"


def test_the_fallback_names_match_the_names_the_checks_print():
    """The two must not drift: a part renamed in its report but not in PART
    would file a crash under a name no reader is looking for. This caught a
    real mismatch when it was written."""
    r = subprocess.run([sys.executable, str(TOOL), "--offline"],
                       capture_output=True, text=True, cwd=ROOT, timeout=900)
    for fn, label in GS.PART.items():
        assert label in r.stdout, (fn, label)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ── the lane gauge ─────────────────────────────────────────────────────
#
# "Gauge each last chat" cannot be answered from a chat: a trigger-fired
# session's transcript is unreachable from an ordinary session, every
# claude-code-remote tool being permission-gated. It CAN be answered from
# what each firing committed, which is better evidence — it is what the lane
# chose to keep rather than what it said on the way there.

def test_both_lanes_are_gauged():
    assert set(GS.LANE_SESSIONS) == {"A", "B"}


def test_each_lane_is_matched_by_its_own_session_stamp():
    """The stamps are the ones the firings actually wrote, so a pattern that
    stops matching means the lane changed how it identifies itself — which
    should surface as an empty gauge, not as a silent pass."""
    a, b = GS.LANE_SESSIONS["A"][0], GS.LANE_SESSIONS["B"][0]
    assert a.search("agent:dma-governance learning-loop pass, session "
                    "20260823-0733-synthesis-gulf-coast-business-credit")
    assert a.search("dma-surface-production producer session gcbc-finish-20260823")
    assert b.search("dma-surface-production assembly session laneB-20260823T082509Z")
    assert b.search("agent:dma-surface-production final-assembly lane B")
    # and they must not match each other
    assert not a.search("laneB-20260823T082509Z")
    assert not b.search("gcbc-finish-20260823")


def test_a_lane_that_shipped_nothing_is_not_reported_as_passing():
    """Lane B produced no client on its last firing. Reporting the pair as
    green because both lanes exist would be the exact laundering this file
    was written to stop."""
    GS.results.clear()

    def fake(tool, **kw):
        if tool == "list_open_findings":
            return {"findings": [
                {"raised_by": "session gcbc-finish-20260823", "severity": "MAJOR"},
                {"raised_by": "assembly session laneB-20260823T082509Z",
                 "severity": "BLOCKER"}]}
        raise AssertionError(tool)

    GS._lane_outcomes(fake)
    part, state, detail = GS.results[0]
    assert state == GS.OPEN, (state, detail)
    assert "SHIPPED NOTHING" in detail


def test_the_gauge_says_the_finding_count_is_not_the_health_signal():
    """Measured: lane A recorded 16 findings and promoted its client; lane B
    recorded 3 and produced nothing. Reading the count as health inverts the
    answer, so the tool states the rule where a reader will meet it."""
    src = TOOL.read_text()
    assert "NUMBER OF FINDINGS IS NOT THE HEALTH SIGNAL" in src
    assert "the count is not the signal, the client is" in src


def test_an_unreachable_connector_makes_the_gauge_unknown_not_green():
    GS.results.clear()

    def boom(tool, **kw):
        raise RuntimeError("429 Too Many Requests")

    GS._lane_outcomes(boom)
    assert GS.results[0][1] == GS.UNKNOWN


# ── would a firing starting NOW get a client? ──────────────────────────
#
# The rejection-vs-triage question, answered by running the gate rather than
# reading it. Reading run_gate.py shows a triage-first design; running it
# shows whether that design holds against the queue as it actually is.

def test_a_gate_that_produces_nothing_is_a_failure_not_an_open_item():
    """This one IS a defect rather than a state of the world: a queue with
    ready runs and a gate that returns no client is the exact behaviour the
    owner reported."""
    GS.results.clear()
    import subprocess as sp
    real = sp.run

    class R:
        stdout = ("GATE: STOP — gated 40 of 170 queued entities and none was "
                  "producible.")
        stderr = ""

    try:
        sp.run = lambda *a, **k: R()
        GS.subprocess.run = sp.run
        GS.check_gate_produces(offline=False)
    finally:
        sp.run = real
        GS.subprocess.run = real
    assert GS.results[0][1] == GS.FAIL
    assert "none was producible" in GS.results[0][2]


def test_a_produce_line_reports_pass_with_the_run_it_named():
    GS.results.clear()
    import subprocess as sp
    real = sp.run

    class R:
        stdout = ("GATE: PRODUCE lawley run bf3754b8-5c0f-444f-bde2-550d9f35f27f\n"
                  "GATE: RESERVE bank-of-the-sierra run bfc6cb31\n"
                  "GATE: RESERVE galway-holdings run 51b57dab")
        stderr = ""

    try:
        sp.run = lambda *a, **k: R()
        GS.subprocess.run = sp.run
        GS.check_gate_produces(offline=False)
    finally:
        sp.run = real
        GS.subprocess.run = real
    part, state, detail = GS.results[0]
    assert state == GS.OK
    assert "lawley" in detail and "2 reserve(s)" in detail


def test_the_check_states_why_walking_past_a_failure_is_correct():
    """Asserted on the RENDERED detail, not the source. The sentence is
    wrapped across f-string fragments, so a source match would be pinning
    concatenation seams rather than the words a reader sees."""
    GS.results.clear()
    import subprocess as sp
    real = sp.run

    class R:
        stdout = "GATE: PRODUCE lawley run bf3754b8\nGATE: RESERVE x run y"
        stderr = ""

    try:
        GS.subprocess.run = lambda *a, **k: R()
        GS.check_gate_produces(offline=False)
    finally:
        GS.subprocess.run = real
    detail = GS.results[0][2]
    assert "a finding to record, not a reason to stop looking" in detail
    src = TOOL.read_text()
    assert "lawley" in src, (
        "the measurement names the package lane B refused, which is what "
        "makes this evidence rather than an assertion")


# ── readiness: which blocked lanes are this checkout's problem ──────────

def _readiness(monkeypatch, doc):
    """Run check_readiness against a canned readiness.py answer."""
    class R:
        returncode = 0
        stdout = json.dumps(doc)
        stderr = ""

    monkeypatch.setattr(GS.subprocess, "run", lambda *a, **k: R())
    GS.results.clear()
    GS.check_readiness(offline=True)
    assert len(GS.results) == 1, GS.results
    return GS.results[0]


def _lane(name, verdict, scope):
    return {"lane": name, "what": "w", "scope": scope, "verdict": verdict,
            "detail": "d", "fix": "f"}


def _doc(lanes):
    return {"lanes": lanes,
            "ready": [x for x in lanes if x["verdict"] == "READY"],
            "blocked": [x for x in lanes if x["verdict"] == "BLOCKED"],
            "unmeasured": [x for x in lanes
                           if x["verdict"] == "NOT_MEASURABLE_HERE"],
            "blocked_in_repository": [
                x for x in lanes
                if x["verdict"] == "BLOCKED" and x["scope"] == "repository"],
            "standing_open": [{"item": "i", "detail": "d", "owner": "o",
                               "specified_in": "docs/x.md"}]}


def test_a_repository_blocker_fails_the_standing_goal(monkeypatch):
    part, state, detail = _readiness(monkeypatch, _doc([
        _lane("coverage", "BLOCKED", "repository"),
        _lane("skills", "READY", "repository")]))
    assert state == GS.FAIL
    assert "coverage" in detail


def test_a_container_blocker_is_open_not_a_goal_failure(monkeypatch):
    """A stale install is real and is somebody's problem. It is not this
    checkout failing a goal, and reporting it as one teaches a reader to
    stop believing the row."""
    part, state, detail = _readiness(monkeypatch, _doc([
        _lane("install", "BLOCKED", "container"),
        _lane("coverage", "READY", "repository")]))
    assert state == GS.OPEN
    assert "install" in detail


def test_unmeasured_lanes_are_unknown_and_are_named(monkeypatch):
    part, state, detail = _readiness(monkeypatch, _doc([
        _lane("coverage", "READY", "repository"),
        _lane("routines", "NOT_MEASURABLE_HERE", "external")]))
    assert state == GS.UNKNOWN
    assert "routines" in detail


def test_every_lane_green_is_the_only_pass(monkeypatch):
    part, state, _d = _readiness(monkeypatch, _doc([
        _lane("coverage", "READY", "repository"),
        _lane("routines", "READY", "external")]))
    assert state == GS.OK


def test_readiness_that_prints_no_json_is_unknown_not_green(monkeypatch):
    class R:
        returncode = 2
        stdout = "Traceback (most recent call last):"
        stderr = "boom"

    monkeypatch.setattr(GS.subprocess, "run", lambda *a, **k: R())
    GS.results.clear()
    GS.check_readiness(offline=True)
    assert GS.results[0][1] == GS.UNKNOWN, GS.results


def test_the_standing_items_are_carried_into_the_line(monkeypatch):
    _p, _s, detail = _readiness(monkeypatch, _doc([
        _lane("coverage", "READY", "repository")]))
    assert "standing item" in detail
    assert "PRODUCTION-READINESS.md" in detail

