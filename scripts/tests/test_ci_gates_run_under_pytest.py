"""Every context-free CI gate runs here, so a green pytest means a green job.

WHAT THIS COST. 2026-08-31: the CI run on the default branch failed while the
whole 4,673-case suite passed locally and in the same workflow. The failing
job was "Architecture gates", the failing step was the FIRST one:

    SECRET SCAN FAILED:
    plugins/dma-insights/scripts/tests/test_slack_client.py:339: Slack token
    plugins/dma-insights/scripts/tests/test_slack_client.py:339:
        hardcoded credential assignment

A test asserting that a stderr note never echoes the bot token had passed a
literal `xoxb-`-prefixed string to prove it. The scanner was right twice, and
nothing in the local loop could see it: `scripts/scan_secrets.py` is a
WORKFLOW STEP, not a test. Seventeen gate scripts run in that job and pytest
ran none of them, so "the suite is green" and "CI is green" were different
claims and only one of them was checkable before pushing.

THE LIST IS DERIVED FROM ci.yml, never typed here. A gate added to the
workflow is covered the moment it lands; a gate that needs context the test
cannot supply has to be named in NEEDS_CONTEXT below, which makes skipping it
a decision somebody wrote down rather than an omission nobody noticed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"

#: Gates that cannot run from a bare checkout, and exactly why. Anything not
#: in here is EXPECTED to run clean with no arguments — that is the whole
#: point: a new gate is covered by default and opting out is explicit.
NEEDS_CONTEXT = {
    "scripts/gate_b_ceiling_ratchet.py":
        "takes a BASE commit; the workflow passes the PR base sha or HEAD~1, "
        "and a bare checkout has no meaningful baseline to ratchet against",
    "scripts/gate_j_surface_parity.py":
        "compares two rendered payloads; the workflow passes "
        "--reference-file/--target-file out of fixtures/parity",
    "scripts/extract_docs.py":
        "writes an extraction to a temp dir and diffs it; the workflow owns "
        "both paths, and running it here would duplicate that step's diff "
        "rather than check it",
}


def _gates_job() -> str:
    y = CI.read_text(encoding="utf-8")
    start = y.index("  gates:")
    nxt = re.search(r"^  [a-z][a-z0-9_-]*:\n", y[start + 10:], re.M)
    return y[start: start + 10 + nxt.start()] if nxt else y[start:]


def _invocations() -> list[tuple[str, list[str]]]:
    """(script, args) for every python3 gate the job runs."""
    out, seen = [], set()
    for m in re.finditer(
            r"python3 ((?:scripts|plugins/[\w/-]+/scripts)/[\w]+\.py)"
            r"([^\n\\|]*)", _gates_job()):
        script = m.group(1)
        if script in seen:
            continue
        seen.add(script)
        # Only flags survive; a shell variable or redirect means the workflow
        # is supplying context, which NEEDS_CONTEXT has to account for.
        args = [a for a in m.group(2).split() if a.startswith("--")]
        out.append((script, args))
    return out


def test_the_workflow_is_still_parseable():
    """Floor. An unparsed job makes every case below vacuously green — which
    is the exact failure mode this file exists to remove."""
    found = _invocations()
    assert len(found) >= 12, (
        f"only {len(found)} gate(s) parsed out of the Architecture gates job "
        f"— the workflow changed shape and this is no longer reading it")
    names = {s for s, _ in found}
    assert "scripts/scan_secrets.py" in names, (
        "the secret scan is the step that failed on 2026-08-31 and the one "
        "this file was written for; if it stopped being parsed, fix the "
        "parse before trusting anything here")


def test_every_gate_is_either_run_here_or_named_as_needing_context():
    """No third category. A gate that is neither exercised nor explained is
    one nobody decided about."""
    unaccounted = [s for s, _ in _invocations()
                   if s not in NEEDS_CONTEXT
                   and not (ROOT / s).exists()]
    assert not unaccounted, (
        f"the workflow runs gates that do not exist in this checkout: "
        f"{unaccounted}")
    for script in NEEDS_CONTEXT:
        assert (ROOT / script).exists(), (
            f"{script} is excused from running but no longer exists — the "
            f"exemption outlived the gate")


@pytest.mark.parametrize(
    "script,args",
    [pytest.param(s, a, id=s.rsplit("/", 1)[-1])
     for s, a in _invocations() if s not in NEEDS_CONTEXT])
def test_the_gate_passes(script, args):
    """Runs the gate exactly as the workflow does. A failure here is a
    failure CI would have had, found before the push instead of after."""
    r = subprocess.run([sys.executable, script, *args],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (
        f"{script} {' '.join(args)} exits {r.returncode} — the Architecture "
        f"gates job fails on this:\n"
        f"{(r.stdout or '')[-2000:]}\n{(r.stderr or '')[-2000:]}")
