"""Sync-DSN resolver — single source of truth for "give me a psycopg URL".

Workers and the backend need a psycopg (sync) DSN for places that can't
use asyncpg — `job_executions_db` lifecycle UPDATEs from worker
processes, `synthesis_cache_db` invalidation on post-commit hooks,
`ccg_loader._persist_loader_run` (writes ccg_loader_runs rows).

The Terraform spec at `infra/terraform/main.tf` only injects
`DATABASE_URL` (asyncpg form) into worker Cloud Run Jobs and the
backend Cloud Run service. The migrations job is the only one that
injects `DATABASE_URL_SYNC` explicitly (and it points at the superuser
secret, which we don't want all workers using anyway).

The two secrets differ ONLY by driver suffix — same password / host /
database / parameters. So when `DATABASE_URL_SYNC` is missing we
derive it from `DATABASE_URL` by replacing the `+asyncpg` suffix with
`+psycopg`. Explicit `DATABASE_URL_SYNC` always wins (preserves the
migrations-job convention of using a different secret).

Fallback ladder (added 2026-05-28):

  1. DATABASE_URL_SYNC env (explicit, wins).
  2. DATABASE_URL env (derived from asyncpg → psycopg).
  3. Secret Manager `dma-insights-database-url-sync` (when ADC available;
     covers Cloud Shell + gcloud-CLI invocations where env isn't wired).

The Secret Manager fallback is what makes `python -m
app.scripts.historical_backfill` work from Cloud Shell — without it the
worker writes no job_executions rows and the admin UI shows no runs.

This module is import-safe in worker containers (only stdlib + an
optional Google Cloud SDK import that fails-closed when missing).
"""
from __future__ import annotations

import os

# Module-level cache so we don't hit Secret Manager more than once per
# process. The DSN is stable across the worker's lifetime — re-pulling
# would burn an unnecessary Secret Manager API call per quarantine row.
_CACHED_SECRET_DSN: str | None = None
_SECRET_LOOKUP_ATTEMPTED = False


def resolve_sync_dsn() -> str | None:
    """Return a psycopg-compatible DSN, or None if no DB env is set.

    Resolution order:
      1. `DATABASE_URL_SYNC` env var (explicit, wins).
      2. `DATABASE_URL` env var with `+asyncpg` driver — return with
         `+asyncpg` replaced by `+psycopg`.
      3. `DATABASE_URL` env var with `postgresql://` (no driver) —
         return with `postgresql://` rewritten to `postgresql+psycopg://`
         so SQLAlchemy picks psycopg explicitly.
      4. Google Secret Manager `dma-insights-database-url-sync` via
         Application Default Credentials. Covers the operator's Cloud
         Shell case where neither env var is wired but the operator's
         gcloud auth grants secretAccessor on the project.
      5. None — caller MUST treat as "no sync DB available". The
         decision to no-op-vs-raise is the caller's; this helper is
         pure resolution, no side effects (modulo the Secret Manager
         lookup, which is cached).

    Caller pattern:
        url = resolve_sync_dsn()
        if not url:
            # local dev / DMA_JOB_EXECUTION_ID unset / test stub
            return  # or raise, depending on the path's contract
        engine = create_engine(url, ...)
    """
    explicit = (os.environ.get("DATABASE_URL_SYNC") or "").strip()
    if explicit:
        return explicit
    async_url = (os.environ.get("DATABASE_URL") or "").strip()
    if async_url:
        if "+asyncpg" in async_url:
            return async_url.replace("+asyncpg", "+psycopg")
        if async_url.startswith("postgresql://"):
            return async_url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        # Some other URL shape — return as-is and let the caller surface
        # the SQLAlchemy error if it's bogus.
        return async_url
    # Secret Manager fallback. Caller can disable via
    # DMA_DISABLE_SECRET_DSN_FALLBACK=1 (tests + local dev).
    if os.environ.get("DMA_DISABLE_SECRET_DSN_FALLBACK"):
        return None
    return _try_secret_manager()


def _try_secret_manager() -> str | None:
    """Look up dma-insights-database-url-sync via ADC. Cached.

    Returns None on ANY failure (no GCP creds, secret missing, lib not
    installed) — the caller falls back to its own "no DSN" branch.
    """
    global _CACHED_SECRET_DSN, _SECRET_LOOKUP_ATTEMPTED
    if _SECRET_LOOKUP_ATTEMPTED:
        return _CACHED_SECRET_DSN
    _SECRET_LOOKUP_ATTEMPTED = True
    try:
        # Lazy import — the google-cloud-secret-manager wheel is shipped
        # in the backend / worker images but missing in some test envs.
        from google.cloud import secretmanager  # type: ignore[import-untyped]
        project_id = (
            os.environ.get("GCP_PROJECT_ID")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or _detect_project_from_metadata_server()
        )
        if not project_id:
            return None
        client = secretmanager.SecretManagerServiceClient()
        name = (
            f"projects/{project_id}/secrets/"
            f"dma-insights-database-url-sync/versions/latest"
        )
        resp = client.access_secret_version(request={"name": name})
        payload = resp.payload.data.decode("utf-8").strip()
        if payload:
            _CACHED_SECRET_DSN = payload
            return payload
    except Exception:
        # Every Secret Manager failure mode lands here:
        #   - google.cloud.secretmanager not installed (test env)
        #   - no Application Default Credentials
        #   - secret doesn't exist in this project
        #   - operator lacks secretAccessor IAM role
        # All silent — the caller's None-handling kicks in.
        pass
    return None


def _detect_project_from_metadata_server() -> str | None:
    """When running on Cloud Run / Cloud Shell, the GCE metadata server
    serves the project id. Best-effort + short timeout."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.read().decode().strip()
    except Exception:
        return None


def reset_secret_cache_for_tests() -> None:
    """Test hook — clears the Secret Manager cache so tests can swap
    the mock between cases."""
    global _CACHED_SECRET_DSN, _SECRET_LOOKUP_ATTEMPTED
    _CACHED_SECRET_DSN = None
    _SECRET_LOOKUP_ATTEMPTED = False
