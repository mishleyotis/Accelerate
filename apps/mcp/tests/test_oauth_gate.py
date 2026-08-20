"""The in-app identity gate: policy matrix, discovery, and the ASGI seam.

The 2026-08-16 lockdown's lesson was that identity must be READ, not merely
sent. These tests pin the reading: who passes each rung, what a refusal says,
that discovery is public, that the 401 challenge carries the metadata pointer
claude.ai's dialog needs, and that an authenticated caller reaches the
capability path without ever knowing the token.
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dma_mcp"))
from dma_mcp import oauth_gate  # noqa: E402
from dma_mcp.oauth_gate import OAuthGate, check_identity  # noqa: E402

HOST = "dmai-mcp-test.run.app"
SA = "dmai-routine@digital-maturity-assessor.iam.gserviceaccount.com"
CLIENT_ID = "1234567890-example.apps.googleusercontent.com"


def _a(email, aud, verified=True):
    return check_identity({"email": email, "aud": aud,
                           "email_verified": verified},
                          "A", host=HOST, oauth_client_id=CLIENT_ID)


def _b(email, aud, verified="true", client_id=CLIENT_ID):
    return check_identity({"email": email, "aud": aud,
                           "email_verified": verified},
                          "B", host=HOST, oauth_client_id=client_id)


# ── rung A: Google-signed ID tokens ─────────────────────────────────────

def test_routine_sa_with_service_audience_passes():
    ok, status, reason = _a(SA, f"https://{HOST}")
    assert ok and "service-account" in reason


def test_sa_with_foreign_audience_is_refused():
    ok, status, _ = _a(SA, "https://some-other-service.run.app")
    assert not ok and status == 403


def test_zennify_human_with_service_audience_passes():
    ok, _, reason = _a("person@zennify.com", f"https://{HOST}")
    assert ok and "domain user" in reason


def test_zennify_human_with_bare_gcloud_token_passes():
    ok, _, _ = _a("person@zennify.com", oauth_gate.GCLOUD_CLI_AUD)
    assert ok


def test_unverified_zennify_email_is_refused():
    ok, status, _ = _a("person@zennify.com", f"https://{HOST}",
                       verified=False)
    assert not ok and status == 403


def test_outside_domain_is_refused_naming_the_policy():
    ok, status, reason = _a("visitor@gmail.com", f"https://{HOST}")
    assert not ok and status == 403 and "zennify.com" in reason


# ── rung B: OAuth access tokens from the DMA Insights client ────────────

def test_oauth_zennify_user_through_our_client_passes():
    ok, _, reason = _b("person@zennify.com", CLIENT_ID)
    assert ok and "oauth user" in reason


def test_oauth_token_from_a_foreign_client_is_refused():
    """The anti-passthrough property: audience must be OUR client."""
    ok, status, reason = _b("person@zennify.com", "other-app-client-id")
    assert not ok and status == 403 and "OAuth client" in reason


def test_oauth_outside_domain_is_refused():
    ok, status, _ = _b("visitor@gmail.com", CLIENT_ID)
    assert not ok and status == 403


def test_unconfigured_client_id_names_the_missing_wiring():
    ok, status, reason = _b("person@zennify.com", CLIENT_ID, client_id="")
    assert not ok and status == 401 and "dmai-oauth-client-id" in reason


# ── the ASGI seam ───────────────────────────────────────────────────────

class _Inner:
    def __init__(self):
        self.seen = []

    async def __call__(self, scope, receive, send):
        self.seen.append(scope.get("path"))
        await send({"type": "http.response.start", "status": 200,
                    "headers": []})
        await send({"type": "http.response.body", "body": b"inner"})


def _run(gate, path, headers=()):
    sent = []

    async def send(msg):
        sent.append(msg)

    async def receive():
        return {"type": "http.request", "body": b""}

    scope = {"type": "http", "path": path, "method": "POST",
             "headers": [(b"host", HOST.encode())] + list(headers)}
    asyncio.run(gate(scope, receive, send))
    status = next(m["status"] for m in sent
                  if m["type"] == "http.response.start")
    hdrs = {k.decode(): v.decode() for k, v in next(
        m["headers"] for m in sent if m["type"] == "http.response.start")}
    body = b"".join(m.get("body", b"") for m in sent
                    if m["type"] == "http.response.body")
    return status, hdrs, body


def _gate(inner=None, jwt_claims=None, token_claims=None):
    calls = {"jwt": 0, "lookup": 0}

    def verify_jwt(tok, audiences):
        calls["jwt"] += 1
        assert isinstance(audiences, list) and audiences, (
            "the gate must hand the verifier its accepted-audience list — "
            "audience=None is not reliably skipped by google-auth")
        if jwt_claims is None:
            raise ValueError("bad signature")
        return jwt_claims

    def lookup(tok):
        calls["lookup"] += 1
        if token_claims is None:
            raise ValueError("google refused")
        return token_claims

    g = OAuthGate(inner or _Inner(), "captok", verify_jwt=verify_jwt,
                  lookup_access_token=lookup)
    return g, calls


def test_discovery_is_public_and_names_OUR_authorization_server(monkeypatch):
    """Changed deliberately on 2026-08-20 and measured, not assumed: Google
    publishes no registration endpoint and issues no refresh token to a
    standard OAuth client, so naming accounts.google.com here made the
    connector unregisterable and its connection expire hourly. The
    authorization server is now this service (dma_mcp/oauth_as.py)."""
    monkeypatch.setenv("MCP_SERVICE_URL", f"https://{HOST}")
    g, _ = _gate()
    status, _, body = _run(g, "/.well-known/oauth-protected-resource")
    assert status == 200
    doc = json.loads(body)
    assert doc["authorization_servers"] == [f"https://{HOST}"]
    assert doc["resource_name"] == "DMA Insights"
    assert doc["resource"] == f"https://{HOST}/mcp"


def test_unauthenticated_mcp_gets_401_with_the_metadata_challenge():
    g, _ = _gate()
    status, hdrs, _ = _run(g, "/mcp")
    assert status == 401
    assert "resource_metadata" in hdrs.get("www-authenticate", "")
    assert "/.well-known/oauth-protected-resource" in hdrs["www-authenticate"]


def test_oauth_caller_reaches_the_capability_path_without_the_token(monkeypatch):
    monkeypatch.setenv("OAUTH_CLIENT_ID", CLIENT_ID)
    inner = _Inner()
    g, _ = _gate(inner, token_claims={
        "email": "person@zennify.com", "email_verified": "true",
        "aud": CLIENT_ID})
    status, _, _ = _run(g, "/mcp",
                        headers=[(b"authorization", b"Bearer ya29.opaque")])
    assert status == 200
    assert inner.seen == ["/mcp/captok"]


def test_header_token_path_is_left_for_the_header_wrapper(monkeypatch):
    monkeypatch.setenv("OAUTH_CLIENT_ID", CLIENT_ID)
    inner = _Inner()
    g, _ = _gate(inner, jwt_claims={
        "email": SA, "aud": f"https://{HOST}", "email_verified": True})
    status, _, _ = _run(
        g, "/mcp",
        headers=[(b"authorization", b"Bearer a.b.c"),
                 (b"x-dma-path-token", b"captok")])
    assert status == 200
    assert inner.seen == ["/mcp"]   # HeaderPathToken's job, untouched


def test_forged_jwt_is_401_and_the_verdict_is_cached():
    g, calls = _gate(jwt_claims=None)
    for _ in range(3):
        status, _, _ = _run(
            g, "/mcp", headers=[(b"authorization", b"Bearer x.y.z")])
        assert status == 401
    assert calls["jwt"] == 1   # cached after the first verification


def test_legacy_capability_url_still_requires_identity():
    g, _ = _gate()
    status, _, _ = _run(g, "/mcp/captok")
    assert status == 401


def test_any_project_service_account_passes_with_service_audience():
    """Operator SAs of this project each held run.invoker under IAM; the
    gate accepts the project SA domain rather than an allowlist that
    breaks the next legitimate one (measured: the deployer 403'd)."""
    ok, _, reason = _a(
        "mishleyotiende@digital-maturity-assessor.iam.gserviceaccount.com",
        f"https://{HOST}")
    assert ok and "service-account" in reason


def test_a_foreign_project_service_account_is_refused():
    ok, status, _ = _a("attacker@some-other-project.iam.gserviceaccount.com",
                       f"https://{HOST}")
    assert not ok and status == 403
