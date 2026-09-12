"""A run may not start in an environment where it cannot finish.

Measured 2026-09-12: a live run began with no enrichment connector bound.
`declare_absence` requires one of `C.ENRICHMENT_TOOLS` and web_search is not
one, so not a single empty cell could be closed; no floors gate could pass;
the driver re-dispatched sixteen categories ~18 times for $96.65 and closed
nothing.

`connector_contract.py` already declared the required set with verdict STOP,
was tested, and was wired into the Routine prompts. It was called from
NOWHERE on the `/run-assessment` path — not by the command, not by the
conductor, and not by `engine.pipeline env`, whose own docstring calls itself
"every hard dependency, measured". `doctor.py` meanwhile returned True for
its connector row unconditionally, so the doctor went green on exactly the
state that caused the burn.

These pin the gate. A session's bound MCP tools cannot be read from a
subprocess (MEM-0112), so the check reads the BASELINE the command layer
writes — and an absent baseline is UNVERIFIED, never a pass.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
sys.path.insert(0, str(PLUGIN / "scripts"))
import connector_contract as cc  # noqa: E402

from engine import pipeline as P  # noqa: E402


def _row(root):
    os.environ["DMA_RUN_ROOT"] = str(root)
    return P._connector_row()


def test_no_baseline_is_unverified_not_a_pass(tmp_path):
    name, ok, detail = _row(tmp_path)
    assert name == "enrichment connectors"
    assert ok is False
    assert "UNVERIFIED" in detail and "not a pass" in detail
    assert "baseline" in detail, "the row must name its own remedy"


def test_a_session_with_no_connectors_is_a_stop(tmp_path):
    """THE REPRODUCTION. This is the exact roster the failing run held."""
    cc.write_baseline(["Read", "Bash", "WebSearch",
                       "mcp__plugin_dma-insights_connector__get_evidence"], tmp_path)
    _, ok, detail = _row(tmp_path)
    assert ok is False
    assert "STOP" in detail
    for fam in ("exa", "tavily"):
        assert fam in detail
    assert "declared absent" in detail, (
        "the row must say WHY it stops, or the reader repairs the wrong thing")


def test_a_session_that_holds_them_passes(tmp_path):
    fam = cc.families()
    cc.write_baseline([fam["exa"][0], fam["tavily"][0], fam["clay"][0]], tmp_path)
    _, ok, detail = _row(tmp_path)
    assert ok is True and "exa" in detail and "tavily" in detail


def test_the_connector_row_is_a_HARD_env_failure(tmp_path):
    """`toolkits` and `connector identity` are exempt by design. This one is
    not: a run that cannot close a cell must not be allowed to start."""
    os.environ["DMA_RUN_ROOT"] = str(tmp_path)
    out = P.env_check()
    assert "enrichment connectors" in out["hard_failures"]
    assert out["ok"] is False


def test_check_without_strict_exits_zero_and_the_docstring_says_so(tmp_path):
    """The trap that makes wiring this in easy to get wrong: a STOP still
    exits 0 unless --strict is passed. That default is deliberate (a caller
    may want to quote the verdict without the exit code deciding), so the
    fix is that the module SAYS it — the docstring used to claim the
    opposite."""
    fam = cc.families()
    short = fam["exa"][0]

    def run(*args):
        return subprocess.run(
            [sys.executable, str(PLUGIN / "scripts" / "connector_contract.py"),
             "check", "--tools", "-", *args],
            input=short, capture_output=True, text=True, timeout=60)

    assert run().returncode == 0, "non-strict reports without deciding"
    assert run("--strict").returncode == 1, "strict is the gate"
    assert "STOP" in run().stdout

    doc = (PLUGIN / "scripts" / "connector_contract.py").read_text()
    head = doc[:doc.index('"""', doc.index('"""') + 3)]
    assert "ONLY under" in head and "--strict" in head, (
        "the docstring must state the real contract — it used to claim exit 1 "
        "whenever a family was missing, which is false without --strict")


def test_the_run_path_actually_calls_the_preflight():
    """The whole defect in one assertion: the contract existed and nothing on
    this path invoked it."""
    cmd = (PLUGIN / "commands" / "run-assessment.md").read_text()
    conductor = (PLUGIN / "agents" / "research" / "research-conductor.md").read_text()
    for name, text in (("run-assessment.md", cmd), ("research-conductor.md", conductor)):
        assert "connector_contract.py" in text, f"{name} must invoke the preflight"
        assert "--strict" in text, f"{name} must pass --strict or the gate is not a gate"
        assert "baseline --tools -" in text, f"{name} must record the baseline"
