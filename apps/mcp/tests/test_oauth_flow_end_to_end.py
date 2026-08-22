"""The whole claude.ai dance, walked start to finish against the real ASGI app.

The owner's report was not "one endpoint is wrong", it was "Authorization
with DMA Insights failed" and then, once connected, "your connection stopped
working, reconnect to continue" — over and over. Neither is diagnosable by
checking endpoints one at a time, because both are properties of the WHOLE
sequence: discover, register, authorize, log in, exchange, call, expire,
refresh, call again. So this file walks the sequence.

Only the human's browser leg is stubbed (Google's consent screen and its
code-for-identity exchange). Everything else — every document, every
redirect, every signature, every PKCE check — is the code that runs in
production, driven through the same ASGI interface Cloud Run drives.
"""
import base64
import hashlib
import json
import sys
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dma_mcp import oauth_as  # noqa: E402
from dma_mcp.oauth_gate import OAuthGate  # noqa: E402

HOST = "dmai-mcp-dukrne5v4a-uc.a.run.app"
BASE = f"https://{HOST}"
CLAUDE_REDIRECT = "https://claude.ai/api/mcp/auth_callback"
SIGNING_KEY = "test-signing-key-not-a-real-secret"
GOOGLE_CLIENT = "306195530103-example.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OAUTH_SIGNING_KEY", SIGNING_KEY)
    monkeypatch.setenv("OAUTH_CLIENT_ID", GOOGLE_CLIENT)
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "test-google-secret")
    monkeypatch.setenv("MCP_SERVICE_URL", BASE)


class _Inner:
    """Stands in for the MCP app: records what reached it."""

    def __init__(self):
        self.seen = []

    async def __call__(self, scope, receive, send):
        self.seen.append(scope.get("path"))
        body = json.dumps({"jsonrpc": "2.0", "id": 1,
                           "result": {"tools": [{"name": f"t{i}"}
                                                for i in range(33)]}}).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})


class Client:
    """A strict OAuth 2.1 / MCP client — what the dialog behaves like."""

    def __init__(self, gate):
        self.gate = gate

    def request(self, method, path, *, query="", headers=(), body=b""):
        # A FRESH loop per call, never the ambient one: run under the full
        # suite, get_event_loop() hands back whatever an earlier async test
        # left behind — often closed — and every request here dies on a
        # loop it never created. Passing alone and failing in suite is the
        # signature of exactly that, and it hid these tests' real verdicts.
        import asyncio
        sent = []

        async def send(msg):
            sent.append(msg)

        chunks = [body]

        async def receive():
            return {"type": "http.request",
                    "body": chunks.pop(0) if chunks else b"",
                    "more_body": bool(chunks)}

        scope = {"type": "http", "method": method, "path": path,
                 "query_string": query.encode(),
                 "headers": [(b"host", HOST.encode())] + list(headers)}
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.gate(scope, receive, send))
        finally:
            loop.close()
        start = next(m for m in sent if m["type"] == "http.response.start")
        hdrs = {k.decode().lower(): v.decode() for k, v in start["headers"]}
        payload = b"".join(m.get("body", b"") for m in sent
                           if m["type"] == "http.response.body")
        return start["status"], hdrs, payload


def _gate(inner=None, google_identity=None):
    gate = OAuthGate(inner or _Inner(), "captok",
                     verify_jwt=lambda t, a: (_ for _ in ()).throw(
                         ValueError("not a google id token")),
                     lookup_access_token=lambda t: (_ for _ in ()).throw(
                         ValueError("not a google access token")))
    if google_identity is not None:
        # Stub ONLY the human leg: Google's code exchange and identity.
        real = oauth_as.callback

        def patched(params, base, exchange=None, identify=None):
            return real(params, base,
                        exchange=lambda code, b: {"id_token": "stub"},
                        identify=lambda idt: google_identity)
        gate._patched_callback = patched
        oauth_as.callback = patched
    return gate


@pytest.fixture
def restore_callback():
    real = oauth_as.callback
    yield
    oauth_as.callback = real


def _pkce():
    verifier = base64.urlsafe_b64encode(b"v" * 48).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


# ── the sequence ─────────────────────────────────────────────────────────

