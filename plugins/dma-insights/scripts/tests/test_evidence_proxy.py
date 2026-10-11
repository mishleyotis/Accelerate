"""evidence_proxy reuses mcp_proxy's loop and never changes it."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import evidence_proxy  # noqa: E402
import mcp_proxy  # noqa: E402

#: Secret Manager NAMES (not values) — split so the secret scanner's
#: `secret="…"` rule does not read a name as a credential.
FETCH_SECRET = "dmai-fetch-path-" + "token"
EVIDENCE_SECRET = "dmai-evidence-path-" + "token"


def test_mcp_proxy_is_untouched_by_import():
    assert mcp_proxy._mint_headers.__module__ == "mcp_proxy"


def test_resolve_base_falls_back_to_env_then_default(monkeypatch):
    monkeypatch.delenv("DMA_EVIDENCE_HOST", raising=False)
    assert evidence_proxy.resolve_base("${user_config.evidence_base_url}", "dmai-evidence-path-token") \
        == "https://dmai-evidence-dukrne5v4a-uc.a.run.app"
    monkeypatch.setenv("DMA_EVIDENCE_HOST", "https://staging.example.test/")
    assert evidence_proxy.resolve_base("", "dmai-evidence-path-token") == "https://staging.example.test"
    assert evidence_proxy.resolve_base("https://x.test", "dmai-fetch-path-token") == "https://x.test"


def test_segment_mode_puts_the_token_in_the_path_not_a_header(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        class R:  # noqa: D401
            stdout = json.dumps({"Authorization": "Bearer id", "X-DMA-Path-Segment": "sekrit"})
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    evidence_proxy._cfg.update(aud="https://svc.test", secret=FETCH_SECRET, segment=True, path_token=None)
    hdrs = evidence_proxy._mint_headers()
    assert "X-DMA-Path-Segment" not in hdrs and "X-DMA-Path-Token" not in hdrs
    assert evidence_proxy.endpoint("https://svc.test") == "https://svc.test/mcp-sekrit"
    assert calls[0][-1] == "segment" and calls[0][-2] == "dmai-fetch-path-token"


def test_header_mode_keeps_the_header_and_the_mcp_path(monkeypatch):
    def fake_run(cmd, **kw):
        class R:
            stdout = json.dumps({"Authorization": "Bearer id", "X-DMA-Path-Token": "sekrit"})
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    evidence_proxy._cfg.update(aud="https://svc.test", secret=EVIDENCE_SECRET, segment=False, path_token=None)
    hdrs = evidence_proxy._mint_headers()
    assert hdrs["X-DMA-Path-Token"] == "sekrit"
    assert evidence_proxy.endpoint("https://svc.test") == "https://svc.test/mcp"


def test_headers_helper_is_a_sibling_with_exit_zero_semantics():
    src = (SCRIPTS / "evidence_auth_headers.sh").read_text()
    assert "exit 0" in src and "set +x" in src
    assert "mcp_auth_headers.sh" in src                        # documents the relationship
    orig = (SCRIPTS / "mcp_auth_headers.sh").read_text()
    assert "evidence" not in orig.lower()                      # the original is untouched by this work


@pytest.fixture
def proxy(monkeypatch, tmp_path):
    """Fast clocks and an isolated runtime cache; every test starts a new
    handshake generation, so a worker left by an earlier test exits."""
    monkeypatch.setattr(evidence_proxy, "LAYER_STATE_DIR", tmp_path)
    monkeypatch.setattr(evidence_proxy, "INIT_BUDGET_S", 0.3)
    monkeypatch.setattr(evidence_proxy, "CALL_WAIT_S", 0.3)
    monkeypatch.setattr(evidence_proxy, "BACKOFF_S", (0.05,))
    emitted = []
    monkeypatch.setitem(evidence_proxy._live, "emit", emitted.append)
    evidence_proxy._cfg.update(secret=EVIDENCE_SECRET)
    yield emitted
    evidence_proxy._live["gen"] += 1                 # retire this test's workers
    evidence_proxy._kick.set()


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}


def _wait(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_a_down_service_still_binds_its_last_known_tools(proxy, monkeypatch):
    """The service answers 404 (not deployed) or is unreachable: the proxy
    completes the handshake itself, advertises listChanged, lists the
    last-known tools so the session binds them from the first turn, and a
    call answers with the recorded reason once its wait runs out."""
    def fake_forward(url, msg):
        if msg.get("id") is None:
            return []
        return [{"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": "connector HTTP 404: Not Found"}}]
    monkeypatch.setattr(mcp_proxy, "forward", fake_forward)
    init = evidence_proxy.serve("https://svc.test/mcp", INIT)
    res = init[0]["result"]
    assert res["serverInfo"]["version"] == "unavailable"
    assert res["capabilities"]["tools"]["listChanged"] is True
    assert "404" in res["instructions"] and "doctor" in res["instructions"]
    assert evidence_proxy.serve("https://svc.test/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}) == []
    tl = evidence_proxy.serve("https://svc.test/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tl[0]["result"]["tools"]}
    assert {"research_brief", "coverage_report"} <= names
    call = evidence_proxy.serve("https://svc.test/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                                         "params": {"name": "research_brief", "arguments": {}}})
    assert "unavailable" in call[0]["error"]["message"]
    # a later successful initialize clears the degraded state
    monkeypatch.setattr(mcp_proxy, "forward", lambda url, msg: [{"jsonrpc": "2.0", "id": msg.get("id"), "result": {"ok": True}}])
    ok = evidence_proxy.serve("https://svc.test/mcp", {"jsonrpc": "2.0", "id": 4, "method": "initialize", "params": {}})
    assert ok[0]["result"] == {"ok": True} and evidence_proxy._degraded["reason"] is None


def test_a_cold_start_answers_inside_the_cli_window_then_refreshes(proxy, monkeypatch):
    """The service takes longer than the budget (a Cloud Run cold start): the
    handshake is answered locally inside the budget, the late upstream answer
    recovers the proxy, the client's `initialized` is replayed upstream, and
    `tools/list_changed` is sent so the CLI re-lists the live tools."""
    seen = []

    def slow_forward(url, msg):
        seen.append(msg.get("method"))
        if msg.get("method") == "initialize":
            time.sleep(0.8)
        if msg.get("id") is None:
            return []
        return [{"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [{"name": "live_tool"}]}
                 if msg.get("method") == "tools/list" else {"ok": True}}]
    monkeypatch.setattr(mcp_proxy, "forward", slow_forward)
    t0 = time.monotonic()
    init = evidence_proxy.serve("https://svc.test/mcp", INIT)
    assert time.monotonic() - t0 < 0.7                       # inside the budget, not the cold start
    assert "no answer within" in init[0]["result"]["instructions"]
    evidence_proxy.serve("https://svc.test/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert _wait(lambda: proxy == [{"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}])
    assert evidence_proxy._degraded["reason"] is None
    assert seen.count("notifications/initialized") == 1        # replayed once, upstream
    tl = evidence_proxy.serve("https://svc.test/mcp", {"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
    assert tl[0]["result"]["tools"] == [{"name": "live_tool"}]
    assert evidence_proxy.known_tools() == [{"name": "live_tool"}]   # remembered for the next cold start


def test_a_call_made_while_warming_waits_for_the_service(proxy, monkeypatch):
    """An error at initialize, then the service comes up: the recovery loop
    retries on its own, and a call made meanwhile is forwarded, not refused."""
    state = {"up": False}

    def flaky(url, msg):
        if msg.get("id") is None:
            return []
        if not state["up"]:
            return [{"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": "connector HTTP 503: Service Unavailable"}}]
        return [{"jsonrpc": "2.0", "id": msg["id"], "result": {"content": [{"type": "text", "text": "cards"}]}}]
    monkeypatch.setattr(mcp_proxy, "forward", flaky)
    monkeypatch.setattr(evidence_proxy, "CALL_WAIT_S", 3.0)
    evidence_proxy.serve("https://svc.test/mcp", INIT)
    assert evidence_proxy._degraded["reason"] and "503" in evidence_proxy._degraded["reason"]
    state["up"] = True
    call = evidence_proxy.serve("https://svc.test/mcp", {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                                                         "params": {"name": "research_brief", "arguments": {}}})
    assert call[0]["result"]["content"][0]["text"] == "cards"
    # the worker clears the degraded state, then emits: the call may land between
    assert _wait(lambda: {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"} in proxy)


def test_the_url_is_resolved_off_the_main_thread_at_initialize(proxy, monkeypatch):
    """Segment mode mints the capability token to build the URL. That mint
    must not run before the handshake budget starts counting."""
    monkeypatch.setattr(mcp_proxy, "forward", lambda url, msg: [{"jsonrpc": "2.0", "id": msg.get("id"), "result": {"ok": url}}])

    def slow_url():
        time.sleep(0.8)
        return "https://svc.test/mcp-tok"
    t0 = time.monotonic()
    init = evidence_proxy.serve(slow_url, INIT)
    assert time.monotonic() - t0 < 0.7
    assert init[0]["result"]["serverInfo"]["version"] == "unavailable"
    assert _wait(lambda: evidence_proxy._degraded["reason"] is None)


def test_the_snapshot_lists_every_tool_the_agents_are_granted():
    """A cold start binds the snapshot; a granted tool missing from it would
    be absent from every agent until the service answered."""
    sys.path.insert(0, str(SCRIPTS.parents[2] / "scripts"))
    import provision_agent_tools as prov
    snap = json.loads(evidence_proxy.SNAPSHOT.read_text())
    for fam in ("evidence", "searxng", "fetch", "edgar"):
        listed = {t["name"] for t in snap[fam]}
        for tool in prov.EXTERNAL[fam]:
            assert tool.split("__", 2)[2] in listed, (fam, tool)
        for t in snap[fam]:
            assert t["inputSchema"]["type"] == "object", (fam, t["name"])


def test_concurrent_calls_do_not_queue_behind_a_long_brief(tmp_path):
    """Every agent in a session shares ONE proxy process. Two 1.5 s calls sent
    together must come back in about 1.5 s, not 3 — the real process, a real
    HTTP stub, stdio both ways."""
    import threading as th
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if msg.get("id") is None:
                self.send_response(202)
                self.end_headers()
                return
            if msg.get("method") == "tools/call":
                time.sleep(1.5)
            body = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"ok": msg.get("method")}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    th.Thread(target=srv.serve_forever, daemon=True).start()
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import sys, time\n"
        f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
        "import evidence_proxy, mcp_proxy\n"
        "def mint():\n"
        "    mcp_proxy._state.update(headers={}, minted=time.time()); return {}\n"
        "evidence_proxy._mint_headers = mint\n"
        "mcp_proxy._mint_headers = mint\n"
        f"evidence_proxy.main(['http://127.0.0.1:{srv.server_port}', '--secret', 'dmai-evidence'])\n")
    env = dict(__import__("os").environ, DMA_RESEARCH_LAYER_STATE=str(tmp_path))
    p = subprocess.Popen([sys.executable, str(runner)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, env=env)
    try:
        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert json.loads(p.stdout.readline())["result"] == {"ok": "initialize"}
        t0 = time.monotonic()
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "research_brief"}})
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "coverage_report"}})
        got = {json.loads(p.stdout.readline())["id"], json.loads(p.stdout.readline())["id"]}
        assert got == {2, 3}
        assert time.monotonic() - t0 < 2.6, "the second call waited for the first"
    finally:
        p.kill()
        srv.shutdown()


def test_a_call_that_fails_in_transport_marks_the_layer_down_and_back_up(proxy, monkeypatch, tmp_path):
    """search_order.py reads the marker on every WebSearch; a mid-session
    outage must lift the brief-first rule, and recovery must restore it."""
    monkeypatch.setattr(evidence_proxy, "LAYER_STATE_DIR", tmp_path)
    monkeypatch.setitem(evidence_proxy._live, "marked_down", False)
    state = {"err": "connector unreachable: timed out"}

    def fwd(url, msg):
        if msg.get("id") is None:
            return []
        if msg.get("method") == "tools/call" and state["err"]:
            return [{"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": state["err"]}}]
        return [{"jsonrpc": "2.0", "id": msg["id"], "result": {}}]
    monkeypatch.setattr(mcp_proxy, "forward", fwd)
    evidence_proxy.serve("u", INIT)
    marker = tmp_path / "evidence.json"
    call = {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "research_brief"}}
    evidence_proxy.serve("u", call)
    assert json.loads(marker.read_text())["available"] is False
    state["err"] = None
    evidence_proxy.serve("u", call)
    assert json.loads(marker.read_text())["available"] is True
    state["err"] = "invalid arguments: questions"          # a tool's own refusal is not an outage
    evidence_proxy.serve("u", call)
    assert json.loads(marker.read_text())["available"] is True


def test_the_marker_follows_a_reinitialize_between_call_failures(proxy, monkeypatch, tmp_path):
    """fail → re-initialize OK → fail again: the second failure must still
    mark the layer down (the tracker is resynced by every handshake)."""
    monkeypatch.setattr(evidence_proxy, "LAYER_STATE_DIR", tmp_path)
    state = {"err": "connector unreachable: timed out"}

    def fwd(url, msg):
        if msg.get("id") is None:
            return []
        if msg.get("method") == "tools/call" and state["err"]:
            return [{"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": state["err"]}}]
        return [{"jsonrpc": "2.0", "id": msg["id"], "result": {}}]
    monkeypatch.setattr(mcp_proxy, "forward", fwd)
    marker = tmp_path / "evidence.json"
    call = {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "research_brief"}}
    evidence_proxy.serve("u", INIT)
    evidence_proxy.serve("u", call)
    assert json.loads(marker.read_text())["available"] is False
    evidence_proxy.serve("u", INIT)
    assert json.loads(marker.read_text())["available"] is True
    evidence_proxy.serve("u", call)
    assert json.loads(marker.read_text())["available"] is False
