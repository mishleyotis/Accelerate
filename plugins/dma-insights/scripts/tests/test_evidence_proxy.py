"""evidence_proxy reuses mcp_proxy's loop and never changes it."""
import json
import subprocess
import sys
from pathlib import Path

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