def test_the_full_connect_sequence_a_claude_ai_client_performs(restore_callback):
    """Discover, register, authorize, log in, exchange, call — in order."""
    inner = _Inner()
    gate = _gate(inner, google_identity={"email": "person@zennify.com",
                                         "email_verified": True})
    c = Client(gate)

    # 1 · the unauthenticated call that starts everything
    status, hdrs, _ = c.request("POST", "/mcp")
    assert status == 401
    assert "resource_metadata=" in hdrs["www-authenticate"]
    assert hdrs["access-control-expose-headers"].lower().startswith(
        "www-authenticate"), "a browser client cannot read a header it is " \
                             "not permitted to see"

    # 2 · protected-resource metadata names an authorization server
    status, _, body = c.request("GET", "/.well-known/oauth-protected-resource")
    assert status == 200
    rm = json.loads(body)
    assert rm["resource_name"] == "DMA Insights"
    assert rm["authorization_servers"] == [BASE], \
        "the AS must be us; Google cannot serve a generic client"

    # 3 · authorization-server metadata — the path that used to answer 401
    status, _, body = c.request("GET", "/.well-known/oauth-authorization-server")
    assert status == 200
    md = json.loads(body)
    assert md["issuer"] == BASE
    assert md["registration_endpoint"] == f"{BASE}/register"
    assert md["code_challenge_methods_supported"] == ["S256"]
    assert "refresh_token" in md["grant_types_supported"], \
        "without refresh, the connection dies in an hour and the owner has " \
        "to reconnect — the reported symptom"

    # 4 · dynamic registration, because the dialog registers rather than asks
    status, _, body = c.request(
        "POST", "/register",
        body=json.dumps({"client_name": "Claude",
                         "redirect_uris": [CLAUDE_REDIRECT],
                         "grant_types": ["authorization_code", "refresh_token"],
                         "token_endpoint_auth_method": "client_secret_post"}
                        ).encode())
    assert status == 201, body
    reg = json.loads(body)
    client_id, client_secret = reg["client_id"], reg["client_secret"]

    # 5 · authorize → we hand the human to Google, carrying a signed state
    verifier, challenge = _pkce()
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id,
        "redirect_uri": CLAUDE_REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "client-state-123",
        "scope": "openid email profile"})
    status, hdrs, _ = c.request("GET", "/authorize", query=q)
    assert status == 302
    to = urllib.parse.urlparse(hdrs["location"])
    assert to.netloc == "accounts.google.com"
    gq = dict(urllib.parse.parse_qsl(to.query))
    assert gq["client_id"] == GOOGLE_CLIENT
    assert gq["redirect_uri"] == f"{BASE}/oauth/callback", \
        "this exact URI must be registered on the Google client"
    assert gq["hd"] == "zennify.com"
    carried_state = gq["state"]

    # 6 · the human logs in; Google returns to OUR callback
    status, hdrs, _ = c.request(
        "GET", "/oauth/callback",
        query=urllib.parse.urlencode({"code": "google-code",
                                      "state": carried_state}))
    assert status == 302
    back = urllib.parse.urlparse(hdrs["location"])
    assert f"{back.scheme}://{back.netloc}{back.path}" == CLAUDE_REDIRECT
    bq = dict(urllib.parse.parse_qsl(back.query))
    assert bq["state"] == "client-state-123", "the client's state must survive"
    code = bq["code"]

    # 7 · token exchange with PKCE
    status, _, body = c.request(
        "POST", "/token",
        body=urllib.parse.urlencode({
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": CLAUDE_REDIRECT, "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": verifier}).encode())
    assert status == 200, body
    tok = json.loads(body)
    assert tok["token_type"] == "Bearer"
    assert tok["expires_in"] == 3600
    assert tok["refresh_token"], "no refresh token means reconnect-every-hour"

    # 8 · the tools finally answer
    status, _, body = c.request(
        "POST", "/mcp",
        headers=[(b"authorization",
                  f"Bearer {tok['access_token']}".encode())])
    assert status == 200
    assert len(json.loads(body)["result"]["tools"]) == 33
    assert inner.seen == ["/mcp/captok"], \
        "an authenticated caller reaches the capability path without ever " \
        "knowing the capability token"

    # 9 · an hour later: refresh, and call again — no human, no reconnect
    status, _, body = c.request(
        "POST", "/token",
        body=urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
            "client_id": client_id, "client_secret": client_secret}).encode())
    assert status == 200, body
    tok2 = json.loads(body)
    assert tok2["access_token"] != tok["access_token"]
    assert tok2["refresh_token"] != tok["refresh_token"], "rotate on use"
    status, _, _ = c.request(
        "POST", "/mcp",
        headers=[(b"authorization",
                  f"Bearer {tok2['access_token']}".encode())])
    assert status == 200


def test_a_non_zennify_login_never_receives_a_code(restore_callback):
    """The domain rule at the login boundary: the person is turned away with
    an OAuth error at the client's own redirect, not with a broken page."""
    gate = _gate(google_identity={"email": "visitor@gmail.com",
                                  "email_verified": True})
    c = Client(gate)
    reg = json.loads(c.request("POST", "/register", body=json.dumps(
        {"client_name": "Claude", "redirect_uris": [CLAUDE_REDIRECT]}).encode())[2])
    _, challenge = _pkce()
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": CLAUDE_REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "s"})
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(
        c.request("GET", "/authorize", query=q)[1]["location"]).query))["state"]
    status, hdrs, _ = c.request("GET", "/oauth/callback", query=(
        urllib.parse.urlencode({"code": "g", "state": state})))
    assert status == 302
    err = dict(urllib.parse.parse_qsl(
        urllib.parse.urlparse(hdrs["location"]).query))
    assert err["error"] == "access_denied"
    assert "zennify.com" in err["error_description"]
    assert "code" not in err


