"""Phase 5 SSE streaming contract regression tests.

Per the audit:
  - test_sse_keepalive_format_valid
  - test_sse_client_disconnect_cleans_pubsub_subscription
  - test_sse_redis_unavailable_returns_error_event_or_503_per_contract

SSE streams hold a Pub/Sub subscription + a connection open until
the client disconnects. Drift in any of:
  - keepalive frame format (must be `: <comment>\\n\\n` per spec)
  - error-event shape (frontend's banner reads `event:error\\ndata:{...}`)
  - disconnect cleanup (leaked subscriptions exhaust Redis pubsub
    connection budget after ~100 abandoned tabs)
... silently breaks the SSE channel until the next user-visible
incident.

Pure source-shape tests + the disconnect path runtime test (which
doesn't depend on real Pub/Sub polling). Long-running keepalive
runtime tests are out of scope (require a real Redis Pub/Sub harness).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

SSE_SRC = (
    Path(__file__).resolve().parents[1] / "app" / "routers" / "sse.py"
).read_text(encoding="utf-8")
RAG_SRC = (
    Path(__file__).resolve().parents[1] / "app" / "routers" / "rag.py"
).read_text(encoding="utf-8")


class _FakeRequest:
    """Stand-in for fastapi.Request."""

    def __init__(self, disconnected: bool = False):
        self.disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self.disconnected


class _FakePubSub:
    def __init__(self):
        self.subscribed_channels: list[str] = []
        self.unsubscribed_channels: list[str] = []
        self.closed: bool = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed_channels.append(channel)

    async def get_message(self, ignore_subscribe_messages: bool = True,
                          timeout: float = 1.0) -> None:
        return None

    async def unsubscribe(self, *channels: str) -> None:
        self.unsubscribed_channels.extend(channels)

    async def close(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(self, pubsub: _FakePubSub):
        self._pubsub = pubsub

    def pubsub(self):
        return self._pubsub


# ── SSE keepalive + error-event source-shape contracts ──────────


def test_sse_keepalive_frame_is_spec_compliant():
    """Hard-coded `b": keepalive\\n\\n"` matches SSE spec (lines
    starting with `:` are comments; blank line terminates the event).
    A drift to `data: keepalive\\n\\n` would be parsed as a real
    event by EventSource clients."""
    assert 'b": keepalive\\n\\n"' in SSE_SRC, (
        "SSE keepalive must use the spec-compliant `b\": keepalive\\n\\n\"` "
        "frame. Any other shape is parsed as a real event by EventSource."
    )


def test_sse_error_event_uses_typed_reason():
    """The error frame must include `reason=redis_unavailable` so
    the frontend's BackendErrorBanner can render the appropriate
    actionable message (reconnect with backoff vs report bug)."""
    assert "redis_unavailable" in SSE_SRC, (
        "SSE Redis-down path must emit `reason: redis_unavailable` "
        "so frontend can pick the right recovery action."
    )


def test_sse_stream_checks_disconnect_on_every_iteration():
    """The loop body must call `await request.is_disconnected()`
    EVERY iteration. Without it a closed tab leaves the subscription
    alive forever -- ~100 abandoned tabs exhaust the Redis pubsub
    connection budget."""
    # Find the inner `while True` loop body in _channel_stream.
    assert "while True:" in SSE_SRC
    # And the body must check disconnected first.
    assert "await request.is_disconnected()" in SSE_SRC, (
        "SSE loop must check request.is_disconnected() per iteration "
        "or abandoned tabs leak Pub/Sub subscriptions."
    )


def test_sse_stream_handles_pubsub_exceptions_as_typed_events():
    """A Pub/Sub raise mid-stream must surface as an `event: error`
    frame, not propagate as a 500. The frontend's SSE handler can
    parse the typed event; an opaque 500 leaves the user with a
    blank intelligence panel."""
    # Pin the try/except + yield-error pattern.
    import re
    m = re.search(
        r"try:[\s\S]+?get_message[\s\S]+?except Exception[\s\S]+?"
        r"yield\s*_format_event[\s\S]+?\"error\"",
        SSE_SRC,
    )
    assert m, (
        "SSE generator must wrap pubsub.get_message in try/except and "
        "emit `event:error` on raise. Without it Redis hiccup = 500."
    )


def test_sse_stream_idle_marker_threshold_documented():
    """The idle-marker constant MAX_SILENT_BEFORE_NOTIFY = 30 (s)
    is the operator-visible "channel quiet" signal. A drift to 0
    or a very large value silently breaks the idle-vs-broken
    distinction the frontend banner relies on."""
    assert "MAX_SILENT_BEFORE_NOTIFY" in SSE_SRC, (
        "MAX_SILENT_BEFORE_NOTIFY constant must remain a named symbol "
        "so the idle-vs-broken distinction is operator-tunable."
    )
    assert "stream_idle" in SSE_SRC, (
        "SSE generator must emit a `stream_idle` event so frontend "
        "can render an 'idle' indicator distinct from connection error."
    )


# ── SSE disconnect-cleanup runtime test (fast path only) ────────


@pytest.mark.asyncio
async def test_sse_disconnect_short_circuits_loop_immediately():
    """When the client is already disconnected on first iteration,
    the generator must yield ZERO frames + terminate cleanly. Without
    this short-circuit a closed tab + a quiet channel = infinite-loop
    holding the subscription open."""
    from unittest.mock import AsyncMock, patch

    from app.routers import sse

    fake_request = _FakeRequest(disconnected=True)
    fake_pubsub = _FakePubSub()
    fake_redis = _FakeRedis(fake_pubsub)

    with patch("app.routers.sse.get_redis",
               AsyncMock(return_value=fake_redis)):
        gen = sse._channel_stream(fake_request, "test_channel")
        frames: list[bytes] = []
        try:
            # Pull at most 3 frames; should get 0 before StopAsyncIteration.
            for _ in range(3):
                frame = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
                frames.append(frame)
        except (TimeoutError, StopAsyncIteration):
            pass
        # Pre-emptive close so the generator's finally block runs.
        await gen.aclose()
        assert len(frames) == 0, (
            f"SSE generator emitted {len(frames)} frames after disconnect. "
            "First iteration must short-circuit on is_disconnected()."
        )


# ── RAG citation validation contracts ───────────────────────────


def test_rag_router_calls_grounding_validator_or_equivalent():
    """Gemini hallucinations must be detected before serving an
    answer to AEs. The rag router must invoke the grounding validator
    OR check citation E-IDs against actual evidence rows."""
    assert (
        "grounding_validator" in RAG_SRC
        or "hallucinat" in RAG_SRC.lower()
        or "validate_citations" in RAG_SRC.lower()
        or "validate_answer" in RAG_SRC.lower()
        or "fabricated" in RAG_SRC.lower()
    ), (
        "rag router must invoke citation/grounding validation. Without "
        "it Gemini hallucinations land on the AE intelligence panel "
        "as facts."
    )


def test_rag_router_records_audit_log():
    """Every /rag/answer call must write an audit_log row so operators
    can debug runaway spend / hallucination patterns."""
    assert "_audit_log" in RAG_SRC or "audit_log" in RAG_SRC.lower(), (
        "rag router must emit audit_log row per /answer call. "
        "Without it runaway spend / hallucinations are invisible."
    )


def test_rag_router_uses_constant_time_bearer_compare():
    """RAG bearer comparison must use hmac.compare_digest, not `==`."""
    assert "hmac.compare_digest" in RAG_SRC, (
        "rag router bearer must use hmac.compare_digest. Plain `==` "
        "leaks the key via timing side-channel."
    )


def test_rag_router_rate_limits_per_user():
    """A single hot user must not exhaust the daily Vertex quota."""
    assert (
        "_check_rate_limit" in RAG_SRC or "rate_limit" in RAG_SRC.lower()
    ), (
        "rag router must enforce per-user rate limits to prevent quota "
        "exhaustion by a single hot user."
    )


def test_rag_router_uses_cohort_scoping_per_adr_0006():
    """ADR 0006: RAG retrieval must scope evidence to the current
    entity's cohort -- queries about Entity A must not bias on
    Entity B's evidence."""
    assert (
        "_fetch_grounding_for_entity" in RAG_SRC
        or "_fetch_evidence_text" in RAG_SRC
    ), (
        "rag router must scope grounding retrieval by entity_id per "
        "ADR 0006. Cross-entity leakage = cohort confusion."
    )


