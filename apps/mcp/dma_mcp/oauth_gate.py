"""In-app identity gate: the connector reads WHO on every request.

WHY (owner, 2026-08-20): the connector must be reachable from claude.ai's
custom-connector dialog, whose client speaks OAuth — not Google IAM identity
tokens — and "anyone with the @zennify domain is authorized". Cloud Run IAM
cannot serve both callers, so ingress opens and the identity check moves
INTO the app, where it verifies more than IAM did, not less. The 2026-08-16
lockdown's lesson ("the plugin minted an identity token on every connection
and sent it; nothing on the other side read it") is honoured here by
construction: every request's bearer is cryptographically verified and its
identity checked against policy, and the capability path token stays as
defense in depth for the service path.

THREE RUNGS, matching the three kinds of caller:

  A · Google-signed ID TOKEN (a JWT) — the service path. The plugin's
      stdio proxy and gcp_token.py mint these with the service URL as
      audience; any service account of this project is an operator
      identity. A @zennify.com person with plain `gcloud auth
      print-identity-token` also lands here.
  B · Google OAuth ACCESS TOKEN (opaque) — a person who obtained one
      directly through this project's Google client, validated at Google's
      tokeninfo endpoint: audience must be OUR client id, email a verified
      @zennify.com address.
  C · OUR OWN access token — the claude.ai path, issued by the
      authorization server in dma_mcp.oauth_as after Google has proved the
      person is a verified @zennify.com account. Verified by HMAC here, and
      the domain re-checked from the token's own subject, because one
      enforcement point is a single edit away from being none.

Rung C exists because Google cannot BE the authorization server for a
generic MCP client: it publishes no registration endpoint, and it issues no
refresh token without proprietary parameters a standard client never sends —
which is exactly why the connection died every hour and had to be
reconnected. See dma_mcp/oauth_as.py for the measurements.

PUBLIC BY DESIGN, and only these: the two metadata documents, the
authorization, token, registration and callback endpoints, and CORS
preflight. Everything else needs a bearer. A path that answered 401 where a
client expected metadata is what made discovery impossible before.

Invariant 1 is untouched: an auth lookup is not a model call, and this is
the agent-facing connector, not the serving path.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

from dma_mcp import oauth_as

DOMAIN = os.environ.get("DMA_OAUTH_DOMAIN", "zennify.com").lower()
ALLOWED_SAS = {
    s.strip().lower()
    for s in os.environ.get(
        "DMA_ALLOWED_SAS",
        "dmai-routine@digital-maturity-assessor.iam.gserviceaccount.com,"
        "claude-deployer@digital-maturity-assessor.iam.gserviceaccount.com",
    ).split(",") if s.strip()
}
# Any service account OF THIS PROJECT is an operator identity: under the
# IAM posture each was granted run.invoker individually, and enumerating
# them in an allowlist just breaks the next legitimate one (measured
# 2026-08-20: the deployer container's active SA 403'd the service path).
PROJECT_SA_SUFFIX = os.environ.get(
    "DMA_SA_SUFFIX", "@digital-maturity-assessor.iam.gserviceaccount.com")
# gcloud's own OAuth client — the audience of a bare
# `gcloud auth print-identity-token`. Accepted for DOMAIN humans only.
GCLOUD_CLI_AUD = "32555940559.apps.googleusercontent.com"
TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
_CACHE_TTL = 300


def _is_domain_user(email: str, verified) -> bool:
    ok_verified = verified in (True, "true", "True", 1)
    return bool(email) and email.lower().endswith(f"@{DOMAIN}") and ok_verified


def check_identity(claims: dict, rung: str, *, host: str,
                   oauth_client_id: str) -> tuple:
    """(allowed, status, reason) — pure policy over verified claims.

    `claims` are TRUSTED here: rung A claims come out of signature
    verification, rung B claims out of Google's tokeninfo. This function
    only decides, so the decision table is testable without any crypto.
    """
    email = (claims.get("email") or "").lower()
    verified = claims.get("email_verified")
    aud = claims.get("aud") or ""
    if rung == "A":
        service_auds = {f"https://{host}",
                        os.environ.get("MCP_SERVICE_URL", "").rstrip("/")}
        if email in ALLOWED_SAS or email.endswith(PROJECT_SA_SUFFIX):
            if aud in service_auds:
                return True, 200, f"service-account {email}"
            return False, 403, ("service-account token audience must be the "
                                "service URL")
        if _is_domain_user(email, verified):
            if aud in service_auds or aud == GCLOUD_CLI_AUD:
                return True, 200, f"domain user {email}"
            return False, 403, "unrecognised token audience for domain user"
        return False, 403, (f"identity not authorised: only @{DOMAIN} "
                            "accounts and the routine service account")
    # rung B — OAuth access token from the pre-registered client
    if not oauth_client_id:
        return False, 401, ("OAuth sign-in not configured on the server "
                            "(dmai-oauth-client-id secret not wired)")
    if aud != oauth_client_id:
        return False, 403, "token was not minted through the DMA Insights " \
                           "OAuth client"
    if not _is_domain_user(email, verified):
        return False, 403, f"only verified @{DOMAIN} accounts are authorised"
    return True, 200, f"oauth user {email}"


def _default_verify_jwt(token: str, audiences: list):
    """Rung A verifier: Google-signed JWT → claims. Signature, expiry,
    issuer AND audience-membership are enforced by google-auth against
    Google's published certs (audience=None does NOT reliably skip the
    check across google-auth versions — measured live 2026-08-20, 'Invalid
    audience' on a valid service token — so the accepted list is passed
    explicitly); policy above then refines WHICH audience each identity
    class may use."""
    import google.auth.transport.requests
    import google.oauth2.id_token
    request = google.auth.transport.requests.Request()
    # One verify per candidate audience STRING: the deployed google-auth
    # lineage predates list-audience support in verify_token (measured live
    # 2026-08-20 on revision 00092 — a valid token failed against a list),
    # and audience=None does not reliably skip. Trying each string is
    # version-proof; the first success returns, and the failure raised is
    # the last audience's, which names the real mismatch.
    last = None
    for aud in audiences:
        try:
            return google.oauth2.id_token.verify_token(
                token, request, audience=aud,
                certs_url="https://www.googleapis.com/oauth2/v3/certs")
        except Exception as e:                              # noqa: BLE001
            last = e
    raise last


def _default_lookup_access_token(token: str):
    """Rung B verifier: opaque token → tokeninfo claims (aud, email,
    email_verified, exp). Google refuses invalid/expired tokens with 4xx."""
    url = f"{TOKENINFO}?{urllib.parse.urlencode({'access_token': token})}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


class OAuthGate:
    """ASGI wrapper enforcing the two-rung identity policy above."""

    def __init__(self, inner, capability_token: str,
                 verify_jwt=None, lookup_access_token=None):
        self.inner = inner
        self.capability_token = capability_token
        self.verify_jwt = verify_jwt or _default_verify_jwt
        self.lookup_access_token = (lookup_access_token
                                    or _default_lookup_access_token)
        self._cache: dict = {}   # sha256(token) -> (expiry, allowed, reason)

    # ── helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _header(scope, name: bytes) -> str:
        for k, v in scope.get("headers") or ():
            if k == name:
                return v.decode("latin-1").strip()
        return ""

    # A browser-based client (which is what the claude.ai dialog is) cannot
    # read a 401 challenge it is not allowed to see: without
    # Access-Control-Expose-Headers the WWW-Authenticate header is invisible
    # to the JavaScript that has to follow it, and the whole discovery chain
    # silently stops at "authorization failed".
    CORS = [
        (b"access-control-allow-origin", b"*"),
        (b"access-control-allow-headers",
         b"authorization, content-type, mcp-protocol-version, mcp-session-id, "
         b"x-dma-path-token, last-event-id"),
        (b"access-control-allow-methods", b"GET, POST, DELETE, OPTIONS"),
        (b"access-control-expose-headers",
         b"WWW-Authenticate, mcp-session-id, mcp-protocol-version"),
        (b"access-control-max-age", b"86400"),
    ]

    async def _send_json(self, send, status: int, body: dict,
                         extra_headers=()):
        raw = json.dumps(body).encode()
        headers = [(b"content-type", b"application/json"),
                   (b"cache-control", b"no-store"),
                   (b"content-length", str(len(raw)).encode())]
        headers.extend(self.CORS)
        headers.extend(extra_headers)
        await send({"type": "http.response.start", "status": status,
                    "headers": headers})
        await send({"type": "http.response.body", "body": raw})

    async def _send_raw(self, send, status: int, headers, body: bytes):
        hdrs = list(headers) + list(self.CORS) + [
            (b"content-length", str(len(body)).encode())]
        await send({"type": "http.response.start", "status": status,
                    "headers": hdrs})
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _body(receive) -> bytes:
        chunks = []
        while True:
            msg = await receive()
            chunks.append(msg.get("body") or b"")
            if not msg.get("more_body"):
                break
        return b"".join(chunks)

    async def _authorization_server(self, scope, receive, send, path, base):
        """The public OAuth surface. Returns True when it handled the request.

        Every path here is deliberately unauthenticated: they are how a
        client LEARNS to authenticate. Answering them with a bearer
        challenge — which this service did until 2026-08-20 — makes the
        connector undiscoverable and is the defect this method exists to
        close.
        """
        method = scope.get("method", "GET").upper()
        query = urllib.parse.parse_qs(
            (scope.get("query_string") or b"").decode(), keep_blank_values=True)
        params = {k: v[0] for k, v in query.items()}

        if path in ("/.well-known/oauth-authorization-server",
                    "/.well-known/oauth-authorization-server/mcp",
                    "/.well-known/openid-configuration",
                    "/.well-known/openid-configuration/mcp"):
            await self._send_json(send, 200, oauth_as.as_metadata(base))
            return True
        if path in ("/.well-known/oauth-protected-resource",
                    "/.well-known/oauth-protected-resource/mcp"):
            await self._send_json(send, 200, oauth_as.resource_metadata(base))
            return True
        if path == "/register" and method == "POST":
            try:
                meta = json.loads(await self._body(receive) or b"{}")
            except ValueError:
                await self._send_json(send, 400, {
                    "error": "invalid_client_metadata",
                    "error_description": "body is not JSON"})
                return True
            reg = oauth_as.register_client(meta)
            await self._send_json(send, 400 if "error" in reg else 201, reg)
            return True
        if path == "/authorize" and method == "GET":
            status, headers, body = oauth_as.authorize_redirect(params, base)
            await self._send_raw(send, status, headers, body)
            return True
        if path == oauth_as.CALLBACK_PATH and method == "GET":
            status, headers, body = oauth_as.callback(params, base)
            await self._send_raw(send, status, headers, body)
            return True
        if path == "/token" and method == "POST":
            raw = (await self._body(receive)).decode("utf-8", "replace")
            form = {k: v[0] for k, v in
                    urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
            status, payload = oauth_as.token_grant(
                form, self._header(scope, b"authorization"))
            await self._send_json(send, status, payload)
            return True
        return False

    def _base(self, host: str) -> str:
        """The canonical origin, so every document and every redirect agrees.

        Cloud Run answers on more than one hostname; metadata that varied by
        which one the client happened to use would send a client to endpoints
        it never discovered, and would break the one redirect URI Google has
        registered.
        """
        return (os.environ.get("MCP_SERVICE_URL", "").rstrip("/")
                or f"https://{host}")

    def _metadata(self, host: str) -> dict:
        return oauth_as.resource_metadata(self._base(host))

    # ── the gate ────────────────────────────────────────────────────────
    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.inner(scope, receive, send)
            return
        host = self._header(scope, b"host") or "localhost"
        path = (scope.get("path") or "").rstrip("/") or "/"
        base = self._base(host)

        if scope.get("method", "").upper() == "OPTIONS":
            await self._send_raw(send, 204, [], b"")
            return

        if await self._authorization_server(scope, receive, send, path, base):
            return

        challenge = (b"www-authenticate",
                     f'Bearer resource_metadata='
                     f'"https://{host}/.well-known/oauth-protected-resource"'
                     .encode())
        auth = self._header(scope, b"authorization")
        if not auth.lower().startswith("bearer "):
            await self._send_json(send, 401,
                                  {"error": "unauthorized",
                                   "detail": "bearer token required"},
                                  [challenge])
            return
        token = auth[7:].strip()
        key = hashlib.sha256(token.encode()).hexdigest()
        now = time.time()
        cached = self._cache.get(key)
        if cached and cached[0] > now:
            allowed, status, reason = cached[1], cached[2], cached[3]
        else:
            allowed, status, reason = self._decide(token, host)
            if len(self._cache) > 1024:
                self._cache.clear()
            self._cache[key] = (now + _CACHE_TTL, allowed, status, reason)
        if not allowed:
            await self._send_json(
                send, status, {"error": "forbidden" if status == 403
                               else "unauthorized", "detail": reason},
                [challenge] if status == 401 else [])
            return

        # Authenticated. An OAuth or domain caller needs no capability
        # token — identity IS the authorisation — so a bare /mcp routes to
        # the capability path unless the header wrapper will do it.
        if (path == "/mcp"
                and not self._header(scope, b"x-dma-path-token")):
            scope = dict(scope)
            scope["path"] = f"/mcp/{self.capability_token}"
            scope["raw_path"] = scope["path"].encode("latin-1")
        await self.inner(scope, receive, send)

    def _decide(self, token: str, host: str) -> tuple:
        oauth_client_id = os.environ.get("OAUTH_CLIENT_ID", "").strip()
        # Rung C first: an HMAC verify is cheap, deterministic and cannot be
        # confused with anything else — a token either carries our signature
        # or it does not, which is a better discriminator than token shape
        # (Google's opaque tokens and ours both contain dots).
        ours = oauth_as.verify(token, typ="at")
        if ours is not None:
            email = (ours.get("sub") or "").lower()
            if email.endswith(f"@{DOMAIN}"):
                return True, 200, f"oauth user {email} (issued here)"
            return False, 403, (f"token subject {email!r} is not an "
                                f"@{DOMAIN} account")
        if token.count(".") == 2:
            audiences = [f"https://{host}", GCLOUD_CLI_AUD]
            svc = os.environ.get("MCP_SERVICE_URL", "").rstrip("/")
            if svc:
                audiences.append(svc)
            try:
                claims = self.verify_jwt(token, audiences)
            except Exception as e:                          # noqa: BLE001
                return False, 401, f"id token failed verification: {e}"
            return check_identity(claims, "A", host=host,
                                  oauth_client_id=oauth_client_id)
        try:
            claims = self.lookup_access_token(token)
        except Exception:
            return False, 401, "access token was refused by Google tokeninfo"
        return check_identity(claims, "B", host=host,
                              oauth_client_id=oauth_client_id)
