"""Worker production-readiness guard regression test.

The 2026-05-28 audit identified that workers never called
`assert_production_ready(...)` even though Terraform set `ENV=prod`
on every worker Cloud Run Job. Without the guard a worker could
boot with missing `database_url` / `gcp_project_id` and silently
no-op every step.

Fix: `workers/_runner.py::track_job_execution` now runs the guard
once at the top of every worker invocation, with `role="worker"`
(the minimal 2-key surface from
`app/config.py::REQUIRED_FOR_PROD_WORKER`).

This file pins:
  1. Calling `track_job_execution(...)` under env=prod with the
     required worker keys populated returns successfully.
  2. Calling it under env=prod with `database_url` empty raises
     RuntimeError BEFORE the worker body runs.
  3. Calling it under env=local skips the guard (so local CLI
     invocations still work).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _find_app_root(start: Path) -> Path:
    """Walk up to the dma-insights app root (carries backend/ + infra/)."""
    for c in [start, *start.parents]:
        if (c / "backend").is_dir() and (c / "infra").is_dir():
            return c
    raise RuntimeError(f"app root not found from {start}")


_APP_ROOT = _find_app_root(Path(__file__).resolve())
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


@pytest.fixture
def _restore_env(monkeypatch):
    """Snapshot + restore env vars the test mutates."""
    saved = {k: os.environ.get(k) for k in (
        "ENV", "DMA_JOB_EXECUTION_ID", "DATABASE_URL", "GCP_PROJECT_ID",
    )}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_worker_guard_fires_under_env_prod_with_missing_required_keys(
    _restore_env,
):
    """Worker tries to boot with ENV=prod but database_url empty -- the
    guard must raise RuntimeError before the worker body executes."""
    from app.config import Settings
    from workers._runner import track_job_execution

    bad_settings = Settings(
        env="prod",
        database_url="",  # missing -- must trip
        gcp_project_id="digital-maturity-assessor",
    )

    body_ran = {"value": False}
    with (
        patch("app.config.get_settings", return_value=bad_settings),
        pytest.raises(RuntimeError, match=r"database_url is unset"),
        track_job_execution("test_worker"),
    ):
        body_ran["value"] = True
    assert not body_ran["value"], (
        "worker body should NOT have executed when the production-"
        "readiness guard tripped"
    )


def test_worker_guard_passes_under_env_prod_with_required_keys(
    _restore_env,
):
    """Worker boots with ENV=prod and BOTH required keys populated --
    the guard returns silently and the worker body runs."""
    from app.config import Settings
    from workers._runner import track_job_execution

    good_settings = Settings(
        env="prod",
        database_url="postgresql+asyncpg://user:pass@10.0.0.5/dma_insights",
        gcp_project_id="digital-maturity-assessor",
    )

    body_ran = {"value": False}
    with (
        patch("app.config.get_settings", return_value=good_settings),
        track_job_execution("test_worker"),
    ):
        body_ran["value"] = True
    assert body_ran["value"]


def test_worker_guard_short_circuits_under_env_local(_restore_env):
    """Local CLI invocations (env=local) must NOT trip the guard even
    when prod-required keys are absent -- dev convenience would break."""
    from app.config import Settings
    from workers._runner import track_job_execution

    local_settings = Settings(
        env="local",
        database_url="",       # dev default leaks through; ok in local
        gcp_project_id="",     # dev default leaks through; ok in local
    )

    body_ran = {"value": False}
    with (
        patch("app.config.get_settings", return_value=local_settings),
        track_job_execution("test_worker"),
    ):
        body_ran["value"] = True
    assert body_ran["value"]


def test_worker_guard_does_not_require_oauth_or_clay(_restore_env):
    """Workers don't sign JWTs, accept OAuth callbacks, or terminate
    Clay webhooks. Even with every backend-only secret empty under
    env=prod, the worker guard must pass as long as the minimal
    worker surface (db + gcp project id) is set. Regression against
    a future REQUIRED_FOR_PROD_WORKER drift."""
    from app.config import Settings
    from workers._runner import track_job_execution

    worker_only_settings = Settings(
        env="prod",
        database_url="postgresql+asyncpg://user:pass@10.0.0.5/dma_insights",
        gcp_project_id="digital-maturity-assessor",
        # Backend-only -- all empty:
        google_oauth_client_id="",
        google_oauth_client_secret="",
        dma_bot_api_key="",
        rag_api_bearer_key="",
        clay_webhook_url="",
        clay_webhook_secret="",
    )

    body_ran = {"value": False}
    with (
        patch("app.config.get_settings", return_value=worker_only_settings),
        track_job_execution("test_worker"),
    ):
        body_ran["value"] = True
    assert body_ran["value"]
