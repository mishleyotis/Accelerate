"""Production-readiness guard tests.

The guard exists to fail fast when a Cloud Run revision starts up with
dev defaults still in place — the alternative is silent 401s on
every bot call, dropped Pub/Sub events, fail-closed Clay webhooks,
and "feature works locally / breaks in prod" reports.

State matrix:
  env=local / env=test         → no validation; defaults stay intact
  env=prod, all required set   → returns None silently
  env=prod, any required unset → RuntimeError with full list of gaps
  env=prod, dev default leaks  → RuntimeError with the leaking key

2026-05-28 audit fix:
  - `REQUIRED_FOR_PROD` is now the BACKEND alias; new
    `REQUIRED_FOR_PROD_WORKER` covers the minimal Cloud Run Job surface.
  - `jwt_private_key_path` / `jwt_public_key_path` removed from the
    required list because Terraform injects JWT_PRIVATE_KEY_PEM via
    Secret Manager. A separate check accepts EITHER the PEM env OR a
    real on-disk path; rejects only the dev default.
"""
from __future__ import annotations

import pytest

from app.config import (
    REQUIRED_FOR_PROD,
    REQUIRED_FOR_PROD_BACKEND,
    REQUIRED_FOR_PROD_WORKER,
    Settings,
    assert_production_ready,
)


@pytest.fixture(autouse=True)
def _arm_jwt_pem_env(monkeypatch):
    """Every test EXCEPT the explicit "missing-PEM" case runs with the
    PEM env populated. Terraform's prod wiring injects
    JWT_PRIVATE_KEY_PEM via Secret Manager (see infra/terraform/main.tf
    backend block, env block for JWT_PRIVATE_KEY_PEM). The guard treats
    that as "JWT key present" and skips the on-disk path check.
    Tests that exercise the missing-PEM branch unset it explicitly.
    """
    monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", "-----BEGIN RSA PRIVATE KEY-----\nFAKE\n-----END RSA PRIVATE KEY-----\n")
    # The 2026-07 Vertex startup probe (assert_production_ready role=
    # "backend") makes a real network call unless the env is declared
    # Vertex-cold. Tests must stay deterministic + offline.
    monkeypatch.setenv("DMA_DISABLE_VERTEX", "1")


def _full_prod_settings(**overrides) -> Settings:
    """Build a Settings instance with every required key filled."""
    base = {
        "env": "prod",
        "database_url": "postgresql+asyncpg://user:pass@10.0.0.5/dma_insights",
        "redis_url": "redis://prod-redis.example.com:6379/0",
        "google_oauth_client_id": "real-client.apps.googleusercontent.com",
        "google_oauth_client_secret": "GOCSPX-real-secret",
        "jwt_private_key_path": "/secrets/jwt-private.pem",
        "jwt_public_key_path": "/secrets/jwt-public.pem",
        "dma_bot_api_key": "prod-bot-key",
        "rag_api_bearer_key": "prod-rag-key",
        "gcp_project_id": "digital-maturity-assessor",
        "clay_webhook_url": "https://table.clay.com/...",
        "clay_webhook_secret": "clay-hmac-secret",
    }
    base.update(overrides)
    return Settings(**base)


def test_local_env_skips_validation():
    """env=local must NOT validate (defaults are intentional)."""
    s = Settings(env="local")
    assert_production_ready(s)


def test_test_env_skips_validation():
    """env=test must NOT validate (in-process testclient)."""
    s = Settings(env="test")
    assert_production_ready(s)


def test_fully_configured_prod_passes():
    """env=prod with every required key set must return silently."""
    s = _full_prod_settings()
    assert_production_ready(s)


def test_missing_oauth_client_id_fails_prod():
    s = _full_prod_settings(google_oauth_client_id="")
    with pytest.raises(RuntimeError, match=r"google_oauth_client_id is unset"):
        assert_production_ready(s)


def test_missing_bot_api_key_fails_prod():
    """dma_bot_api_key unset → silent 401 on every Request DMA submit;
    guard catches it at startup."""
    s = _full_prod_settings(dma_bot_api_key="")
    with pytest.raises(RuntimeError, match=r"dma_bot_api_key is unset"):
        assert_production_ready(s)


def test_missing_rag_bearer_fails_prod():
    """Without rag_api_bearer_key the RAG API would let unauthenticated
    callers through — block at startup."""
    s = _full_prod_settings(rag_api_bearer_key="")
    with pytest.raises(RuntimeError, match=r"rag_api_bearer_key is unset"):
        assert_production_ready(s)


def test_dev_db_url_leak_fails_prod():
    """Operator forgot to override DATABASE_URL in Cloud Run env →
    revision would try localhost:5433 (dev compose) and hang.
    Guard catches it."""
    s = _full_prod_settings(
        database_url="postgresql+asyncpg://x:y@localhost:5433/dma_insights",
    )
    with pytest.raises(RuntimeError, match=r"still contains dev default"):
        assert_production_ready(s)


