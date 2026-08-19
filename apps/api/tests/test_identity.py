"""Who a write is attributed to (MEM-0016).

The measured defect: both write endpoints took `actor` from a query
parameter. Until 2026-08-08 the annotation write failed for everyone twice
over and it did not matter; the morning both failures were closed, any
principal holding `run.invoker` on `dmai-api` could name any allowlisted
actor and have the verdict attributed to them. These rows feed the findings
memory and, through it, skill refinement — a forged verdict teaches.

What is asserted here:

1. No assertion, no write. There is no fallback to the query parameter and no
   environment flag that restores one.
2. A real ES256 signature is required — verified against a key set, with the
   issuer and the audience pinned. Every one of those is exercised by
   FORGING the corresponding failure with a real key, not by reading the code.
3. `actor` naming somebody other than the verified user is refused, not
   quietly corrected. Naming the verified user is allowed through.
4. The routes read the verified identity and not the parameter — asserted
   against main.py's source, so re-introducing `actor_email=actor` fails.

The JWK set is injected, so these run offline against a keypair generated in
the test rather than against Google's live endpoint.
"""
import json
import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import ec   # noqa: E402

from dma_api.identity import (ActorError, ISSUER, reset_jwks_cache,  # noqa: E402
                              verified_actor, verify_assertion)

AUD = "/projects/1234/locations/us-central1/services/dmai-web"
KID = "test-key-1"
EMAIL = "mishley.otiende@zennify.com"

_key = ec.generate_private_key(ec.SECP256R1())
_other_key = ec.generate_private_key(ec.SECP256R1())


def _jwk(private, kid=KID):
    """The public half as a JWK, the shape Google publishes.

    Built by hand rather than through `ECAlgorithm.to_jwk`, which emits a
    31-byte coordinate whenever the point has a leading zero byte — and
    `from_jwk` then refuses its own library's output with InvalidKeyError.
    A fresh key is drawn at module scope every run, so roughly one CI run
    in sixty-four failed all four verification tests at once with no code
    change anywhere (measured: three red runs on 2026-08-19, the failing
    JWK's y at 42 base64url chars in the log). RFC 7518 §6.2.1.2 requires
    exactly ceil(key_size/8) octets, zero-padded; this does that.
    """
    import base64
    nums = private.public_key().public_numbers()

    def b64(n):
        return base64.urlsafe_b64encode(
            n.to_bytes(32, "big")).rstrip(b"=").decode()

    return {"kty": "EC", "crv": "P-256", "x": b64(nums.x), "y": b64(nums.y),
            "kid": kid, "alg": "ES256", "use": "sig"}


def _fetch(keys=None):
    ks = keys if keys is not None else [_jwk(_key)]
    return lambda: {"keys": ks}


def _token(key=None, kid=KID, aud=AUD, iss=ISSUER, email=EMAIL, exp=None,
           iat=None, alg="ES256", **extra):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "email": email, "sub": "accounts.google.com:1",
              "exp": exp if exp is not None else now + 600,
              "iat": iat if iat is not None else now, **extra}
    return jwt.encode(claims, key or _key, algorithm=alg,
                      headers={"kid": kid})


class _Req:
    def __init__(self, **headers):
        self.headers = {k.lower(): v for k, v in headers.items()}


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_jwks_cache()
    yield
    reset_jwks_cache()


# ── no assertion, no write ─────────────────────────────────────────────
def test_a_missing_assertion_refuses_the_write():
    with pytest.raises(ActorError) as e:
        verify_assertion(None, audience=AUD, fetch=_fetch())
    assert e.value.status == 401 and e.value.code == "actor_unverified"
    assert "x-goog-iap-jwt-assertion" in e.value.detail


def test_the_query_parameter_alone_is_never_an_identity():
    """The whole defect, in one test: `?actor=` with nothing to verify it."""
    with pytest.raises(ActorError) as e:
        verified_actor(_Req(), "dma@zennify.com", audience=AUD, fetch=_fetch())
    assert e.value.status == 401


def test_no_audience_configured_refuses_rather_than_skipping_the_check():
    with pytest.raises(ActorError) as e:
        verify_assertion(_token(), audience="", fetch=_fetch())
    assert e.value.code == "actor_unverifiable" and e.value.status == 500


