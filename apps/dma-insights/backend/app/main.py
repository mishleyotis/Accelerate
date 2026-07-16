"""DMA Insights FastAPI app entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import assert_production_ready, get_settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("dma_insights.startup", env=settings.env)

    # ── Self-heal startup diagnostic (2026-05-28) ─────────────────────
    #
    # Run the same SQL queries that back `/api/v1/admin/diagnostics` and
    # log structured warnings for every issue detected. NON-BLOCKING —
    # the deploy must never fail because of stale catalogue state; we
    # only emit log lines so Cloud Logging surfaces them in the deploy
    # observability surface.
    #
    # In production this gives the operator an immediate picture of
    # what state the new image inherited from the prior one (e.g.
    # placeholder catalogue rows that the loader hasn't replaced,
    # stuck job_executions from a worker that died during the rollover,
    # parser-warning-flagged runs with unresolved scores).
    #
    # State-branch contract:
    #   db_unreachable        → log warning; deploy continues
    #   no_issues_detected    → single log.info confirming clean state
    #   issues_detected       → log.warning per category with counts
    try:
        from app.services.startup_diagnostic import run_startup_diagnostic
        await run_startup_diagnostic(log)
    except Exception as e:
        # Defense-in-depth: NEVER let the diagnostic block startup.
        # If the diagnostic itself is broken, we still want the rest
        # of the service to come up so the operator can reach
        # /healthz and roll back if needed.
        log.warning(
            "startup_diagnostic.unexpected_error",
            err=str(e)[:200],
            err_type=type(e).__name__,
        )

    # ── Route-composition safety audit (2026-06-05) ───────────────────
    #
    # The recurring stage-7 500 (heatmap/subcap returning 500 against
    # seeded AmeriCU + every other entity hit at that path) was caused
    # by a `run: str | None = Query(default=None)` parameter default
    # leaking a `fastapi.params.Query` sentinel into a sibling handler
    # that composed it via direct Python call. The sentinel had no
    # `.strip()` method and the resolver raised AttributeError -> 500.
    #
    # Scan every registered route at startup; if ANY handler has a
    # `run` parameter whose default is NOT plain None, emit a loud
    # warning + log the offender. (We don't crash because Cloud Run
    # would then never serve traffic for an issue that may be fixable
    # in the next deploy; the runtime resolver also has a defensive
    # coercion -- belt and braces.)
    try:
        from app.services.run_resolver import audit_route_composition_safety
        audit_route_composition_safety(app, log)
    except Exception as e:
        log.warning(
            "route_composition_audit.unexpected_error",
            err=str(e)[:200],
            err_type=type(e).__name__,
        )

    yield
    log.info("dma_insights.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    # Production-readiness guard. Pre-2026-06-05 this called
    # `assert_production_ready(settings)` directly -- on any
    # misconfiguration it RAISED RuntimeError, crashing the FastAPI
    # process before uvicorn could bind. Cloud Run then served 503
    # from the load balancer with NO body, leaving the operator
    # totally blind during a Phase 4 candidate probe.
    #
    # New contract: run the check, capture any failure as a string,
    # stash on app.state. /readyz reads it + returns 503 with the
    # FULL error message in the response body so the operator sees
    # exactly which secret is unset / dev-default'd. The container
    # still binds + serves, the body is the diagnostic.
    #
    # Net effect: misconfigured prod secrets still block traffic
    # promotion (Phase 4 readyz fails -> deploy aborts), but the
    # operator gets the actionable error instead of a silent crash.
    prod_readiness_error: str | None = None
    try:
        assert_production_ready(settings)
    except RuntimeError as e:
        prod_readiness_error = str(e)
        log.error(
            "dma_insights.production_readiness_failed",
            err=prod_readiness_error[:500],
        )

    app = FastAPI(
        title="DMA Insights",
        version="0.1.0",
        description="Internal surface for every completed Digital Maturity Assessment.",
        lifespan=lifespan,
    )
    app.state.prod_readiness_error = prod_readiness_error

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    from app.routers.admin import router as admin_router
    from app.routers.auth import router as auth_router
    from app.routers.chat import router as chat_router
    from app.routers.clay import router as clay_router
    from app.routers.context import router as context_router
    from app.routers.cross_pillar import router as cross_pillar_router
    from app.routers.entities import router as entities_router
    from app.routers.evidence import router as evidence_router
    from app.routers.health import alerts_router, health_router
    from app.routers.heatmap import router as heatmap_router
    from app.routers.ingest import router as ingest_router
    from app.routers.ingest_package import router as ingest_package_router
    from app.routers.insights import router as insights_router
    from app.routers.intelligence import router as intelligence_router
    from app.routers.notes import router as notes_router
    from app.routers.patterns import router as patterns_router
    from app.routers.platforms import router as platforms_router
    from app.routers.prospecting import router as prospecting_router
    from app.routers.rag import router as rag_router
    from app.routers.recommendations import router as recommendations_router
    from app.routers.runs_new import router as runs_new_router
    from app.routers.search import router as search_router
    from app.routers.sse import router as sse_router
    from app.routers.stairstep import router as stairstep_router
    from app.routers.write_surfaces import (
        entities_router as write_surfaces_router,
    )
    from app.routers.write_surfaces import (
        notifications_router,
    )

    app.include_router(auth_router)
    app.include_router(entities_router)
    app.include_router(search_router)
    app.include_router(insights_router)
    app.include_router(heatmap_router)
    app.include_router(platforms_router)
    app.include_router(stairstep_router)
    app.include_router(recommendations_router)
    app.include_router(context_router)
    app.include_router(cross_pillar_router)
    app.include_router(health_router)
    app.include_router(alerts_router)
    app.include_router(runs_new_router)
    app.include_router(ingest_router)
    app.include_router(ingest_package_router)
    app.include_router(clay_router)
    app.include_router(rag_router)
    app.include_router(sse_router)
    app.include_router(patterns_router)
    app.include_router(prospecting_router)
    app.include_router(admin_router)
    app.include_router(chat_router)
    app.include_router(intelligence_router)
    app.include_router(evidence_router)
    app.include_router(write_surfaces_router)
    app.include_router(notifications_router)
    app.include_router(notes_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["meta"])
    async def readyz() -> dict[str, str]:
        """Cloud Run startup + liveness probe.

        Production behaviour: returns 503 when the DB is unreachable so
        Cloud Run can delay sending traffic to a freshly-rolled revision
        until the pool is warm, and drain a degraded instance during a
        brief network blip.

        Local/test behaviour: returns 200 with `status=degraded` when
        any downstream is unreachable so the in-process TestClient (no
        DB) still passes. The env check uses `Settings.env` which is
        forced to `local` by pytest fixtures.

        Redis is a soft dependency — its check never escalates to 503.
        """
        import asyncio

        from fastapi import HTTPException
        from sqlalchemy import text

        from app.config import get_settings
        from app.database import get_engine, refresh_engine_on_auth_failure
        from app.deps import get_redis

        settings = get_settings()
        is_prod = settings.env not in ("local", "test")
        result: dict[str, str] = {"status": "ready"}

        # 2026-06-05: surface the production-readiness check result.
        # Pre-fix the check raised at module load and crashed the
        # process; now it's stashed on app.state and we 503 with the
        # full diagnostic in the response BODY so the operator sees
        # exactly which secret is misconfigured during Phase 4 probes.
        readiness_err = getattr(app.state, "prod_readiness_error", None)
        if readiness_err and is_prod:
            raise HTTPException(
                status_code=503,
                detail=f"production-readiness check failed: {readiness_err[:400]}",
            )

        # Self-healing DB probe (2026-06): tries SELECT 1 once, and on
        # InvalidPasswordError (the recurring drift symptom) refreshes
        # the engine + retries ONCE. The refresh disposes the cached
        # engine so the next get_engine() reads `postgres-dsn:latest`
        # from Secret Manager fresh — matching whatever force-heal-db.sh
        # last wrote. This makes the backend revision tolerate a secret
        # rotation that lands AFTER the revision was deployed (the
        # b1da810 deploy's Phase 4 503 class of failure) WITHOUT
        # waiting for a manual revision roll.
        async def _probe_db() -> None:
            engine = get_engine()
            async with engine.connect() as conn:
                # Tight timeout — a hung DB should surface in seconds.
                await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=2.0)

        try:
            await _probe_db()
        except Exception as e:
            err_name = type(e).__name__
            # asyncpg's InvalidPasswordError is the canonical drift
            # symptom. Refresh + retry. If the second probe also
            # fails, fall through to the original error handling.
            if "InvalidPassword" in err_name or "AuthenticationFail" in err_name:
                await refresh_engine_on_auth_failure()
                try:
                    await _probe_db()
                    result["db"] = "recovered_after_engine_refresh"
                except Exception as e2:
                    e = e2
                    if is_prod:
                        raise HTTPException(
                            status_code=503,
                            detail=f"db unavailable after engine refresh: {type(e).__name__}",
                        ) from e
                    result["status"] = "degraded"
                    result["db"] = f"down: {type(e).__name__} (engine-refresh failed)"
                else:
                    return result
            elif is_prod:
                raise HTTPException(
                    status_code=503,
                    detail=f"db unavailable: {err_name}",
                ) from e
            else:
                result["status"] = "degraded"
                result["db"] = f"down: {err_name}"

        try:
            redis = await get_redis()
            await asyncio.wait_for(redis.ping(), timeout=1.0)
        except Exception as e:
            # Redis blip is non-fatal — most reads work without it.
            result["redis"] = f"down: {type(e).__name__}"

        # D1: migration drift — fail-closed in prod when the DB's
        # alembic_version doesn't match the head revision shipped in
        # the image. Without this check, a deploy against an older
        # schema renders silently broken (missing columns → 500s
        # only when the affected endpoint is hit). Skipped in
        # local/test so the in-process TestClient (no real DB) and
        # ephemeral pytest sessions still pass.
        #
        # 2026-06-05: bumped the SELECT timeout 2s -> 5s and the
        # alembic.ini path resolution now falls back to a runtime
        # search (Path(__file__).parent.parent works in the local
        # checkout but the Cloud Run container's /home/app layout
        # has alembic.ini at /home/app/alembic.ini, not /home/app/
        # parent. Pre-fix the parent.parent path resolved to /home,
        # alembic.ini wasn't there, Config() raised at the str(cfg_path)
        # construction, and /readyz returned a misleading
        # "migration check failed: NoSuchTableError" 503 on every probe).
        # 2026-06-11 deploy-simulation finding: migration_head was
        # prod-gated, so post-deploy-smoke.sh's A5 readyz check
        # false-failed against every non-prod env ("Deploy is silently
        # broken" on a healthy local stack). Emit the head in EVERY env
        # — only the drift 503 below stays prod-gated.
        if result.get("status") == "ready":
            try:
                from pathlib import Path

                from alembic.config import Config
                from alembic.script import ScriptDirectory

                engine = get_engine()
                async with engine.connect() as conn:
                    row = await asyncio.wait_for(
                        conn.execute(
                            text("SELECT version_num FROM alembic_version")
                        ),
                        timeout=5.0,
                    )
                    db_head = row.scalar_one_or_none()

                # Resilient alembic.ini resolution -- the Dockerfile
                # copies it to /home/app/alembic.ini but Path(__file__)
                # points at /home/app/app/main.py so parent.parent is
                # /home/app -- right. For an editable local install
                # backend/app/main.py -> parent.parent is backend/ ->
                # backend/alembic.ini -- right. So the fallback search
                # exists only for unusual layouts (test fixtures, etc.).
                cfg_path = Path(__file__).parent.parent / "alembic.ini"
                if not cfg_path.exists():
                    # Walk up to find alembic.ini next to an alembic/ dir.
                    for ancestor in Path(__file__).resolve().parents:
                        candidate = ancestor / "alembic.ini"
                        if candidate.exists() and (ancestor / "alembic").is_dir():
                            cfg_path = candidate
                            break
                cfg = Config(str(cfg_path))
                cfg.set_main_option(
                    "script_location",
                    str(cfg_path.parent / "alembic"),
                )
                script = ScriptDirectory.from_config(cfg)
                code_head = script.get_current_head()
                if is_prod and db_head != code_head:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"migration drift: db={db_head} "
                            f"code={code_head} — run alembic upgrade head"
                        ),
                    )
                result["migration_head"] = code_head or "unknown"
            except HTTPException:
                raise
            except Exception as e:
                # Best-effort: if we can't read alembic_version (table
                # missing on a never-migrated DB) escalate to 503 too —
                # serving traffic against an un-migrated DB is the
                # exact failure mode this check exists to prevent.
                # Recognize the specific InsufficientPrivilegeError on
                # alembic_version and surface the operator-actionable
                # remediation directly — otherwise the trace ends in a
                # truncated SQLAlchemy ProgrammingError and the operator
                # has to grep psycopg internals to find the fix.
                err_str = str(e)
                if (
                    "InsufficientPrivilegeError" in err_str
                    or "permission denied for table alembic_version" in err_str
                    or "permission denied for relation alembic_version" in err_str
                ):
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "migration check failed: app user lacks SELECT "
                            "on alembic_version. Re-run the migrations Cloud "
                            "Run Job to apply the explicit GRANT+OWNER fix "
                            "from post_migrate.py: "
                            "`gcloud run jobs execute dma-insights-migrations "
                            "--region=us-central1 --wait` "
                            f"(underlying: {type(e).__name__}: {err_str[:160]})"
                        ),
                    ) from e
                raise HTTPException(
                    status_code=503,
                    detail=f"migration check failed: {type(e).__name__}: {err_str[:200]}",
                ) from e

        return result

    return app


app = create_app()
