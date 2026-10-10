"""SubagentStop on a research lane: write the handback, do not hold the lane.

MEASURED IN THIS CONTAINER (Claude Code 2.1.270, 2026-09-14): SubagentStop
FIRES for Agent-tool subagents. A probe bound SubagentStart/SubagentStop/Stop
to a hook that appended its stdin to a file and dispatched one general-purpose
subagent through the Agent tool; both subagent events arrived, carrying
`agent_type`, `agent_id`, `stop_hook_active`, `last_assistant_message` and
`agent_transcript_path` — a JSONL of the subagent's own turns, in exactly the
shape `relay.lane_output` already reads.

So the binding is real, and H4 remains the parent-side cover. What these pin
is that the recorder is HONEST (every number read from the run) and
NON-BLOCKING: a lane that cannot finish is re-dispatched with its handback,
inside the run's budget — forcing it to continue burns turns against the same
wall it just hit.
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
HOOK = PLUGIN / "scripts" / "hooks" / "record_handback.py"


def _mod():
    spec = importlib.util.spec_from_file_location("record_handback", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def run(tmp_path: Path) -> Path:
    d = tmp_path / "run-handback"
    (d / "07_qa").mkdir(parents=True)
    (d / f"DMA_Scoring_Workbook_{d.name}.xlsx").write_bytes(b"stub")
    return d


@pytest.fixture()
def transcript(tmp_path: Path) -> Path:
    """The real shape: the subagent's own JSONL, assistant text blocks."""
    p = tmp_path / "agent-a8de91264b2b7724e.jsonl"
    rows = [
        {"type": "user", "isSidechain": True,
         "message": {"role": "user", "content": "Work P1C1."}},
        {"type": "assistant", "isSidechain": True, "message": {
            "role": "assistant", "content": [
                {"type": "text", "text":
                 'Two cells need the connector.\n```json\n{"search_requests": '
                 '[{"query": "acme bank core migration", "subcap": "P1C1.3"}]}'
                 '\n```'}]}},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def _event(run: Path, transcript: Path, agent="research-p1c1-producer"):
    return {"hook_event_name": "SubagentStop",
            "agent_type": f"dma-insights:{agent}",
            "agent_id": "a8de91264b2b7724e",
            "stop_hook_active": False,
            "last_assistant_message": "Two cells need the connector.",
            "agent_transcript_path": str(transcript)}


def _hook(run, monkeypatch):
    monkeypatch.setenv("DMA_RUN_ID", run.name)
    monkeypatch.setenv("DMA_RUN_ROOT", str(run))
    return _mod()


def test_the_handback_is_written_where_the_re_dispatch_reads_it(run, transcript,
                                                                monkeypatch):
    m = _hook(run, monkeypatch)
    where = m.record(_event(run, transcript))
    assert where is not None
    assert where.parent == run / "07_qa" / "handbacks"
    doc = json.loads(where.read_text())
    assert doc["agent"] == "research-p1c1-producer"
    assert doc["category"] == "P1C1"
    assert doc["run_id"] == run.name
    for key in ("still_open", "notes_written", "substrate_writes"):
        assert key in doc, key


def test_the_requests_are_read_out_of_the_agent_transcript(run, transcript,
                                                           monkeypatch):
    m = _hook(run, monkeypatch)
    doc = json.loads(m.record(_event(run, transcript)).read_text())
    assert [r["subcap"] for r in doc["search_requests"]] == ["P1C1.3"]
    assert doc["search_requests"][0]["query"].startswith("acme bank core")


def test_the_transcript_reader_is_relays(run, transcript, monkeypatch):
    """One reader for both transcript kinds — `relay.lane_output` walks a
    `result` event first and falls back to assistant text blocks, which is
    exactly the agent transcript's shape."""
    m = _hook(run, monkeypatch)
    text = m.lane_text(str(transcript))
    assert "search_requests" in text


def test_a_missing_transcript_still_writes_a_handback(run, monkeypatch):
    m = _hook(run, monkeypatch)
    where = m.record({"agent_type": "research-p2c1-producer",
                      "agent_transcript_path": "/nonexistent/x.jsonl"})
    assert where is not None
    assert json.loads(where.read_text())["search_requests"] == []


def test_substrate_writes_is_null_when_there_is_nothing_to_compare(run,
                                                                   transcript,
                                                                   monkeypatch):
    m = _hook(run, monkeypatch)
    doc = json.loads(m.record(_event(run, transcript)).read_text())
    assert doc["substrate_writes"] is None


def test_substrate_writes_is_false_when_the_lane_changed_nothing(run, transcript,
                                                                 monkeypatch):
    m = _hook(run, monkeypatch)
    m.ctx.record_dispatch(m.ctx.locate(), "research-p1c1-producer")
    doc = json.loads(m.record(_event(run, transcript)).read_text())
    assert doc["substrate_writes"] is False


def test_only_research_lanes_are_recorded(run, transcript, monkeypatch):
    m = _hook(run, monkeypatch)
    assert m.record(_event(run, transcript, agent="scoring-p1-producer")) is None
    assert m.record(_event(run, transcript, agent="general-purpose")) is None


# ── the contract: never blocks ───────────────────────────────────────────

def _cli(payload: str, env=None) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True, timeout=120, env=e)


def test_it_never_blocks_the_lane(run, transcript):
    p = _cli(json.dumps(_event(run, transcript)),
             env={"DMA_RUN_ID": run.name, "DMA_RUN_ROOT": str(run)})
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout) if p.stdout.strip() else {}
    assert out.get("decision") != "block"
    assert out.get("continue") is not False
    if out:
        assert out["hookSpecificOutput"]["hookEventName"] == "SubagentStop"
        assert "not a request to keep working" in \
            out["hookSpecificOutput"]["additionalContext"]


def test_it_fails_open_on_input_it_did_not_parse():
    for payload in ("not json", "", "[1,2,3]"):
        p = _cli(payload)
        assert p.returncode == 0
        assert not p.stdout.strip()
