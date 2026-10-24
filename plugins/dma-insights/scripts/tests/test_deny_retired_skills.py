"""The retired-skill guard: a legacy phrase lands on the current owner.

Measured 28-09-2026 (QA audit F-A05-001 / F-B03-002, regression seed 10):
dma-p1, dma-orchestrator and dma-core were still installed at account
level with live triggers, and a fresh router sent 6 of 64 utterances to
them. The plugin cannot delete an account skill; it can refuse to load
one and name the owner.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "deny_retired_skills.py"


def _run(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    r = subprocess.run([sys.executable, str(HOOK)], input=raw,
                       capture_output=True, text=True)
    assert r.returncode == 0  # the guard never errors a call, it decides
    return json.loads(r.stdout) if r.stdout.strip() else None


def _skill(name, key="skill"):
    return {"tool_name": "Skill", "tool_input": {key: name}}


def _deny_reason(out):
    h = (out or {}).get("hookSpecificOutput", {})
    assert h.get("permissionDecision") == "deny", out
    return h["permissionDecisionReason"]


@pytest.mark.parametrize("name", [
    "dma-p1", "dma-orchestrator", "dma-core",
    "anthropic-skills:dma-p1", "anthropic-skills:dma-orchestrator",
    "anthropic-skills:dma-core", "/dma-p1",
])
def test_a_retired_skill_is_denied_and_the_owner_is_named(name):
    reason = _deny_reason(_run(_skill(name)))
    assert "RETIRED" in reason and "dma-insights:dma-research" in reason


@pytest.mark.parametrize("name", [
    "anthropic-skills:dma-assessment", "anthropic-skills:dma-research",
    "anthropic-skills:dma-governance", "anthropic-skills:dma-first-call-deck",
])
def test_an_account_copy_of_a_plugin_skill_is_redirected_to_the_plugin_copy(name):
    reason = _deny_reason(_run(_skill(name)))
    assert "dma-insights:" + name.split(":")[-1] in reason


@pytest.mark.parametrize("name", [
    "dma-insights:dma-research", "dma-insights:dma-assessment",
    "dma-insights:dma-surface-production", "dma-insights:run-assessment",
    "anthropic-skills:dma-ai-overlay", "anthropic-skills:zennify-narrative",
    "dataviz", "code-review",
])
def test_every_live_skill_is_allowed(name):
    assert _run(_skill(name)) is None


def test_the_name_may_arrive_under_another_key():
    assert "RETIRED" in _deny_reason(_run(_skill("dma-p1", key="name")))


def test_other_tools_and_unparsable_input_fail_open():
    assert _run({"tool_name": "Bash", "tool_input": {"command": "dma-p1"}}) is None
    assert _run("not json") is None
    assert _run({"tool_name": "Skill"}) is None
