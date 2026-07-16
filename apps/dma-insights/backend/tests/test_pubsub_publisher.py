"""Pub/Sub publish tests for `dma.ingest.completed`.

Each test maps onto one of the state branches documented in
`app.services.pubsub_publisher`:
  publish_succeeds            → ok=True, message_id set
  publish_disabled_in_dev     → gcp_project_id empty
  publish_fails_topic_missing → NotFound from publish()
  publish_fails_auth_missing  → DefaultCredentialsError
  publish_timeout             → future.result() blocks past timeout
  envelope shape              → JSON body keys + attrs
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.pubsub_publisher import (
    IngestCompletedEnvelope,
    publish_ingest_completed,
)


def _envelope(**overrides) -> IngestCompletedEnvelope:
    defaults = {
        "run_id": "00000000-0000-0000-0000-0000000000aa",
        "entity_id": "00000000-0000-0000-0000-0000000000bb",
        "request_id": "REQ-DEADBEEF",
        "ccg_catalog_version": "v7.0",
        "completed_at": "2026-05-23T10:00:00+00:00",
        "is_rerun": False,
        "parent_request_id": None,
    }
    defaults.update(overrides)
    return IngestCompletedEnvelope(**defaults)


# ---------- envelope shape ----------

def test_envelope_to_json_bytes_keys() -> None:
    env = _envelope()
    body = json.loads(env.to_json_bytes())
    assert body["run_id"] == env.run_id
    assert body["entity_id"] == env.entity_id
    assert body["request_id"] == env.request_id
    assert body["ccg_catalog_version"] == "v7.0"
    assert body["is_rerun"] is False
    assert body["parent_request_id"] is None
    assert body["completed_at"] == "2026-05-23T10:00:00+00:00"


def test_envelope_includes_parent_when_rerun() -> None:
    env = _envelope(is_rerun=True, parent_request_id="REQ-PARENT01")
    body = json.loads(env.to_json_bytes())
    assert body["is_rerun"] is True
    assert body["parent_request_id"] == "REQ-PARENT01"


# ---------- state-branch tests ----------

@pytest.mark.asyncio
async def test_publish_disabled_when_no_project_id() -> None:
    """publish_disabled_in_dev branch."""
    ok, mid, reason = await publish_ingest_completed(
        _envelope(), client=MagicMock(), project_id="",
    )
    assert ok is False
    assert mid is None
    assert reason == "disabled"


@pytest.mark.asyncio
async def test_publish_succeeds_via_stub_client() -> None:
    """publish_succeeds branch — happy path."""
    fake_future = MagicMock()
    fake_future.result = MagicMock(return_value="msg-abc-123")
    fake_client = MagicMock()
    fake_client.topic_path = MagicMock(return_value="projects/p/topics/t")
    fake_client.publish = MagicMock(return_value=fake_future)

    ok, mid, reason = await publish_ingest_completed(
        _envelope(), client=fake_client,
        project_id="my-project", topic_id="dma.ingest.completed",
    )
    assert ok is True
    assert mid == "msg-abc-123"
    assert reason is None
    # The publisher was called exactly once
    assert fake_client.publish.call_count == 1
    args, kwargs = fake_client.publish.call_args
    assert args[0] == "projects/p/topics/t"
    # JSON body present in second positional
    body = json.loads(args[1])
    assert body["run_id"] == _envelope().run_id
    # Attributes (kwargs) include run_id + request_id for filtering
    assert kwargs["run_id"] == _envelope().run_id
    assert kwargs["request_id"] == _envelope().request_id


@pytest.mark.asyncio
async def test_publish_topic_not_found_returns_soft_failure() -> None:
    """publish_fails_topic_missing branch."""
    class _NotFound(Exception):
        pass
    _NotFound.__name__ = "NotFound"

    fake_client = MagicMock()
    fake_client.topic_path = MagicMock(return_value="projects/p/topics/t")
    fake_client.publish = MagicMock(side_effect=_NotFound("missing"))

    ok, mid, reason = await publish_ingest_completed(
        _envelope(), client=fake_client, project_id="my-project",
    )
    assert ok is False
    assert mid is None
    assert reason == "topic_not_found"


@pytest.mark.asyncio
async def test_publish_auth_missing_returns_soft_failure() -> None:
    """publish_fails_auth_missing branch."""
    class _DefaultCredentialsError(Exception):
        pass
    _DefaultCredentialsError.__name__ = "DefaultCredentialsError"

    fake_client = MagicMock()
    fake_client.topic_path = MagicMock(return_value="projects/p/topics/t")
    fake_client.publish = MagicMock(side_effect=_DefaultCredentialsError("no ADC"))

    ok, _mid, reason = await publish_ingest_completed(
        _envelope(), client=fake_client, project_id="my-project",
    )
    assert ok is False
    assert reason == "auth_unavailable"


@pytest.mark.asyncio
async def test_publish_timeout_returns_soft_failure() -> None:
    """publish_timeout branch — future.result blocks past timeout."""
    fake_future = MagicMock()

    def _blocking_result(_timeout=None):
        # Block longer than the test's allotted timeout
        import time as _t
        _t.sleep(2.0)
        return "should-not-arrive"

    fake_future.result = _blocking_result
    fake_client = MagicMock()
    fake_client.topic_path = MagicMock(return_value="projects/p/topics/t")
    fake_client.publish = MagicMock(return_value=fake_future)

    ok, _mid, reason = await publish_ingest_completed(
        _envelope(), client=fake_client, project_id="my-project",
        timeout=0.1,
    )
    assert ok is False
    assert reason == "timeout"


# ---------- ingest is never blocked by publish failure ----------

@pytest.mark.asyncio
async def test_publish_post_commit_never_raises_on_publisher_failure() -> None:
    """`publish_post_commit` swallows publisher exceptions so the
    backfill / live ingest never wedges."""
    from app.services.parsers.package_persist import publish_post_commit

    async def _boom(envelope):
        raise RuntimeError("publisher kaboom")

    ok, _mid, reason = await publish_post_commit(
        db_run_id="00000000-0000-0000-0000-000000000001",
        entity_id="00000000-0000-0000-0000-000000000002",
        request_id="REQ-AAA",
        ccg_catalog_version="v7.0",
        publisher=_boom,
    )
    assert ok is False
    assert reason in ("outer_error", "disabled")  # depending on env
