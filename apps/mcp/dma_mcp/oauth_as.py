"""A minimal OAuth 2.1 authorization server, so a generic MCP client can connect.

WHY THIS EXISTS, measured 2026-08-20 rather than assumed.

The connector advertised `accounts.google.com` as its authorization server.
Three facts killed that:

  1. Google publishes NO `registration_endpoint` (verified live against
     https://accounts.google.com/.well-known/oauth-authorization-server), so a
     client that registers dynamically — which is what the claude.ai custom
     connector dialog does when you leave the client fields blank — has
     nowhere to register.
  2. Google issues a REFRESH TOKEN only for `access_type=offline` plus
     `prompt=consent`, both Google-proprietary parameters a standard OAuth
     2.1 client never sends. Without one, the access token dies in an hour
     and the connection is unrecoverable — the owner's exact report: "Your
     connection to DMA Insights stopped working. Reconnect to continue. I
     keep on reconnecting."
  3. Every /.well-known path on this host answered 401, because the identity
     gate demanded a bearer for everything except one document. A client
     probing for authorization-server metadata got an auth challenge where it
     needed either metadata or an honest 404.

So this module IS the authorization server: it registers clients, runs the
authorization-code flow with PKCE, issues our own access and refresh tokens,
and delegates only the human LOGIN to Google — which is still what proves the
person is a verified @zennify.com account. Google remains the identity
provider; it is no longer asked to be an OAuth server for a client it was
never built for.

STATELESS BY CONSTRUCTION. Cloud Run serves consecutive requests from
different instances and this service holds no session store, so nothing here
is written down: client ids, authorization codes, access tokens and refresh
tokens are all HMAC-signed blobs that carry their own claims. A signature
that verifies IS the record. The key lives in Secret Manager
(dmai-oauth-signing-key) and rotating it invalidates every issued token,
which is the intended revocation lever.

The domain rule is enforced TWICE, deliberately: once at login, where a
non-@zennify.com Google account never receives a code, and again on every
tool call in oauth_gate, where the token's own subject is re-checked. One
enforcement point is a single edit away from being no enforcement point.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
DOMAIN = os.environ.get("DMA_OAUTH_DOMAIN", "zennify.com").lower()

CODE_TTL = 300           # 5 min — an authorization code is a one-hop artefact
ACCESS_TTL = 3600        # 1 h
REFRESH_TTL = 60 * 60 * 24 * 30   # 30 days; rotated on every use
STATE_TTL = 900          # 15 min for the round trip through Google

CALLBACK_PATH = "/oauth/callback"


# ── signing ──────────────────────────────────────────────────────────────
def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64u_dec(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def signing_key() -> bytes:
    key = os.environ.get("OAUTH_SIGNING_KEY", "").strip()
    return key.encode() if key else b""


def sign(payload: dict) -> str:
    """payload.signature — compact, url-safe, and self-describing."""
    body = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64u(hmac.new(signing_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token: str, *, typ: str | None = None) -> dict | None:
    """Claims if the signature holds and the token has not expired, else None.

    Constant-time comparison, and expiry checked HERE rather than by callers,
    so no call site can forget it.
    """
    try:
        body, sig = token.split(".", 1)
        want = _b64u(hmac.new(signing_key(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, want):
            return None
        claims = json.loads(_b64u_dec(body))
    except Exception:                                        # noqa: BLE001
        return None
    if typ is not None and claims.get("typ") != typ:
        return None
    exp = claims.get("exp")
    if exp is not None and time.time() > float(exp):
        return None
    return claims


# ── stateless dynamic client registration (RFC 7591) ─────────────────────
def register_client(meta: dict) -> dict:
    """A client id that IS its own registration record.

    The redirect URIs the client declared travel inside the signed id, so a
    later /authorize can check them without any storage — and a tampered id
    fails its signature rather than widening the allowed redirects.
    """
    redirects = [u for u in (meta.get("redirect_uris") or []) if isinstance(u, str)]
    if not redirects:
        return {"error": "invalid_redirect_uri",
                "error_description": "redirect_uris is required"}
    now = int(time.time())
    client_id = "dmai." + sign({"typ": "client", "ru": redirects,
                                "n": (meta.get("client_name") or "")[:120],
                                "iat": now})
    secret = _b64u(hmac.new(signing_key(), f"secret:{client_id}".encode(),
                            hashlib.sha256).digest())
    return {
        "client_id": client_id,
        "client_secret": secret,
        "client_id_issued_at": now,
        "client_secret_expires_at": 0,          # 0 = never, per RFC 7591
        "redirect_uris": redirects,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": meta.get("token_endpoint_auth_method")
                                      or "client_secret_post",
    }


_CIMD_CACHE: dict = {}


def _client_id_metadata(url: str) -> dict | None:
    """A client identified by a URL that serves its own registration.

    Claude publishes one at https://claude.ai/oauth/mcp-oauth-client-metadata
    (fetched 2026-08-20: client_name "Claude", the single redirect URI
    https://claude.ai/api/mcp/auth_callback, token_endpoint_auth_method
    "none"), and prefers it to dynamic registration. Supporting it costs one
    cached fetch and removes a whole failure mode: a client that cannot
    register has no identity, and a server that refuses its URL-shaped
    client_id as "unknown" fails the connection with exactly the opaque
    authorization error this connector was reporting.

    The document must name itself — `client_id` inside must equal the URL it
    was fetched from — so a URL cannot be used to assert someone else's
    identity, and only https is fetched.
    """
    if not url.startswith("https://"):
        return None
    hit = _CIMD_CACHE.get(url)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            doc = json.loads(resp.read(65536))
    except Exception:                                        # noqa: BLE001
        return None
    if doc.get("client_id") != url:
        return None
    redirects = [u for u in (doc.get("redirect_uris") or [])
                 if isinstance(u, str)]
    if not redirects:
        return None
    claims = {"ru": redirects, "n": doc.get("client_name", ""), "cimd": True}
    _CIMD_CACHE[url] = (time.time() + 3600, claims)
    return claims


def client_claims(client_id: str) -> dict | None:
    if client_id.startswith("https://"):
        return _client_id_metadata(client_id)
    if not client_id.startswith("dmai."):
        return None
    return verify(client_id[5:], typ="client")


def client_secret_for(client_id: str) -> str:
    return _b64u(hmac.new(signing_key(), f"secret:{client_id}".encode(),
                          hashlib.sha256).digest())


# ── metadata documents ───────────────────────────────────────────────────
def issuer(base: str) -> str:
    return base.rstrip("/")


def as_metadata(base: str) -> dict:
    b = issuer(base)
    return {
        "issuer": b,
        "authorization_endpoint": f"{b}/authorize",
        "token_endpoint": f"{b}/token",
        "registration_endpoint": f"{b}/register",
        "scopes_supported": ["openid", "email", "profile", "offline_access"],
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post", "client_secret_basic", "none"],
        "code_challenge_methods_supported": ["S256"],
        # Claude prefers a Client ID Metadata Document to dynamic
        # registration; advertising it REQUIRES "none" above, because a
        # CIMD client is public and authenticates with PKCE alone.
        "client_id_metadata_document_supported": True,
        "service_documentation": f"{b}/.well-known/oauth-protected-resource",
    }


def resource_metadata(base: str) -> dict:
    b = issuer(base)
    return {
        "resource": f"{b}/mcp",
        "resource_name": "DMA Insights",
        "authorization_servers": [b],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "email", "profile", "offline_access"],
    }


# ── the flow ─────────────────────────────────────────────────────────────
def authorize_redirect(params: dict, base: str) -> tuple:
    """(status, headers, body) for GET /authorize.

    Errors go back to the CLIENT's redirect_uri when we have a verified one
    (OAuth's rule — the user must land somewhere that can explain itself),
    and only otherwise render as JSON.
    """
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    claims = client_claims(client_id)
    if claims is None:
        return _json_err(400, "invalid_client", "unknown or tampered client_id")
    if redirect_uri not in (claims.get("ru") or []):
        return _json_err(400, "invalid_request",
                         "redirect_uri is not registered for this client")
    state = params.get("state", "")
    if params.get("response_type") != "code":
        return _redirect_err(redirect_uri, "unsupported_response_type",
                             "only response_type=code is supported", state)
    challenge = params.get("code_challenge", "")
    method = params.get("code_challenge_method", "")
    if not challenge or method != "S256":
        return _redirect_err(redirect_uri, "invalid_request",
                             "PKCE with code_challenge_method=S256 is required",
                             state)
    google_client = os.environ.get("OAUTH_CLIENT_ID", "").strip()
    if not google_client or not signing_key():
        return _redirect_err(
            redirect_uri, "server_error",
            "authorization server not configured: OAUTH_CLIENT_ID and "
            "OAUTH_SIGNING_KEY must be wired from Secret Manager", state)
    carried = sign({"typ": "xstate", "ci": client_id, "ru": redirect_uri,
                    "cc": challenge, "st": state,
                    "sc": params.get("scope", ""),
                    # RFC 8707: Claude sends `resource` on both /authorize and
                    # /token, and expects the token to be bound to it.
                    "rs": params.get("resource", ""),
                    "exp": int(time.time()) + STATE_TTL})
    google = GOOGLE_AUTH + "?" + urllib.parse.urlencode({
        "client_id": google_client,
        "redirect_uri": f"{issuer(base)}{CALLBACK_PATH}",
        "response_type": "code",
        "scope": "openid email profile",
        "state": carried,
        "prompt": "select_account",
        "hd": DOMAIN,          # ask Google for the right domain up front
        "include_granted_scopes": "true",
    })
    return 302, [(b"location", google.encode())], b""


def _exchange_with_google(code: str, base: str) -> dict:
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": os.environ.get("OAUTH_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("OAUTH_CLIENT_SECRET", "").strip(),
        "redirect_uri": f"{issuer(base)}{CALLBACK_PATH}",
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(GOOGLE_TOKEN, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _identity_from_id_token(id_token: str) -> dict:
    """Claims from Google's id_token, signature-verified against its certs."""
    import google.auth.transport.requests
    import google.oauth2.id_token
    request = google.auth.transport.requests.Request()
    return google.oauth2.id_token.verify_oauth2_token(
        id_token, request, os.environ.get("OAUTH_CLIENT_ID", "").strip())


def callback(params: dict, base: str, exchange=None, identify=None) -> tuple:
    """(status, headers, body) for GET /oauth/callback — Google's return leg."""
    carried = verify(params.get("state", ""), typ="xstate")
    if carried is None:
        return _json_err(400, "invalid_request",
                         "state did not verify or expired; restart the login")
    redirect_uri, state = carried["ru"], carried.get("st", "")
    if params.get("error"):
        return _redirect_err(redirect_uri, params["error"],
                             params.get("error_description", "")[:200], state)
    try:
        tok = (exchange or _exchange_with_google)(params.get("code", ""), base)
        ident = (identify or _identity_from_id_token)(tok.get("id_token", ""))
    except Exception as e:                                   # noqa: BLE001
        return _redirect_err(redirect_uri, "server_error",
                             f"google exchange failed: {type(e).__name__}", state)
    email = (ident.get("email") or "").lower()
    verified = ident.get("email_verified") in (True, "true", "True", 1)
    if not email.endswith(f"@{DOMAIN}") or not verified:
        return _redirect_err(
            redirect_uri, "access_denied",
            f"only verified @{DOMAIN} accounts may use DMA Insights", state)
    code = sign({"typ": "code", "sub": email, "ci": carried["ci"],
                 "ru": redirect_uri, "cc": carried["cc"],
                 "sc": carried.get("sc", ""), "rs": carried.get("rs", ""),
                 "jti": _b64u(os.urandom(9)),
                 "exp": int(time.time()) + CODE_TTL})
    back = redirect_uri + ("&" if "?" in redirect_uri else "?") + \
        urllib.parse.urlencode({"code": code, "state": state})
    return 302, [(b"location", back.encode())], b""


def _pkce_ok(verifier: str, challenge: str) -> bool:
    if not verifier:
        return False
    digest = hashlib.sha256(verifier.encode()).digest()
    return hmac.compare_digest(_b64u(digest), challenge)


def _issue(email: str, client_id: str, scope: str,
           resource: str = "") -> dict:
    """A fresh pair, unique per issuance.

    The `jti` nonce is not decoration: without it two tokens minted in the
    same second for the same subject are BYTE-IDENTICAL (caught by the
    end-to-end test, 2026-08-20), which quietly turns refresh-token rotation
    into a no-op — the "new" token equals the old one, so nothing is
    superseded and a leaked refresh token would stay valid for its whole
    thirty days.
    """
    now = int(time.time())
    return {
        "access_token": sign({"typ": "at", "sub": email, "ci": client_id,
                              "sc": scope, "aud": resource,
                              "exp": now + ACCESS_TTL,
                              "jti": _b64u(os.urandom(9))}),
        "token_type": "Bearer",
        "expires_in": ACCESS_TTL,
        "refresh_token": sign({"typ": "rt", "sub": email, "ci": client_id,
                               "sc": scope, "aud": resource,
                               "exp": now + REFRESH_TTL,
                               "jti": _b64u(os.urandom(9))}),
        "scope": scope or "openid email profile",
    }


def token_grant(form: dict, auth_header: str = "") -> tuple:
    """(status, body dict) for POST /token — both grants this server issues."""
    if not signing_key():
        return 500, {"error": "server_error",
                     "error_description": "OAUTH_SIGNING_KEY is not wired"}
    grant = form.get("grant_type", "")
    client_id = form.get("client_id", "")
    if not client_id and auth_header.lower().startswith("basic "):
        try:
            raw = base64.b64decode(auth_header[6:]).decode()
            client_id = urllib.parse.unquote(raw.split(":", 1)[0])
        except Exception:                                    # noqa: BLE001
            client_id = ""
    if client_claims(client_id) is None:
        return 401, {"error": "invalid_client",
                     "error_description": "unknown or tampered client_id"}

    if grant == "authorization_code":
        claims = verify(form.get("code", ""), typ="code")
        if claims is None:
            return 400, {"error": "invalid_grant",
                         "error_description": "code invalid or expired"}
        if claims.get("ci") != client_id:
            return 400, {"error": "invalid_grant",
                         "error_description": "code was issued to another client"}
        if form.get("redirect_uri") and form["redirect_uri"] != claims.get("ru"):
            return 400, {"error": "invalid_grant",
                         "error_description": "redirect_uri does not match the code"}
        if not _pkce_ok(form.get("code_verifier", ""), claims.get("cc", "")):
            return 400, {"error": "invalid_grant",
                         "error_description": "PKCE verification failed"}
        return 200, _issue(claims["sub"], client_id, claims.get("sc", ""),
                           form.get("resource") or claims.get("rs", ""))

    if grant == "refresh_token":
        claims = verify(form.get("refresh_token", ""), typ="rt")
        if claims is None:
            return 400, {"error": "invalid_grant",
                         "error_description": "refresh token invalid or expired"}
        if claims.get("ci") != client_id:
            return 400, {"error": "invalid_grant",
                         "error_description": "refresh token belongs to another client"}
        email = (claims.get("sub") or "").lower()
        if not email.endswith(f"@{DOMAIN}"):
            return 400, {"error": "invalid_grant",
                         "error_description": "subject is no longer authorised"}
        # Rotation: the old refresh token is superseded by the new one.
        return 200, _issue(email, client_id, claims.get("sc", ""),
                           form.get("resource") or claims.get("aud", ""))

    return 400, {"error": "unsupported_grant_type",
                 "error_description": f"{grant!r} is not supported"}


# ── small helpers ────────────────────────────────────────────────────────
def _json_err(status: int, err: str, desc: str) -> tuple:
    body = json.dumps({"error": err, "error_description": desc}).encode()
    return status, [(b"content-type", b"application/json")], body


def _redirect_err(redirect_uri: str, err: str, desc: str, state: str) -> tuple:
    url = redirect_uri + ("&" if "?" in redirect_uri else "?") + \
        urllib.parse.urlencode({"error": err, "error_description": desc,
                                "state": state})
    return 302, [(b"location", url.encode())], b""
