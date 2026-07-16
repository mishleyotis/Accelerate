"""Tests for the auth allow-list and role hierarchy."""
from __future__ import annotations

import pytest

from app.auth import assign_initial_role, is_zennify_email, role_at_least


class TestAdminAllowlist:
    @pytest.mark.parametrize(
        "email",
        [
            "mishley.otiende@zennify.com",
            "richard.odhiambo@zennify.com",
            "sam.friedewald@zennify.com",
            "kevin.murray@zennify.com",
            "chris.conant@zennify.com",
            "carlie.welsh@zennify.com",
            "tom.hedgecoth@zennify.com",
        ],
    )
    def test_seven_admin_emails_resolve_to_admin(self, email: str) -> None:
        assert assign_initial_role(email) == "ADMIN"

    def test_admin_match_is_case_insensitive(self) -> None:
        assert assign_initial_role("MISHLEY.OTIENDE@ZENNIFY.COM") == "ADMIN"

    def test_random_zennify_email_defaults_to_ae(self) -> None:
        assert assign_initial_role("new.hire@zennify.com") == "AE"

    def test_external_email_still_returns_ae_when_called(self) -> None:
        # Domain enforcement is upstream; this function never throws.
        assert assign_initial_role("attacker@evil.com") == "AE"


class TestZennifyDomainGate:
    def test_zennify_passes(self) -> None:
        assert is_zennify_email("anyone@zennify.com") is True

    def test_external_blocked(self) -> None:
        assert is_zennify_email("anyone@gmail.com") is False

    def test_case_insensitive(self) -> None:
        assert is_zennify_email("ANYONE@ZENNIFY.COM") is True


class TestRoleHierarchy:
    @pytest.mark.parametrize(
        ("role", "minimum", "expected"),
        [
            ("ADMIN", "ADMIN", True),
            ("ADMIN", "ANALYST", True),
            ("ADMIN", "AE", True),
            ("ADMIN", "CUSTOMER", True),
            ("ANALYST", "ADMIN", False),
            ("ANALYST", "ANALYST", True),
            ("ANALYST", "AE", True),
            ("AE", "ANALYST", False),
            ("AE", "AE", True),
            ("AE", "CUSTOMER", True),
            ("CUSTOMER", "AE", False),
        ],
    )
    def test_role_at_least(self, role: str, minimum: str, expected: bool) -> None:
        assert role_at_least(role, minimum) is expected

    def test_unknown_role_returns_false(self) -> None:
        assert role_at_least("HACKER", "ADMIN") is False
        assert role_at_least("ADMIN", "GOD") is False


class TestJwtErrorLeakage:
    """Regression for finding #1 (carryover from refined behavioral QA):
    the JWT verifier was raising HTTPException(detail=f"Invalid token: {e}")
    which leaked the PyJWT library's internal message — letting an
    attacker probing a stolen/forged token distinguish "expired"
    from "bad signature" from "missing claim".

    Contract: the HTTP detail MUST be a constant string ("Invalid
    session"). The underlying error MAY be structlogged for ops.
    """
    def test_expired_token_detail_is_constant(self) -> None:
        import datetime as dt

        import jwt as pyjwt
        from fastapi import HTTPException

        from app.config import get_settings
        from app.services.jwt_service import (
            _private_key,
            verify_token,
        )
        s = get_settings()
        payload = {
            "sub": "u1", "user_id": "u1", "email": "ae.test@zennify.com",
            "role": "AE", "name": "AE Test",
            "iss": s.jwt_issuer, "aud": s.jwt_audience,
            "iat": int((dt.datetime.now(dt.UTC) - dt.timedelta(hours=24)).timestamp()),
            "exp": int((dt.datetime.now(dt.UTC) - dt.timedelta(hours=23)).timestamp()),
        }
        tok = pyjwt.encode(payload, _private_key(), algorithm="RS256")
        with pytest.raises(HTTPException) as ei:
            verify_token(tok)
        assert ei.value.status_code == 401
        # MUST be the constant — must NOT contain PyJWT internals.
        assert ei.value.detail == "Invalid session", (
            f"JWT detail leaked: {ei.value.detail!r} (must be 'Invalid session')"
        )
        for forbidden in (
            "Signature has expired", "Invalid signature",
            "Invalid issuer", "Invalid audience",
            "decode", "Expired", "bad",
        ):
            assert forbidden.lower() not in ei.value.detail.lower(), (
                f"JWT detail leaks {forbidden!r}: {ei.value.detail!r}"
            )

    def test_bad_signature_detail_is_constant(self) -> None:
        import jwt as pyjwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from fastapi import HTTPException

        from app.config import get_settings
        from app.services.jwt_service import verify_token
        s = get_settings()
        # Sign with a DIFFERENT key — verifier should reject.
        attacker_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048,
        )
        payload = {
            "sub": "u1", "user_id": "u1", "email": "x@zennify.com",
            "role": "ADMIN", "name": "X",
            "iss": s.jwt_issuer, "aud": s.jwt_audience,
            "iat": 1, "exp": 9999999999,
        }
        tok = pyjwt.encode(payload, attacker_key, algorithm="RS256")
        with pytest.raises(HTTPException) as ei:
            verify_token(tok)
        assert ei.value.status_code == 401
        assert ei.value.detail == "Invalid session"
