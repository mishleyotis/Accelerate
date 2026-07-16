"""Post-migration grants for the app database user.

Runs once after `alembic upgrade head` (from the dma-insights-migrations
Cloud Run Job). All migrations execute as the `postgres` superuser, so
the resulting tables / sequences / functions are owned by `postgres`.
Postgres 15's `public` schema lockdown means non-owners get
`permission denied for schema public` (or `permission denied for table
users`) on every INSERT until USAGE + per-object grants are issued
explicitly — which is exactly the failure mode the backend's auth
handler hits on first sign-in.

This script connects as the superuser (via DATABASE_URL_SYNC) and
runs the GRANT chain that lets the `dma_insights` app user own its
runtime tables.

Idempotent: re-running is a no-op (Postgres grants are upserts).
"""
from __future__ import annotations

import os
import sys

import psycopg

APP_USER = "dma_insights"


def _grant_statements(app_db: str) -> list[str]:
    """Grant chain for the app user. The DATABASE name is taken from the
    live connection (current_database()) rather than a hardcoded
    'dma_insights' — the 2026-06-10 fresh-DB deploy simulation showed the
    hardcode's `GRANT CONNECT ON DATABASE dma_insights` failing on every
    target whose DB isn't literally named dma_insights (CI sidecar,
    staging, local sim). Production's DB *is* dma_insights, so this is a
    no-op there and a correctness fix everywhere else."""
    return [
        f'GRANT CONNECT ON DATABASE "{app_db}" TO {APP_USER}',
        f"GRANT USAGE, CREATE ON SCHEMA public TO {APP_USER}",
        f"GRANT ALL ON ALL TABLES    IN SCHEMA public TO {APP_USER}",
        f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {APP_USER}",
        f"GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO {APP_USER}",
        # Future-proof: anything migrations add later inherits the grants.
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES    TO {APP_USER}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {APP_USER}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO {APP_USER}",
    ]