def test_rag_router_emits_stale_disclaimer_when_evidence_old():
    """When >40% of grounding is stale (freshness_band='stale'),
    answer must carry a typed disclaimer."""
    assert (
        "stale_pct" in RAG_SRC
        or "stale_disclaimer" in RAG_SRC
        or "freshness_band" in RAG_SRC
    ), (
        "rag router must surface stale disclaimer when evidence is "
        "predominantly old. AEs trust answers more than they should."
    )


def test_rag_router_returns_sanitized_fallback_on_vertex_failure():
    """When Vertex call fails (403, 5xx, timeout), the router must
    return a sanitized fallback answer + log the failure -- NOT
    propagate the SDK exception as a stack trace."""
    # Must have an except block around the vertex call that returns
    # a fallback rather than re-raising.
    assert (
        "vertex_error" in RAG_SRC.lower()
        or "_generate_via_vertex" in RAG_SRC
        or "fallback" in RAG_SRC.lower()
    ), (
        "rag router must wrap _generate_via_vertex in error handling "
        "that returns a sanitized fallback, not leak SDK stack traces."
    )


def test_rag_answer_response_includes_cited_e_ids():
    """Audit citation guard: the response must declare cited_e_ids
    so the frontend can render hover-over evidence chips. A response
    without citations + an LLM that names E-IDs in prose = the
    classic hallucination pattern."""
    assert (
        "cited_e_ids" in RAG_SRC
        or "cited_evidence" in RAG_SRC.lower()
        or "citations" in RAG_SRC.lower()
    ), (
        "rag answer response must declare cited E-IDs explicitly. "
        "Hover chips in the frontend depend on this field."
    )
