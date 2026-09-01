"""A dispatched agent must be watchable while it works, not after it exits.

OWNER, 2026-08-31: "I have no visibility onto how the agents are doing the
research or how they think through challenges. I cannot even see them on the
background task list."

Both halves have one cause. `dispatch` ran the child through
`subprocess.run(capture_output=True)`, which returns nothing until the
process exits — a forty-minute researcher was a black box for forty minutes.
And because the children are spawned INSIDE one Bash call, the harness sees a
single task, not sixteen agents, so there is nothing for a task list to show.
Neither is fixed by logging harder at the end.

These pin the streaming path: that a transcript exists WHILE the child runs,
that the status file says what the agent is doing now, and — the one that
matters most — that an event shape this parser does not recognise degrades
the summary and never the transcript. "The monitor showed nothing" is the
exact failure being fixed; it must never be caused BY the monitor.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import agent_run as ar  # noqa: E402


def _st():
    return {"agent": "x", "events": 0, "tools": 0}


def test_a_tool_call_is_visible_as_it_happens():
    st = _st()
    ar._summarise({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "mcp__Exa__web_search_exa"}]}}, st)
    assert st["tools"] == 1
    assert st["last_tool"] == "mcp__Exa__web_search_exa"
    assert "calling" in st["doing"]


def test_thinking_and_writing_are_distinguishable():
    """'How they think through challenges' was the actual ask."""
    st = _st()
    ar._summarise({"type": "assistant",
                   "message": {"content": [{"type": "thinking"}]}}, st)
    assert st["doing"] == "thinking"
    ar._summarise({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "P1C1 has three subcaps with no evidence"}]}},
        st)
    assert st["doing"] == "writing"
    assert "three subcaps" in st["last_text"]


def test_an_unrecognised_event_is_counted_and_never_crashes():
    """THE ONE THAT MATTERS. The event schema belongs to the CLI and can
    change; a parser that raises would take the transcript with it."""
    st = _st()
    for weird in ({"type": "something_new", "payload": {"a": 1}},
                  {"no_type_at_all": True},
                  {"type": "assistant"},                  # no message
                  {"type": "assistant", "message": {}},   # no content
                  {"type": "assistant", "message": {"content": None}}):
        ar._summarise(weird, st)
    assert st["events"] == 5, "every event counts, recognised or not"


def test_the_final_text_survives_every_shape():
    """`verdict_of` and every caller read this as the agent's answer.
    Returning '' on an unfamiliar shape would turn a working stage into a
    silent empty verdict."""
    result_ev = [{"type": "result", "subtype": "success",
                  "result": "FINAL REPORT: 16 categories closed"}]
    assert "FINAL REPORT" in ar._final_text(result_ev, "raw")

    blocks = [{"type": "assistant", "message": {"content": [
                 {"type": "text", "text": "part one"}]}},
              {"type": "assistant", "message": {"content": [
                 {"type": "text", "text": "part two"}]}}]
    assert ar._final_text(blocks, "raw") == "part one\npart two"

    # nothing recognisable at all -> the raw stream, never an empty string
    assert ar._final_text([{"type": "mystery"}], "raw bytes") == "raw bytes"
    assert ar._final_text([], "") == ""


def test_the_result_event_carries_cost_and_turns_when_present():
    st = _st()
    ar._summarise({"type": "result", "subtype": "success", "num_turns": 42,
                   "total_cost_usd": 1.23, "is_error": False}, st)
    assert st["doing"] == "done" and st["num_turns"] == 42
    assert st["total_cost_usd"] == 1.23


def test_logs_are_run_scoped_so_two_runs_cannot_overwrite(monkeypatch,
                                                          tmp_path):
    monkeypatch.setenv("DMA_RUN_ROOT", str(tmp_path / "run-a"))
    assert ar.log_dir_for() == tmp_path / "run-a" / "agent_logs"
    monkeypatch.delenv("DMA_RUN_ROOT")
    assert ar.log_dir_for() == Path("/root/.dma/agent_logs")
    assert ar.log_dir_for("/somewhere/else") == Path("/somewhere/else")


def test_watch_reports_an_empty_dir_rather_than_looking_healthy(tmp_path,
                                                                capsys):
    """Silence is what we are fixing. An empty watch must say so."""
    assert ar.watch(tmp_path, once=True) == 0
    out = capsys.readouterr().out
    assert "nothing yet" in out and "--stream" in out


def test_watch_renders_every_agent_with_what_it_is_doing(tmp_path, capsys):
    import time
    now = time.time()
    for name, doing, state in (("research-p1c1-producer", "calling Exa", "running"),
                               ("research-p2c3-producer", "thinking", "running"),
                               ("technographic-scanner", "done", "ok")):
        (tmp_path / f"{name}.status.json").write_text(json.dumps({
            "agent": name, "state": state, "doing": doing,
            "started_at": now - 120, "last_event_at": now - 5,
            "events": 30, "tools": 7}))
    ar.watch(tmp_path, once=True)
    out = capsys.readouterr().out
    for name in ("research-p1c1-producer", "research-p2c3-producer",
                 "technographic-scanner"):
        assert name in out
    assert "calling Exa" in out and "thinking" in out
    assert "3 agent(s)" in out


def test_a_corrupt_status_file_does_not_hide_the_others(tmp_path, capsys):
    (tmp_path / "good.status.json").write_text(json.dumps(
        {"agent": "good", "state": "running", "doing": "working"}))
    (tmp_path / "bad.status.json").write_text("{not json")
    ar.watch(tmp_path, once=True)
    assert "good" in capsys.readouterr().out


def test_streaming_is_opt_in_so_the_default_path_is_untouched():
    """A run was in flight in another session when this landed. The default
    dispatch had to stay byte-for-byte the behaviour it already had."""
    import inspect
    src = inspect.getsource(ar.dispatch)
    assert "subprocess.run" in src and "capture_output=True" in src
    assert "stream-json" not in src
