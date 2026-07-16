"""Pub/Sub publisher for the `dma.ingest.completed` topic.

State transitions:
  publish_succeeds
    → topic accepted the message; returns (True, message_id, None).
      The embedder worker picks it up on its subscription and runs.
  publish_fails_topic_missing
    → google.api_core.exceptions.NotFound bubbles up; we swallow,
      log a structured warning, return (False, None, "topic_not_found").
      Ingest itself does NOT roll back.
  publish_fails_auth_missing
    → DefaultCredentialsError (no ADC) or 401/403 from Google;
      log + swallow; return (False, None, "auth_unavailable").
  publish_disabled_in_dev
    → settings.gcp_project_id is empty (local dev) or the import of
      google.cloud.pubsub_v1 fails because the dep isn't installed.
      Returns (False, None, "disabled") with no log spam.
  publish_timeout
    → publish() future doesn't resolve within
      settings.pubsub_publish_timeout_seconds. We log + swallow;
      the embedder will still catch up on its nightly catch-all sweep.

Best-effort by design. The ingest pipeline must never wedge on a
Pub/Sub outage.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from app.config import get_settings

log = structlog.get_logger()


@dataclass(frozen=True)
class IngestCompletedEnvelope:
    """The canonical message shape published on ingest success."""
    run_id: str
    entity_id: str
    request_id: str
    ccg_catalog_version: str
    completed_at: str           # ISO8601 UTC
    is_rerun: bool = False
    parent_request_id: str | None = None

    def to_json_bytes(self) -> bytes:
        d: dict[str, Any] = {
            "run_id": self.run_id,
            "entity_id": self.entity_id,
            "request_id": self.request_id,
            "ccg_catalog_version": self.ccg_catalog_version,
            "completed_at": self.completed_at,
            "is_rerun": self.is_rerun,
            "parent_request_id": self.parent_request_id,
        }
        return json.dumps(d, default=str).encode("utf-8")


PublishResult = tuple[bool, str | None, str | None]


async def publish_ingest_completed(
    envelope: IngestCompletedEnvelope,
    *,
    client: Any | None = None,
    project_id: str | None = None,
    topic_id: str | None = None,
    timeout: float | None = None,
) -> PublishResult:
    """Best-effort publish to the ingest-completed topic.

    Returns ``(ok, message_id, reason)`` so the caller can log a
    structured outcome but never block on publish failure.

    Parameters are dependency-injected so tests can pass a stub client
    without touching real env vars or imports.
    """
    settings = get_settings()
    project_id = project_id or settings.gcp_project_id
    topic_id = topic_id or settings.pubsub_ingest_topic
    timeout = timeout if timeout is not None else settings.pubsub_publish_timeout_seconds

    if not project_id:
        # publish_disabled_in_dev — local without GCP project bound.
        return (False, None, "disabled")

    # Lazy import so the backend boots without google-cloud-pubsub installed.
    try:
        if client is None:
            from google.cloud import pubsub_v1
            client = pubsub_v1.PublisherClient()
    except Exception as e:
        log.warning(
            "pubsub.publish.skipped",
            reason="client_init_failed", err=str(e),
            topic=topic_id, run_id=envelope.run_id,
        )
        return (False, None, "disabled")

    topic_path = (
        client.topic_path(project_id, topic_id)
        if hasattr(client, "topic_path")
        else f"projects/{project_id}/topics/{topic_id}"
    )

    try:
        future = client.publish(
            topic_path,
            envelope.to_json_bytes(),
            run_id=envelope.run_id,
            request_id=envelope.request_id,
        )
    except Exception as e:
        # NotFound on topic, auth, etc.
        name = type(e).__name__
        reason = (
            "topic_not_found" if "NotFound" in name
            else "auth_unavailable" if "Default" in name or "Permission" in name
            else "publish_error"
        )
        log.warning(
            "pubsub.publish.failed",
            reason=reason, err=str(e), err_type=name,
            topic=topic_id, run_id=envelope.run_id,
        )
        return (False, None, reason)

    # The publisher returns a concurrent.futures.Future. We wrap it in
    # asyncio.to_thread so we can await with a timeout without blocking
    # the event loop. If timeout fires, treat as a soft failure.
    try:
        message_id = await asyncio.wait_for(
            asyncio.to_thread(future.result, timeout), timeout=timeout + 0.5,
        )
    except TimeoutError:
        log.warning(
            "pubsub.publish.timeout", topic=topic_id, run_id=envelope.run_id,
        )
        return (False, None, "timeout")
    except Exception as e:
        log.warning(
            "pubsub.publish.future_failed", err=str(e), topic=topic_id,
            run_id=envelope.run_id,
        )
        return (False, None, "future_error")

    log.info(
        "pubsub.publish.ok", topic=topic_id, run_id=envelope.run_id,
        message_id=message_id,
    )
    return (True, str(message_id), None)


async def publish_admin_job_trigger(
    *,
    job_name: str,
    execution_id: str,
    mode: str | None = None,
    args: dict | None = None,
    client: Any | None = None,
    project_id: str | None = None,
    topic_id: str | None = None,
    timeout: float | None = None,
) -> PublishResult:
    """Best-effort publish of an admin-triggered worker run.

    State branches (mirror of publish_ingest_completed):
      publish_succeeds        — (True, msg_id, None)
      publish_disabled_in_dev — (False, None, 'disabled')  ← local env
      publish_fails_topic_missing — (False, None, 'topic_not_found')
      publish_fails_auth_missing  — (False, None, 'auth_unavailable')
      publish_timeout         — (False, None, 'timeout')

    The job_executions row IS the authoritative trigger record; this
    fan-out is a fast path for subscribed workers. Workers that aren't
    Pub/Sub-subscribed (yet) still see the row and can act on it via
    the next scheduled poll.
    """
    settings = get_settings()
    project_id = project_id or settings.gcp_project_id
    topic_id = topic_id or "admin-job-triggered"
    timeout = timeout if timeout is not None else settings.pubsub_publish_timeout_seconds

    if not project_id:
        return (False, None, "disabled")

    try:
        if client is None:
            from google.cloud import pubsub_v1
            client = pubsub_v1.PublisherClient()
    except Exception as e:
        log.warning(
            "pubsub.publish.skipped",
            reason="client_init_failed", err=str(e),
            topic=topic_id, job_name=job_name,
        )
        return (False, None, "disabled")

    topic_path = (
        client.topic_path(project_id, topic_id)
        if hasattr(client, "topic_path")
        else f"projects/{project_id}/topics/{topic_id}"
    )

    payload = json.dumps({
        "schema_version": "v1", "job_name": job_name,
        "execution_id": execution_id, "mode": mode, "args": args or {},
        "triggered_at": datetime.now(tz=UTC).isoformat(),
    }, default=str).encode("utf-8")

    try:
        future = client.publish(
            topic_path, payload, job_name=job_name,
            execution_id=execution_id,
        )
    except Exception as e:
        name = type(e).__name__
        reason = (
            "topic_not_found" if "NotFound" in name
            else "auth_unavailable" if "Default" in name or "Permission" in name
            else "publish_error"
        )
        log.warning(
            "pubsub.publish.failed",
            reason=reason, err=str(e), err_type=name,
            topic=topic_id, job_name=job_name,
        )
        return (False, None, reason)

    try:
        message_id = await asyncio.wait_for(
            asyncio.to_thread(future.result, timeout), timeout=timeout + 0.5,
        )
    except TimeoutError:
        return (False, None, "timeout")
    except Exception as e:
        log.warning(
            "pubsub.publish.future_failed", err=str(e), topic=topic_id,
            job_name=job_name,
        )
        return (False, None, "future_error")

    log.info(
        "pubsub.publish.ok", topic=topic_id, job_name=job_name,
        execution_id=execution_id, message_id=message_id,
    )
    return (True, str(message_id), None)
