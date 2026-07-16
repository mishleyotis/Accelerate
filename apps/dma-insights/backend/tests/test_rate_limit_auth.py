"""Auth rate-limit regression tests for `app/services/rate_limit.py`.

The 2026-05-28 audit added Redis-backed rate limiting to /auth/google
and /auth/dev-login. This file pins the contract:

  1. Under the limit  → request proceeds normally
  2. At/over the limit → HTTP 429 with Retry-After header
  3. Redis unavailable → fail-open (request proceeds; warn logged)
  4. Distinct routes  → distinct counters (Google traffic doesn't
                         consume dev-login budget)
  5. Distinct IPs     → distinct counters

The limiter logic is exercised against a fake Redis client (no live
Redis required) so these tests run in the standard CI sweep.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException


class _FakeRedis:
    """In-memory stand-in implementing only the surface the limiter
    touches:
      - `pipeline(transaction=True)` returning a context with `incr`,
        `ttl`, `execute`
      - top-level `expire(key, seconds)` (the limiter now sets the
        window outside the pipeline so the EXPIRE only fires on the
        first request of a window)

    `expire_call_count` lets tests assert that EXPIRE was called the
    right number of times (audit: must be exactly once per window,
    not once per request).
    """

    def __init__(self):
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.fail_mode: str | None = None  # 'connection' | 'garbage' | None
        self.expire_call_count: int = 0

    def pipeline(self, transaction: bool = True):
        return _FakePipeline(self)

    async def expire(self, key: str, seconds: int) -> bool:
        if self.fail_mode == "connection":
            raise ConnectionError("Redis is down")
        self.expire_call_count += 1
        self.ttls[key] = seconds
        return True


class _FakePipeline:
    def __init__(self, parent: _FakeRedis):
        self.parent = parent
        self._ops: list[tuple[str, tuple]] = []

    def incr(self, key: str):
        self._ops.append(("incr", (key,)))
        return self

    def expire(self, key: str, seconds: int):
        # Kept for back-compat with any caller that still uses pipeline
        # EXPIRE; production limiter does NOT.
        self._ops.append(("expire", (key, seconds)))
        return self

    def ttl(self, key: str):
        self._ops.append(("ttl", (key,)))
        return self

    async def execute(self) -> list[int]:
        if self.parent.fail_mode == "connection":
            raise ConnectionError("Redis is down")
        if self.parent.fail_mode == "garbage":
            return ["not a number", "not a number"]  # type: ignore[list-item]
        results: list[int] = []
        for op, args in self._ops:
            if op == "incr":
                key = args[0]
                self.parent.store[key] = self.parent.store.get(key, 0) + 1
                results.append(self.parent.store[key])
            elif op == "expire":
                key, seconds = args
                self.parent.ttls[key] = seconds
                results.append(1)
            elif op == "ttl":
                key = args[0]
                results.append(self.parent.ttls.get(key, -1))
        return results


@pytest.mark.asyncio
async def test_under_limit_allows_request() -> None:
    """First call to a fresh key passes."""
    from app.services.rate_limit import _check_and_increment

    fake = _FakeRedis()
    allowed, retry = await _check_and_increment(
        fake, key="rl:auth:google_login:1.2.3.4", limit=10, window_seconds=60,
    )
    assert allowed is True
    assert retry == 0


@pytest.mark.asyncio
async def test_at_limit_still_allows() -> None:
    """Exactly `limit` calls all pass; the (limit+1)-th rejects."""
    from app.services.rate_limit import _check_and_increment

    fake = _FakeRedis()
    for i in range(10):
        allowed, _ = await _check_and_increment(
            fake, key="rl:auth:test:5.5.5.5", limit=10, window_seconds=60,
        )
        assert allowed, f"call {i + 1} should be under the cap"
    allowed, retry = await _check_and_increment(
        fake, key="rl:auth:test:5.5.5.5", limit=10, window_seconds=60,
    )
    assert not allowed
    assert retry == 60


@pytest.mark.asyncio
async def test_redis_outage_fails_open() -> None:
    """When Redis is unavailable the limiter MUST let the request
    through (auth shouldn't fail-close on a Redis blip)."""
    from app.services.rate_limit import _check_and_increment

    fake = _FakeRedis()
    fake.fail_mode = "connection"
    allowed, retry = await _check_and_increment(
        fake, key="rl:auth:test:7.7.7.7", limit=10, window_seconds=60,
    )
    assert allowed is True, "Redis outage must fail-open"
    assert retry == 0


@pytest.mark.asyncio
async def test_distinct_routes_distinct_buckets() -> None:
    """/auth/google requests don't consume /auth/dev-login's budget."""
    from app.services.rate_limit import _check_and_increment

    fake = _FakeRedis()
    # Burn the Google bucket.
    for _ in range(11):
        await _check_and_increment(
            fake, key="rl:auth:google_login:1.1.1.1",
            limit=10, window_seconds=60,
        )
    # dev_login bucket for the same IP should still be fresh.
    allowed, _ = await _check_and_increment(
        fake, key="rl:auth:dev_login:1.1.1.1", limit=10, window_seconds=60,
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_distinct_ips_distinct_buckets() -> None:
    """One client hammering an endpoint doesn't lock out other clients."""
    from app.services.rate_limit import _check_and_increment

    fake = _FakeRedis()
    for _ in range(11):
        await _check_and_increment(
            fake, key="rl:auth:dev_login:9.9.9.9",
            limit=10, window_seconds=60,
        )
    # Different IP, same route → fresh bucket.
    allowed, _ = await _check_and_increment(
        fake, key="rl:auth:dev_login:8.8.8.8", limit=10, window_seconds=60,
    )
    assert allowed is True


def test_client_ip_prefers_xforwarded_first_value() -> None:
    """Cloud Run + Cloud LB chain puts the original client first in
    X-Forwarded-For. The limiter MUST use that, not the request.client
    IP (which would be the load balancer's edge IP and lump every
    client into one bucket)."""
    from unittest.mock import MagicMock

    from app.services.rate_limit import _client_ip

    request = MagicMock()
    request.headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1, 130.211.0.7"}
    request.client = MagicMock(host="10.0.0.1")
    assert _client_ip(request) == "203.0.113.5"


def test_client_ip_falls_back_to_socket_peer() -> None:
    """No XFF → use request.client.host (local dev / direct uvicorn)."""
    from unittest.mock import MagicMock

    from app.services.rate_limit import _client_ip

    request = MagicMock()
    request.headers = {}
    request.client = MagicMock(host="127.0.0.1")
    assert _client_ip(request) == "127.0.0.1"


def test_client_ip_handles_missing_client_object() -> None:
    """Edge: no XFF and no request.client (TestClient on some
    fastapi versions) — return 'unknown' rather than raising."""
    from unittest.mock import MagicMock

    from app.services.rate_limit import _client_ip

    request = MagicMock()
    request.headers = {}
    request.client = None
    assert _client_ip(request) == "unknown"


def test_dependency_factory_returns_callable_per_route() -> None:
    """rate_limit_auth(route_key='X') returns a fresh dependency each
    call — used so each route gets its own counter via dependency
    injection."""
    from app.services.rate_limit import rate_limit_auth

    dep_a = rate_limit_auth(route_key="google_login")
    dep_b = rate_limit_auth(route_key="dev_login")
    assert callable(dep_a)
    assert callable(dep_b)
    assert dep_a is not dep_b


@pytest.mark.asyncio
async def test_dependency_raises_429_with_retry_after() -> None:
    """End-to-end: the dependency raises HTTPException(429) with a
    Retry-After header when the cap is exceeded."""
    from unittest.mock import MagicMock

    from app.services.rate_limit import rate_limit_auth

    fake = _FakeRedis()
    dep = rate_limit_auth(route_key="test_route", limit=2, window_seconds=30)
    request = MagicMock()
    request.headers = {"x-forwarded-for": "4.4.4.4"}
    request.client = MagicMock(host="4.4.4.4")

    # First two calls pass.
    await dep(request=request, redis_client=fake)
    await dep(request=request, redis_client=fake)
    # Third trips the cap.
    with pytest.raises(HTTPException) as exc:
        await dep(request=request, redis_client=fake)
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers
    assert exc.value.headers["Retry-After"] == "30"


@pytest.mark.asyncio
async def test_expire_called_exactly_once_per_window() -> None:
    """Tumbling-window contract: EXPIRE is set on the first INCR of a
    window and NOT reset by subsequent calls. The audit found the
    previous impl called pipe.expire() on every request, which let an
    attacker keep extending their own lockout indefinitely."""
    from app.services.rate_limit import _check_and_increment

    fake = _FakeRedis()
    # Burn 20 calls (limit is 10) — over-limit calls included.
    for _ in range(20):
        await _check_and_increment(
            fake, key="rl:auth:tumbling:1.2.3.4",
            limit=10, window_seconds=60,
        )
    # EXPIRE must have been called exactly ONCE (the first call set the
    # window; subsequent calls — including all the over-limit ones —
    # must not have reset it).
    assert fake.expire_call_count == 1, (
        f"expected 1 EXPIRE per window, got {fake.expire_call_count}. "
        "Over-limit requests are extending the lockout clock!"
    )


@pytest.mark.asyncio
async def test_retry_after_uses_current_ttl_not_full_window() -> None:
    """When the cap is tripped, Retry-After should reflect the CURRENT
    TTL of the existing key — not the full window length. The fake
    Redis returns the TTL stored on first EXPIRE; subsequent rejects
    should report that same (or smaller) value, never larger."""
    from app.services.rate_limit import _check_and_increment

    fake = _FakeRedis()
    # First call sets EXPIRE=60, TTL=60.
    await _check_and_increment(
        fake, key="rl:auth:tickdown:9.9.9.9",
        limit=2, window_seconds=60,
    )
    # Simulate clock advancement by manually shrinking the TTL.
    fake.ttls["rl:auth:tickdown:9.9.9.9"] = 30
    # Burn the remaining budget + trip.
    await _check_and_increment(
        fake, key="rl:auth:tickdown:9.9.9.9",
        limit=2, window_seconds=60,
    )
    allowed, retry = await _check_and_increment(
        fake, key="rl:auth:tickdown:9.9.9.9",
        limit=2, window_seconds=60,
    )
    assert allowed is False
    assert retry == 30, f"Retry-After should reflect current TTL=30, got {retry}"


class _NoOpSession:
    """Async session stub that swallows execute/commit -- the route-
    level tests below only care that the rate-limit dependency fires
    BEFORE the handler runs DB work. Returning fake rows isn't safe
    because the handler interprets them; raising HTTPException at
    .execute() is the cleanest way to say "rate-limit gate fired and
    the route body started but we don't care about its result."""

    async def execute(self, *a, **kw):
        raise RuntimeError("DB call blocked in route-rate-limit test")

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_route_level_dev_login_returns_429_after_limit(monkeypatch) -> None:
    """Route-level integration: POST /api/v1/auth/dev-login through
    the actual FastAPI app -- not just the helper -- returns 429 after
    the 10/min cap. Proves the dependency is wired to the route and
    the Retry-After header survives FastAPI's response pipeline.

    Both RedisDep and SessionDep are overridden so the test doesn't
    require live infrastructure -- the rate-limit gate runs first; on
    the 11th call it raises 429 without ever reaching the DB.

    `env` is pinned to a non-local value because dev-login's rate-limit
    skip in env=local (introduced to unblock Playwright visual-regression
    suites) would otherwise turn this test into a no-op. The 429 wire
    contract still needs verification for the (unsupported) case where
    dev_login somehow stays reachable in a non-local deploy.
    """
    from fastapi.testclient import TestClient

    from app.database import get_session
    from app.deps import get_redis
    from app.main import app
    from app.services import rate_limit as rl_mod

    fake_redis = _FakeRedis()

    async def _override_redis():
        return fake_redis

    async def _override_session():
        yield _NoOpSession()

    # Force a non-local env so the dev_login rate-limit bypass doesn't
    # short-circuit. We monkeypatch BOTH `app.config.get_settings` (used
    # by rate_limit._dep) and `app.routers.auth.get_settings` (used by
    # the dev_login handler's "is local?" guard). The handler still
    # 403s in non-local env, but that doesn't matter -- the 429 fires
    # first, before reaching the handler body.
    class _SettingsNonLocal:
        env = "staging"

    monkeypatch.setattr("app.config.get_settings", lambda: _SettingsNonLocal())
    monkeypatch.setattr(
        "app.routers.auth.get_settings", lambda: _SettingsNonLocal(),
    )

    app.dependency_overrides[get_redis] = _override_redis
    app.dependency_overrides[get_session] = _override_session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            for _ in range(rl_mod.AUTH_DEFAULT_LIMIT):
                r = client.post(
                    "/api/v1/auth/dev-login",
                    params={"email": "ae@zennify.com"},
                    headers={"X-Forwarded-For": "5.5.5.5"},
                )
                assert r.status_code != 429, (
                    f"call before limit returned 429: {r.text}"
                )
            # 11th call must 429.
            r = client.post(
                "/api/v1/auth/dev-login",
                params={"email": "ae@zennify.com"},
                headers={"X-Forwarded-For": "5.5.5.5"},
            )
            assert r.status_code == 429, (
                f"expected 429 after limit, got {r.status_code}: {r.text}"
            )
            assert "Retry-After" in r.headers
    finally:
        app.dependency_overrides.pop(get_redis, None)
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_route_level_google_login_returns_429_after_limit() -> None:
    """Same contract for /api/v1/auth/google -- the limiter must
    fire before the JWKS fetch / token decode path even starts."""
    from fastapi.testclient import TestClient

    from app.database import get_session
    from app.deps import get_redis
    from app.main import app
    from app.services import rate_limit as rl_mod

    fake_redis = _FakeRedis()

    async def _override_redis():
        return fake_redis

    async def _override_session():
        yield _NoOpSession()

    app.dependency_overrides[get_redis] = _override_redis
    app.dependency_overrides[get_session] = _override_session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            for _ in range(rl_mod.AUTH_DEFAULT_LIMIT):
                r = client.post(
                    "/api/v1/auth/google",
                    json={"id_token": "not-a-real-token"},
                    headers={"X-Forwarded-For": "6.6.6.6"},
                )
                assert r.status_code != 429
            r = client.post(
                "/api/v1/auth/google",
                json={"id_token": "not-a-real-token"},
                headers={"X-Forwarded-For": "6.6.6.6"},
            )
            assert r.status_code == 429
            assert "Retry-After" in r.headers
    finally:
        app.dependency_overrides.pop(get_redis, None)
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_dev_login_skips_rate_limit_in_local_env(monkeypatch) -> None:
    """When env=local AND route_key="dev_login", the rate-limit dependency
    must return immediately without touching Redis. The dev-login endpoint
    is already gated to env=local at the endpoint level (403 in prod), so
    the per-IP budget adds no production safety -- only local-dev pain.
    Concrete bug it caused: a Playwright visual-regression suite of 84
    route x breakpoint tests against localhost choked at 10 logins/min/IP
    and 74 tests failed with 'dev-login returned 429' (mis-surfaced as
    500). With the bypass, the suite completes deterministically.
    """
    from unittest.mock import MagicMock

    from app.services.rate_limit import rate_limit_auth

    class _SettingsLocal:
        env = "local"

    monkeypatch.setattr(
        "app.config.get_settings", lambda: _SettingsLocal(),
    )

    dep = rate_limit_auth(route_key="dev_login", limit=2, window_seconds=30)
    request = MagicMock()
    request.headers = {"x-forwarded-for": "5.5.5.5"}
    request.client = MagicMock(host="5.5.5.5")

    # An "exploding" redis_client whose .pipeline() raises tells us the
    # dependency short-circuited before any Redis call.
    class _ExplodingRedis:
        def pipeline(self, *_a, **_kw):
            raise AssertionError(
                "redis was consulted -- dev_login rate-limit "
                "bypass must short-circuit BEFORE pipeline()",
            )

    # 20 back-to-back calls all succeed (no Redis, no HTTPException).
    for _ in range(20):
        await dep(request=request, redis_client=_ExplodingRedis())


@pytest.mark.asyncio
async def test_dev_login_rate_limit_still_applies_in_non_local(monkeypatch) -> None:
    """The bypass only fires when env == 'local'. In any other env the
    dependency must consult Redis exactly as before so a misconfigured
    deploy that somehow leaves dev-login reachable still has the rate
    limit as a second-line defence (defence in depth)."""
    from unittest.mock import MagicMock

    from app.services.rate_limit import rate_limit_auth

    class _SettingsProd:
        env = "prod"

    monkeypatch.setattr(
        "app.config.get_settings", lambda: _SettingsProd(),
    )

    dep = rate_limit_auth(route_key="dev_login", limit=2, window_seconds=30)
    request = MagicMock()
    request.headers = {"x-forwarded-for": "6.6.6.6"}
    request.client = MagicMock(host="6.6.6.6")

    fake = _FakeRedis()
    await dep(request=request, redis_client=fake)
    await dep(request=request, redis_client=fake)
    with pytest.raises(HTTPException) as exc:
        await dep(request=request, redis_client=fake)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_other_route_keys_keep_rate_limit_in_local(monkeypatch) -> None:
    """The bypass is targeted: route_key="google_login" must STILL be
    rate-limited even in env=local (an attacker hammering Google OAuth
    from a dev box deserves the limit). Only "dev_login" gets the pass."""
    from unittest.mock import MagicMock

    from app.services.rate_limit import rate_limit_auth

    class _SettingsLocal:
        env = "local"

    monkeypatch.setattr(
        "app.config.get_settings", lambda: _SettingsLocal(),
    )

    dep = rate_limit_auth(
        route_key="google_login", limit=2, window_seconds=30,
    )
    request = MagicMock()
    request.headers = {"x-forwarded-for": "7.7.7.7"}
    request.client = MagicMock(host="7.7.7.7")

    fake = _FakeRedis()
    await dep(request=request, redis_client=fake)
    await dep(request=request, redis_client=fake)
    with pytest.raises(HTTPException) as exc:
        await dep(request=request, redis_client=fake)
    assert exc.value.status_code == 429
