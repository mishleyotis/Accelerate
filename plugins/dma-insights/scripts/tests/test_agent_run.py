"""The headless dispatch fallback: trigger-fired sessions carry no Agent
tool (measured 2026-08-20 — the first live synthesis firing correctly
blocked rather than write six pages inline), so the routed pipeline runs
each stage as `claude -p --agent dma-insights:<name>`. What pins here is
the routing discipline: the roster is real, a guessed name refuses, and
the dispatch-mode preamble keeps enrichment honest in children that carry
no claude.ai connectors.
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import agent_run  # noqa: E402


def test_the_roster_is_the_full_64():
    names = agent_run.roster()
    assert len(names) == 64, (
        "47 production/QA agents + the research-conductor + 16 "
        "category researchers")
    for required in ("finding-challenger", "page-consolidator",
                     "package-vetter", "surface-producer", "qa-overseer",
                     "overview-whynow-producer", "research-conductor",
                     "research-p1c1-producer", "research-p4c4-producer"):
        assert required in names, required


def test_an_unknown_agent_refuses_instead_of_routing_to_nothing():
    with pytest.raises(SystemExit) as e:
        agent_run.main(["--agent", "overview-producer",
                        "--prompt-file", "/dev/null"])
    assert "route to nothing" in str(e.value)


def test_the_plugin_prefix_is_accepted_and_stripped(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd

        class R:
            returncode = 0
            # A real verdict: agent_run now refuses an empty one as a failed
            # stage (MEM-0111), so these fixtures must look like work.
            stdout = "verdict: " + "x" * 400
            stderr = ""
        return R()

    monkeypatch.setattr(agent_run.subprocess, "run", fake_run)
    rc = agent_run.main(["--agent", "dma-insights:finding-challenger",
                         "--prompt-file", __file__])
    assert rc == 0
    assert "dma-insights:finding-challenger" in captured["cmd"]
    assert "--agent" in captured["cmd"] and "-p" in captured["cmd"]


def test_the_preamble_forbids_fabricated_searches(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["prompt"] = cmd[-1]

        class R:
            returncode = 0
            # A real verdict: agent_run now refuses an empty one as a failed
            # stage (MEM-0111), so these fixtures must look like work.
            stdout = "verdict: " + "x" * 400
            stderr = ""
        return R()

    monkeypatch.setattr(agent_run.subprocess, "run", fake_run)
    agent_run.main(["--agent", "package-vetter", "--prompt-file", __file__])
    p = captured["prompt"]
    assert "search_requests" in p and "NOT the claude.ai" in p
    assert "do NOT fabricate" in p.replace("not fabricate", "NOT fabricate")


def test_an_empty_prompt_is_refused():
    with pytest.raises(SystemExit) as e:
        agent_run.main(["--agent", "package-vetter",
                        "--prompt-file", "/dev/null"])
    assert "empty prompt" in str(e.value)


# ── a starved child must not return an empty verdict ──────────────────────
#
# MEM-0111 and MEM-0112, both BLOCKER, measured 2026-08-20. This dispatched
# with `--allowedTools=mcp__plugin_dma-insights_connector` alone, and dontAsk
# DENIES anything not pre-approved rather than asking — so the child lost Bash
# and Read as well. One probe returned `verified_this_session: []` with three
# tool families blocked; another measured 0 of 4 connector-or-python
# capabilities, i.e. 0 of the 4 mandatory local checkers runnable and 0 of 34
# sections producible.
#
# The permission grant is half the fix. The other half is that an agent with
# no tools DOES NOT REPORT having no tools — it returns an empty verdict, and
# the caller read that as a stage that ran and found nothing. That half
# survives any future starvation, which is why it is tested separately.

class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _dispatch(monkeypatch, tmp_path, proc):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["kw"] = kw
        return proc

    monkeypatch.setattr(agent_run.subprocess, "run", fake_run)
    p = tmp_path / "stage.md"
    p.write_text("do the thing")
    rc = agent_run.main(["--agent", "finding-challenger",
                         "--prompt-file", str(p)])
    return rc, seen


def test_the_child_can_reach_the_package_directory(monkeypatch, tmp_path):
    """The measured refusal, verbatim: "ls in '/root/.dma/packages/…' was
    blocked … may only list files in '/home/user/Accelerate'." The package,
    the resume bundles and the client memory all live under /root/.dma."""
    _, seen = _dispatch(monkeypatch, tmp_path, _Proc(stdout="x" * 500))
    assert "--add-dir" in seen["cmd"]
    assert "/root/.dma" in seen["cmd"]


def test_the_child_can_run_the_local_checkers(monkeypatch, tmp_path):
    """0 of 4 mandatory checkers were runnable because Bash was not granted."""
    _, seen = _dispatch(monkeypatch, tmp_path, _Proc(stdout="x" * 500))
    allowed = next(c for c in seen["cmd"] if c.startswith("--allowedTools="))
    for tool in ("Bash", "Read", "Glob", "Grep",
                 "mcp__plugin_dma-insights_connector"):
        assert tool in allowed, f"{tool} is not pre-approved, so dontAsk denies it"


def test_an_empty_verdict_is_a_failed_stage(monkeypatch, tmp_path, capsys):
    """The half that survives any permission fix. A child that produced
    nothing exits 0, and that used to be returned as the stage's result."""
    rc, _ = _dispatch(monkeypatch, tmp_path, _Proc(returncode=0, stdout=""))
    assert rc == 125, "exit 0 with no output is not a clean stage"
    assert "PRODUCED NOTHING" in capsys.readouterr().err


def test_a_blocked_child_is_named_even_when_it_wrote_plenty(
        monkeypatch, tmp_path, capsys):
    """A child can be verbose ABOUT being blocked. The markers are the
    sentences a starved child actually emitted."""
    said = ("I tried to read the package but ls in '/root/.dma/packages/x' "
            "was blocked. For security, Claude Code may only list files in "
            "the allowed working directories for this session.") * 4
    rc, _ = _dispatch(monkeypatch, tmp_path, _Proc(returncode=0, stdout=said))
    assert rc == 125
    assert "PRODUCED NOTHING" in capsys.readouterr().err


def test_a_real_verdict_passes_through(monkeypatch, tmp_path, capsys):
    verdict = ('{"surface":"heatmap.cell_evidence","claims_challenged":9,'
               '"verdicts":[{"claim":"peer median 3.0","label":"HOLDS",'
               '"basis":"Peer_Median_Directional row 2 of the workbook '
               'package_map resolves","storyline_alignment":"carries"}]}')
    assert len(verdict) > agent_run._MIN_VERDICT
    rc, _ = _dispatch(monkeypatch, tmp_path, _Proc(returncode=0, stdout=verdict))
    assert rc == 0
    assert verdict in capsys.readouterr().out, "output is the child's, verbatim"


def test_a_nonzero_child_keeps_its_own_exit_code(monkeypatch, tmp_path):
    """A stage that failed for its own reasons reports that reason, not 125."""
    rc, _ = _dispatch(monkeypatch, tmp_path, _Proc(returncode=3, stdout=""))
    assert rc == 3
