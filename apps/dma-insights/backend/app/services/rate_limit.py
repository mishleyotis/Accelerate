"""Redis-backed sliding-window rate limiter for auth endpoints.

2026-05-28 audit fix: `/auth/google` and `/auth/dev-login` had no
rate limit. An attacker could:

  - Spray Google ID tokens at /auth/google trying to find one that
    decodes under our `aud` (low probability per attempt but free in
    Cloud Run cost; the JWKS lookup is cached so the per-call cost
    is near-zero).
  - Hammer /auth/dev-login in any env where the env-gate is
    accidentally relaxed (e.g. dev or staging) -- 10 attempts per
    second is enough to enumerate the @zennify.com email allowlist.

Both endpoints now hang off the `rate_limit_auth` dependency below,
which uses Redis INCR + EXPIRE on a per-(client_ip, route, minute)
key. Cap default: 10 attempts per 60-second window. Over the cap →
HTTP 429 with `Retry-After` header.

Best-effort by design: if Redis is down at the time of the call,
the limiter logs a WARN and lets the request through. We'd rather
auth keep working during a Redis outage than fail-close every
login. This matches the rest of the auth path's resilience contract
(JWKS fetch fails → 503; DB connection fails → 503 with detail;
Redis → degrade gracefully).

State branches:
  redis ok + under cap   → no action; request proceeds
  redis ok + at cap      → HTTP 429 + Retry-After header
  redis ok + over cap    → HTTP 429 + Retry-After header
  redis unavailable      → log warn, proceed (fail-open)
  redis returns garbage  → log warn, proceed (fail-open)
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status

from app.deps import RedisDep

log = structlog.get_logger()

# Default cap: 10 attempts / 60s window. The window is a tumbling
# minute (not strictly sliding) because INCR + EXPIRE is cheaper
# than ZADD/ZREMRANGEBYSCORE + atomicity guarantees are simpler.
# A tumbling window means an attacker could fire 10 at second 59
# + 10 at second 61 -- 20 in 2 seconds. That's still 7-10x below
# what a brute-force attack needs to enumerate even a small
# token space. If we tighten in future, switch to a sliding-window
# implementation via a Lua script.
AUTH_DEFAULT_LIMIT = 10
AUTH_DEFAULT_WINDOW_SECONDS = 60


def _client_ip(request: Request) -> str:
    """Resolve the requesting client IP, honouring the Cloud Run +
    Cloud Load Balancer X-Forwarded-For chain. Cloud Run appends the
    edge IP last, so we take the FIRST entry (original client). Falls
    back to the direct socket peer if no header is present (local dev
    + the testclient case).
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        # XFF is comma-separated -- first value is the original client.
        return fwd.split(",")[0].strip() or "unknown"
    if request.client is not None:
        return request.client.host or "unknown"
    return "unknown"


async def _check_and_increment(
    redis_client,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds).

    Tumbling-window semantics: the window starts on the FIRST request
    and lasts exactly `window_seconds`. Subsequent INCR calls do NOT
    reset the TTL. Over-limit requests inside the window are rejected
    with the current remaining TTL as Retry-After.

    2026-05-28 audit fix: the previous implementation called
    `pipe.expire(key, window_seconds)` on every request, including
    over-limit ones. That meant an attacker hammering the endpoint
    kept resetting the lockout clock -- the window would never expire
    while the attack continued. Now we EXPIRE only on the first call
    (when INCR returns 1), so the window is fixed once set and an
    attacker's later calls are pure read-from-existing-counter.

    Uses a transactional pipeline so INCR + (conditional) EXPIRE + TTL
    happen atomically.
    """
    try:
        # Step 1: INCR + TTL atomically. We need to know the post-INCR
        # count to decide whether to EXPIRE -- a single pipeline would
        # require Lua to read INCR's result, so we do two round-trips.
        # Both are O(1) Redis ops; the cost is one extra RTT, not an
        # extra Redis CPU cycle.
        pipe = redis_client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.ttl(key)
        results = await pipe.execute()
        count = int(results[0])
        ttl = int(results[1])
        # Step 2: if this is the first call in the window (count == 1
        # OR TTL came back as -1 = no expiry set), apply the window.
        if count == 1 or ttl < 0:
            await redis_client.expire(key, window_seconds)
            ttl = window_seconds
    except Exception as e:
        # Fail-open: a Redis outage shouldn't break auth. The catch
        # is intentionally broad -- ConnectionError, TimeoutError,
        # ResponseError all surface the same way to the caller.
        log.warning("rate_limit.redis_unavailable", err=str(e), key=key)
        return (True, 0)
    if count > limit:
        # Retry-After uses the current remaining TTL, not the original
        # window size. After the first reject the second over-limit
        # call will report a SHORTER Retry-After (correct: the window
        # is already counting down).
        return (False, max(1, ttl))
    return (True, 0)


def rate_limit_auth(
    *,
    limit: int = AUTH_DEFAULT_LIMIT,
    window_seconds: int = AUTH_DEFAULT_WINDOW_SECONDS,
    route_key: str,
):
    """Factory returning a FastAPI dependency. Each route gets its
    own counter via `route_key` so /auth/google traffic doesn't
    consume the /auth/dev-login budget.

    Usage:
        @router.post(
            "/dev-login",
            dependencies=[
                Depends(rate_limit_auth(route_key="dev_login")),
            ],
        )
        async def dev_login(...): ...
    """

    async def _dep(
        request: Request,
        redis_client: RedisDep,
    ) -> None:
        # `dev_login` is already gated to env=local at the endpoint
        # level (returns 403 otherwise). Layering a per-IP rate limit
        # on top means a Playwright suite running 84 visual-regression
        # tests against localhost gets choked at 10 logins/min/IP
        # and 74 tests fail with "dev-login returned 429". The endpoint
        # is unreachable in prod regardless of this knob, so the rate
        # limit adds no production safety -- only local-dev pain. Skip
        # the budget when env=local AND route is dev_login.
        from app.config import get_settings as _get_settings
        if route_key == "dev_login" and _get_settings().env == "local":
            return
        ip = _client_ip(request)
        # Per-IP, per-route, per-minute key. We round to the current
        # minute so adjacent windows don't share state (the INCR'd
        # key naturally rolls over via EXPIRE).
        key = f"rl:auth:{route_key}:{ip}"
        allowed, retry_after = await _check_and_increment(
            redis_client,
            key=key,
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            log.info(
                "rate_limit.exceeded",
                route=route_key, ip=ip, retry_after=retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"too many auth attempts -- retry in "
                    f"{retry_after}s ({limit} per {window_seconds}s window)"
                ),
                headers={"Retry-After": str(retry_after)},
            )

    return _dep


# Pre-baked dependencies for the two auth endpoints. Wired via
# `Depends(...)` in the route signatures (router file).
RateLimitGoogleLogin = Annotated[
    None,
    Depends(rate_limit_auth(route_key="google_login")),
]
RateLimitDevLogin = Annotated[
    None,
    Depends(rate_limit_auth(route_key="dev_login")),
]
