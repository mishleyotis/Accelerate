"""Regression: post_migrate.py must guarantee `dma_insights` has SELECT
on `public.alembic_version` after every run.

The recurring production symptom is Phase 4 of the two-phase deploy
503'ing on `/readyz`:

    attempt 1: status=503 body={"detail":"migration check failed:
      ProgrammingError: (sqlalchemy.dialects.postgresql.asyncpg.
      ProgrammingError) <class 'asyncpg.exceptions.InsufficientPrivilegeError'>:
      permission denied for table alembic_version
      [SQL: SELECT version_num FROM alembic_ver"}

The broad `GRANT ALL ON ALL TABLES IN SCHEMA public TO dma_insights`
inside post_migrate.py is supposed to cover alembic_version. In Cloud
SQL production it's failed to do so on multiple deploys -- some
combination of:
  (a) `postgres` is a member of `cloudsqlsuperuser` but not a true
      superuser; `GRANT ON ALL TABLES IN SCHEMA <s>` from a non-
      superuser only covers tables the grantor OWNS / has GRANT OPTION
      on. If alembic_version was created during initial bootstrap by a
      different role, the broad sweep silently skips it.
  (b) An earlier post_migrate ran against a different DB (the operator
      hand-fixed something via psql to `postgres` DB, alembic_version
      survived there) and the broad sweep never reached this table.

Fix shape (in app/scripts/post_migrate.py):
  1. ALTER TABLE public.alembic_version OWNER TO postgres  (safe;
     savepoint-guarded so insufficient-privilege failure doesn't poison
     the outer transaction)
  2. GRANT SELECT ON public.alembic_version TO dma_insights  (explicit,
     named, idempotent)
  3. has_table_privilege(dma_insights, alembic_version, SELECT) → exit
     non-zero if it ever returns false

These tests exercise the contract end-to-end against a live Postgres so
the failure mode caught in production can no longer reach `/readyz`.
"""
from __future__ import annotations

import os
import subprocess
import sys

import psycopg
import pytest

# Live-PG gate -- skip when running without a real Postgres on hand.
# Match the canonical single-env-var pattern used by every other live-PG
# test in the suite (test_live_endpoint_smoke.py, test_live_db_integration.py,
# test_persona_e2e.py, test_write_surfaces.py, test_startup_diagnostic.py).
# The previous SEED_CI_PG_URL → DATABASE_URL_SYNC fallback evaluated True
# in Cloud Build Stage 1 ("backend-tests") which sets DATABASE_URL_SYNC to
# the placeholder `postgresql+psycopg://x/y` for offline alembic DDL --
# then tries a real connect and crashes with `Name or service not known`.
# Stage 2b sets SEED_CI_PG_URL to the real pgvector sidecar URL; that's
# where the live-PG part of this contract actually runs.
LIVE_DB_URL = os.environ.get("SEED_CI_PG_URL", "")
HAVE_LIVE_DB = bool(LIVE_DB_URL)


def _sync_url(url: str) -> str:
    """Coerce DATABASE_URL flavors into a plain psycopg-compatible DSN."""
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
           .replace("postgresql+psycopg://", "postgresql://")
    )


def test_post_migrate_explicit_alembic_version_grant_section_exists() -> None:
    """Static guard: post_migrate.py source must contain the explicit
    alembic_version handling (ALTER OWNER + GRANT SELECT + verify).
    If any of these go missing the production 503 recurs."""
    from pathlib import Path

    here = Path(__file__).resolve().parents[1]
    src = (here / "app" / "scripts" / "post_migrate.py").read_text()
    assert "ALTER TABLE public.alembic_version OWNER TO postgres" in src
    assert "GRANT SELECT ON public.alembic_version" in src
    assert "has_table_privilege" in src and "alembic_version" in src


