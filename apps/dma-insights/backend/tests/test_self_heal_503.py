"""Regression tests for the 2026-06-05 self-healing fixes.

Pre-fix, `refresh_engine_on_auth_failure()` disposed the cached engine
but `get_settings()` was `@lru_cache`'d so the next `_make_engine()`
call read the SAME stale `database_url`. The self-heal path that's
supposed to recover after a Cloud SQL password rotation was a no-op,
which caused the recurring Phase 4 503.

Plus a contract test for the production-readiness guard now being
non-fatal at startup (was crashing the container -- LB returned 503
with no body, operator was blind).
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.config import Settings, get_settings


def _make_settings_with_dsn(dsn: str) -> Settings:
    """Construct Settings with an overridden database_url."""
    with patch.dict(os.environ, {"DATABASE_URL": dsn, "ENV": "local"}, clear=False):
        get_settings.cache_clear()
        return get_settings()


class TestSettingsCacheClear:
    """`get_settings.cache_clear()` must evict the lru_cache so the
    next `get_settings()` re-reads env vars. Without this the engine
    refresh path is a no-op."""

    def setup_method(self) -> None:
        get_settings.cache_clear()

    def teardown_method(self) -> None:
        get_settings.cache_clear()

    def test_settings_returns_cached_instance_until_cache_clear(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://a:b@/x"}, clear=False):
            get_settings.cache_clear()
            s1 = get_settings()
            s2 = get_settings()
            # Same instance until cleared.
            assert s1 is s2

    def test_settings_re_reads_env_after_cache_clear(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://a:b@/x"}, clear=False):
            get_settings.cache_clear()
            s1 = get_settings()
            assert "a:b" in s1.database_url
        # Mutate the env + clear cache -- next call must reflect new value.
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql+asyncpg://NEWUSER:NEWPASS@/x"},
            clear=False,
        ):
            get_settings.cache_clear()
            s2 = get_settings()
            assert "NEWUSER:NEWPASS" in s2.database_url
            assert s1 is not s2


class TestRefreshEngineClearsSettings:
    """`refresh_engine_on_auth_failure` MUST call get_settings.cache_clear()
    -- without it the engine rebuilds against a stale DSN and the
    InvalidPasswordError keeps firing forever, which is exactly the
    recurring Phase 4 503 the user kept hitting."""

    @pytest.mark.asyncio
    async def test_refresh_re_reads_settings(self) -> None:
        """The actual behavioural contract: after a refresh, a freshly-
        mutated DATABASE_URL env var must be reflected in get_settings().
        This is what makes the Cloud Run secret rotation pick-up work."""
        from app import database as db
        from app.database import refresh_engine_on_auth_failure

        # Pin starting state.
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql+asyncpg://old:pw@/x", "ENV": "local"},
            clear=False,
        ):
            get_settings.cache_clear()
            assert "old:pw" in get_settings().database_url
            # Engine doesn't actually need to exist for the test.
            db._engine = None
            db._sessionmaker = None

        # Simulate the secret rotation: env updated to new value.
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql+asyncpg://NEW:PW@/x", "ENV": "local"},
            clear=False,
        ):
            # Pre-fix the refresh did NOT clear the lru_cache so
            # get_settings() kept returning the cached "old:pw" DSN.
            # Post-fix it must clear + re-read.
            await refresh_engine_on_auth_failure()
            assert "NEW:PW" in get_settings().database_url

    @pytest.mark.asyncio
    async def test_refresh_nulls_engine_globals(self) -> None:
        from app import database as db
        from app.database import refresh_engine_on_auth_failure

        # Pretend an engine exists.
        class _StubEngine:
            disposed = False

            async def dispose(self) -> None:
                self.disposed = True

        stub = _StubEngine()
        db._engine = stub  # type: ignore[assignment]
        db._sessionmaker = "sentinel"  # type: ignore[assignment]
        await refresh_engine_on_auth_failure()
        assert db._engine is None
        assert db._sessionmaker is None
        assert stub.disposed

    @pytest.mark.asyncio
    async def test_refresh_survives_dispose_failure(self) -> None:
        """A failed dispose must still null the globals so the next call
        constructs a fresh engine. Pre-fix a raise here would leave the
        old engine cached and the self-heal is permanently broken."""
        from app import database as db
        from app.database import refresh_engine_on_auth_failure

        class _BrokenEngine:
            async def dispose(self) -> None:
                raise RuntimeError("simulated dispose failure")

        db._engine = _BrokenEngine()  # type: ignore[assignment]
        db._sessionmaker = "sentinel"  # type: ignore[assignment]
        await refresh_engine_on_auth_failure()  # must not raise
        assert db._engine is None
        assert db._sessionmaker is None


class TestProductionReadinessNonFatal:
    """create_app() must not crash on missing prod secrets; the error
    must be captured and surfaced via /readyz body."""

    def test_misconfigured_prod_stashes_error_on_app_state(self) -> None:
        """When env=prod + a required secret is missing, the app should
        STILL be constructable (so uvicorn binds + /readyz can respond
        with a useful body). The error message is stashed on
        app.state.prod_readiness_error so /readyz reads it."""
        from app.main import create_app

        # Force prod env with no secrets present.
        with patch.dict(
            os.environ,
            {
                "ENV": "prod",
                "DATABASE_URL": "",  # blank -> fail
                "REDIS_URL": "",
                "GOOGLE_OAUTH_CLIENT_ID": "",
                "GOOGLE_OAUTH_CLIENT_SECRET": "",
                "DMA_BOT_API_KEY": "",
                "RAG_API_BEARER_KEY": "",
                "GCP_PROJECT_ID": "",
                "CLAY_WEBHOOK_URL": "",
                "CLAY_WEBHOOK_SECRET": "",
            },
            clear=False,
        ):
            get_settings.cache_clear()
            try:
                # Pre-fix this raised RuntimeError -- now it captures.
                app = create_app()
                # The error is stashed on app.state for /readyz to read.
                err = getattr(app.state, "prod_readiness_error", None)
                assert err is not None
                assert "Production-readiness check FAILED" in err
            finally:
                get_settings.cache_clear()

    def test_local_env_leaves_state_clean(self) -> None:
        """env=local skips the check entirely; no error stashed."""
        from app.main import create_app

        with patch.dict(os.environ, {"ENV": "local"}, clear=False):
            get_settings.cache_clear()
            try:
                app = create_app()
                err = getattr(app.state, "prod_readiness_error", None)
                assert err is None
            finally:
                get_settings.cache_clear()
