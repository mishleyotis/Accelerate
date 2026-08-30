"""The connector could not be added to claude.ai, and the reason was a header.

claude.ai does not use dynamic client registration to reach this connector.
It passes a URL as the `client_id` — a Client-ID Metadata Document — and the
authorization server is expected to fetch that URL and read the client's
registration out of it.

Measured 2026-08-21, from the owner's browser:

    /authorize?response_type=code&client_id=https%3A%2F%2Fclaude.ai%2Foauth
        %2Fmcp-oauth-client-metadata&...
    {"error": "invalid_client", "error_description": "unknown or tampered
     client_id"}

The client_id was entirely valid. `_client_id_metadata` fetched it with
`urllib`, which sends `Python-urllib/3.x` as its User-Agent, and claude.ai's
edge answers that with **HTTP 403 and Cloudflare error 1010** — the browser
integrity refusal. The fetch raised, the function returned None, and a
perfectly good client became "unknown or tampered".

Measured the same afternoon, same URL, same second:

    python default UA   403
    curl/8.5.0          200
    dma-insights-mcp/1.0 200

That is the whole defect. It also explains why it survived review: a `curl`
probe of the endpoint succeeds, so the server looks correct from every angle
except the one it actually runs from. Two earlier verification passes used
curl and concluded the flow was healthy.

These tests never touch the network — claude.ai's edge behaviour is not this
repo's to assert. They pin what the SERVER sends and how it behaves when the
fetch fails, which is what was wrong.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dma_mcp import oauth_as  # noqa: E402

CLAUDE_CIMD = "https://claude.ai/oauth/mcp-oauth-client-metadata"


@pytest.fixture(autouse=True)
def _clear_cache():
    oauth_as._CIMD_CACHE.clear()
    yield
    oauth_as._CIMD_CACHE.clear()


class _Resp:
    def __init__(self, body): self._b = json.dumps(body).encode()
    def read(self, n=None): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _capture(monkeypatch, body, boom=None):
    """Record the Request the server would send; answer with `body`."""
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        if boom:
            raise boom
        return _Resp(body)

    monkeypatch.setattr(oauth_as.urllib.request, "urlopen", fake_urlopen)
    return seen


GOOD = {"client_id": CLAUDE_CIMD,
        "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "client_name": "Claude", "token_endpoint_auth_method": "none"}


# ── the header that was missing ──


def test_the_fetch_sends_an_explicit_user_agent(monkeypatch):
    """THE REGRESSION. Without this header urllib sends Python-urllib/3.x,
    claude.ai returns 403/1010, and a valid client_id reads as tampered."""
    seen = _capture(monkeypatch, GOOD)
    assert oauth_as._client_id_metadata(CLAUDE_CIMD) is not None
    ua = seen["headers"].get("User-agent".lower()) or seen["headers"].get("user-agent")
    assert ua, "no User-Agent sent — this is the exact defect, restored"
    assert "python-urllib" not in ua.lower(), (
        f"the default urllib agent is refused by claude.ai's edge: {ua!r}")


def test_the_user_agent_identifies_this_service_rather_than_faking_a_browser():
    """The block is on the anonymous default, not on being a robot, so there
    is no reason to impersonate Chrome — and a UA that names us is what makes
    the traffic explicable to whoever reads the other end's logs."""
    src = (ROOT / "dma_mcp" / "oauth_as.py").read_text()
    assert "dma-insights-mcp/" in src
    for fake in ("Mozilla/5.0 (Windows", "Chrome/", "Safari/", "AppleWebKit"):
        assert fake not in src, f"do not impersonate a browser: {fake}"


def test_the_accept_header_is_still_sent(monkeypatch):
    seen = _capture(monkeypatch, GOOD)
    oauth_as._client_id_metadata(CLAUDE_CIMD)
    assert "application/json" in seen["headers"].get("accept", "")


# ── the happy path still works ──


def test_a_self_identifying_document_is_accepted(monkeypatch):
    _capture(monkeypatch, GOOD)
    claims = oauth_as._client_id_metadata(CLAUDE_CIMD)
    assert claims["ru"] == ["https://claude.ai/api/mcp/auth_callback"]
    assert claims["n"] == "Claude"
    assert claims["cimd"] is True


def test_client_claims_routes_a_url_client_id_to_cimd(monkeypatch):
    """The entry point the /authorize handler actually calls."""
    _capture(monkeypatch, GOOD)
    assert oauth_as.client_claims(CLAUDE_CIMD) is not None


def test_the_document_is_cached_rather_than_refetched(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        return _Resp(GOOD)

    monkeypatch.setattr(oauth_as.urllib.request, "urlopen", fake_urlopen)
    oauth_as._client_id_metadata(CLAUDE_CIMD)
    oauth_as._client_id_metadata(CLAUDE_CIMD)
    assert len(calls) == 1


# ── the safety properties the fix must not have loosened ──


def test_a_document_that_does_not_self_identify_is_refused(monkeypatch):
    """A URL may not assert somebody else's identity."""
    _capture(monkeypatch, {**GOOD, "client_id": "https://evil.example/other"})
    assert oauth_as._client_id_metadata(CLAUDE_CIMD) is None


def test_a_document_with_no_redirect_uris_is_refused(monkeypatch):
    _capture(monkeypatch, {"client_id": CLAUDE_CIMD, "redirect_uris": []})
    assert oauth_as._client_id_metadata(CLAUDE_CIMD) is None


def test_plain_http_is_never_fetched(monkeypatch):
    called = []
    monkeypatch.setattr(oauth_as.urllib.request, "urlopen",
                        lambda *a, **k: called.append(1))
    assert oauth_as._client_id_metadata("http://claude.ai/oauth/x") is None
    assert not called, "an http:// client_id must not be fetched at all"


def test_a_non_url_non_dmai_client_id_is_still_unknown():
    assert oauth_as.client_claims("whatever") is None


# ── the failure is diagnosable now ──


def test_a_failed_fetch_says_why_on_stderr(monkeypatch, capsys):
    """Returning None renders as an opaque `invalid_client`, which is
    indistinguishable from a genuinely bad id — telling the 403 from a
    tampered client_id took a packet-level comparison. One log line makes the
    next one a lookup."""
    _capture(monkeypatch, GOOD, boom=OSError("HTTP Error 403: Forbidden"))
    assert oauth_as._client_id_metadata(CLAUDE_CIMD) is None
    err = capsys.readouterr().err
    assert "CIMD fetch failed" in err
    assert CLAUDE_CIMD in err
    assert "403" in err


def test_a_non_self_identifying_document_also_says_why(monkeypatch, capsys):
    _capture(monkeypatch, {**GOOD, "client_id": "https://evil.example/other"})
    assert oauth_as._client_id_metadata(CLAUDE_CIMD) is None
    assert "does not self-identify" in capsys.readouterr().err
