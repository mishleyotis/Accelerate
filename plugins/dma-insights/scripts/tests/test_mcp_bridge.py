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


# ---------------------------------------------------------------------------
# revive — the verdict a continued session runs when its binding is gone.
#
# Reported by the owner 2026-08-24: a session continued after its token
# budget reset found the connector tools "not present … lost mid-session …
# cannot be recovered" and produced nothing, while the server held every
# claim the whole time. Two lane claims that day (12:15Z, 12:18Z holders)
# died at 0/6 pages staged. revive is the one command that state runs: it
# measures identity, server and run state, and its OK text carries the
# standing authorization to finish the run through the bridge instead of
# declaring the tools lost.
# ---------------------------------------------------------------------------

import mcp_raw  # noqa: E402


def _tool_reply(payload: dict) -> dict:
    return {"result": {"content": [{"type": "text",
                                    "text": json.dumps(payload)}]}}


def test_revive_names_the_missing_identity_and_its_fix(monkeypatch, capsys):
    monkeypatch.setattr(mcp_raw.gcp_token, "load_key",
                        lambda path: (None, "no key at /root/.dma/sa.json"))
    rc = mcp_raw.revive(None)
    out = capsys.readouterr().out
    assert rc == 1
    assert "IDENTITY_MISSING" in out
    assert "DMA_ROUTINE_SA_KEY_B64" in out and "bootstrap_session.sh" in out


def test_revive_reports_a_down_server_with_its_error(monkeypatch, capsys):
    monkeypatch.setattr(mcp_raw.gcp_token, "load_key",
                        lambda path: ({"k": 1}, "sa.json"))

    def dead_rpc(method, params=None):
        raise urllib.error.HTTPError("https://x/mcp", 503, "unavailable",
                                     {}, io.BytesIO(b""))
    monkeypatch.setattr(mcp_raw, "rpc", dead_rpc)
    rc = mcp_raw.revive(None)
    out = capsys.readouterr().out
    assert rc == 1
    assert "SERVER_DOWN" in out and "503" in out


def test_revive_ok_reports_banked_state_and_the_authorization(monkeypatch,
                                                             capsys):
    monkeypatch.setattr(mcp_raw.gcp_token, "load_key",
                        lambda path: ({"k": 1}, "sa.json"))
    progress = {"pages": {"overview": {"status": "pass"},
                          "heatmap": {"status": "missing"},
                          "insights": {"status": "missing"},
                          "platform": {"status": "missing"},
                          "context": {"status": "missing"},
                          "techstack": {"status": "missing"}},
                "promotable": False,
                "claim": {"held_by": "lane-b-x", "live": False,
                          "expires_at": "2026-08-24T13:50:07+00:00"}}

    def fake_rpc(method, params=None):
        if method == "tools/list":
            return {"result": {"tools": [{"name": f"t{i}"}
                                         for i in range(33)]}}
        assert params["name"] == "get_run_progress"
        return _tool_reply(progress)
    monkeypatch.setattr(mcp_raw, "rpc", fake_rpc)
    rc = mcp_raw.revive("run-1")
    out = capsys.readouterr().out
    assert rc == 0
    assert "REVIVE: OK" in out and "33 tools" in out
    assert "1/6 pages present (overview)" in out, (
        "the banked-versus-missing split is the whole point — a resumed "
        "session must see what is already staged before producing")
    assert "held_by=lane-b-x" in out
    assert "standing owner authorization (2026-08-24)" in out
    assert "UNPROMOTED" in out or "nothing server-side was lost" in out.lower()


def test_the_ladder_prescribes_revive_not_abandonment():
    """The old step 2 said 'writes only with the owner's explicit
    re-affirmation' and sessions obeyed it into abandoning unpromoted
    claims. The owner gave that affirmation as standing on 2026-08-24; the
    ladder must carry it, and must not carry a version literal (the '0.6.7
    stdio transport' the old text named)."""
    src = (HERE / "mcp_raw.py").read_text()
    assert "STANDING AUTHORIZATION" in src and "2026-08-24" in src
    assert "revive" in src
    assert "do not abandon the\n     claim" in src or \
        "do not abandon the claim" in src
    import re as _re
    assert not _re.search(r"\b\d+\.\d+\.\d+\b", src), (
        "no version literal in the bridge's prose — plugin_version.py is "
        "how versions are checked")
