"""D1: /readyz must catch migration-head drift in prod.

A deploy that ships container image @ revision N but lands against a
DB still at revision N-1 silently breaks features that depend on the
new columns/tables — until the affected endpoint is hit, the deploy
looks green. This test pins the contract:

    env=prod, alembic_version != code head → 503
    env=prod, alembic_version == code head → 200 with migration_head
    env=local                               → 200 (skip check)
    env=prod, no alembic_version table      → 503 (DB never migrated)
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_app() -> Any:
    """Re-import create_app so each test gets a fresh settings cache.
    The production-readiness guard (added 2026-05-24 — see §36) is
    patched out here because these tests only exercise /readyz; the
    guard has its own dedicated test file."""
    from app.config import get_settings
    from app.main import create_app
    get_settings.cache_clear()
    with patch("app.main.assert_production_ready"):
        return create_app()


def _mock_engine_returning(version_num: str | None) -> MagicMock:
    """Build an async engine mock whose conn.execute returns version_num."""
    engine = MagicMock()
    conn = MagicMock()

    async def aenter(self):
        return conn

    async def aexit(self, exc_type, exc, tb):
        return False

    conn_ctx = MagicMock()
    conn_ctx.__aenter__ = aenter
    conn_ctx.__aexit__ = aexit
    engine.connect = MagicMock(return_value=conn_ctx)

    async def execute(stmt):
        result = MagicMock()
        if "SELECT 1" in str(stmt):
            result.scalar_one_or_none = MagicMock(return_value=1)
            return result
        # alembic_version row
        result.scalar_one_or_none = MagicMock(return_value=version_num)
        return result

    conn.execute = AsyncMock(side_effect=execute)
    return engine


def _mock_script_head(head: str | None) -> MagicMock:
    """Mock alembic.ScriptDirectory.from_config to return a fixed head."""
    sd = MagicMock()
    sd.get_current_head = MagicMock(return_value=head)
    return sd


def _reset_settings_cache():
    from app.config import get_settings
    get_settings.cache_clear()


@pytest.fixture
def prod_env(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    _reset_settings_cache()
    yield
    monkeypatch.delenv("ENV", raising=False)
    _reset_settings_cache()


@pytest.fixture
def local_env(monkeypatch):
    monkeypatch.setenv("ENV", "local")
    _reset_settings_cache()
    yield
    monkeypatch.delenv("ENV", raising=False)
    _reset_settings_cache()


def test_readyz_local_reports_head_without_drift_503(local_env):
    """env=local must return 200 even when DB+Redis are unreachable —
    pytest fixtures don't spin up a real DB.

    2026-06-11 deploy-simulation finding: migration_head was prod-gated,
    so post-deploy-smoke.sh's A5 readyz check false-failed against every
    non-prod environment ("Deploy is silently broken" on a healthy local
    stack). The contract is now: the head is REPORTED in every env
    (best-effort — absent only when alembic state is unreadable), while
    the drift 503 stays prod-only. Local must never 503 on drift."""
    app = _make_app()
    with TestClient(app) as client:
        r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ready", "degraded")


def test_readyz_prod_passes_when_db_head_matches_code_head(prod_env):
    """env=prod with matching heads → 200 with migration_head reported."""
    engine = _mock_engine_returning("020_job_executions")
    script = _mock_script_head("020_job_executions")

    with patch("app.database.get_engine", return_value=engine), \
         patch("app.deps.get_redis", new=AsyncMock(return_value=AsyncMock(ping=AsyncMock(return_value=True)))), \
         patch("alembic.script.ScriptDirectory.from_config", return_value=script):
        app = _make_app()
        with TestClient(app) as client:
            r = client.get("/readyz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert body["migration_head"] == "020_job_executions"


def test_readyz_prod_fails_503_on_migration_drift(prod_env):
    """env=prod with DB head behind code head → 503 with drift message."""
    engine = _mock_engine_returning("019_synthesis_cache")
    script = _mock_script_head("020_job_executions")

    with patch("app.database.get_engine", return_value=engine), \
         patch("app.deps.get_redis", new=AsyncMock(return_value=AsyncMock(ping=AsyncMock(return_value=True)))), \
         patch("alembic.script.ScriptDirectory.from_config", return_value=script):
        app = _make_app()
        with TestClient(app) as client:
            r = client.get("/readyz")
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert "migration drift" in detail
    assert "019_synthesis_cache" in detail
    assert "020_job_executions" in detail
    assert "alembic upgrade head" in detail


def test_readyz_prod_fails_503_when_alembic_version_table_missing(prod_env):
    """env=prod with no alembic_version table → 503 (DB never migrated)."""
    engine = MagicMock()
    conn = MagicMock()

    async def aenter(self):
        return conn

    async def aexit(self, exc_type, exc, tb):
        return False

    conn_ctx = MagicMock()
    conn_ctx.__aenter__ = aenter
    conn_ctx.__aexit__ = aexit
    engine.connect = MagicMock(return_value=conn_ctx)

    call_count = [0]

    async def execute(stmt):
        call_count[0] += 1
        result = MagicMock()
        if "SELECT 1" in str(stmt):
            result.scalar_one_or_none = MagicMock(return_value=1)
            return result
        # 2nd call (alembic_version) — raise the relation-missing error
        raise RuntimeError("relation \"alembic_version\" does not exist")

    conn.execute = AsyncMock(side_effect=execute)

    with patch("app.database.get_engine", return_value=engine), \
         patch("app.deps.get_redis", new=AsyncMock(return_value=AsyncMock(ping=AsyncMock(return_value=True)))):
        app = _make_app()
        with TestClient(app) as client:
            r = client.get("/readyz")
    assert r.status_code == 503, r.text
    assert "migration check failed" in r.json()["detail"]


def test_readyz_prod_fails_503_on_db_unavailable(prod_env):
    """env=prod with DB down → 503 (existing behaviour preserved)."""
    engine = MagicMock()
    conn = MagicMock()

    async def aenter(self):
        return conn

    async def aexit(self, exc_type, exc, tb):
        return False

    conn_ctx = MagicMock()
    conn_ctx.__aenter__ = aenter
    conn_ctx.__aexit__ = aexit
    engine.connect = MagicMock(return_value=conn_ctx)

    async def execute(stmt):
        raise TimeoutError()

    conn.execute = AsyncMock(side_effect=execute)

    with patch("app.database.get_engine", return_value=engine), \
         patch("app.deps.get_redis", new=AsyncMock(return_value=AsyncMock(ping=AsyncMock(return_value=True)))):
        app = _make_app()
        with TestClient(app) as client:
            r = client.get("/readyz")
    assert r.status_code == 503, r.text
    assert "db unavailable" in r.json()["detail"]


def test_readyz_prod_503_on_alembic_version_insufficient_privilege_surfaces_remediation(prod_env):
    """env=prod + dma_insights lacks SELECT on alembic_version → 503 with
    the operator-actionable remediation embedded in the detail, NOT just
    a truncated SQLAlchemy ProgrammingError trace.

    This is the exact Phase 4 trace operators have hit on three deploys:
        503 body={"detail":"migration check failed: ProgrammingError: …
        InsufficientPrivilegeError: permission denied for table
        alembic_version [SQL: SELECT version_num FROM alembic_ver…

    The detail must now tell the operator to re-run the migrations job
    so the post_migrate.py ALTER OWNER + explicit GRANT chain fires."""
    engine = MagicMock()
    conn = MagicMock()

    async def aenter(self):
        return conn

    async def aexit(self, exc_type, exc, tb):
        return False

    conn_ctx = MagicMock()
    conn_ctx.__aenter__ = aenter
    conn_ctx.__aexit__ = aexit
    engine.connect = MagicMock(return_value=conn_ctx)

    async def execute(stmt):
        result = MagicMock()
        if "SELECT 1" in str(stmt):
            result.scalar_one_or_none = MagicMock(return_value=1)
            return result
        # The SELECT version_num FROM alembic_version path — raise the
        # same error shape SQLAlchemy + asyncpg produce when the app
        # user lacks SELECT on the table.
        raise RuntimeError(
            "(sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) "
            "<class 'asyncpg.exceptions.InsufficientPrivilegeError'>: "
            "permission denied for table alembic_version"
        )

    conn.execute = AsyncMock(side_effect=execute)

    with patch("app.database.get_engine", return_value=engine), \
         patch("app.deps.get_redis", new=AsyncMock(return_value=AsyncMock(ping=AsyncMock(return_value=True)))):
        app = _make_app()
        with TestClient(app) as client:
            r = client.get("/readyz")
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    # The detail must surface the *remediation*, not just the trace.
    assert "lacks SELECT" in detail, detail
    assert "alembic_version" in detail, detail
    assert "dma-insights-migrations" in detail, detail
    # The underlying error type is still attached so log analysis works.
    assert "InsufficientPrivilegeError" in detail, detail
