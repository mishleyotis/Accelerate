"""The connector's queue is in the brief at session start (F-O04-007).

Measured 28-09-2026: 200 open rejections and nothing in the plugin read
`list_open_rejections` at session start — the instruction was prose. The
hook now reads it once, with a short timeout, and the brief states the
answer; with no identity it says nothing, and a failed read says so.
"""
import importlib.util
import json
import os
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
_spec = importlib.util.spec_from_file_location("session_brief", HOOKS / "session_brief.py")
sb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sb)


def _reply(doc):
    return {"result": {"content": [{"type": "text", "text": json.dumps(doc)}]}}


def test_the_queue_is_stated_worst_first(monkeypatch):
    monkeypatch.delenv(sb.NO_CONNECTOR_ENV, raising=False)
    calls = []

    def rpc(method, params=None, *, timeout=None):
        calls.append((method, params, timeout))
        return _reply({"open": 2, "looping": 1, "pages": ["heatmap", "insights"],
                       "rejections": [
                           {"display_id": "swbc", "page": "insights", "gate_id": "ET-04",
                            "attempts": 5, "run_seq": 3},
                           {"display_id": "goeasy-ltd", "page": "heatmap", "gate_id": "CG-15",
                            "attempts": 2, "run_seq": 18}]})
    text = sb.connector_outstanding(rpc=rpc, has_identity=True)
    assert calls[0][0] == "tools/call" and calls[0][1]["name"] == "list_open_rejections"
    assert calls[0][2] == 8.0, "a short timeout: a hook must not hang a session"
    assert "CONNECTOR QUEUE (read this first): 2 open" in text
    assert "swbc insights ET-04 x5 (run seq 3)" in text
    assert "CHANGE APPROACH" in text and "list_submissions" in text


def test_no_identity_says_nothing_and_a_failed_read_says_so():
    assert sb.connector_outstanding(rpc=lambda *a, **k: 1 / 0, has_identity=False) == ""

    def boom(*a, **k):
        raise TimeoutError("slow")
    text = sb.connector_outstanding(rpc=boom, has_identity=True)
    assert "CONNECTOR QUEUE NOT READ (TimeoutError)" in text
    assert "list_open_rejections" in text and "not an empty one" in text


def test_an_empty_queue_is_stated_as_zero(monkeypatch):
    monkeypatch.delenv(sb.NO_CONNECTOR_ENV, raising=False)
    text = sb.connector_outstanding(rpc=lambda *a, **k: _reply({"rejections": []}),
                                    has_identity=True)
    assert text == " CONNECTOR QUEUE: 0 open rejections."


def test_the_kill_switch_and_the_hook_wiring(monkeypatch):
    monkeypatch.setenv(sb.NO_CONNECTOR_ENV, "1")
    assert sb.connector_outstanding(rpc=lambda *a, **k: 1 / 0, has_identity=True) == ""
    src = (HOOKS / "session_brief.py").read_text()
    assert "text += connector_outstanding()" in src
    assert 'hook_name in ("", "SessionStart", "PostCompact")' in src
