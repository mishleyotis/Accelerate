"""A lane's spend is never lost: priced from its stream, booked as it ends.

AAA Western and Central New York (2026-10-14): four scorer lanes timed out,
emitted no CLI result event, and their spend reached no ledger; and because
a batch booked its lanes only when the WHOLE batch returned, the driver
killed at the 2-hour background cap lost every finished lane's cost too.
"""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "agent_run.py"


def _module():
    spec = importlib.util.spec_from_file_location("agent_run", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _msg(mid, out=100):
    return {"type": "assistant", "message": {
        "id": mid, "model": "claude-sonnet-x",
        "usage": {"input_tokens": 10, "output_tokens": out, "cache_read_input_tokens": 1000},
        "content": [{"type": "text", "text": "working"}]}}


def test_a_lane_without_a_result_event_is_priced_from_its_stream():
    m = _module()
    st = {}
    for ev in (_msg("a"), _msg("a"), _msg("b", out=50)):      # "a" twice: one message, two blocks
        m._summarise(ev, st)
    use = m._lane_usage(st)
    assert use["usd_basis"] == "stream" and use["usd"] and use["usd"] > 0
    assert use["tokens"]["output"] == 150 and use["turns"] == 2


def test_the_result_event_wins_when_it_came():
    m = _module()
    st = {}
    m._summarise(_msg("a"), st)
    m._summarise({"type": "result", "total_cost_usd": 0.42, "num_turns": 7}, st)
    use = m._lane_usage(st)
    assert use["usd"] == 0.42 and use["usd_basis"] == "result" and use["turns"] == 7


def test_each_lane_is_booked_as_it_finishes_and_the_batch_row_carries_no_money(
        monkeypatch, tmp_path):
    m = _module()
    lanes, batch = [], []

    def fake_dispatch(name, prompt, timeout, repo_root, allowed, lean=None):
        return {"agent": name, "code": 0, "stdout": "x" * 300, "stderr": "", "note": "",
                "turns": 3, "usd": 0.5, "tokens": {"output": 10}, "model": "sonnet",
                "usd_basis": "result"}
    monkeypatch.setattr(m, "dispatch", fake_dispatch)
    monkeypatch.setattr(m, "_record_lane_cost",
                        lambda record, res, root: lanes.append(res["usd"]) or {"recorded": True})
    monkeypatch.setattr(m, "_record_cost",
                        lambda record, summary, root: batch.append(summary) or {"recorded": True})
    rows = [{"agent": "scoring-p1-producer", "prompt": "go"},
            {"agent": "scoring-p2-producer", "prompt": "go"}]
    m.run_batch(rows, 2, 60, tmp_path, "Bash", None, record={"run": "r", "stage": "SCORING"})
    assert lanes == [0.5, 0.5], "every lane is booked the moment it finishes"
    assert batch and batch[0]["usd"] is None, "the batch row must not book the money twice"
