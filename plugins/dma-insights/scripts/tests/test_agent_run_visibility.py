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


# ── the usage the result event already carried ──────────────────────────
#
# Measured 2026-09-14: `_summarise` captured `total_cost_usd` and `num_turns`
# from the CLI's result event and dropped `usage`, so no ledger row ever
# carried a token field and `cost.as_baseline` refused every real run with
# "record stages with --turns and --tokens (agent_run.py --record-run does)"
# — which it did not. 76% of the measured bill is cache reads, and nothing
# downstream could see them.

USAGE = {"cache_read_input_tokens": 24_454_213,
         "cache_creation_input_tokens": 441_293,
         "input_tokens": 211_703, "output_tokens": 2_935}


def test_the_result_events_usage_reaches_the_status_file():
    st = _st()
    ar._summarise({"type": "result", "subtype": "success", "num_turns": 42,
                   "total_cost_usd": 1.23, "usage": USAGE,
                   "modelUsage": {"claude-sonnet-4-5": {"inputTokens": 10}},
                   "is_error": False}, st)
    assert st["tokens"] == {"cache_read": 24_454_213, "cache_write": 441_293,
                            "uncached": 211_703, "output": 2_935}
    assert st["model"] == "sonnet"


def test_a_result_event_without_usage_says_nothing_rather_than_zero():
    """A lane whose stream carried no usage must not report a free lane."""
    st = _st()
    ar._summarise({"type": "result", "subtype": "success", "num_turns": 42,
                   "is_error": False}, st)
    assert "tokens" not in st and "model" not in st


def test_the_model_is_read_from_the_dominant_model_usage():
    st = _st()
    ar._summarise({"type": "result", "usage": USAGE, "modelUsage": {
        "claude-haiku-4-5": {"inputTokens": 10},
        "claude-opus-4-6": {"inputTokens": 900}}}, st)
    assert st["model"] == "opus"


def test_the_cost_record_passes_the_tokens_it_has(monkeypatch, tmp_path):
    """The half that makes the ledger measurable: the batch summary's
    tokens reach `engine.cost record --tokens`."""
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        class R:
            returncode, stdout, stderr = 0, "ok", ""
        return R()

    monkeypatch.setattr(ar.subprocess, "run", fake_run)
    summary = {"elapsed_s": 1.0, "started_at": "2026-09-14T00:00:00Z",
               "ended_at": "2026-09-14T00:01:00Z", "lanes": 2, "ok": 2,
               "dispatched": 2, "lanes_detail": [{"attempts": 1}],
               "turns": 42, "usd": 1.23,
               "tokens": {"cache_read": 5, "cache_write": 1, "uncached": 2,
                          "output": 3},
               "model": "sonnet"}
    ar._record_cost({"run": "R-1", "stage": "CHALLENGE", "root": str(tmp_path)},
                    summary, tmp_path)
    cmd = seen["cmd"]
    assert "--tokens" in cmd and "--model" in cmd
    import json as _json
    assert _json.loads(cmd[cmd.index("--tokens") + 1])["cache_read"] == 5
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--stage") + 1] == "CHALLENGE"


def test_the_child_is_told_which_agent_it_is():
    """A headless lane cannot be identified from inside a hook, and until
    2026-09-14 nothing carried the name into the process either — so no
    write path and no guard could tell which lane was writing."""
    env = ar._child_env("research-p1c1-producer")
    assert env["DMA_ACTOR"] == "research-p1c1-producer"
    assert env["DMA_STAGE_GUARD"] == "off", "the stage guard is the conductor's"
