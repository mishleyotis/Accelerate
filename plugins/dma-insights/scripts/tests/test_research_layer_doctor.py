"""The doctor's research-layer rows: declared, reachable, and the brief's
WARNING-vs-BLOCKER rule for the engine."""
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import research_layer as rl  # noqa: E402


def _plugin(tmp_path, servers):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": servers}))
    return tmp_path


FULL = {
    "connector": {"command": "python3", "args": ["x/mcp_proxy.py", "u"]},
    "evidence": {"command": "python3", "args": ["x/evidence_proxy.py", "https://e.test", "--secret", "dmai-evidence-path-token"]},
    "searxng": {"command": "python3", "args": ["x/evidence_proxy.py", "", "--secret", "dmai-searxng-path-token", "--segment"]},
    "fetch": {"command": "python3", "args": ["x/evidence_proxy.py", "", "--secret", "dmai-fetch-path-token", "--segment"]},
    "edgar": {"command": "python3", "args": ["x/evidence_proxy.py", "", "--secret", "dmai-edgar-path-token", "--segment"]},
    "parallel": {"type": "http", "url": "https://search.parallel.ai/mcp"},
    "alphaxiv": {"type": "http", "url": "https://api.alphaxiv.org/mcp/v1"},
}


def test_the_real_mcp_json_declares_all_six():
    names = set(rl.declared())
    assert set(rl.RESEARCH_SERVERS) <= names and "connector" in names


def test_no_probe_only_reports_declarations(tmp_path):
    rows = rl.checks(probe_network=False, plugin_root=_plugin(tmp_path, FULL))
    assert len(rows) == 6 and all(r["ok"] for r in rows)
    assert all("SKIPPED" in r["detail"] for r in rows)


def test_a_missing_raw_fallback_is_a_warning_and_a_missing_engine_is_not(tmp_path):
    servers = {k: v for k, v in FULL.items() if k not in ("fetch", "evidence")}
    rows = {r["check"]: r for r in rl.checks(probe_network=False, plugin_root=_plugin(tmp_path, servers))}
    assert rows["research layer: fetch"]["ok"] and rows["research layer: fetch"]["warn"]
    assert not rows["research layer: evidence"]["ok"]


def test_engine_down_with_a_search_fallback_is_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(rl, "resolve_url", lambda s, spec: (f"https://{s}.test/mcp", {"X": "y"}))
    def prober(url, hdrs):
        if "evidence" in url:
            return None, "URLError: refused"
        if "alphaxiv" in url:
            return 401, "HTTP 401"
        return 200, "initialize OK"
    rows = {r["check"]: r for r in rl.checks(probe_network=True, plugin_root=_plugin(tmp_path, FULL), prober=prober)}
    e = rows["research layer: evidence"]
    assert e["ok"] and e["warn"] and "WARNING" in e["detail"] and "searxng" in e["detail"]
    assert rows["research layer: alphaxiv"]["ok"] and "OAuth" in rows["research layer: alphaxiv"]["detail"]
    assert "token value not shown" in rows["research layer: searxng"]["detail"]


def test_engine_down_with_no_fallback_is_a_blocker(tmp_path, monkeypatch):
    monkeypatch.setattr(rl, "resolve_url", lambda s, spec: (f"https://{s}.test/mcp", {}))
    rows = {r["check"]: r for r in rl.checks(probe_network=True, plugin_root=_plugin(tmp_path, FULL),
                                             prober=lambda u, h: (None, "down"), baseline_families=set())}
    e = rows["research layer: evidence"]
    assert not e["ok"] and "BLOCKER" in e["detail"]
    for s in ("searxng", "fetch", "edgar", "parallel"):
        assert rows[f"research layer: {s}"]["ok"] and rows[f"research layer: {s}"]["warn"]


def test_session_exa_counts_as_a_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(rl, "resolve_url", lambda s, spec: (f"https://{s}.test/mcp", {}))
    rows = {r["check"]: r for r in rl.checks(probe_network=True, plugin_root=_plugin(tmp_path, FULL),
                                             prober=lambda u, h: (None, "down"), baseline_families={"exa"})}
    assert rows["research layer: evidence"]["ok"] and rows["research layer: evidence"]["warn"]
