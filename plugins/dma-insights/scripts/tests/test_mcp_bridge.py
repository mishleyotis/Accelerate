"""The connector self-heal bridge: fresh tokens per call, no OAuth fallback.

Measured 2026-08-20 (TRP production, 12:22Z): the CLI's HTTP MCP client
lost auth mid-session and fell back to Dynamic Client Registration, which
the connector rejects — every tool call 401ed while the server was healthy.
The stdio proxy prevents the class; mcp_raw is the in-session recovery.
The live halves are proven by `mcp_raw.py probe` (33 tools) and a full
initialize+tools/list handshake through the proxy; what pins here is the
offline logic.
"""
import io
import json
import sys
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import mcp_proxy  # noqa: E402


class _Resp:
    def __init__(self, payload, ctype="application/json", status=200,
                 session=None):
        self._raw = payload.encode()
        self.status = status
        self.headers = {"Content-Type": ctype}
        if session:
            self.headers["Mcp-Session-Id"] = session

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_parse_payload_handles_sse_and_raw(monkeypatch):
    sse = _Resp('event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n',
                ctype="text/event-stream", session="s1")
    out = mcp_proxy._parse_payload(sse)
    assert out and out[0]["id"] == 1
    assert mcp_proxy._state["session_id"] == "s1"
    raw = _Resp('{"jsonrpc":"2.0","id":2,"result":{"ok":true}}')
    assert mcp_proxy._parse_payload(raw)[0]["id"] == 2


def test_forward_reminets_on_401_then_succeeds(monkeypatch):
    calls = {"n": 0, "mints": 0}

    def fake_post(url, body, headers):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(url, 401, "unauthorized", {},
                                         io.BytesIO(b""))
        return _Resp('{"jsonrpc":"2.0","id":7,"result":{}}')

    monkeypatch.setattr(mcp_proxy, "_post", fake_post)
    monkeypatch.setattr(mcp_proxy, "_mint_headers",
                        lambda: calls.__setitem__("mints",
                                                  calls["mints"] + 1) or {})
    mcp_proxy._state.update({"headers": {}, "minted": 9e12,
                             "session_id": None, "init_params": None})
    out = mcp_proxy.forward("https://x/mcp", {"jsonrpc": "2.0", "id": 7,
                                              "method": "tools/list"})
    assert out and out[0]["id"] == 7
    assert calls["mints"] >= 1 and calls["n"] == 2


def test_notifications_swallow_errors_without_fake_replies(monkeypatch):
    def dead_post(url, body, headers):
        raise urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b""))
    monkeypatch.setattr(mcp_proxy, "_post", dead_post)
    mcp_proxy._state.update({"headers": {}, "minted": 9e12,
                             "session_id": None, "init_params": None})
    out = mcp_proxy.forward("https://x/mcp",
                            {"jsonrpc": "2.0",
                             "method": "notifications/initialized"})
    assert out == []


def test_the_self_heal_ladder_is_documented_in_mcp_raw():
    src = (HERE / "mcp_raw.py").read_text()
    for step in ("SELF-HEAL LADDER", "probe", "bootstrap_session.sh",
                 "never fabricate"):
        assert step in src, step
