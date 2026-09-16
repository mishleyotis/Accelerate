"""Gate L, and the workflow shape that made it necessary.

On 2026-08-19 two runs of the same commit sat on one CI step for 33 minutes
and would have sat there for six hours: `playwright install --with-deps`
shells out to apt, apt queued behind the dpkg lock, and no job in this
repository declared a timeout. The check was neither passing nor failing. It
was `in_progress`, which reads as diligence.

Two things are pinned here. The gate itself — including its refusal to pass
having examined nothing, which is the failure mode of every scanner written
against a file format. And the shape of the step that hung, because a bound
alone would only have turned a six-hour hang into a twelve-minute one.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from gate_l_ci_jobs_are_bounded import (  # noqa: E402
    CEILING_MINUTES, jobs_in, main,
)

CI = ROOT / ".github" / "workflows" / "ci.yml"


# ── the gate ───────────────────────────────────────────────────────────

def test_the_repository_workflows_pass_today():
    assert main() == 0


def test_a_job_without_a_clock_is_named():
    found = jobs_in("jobs:\n  build:\n    runs-on: ubuntu-latest\n")
    assert found == [("build", None)]


def test_a_bounded_job_reports_its_bound():
    found = jobs_in("jobs:\n  build:\n    runs-on: ubuntu-latest\n"
                    "    timeout-minutes: 12\n")
    assert found == [("build", 12)]


def test_the_first_bound_wins_over_a_step_level_one():
    """A step's `timeout-minutes` sits at deeper indentation and must not be
    mistaken for the job's — a job bounded only through one of its steps is
    still unbounded everywhere else."""
    found = jobs_in("jobs:\n  build:\n    runs-on: ubuntu-latest\n"
                    "    steps:\n      - name: x\n        timeout-minutes: 3\n")
    assert found == [("build", None)]


def test_every_job_in_the_file_is_found_not_just_the_first():
    found = jobs_in("jobs:\n"
                    "  a:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n"
                    "  b:\n    runs-on: ubuntu-latest\n")
    assert found == [("a", 5), ("b", None)]


def test_workflow_level_keys_above_jobs_are_not_read_as_jobs():
    """`on:`, `env:` and `concurrency:` all carry two-space children that look
    exactly like job names. Reading them as jobs would report bounds on things
    that cannot hang."""
    found = jobs_in("on:\n  push:\n    branches: ['**']\n"
                    "concurrency:\n  group: x\n"
                    "jobs:\n  real:\n    runs-on: ubuntu-latest\n"
                    "    timeout-minutes: 9\n")
    assert found == [("real", 9)]


def test_a_file_that_parses_to_nothing_is_a_refusal(tmp_path, monkeypatch):
    """THE VACUOUS PASS. A scanner whose regexes have drifted out of step with
    the file finds no jobs, finds no violations, and reports success — the
    same shape as the hang it exists to catch."""
    import gate_l_ci_jobs_are_bounded as g
    wf = tmp_path / "workflows"
    wf.mkdir()
    (wf / "ci.yml").write_text("name: CI\non:\n  push:\n")
    monkeypatch.setattr(g, "WORKFLOWS", wf)
    monkeypatch.setattr(g, "ROOT", tmp_path)
    assert g.main() == 1


def test_no_workflows_at_all_is_a_refusal(tmp_path, monkeypatch):
    import gate_l_ci_jobs_are_bounded as g
    wf = tmp_path / "workflows"
    wf.mkdir()
    monkeypatch.setattr(g, "WORKFLOWS", wf)
    assert g.main() == 1


def test_a_bound_beyond_the_ceiling_fails(tmp_path, monkeypatch):
    import gate_l_ci_jobs_are_bounded as g
    wf = tmp_path / "workflows"
    wf.mkdir()
    (wf / "ci.yml").write_text(
        "jobs:\n  slow:\n    runs-on: ubuntu-latest\n"
        f"    timeout-minutes: {CEILING_MINUTES + 1}\n")
    monkeypatch.setattr(g, "WORKFLOWS", wf)
    monkeypatch.setattr(g, "ROOT", tmp_path)
    assert g.main() == 1


def test_the_scanner_agrees_with_a_real_yaml_parser():
    """The line scan is dependency-free so the gate can run on a bare
    `python3`. That is only safe while it reads the file the same way YAML
    does, so where a parser IS available, they are compared."""
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(CI.read_text())
    by_yaml = {k: v.get("timeout-minutes") for k, v in doc["jobs"].items()}
    assert dict(jobs_in(CI.read_text())) == by_yaml


# ── the step that hung ─────────────────────────────────────────────────

def test_the_browser_download_is_not_welded_to_an_apt_run():
    """`--with-deps` is the defect itself: it puts an apt-get run, which can
    queue behind a lock held by another process, in front of the download the
    suites actually need. They are separate commands now and must stay so."""
    text = CI.read_text()
    assert "install --with-deps chromium" not in text, \
        "the apt run is back in front of the browser download"
    assert "playwright@1.62.1 install chromium" in text


def test_the_apt_half_is_bounded_and_cannot_fail_the_job():
    text = CI.read_text()
    assert "install-deps chromium" in text
    line = next(l for l in text.splitlines() if "install-deps chromium" in l)
    assert "timeout" in line, "an unbounded apt run is the hang, wherever it sits"
    assert line.lstrip().startswith("if !"), \
        "ubuntu-latest already ships most of these libraries; the launch " \
        "probe decides whether a failed apt run mattered"


def test_the_install_is_proved_by_launching_not_by_stat():
    """Resolving a path proves a file exists. A missing system library only
    shows itself on launch, which is why the previous verification could not
    have caught this and the tests found it twelve files later."""
    text = CI.read_text()
    assert "Prove Chromium launches" in text
    assert "chromium.launch(" in text
    assert "chromium will not launch here" in text


# ── the skip ceiling's own diagnostic ────────────────────────────────────
#
# The ceiling step counts skips and, when it overruns, prints the reasons so
# the failure names itself. On 2026-08-30 it overran and printed a header
# with nothing under it: the invocation carried `-rs -rf`, and a second -r
# REPLACES the first rather than adding to it, so ^SKIPPED lines were never
# emitted and the grep beneath them could never match. Which three tests had
# started skipping had to be found by reproducing the whole suite locally.
#
# A diagnostic that is present and empty is worse than one that is absent,
# because the absent one gets noticed. This pins the flag that makes it real.

def _pytest_lines() -> list[str]:
    """Whole invocations, with backslash continuations folded back in.

    The ceiling's own command is written across three lines, so reading the
    file line-wise finds the word `pytest` on a line carrying none of its
    flags — a check that would pass while measuring nothing.
    """
    joined, buf = [], ""
    for raw in CI.read_text(encoding="utf-8").splitlines():
        ln = raw.strip()
        if buf:
            buf += " " + ln.rstrip("\\").strip()
            if not ln.endswith("\\"):
                joined.append(buf)
                buf = ""
            continue
        if "python -m pytest" in ln or "python3 -m pytest" in ln:
            if ln.endswith("\\"):
                buf = ln.rstrip("\\").strip()
            else:
                joined.append(ln)
    if buf:
        joined.append(buf)
    return joined


def test_a_pytest_invocation_never_carries_two_r_flags():
    """The defect in general form. `-rs -rf` looks additive and is not."""
    for ln in _pytest_lines():
        rs = [w for w in ln.split() if w.startswith("-r") and w != "-r"]
        assert len(rs) <= 1, (
            f"two -r flags in one invocation — the second replaces the "
            f"first, so one of them does nothing: {ln}")


def test_the_ceiling_step_reports_skips_as_well_as_failures():
    """The specific one: the step that greps ^SKIPPED must ask for them."""
    text = CI.read_text(encoding="utf-8")
    assert "grep '^SKIPPED'" in text, (
        "the ceiling step no longer prints the reasons it overran on")
    counting = [ln for ln in _pytest_lines() if "plugins/dma-insights" in ln
                or "tests/skills/" in ln]
    assert counting, "the ceiling's own pytest invocation was not found"
    for ln in counting:
        flags = "".join(w[2:] for w in ln.split() if w.startswith("-r"))
        assert "s" in flags, (
            f"the ceiling greps for ^SKIPPED and this invocation does not "
            f"ask pytest for skip reasons: {ln}")
        assert "f" in flags, (
            f"the report step greps for FAILED and this invocation does not "
            f"ask pytest for failure lines: {ln}")


#: Every skip-ceiling assignment in the workflow, as written.
SKIP_COUNT = re.compile(r"^\s*(n=\$\(grep -oE '\[0-9\]\+ skipped'.*)$", re.M)


def _skip_count_lines() -> list:
    return SKIP_COUNT.findall(CI.read_text(encoding="utf-8"))


@pytest.mark.parametrize("summary", [
    "82 passed in 528.40s (0:08:48)",       # the measured failure
    "1001 passed, 6 skipped in 790.06s",    # skips present
    "3 failed, 79 passed in 120.00s",       # a red run still reaches the check
])
def test_the_skip_ceiling_survives_a_run_with_nothing_to_count(summary, tmp_path):
    """RUN the assignment, do not read it.

    Measured 2026-09-14, run 34866563499: the acceptance job printed
    "82 passed in 528.40s (0:08:48)" and then "Process completed with exit
    code 1". Every test passed. The step runs under `bash -e` with pipefail,
    pytest prints no "N skipped" when nothing skipped, so grep exited 1, the
    pipeline exited 1, and the shell died ON THE ASSIGNMENT — before the
    ceiling it exists to compare was ever compared.

    A clean result is the one input a ceiling check must survive, and it was
    the only one never exercised: the older jobs pass only because their
    suites happen always to skip something. Asserting `|| true` is in the
    text would pass against a subtly different shape, so this executes each
    assignment the workflow actually contains against a summary with no skip
    line and requires exit 0 and a usable count.
    """
    lines = _skip_count_lines()
    assert lines, ("no skip-ceiling assignment found in the workflow — either "
                   "the ceilings are gone or this pattern has drifted; either "
                   "way this test is no longer guarding anything")
    out = tmp_path / "pytest.txt"
    out.write_text(summary + "\n", encoding="utf-8")
    for raw in lines:
        stmt = re.sub(r"/tmp/[a-z-]*pytest\.txt", str(out), raw)
        r = subprocess.run(
            ["bash", "-e", "-c",
             f'set -o pipefail\n{stmt}\necho "COUNT=${{n:-0}}"'],
            capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, (
            f"the skip-ceiling assignment dies on {summary!r}, so a run this "
            f"shape fails its check with every test passing: {stmt}\n"
            f"{r.stderr.strip()}")
        assert "COUNT=" in r.stdout, (
            f"the assignment ran but the step never reached the line after "
            f"it: {stmt}")