def test_dev_redis_url_leak_fails_prod():
    s = _full_prod_settings(redis_url="redis://localhost:6380/0")
    with pytest.raises(RuntimeError, match=r"redis_url"):
        assert_production_ready(s)


def test_dev_jwt_key_path_leak_fails_prod(monkeypatch):
    """Operator forgot to inject JWT_PRIVATE_KEY_PEM AND left the dev
    `jwt_private_key_path` default. The env-or-path check fails.
    """
    monkeypatch.delenv("JWT_PRIVATE_KEY_PEM", raising=False)
    s = _full_prod_settings(jwt_private_key_path="./local-data/jwt-private.pem")
    with pytest.raises(RuntimeError, match=r"JWT private key missing"):
        assert_production_ready(s)


def test_jwt_pem_env_satisfies_check(monkeypatch):
    """Terraform's prod wiring: JWT_PRIVATE_KEY_PEM set via Secret
    Manager. Even when `jwt_private_key_path` still holds the dev
    default string, the check passes — that's the whole point of the
    fix: the path is a fallback, not a requirement."""
    monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", "-----BEGIN RSA PRIVATE KEY-----\nREAL\n-----END RSA PRIVATE KEY-----\n")
    s = _full_prod_settings(jwt_private_key_path="./local-data/jwt-private.pem")
    assert_production_ready(s)


def test_worker_role_skips_backend_only_secrets(monkeypatch):
    """Workers don't sign JWTs, don't accept OAuth callbacks, don't
    terminate Clay webhooks. role='worker' must pass with only
    database_url + gcp_project_id populated — even when
    oauth/jwt/clay/bot/rag are all empty."""
    monkeypatch.delenv("JWT_PRIVATE_KEY_PEM", raising=False)
    s = Settings(
        env="prod",
        database_url="postgresql+asyncpg://user:pass@10.0.0.5/dma_insights",
        gcp_project_id="digital-maturity-assessor",
        # Backend-only secrets left empty — must NOT trip the worker
        # gate because workers don't use them.
        google_oauth_client_id="",
        google_oauth_client_secret="",
        dma_bot_api_key="",
        rag_api_bearer_key="",
        clay_webhook_url="",
        clay_webhook_secret="",
    )
    assert_production_ready(s, role="worker")


def test_worker_role_still_requires_database_url():
    """role='worker' isn't a bypass — the minimal surface (DB + GCP
    project id) must still be populated."""
    s = Settings(
        env="prod",
        database_url="",
        gcp_project_id="digital-maturity-assessor",
    )
    with pytest.raises(RuntimeError, match=r"database_url"):
        assert_production_ready(s, role="worker")


def test_multiple_missing_keys_listed_in_one_error():
    """All gaps surface together so the operator sees the full list
    in one log line, not one revision-failure per fix."""
    s = _full_prod_settings(
        dma_bot_api_key="",
        rag_api_bearer_key="",
        redis_url="",
    )
    with pytest.raises(RuntimeError) as exc:
        assert_production_ready(s)
    msg = str(exc.value)
    assert "dma_bot_api_key" in msg
    assert "rag_api_bearer_key" in msg
    assert "redis_url" in msg
    assert "3 setting(s) misconfigured" in msg


def test_required_for_prod_backend_covers_critical_secrets():
    """Sanity: the backend required-for-prod list must include every
    key that can cause silent runtime failures. If this list shrinks,
    we want a hard prompt to update the test.

    NOTE: jwt_private_key_path is NOT in this list anymore — the env-
    or-path check (JWT_PRIVATE_KEY_PEM) runs separately to accommodate
    Terraform's Secret Manager injection pattern.
    """
    required_names = {name for name, _ in REQUIRED_FOR_PROD_BACKEND}
    must_include = {
        "database_url", "redis_url",
        "google_oauth_client_id", "google_oauth_client_secret",
        "dma_bot_api_key", "rag_api_bearer_key",
        "gcp_project_id",
        # clay_webhook_url / clay_webhook_secret deliberately ABSENT:
        # Clay is deferred this version (2026-06-10) — see
        # test_clay_prod_config_contract.py for the deferral pins.
    }
    missing = must_include - required_names
    assert not missing, (
        f"REQUIRED_FOR_PROD_BACKEND missing critical keys: {missing}. "
        "Adding without test → silent prod startup with the gap present."
    )


def test_required_for_prod_worker_is_minimal():
    """The worker list must NOT include backend-only secrets — every
    extra key there blocks every Cloud Run Job startup needlessly.
    Workers need only DB + GCP project id."""
    required_names = {name for name, _ in REQUIRED_FOR_PROD_WORKER}
    assert required_names == {"database_url", "gcp_project_id"}, (
        f"REQUIRED_FOR_PROD_WORKER drifted: {required_names}. "
        "Workers don't sign JWTs / accept OAuth / terminate Clay webhooks."
    )


def test_required_for_prod_alias_points_to_backend():
    """Back-compat: `REQUIRED_FOR_PROD` (no suffix) must remain an
    alias for the BACKEND list so existing imports keep working."""
    assert REQUIRED_FOR_PROD is REQUIRED_FOR_PROD_BACKEND
