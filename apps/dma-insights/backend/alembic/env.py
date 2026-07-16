"""Alembic env — uses the sync DSN from settings, never the async one.

╔══════════════════════════════════════════════════════════════════════╗
║  ERROR HISTORY — keep this list in sync with new failure modes.      ║
╠══════════════════════════════════════════════════════════════════════╣
║  A1  StringDataRightTruncation: value too long for char varying(32)  ║
║      → alembic's alembic_version.version_num defaults to VARCHAR(32) ║
║      → revision ID '021_runs_data_source_drive_backfill' was 35 chars║
║      → migration body executed but the version UPDATE failed →        ║
║        transaction rolled back → operator saw a fresh-looking SQL    ║
║        error with no hint that the column width was the cause       ║
║      FIX: _ensure_version_column_wide_enough() below runs BEFORE     ║
║           any context.run_migrations(); idempotent ALTER to          ║
║           VARCHAR(128). Combined with author-time CI guard           ║
║           (test_migration_id_lengths.py) + L1 rename of the          ║
║           offending revision to 23 chars.                            ║
║                                                                      ║
║  A2  DATABASE_URL with +asyncpg/+aiopg dialects rejected by alembic  ║
║      → 'Can't load plugin: sqlalchemy.dialects:postgresql.asyncpg'   ║
║      → operator passed the async DSN to migrations by mistake        ║
║      FIX: _sync_url() reads DATABASE_URL_SYNC env var FIRST so the   ║
║           sync DSN is used unambiguously                             ║
║                                                                      ║
║  A3  Autogen produced empty migrations because models weren't loaded ║
║      → 'no changes detected' on a fresh migration                    ║
║      FIX: target_metadata = None (we hand-write all migrations);     ║
║           never use --autogenerate                                   ║
║                                                                      ║
║  A4  Migration ran twice on retry because the body wasn't            ║
║      idempotent → 'already exists' on second attempt                 ║
║      FIX (in migration authors' hands): every CREATE uses            ║
║           IF NOT EXISTS; every INSERT uses ON CONFLICT DO NOTHING    ║
║                                                                      ║
║  A5  generation expression is not immutable (migration 018)          ║
║      → can't use CURRENT_DATE in STORED GENERATED columns            ║
║      FIX (not here): trigger-based maintained columns in 018         ║
╚══════════════════════════════════════════════════════════════════════╝

Defence-in-depth: every online run widens `alembic_version.version_num`
from alembic's default VARCHAR(32) to VARCHAR(128) BEFORE any
migrations execute. The default is too narrow for descriptive slugs
(e.g. `021_runs_data_source_drive_backfill` = 35 chars) and the
failure mode is opaque — alembic UPDATEs alembic_version, psycopg
raises StringDataRightTruncation, the DDL transaction rolls back,
the migration body is undone, and the operator sees only the
truncation error with no hint that the column is the cause.

The widener is idempotent — it short-circuits when the column is
already ≥ 128. State branches:

  table_missing         → skip (first-ever run; alembic creates it next)
  column_already_wide   → skip (NO-OP)
  column_narrow         → ALTER + commit
  ddl_failed_perm       → log + continue (the migration may still
                          succeed if every revision ID happens to
                          fit; the CI guard test catches overruns
                          at author time anyway)
"""
from __future__ import annotations

import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migrations are pure DDL — no model metadata autogen needed. Every migration
# is written by hand to keep the schema reviewable.
target_metadata = None

_log = logging.getLogger("alembic.env")


def _sync_url() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        config.get_main_option("sqlalchemy.url") or "",
    )


def _ensure_version_column_wide_enough(connection) -> None:
    """Widen alembic_version.version_num to VARCHAR(128) if needed.

    Runs OUTSIDE the per-migration transaction so it commits
    independently and is observable from the next connection.
    """
    try:
        result = connection.execute(
            text(
                "SELECT character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_name='alembic_version' "
                "  AND column_name='version_num'"
            )
        ).first()
    except Exception as exc:  # pragma: no cover — diagnostic only
        _log.warning("version-col width check failed: %s", exc)
        return

    if result is None:
        # State: table_missing — alembic will create it on first commit
        # with the default VARCHAR(32). Subsequent runs widen it.
        _log.info("alembic_version does not exist yet; will widen on next run")
        return

    width = result[0]
    if width is None or width >= 128:
        return  # State: column_already_wide — NO-OP

    # State: column_narrow — widen + commit independently.
    try:
        connection.execute(
            text(
                "ALTER TABLE alembic_version "
                "ALTER COLUMN version_num TYPE VARCHAR(128)"
            )
        )
        connection.commit()
        _log.info(
            "widened alembic_version.version_num: %d -> 128", width
        )
    except Exception as exc:
        # State: ddl_failed_perm — keep going; per-migration ALTER ran
        # in a separate transaction, so this exception doesn't poison
        # the upcoming run_migrations() call.
        _log.warning("could not widen version_num: %s", exc)


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        _ensure_version_column_wide_enough(connection)
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        # SQLAlchemy 2.0 connection: explicit commit is required —
        # `begin_transaction()`'s context-exit does not propagate to
        # the underlying DBAPI connection if alembic itself didn't
        # commit (older alembic+sqlalchemy 1.4 auto-committed here).
        # Without this the migration log shows success but tables
        # never persist past connection close.
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
