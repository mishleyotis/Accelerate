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

Two rungs, matching the two kinds of caller:

  A · Google-signed ID TOKEN (a JWT) — the service path. The plugin's
      stdio proxy and gcp_token.py mint these with the service URL as
      audience; the routine service account is allowlisted. A @zennify.com
      person with plain `gcloud auth print-identity-token` also lands here
      (their token's audience is the gcloud CLI's own client id, accepted
      for DOMAIN users only — a service account must name this service).
  B · Google OAuth ACCESS TOKEN (opaque, ya29.…) — the claude.ai path.
      claude.ai obtains it from Google using the pre-registered OAuth
      client (Secret Manager: dmai-oauth-client-id/-secret; the dialog's
      Client ID + Client Secret fields). Validated against Google's
      tokeninfo endpoint: audience must be OUR client id — a token minted
      through anyone else's app is refused, which is what keeps this from
      being a token-passthrough hole — and the email must be a verified
      @zennify.com address. Verdicts are cached briefly by token hash.

Discovery: /.well-known/oauth-protected-resource is served UNAUTHENTICATED
(RFC 9728) naming accounts.google.com as the authorization server, and every
401 carries WWW-Authenticate with resource_metadata — that header is how the
claude.ai dialog finds the flow. Google is the authorization server; this
app never issues tokens and never sees the client secret (the audience
check needs only the client ID).

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

    async def _send_json(self, send, status: int, body: dict,
                         extra_headers=()):
        raw = json.dumps(body).encode()
        headers = [(b"content-type", b"application/json"),
                   (b"content-length", str(len(raw)).encode())]
        headers.extend(extra_headers)
        await send({"type": "http.response.start", "status": status,
                    "headers": headers})
        await send({"type": "http.response.body", "body": raw})

    def _metadata(self, host: str) -> dict:
        return {
            "resource": f"https://{host}/mcp",
            "resource_name": "DMA Insights",
            "authorization_servers": ["https://accounts.google.com"],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["openid", "email", "profile"],
        }

    # ── the gate ────────────────────────────────────────────────────────
    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.inner(scope, receive, send)
            return
        host = self._header(scope, b"host") or "localhost"
        path = (scope.get("path") or "").rstrip("/")

        if path in ("/.well-known/oauth-protected-resource",
                    "/.well-known/oauth-protected-resource/mcp"):
            await self._send_json(send, 200, self._metadata(host))
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
