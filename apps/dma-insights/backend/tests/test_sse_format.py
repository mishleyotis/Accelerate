"""Tests for the SSE event formatter."""
from __future__ import annotations

from app.routers.sse import _format_event


def test_string_payload() -> None:
    out = _format_event("message", "hello").decode()
    assert out == "event: message\ndata: hello\n\n"


def test_dict_payload_serialized_to_json() -> None:
    out = _format_event("token", {"kind": "token", "text": "Hi"}).decode()
    # ordering preserved because dict insertion order = json output order
    assert out.startswith("event: token\n")
    assert '"kind": "token"' in out
    assert '"text": "Hi"' in out
    assert out.endswith("\n\n")


def test_handles_non_serializable_via_default() -> None:
    from datetime import datetime
    out = _format_event(
        "done",
        {"at": datetime(2026, 5, 20, 15, 0, 0)},
    ).decode()
    assert "2026-05-20" in out
