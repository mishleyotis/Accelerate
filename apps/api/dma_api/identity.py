"""Who is writing — verified here, never asserted by the caller.

## The defect this closes

Both of the API's write endpoints took their actor from a QUERY PARAMETER:

    POST /v1/entities/{id}/insights/{ic_id}/annotation?actor=dma@zennify.com
    POST /v1/alerts/{id}/actions?actor=<user uuid>

The intended caller is the web BFF, which forwards the signed-in session's
email, and nothing in the API enforced that. Until 2026-08-08 it did not
matter, because the annotation write failed for everyone twice over — the
actor resolved to no user (403 `unknown_actor`) and, behind that, svc_api held
no grant on `entities` so the anchor query would have raised 42501 anyway.
Both were closed that morning. From that moment, any principal holding
`roles/run.invoker` on `dmai-api` could name any allowlisted actor and have
the verdict attributed to them.

The exposure was bounded — that binding is `dmai-web` only — but attribution
a caller supplies is not attribution. These rows feed the findings memory and,
through it, skill refinement: a forged verdict does not merely mislabel a row,
it teaches.

## What is trusted instead

The IAP assertion. Cloud Run's integrated IAP fronts `dmai-web` (enabled in
production, `run.googleapis.com/iap-enabled=true`) and mints a signed
ES256 JWT naming the human on every request. `apps/web/lib/iap.js` already
verifies it at the web tier; this module verifies it AGAIN, independently, in
the service that performs the write:

  · ES256 over Google's published IAP JWK set, matched by `kid`
  · issuer `https://cloud.google.com/iap`
  · `exp` in the future, `iat` not in the future
  · `aud` equal to `IAP_AUDIENCE` exactly — the audience is what stops an
    assertion minted for some other service being replayed at this one

Two independent verifications rather than one is the point: the API must not
have to trust that its caller checked. The platform's `run.invoker` binding
proves the request came from `dmai-web`; the assertion proves which person is
behind it. Neither alone is enough and the API now requires both.

## What it refuses

A missing assertion, an invalid one, or a configuration with no
`IAP_AUDIENCE` — all 401, all naming what is missing. There is NO fallback to
the query parameter and no environment flag that restores one: a switch that
disables identity verification is a switch that ships enabled. A caller that
supplies `actor` AND a valid assertion naming somebody else is refused rather
than silently corrected, because a caller naming another person is exactly the
thing being defended against; a caller that supplies its own verified email is
accepted, since that is a request that agrees with the grant.

## Residual, stated rather than hidden

A principal that already holds `run.invoker` on `dmai-api` and can CAPTURE a
live assertion could replay it within its lifetime. Closing that needs the
assertion bound per-request (a nonce or a request hash), which IAP does not
mint. The exposure it leaves is strictly smaller than the one it replaces: an
attacker must obtain a real user's live assertion rather than type an email.
"""
from __future__ import annotations

import os
import time

ISSUER = "https://cloud.google.com/iap"
JWKS_URL = "https://www.gstatic.com/iap/verify/public_key-jwk"
_JWKS_TTL = 12 * 60 * 60

_cache: dict = {"keys": None, "at": 0.0}


class ActorError(Exception):
    """A write that cannot be attributed. Carries the API error shape."""

    def __init__(self, code: str, detail: str, status: int = 401):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


def _jwks(fetch=None) -> list:
    """Google's IAP signing keys, cached. `fetch` is injectable so the tests
    verify a real signature without reaching the network."""
    now = time.time()
    if _cache["keys"] is not None and now - _cache["at"] < _JWKS_TTL:
        return _cache["keys"]
    if fetch is None:
        import json
        import urllib.request
        with urllib.request.urlopen(JWKS_URL, timeout=5) as r:
            body = json.loads(r.read())
    else:
        body = fetch()
    _cache["keys"] = body.get("keys") or []
    _cache["at"] = now
    return _cache["keys"]


def reset_jwks_cache() -> None:
    _cache["keys"], _cache["at"] = None, 0.0


def verify_assertion(token: str | None, *, audience: str | None = None,
                     fetch=None, now: float | None = None) -> dict:
    """{email, sub} for a valid IAP assertion. Raises ActorError otherwise.

    Every refusal names what failed. An assertion that cannot be attributed
    is not a degraded success — it is the absence of an identity, and this
    function has no way to return one.
    """
    audience = audience if audience is not None else os.environ.get("IAP_AUDIENCE")
    if not audience:
        raise ActorError(
            "actor_unverifiable",
            "IAP_AUDIENCE is not configured on this service, so an assertion "
            "cannot be bound to it; the write is refused rather than "
            "attributed to an unverified caller", status=500)
    if not token:
        raise ActorError(
            "actor_unverified",
            "this write must be attributable to a verified person: forward "
            "the IAP assertion in x-goog-iap-jwt-assertion. A caller-supplied "
            "`actor` parameter is not an identity and is no longer accepted")

    import jwt
    from jwt import PyJWK

    try:
        header = jwt.get_unverified_header(token)
    except Exception:                                         # noqa: BLE001
        raise ActorError("actor_unverified", "the assertion is not a JWT")
    if header.get("alg") != "ES256":
        raise ActorError("actor_unverified",
                         f"IAP assertions are ES256; got {header.get('alg')!r}")
    jwk = next((k for k in _jwks(fetch) if k.get("kid") == header.get("kid")), None)
    if jwk is None:
        raise ActorError("actor_unverified",
                         "the assertion names a signing key that is not in "
                         "Google's published IAP key set")
    try:
        claims = jwt.decode(
            token, PyJWK.from_dict(jwk).key, algorithms=["ES256"],
            audience=audience, issuer=ISSUER,
            options={"require": ["exp", "iss", "aud", "email"]})
    except Exception as e:                                    # noqa: BLE001
        # The class and the message, never the token.
        raise ActorError("actor_unverified",
                         f"the assertion did not verify: {type(e).__name__}")

    # PyJWT checks exp; iat in the future is a clock the issuer does not have.
    now = now if now is not None else time.time()
    iat = claims.get("iat")
    if isinstance(iat, (int, float)) and iat > now + 300:
        raise ActorError("actor_unverified",
                         "the assertion is issued more than five minutes in "
                         "the future")
    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise ActorError("actor_unverified",
                         "the assertion carries no email claim")
    return {"email": email, "sub": claims.get("sub")}


def verified_actor(request, claimed: str | None = None, *,
                   audience: str | None = None, fetch=None) -> str:
    """The email this write is attributed to, from the request's assertion.

    `claimed` is whatever the caller put in `?actor=`. It is never the answer.
    It is compared: agreeing with the verified identity is a request that
    matches the grant and is allowed through; naming somebody else is refused,
    because that is the attack rather than a mistake worth correcting quietly.
    """
    token = request.headers.get("x-goog-iap-jwt-assertion")
    ident = verify_assertion(token, audience=audience, fetch=fetch)
    if claimed and claimed.strip().lower() != ident["email"]:
        raise ActorError(
            "actor_mismatch",
            "the `actor` parameter names somebody other than the verified "
            "signed-in user; a client's value is a request, never a grant",
            status=403)
    return ident["email"]
