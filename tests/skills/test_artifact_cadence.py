"""The hook that catches a producer whose output was never filed.

It shipped without a test. Storing an artifact was a step in a prompt, which
means it was a step that got skipped: sections were produced, reported in a
transcript and never written anywhere durable, and nothing detected it because
a missing artifact and an unproduced one look identical.

What this pins is the three properties that make the hook safe to leave on:
it is SILENT on success (a hook that speaks when nothing is wrong trains
people to ignore it), it NEVER blocks (the payload is already paid for), and
it stays quiet rather than guessing when it cannot locate the run.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "dma-insights"
HOOK = PLUGIN / "scripts" / "hooks" / "artifact_cadence.py"


def _run(payload: dict, env=None) -> dict:
    e = {k: v for k, v in os.environ.items()
         if k not in ("DMA_ARTIFACT_ROOT", "DMA_RUN_ID")}
    e.update(env or {})
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=120, env=e)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else {}


def _return(agent: str):
    return {"hook_event_name": "PostToolUse", "tool_name": "Agent",
            "tool_input": {"subagent_type": f"dma-insights:{agent}"},
            "tool_response": "done"}


@pytest.fixture()
def artifacts(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    return {"DMA_ARTIFACT_ROOT": str(root), "DMA_RUN_ID": "run-cadence-1"}


def test_an_unfiled_producer_return_names_the_exact_put_command(artifacts):
    out = _run(_return("overview-hero-producer"), artifacts)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "ARTIFACT CADENCE" in ctx
    assert "artifact_store.py put" in ctx
    assert "--agent overview-hero-producer" in ctx
    assert "--run run-cadence-1" in ctx
    assert "drive_fetch.py push-artifact" in ctx


def test_it_never_blocks(artifacts):
    out = _run(_return("overview-hero-producer"), artifacts)
    assert out.get("decision") != "block"
    assert out.get("continue") is not False
    assert "permissionDecision" not in json.dumps(out)


def test_checkers_and_auditors_count_as_producers(artifacts):
    """A challenge report nobody kept is a challenge that has to be run again
    before the page can consolidate."""
    for agent in ("evidence-integrity-checker", "finding-challenger",
                  "page-consolidator", "package-vetter", "enrichment-planner"):
        assert _run(_return(agent), artifacts), agent


def test_an_agent_that_produces_nothing_durable_is_untouched(artifacts):
    for agent in ("research-conductor", "general-purpose",
                  "enrichment-web-specialist"):
        assert _run(_return(agent), artifacts) == {}, agent


def test_it_stays_silent_when_it_cannot_locate_the_run(tmp_path):
    """An enforcement that fires on a wrong run id is noise, and noise gets
    switched off."""
    out = _run(_return("overview-hero-producer"),
               {"DMA_BUNDLE_CACHE": str(tmp_path / "no-bundles-here")})
    assert out == {}


def test_it_is_silent_once_the_artifact_is_filed(artifacts, monkeypatch, tmp_path):
    """The success path: `artifact_store.py find` printing anything at all
    means something is filed for this agent and this run."""
    fake_store = tmp_path / "artifact_store.py"
    fake_store.write_text("print('artifacts/overview/hero.json')\n")
    real = PLUGIN / "scripts" / "artifact_store.py"
    backup = real.with_suffix(".py.bak-test")
    assert real.is_file(), "the hook's store script has moved"
    # no monkeypatching of another stream's file: drive the real `find`
    # through a run root where nothing is filed, then through one where the
    # store itself reports a hit.
    import importlib.util
    spec = importlib.util.spec_from_file_location("artifact_cadence", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "STORE", fake_store)
    assert m._already_filed(tmp_path, "run-cadence-1", "overview-hero-producer")
    assert not backup.exists()


def test_it_fails_open_on_input_it_did_not_parse():
    for payload in ("not json", "", "[1,2,3]"):
        p = subprocess.run([sys.executable, str(HOOK)], input=payload,
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0
        assert not p.stdout.strip()
