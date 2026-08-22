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