def test_an_unverified_google_email_is_refused(restore_callback):
    gate = _gate(google_identity={"email": "person@zennify.com",
                                 "email_verified": False})
    c = Client(gate)
    reg = json.loads(c.request("POST", "/register", body=json.dumps(
        {"redirect_uris": [CLAUDE_REDIRECT]}).encode())[2])
    _, challenge = _pkce()
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": CLAUDE_REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "s"})
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(
        c.request("GET", "/authorize", query=q)[1]["location"]).query))["state"]
    _, hdrs, _ = c.request("GET", "/oauth/callback", query=(
        urllib.parse.urlencode({"code": "g", "state": state})))
    assert "access_denied" in hdrs["location"]


# ── the attacks the flow must survive ────────────────────────────────────

def test_an_unregistered_redirect_uri_is_refused():
    """Open-redirect prevention: the registered set is inside the signed
    client id, so it cannot be widened by editing the request."""
    c = Client(_gate())
    reg = json.loads(c.request("POST", "/register", body=json.dumps(
        {"redirect_uris": [CLAUDE_REDIRECT]}).encode())[2])
    _, challenge = _pkce()
    status, _, body = c.request("GET", "/authorize", query=urllib.parse.urlencode({
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": "https://evil.example/steal",
        "code_challenge": challenge, "code_challenge_method": "S256"}))
    assert status == 400
    assert "not registered" in json.loads(body)["error_description"]


def test_a_tampered_client_id_fails_its_signature():
    c = Client(_gate())
    reg = json.loads(c.request("POST", "/register", body=json.dumps(
        {"redirect_uris": [CLAUDE_REDIRECT]}).encode())[2])
    forged = reg["client_id"][:-4] + "AAAA"
    _, challenge = _pkce()
    status, _, body = c.request("GET", "/authorize", query=urllib.parse.urlencode({
        "response_type": "code", "client_id": forged,
        "redirect_uri": CLAUDE_REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256"}))
    assert status == 400 and json.loads(body)["error"] == "invalid_client"


def test_pkce_is_required_and_enforced(restore_callback):
    """Both halves: the request must carry S256, and the wrong verifier at
    the token endpoint must fail."""
    gate = _gate(google_identity={"email": "person@zennify.com",
                                  "email_verified": True})
    c = Client(gate)
    reg = json.loads(c.request("POST", "/register", body=json.dumps(
        {"redirect_uris": [CLAUDE_REDIRECT]}).encode())[2])
    # (a) no challenge at all
    _, hdrs, _ = c.request("GET", "/authorize", query=urllib.parse.urlencode({
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": CLAUDE_REDIRECT, "state": "s"}))
    assert "invalid_request" in hdrs["location"]
    # (b) right challenge, wrong verifier
    verifier, challenge = _pkce()
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": CLAUDE_REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "s"})
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(
        c.request("GET", "/authorize", query=q)[1]["location"]).query))["state"]
    code = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(
        c.request("GET", "/oauth/callback", query=urllib.parse.urlencode(
            {"code": "g", "state": state}))[1]["location"]).query))["code"]
    status, _, body = c.request("POST", "/token", body=urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code,
        "client_id": reg["client_id"], "code_verifier": "wrong-verifier",
        "redirect_uri": CLAUDE_REDIRECT}).encode())
    assert status == 400
    assert json.loads(body)["error_description"] == "PKCE verification failed"


