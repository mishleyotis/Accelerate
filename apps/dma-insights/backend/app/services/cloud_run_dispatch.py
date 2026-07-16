"""Cloud Run Jobs dispatcher — invokes a worker when the operator triggers
a job from the Admin UI.

Background: `POST /api/v1/admin/jobs/{name}:execute` writes a
`job_executions` row in 'running' state then (historically) published a
Pub/Sub fan-out message to topic `admin-job-triggered`. **No worker
subscribed to that topic**, so the row stayed in 'running' forever and
the operator's "Drive crawl" / "Embeddings" / "Peer patterns" button
appeared to do nothing — which is exactly what the user reported
("Currently none has been ingested from the drive").

This module closes the gap. The trigger now ALSO calls the Cloud Run
Jobs REST API directly (`JobsAsyncClient.run_job`) with an env-var
override so the worker that runs picks up the `DMA_JOB_EXECUTION_ID`
and updates the SAME `job_executions` row.

State-branch contract:
  - dispatched           → Cloud Run Jobs returned 200; worker now running
  - skipped_local_env    → env=local; subprocess fired instead so local
                           dev parity is preserved (admin tests can
                           verify the dispatch path end-to-end)
  - skipped_no_project   → GCP project not configured; dispatch is no-op
  - job_not_in_registry  → job_name not in `JOB_DISPATCH`; raises
  - run_job_failed       → REST call raised; caller marks row 'failed'
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import structlog

from app.config import get_settings

log = structlog.get_logger()

# Mapping: admin-side job_name → (Cloud Run Job resource name,
# default args, python module entrypoint for local-env subprocess).
JOB_DISPATCH: dict[str, tuple[str, list[str], str]] = {
    "drive_crawler":          ("dma-insights-drive-crawler",
                                ["--once"], "workers.drive_crawler.main"),
    "historical_backfill":    ("dma-insights-historical-backfill",
                                [], "app.scripts.historical_backfill"),
    "embedder":               ("dma-insights-embedder",
                                ["--once"], "workers.embedder.main"),
    # peer_patterns: without --all the argparse defaults exit 0
    # immediately (no subvertical → no work). The admin button has to
    # default to the all-subverticals KMeans pass; per-subvertical
    # runs override via extra_args=["--subvertical","CU"].
    "peer_patterns":          ("dma-insights-peer-patterns",
                                ["--all"], "workers.peer_patterns.main"),
    # ccg_loader: argparse REQUIRES --version + --workbooks-dir; an empty
    # default-args list caused admin button presses to exit with
    # "the following arguments are required" (2026-05-29 audit).
    # The defaults below mirror Terraform's Cloud Run Job spec — admin
    # one-shot clicks reload the current catalogue version (v7.0) from
    # the canonical GCS staging bucket. To load a different version,
    # admin passes extra_args=["--version", "v5.0", "--workbooks-dir",
    # "gs://<bucket>/v5.0/"].
    "ccg_loader":             ("dma-insights-ccg-loader",
                                ["--version", "v7.0",
                                 "--workbooks-dir",
                                 "gs://${PROJECT_ID}-catalogue-staging/v7.0/"],
                                "workers.ccg_loader.main"),
    "sheet_poller":           ("dma-insights-sheet-poller",
                                ["--once"], "workers.sheet_poller.main"),
    # intelligence_recompute: same no-op-on-empty-args gotcha as
    # peer_patterns. Admin one-shot button → --all (recompute every
    # entity's customer_intelligence_profile). Scheduled subscriber
    # is a separate Cloud Run Job (deployed via `--subscribe` mode).
    "intelligence_recompute": ("dma-insights-intelligence-recompute",
                                ["--all"], "workers.intelligence_recompute.main"),
    "chat_learning":          ("dma-insights-chat-learning",
                                [], "workers.chat_learning.main"),
}


async def dispatch_job(
    *,
    job_name: str,
    execution_id: str,
    extra_args: list[str] | None = None,
    region: str | None = None,
) -> tuple[bool, str]:
    """Invoke the Cloud Run Job for `job_name`. Returns (dispatched, reason).

    Workers honour `DMA_JOB_EXECUTION_ID` (see `workers/_runner.py`) so
    the dispatched run updates the SAME `job_executions` row instead of
    creating a parallel one.
    """
    settings = get_settings()
    if job_name not in JOB_DISPATCH:
        return (False, f"job_not_in_registry:{job_name}")
    cr_job_name, default_args, py_module = JOB_DISPATCH[job_name]
    extra_args = extra_args or []
    args_list = list(default_args) + list(extra_args)

    # Interpolate ${PROJECT_ID} placeholder in the registry defaults
    # (e.g. ccg_loader's GCS workbooks-dir). Without this, the admin
    # button dispatches a literal `gs://${PROJECT_ID}-catalogue-staging/`
    # path that doesn't exist (2026-05-29 QA audit). Cheaper than
    # computing the dict at import time, which would force a settings
    # load and break tests that monkeypatch the env afterwards.
    if "${PROJECT_ID}" in " ".join(args_list):
        project_id = settings.gcp_project_id or os.environ.get("GCP_PROJECT_ID", "")
        if project_id:
            args_list = [
                a.replace("${PROJECT_ID}", project_id) for a in args_list
            ]

    # Local / test path — fire-and-forget subprocess so the admin
    # button's behaviour is testable end-to-end without GCP creds.
    if settings.env in ("local", "test"):
        try:
            env = {**os.environ, "DMA_JOB_EXECUTION_ID": execution_id}
            await asyncio.create_subprocess_exec(
                sys.executable, "-m", py_module, *args_list, env=env,
            )
            log.info(
                "admin.dispatch.local",
                job_name=job_name, module=py_module, execution_id=execution_id,
            )
            return (True, "skipped_local_env_subprocess_fired")
        except Exception as e:
            log.warning(
                "admin.dispatch.local_failed",
                err=str(e), job_name=job_name,
            )
            return (False, f"local_subprocess_failed:{type(e).__name__}")

    # Production path — invoke Cloud Run Jobs REST API.
    project_id = settings.gcp_project_id
    if not project_id:
        return (False, "skipped_no_project")
    region = region or os.environ.get("GCP_REGION", "us-central1")

    try:
        from google.cloud import run_v2  # type: ignore[import-untyped]
    except Exception as e:
        log.warning("admin.dispatch.import_failed", err=str(e))
        return (False, f"import_failed:{type(e).__name__}")

    try:
        client = run_v2.JobsAsyncClient()
        name = f"projects/{project_id}/locations/{region}/jobs/{cr_job_name}"
        container_override = run_v2.RunJobRequest.Overrides.ContainerOverride(
            args=args_list,
            env=[run_v2.types.EnvVar(name="DMA_JOB_EXECUTION_ID", value=execution_id)],
        )
        overrides = run_v2.RunJobRequest.Overrides(
            container_overrides=[container_override],
        )
        await client.run_job(
            request=run_v2.RunJobRequest(name=name, overrides=overrides),
        )
        log.info(
            "admin.dispatch.ok",
            job_name=job_name, cr_job=cr_job_name, execution_id=execution_id,
        )
        return (True, "dispatched")
    except Exception as e:
        log.warning(
            "admin.dispatch.run_job_failed",
            err=str(e), job_name=job_name, cr_job=cr_job_name,
        )
        return (False, f"run_job_failed:{type(e).__name__}:{e!s}"[:300])


def dispatch_job_arg_validator(extra_args: Any) -> list[str]:
    """Coerce admin-supplied args to a list[str] so the REST call doesn't
    explode on dict / None / int. Drops anything non-string."""
    if extra_args is None:
        return []
    if isinstance(extra_args, list):
        return [str(x) for x in extra_args if x is not None]
    return []
