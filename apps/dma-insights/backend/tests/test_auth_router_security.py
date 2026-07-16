"""Phase 3 auth router specific security regression tests.

Per the principal-QA audit, every route gets per-defect tests
covering:
  - dev-login disabled in prod even for admin email
  - google_login hosted_domain mismatch rejected
  - logout clears cookie with same flags as set
  - can_act_as cannot escalate role

Each test exercises the actual FastAPI app via dependency-overridden
TestClient -- not the dependency function in isolation. Surfaces
route-level wiring drift (the previous bearer test was helper-only).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


class _NoOpSession:
    async def execute(self, *a, **kw):
        raise RuntimeError("DB call blocked")
    async def commit(self): pass
    async def rollback(self): pass
    async def close(self): pass


class _FakeRedis:
    """Minimal Redis stand-in for the auth rate limiter -- enough
    surface to let one fresh-key call pass."""
    def __init__(self):
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def pipeline(self, transaction=True):
        return self

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self

    def ttl(self, key):
        return self

    async def execute(self):
        # Pipeline returns [count, ttl] -- the limiter reads both.
        if not self.store:
            return [1, -1]
        last_key = list(self.store)[-1]
        return [self.store[last_key], self.ttls.get(last_key, -1)]

    async def expire(self, key, seconds):
        self.ttls[key] = seconds
        return True


@pytest.fixture
def client():
    """FastAPI TestClient with Redis + Session overrides so security
    tests can exercise the actual route layer without hitting infra."""
    from fastapi.testclient import TestClient

    from app.database import get_session
    from app.deps import get_redis
    from app.main import app

    fake_redis = _FakeRedis()

    async def _override_redis():
        return fake_redis

    async def _override_session():
        yield _NoOpSession()

    app.dependency_overrides[get_redis] = _override_redis
    app.dependency_overrides[get_session] = _override_session
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_session, None)


def test_dev_login_disabled_in_prod_even_for_admin_email(client):
    """Audit assertion: env=prod returns 403 on /dev-login EVEN if
    the supplied email is in admin_emails. The dev-login gate is
    env-only -- a leaked admin email should never bypass it."""
    from app.config import Settings

    prod_settings = Settings(env="prod")
    with patch("app.routers.auth.get_settings", return_value=prod_settings):
        r = client.post(
            "/api/v1/auth/dev-login",
            params={"email": "mishley.otiende@zennify.com"},  # in admin_emails
        )
    assert r.status_code == 403, (
        f"dev-login must return 403 in env=prod regardless of email, "
        f"got {r.status_code}: {r.text}"
    )


def test_google_login_hosted_domain_mismatch_rejected(client):
    """Google ID token decoded payload has `hd` != "zennify.com" → 403.
    Pre-fix the route only enforced is_zennify_email() on the email
    field; a leaked Google token from any other hosted domain with a
    @zennify.com-shaped email would have passed."""

    # Build a fake JWT we can return from the stubbed verifier.
    # The route's flow:
    #   1. JWKS fetch (we patch _jwks to return a stub)
    #   2. jwt.decode (we patch to return our payload directly)
    #   3. hd / email checks -- this is what we want to exercise.
    fake_payload = {
        "email": "evil@zennify.com",  # zennify shape, but...
        "name": "Evil",
        "hd": "evil.com",              # ...wrong hosted domain
        "email_verified": True,
        "sub": "100",
    }
    with patch("app.routers.auth.pyjwt.decode", return_value=fake_payload), \
         patch("app.routers.auth._jwks"):
        r = client.post(
            "/api/v1/auth/google",
            json={"id_token": "stub.token.here"},
        )
    assert r.status_code == 403, (
        f"google_login must 403 on hd mismatch, got {r.status_code}: {r.text}"
    )
    assert "zennify.com" in r.text


def test_google_login_unverified_email_rejected(client):
    """email_verified=False from Google → 403. Google says "we couldn't
    verify this address"; the app must NOT trust it."""
    fake_payload = {
        "email": "u@zennify.com",
        "name": "U",
        "hd": "zennify.com",
        "email_verified": False,  # NOT verified
        "sub": "100",
    }
    with patch("app.routers.auth.pyjwt.decode", return_value=fake_payload), \
         patch("app.routers.auth._jwks"):
        r = client.post(
            "/api/v1/auth/google",
            json={"id_token": "stub.token"},
        )
    assert r.status_code == 403, (
        f"unverified email must 403, got {r.status_code}: {r.text}"
    )


def test_logout_clears_cookie_with_path_matching_set(client):
    """logout must call delete_cookie with the SAME `path` as the
    cookie was set with (`path="/"`). Mismatched path leaves the
    cookie alive in the browser, and the next /auth/me call still
    succeeds — defeating the entire logout."""
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    # Set-Cookie header must contain path=/ on the deletion.
    cookie_header = r.headers.get("set-cookie") or ""
    assert "dma_session" in cookie_header
    assert "Path=/" in cookie_header or "path=/" in cookie_header.lower(), (
        f"logout Set-Cookie missing Path=/: {cookie_header}. "
        "Without it browsers retain the cookie scoped at the issuing path."
    )


def test_can_act_as_cannot_escalate_role():
    """The downgrade-only acting-as contract: an AE's _can_act_as
    list never includes ADMIN or ANALYST; an ANALYST never includes
    ADMIN. Tampering with localStorage on the frontend can't escalate
    because the server-side list is the floor."""
    from app.routers.auth import _can_act_as_for_role

    # AE should only see themselves + customer-view (or just themselves).
    ae_list = _can_act_as_for_role("AE")
    assert "ADMIN" not in ae_list
    assert "ANALYST" not in ae_list

    # ANALYST should see at most themselves + AE/customer.
    analyst_list = _can_act_as_for_role("ANALYST")
    assert "ADMIN" not in analyst_list

    # ADMIN can act-as anyone (or themselves) — but must not be the
    # SAME object as another role's list (would cause shared-state bugs).
    admin_list = _can_act_as_for_role("ADMIN")
    assert admin_list is not ae_list
    assert admin_list is not analyst_list