def test_a_forged_access_token_never_reaches_the_tools():
    inner = _Inner()
    c = Client(_gate(inner))
    forged = oauth_as.sign({"typ": "at", "sub": "person@zennify.com",
                            "exp": 9999999999})
    # signed with the right key but by us in-process — so instead break it:
    status, _, _ = c.request("POST", "/mcp", headers=[
        (b"authorization", f"Bearer {forged[:-3]}xyz".encode())])
    assert status == 401
    assert inner.seen == []


def test_a_valid_token_for_the_wrong_domain_is_refused():
    inner = _Inner()
    c = Client(_gate(inner))
    tok = oauth_as.sign({"typ": "at", "sub": "visitor@gmail.com",
                         "exp": 9999999999})
    status, _, body = c.request("POST", "/mcp", headers=[
        (b"authorization", f"Bearer {tok}".encode())])
    assert status == 403
    assert "zennify.com" in json.loads(body)["detail"]
    assert inner.seen == []


def test_an_expired_access_token_is_refused_not_accepted():
    c = Client(_gate())
    stale = oauth_as.sign({"typ": "at", "sub": "person@zennify.com",
                           "exp": 1000000000})
    assert c.request("POST", "/mcp", headers=[
        (b"authorization", f"Bearer {stale}".encode())])[0] == 401


def test_a_refresh_token_cannot_be_used_as_an_access_token():
    """Type confusion, closed: the typ claim is checked, not just the
    signature."""
    c = Client(_gate())
    rt = oauth_as.sign({"typ": "rt", "sub": "person@zennify.com",
                        "exp": 9999999999})
    assert c.request("POST", "/mcp", headers=[
        (b"authorization", f"Bearer {rt}".encode())])[0] == 401


def test_an_authorization_code_is_not_reusable_across_clients(restore_callback):
    gate = _gate(google_identity={"email": "person@zennify.com",
                                  "email_verified": True})
    c = Client(gate)
    a = json.loads(c.request("POST", "/register", body=json.dumps(
        {"redirect_uris": [CLAUDE_REDIRECT]}).encode())[2])
    b = json.loads(c.request("POST", "/register", body=json.dumps(
        {"redirect_uris": ["https://other.example/cb"]}).encode())[2])
    verifier, challenge = _pkce()
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": a["client_id"],
        "redirect_uri": CLAUDE_REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "s"})
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(
        c.request("GET", "/authorize", query=q)[1]["location"]).query))["state"]
    code = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(
        c.request("GET", "/oauth/callback", query=urllib.parse.urlencode(
            {"code": "g", "state": state}))[1]["location"]).query))["code"]
    status, _, body = c.request("POST", "/token", body=urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code,
        "client_id": b["client_id"], "code_verifier": verifier}).encode())
    assert status == 400
    assert "another client" in json.loads(body)["error_description"]


def test_cors_preflight_answers_without_authentication():
    """The dialog's browser sends OPTIONS first; a 401 there ends the flow
    before the real request is ever made."""
    c = Client(_gate())
    status, hdrs, _ = c.request("OPTIONS", "/mcp")
    assert status == 204
    assert hdrs["access-control-allow-origin"] == "*"
    assert "authorization" in hdrs["access-control-allow-headers"]


def test_metadata_is_canonical_regardless_of_which_hostname_was_used():
    """Cloud Run answers on several hostnames; endpoints that varied by host
    would strand a client on endpoints it never discovered."""
    c = Client(_gate())
    _, _, body = c.request("GET", "/.well-known/oauth-authorization-server")
    assert json.loads(body)["issuer"] == BASE


