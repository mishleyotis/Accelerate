"""Tests for `app.services.sync_dsn.resolve_sync_dsn`.

Single source of truth for "give me a psycopg URL" used by
job_executions_db, synthesis_cache_db, and workers/ccg_loader. The
2026-05-28 production incident was caused by each of those sites
reading `DATABASE_URL_SYNC` directly with no fallback while the
terraform worker-job spec only injected `DATABASE_URL` (asyncpg).
Result: each site silently no-op'd, and the admin UI / ccg_loader_runs
table looked empty even though the workers ran successfully.

Test matrix (one row per resolution branch):

  | DATABASE_URL_SYNC | DATABASE_URL                   | expected
  +-------------------+--------------------------------+-----------
  | <set>             | <anything>                     | DATABASE_URL_SYNC (explicit wins)
  | <unset>           | postgresql+asyncpg://...       | replace +asyncpg → +psycopg
  | <unset>           | postgresql://...               | rewrite to postgresql+psycopg://
  | <unset>           | postgresql+otherdriver://...   | return as-is (caller's problem)
  | <unset>           | <unset>                        | None
"""
from __future__ import annotations

import pytest


def test_explicit_sync_dsn_wins(monkeypatch):
    """DATABASE_URL_SYNC always beats any derivation from DATABASE_URL —
    the migrations job uses a DIFFERENT secret (superuser) and we
    must not override its explicit DSN with the app-user async one."""
    from app.services.sync_dsn import resolve_sync_dsn

    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg://super:s@h/d")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:a@h/d")

    assert resolve_sync_dsn() == "postgresql+psycopg://super:s@h/d"


def test_derives_sync_from_asyncpg(monkeypatch):
    """The production worker case: only DATABASE_URL with +asyncpg is
    set; we must derive the +psycopg form by string-replace."""
    from app.services.sync_dsn import resolve_sync_dsn

    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://dma:pw@/dma?host=/cloudsql/proj:reg:inst",
    )

    out = resolve_sync_dsn()
    assert out is not None
    assert out.startswith("postgresql+psycopg://")
    assert "+asyncpg" not in out
    # Password / host / params preserved exactly.
    assert "dma:pw@" in out
    assert "host=/cloudsql/proj:reg:inst" in out


def test_rewrites_bare_postgresql_url(monkeypatch):
    """Some envs (local dev) set `postgresql://` with no driver. We
    rewrite to `postgresql+psycopg://` so SQLAlchemy picks the
    intended driver instead of psycopg2 (not installed)."""
    from app.services.sync_dsn import resolve_sync_dsn

    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:pw@localhost/db")

    out = resolve_sync_dsn()
    assert out == "postgresql+psycopg://app:pw@localhost/db"


def test_returns_none_when_both_unset(monkeypatch):
    """Test/local env with no DB at all — return None so callers can
    short-circuit cleanly (vs raising during import)."""
    from app.services.sync_dsn import resolve_sync_dsn

    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert resolve_sync_dsn() is None


def test_returns_none_under_simulated_cloud_build_secret_manager_access(
    monkeypatch,
):
    """Cloud Build worker SA has secretAccessor; without the
    conftest._hermetic_secret_manager autouse fixture, this test fails
    (resolver falls through to Secret Manager and returns the prod DSN).

    Regression lock for the 2026-05-29 CI failure: stage 1 backend-tests
    failed on Cloud Build because Secret Manager returned a real value
    even after `monkeypatch.delenv` cleared both DSN env vars.
    """
    from app.services import sync_dsn

    # Force `_try_secret_manager` to behave as it would on Cloud Build:
    # ADC-authenticated, secret exists, payload is the prod DSN.
    sentinel_dsn = (
        "postgresql+psycopg://prod_leak:should_never_appear@/db"
        "?host=/cloudsql/digital-maturity-assessor:us-central1:dma-pg"
    )
    monkeypatch.setattr(
        sync_dsn, "_try_secret_manager", lambda: sentinel_dsn,
    )
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # The autouse fixture sets DMA_DISABLE_SECRET_DSN_FALLBACK=1; the
    # resolver MUST short-circuit before calling `_try_secret_manager`.
    out = sync_dsn.resolve_sync_dsn()
    assert out is None, (
        f"conftest._hermetic_secret_manager autouse fixture is broken "
        f"or absent — resolver returned {out!r} when it should have "
        f"short-circuited via DMA_DISABLE_SECRET_DSN_FALLBACK=1. "
        f"Cloud Build CI will leak the prod DSN into pytest stderr."
    )


