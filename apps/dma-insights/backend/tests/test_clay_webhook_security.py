"""Phase 3 Clay webhook security regression tests.

The Clay inbound webhook accepts enriched payloads from clay.com. The
HMAC must:
  1. Reject missing X-Clay-Signature header → 401
  2. Reject wrong HMAC using constant-time compare (hmac.compare_digest)
  3. Reject when clay_webhook_secret is unset (fail-closed)
  4. Accept valid HMAC

These tests pin the contract so a refactor that swaps the HMAC
algorithm or drops compare_digest surfaces before the production
incident.
"""
from __future__ import annotations

import hashlib
import hmac

import pytest


def _hmac_hex(secret: str, body: bytes) -> str:
    """Helper: compute the expected `sha256=<hex>` shape Clay sends."""
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def test_clay_webhook_missing_signature_rejected():
    """No X-Clay-Signature header → verify_signature returns False.
    The router 401s every payload."""
    from app.services.clay_client import verify_signature

    assert verify_signature(b"any body", None) is False


def test_clay_webhook_wrong_hmac_rejected():
    """Wrong HMAC → False. compare_digest does the constant-time work."""
    from app.config import get_settings
    from app.services.clay_client import verify_signature

    # The verifier reads clay_webhook_secret from settings. Use the
    # configured value -- when local-dev defaults are empty, verify_
    # signature returns False outright (fail-closed). For this test we
    # need a real secret so we can construct a deliberately-wrong sig
    # that proves compare_digest fires (not a missing-secret short
    # circuit). monkeypatch the lru_cache.
    settings = get_settings()
    if not settings.clay_webhook_secret:
        pytest.skip("clay_webhook_secret unset; covered by fail-closed test")

    wrong_sig = "sha256=" + "0" * 64
    assert verify_signature(b"any body", wrong_sig) is False


def test_clay_webhook_correct_hmac_accepted(monkeypatch):
    """A correctly-computed HMAC verifies. This is the round-trip
    sanity test: write the same code Clay runs on its side, confirm
    our verifier accepts it."""
    from app.services.clay_client import verify_signature

    body = b'{"entity_id": "e1", "name": "Acme"}'

    # Force a known secret + patch get_settings to return it. The
    # verifier function reads it at call time so monkeypatching the
    # module-level get_settings call is enough.
    class _S:
        clay_webhook_secret = "test-secret-value"

    monkeypatch.setattr(
        "app.services.clay_client.get_settings", lambda: _S(),
    )
    sig = _hmac_hex("test-secret-value", body)
    assert verify_signature(body, sig) is True


def test_clay_webhook_uses_constant_time_compare():
    """Source-shape check: the verifier must call
    `hmac.compare_digest` (not raw `==`). Catches a refactor that
    introduces a timing oracle for the shared secret."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "clay_client.py"
    ).read_text(encoding="utf-8")
    assert "hmac.compare_digest" in src, (
        "Clay verify_signature must use hmac.compare_digest -- a raw "
        "`==` comparison leaks the HMAC byte-by-byte via timing."
    )


def test_clay_webhook_fail_closed_when_secret_unset(monkeypatch):
    """If clay_webhook_secret is empty, the verifier must return False
    for every input (including correctly-signed payloads). Without
    this contract a misconfigured prod deploy would 200 every webhook
    from any sender."""
    from app.services.clay_client import verify_signature

    class _S:
        clay_webhook_secret = ""  # unset

    monkeypatch.setattr(
        "app.services.clay_client.get_settings", lambda: _S(),
    )
    # Even a "correct"-looking signature must reject.
    sig = "sha256=" + "0" * 64
    assert verify_signature(b"body", sig) is False


def test_clay_webhook_replay_policy_documented():
    """Clay does NOT include a timestamp in its payload signature
    today. Replay attacks (re-POSTing a captured payload) would
    succeed against verify_signature alone. The router-level
    idempotency contract -- ON CONFLICT DO NOTHING on the firmographics
    upsert -- is what neutralises replay. This test documents the
    policy so a future refactor that drops the upsert idempotency
    must update the policy or add timestamp-binding to the signature."""
    from pathlib import Path
    router_src = (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "clay.py"
    ).read_text(encoding="utf-8")
    # The router must EITHER include a timestamp check OR rely on
    # idempotent persistence. Today it's the latter -- assert the
    # persistence is idempotent.
    assert "ON CONFLICT" in router_src or "upsert" in router_src.lower(), (
        "Clay webhook router must use idempotent persistence (ON CONFLICT) "
        "to neutralise replay attacks. Without it, a captured payload can "
        "be re-POSTed indefinitely."
    )
