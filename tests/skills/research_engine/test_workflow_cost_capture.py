"""I-37: workflow agents' spend reaches the ledger once, and only this run's."""
from __future__ import annotations

import json

from engine import cost
from fixtures import new_run


def _agent(d, aid, run_id, turns=3):
    lines = [json.dumps({"type": "user", "message": {"content": f"work run {run_id}"}})]
    for _ in range(turns):
        lines.append(json.dumps({"type": "assistant", "message": {
            "model": "claude-sonnet-x", "usage": {"input_tokens": 10,
            "cache_read_input_tokens": 100_000, "cache_creation_input_tokens": 1000,
            "output_tokens": 50}}}))
    (d / f"agent-{aid}.jsonl").write_text("\n".join(lines))


def test_this_runs_agents_are_charged_by_delta(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    wf = tmp_path / "proj" / "sess" / "subagents" / "workflows" / "wf_1"
    wf.mkdir(parents=True)
    _agent(wf, "a1", run.run_id)
    _agent(wf, "a2", "DMA-RES-OTHER-0001")          # another run's agent
    got = cost.capture_workflows(run, base=tmp_path)
    assert got["captured"] == 1 and got["turns"] == 3 and got["usd"] > 0, got
    assert cost.capture_workflows(run, base=tmp_path)["captured"] == 0, "charged twice"
    _agent(wf, "a1", run.run_id, turns=5)            # the agent kept working
    more = cost.capture_workflows(run, base=tmp_path)
    assert more["turns"] == 2 and 0 < more["usd"] < got["usd"], more
    rows = [r for r in cost.ledger(run) if "workflow agents" in r["note"]]
    assert round(sum(r["usd"] for r in rows), 4) == round(got["usd"] + more["usd"], 4)


def test_in_session_subagents_are_charged_too(tmp_path):
    # C-31 (2026-10-01): the PRELIM connector pass runs as an in-process
    # subagent, whose transcript sits in subagents/, not subagents/workflows/.
    run = new_run(tmp_path, n=3, prelim=False)
    sub = tmp_path / "proj" / "sess" / "subagents"
    sub.mkdir(parents=True)
    _agent(sub, "s1", run.run_id, turns=4)
    _agent(sub, "s2", "DMA-RES-OTHER-0001")
    got = cost.capture_workflows(run, base=tmp_path)
    assert got["captured"] == 1 and got["turns"] == 4, got
    assert cost.capture_workflows(run, base=tmp_path)["captured"] == 0
