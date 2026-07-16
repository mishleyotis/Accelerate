"""Runtime configuration loaded from env vars / Secret Manager."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["local", "dev", "prod", "test"] = "local"
    log_level: str = "info"
    allowed_origins: str = "http://localhost:5173"

    database_url: str = (
        "postgresql+asyncpg://dma_insights:dma_insights_local"
        "@localhost:5433/dma_insights"
    )
    database_url_sync: str = (
        # Default uses `+psycopg` to pin SQLAlchemy onto the psycopg3
        # driver (`psycopg[binary]==3.2.3` in the backend image). Bare
        # `postgresql://` defaults to psycopg2 in SQLAlchemy 2.0, which
        # is NOT installed → ModuleNotFoundError at every cold start.
        # Fix landed 2026-05-24 after the Cloud Build alembic-against-
        # backend-image step failed with this exact error.
        "postgresql+psycopg://dma_insights:dma_insights_local"
        "@localhost:5433/dma_insights"
    )

    redis_url: str = "redis://localhost:6380/0"

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_hosted_domain: str = "zennify.com"

    jwt_private_key_path: str = "./local-data/jwt-private.pem"
    jwt_public_key_path: str = "./local-data/jwt-public.pem"
    jwt_issuer: str = "https://dma-insights.local"
    jwt_audience: str = "dma-insights"
    jwt_ttl_hours: int = 12

    vertex_project_id: str = "digital-maturity-assessor"
    vertex_location: str = "us-central1"
    # Gemini model IDs — operator overrides via env vars
    # VERTEX_FLASH_MODEL / VERTEX_PRO_MODEL. Defaults below are pinned
    # to the 2.5 family because the canonical Zennify project (digital-
    # maturity-assessor in us-central1) has Model Garden access to
    # gemini-2.5-{flash,pro} but NOT to gemini-2.0-flash-001 or any of
    # the gemini-1.5-* variants (verified 2026-05-29 via :generateContent
    # probe — see DEPLOYMENT.md §0.2.13 for the discovery loop).
    #
    # If a different project has Model Garden access to a different
    # family, override via the env vars at deploy time without touching
    # this default. The discovery loop in DEPLOYMENT.md §0.2.13 exports
    # the right values automatically.
    vertex_flash_model: str = "gemini-2.5-flash"
    vertex_pro_model: str = "gemini-2.5-pro"
    # text-embedding-004 was RETIRED by Google (announced EOL 2026-01-14)
    # — embed calls against it fail, so the corpus shipped with ZERO baked
    # vectors. text-embedding-005 is the same-dimension (768) drop-in for
    # the Vector(768) *_embeddings columns; gemini-embedding-001 is the
    # eventual migration (needs output_dimensionality=768). No stored
    # vectors existed under 004, so the model_version switch is clean.
    vertex_embedding_model: str = "text-embedding-005"

    drive_root_folder_id: str = "1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P"
    ops_sheet_id: str = "1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8"

    dma_bot_url: str = "https://dma-bot-306195530103.us-central1.run.app"
    dma_bot_api_key: str = ""

    rag_api_bearer_key: str = ""

    gcs_bucket_request_materials: str = "dma-insights-request-materials"
    gcs_bucket_catalogue_staging: str = "dma-insights-catalogue-staging"

    catalogue_default_version: str = "v7.0"
    catalogue_cache_ttl_seconds: int = 3600
    adjacency_cache_ttl_seconds: int = 60

    # Historical Drive backfills predate v7.0 — the assessments
    # uploaded by the n8n bot before 2026-04 were scored against v5.*
    # catalogue IDs. When `data_source='DRIVE_BACKFILL'` and the package's
    # manifest doesn't declare an explicit catalogue version, this is
    # the version the resolver pins to. Persisting with `v7.0` would
    # mis-route every v5 subcap ID through aliases that don't exist
    # for old IDs (e.g. legacy `P1C1.1`-shaped IDs).
    # Per ADR 0005 + ADR 0013: the audit pending-register item C
    # required this to be a configured env var, not a hard-coded
    # default. Operators set `DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION`
    # in .deploy.parameters.env; the preflight refuses to bootstrap
    # without it when historical_backfill is part of the deployment.
    backfill_default_catalogue_version: str = "v5.0"

    # Pub/Sub topic the package-persist + backfill paths publish a
    # `dma.ingest.completed` envelope to. The embedder worker subscribes
    # to this topic and triggers a one-shot run per message.
    # In local dev (no creds / no project) the publish is a no-op that
    # logs a warning and never fails ingest.
    gcp_project_id: str = ""
    pubsub_ingest_topic: str = "dma.ingest.completed"
    pubsub_publish_timeout_seconds: float = 2.0

    # Clay enrichment connector (firmographics + leadership). Per
    # `docs/decisions/0010-clay-connector.md`: outbound trigger posts to
    # a Clay table-webhook URL, the table runs its enrichment chain,
    # and Clay posts the result back to /api/v1/clay/webhook signed with
    # `clay_webhook_secret`. All three vars come from Secret Manager.
    clay_webhook_url: str = ""             # outbound; per-environment
    clay_webhook_secret: str = ""          # HMAC-SHA256 shared secret
    clay_request_timeout_seconds: int = 8

    admin_emails: tuple[str, ...] = Field(
        default=(
            "mishley.otiende@zennify.com",
            "richard.odhiambo@zennify.com",
            "sam.friedewald@zennify.com",
            "kevin.murray@zennify.com",
            "chris.conant@zennify.com",
            "carlie.welsh@zennify.com",
            "tom.hedgecoth@zennify.com",
        )
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


# ── Production-readiness guard ─────────────────────────────────────────
# These keys MUST be populated via Secret Manager (or equivalent) when
# env=prod / env=dev. The validator runs at startup; missing values
# raise RuntimeError so the deploy fails fast instead of silently
# serving 401s / dropping events / fail-closed-ing every Clay webhook.
#
# State-branch contract:
#   env=local / env=test   → all checks skipped (defaults are intended
#                             for dev convenience).
#   env=prod / env=dev     → every key below must be non-empty AND
#                             must not equal its dev default. First
#                             violation raises with a typed message.
#
# 2026-05-28 audit fix:
#  - Split into BACKEND and WORKER lists. Workers don't sign JWTs,
#    don't accept OAuth callbacks, don't terminate Clay webhooks —
#    requiring backend-only secrets at worker boot would block every
#    Cloud Run Job startup.
#  - Removed `jwt_public_key_path` (derived from private key at runtime).
#  - `jwt_private_key_path` replaced by an env-or-path check: Terraform
#    injects `JWT_PRIVATE_KEY_PEM` (Secret Manager); the path-default
#    leak check no longer rejects that wiring.
REQUIRED_FOR_PROD_BACKEND: tuple[tuple[str, str | None], ...] = (
    ("database_url", "localhost:5433"),
    ("redis_url", "localhost:6380"),
    ("google_oauth_client_id", ""),
    ("google_oauth_client_secret", ""),
    ("dma_bot_api_key", ""),
    ("rag_api_bearer_key", ""),
    ("gcp_project_id", ""),
    # clay_webhook_url / clay_webhook_secret intentionally NOT required
    # (2026-06-10): Clay is NOT in prod for this version — firmographics
    # come from the client research/profile reports at ingest, with the
    # Gemini firmographics_extraction surface filling gaps. The Clay
    # client fail-closes on empty values (ADR 0010), and
    # deploy-two-phase.sh provisions placeholder secrets so the Cloud
    # Run secret refs resolve. Re-add both entries when Clay ships.
)
REQUIRED_FOR_PROD_WORKER: tuple[tuple[str, str | None], ...] = (
    ("database_url", "localhost:5433"),
    ("gcp_project_id", ""),
)
# Back-compat alias — existing tests + scripts import REQUIRED_FOR_PROD.
REQUIRED_FOR_PROD = REQUIRED_FOR_PROD_BACKEND


def assert_production_ready(
    settings: Settings, *, role: str = "backend"
) -> None:
    """Raise RuntimeError if `env in (prod, dev)` and any
    production-required setting is unset / equals its dev default.

    Caller invokes this from app startup BEFORE `app.run()` so the
    misconfiguration surfaces as a failed Cloud Run health check
    (revision never serves traffic) rather than as a runtime 500
    after the first user request.

    `role` selects which list of required keys to enforce:
      - 'backend' (default): full FastAPI service surface
      - 'worker': minimal Cloud Run Job surface (DB + GCP project id)
    """
    if settings.env not in ("prod", "dev"):
        return
    required = (
        REQUIRED_FOR_PROD_WORKER if role == "worker"
        else REQUIRED_FOR_PROD_BACKEND
    )
    problems: list[str] = []
    for name, dev_default in required:
        value = getattr(settings, name, None)
        if value is None or value == "":
            problems.append(
                f"{name} is unset (env={settings.env} requires a real value)"
            )
            continue
        # Reject the case where dev default leaks through (e.g. dev
        # docker-compose URL still in the prod Cloud Run env).
        if dev_default and dev_default in str(value):
            problems.append(
                f"{name} still contains dev default `{dev_default}` — "
                f"set via Secret Manager"
            )
    # JWT key check (backend only) — accept EITHER the PEM env that
    # Terraform actually injects (JWT_PRIVATE_KEY_PEM via Secret
    # Manager) OR a real on-disk path. The old REQUIRED_FOR_PROD entry
    # for `jwt_private_key_path` rejected prod because the field still
    # held the dev default string even when JWT_PRIVATE_KEY_PEM was set.
    if role == "backend":
        import os as _os
        import pathlib as _pl
        pem_env = (_os.environ.get("JWT_PRIVATE_KEY_PEM") or "").strip()
        path_val = getattr(settings, "jwt_private_key_path", "")
        has_pem = bool(pem_env)
        has_real_path = bool(
            path_val
            and path_val != "./local-data/jwt-private.pem"
            and _pl.Path(path_val).exists()
        )
        if not (has_pem or has_real_path):
            problems.append(
                "JWT private key missing — set JWT_PRIVATE_KEY_PEM env "
                "(via Secret Manager) OR a real JWT_PRIVATE_KEY_PATH"
            )
    # ── Vertex 1-token reachability probe (backend, prod/dev) ──────────
    # RC1 (2026-07 audit): Gemini surfaces silently served deterministic
    # fallbacks for weeks because nothing at startup proved the service
    # could actually reach Vertex. `VertexClient.probe()` makes the
    # cheapest authenticated call (count_tokens, zero generation cost)
    # so an IAM / project / network misconfiguration fails the deploy
    # loudly instead of degrading every AI surface to templates.
    #
    # Escape hatches (both honored — see infra/EXIT_CODES.md +
    # DEPLOYMENT.md §26 "Gemini at deploy"):
    #   DMA_DISABLE_VERTEX=1        → intentionally Vertex-cold env
    #                                 (qa-gates, local sandboxes)
    #   _ALLOW_COLD_GEMINI=true /
    #   ALLOW_COLD_GEMINI=true      → operator accepts a cold deploy;
    #                                 probe failure downgrades to a
    #                                 loud warning.
    # Only for role="backend": workers that need Vertex fail per-job
    # with their own grounded fallbacks, and blocking e.g. drive_crawler
    # boot on a Vertex blip would wedge ingest for no benefit.
    if role == "backend":
        import os as _os
        _disabled = (_os.environ.get("DMA_DISABLE_VERTEX", "").strip()
                     in {"1", "true", "TRUE", "yes"})
        _allow_cold = (
            (_os.environ.get("_ALLOW_COLD_GEMINI")
             or _os.environ.get("ALLOW_COLD_GEMINI")
             or "").strip().lower() == "true"
        )
        if not _disabled:
            try:
                from app.services.vertex_client import get_vertex_client
                get_vertex_client().probe()
            except Exception as exc:  # probe MUST never crash unhandled
                msg = (
                    f"Vertex unreachable ({type(exc).__name__}: "
                    f"{str(exc)[:160]}) — Gemini surfaces would silently "
                    "serve deterministic fallbacks. Fix: grant "
                    "roles/aiplatform.user to this service's SA "
                    "(gcloud projects add-iam-policy-binding $PROJECT_ID "
                    "--member=serviceAccount:<SA> "
                    "--role=roles/aiplatform.user), verify "
                    "VERTEX_PROJECT_ID/VERTEX_LOCATION, or set "
                    "_ALLOW_COLD_GEMINI=true / DMA_DISABLE_VERTEX=1 to "
                    "deploy cold deliberately."
                )
                if _allow_cold:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "ALLOW_COLD_GEMINI: %s", msg,
                    )
                else:
                    problems.append(msg)
    if problems:
        raise RuntimeError(
            "Production-readiness check FAILED — "
            f"{len(problems)} setting(s) misconfigured for env={settings.env} "
            f"(role={role}):\n  - "
            + "\n  - ".join(problems)
            + "\n\nFix: populate via Secret Manager + Cloud Run env "
            "vars. See DEPLOYMENT.md §36."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
