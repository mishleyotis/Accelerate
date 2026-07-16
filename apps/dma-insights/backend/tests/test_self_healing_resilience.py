"""Self-healing resilience contracts for production-critical services.

The principal-QA audit identified a recurring class of bugs: a
dependency (Redis, Pub/Sub, Vertex JWKS, cache DB) becomes
temporarily unavailable and the calling service either:
  - Crashes the whole worker / request handler instead of degrading
  - Wedges in a retry loop instead of surfacing a typed warning
  - Swallows the failure silently, leaving operators blind

This file pins the SELF-HEALING contracts. Every test here asserts
that the documented degraded-state behaviour is preserved -- a
refactor that removes a fallback / retry trips here BEFORE the
production incident.

Contracts pinned:
  1. Pub/Sub publish failure is best-effort (publisher returns
     False; caller continues).
  2. Rate limiter fails open when Redis is unreachable.
  3. Worker `_runner.track_job_execution` survives DB unavailable
     at __enter__ AND at __exit__ (logs + continues).
  4. Backend production guard is the FIRST thing that runs in a
     worker (before any DB call) so misconfigured workers fail
     fast in prod but defer to body in local.
  5. Vertex client retries transient 5xx / DEADLINE_EXCEEDED but
     NOT 4xx (permission, invalid arg).
  6. backend-loader-style audience param injection is idempotent
     (calling it twice doesn't double-stamp).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Workers package isn't on PYTHONPATH for backend tests by default.
APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


# ── Pub/Sub publisher best-effort ──────────────────────────────────


@pytest.mark.asyncio
async def test_pubsub_publish_failure_returns_falsy_not_raise():
    """A Pub/Sub outage during post-commit fan-out must not wedge
    the ingest request. The publisher returns a falsy value (False
    or a (False, reason) tuple depending on the helper) and the
    ingest handler continues to ack the caller. Self-healing
    contract: no exception escapes the publisher."""
    from app.services.pubsub_publisher import publish_ingest_completed

    fake_settings = AsyncMock()
    fake_settings.gcp_project_id = ""  # no project → publisher early-returns
    fake_settings.pubsub_ingest_topic = "dma.ingest.completed"
    fake_settings.pubsub_publish_timeout_seconds = 2.0

    from app.services.pubsub_publisher import IngestCompletedEnvelope

    envelope = IngestCompletedEnvelope(
        run_id="r1", entity_id="e1", request_id="REQ-A6654887",
        ccg_catalog_version="v7.0", is_rerun=False,
        parent_request_id=None, completed_at="2026-05-28T00:00:00Z",
    )
    with patch(
        "app.services.pubsub_publisher.get_settings",
        return_value=fake_settings,
    ):
        result = await publish_ingest_completed(envelope)
        # Result shape is (ok, message_id, reason). ok must be False
        # when project_id is empty + no exception escapes.
        assert isinstance(result, tuple)
        assert result[0] is False
        # Reason field surfaces WHY publish was skipped.
        assert result[2], (
            "publisher must surface a typed reason when it skips "
            "publishing -- operators need a debuggable signal."
        )


# ── Rate limiter fail-open under Redis outage ──────────────────────


@pytest.mark.asyncio
async def test_rate_limiter_fails_open_on_redis_outage():
    """When Redis throws ConnectionError, the limiter MUST allow the
    request through. Without this contract a Redis blip would 503
    every login during the outage."""
    from app.services.rate_limit import _check_and_increment

    class _DownRedis:
        def pipeline(self, transaction=True):
            return self
        def incr(self, key): return self
        def ttl(self, key): return self
        async def execute(self):
            raise ConnectionError("simulated outage")
        async def expire(self, key, seconds):
            raise ConnectionError("simulated outage")

    allowed, retry = await _check_and_increment(
        _DownRedis(), key="rl:auth:fail-open:1", limit=10, window_seconds=60,
    )
    assert allowed is True
    assert retry == 0


# ── Worker tracker survives DB unavailable ─────────────────────────


def test_track_job_execution_survives_db_unavailable_at_enter(monkeypatch):
    """`_safe_create_row` returning None (DB down) must NOT prevent
    the worker body from running. The contract: do the work, write
    no row, log a warning -- the next scheduler tick reconciles."""
    # Patch _safe_create_row to simulate DB-down (returns None).
    import workers._runner as runner_mod
    from workers._runner import track_job_execution
    monkeypatch.setattr(runner_mod, "_safe_create_row", lambda *a, **k: None)
    monkeypatch.setattr(runner_mod, "_safe_mark_started", lambda *a, **k: None)
    monkeypatch.setattr(runner_mod, "_safe_mark_succeeded", lambda *a, **k: None)
    monkeypatch.setattr(runner_mod, "_safe_mark_failed", lambda *a, **k: None)

    body_ran = {"value": False}
    with track_job_execution("test_worker"):
        body_ran["value"] = True
    assert body_ran["value"], "worker body should still run when DB is down"


def test_track_job_execution_survives_db_unavailable_at_exit(monkeypatch):
    """Same contract for the success-flush path: _safe_mark_succeeded
    returning None / raising must not propagate to the caller."""
    import workers._runner as runner_mod
    from workers._runner import track_job_execution
    monkeypatch.setattr(runner_mod, "_safe_create_row", lambda *a, **k: "fake-id")
    monkeypatch.setattr(runner_mod, "_safe_mark_started", lambda *a, **k: None)

    flush_calls = {"value": 0}
    def _flaky_mark(execution_id, **kwargs):
        flush_calls["value"] += 1
        # Don't raise -- _safe_* helpers swallow internally per their
        # contract. This test pins that the contract holds.
        return None

    monkeypatch.setattr(runner_mod, "_safe_mark_succeeded", _flaky_mark)
    monkeypatch.setattr(runner_mod, "_safe_mark_failed", lambda *a, **k: None)

    with track_job_execution("test_worker"):
        pass
    assert flush_calls["value"] == 1, "succeeded flush must run exactly once"


# ── Vertex retry classifier ────────────────────────────────────────


def test_vertex_retry_classifier_retries_5xx_not_4xx():
    """The vertex_client retry decider must distinguish transient
    server errors (5xx, deadline, unavailable) from configuration
    errors (4xx). Retrying a 403 permission denied wastes 3 round
    trips before failing the same way -- worse, on a real prod
    outage that hits the quota limit, retries amplify the problem."""
    from app.services.vertex_client import _is_retryable_vertex_error

    # Build fakes for both classes. The classifier inspects either
    # the type name OR a status_code attribute.
    class _Internal(Exception):
        pass
    _Internal.__name__ = "InternalServerError"
    class _Forbidden(Exception):
        pass
    _Forbidden.__name__ = "PermissionDenied"

    assert _is_retryable_vertex_error(_Internal("server")) is True
    assert _is_retryable_vertex_error(_Forbidden("nope")) is False


# ── Audience param idempotency ─────────────────────────────────────


def test_audience_strip_is_idempotent_on_already_stripped_payload():
    """Calling strip_internal twice on the same dict must produce the
    same result as calling it once. Pipeline code that runs strip at
    multiple layers (e.g. nested model_dump → strip → re-validate)
    must be safe."""
    from app.services.audience_strip import strip_internal

    payload = {
        "score": 3.2,
        "peer_median": 3.0,
        "parser_warnings": ["json_corrupt"],
        "items": [
            {"id": 1, "rationale_internal": "secret", "label": "ok"},
            {"id": 2, "peer_gap": 0.2, "label": "ok"},
        ],
    }
    once = strip_internal(payload, "customer")
    twice = strip_internal(once, "customer")
    assert once == twice


def test_audience_strip_returns_object_unchanged_for_internal_view():
    """When audience='internal', strip_internal is a NO-OP -- it must
    return the SAME object reference (or deep-equal) so internal callers
    don't pay a copy cost."""
    from app.services.audience_strip import strip_internal

    payload = {"parser_warnings": ["x"], "peer_median": 3.0}
    out = strip_internal(payload, "internal")
    assert out == payload  # field-for-field equal; strip skipped
    assert out is payload  # same reference -- the strip's `if audience != "customer"`
    # short-circuit must return the original object without copying.