def test_there_is_no_flag_that_turns_verification_off():
    src = (ROOT / "apps" / "api" / "dma_api" / "identity.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    # os.environ is read for exactly one name: the audience to pin against.
    assert re.findall(r"os\.environ\.get\(\"([^\"]+)\"", body) == ["IAP_AUDIENCE"]


# ── the signature, and every claim that binds it ───────────────────────
def test_a_valid_assertion_names_the_person():
    out = verify_assertion(_token(), audience=AUD, fetch=_fetch())
    assert out["email"] == EMAIL


def test_a_signature_from_another_key_is_refused():
    with pytest.raises(ActorError) as e:
        verify_assertion(_token(key=_other_key), audience=AUD, fetch=_fetch())
    assert e.value.code == "actor_unverified"


def test_a_key_that_is_not_in_googles_set_is_refused():
    with pytest.raises(ActorError) as e:
        verify_assertion(_token(key=_other_key, kid="not-published"),
                         audience=AUD, fetch=_fetch())
    assert "not in Google's published IAP key set" in e.value.detail


def test_an_assertion_minted_for_another_service_is_refused():
    other = "/projects/1234/locations/us-central1/services/somebody-else"
    with pytest.raises(ActorError):
        verify_assertion(_token(aud=other), audience=AUD, fetch=_fetch())


def test_a_foreign_issuer_is_refused():
    with pytest.raises(ActorError):
        verify_assertion(_token(iss="https://evil.example"), audience=AUD,
                         fetch=_fetch())


def test_an_expired_assertion_is_refused():
    with pytest.raises(ActorError):
        verify_assertion(_token(exp=int(time.time()) - 10), audience=AUD,
                         fetch=_fetch())


def test_an_assertion_from_the_future_is_refused():
    """An `iat` the issuer's clock could not have produced."""
    with pytest.raises(ActorError) as e:
        verify_assertion(_token(iat=int(time.time()) + 3600), audience=AUD,
                         fetch=_fetch())
    assert e.value.code == "actor_unverified"


def test_an_assertion_with_no_iat_is_refused():
    now = int(time.time())
    tok = jwt.encode({"iss": ISSUER, "aud": AUD, "email": EMAIL,
                      "exp": now + 600}, _key, algorithm="ES256",
                     headers={"kid": KID})
    with pytest.raises(ActorError):
        verify_assertion(tok, audience=AUD, fetch=_fetch())


def test_an_assertion_with_no_email_claim_is_refused():
    now = int(time.time())
    tok = jwt.encode({"iss": ISSUER, "aud": AUD, "exp": now + 600, "iat": now},
                     _key, algorithm="ES256", headers={"kid": KID})
    with pytest.raises(ActorError):
        verify_assertion(tok, audience=AUD, fetch=_fetch())


def test_an_unsigned_algorithm_is_refused():
    """`alg: none` is the classic JWT forgery; ES256 is required by name."""
    tok = jwt.encode({"iss": ISSUER, "aud": AUD, "email": EMAIL,
                      "exp": int(time.time()) + 600}, key="",
                     algorithm="none", headers={"kid": KID})
    with pytest.raises(ActorError) as e:
        verify_assertion(tok, audience=AUD, fetch=_fetch())
    assert "ES256" in e.value.detail


def test_a_token_that_is_not_a_jwt_is_refused_without_raising_a_type_error():
    with pytest.raises(ActorError) as e:
        verify_assertion("not.a.jwt", audience=AUD, fetch=_fetch())
    assert e.value.code == "actor_unverified"


def test_no_refusal_ever_echoes_the_token():
    tok = _token(key=_other_key)
    with pytest.raises(ActorError) as e:
        verify_assertion(tok, audience=AUD, fetch=_fetch())
    assert tok not in e.value.detail and tok[:32] not in e.value.detail


# ── the parameter is compared, never believed ──────────────────────────
def test_an_actor_naming_somebody_else_is_refused_not_corrected():
    req = _Req(**{"x-goog-iap-jwt-assertion": _token()})
    with pytest.raises(ActorError) as e:
        verified_actor(req, "dma@zennify.com", audience=AUD, fetch=_fetch())
    assert e.value.status == 403 and e.value.code == "actor_mismatch"
    assert "never a grant" in e.value.detail


def test_an_actor_that_agrees_with_the_verified_user_passes():
    req = _Req(**{"x-goog-iap-jwt-assertion": _token()})
    assert verified_actor(req, EMAIL.upper(), audience=AUD,
                          fetch=_fetch()) == EMAIL


def test_no_actor_parameter_at_all_is_the_normal_case():
    req = _Req(**{"x-goog-iap-jwt-assertion": _token()})
    assert verified_actor(req, None, audience=AUD, fetch=_fetch()) == EMAIL


# ── the routes use it ──────────────────────────────────────────────────
def test_both_write_routes_take_their_actor_from_the_verified_identity():
    src = (ROOT / "apps" / "api" / "dma_api" / "main.py").read_text(encoding="utf-8")
    assert "actor_email = verified_actor(request, actor)" in src, \
        "the annotation route must verify, not trust"
    assert "actor_email=actor_email" in src
    assert "actor_email=actor," not in src, \
        "the query parameter must not reach annotate_insight"
    # the alert route resolves the VERIFIED email to a user id and passes that
    assert "actor=str(row[0])" in src
    assert re.search(r"alert_act\(\s*\n?\s*cur, alert_id, body=body, "
                     r"idempotency_key=key, actor=actor\b", src) is None, \
        "the alert route must not pass the query parameter as the actor"


def test_a_key_with_a_leading_zero_coordinate_still_verifies():
    """The flake, pinned so it cannot come back as weather. One key in ~64
    has a coordinate under 2^248; RFC 7518 requires the JWK coordinate
    zero-padded to 32 octets regardless, and the fixture must produce that
    for EVERY key — a fixture that fails one run in sixty-four is a
    fixture that teaches people to re-run CI instead of reading it."""
    for _ in range(4000):
        k = ec.generate_private_key(ec.SECP256R1())
        nums = k.public_key().public_numbers()
        if nums.x >> 248 == 0 or nums.y >> 248 == 0:
            break
    else:
        pytest.skip("no leading-zero coordinate in 4000 draws (p ~ 1e-14)")
    d = _jwk(k)
    assert len(d["x"]) == 43 and len(d["y"]) == 43, (
        "coordinates must be exactly 32 zero-padded octets (43 base64url "
        "chars); an unpadded coordinate is refused by PyJWK.from_dict")
    reset_jwks_cache()
    claims = verify_assertion(_token(key=k), audience=AUD,
                              fetch=_fetch([_jwk(k)]))
    assert claims["email"] == EMAIL
