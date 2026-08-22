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


def test_the_roster_is_the_full_47():
    names = agent_run.roster()
    assert len(names) == 47
    for required in ("finding-challenger", "page-consolidator",
                     "package-vetter", "surface-producer", "qa-overseer",
                     "overview-whynow-producer"):
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
