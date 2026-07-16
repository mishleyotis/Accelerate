"""Post-commit worker orchestration — direct dispatch of the
embedder + intelligence_recompute Cloud Run Jobs after every
successful package commit.

Background (2026-05-29 QA audit P1):
  Ingest used to do exactly two things post-commit: persist the run
  rows and publish a `dma.ingest.completed` Pub/Sub message. The
  publish was best-effort. The cluster had a topic AND two pull
  subscriptions (terraform: `google_pubsub_subscription.ingest_
  completed_*`), but no deployed process consumed them — the
  embedder + intelligence_recompute workers run as Cloud Run JOBS
  (not Services), so they don't have a long-lived `--subscribe`
  loop attached to the subscription. Result: a successful ingest
  published a message no one listened to; section_embeddings +
  customer_intelligence_profiles never populated; the UI's derived
  surfaces stayed empty even though the raw ingest was on disk.

What this module fixes:
  After every commit (live `/ingest/package` AND
  `historical_backfill`), we DIRECTLY dispatch the two Cloud Run
  Jobs that produce derived data — with `--run-id <run_id>` so the
  workers process exactly the run that just landed. Recording is
  done via the existing `job_executions` table so failures surface
  in the Admin UI's Last Run column.

Why direct dispatch instead of Pub/Sub push/Eventarc:
  • Cheapest: zero new infra, reuses the existing dispatch path
    (the admin "Execute" buttons use the same one).
  • Verifiable: every dispatch produces a `job_executions` row;
    operator can audit "did the embedder run for this ingest?".
  • Self-healing belt + braces: the scheduled reconciliation
    triggers (Terraform: `cloud_scheduler_job.embedder_hourly` +
    `intelligence_recompute_hourly`) catch any direct-dispatch
    failure on the next sweep.

Failure semantics:
  Every operation is best-effort. A failed dispatch is logged +
  flipped on the job_executions row, never re-raised to the
  caller, never blocks the API response. The ingest is the
  authoritative event; the workers are a follow-on.
"""
from __future__ import annotations

import contextlib
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# The 2 derived-data workers that MUST run after every successful
# package commit. Kept tight on purpose: peer_patterns +
# chat_learning are batch jobs that aren't tied to a single run.
_POST_COMMIT_JOBS = ("embedder", "intelligence_recompute")


async def dispatch_post_commit_workers(
    session: AsyncSession,
    *,
    run_id: str,
    entity_id: str | None,
) -> list[dict[str, Any]]:
    """Insert a `job_executions` row + dispatch each derived-data
    worker against the freshly-committed `run_id`.

    Returns a list of `{job_name, execution_id, dispatched, reason}`
    dicts (one per worker) for caller-side logging. Never raises —
    every dispatch is best-effort. A `job_executions` insert that
    fails (e.g. table missing on a pre-020 DB) is logged + the
    worker is skipped; the ingest still returns 201.

    Caller invokes from the **router** path (post `session.commit()`)
    and from `historical_backfill` (post its own commit). Both call
    sites already do the same with `publish_post_commit`.

    State branches:
      job_executions_table_missing  -> skip all dispatches, return
                                      [{... "reason":"job_executions_
                                      table_missing"}] x N
      insert_then_dispatch_ok       -> returned row + dispatched=True
      insert_ok_dispatch_failed     -> row exists, flipped to 'failed'
                                      with stderr_tail=reason
      tests/local                   -> dispatch_job's local-env path
                                      spawns a subprocess (same as
                                      the admin button path).
    """
    # Lazy import to avoid a top-level cycle (cloud_run_dispatch
    # imports get_settings → potentially Settings init at module
    # import time during tests).
    from app.services.cloud_run_dispatch import dispatch_job

    results: list[dict[str, Any]] = []
    for job_name in _POST_COMMIT_JOBS:
        extra_args = ["--run-id", run_id]
        # 1. Insert the job_executions row so the Admin UI can
        #    show "Last run …" + the eventual status.
        try:
            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO job_executions (
                            job_name, mode, trigger_source, status,
                            entity_id, args
                        ) VALUES (
                            :name, 'auto', 'post_commit', 'running',
                            CAST(:eid AS uuid),
                            CAST(:args AS jsonb)
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "name": job_name,
                        "eid": entity_id,
                        # args matches the admin-button shape so the
                        # UI's drawer renders the same way.
                        "args": _json_args(extra_args, run_id=run_id),
                    },
                )
            ).first()
            execution_id = str(row.id) if row else ""
        except Exception as e:
            msg = str(e).lower()
            if "job_executions" in msg and (
                "does not exist" in msg or "undefinedtable" in msg
            ):
                # Pre-020 DB. Skip silently — the run is already
                # committed; the scheduled reconciliation will
                # catch up once the migration lands.
                log.warning(
                    "post_commit.skip.job_executions_missing",
                    extra={"job": job_name, "run_id": run_id},
                )
                results.append({
                    "job_name": job_name, "execution_id": "",
                    "dispatched": False,
                    "reason": "job_executions_table_missing",
                })
                continue
            log.warning(
                "post_commit.insert_failed",
                extra={"job": job_name, "run_id": run_id, "err": repr(e)},
            )
            results.append({
                "job_name": job_name, "execution_id": "",
                "dispatched": False, "reason": f"insert_failed:{type(e).__name__}",
            })
            continue

        # 2. Dispatch the Cloud Run Job (or local subprocess in
        #    test/local env). `dispatch_job` returns (bool, reason)
        #    and never raises — the bool drives the UI status.
        try:
            dispatched, reason = await dispatch_job(
                job_name=job_name,
                execution_id=execution_id,
                extra_args=extra_args,
            )
        except Exception as e:
            dispatched, reason = (False, f"dispatch_exception:{type(e).__name__}")

        if not dispatched and not reason.startswith("skipped_"):
            # Flip the row to 'failed' so the UI's poller sees the
            # dispatch failure inline (matches the admin button path).
            # best-effort — a flip failure must not break the loop.
            with contextlib.suppress(Exception):
                await session.execute(
                    text(
                        "UPDATE job_executions "
                        "SET status='failed', completed_at=NOW(), "
                        "    error_message=:reason "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {
                        "reason": f"dispatch_failed:{reason}"[:500],
                        "id": execution_id,
                    },
                )
        results.append({
            "job_name": job_name, "execution_id": execution_id,
            "dispatched": dispatched, "reason": reason,
        })
    # Commit the job_executions rows (+ any failure flips) so the
    # API caller's next poll sees them. The caller already
    # `await session.commit()`-ed the run rows BEFORE invoking
    # us, so this commit is scoped to our inserts/updates only.
    try:
        await session.commit()
    except Exception as e:
        log.warning("post_commit.tracking_commit_failed", extra={"err": repr(e)})
    return results


def _json_args(extra_args: list[str], *, run_id: str) -> str:
    """Render the args body the admin UI's drawer expects. Kept
    minimal — operators don't usually inspect post-commit rows."""
    import json

    return json.dumps({
        "extra_args": extra_args,
        "auto_post_commit": True,
        "run_id": run_id,
    })