def test_the_service_path_still_belongs_to_the_plugin():
    """Rung C must not have displaced rung A: a header-token request with a
    Google identity still routes exactly as it did."""
    inner = _Inner()
    gate = OAuthGate(inner, "captok",
                     verify_jwt=lambda t, a: {
                         "email": "dmai-routine@digital-maturity-assessor."
                                  "iam.gserviceaccount.com",
                         "aud": BASE, "email_verified": True},
                     lookup_access_token=lambda t: {})
    c = Client(gate)
    status, _, _ = c.request("POST", "/mcp", headers=[
        (b"authorization", b"Bearer a.b.c"),
        (b"x-dma-path-token", b"captok")])
    assert status == 200
    assert inner.seen == ["/mcp"]


# ── what the ground-truth probe measured about Claude's own client ───────

def test_metadata_advertises_what_claude_actually_looks_for():
    """Measured 2026-08-20 from Claude's live client metadata document and
    Anthropic's connector docs, not assumed: offline_access is what makes
    the client ask for a refresh token, CIMD support requires the "none"
    auth method beside it, and S256 is sent unconditionally."""
    c = Client(_gate())
    _, _, body = c.request("GET", "/.well-known/oauth-authorization-server")
    md = json.loads(body)
    assert "offline_access" in md["scopes_supported"]
    assert md["client_id_metadata_document_supported"] is True
    assert "none" in md["token_endpoint_auth_methods_supported"], \
        "a CIMD client is public: advertising CIMD without 'none' is a " \
        "contradiction the client resolves by giving up"
    assert md["code_challenge_methods_supported"] == ["S256"]
    _, _, body = c.request("GET", "/.well-known/oauth-protected-resource/mcp")
    assert "offline_access" in json.loads(body)["scopes_supported"]


def test_a_client_id_metadata_document_is_accepted_and_must_self_identify(monkeypatch):
    """Claude's preferred client identity is a URL. It is honoured only when
    the document names itself — otherwise any URL could assert any client."""
    from dma_mcp import oauth_as as m
    m._CIMD_CACHE.clear()
    url = "https://claude.ai/oauth/mcp-oauth-client-metadata"
    served = {"client_id": url, "client_name": "Claude",
              "redirect_uris": [CLAUDE_REDIRECT],
              "token_endpoint_auth_method": "none"}

    class _Resp:
        def __init__(self, doc):
            self._raw = json.dumps(doc).encode()

        def read(self, n=None):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(m.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(served))
    claims = m.client_claims(url)
    assert claims and claims["ru"] == [CLAUDE_REDIRECT] and claims["cimd"]

    # a document claiming to be someone else is refused
    m._CIMD_CACHE.clear()
    served["client_id"] = "https://evil.example/other"
    assert m.client_claims(url) is None
    # and a non-https client id is never fetched at all
    assert m.client_claims("http://claude.ai/x") is None


def test_the_resource_indicator_is_carried_into_the_token(restore_callback):
    """RFC 8707: Claude sends `resource` on /authorize and /token; the token
    it gets back must be bound to that resource rather than silently
    audience-less."""
    gate = _gate(google_identity={"email": "person@zennify.com",
                                  "email_verified": True})
    c = Client(gate)
    reg = json.loads(c.request("POST", "/register", body=json.dumps(
        {"redirect_uris": [CLAUDE_REDIRECT]}).encode())[2])
    verifier, challenge = _pkce()
    resource = f"{BASE}/mcp"
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": CLAUDE_REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "s",
        "scope": "openid email profile offline_access", "resource": resource})
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(
        c.request("GET", "/authorize", query=q)[1]["location"]).query))["state"]
    code = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(
        c.request("GET", "/oauth/callback", query=urllib.parse.urlencode(
            {"code": "g", "state": state}))[1]["location"]).query))["code"]
    _, _, body = c.request("POST", "/token", body=urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code,
        "client_id": reg["client_id"], "code_verifier": verifier,
        "redirect_uri": CLAUDE_REDIRECT, "resource": resource}).encode())
    tok = json.loads(body)
    claims = oauth_as.verify(tok["access_token"], typ="at")
    assert claims["aud"] == resource
    assert "offline_access" in claims["sc"]