def test_post_migrate_restores_alembic_version_select_after_revoke() -> None:
    """Live-PG: revoke dma_insights's SELECT on alembic_version (the
    state the production DB is in after the failing deploy), run
    post_migrate, confirm SELECT is restored. This is the exact
    operator-actionable remediation the new /readyz error tells them
    to execute.

    Production-matching: in Cloud SQL, dma_insights is NOSUPERUSER, so
    the broad GRANT chain in post_migrate.py is the only way it gets
    privileges. Local dev DBs often set dma_insights to SUPERUSER for
    convenience -- if we run the test as-is on such a DB, the REVOKE
    silently no-ops (superusers bypass privilege checks) and the test
    becomes vacuous.

    Rather than skipping in that environment (which leaves the contract
    unverified everywhere it matters), we temporarily ALTER the role
    to NOSUPERUSER inside a try/finally so the original state is always
    restored. This makes the test exercise the REAL contract in EVERY
    environment, matching production behavior."""
    if not HAVE_LIVE_DB:
        pytest.skip("SEED_CI_PG_URL not set — live-PG post_migrate grant test skipped")
    url = _sync_url(LIVE_DB_URL)

    # Snapshot dma_insights's SUPERUSER bit so we can restore it.
    conn = psycopg.connect(url, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = 'dma_insights'"
        )
        row = cur.fetchone()
        assert row is not None, (
            "dma_insights role missing -- run `python -m app.scripts.post_migrate` "
            "once before this test"
        )
        was_superuser = row[0]

    # 2026-07-10 redeployment-QA fix (self-demotion trap): when the DSN's
    # login role IS dma_insights (exactly what docker-compose.yml + the
    # §6.10 local simulate env produce), the ALTER ROLE dma_insights
    # NOSUPERUSER below stripped the CONNECTED role's superuser bit — and
    # the finally-block restore then failed with InsufficientPrivilege
    # (a non-superuser cannot ALTER itself back), failing this test AND
    # leaving the role demoted so every later live-PG test that needs
    # CREATE EXTENSION died on "must be superuser". Bracket the demote/
    # restore through a throwaway superuser admin role instead: created
    # while we are still superuser, used for both ALTERs, dropped after.
    admin_role = "dma_probe_admin_alembic_grant"
    admin_pw = "dma_probe_admin_pw"

    def _admin_conn():
        return psycopg.connect(url, user=admin_role, password=admin_pw, autocommit=True)

    try:
        if was_superuser:
            conn = psycopg.connect(url, autocommit=True)
            with conn.cursor() as cur:
                cur.execute(f"DROP ROLE IF EXISTS {admin_role}")
                cur.execute(
                    f"CREATE ROLE {admin_role} LOGIN SUPERUSER PASSWORD '{admin_pw}'"
                )
            conn.close()
            # Downgrade to match production (NOSUPERUSER) so REVOKE +
            # has_table_privilege actually reflect the privilege state
            # the broad GRANT chain is trying to maintain.
            conn = _admin_conn()
            with conn.cursor() as cur:
                cur.execute("ALTER ROLE dma_insights NOSUPERUSER")
            conn.close()

        # Revoke SELECT to put the DB in the failing-production state.
        # Via the admin connection when we created one: after the demote,
        # the login role may be dma_insights itself, whose REVOKE silently
        # no-ops on a grant whose grantor is postgres (post_migrate's ALTER
        # OWNER makes postgres the grantor on every re-run).
        conn = _admin_conn() if was_superuser else psycopg.connect(url, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("REVOKE SELECT ON public.alembic_version FROM dma_insights")
            cur.execute(
                "SELECT has_table_privilege('dma_insights', 'public.alembic_version', 'SELECT')"
            )
            assert cur.fetchone()[0] is False, (
                "REVOKE didn't take effect -- another GRANT path is still in play"
            )
        conn.close()

        # Run post_migrate -- the new fix path must re-grant SELECT.
        # Production contract: post_migrate connects as a SUPERUSER-ish role
        # distinct from dma_insights (the Cloud SQL postgres DSN). When this
        # test demoted a same-role login DSN, hand post_migrate the admin
        # DSN instead — running it as the just-demoted dma_insights would
        # no-op the GRANT (non-owner, no grant option) and exit 6 for an
        # environment reason production never has.
        pm_url = url
        if was_superuser:
            from urllib.parse import urlsplit, urlunsplit

            parts = urlsplit(url)
            host = parts.hostname or "localhost"
            port = f":{parts.port}" if parts.port else ""
            pm_url = urlunsplit((
                parts.scheme, f"{admin_role}:{admin_pw}@{host}{port}",
                parts.path, parts.query, parts.fragment,
            ))
        env = {**os.environ, "DATABASE_URL_SYNC": pm_url}
        result = subprocess.run(
            [sys.executable, "-m", "app.scripts.post_migrate"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"post_migrate.py exited {result.returncode}.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        # The verification line is the load-bearing signal that the
        # explicit alembic_version grant landed.
        assert (
            "has_table_privilege(dma_insights, alembic_version, SELECT) = True"
            in result.stdout
        ), (
            f"post_migrate didn't confirm SELECT was restored:\n{result.stdout}"
        )

        # And the actual privilege bit is back.
        conn = psycopg.connect(url, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT has_table_privilege('dma_insights', 'public.alembic_version', 'SELECT')"
            )
            assert cur.fetchone()[0] is True
        conn.close()
    finally:
        # Always restore the original SUPERUSER bit so subsequent tests
        # that expect a SUPERUSER dma_insights (seed_ci, write_surfaces,
        # etc.) keep working. Restore runs on the ADMIN connection — the
        # login role may be the just-demoted dma_insights itself, which
        # can no longer self-promote.
        if was_superuser:
            conn = _admin_conn()
            with conn.cursor() as cur:
                cur.execute("ALTER ROLE dma_insights SUPERUSER")
            conn.close()
            conn = psycopg.connect(url, autocommit=True)
            with conn.cursor() as cur:
                # post_migrate (run via the admin DSN) leaves ALTER DEFAULT
                # PRIVILEGES entries owned by the admin role; DROP OWNED
                # clears them (it owns no real objects) so the role drops.
                cur.execute(f"DROP OWNED BY {admin_role}")
                cur.execute(f"DROP ROLE IF EXISTS {admin_role}")
            conn.close()


def test_post_migrate_idempotent_when_grants_already_in_place() -> None:
    """Live-PG: running post_migrate.py twice in a row must succeed --
    ALTER OWNER to the existing owner is a no-op, GRANT SELECT to a
    user that already has it is a no-op."""
    if not HAVE_LIVE_DB:
        pytest.skip("SEED_CI_PG_URL not set — live-PG post_migrate grant test skipped")
    url = _sync_url(LIVE_DB_URL)
    env = {**os.environ, "DATABASE_URL_SYNC": url}
    for run in (1, 2):
        result = subprocess.run(
            [sys.executable, "-m", "app.scripts.post_migrate"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"post_migrate.py exited {result.returncode} on run {run}.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert (
            "has_table_privilege(dma_insights, alembic_version, SELECT) = True"
            in result.stdout
        ), (
            f"run {run} stdout missing the alembic_version privilege "
            f"confirmation:\n{result.stdout}"
        )