def main() -> None:
    url = os.environ.get("DATABASE_URL_SYNC")
    if not url:
        print("ERROR: DATABASE_URL_SYNC env not set", file=sys.stderr)
        sys.exit(2)
    # psycopg connects with the plain postgresql:// scheme — strip any
    # SQLAlchemy driver suffix that the migration DSN carries.
    url = url.replace("postgresql+psycopg://", "postgresql://")

    print("post_migrate: connecting as superuser via DATABASE_URL_SYNC…", flush=True)
    try:
        conn = psycopg.connect(url, autocommit=True)
    except Exception as e:
        print(f"FATAL: superuser connect failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        sys.exit(3)

    with conn, conn.cursor() as cur:
        # Sanity-check who we are + which DB we're on. If this prints
        # anything other than (postgres, dma_insights, public) something
        # is fundamentally misconfigured.
        cur.execute("SELECT current_user, current_database(), current_schema")
        ident = cur.fetchone()
        print(f"post_migrate: identity = {ident}", flush=True)
        # DB name from the live connection — drives GRANT CONNECT.
        grant_statements = _grant_statements(ident[1])

        # Confirm the target app user actually exists; if not, the
        # grants will silently succeed (postgres allows GRANT TO a
        # non-existent role) and we'd never know.
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_USER,))
        if cur.fetchone() is None:
            print(
                f"FATAL: role {APP_USER!r} does not exist; "
                "terraform's null_resource.db_app_user_setup should "
                "have created it. Re-apply with -replace=null_resource.db_app_user_setup.",
                file=sys.stderr, flush=True,
            )
            sys.exit(4)

        # Count tables we're about to grant on — there should be ≥ 28
        # after migrations land. If 0, alembic never ran.
        cur.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
        )
        n_tables = cur.fetchone()[0]
        print(f"post_migrate: {n_tables} tables in public", flush=True)
        if n_tables == 0:
            print(
                "FATAL: 0 tables in public — alembic upgrade head did "
                "not run or targeted a different database.",
                file=sys.stderr, flush=True,
            )
            sys.exit(5)

        # Run the grants.
        for stmt in grant_statements:
            print(f"  exec: {stmt}", flush=True)
            cur.execute(stmt)

        # ── Belt-and-braces: explicit alembic_version handling ──────────
        # The recurring production symptom is Phase 4 /readyz 503'ing
        # with `InsufficientPrivilegeError: permission denied for table
        # alembic_version` even after the broad `GRANT ALL ON ALL TABLES
        # IN SCHEMA public` above. Two real-world causes seen in Cloud
        # SQL:
        #   (a) On a Cloud SQL bootstrap, the very first alembic upgrade
        #       can land before the postgres role is fully promoted to
        #       cloudsqlsuperuser-equivalent rights. The alembic_version
        #       table is then owned by `cloudsqlsuperuser`, not
        #       `postgres`. `GRANT ALL ON ALL TABLES IN SCHEMA public`
        #       run AS postgres silently skips tables postgres doesn't
        #       own — leaving alembic_version un-granted.
        #   (b) An older post_migrate ran against a different DB and the
        #       alembic_version that's there now was hand-created
        #       outside the normal chain.
        # The explicit ALTER OWNER + GRANT below is idempotent and fixes
        # both cases. Wrapped in a small savepoint so an ownership-change
        # failure (insufficient privilege as postgres) doesn't poison the
        # outer transaction.
        cur.execute(
            "SELECT tableowner FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = 'alembic_version'"
        )
        row = cur.fetchone()
        if row is None:
            print(
                "FATAL: alembic_version table not found in public schema. "
                "alembic upgrade head did not run, or ran against a "
                "different DB. Re-check DATABASE_URL_SYNC.",
                file=sys.stderr, flush=True,
            )
            sys.exit(5)
        alembic_owner = row[0]
        print(
            f"post_migrate: alembic_version owner = {alembic_owner!r}",
            flush=True,
        )
        if alembic_owner != "postgres":
            # Re-own to postgres so subsequent GRANTs from postgres can
            # reach it. If we lack rights (rare — postgres should be a
            # cloudsqlsuperuser member that can REASSIGN), surface the
            # error with a remediation hint rather than crashing.
            try:
                print(
                    f"  exec: ALTER TABLE public.alembic_version OWNER TO postgres "
                    f"(was {alembic_owner!r})",
                    flush=True,
                )
                cur.execute(
                    "ALTER TABLE public.alembic_version OWNER TO postgres"
                )
            except Exception as e:
                print(
                    f"  warn: could not re-own alembic_version: "
                    f"{type(e).__name__}: {e}. Continuing — the explicit "
                    f"GRANT below uses the existing owner's privileges.",
                    file=sys.stderr, flush=True,
                )
        # Explicit grant, even if the broad sweep above already covered
        # it. Idempotent.
        print(
            f"  exec: GRANT SELECT ON public.alembic_version TO {APP_USER}",
            flush=True,
        )
        cur.execute(
            f"GRANT SELECT ON public.alembic_version TO {APP_USER}"
        )

        # Verify by reading back the privilege bits on the `users`
        # table — the exact table the auth handler INSERTs into.
        # If this returns no rows for INSERT/SELECT/UPDATE/DELETE
        # for `dma_insights`, the grants didn't stick and we need
        # to fail loudly.
        cur.execute(
            """
            SELECT privilege_type
              FROM information_schema.role_table_grants
             WHERE grantee  = %s
               AND table_schema = 'public'
               AND table_name   = 'users'
             ORDER BY privilege_type
            """,
            (APP_USER,),
        )
        privs = [r[0] for r in cur.fetchall()]
        print(f"post_migrate: {APP_USER} privileges on public.users = {privs}", flush=True)
        required = {"INSERT", "SELECT", "UPDATE", "DELETE"}
        missing = required - set(privs)
        if missing:
            print(
                f"FATAL: {APP_USER} is missing {sorted(missing)} on public.users "
                f"AFTER running grants. Possible causes: (a) the users table "
                f"is owned by a role other than postgres (check `\\dt public.users` "
                f"in psql); (b) the grants ran against a different database "
                f"(check the DATABASE_URL_SYNC secret).",
                file=sys.stderr, flush=True,
            )
            sys.exit(6)

        # Verify alembic_version is readable by the app user — this is
        # the exact SELECT the backend's /readyz probe runs at startup.
        # If we got the grants right but readyz still 503s, that's
        # a regression in the readyz code path, not here.
        cur.execute(
            """
            SELECT has_table_privilege(%s, 'public.alembic_version', 'SELECT')
            """,
            (APP_USER,),
        )
        can_select = cur.fetchone()[0]
        print(
            f"post_migrate: has_table_privilege({APP_USER}, alembic_version, SELECT) = {can_select}",
            flush=True,
        )
        if not can_select:
            print(
                f"FATAL: {APP_USER} cannot SELECT public.alembic_version "
                "AFTER the explicit GRANT above. This is the exact failure "
                "mode that 503s /readyz on Phase 4 deploy probes. "
                "Inspect:  \\dp public.alembic_version  in psql.",
                file=sys.stderr, flush=True,
            )
            sys.exit(6)

    print(
        f"post_migrate: granted {len(grant_statements)} privileges to {APP_USER}. "
        f"Verified INSERT/SELECT/UPDATE/DELETE on public.users.",
        flush=True,
    )

    # ── Optional: ad-hoc post-deploy SQL ────────────────────────────────
    # `infra/post-deploy-refresh.sh --invalidate-cache` injects an
    # UPDATE vertex_synthesis_cache SET invalidated_at=NOW() statement
    # via this env-var so the next read for every cached surface
    # re-synthesizes against the freshly-deployed code. Single-statement
    # only; rejected at length 8192 to keep this from becoming an
    # arbitrary SQL execution surface. Only UPDATE / DELETE are allowed
    # (no DDL — that's what migrations are for).
    post_sql = os.environ.get("DMA_POST_DEPLOY_SQL", "").strip()
    if post_sql:
        if len(post_sql) > 8192:
            print(
                f"FATAL: DMA_POST_DEPLOY_SQL is {len(post_sql)} chars; "
                "max 8192. Reject to avoid arbitrary SQL surface.",
                file=sys.stderr, flush=True,
            )
            sys.exit(7)
        first_word = post_sql.lstrip().split(None, 1)[0].upper()
        if first_word not in {"UPDATE", "DELETE"}:
            print(
                f"FATAL: DMA_POST_DEPLOY_SQL must start with UPDATE or "
                f"DELETE; got {first_word!r}.",
                file=sys.stderr, flush=True,
            )
            sys.exit(7)
        # Use a fresh connection in a new transaction so the row count
        # is reported via rowcount. Re-use the same superuser DSN.
        conn2 = psycopg.connect(url, autocommit=False)
        with conn2, conn2.cursor() as cur2:
            print(f"post_migrate: executing DMA_POST_DEPLOY_SQL ({len(post_sql)} chars)",
                  flush=True)
            cur2.execute(post_sql)
            print(f"post_migrate: invalidated {cur2.rowcount} rows", flush=True)
            conn2.commit()

    # ── Optional: seed CI fixtures ──────────────────────────────────────
    # `infra/seed-and-run-e2e.sh` sets DMA_RUN_SEED_CI=1 on the
    # migrations Cloud Run Job before executing it, so the e2e suite
    # always runs against a populated DB regardless of what state it
    # was in. seed_ci is idempotent — re-running on a populated DB is
    # a no-op (UPSERT by request_id). Failures are logged but don't
    # fail the post_migrate chain since seeding is operationally
    # separable from the grant chain above.
    if os.environ.get("DMA_RUN_SEED_CI", "").strip() in ("1", "true", "yes"):
        print("post_migrate: DMA_RUN_SEED_CI=1 set; invoking seed_ci…",
              flush=True)
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "app.scripts.seed_ci"],
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
            )
            print(result.stdout, flush=True)
            if result.returncode != 0:
                print(
                    f"post_migrate: seed_ci exited {result.returncode}; "
                    "stderr below (continuing — seeding failure does not "
                    "block the grant chain):",
                    file=sys.stderr, flush=True,
                )
                print(result.stderr, file=sys.stderr, flush=True)
            else:
                print("post_migrate: seed_ci OK", flush=True)
        except subprocess.TimeoutExpired:
            print(
                "post_migrate: seed_ci timed out after 600s; continuing",
                file=sys.stderr, flush=True,
            )
        except Exception as e:
            print(
                f"post_migrate: seed_ci raised {type(e).__name__}: {e}; continuing",
                file=sys.stderr, flush=True,
            )


if __name__ == "__main__":
    main()