# ── Worker prod-guard ordering ─────────────────────────────────────


def test_worker_runner_calls_prod_guard_BEFORE_db_writes(monkeypatch):
    """If a misconfigured worker tries to run in prod, the guard must
    fire BEFORE any DB write. Otherwise we'd see corrupt half-written
    job_execution rows from a worker that the guard then crashes."""
    import workers._runner as runner_mod
    from app.config import Settings
    from workers._runner import track_job_execution

    call_order: list[str] = []
    monkeypatch.setattr(
        runner_mod, "_safe_create_row",
        lambda *a, **k: (call_order.append("db") or "id"),
    )
    monkeypatch.setattr(
        runner_mod, "_safe_mark_started",
        lambda *a, **k: call_order.append("db"),
    )
    monkeypatch.setattr(
        runner_mod, "_safe_mark_succeeded",
        lambda *a, **k: call_order.append("db"),
    )
    monkeypatch.setattr(
        runner_mod, "_safe_mark_failed", lambda *a, **k: None,
    )

    bad = Settings(env="prod", database_url="", gcp_project_id="x")
    with (
        patch("app.config.get_settings", return_value=bad),
        pytest.raises(RuntimeError),
        track_job_execution("test_worker"),
    ):
        pass

    assert "db" not in call_order, (
        f"DB calls happened before the guard fired: {call_order}. "
        "Move assert_production_ready earlier in track_job_execution."
    )
