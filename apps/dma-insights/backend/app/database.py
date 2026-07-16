"""Async SQLAlchemy engine + session factory.

Self-healing contract (2026-06):

  - `pool_pre_ping=True` (already enabled): every checkout pings the
    connection first; stale/closed sockets get replaced transparently.
    Closes the Cloud SQL idle-disconnect class of bug (Cloud SQL drops
    TCP keepalive after ~10min of pool inactivity).
  - `pool_recycle=1800`: force-recycle connections every 30 min so the
    pool doesn't accumulate connections older than the Cloud SQL
    server's `idle_in_transaction_session_timeout`. Prevents the
    "FATAL: terminating connection due to administrator command"
    that surfaces during Cloud SQL maintenance windows.
  - `refresh_engine_on_auth_failure()`: when an InvalidPasswordError
    is observed in `/readyz` or a request handler, the engine globals
    are nulled so the next request rebuilds the engine from a fresh
    `get_settings()` read. Pairs with the migrate.sh DMA_SECRET_ROLL
    trick — together they make the backend self-heal against secret
    rotation without a manual revision roll.

The engine is built lazily via `get_engine()`; tests reset both module
globals via `_engine = None` + `_sessionmaker = None`. `get_settings()`
is also reset by tests that mutate DATABASE_URL post-import.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

log = structlog.get_logger(__name__)


def _make_engine() -> AsyncEngine:
    s = get_settings()
    return create_async_engine(
        s.database_url,
        # pool_pre_ping: SELECT 1 on every checkout to skip dead sockets
        # (Cloud SQL idle-disconnect, NAT timeout, etc.).
        pool_pre_ping=True,
        # pool_recycle: force-rotate connections every 30 min so we
        # never serve a connection older than Cloud SQL's typical
        # `idle_in_transaction_session_timeout`.
        pool_recycle=1800,
        pool_size=10,
        max_overflow=20,
        echo=False,
        future=True,
    )


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


async def refresh_engine_on_auth_failure() -> None:
    """Force the next request to rebuild the engine + sessionmaker
    AGAINST A FRESH SETTINGS READ.

    Invoked by `/readyz` and the global exception handler when an
    asyncpg `InvalidPasswordError` is observed -- the secret was
    rotated since the engine was constructed (typical after a
    `force-heal-db.sh` heal in the deploy pipeline). Two things happen:

      1. The cached `Settings` instance is evicted via
         `get_settings.cache_clear()`. Without this, Pydantic Settings
         keeps the SAME instance for the lifetime of the process and
         re-instantiating Settings (next get_settings() call) re-reads
         every env var -- which on Cloud Run picks up the freshly-
         injected secret version when DMA_SECRET_ROLL forced a
         revision restart between heals.

         Pre-2026-06-05 this clear was missing -- the engine was
         rebuilt against the SAME stale `database_url` and the
         /readyz self-heal path was a no-op. Anything reading
         settings.database_url after a heal kept seeing the old DSN
         until the container itself restarted.

      2. The cached engine + sessionmaker are nulled and disposed.
         Next request -> `get_engine()` -> `_make_engine()` ->
         `get_settings()` (now fresh) -> create_async_engine with the
         current DSN. Connections are SCRAM-authenticated against
         whichever password Cloud SQL holds RIGHT NOW.

    Best-effort: if the dispose itself raises (already-disposed, etc.)
    we log + continue -- the engine globals are nulled either way so
    the next call constructs a fresh one.
    """
    global _engine, _sessionmaker
    old_engine = _engine
    _engine = None
    _sessionmaker = None
    # Critical: drop the Settings cache so the next get_settings()
    # call re-reads `database_url` from os.environ. Without this the
    # engine refresh is a no-op and we'd loop forever 503'ing.
    try:
        get_settings.cache_clear()
    except Exception as e:
        log.warning(
            "database.settings_cache_clear_failed",
            err=str(e)[:200],
        )
    if old_engine is not None:
        try:
            await old_engine.dispose()
            log.info("database.engine_refreshed_after_auth_failure")
        except Exception as e:
            log.warning(
                "database.engine_dispose_failed",
                err=str(e)[:200],
            )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a single async session per request."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Standalone async session for workers and one-off scripts."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
