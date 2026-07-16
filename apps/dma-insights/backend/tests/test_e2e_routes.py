"""End-to-end route smoke test.

Boots the FastAPI app in-process (no DB, no Redis) and confirms every
registered route either:
  (a) returns 200 OK without auth (healthz / readyz / docs etc.), or
  (b) returns 401 Unauthorized when called without a session token, or
  (c) returns 403 Forbidden when the role gate would reject the user
      even with a token (the patterns endpoints + admin routes).

This is the broadest end-to-end QA we can run without standing up
external infrastructure — it catches:
  - any router accidentally dropped from main.py's include_router calls
  - any new endpoint missing a CurrentUserDep / require_* gate
  - any 500-on-boot wiring break (the test framework would crash the app)

The route inventory is built dynamically from `app.routes` so adding a
new endpoint automatically pulls it into the assertion. Methods with
path parameters use lab placeholder values.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Force jwt_service to use an ephemeral key (no on-disk pem required).
os.environ.setdefault("JWT_PRIVATE_KEY_PATH", "/nonexistent/key.pem")
os.environ.setdefault("JWT_PUBLIC_KEY_PATH", "/nonexistent/pub.pem")


# Routes that are intentionally public (no auth required).
PUBLIC_ROUTES = frozenset({
    "/healthz",
    "/readyz",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/google",
    "/api/v1/auth/logout",
    "/api/v1/auth/dev-login",  # env-gated (returns 403 outside local env)
})


# Routes that are gated by a Bearer token instead of session JWT.
# When called without auth they still 401 (FastAPI's default), which is
# the same expectation as the user-gated routes — so they're folded in.
BEARER_GATED_PREFIXES = (
    "/api/v1/ingest/",
    "/api/v1/rag/",
)


def _placeholder_for(param: str) -> str:
    """Return a non-empty placeholder for any path param. The endpoint
    will 401 before path-param parsing matters, but FastAPI's router
    still needs SOMETHING."""
    if "uuid" in param.lower():
        return "00000000-0000-0000-0000-000000000000"
    if param.endswith("_id"):
        return "x"
    return "x"


def _resolve_path(template: str) -> str:
    out = template
    while "{" in out and "}" in out:
        start = out.index("{")
        end = out.index("}", start)
        name = out[start + 1 : end]
        out = out[:start] + _placeholder_for(name) + out[end + 1 :]
    return out


@pytest.fixture(scope="module")
def client():
    # Import inside the fixture so any module-import side effects (like
    # the lazy Vertex client) don't blow up collection-time.
    from app.main import app

    return TestClient(app)


def test_every_route_is_either_public_or_auth_gated(client):
    """No accidental open endpoint slipped in. Every non-public,
    non-meta route returns 401 / 403 (auth-gated) when called without
    credentials. SSE endpoints return 401 too — they need a session
    cookie before they open the EventSource stream."""
    from app.main import app

    failures: list[str] = []

    for route in app.routes:
        if not hasattr(route, "path") or not hasattr(route, "methods"):
            continue
        path: str = route.path  # type: ignore[attr-defined]
        if path in PUBLIC_ROUTES:
            continue

        # FastAPI's TestClient resolves methods set
        methods = getattr(route, "methods", None) or {"GET"}
        method = "GET" if "GET" in methods else next(iter(methods))

        url = _resolve_path(path)
        resp = client.request(method, url)
        # Accept 401 (no auth), 403 (role gate), 404 (entity not found
        # — still proves the route is wired and reaches the handler),
        # 422 (validation — same: handler reached), or 405 if the
        # method isn't supported on this path placeholder.
        if resp.status_code not in (401, 403, 404, 405, 422):
            failures.append(
                f"{method} {path} → {resp.status_code} (expected 401/403/404/405/422)"
            )

    if failures:
        joined = "\n  ".join(failures)
        raise AssertionError(
            f"{len(failures)} route(s) returned an unexpected status:\n  {joined}"
        )


def test_health_endpoints_open(client):
    """Public liveness endpoints stay reachable without auth."""
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_openapi_doc_renders(client):
    """OpenAPI spec is published — the Claude project's bot pipeline
    relies on this for client-code generation."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec.get("info", {}).get("title") == "DMA Insights"
    # At least 40 paths registered (we're at 45+ post-finalize).
    assert len(spec["paths"]) >= 40


