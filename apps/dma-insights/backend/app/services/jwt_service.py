"""JWT issuance + verification (RS256). Used by auth router and `deps.get_current_user`.

Private key source priority:
  1. `JWT_PRIVATE_KEY_PEM` env var — full PEM content. Set in prod via
     a Cloud Run env that reads from Secret Manager.
  2. File at `JWT_PRIVATE_KEY_PATH` (settings.jwt_private_key_path) —
     dev path; default `./local-data/jwt-private.pem`.
  3. Ephemeral keypair generated in memory (tests + dev only).

The public key is ALWAYS derived from the private key at boot — there
is no separate public-key file or env var. This eliminates the
two-keys-must-match-or-tokens-fail-validation footgun. The private
key is the only secret.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
from functools import lru_cache
from typing import Any

import jwt
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException, status

from app.config import get_settings

log = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _private_key() -> bytes:
    """Load the RS256 private key as PEM bytes.

    Production: `JWT_PRIVATE_KEY_PEM` env var, populated by Cloud Run
    from a Secret Manager value_source. Cloud Run env values handle
    multiline content correctly when sourced this way.

    Dev: file on disk at `settings.jwt_private_key_path`.

    Tests / fallback: ephemeral keypair (regenerated per process).
    """
    pem_inline = os.environ.get("JWT_PRIVATE_KEY_PEM", "").strip()
    if pem_inline:
        return pem_inline.encode("utf-8") if isinstance(pem_inline, str) else pem_inline

    s = get_settings()
    path = pathlib.Path(s.jwt_private_key_path)
    if path.exists():
        return path.read_bytes()

    return _generate_ephemeral_key()


@lru_cache(maxsize=1)
def _public_key() -> bytes:
    """Public key derived from `_private_key()` — no separate source.

    Loading the private key and exporting its public half is cheap
    (~1ms) and lru_cached, so it runs once per process.
    """
    priv = serialization.load_pem_private_key(_private_key(), password=None)
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


@lru_cache(maxsize=1)
def _generate_ephemeral_key() -> bytes:
    """Generate an ephemeral RSA private key (only when nothing else is configured).

    Persisted to `jwt_private_key_path` only when
    `DMA_INSIGHTS_PERSIST_DEV_KEY=1` — so re-runs of dev get a stable
    key without committing it to the repo.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    if os.environ.get("DMA_INSIGHTS_PERSIST_DEV_KEY", "0") == "1":
        s = get_settings()
        pathlib.Path(s.jwt_private_key_path).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(s.jwt_private_key_path).write_bytes(priv_pem)
    return priv_pem


def issue_token(*, user_id: str, email: str, role: str, name: str = "") -> str:
    s = get_settings()
    now = dt.datetime.now(tz=dt.UTC)
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "email": email,
        "role": role,
        "name": name,
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(hours=s.jwt_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, _private_key(), algorithm="RS256")


def verify_token(token: str) -> dict[str, Any]:
    """Verify a session JWT.

    Security: the HTTP response detail MUST be a constant string. The
    underlying PyJWT error message (e.g. "Signature has expired",
    "Invalid signature", "Token missing 'aud' claim") is forensically
    useful but reveals the exact failure mode to an attacker probing
    a stolen/forged token. Detail is therefore stripped to
    "Invalid session"; the actual error is structlogged for ops.

    State branches:
      ok           → payload returned with the 4 claim fields
      expired      → 401 "Invalid session" (log: "jwt.expired")
      bad_sig      → 401 "Invalid session" (log: "jwt.bad_signature")
      bad_aud/iss  → 401 "Invalid session" (log: "jwt.claim_mismatch")
      malformed    → 401 "Invalid session" (log: "jwt.decode_failed")
    """
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            _public_key(),
            algorithms=["RS256"],
            issuer=s.jwt_issuer,
            audience=s.jwt_audience,
        )
    except jwt.ExpiredSignatureError as e:
        log.info("jwt.expired", err=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        ) from e
    except jwt.InvalidSignatureError as e:
        log.warning("jwt.bad_signature", err=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        ) from e
    except (jwt.InvalidAudienceError, jwt.InvalidIssuerError) as e:
        log.warning("jwt.claim_mismatch", err=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        ) from e
    except jwt.PyJWTError as e:
        log.warning("jwt.decode_failed", err=str(e), err_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        ) from e
    return {
        "user_id": payload["user_id"],
        "email": payload["email"],
        "role": payload["role"],
        "name": payload.get("name", ""),
    }

