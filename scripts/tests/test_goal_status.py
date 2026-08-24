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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