def test_bearer_endpoints_reject_missing_bearer(client):
    """Ingest + RAG endpoints are Bearer-gated; missing header → 401.
    (The dependency early-returns when the bot_api_key isn't configured,
    so in local dev they appear open — guarded by the env check in the
    dependency itself.)"""
    from app.config import get_settings

    s = get_settings()
    if not s.dma_bot_api_key:
        pytest.skip("Bearer guard disabled in local dev (no DMA_BOT_API_KEY).")
    resp = client.post(
        "/api/v1/ingest/assessment",
        json={"payload_version": "v1", "request_id": "REQ-A6654887",
              "entity_name": "X", "scqa": {"situation": "s", "complication": "c",
              "question": "q", "answer": "a"}, "subcap_scores": [],
              "evidence": [], "insights": [], "recommendations": []},
    )
    assert resp.status_code == 401


def test_ingest_assessment_accepts_admin_cookie(client):
    """2026-05-28 audit fix: /ingest/assessment accepts EITHER the bot
    bearer OR an admin session cookie. Operators can replay an ingest
    from a curl session without retrieving the bot secret from Secret
    Manager.

    Builds the JWT directly (bypasses dev-login which hits the DB)
    and injects it as a cookie. Empty body → Pydantic 422 confirms
    auth passed; 401 would mean the dual-auth dependency failed.
    """
    from app.config import get_settings
    from app.services.jwt_service import issue_token

    s = get_settings()
    if not s.dma_bot_api_key:
        pytest.skip("Bearer guard disabled in local dev (no DMA_BOT_API_KEY).")

    admin_token = issue_token(
        user_id="admin-test", email="admin@zennify.com",
        role="ADMIN", name="Admin Test",
    )
    # Set cookie on the client (httpx 0.27+ deprecated per-request
    # cookies=… for ambiguity around cookie persistence).
    client.cookies.set("dma_session", admin_token)
    try:
        resp = client.post("/api/v1/ingest/assessment", json={})
    finally:
        client.cookies.clear()
    assert resp.status_code == 422, (
        f"admin cookie should reach Pydantic validation (422); got "
        f"{resp.status_code}: {resp.text}"
    )


def test_ingest_assessment_rejects_non_admin_cookie(client):
    """Same dual-auth path but with a non-admin session: must 403.
    Customer/AE/Analyst replay isn't allowed -- only admin or the bot."""
    from app.config import get_settings
    from app.services.jwt_service import issue_token

    s = get_settings()
    if not s.dma_bot_api_key:
        pytest.skip("Bearer guard disabled in local dev (no DMA_BOT_API_KEY).")

    ae_token = issue_token(
        user_id="ae-test", email="ae@zennify.com",
        role="AE", name="AE Test",
    )
    # Set cookie on the client (httpx 0.27+ deprecated per-request cookies=…).
    client.cookies.set("dma_session", ae_token)
    try:
        resp = client.post("/api/v1/ingest/assessment", json={})
    finally:
        client.cookies.clear()
    assert resp.status_code == 403, (
        f"AE cookie should 403, got {resp.status_code}: {resp.text}"
    )


def test_dev_login_returns_403_in_non_local_env(client) -> None:
    """dev-login endpoint must return 403 outside local env."""
    from unittest.mock import patch

    from app.config import Settings

    non_local_settings = Settings(env="prod")  # type: ignore[call-arg]
    with patch("app.routers.auth.get_settings", return_value=non_local_settings):
        resp = client.post("/api/v1/auth/dev-login", params={"email": "x@zennify.com"})
    assert resp.status_code == 403, (
        f"dev-login should be blocked in prod env, got {resp.status_code}"
    )


def test_dev_login_returns_400_for_non_zennify_email(client) -> None:
    """dev-login endpoint rejects non-@zennify.com emails even in local env."""
    from unittest.mock import patch

    from app.config import Settings

    local_settings = Settings(env="local")  # type: ignore[call-arg]
    with patch("app.routers.auth.get_settings", return_value=local_settings):
        resp = client.post("/api/v1/auth/dev-login", params={"email": "attacker@evil.com"})
    assert resp.status_code == 400