def test_opt_out_of_hermetic_fixture_restores_secret_manager_fallback(
    monkeypatch,
):
    """Tests that legitimately want the Secret Manager branch opt out
    of the autouse fixture by delenv-ing the guard. Lock this contract
    so a future engineer doesn't refactor the fixture in a way that
    forecloses the opt-out.
    """
    from app.services import sync_dsn

    sentinel_dsn = "postgresql+psycopg://from-secret-mgr@/db"
    monkeypatch.setattr(
        sync_dsn, "_try_secret_manager", lambda: sentinel_dsn,
    )
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Explicit opt-out.
    monkeypatch.delenv("DMA_DISABLE_SECRET_DSN_FALLBACK", raising=False)

    assert sync_dsn.resolve_sync_dsn() == sentinel_dsn


def test_returns_as_is_for_unknown_driver(monkeypatch):
    """Pathological case — `postgresql+something://` — return as-is.
    Caller (SQLAlchemy) will surface the unsupported-driver error
    rather than us silently rewriting in a wrong direction."""
    from app.services.sync_dsn import resolve_sync_dsn

    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+otherdriver://h/d")

    assert resolve_sync_dsn() == "postgresql+otherdriver://h/d"


def test_handles_whitespace_padding(monkeypatch):
    """Secret Manager occasionally returns values with a trailing
    newline. Strip both ends so the derived URL doesn't carry
    surprise whitespace into SQLAlchemy."""
    from app.services.sync_dsn import resolve_sync_dsn

    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", "  postgresql+asyncpg://a:b@h/d\n")

    out = resolve_sync_dsn()
    assert out is not None
    assert out == "postgresql+psycopg://a:b@h/d"


# ── Integration: the three consumer call-sites use the resolver ───────


def test_job_executions_db_uses_resolver(monkeypatch):
    """`job_executions_db._get_engine` must go through `resolve_sync_dsn`
    so the +asyncpg → +psycopg fallback is applied. Regression-locked
    test: without this, the 2026-05-28 incident silently returns.
    """
    from app.services import job_executions_db as je

    monkeypatch.setattr(je, "_engine", None, raising=False)
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://a:b@h/d")

    captured: dict[str, str] = {}

    def _fake_create_engine(url, **_kwargs):
        captured["url"] = url
        return object()

    monkeypatch.setattr(je, "create_engine", _fake_create_engine)
    je._get_engine()

    assert captured["url"] == "postgresql+psycopg://a:b@h/d"


def test_synthesis_cache_db_uses_resolver(monkeypatch):
    """Same regression lock for synthesis_cache_db. Pre-fix, every
    post-commit cache-invalidation raised silently → cached
    synthesis stayed stale across re-ingests."""
    from app.services import synthesis_cache_db as sc

    monkeypatch.setattr(sc, "_engine", None, raising=False)
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://a:b@h/d")

    captured: dict[str, str] = {}

    def _fake_create_engine(url, **_kwargs):
        captured["url"] = url
        return object()

    monkeypatch.setattr(sc, "create_engine", _fake_create_engine)
    sc._get_engine()

    assert captured["url"] == "postgresql+psycopg://a:b@h/d"


def test_job_executions_db_raises_when_resolver_returns_none(monkeypatch):
    """Belt-and-braces — when both DSNs are unset, the call site
    raises loudly, NOT silently. Otherwise misconfigurations hide
    behind the runner's `_safe_*` warning swallowing."""
    from app.services import job_executions_db as je

    monkeypatch.setattr(je, "_engine", None, raising=False)
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="sync DSN"):
        je._get_engine()
