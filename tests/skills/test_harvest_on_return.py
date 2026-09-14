"""A returning lane's `search_requests` reach the queue, or they reach nobody.

MEM-0333: the protocol said a lane must emit `search_requests` and "the
orchestrating session drains them", and zero code read one. This hook is the
drain at the moment it is free — the lane has returned, its output is in
hand, nothing has been summarised away.

These pin the three things that make it worth having: the grammar is relay's
own (not a second parser), it NEVER blocks, and it says the one thing a lane
cannot say about itself — that it wrote nothing.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "dma-insights"
HOOK = PLUGIN / "scripts" / "hooks" / "harvest_on_return.py"
SKILL = PLUGIN / "skills" / "dma-research"


def _mod():
    spec = importlib.util.spec_from_file_location("harvest_on_return", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def run(tmp_path: Path) -> Path:
    d = tmp_path / "run-harvest"
    (d / "07_qa").mkdir(parents=True)
    (d / f"DMA_Scoring_Workbook_{d.name}.xlsx").write_bytes(b"stub")
    (d / "07_qa" / "pipeline_state.json").write_text(json.dumps({}))
    return d


@pytest.fixture()
def hook(run, monkeypatch):
    monkeypatch.setenv("DMA_RUN_ID", run.name)
    monkeypatch.setenv("DMA_RUN_ROOT", str(run))
    return _mod()


RETURN_WITH_REQUESTS = """
I closed four cells and could not close two.

```json
{"search_requests": [
  {"query": "acme bank core banking platform migration 2025",
   "subcap": "P1C1.3", "facet": "works"},
  {"query": "acme bank digital account opening abandonment rate",
   "subcap": "P1C1.4"}
]}
```
"""


# ── the grammar is relay's ───────────────────────────────────────────────

def test_the_requests_are_queued_through_the_engines_own_harvest(hook, run):
    got = hook.harvest(run and _located(hook), "research-p1c1-producer",
                       RETURN_WITH_REQUESTS)
    assert got["harvested"] == 2, got
    queue = (run / "07_qa" / "search_relay.jsonl")
    assert queue.is_file()
    rows = [json.loads(line) for line in queue.read_text().splitlines() if line.strip()]
    assert {r["subcap"] for r in rows} == {"P1C1.3", "P1C1.4"}
    assert all(r["lane"] == "research-p1c1-producer" for r in rows)


def _located(hook):
    return hook.ctx.locate()


def test_harvesting_twice_queues_one_copy(hook, run):
    r = _located(hook)
    first = hook.harvest(r, "research-p1c1-producer", RETURN_WITH_REQUESTS)
    second = hook.harvest(r, "research-p1c1-producer", RETURN_WITH_REQUESTS)
    assert first["harvested"] == 2 and second["harvested"] == 0
    # which is what makes H4 and the SubagentStop recorder safe to both run
    assert second["seen"] == 2


def test_a_return_with_no_requests_harvests_nothing(hook):
    got = hook.harvest(_located(hook), "research-p1c1-producer",
                       "I closed every cell. Nothing outstanding.")
    assert got == {"harvested": 0, "seen": 0, "unqueued": 0, "note": ""}


def test_the_key_in_prose_shape_is_read_too(hook, run):
    """Relay's grammar admits three shapes; the hook inherits all three
    because it calls relay rather than re-implementing it."""
    text = ('I need help. My search_requests are: "search_requests": '
            '[{"query": "acme bank fraud model governance", "subcap": "P1C1.9"}] '
            'and that is all.')
    got = hook.harvest(_located(hook), "research-p1c1-producer", text)
    assert got["harvested"] == 1


# ── the response, read ───────────────────────────────────────────────────

def test_the_tool_response_is_flattened_whatever_shape_it_arrives_in(hook):
    for shape in (
        "plain text",
        {"content": "plain text"},
        {"content": [{"type": "text", "text": "plain text"}]},
        [{"type": "text", "text": "plain text"}],
    ):
        assert "plain text" in hook.response_text({"tool_response": shape})


# ── the report ───────────────────────────────────────────────────────────

def test_a_lane_that_wrote_nothing_is_told_not_to_be_re_dispatched(hook, run):
    r = _located(hook)
    hook.ctx.record_dispatch(r, "research-p1c1-producer")
    out = hook.context_for(r, "research-p1c1-producer",
                           "I searched a lot and found things.")
    assert out and "SUBSTRATE DID NOT CHANGE" in out
    assert "DO NOT RE-DISPATCH IT VERBATIM" in out
    assert "read the handback" in out.lower()


def test_a_lane_that_wrote_is_not_accused(hook, run):
    r = _located(hook)
    hook.ctx.record_dispatch(r, "research-p1c1-producer")
    out = hook.context_for(r, "research-p1c1-producer", RETURN_WITH_REQUESTS)
    assert out
    assert "SUBSTRATE DID NOT CHANGE" not in out
    assert "RELAY" in out


def test_with_no_dispatch_recorded_it_claims_nothing(hook, run):
    """No fingerprint to compare against is not evidence of no write."""
    out = hook.context_for(_located(hook), "research-p1c1-producer",
                           "I searched a lot.")
    assert out is None or "SUBSTRATE DID NOT CHANGE" not in out


def test_a_pending_relay_batch_names_the_specialist_that_services_it(hook, run):
    (run / "07_qa" / "pipeline_state.json").write_text(json.dumps(
        {"relay_batches": [str(run / "briefs" / "relay_r1" / "batch.md")]}))
    r = _located(hook)
    hook.harvest(r, "research-p1c1-producer", RETURN_WITH_REQUESTS)
    out = hook.context_for(r, "research-p1c1-producer", RETURN_WITH_REQUESTS)
    assert out and "enrichment-web-specialist" in out
    assert "agent_run.py" in out


# ── the contract ─────────────────────────────────────────────────────────

def _cli(payload: str, env=None) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True, timeout=180, env=e)


def test_it_never_blocks_and_never_denies(run):
    p = _cli(json.dumps({
        "tool_name": "Agent", "hook_event_name": "PostToolUse",
        "tool_input": {"subagent_type": "dma-insights:research-p1c1-producer"},
        "tool_response": RETURN_WITH_REQUESTS}),
        env={"DMA_RUN_ID": run.name, "DMA_RUN_ROOT": str(run)})
    assert p.returncode == 0, p.stderr
    if p.stdout.strip():
        doc = json.loads(p.stdout)
        assert doc.get("decision") != "block"
        assert "permissionDecision" not in json.dumps(doc)
        assert doc["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_a_non_dma_subagent_is_untouched(run):
    p = _cli(json.dumps({
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose"},
        "tool_response": RETURN_WITH_REQUESTS}),
        env={"DMA_RUN_ID": run.name, "DMA_RUN_ROOT": str(run)})
    assert p.returncode == 0 and not p.stdout.strip()


def test_it_fails_open_on_input_it_did_not_parse():
    for payload in ("not json", "", "[1,2,3]"):
        p = _cli(payload)
        assert p.returncode == 0
        assert not p.stdout.strip()
