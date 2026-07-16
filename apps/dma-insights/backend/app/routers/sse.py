"""SSE channels for live UI updates.

Frontend opens an EventSource (via lib/sse.ts) against one of:
  GET /api/v1/sse/runs       — global active-runs ticker (Dashboard tile)
  GET /api/v1/sse/entity/{display_id}  — per-entity events (ingest, alerts,
                                          score updates)
  GET /api/v1/sse/intelligence/{surface}/{ref} — Gemini token stream

Events are pushed via Redis pub/sub. Producers (sheet_poller, ingest router,
embedder, gemini orchestrator) publish to channels:
  dma:sse:runs                  — { kind: 'run_state', request_id, status }
  dma:sse:entity:{entity_id}    — { kind, ... }
  dma:sse:gemini:{cache_key}    — { kind: 'token', text } | { kind: 'done' }
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep, get_redis

router = APIRouter(prefix="/api/v1/sse", tags=["sse"])

KEEPALIVE_SECONDS = 15.0
# Cap each SSE connection's lifetime (2026-06 cost safeguard). A tab left open
# otherwise pins a backend request — and a Cloud Run concurrency slot, billing
# CPU the whole time (idle-CPU throttling does NOT apply during an active
# request) — indefinitely, which can hold an instance up overnight. At the cap
# we emit a `reconnect` event and close; the browser's EventSource then
# auto-reconnects (re-subscribes + re-sends the snapshot), so the UI is
# unaffected and no live event is lost (events are also persisted in Postgres
# and the client re-syncs on (re)connect) — but the old request ends, letting
# idle instances scale to zero. 15 min balances reconnect overhead vs billing.
MAX_STREAM_SECONDS = 900.0


def _format_event(event: str, data: Any) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode()


async def _channel_stream(
    request: Request,
    channel: str,
    initial_event: tuple[str, Any] | None = None,
) -> AsyncGenerator[bytes, None]:
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    # If Redis drops connectivity mid-stream, `pubsub.get_message` raises
    # or returns None forever. We track consecutive timeouts so the
    # client gets a clear `error` event after ~30s of silence (long
    # enough to ride out brief network blips, short enough that a real
    # outage isn't masked by keepalives).
    consecutive_silent_polls = 0
    MAX_SILENT_BEFORE_NOTIFY = 30  # 30 * 1s timeout = 30s of silence
    try:
        if initial_event is not None:
            yield _format_event(initial_event[0], initial_event[1])
        stream_start = asyncio.get_event_loop().time()
        last_kept_alive = stream_start
        while True:
            if await request.is_disconnected():
                return
            # Bounded lifetime — close so the browser reconnects fresh,
            # releasing the request + concurrency slot (see MAX_STREAM_SECONDS).
            if asyncio.get_event_loop().time() - stream_start >= MAX_STREAM_SECONDS:
                yield _format_event("reconnect", {"reason": "max_stream_age"})
                return
            try:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
            except Exception as exc:
                # Redis fully unreachable — emit an error event the
                # frontend can act on (reconnect with backoff or show
                # a banner) instead of hanging.
                yield _format_event(
                    "error",
                    {"reason": "redis_unavailable", "detail": type(exc).__name__},
                )
                return
            now = asyncio.get_event_loop().time()
            if msg is None:
                consecutive_silent_polls += 1
                if consecutive_silent_polls == MAX_SILENT_BEFORE_NOTIFY:
                    # Not necessarily an error — could just be quiet.
                    # But surface it so the frontend can show "idle".
                    yield _format_event(
                        "stream_idle",
                        {"polls_silent": consecutive_silent_polls},
                    )
                if now - last_kept_alive >= KEEPALIVE_SECONDS:
                    yield b": keepalive\n\n"
                    last_kept_alive = now
                continue
            consecutive_silent_polls = 0
            data = msg.get("data")
            if isinstance(data, bytes | bytearray):
                data = data.decode("utf-8", errors="replace")
            event_name = "message"
            try:
                parsed = json.loads(data) if isinstance(data, str) else data
                if isinstance(parsed, dict) and "kind" in parsed:
                    event_name = str(parsed["kind"])
            except (TypeError, json.JSONDecodeError):
                parsed = data
            yield _format_event(event_name, parsed)
            last_kept_alive = now
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
        with contextlib.suppress(Exception):
            await pubsub.aclose()


@router.get("/runs")
async def sse_runs(request: Request, _user: CurrentUserDep) -> StreamingResponse:
    return StreamingResponse(
        _channel_stream(
            request, "dma:sse:runs",
            initial_event=("hello", {"channel": "runs"}),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/entity/{display_id}")
async def sse_entity(
    display_id: str,
    request: Request,
    _user: CurrentUserDep,
    session: SessionDep,
) -> StreamingResponse:
    ent = (
        await session.execute(
            text("SELECT id FROM entities WHERE display_id = :did"),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"entity {display_id} not found")
    channel = f"dma:sse:entity:{ent.id}"
    return StreamingResponse(
        _channel_stream(
            request, channel,
            initial_event=("hello", {"channel": channel, "entity": display_id}),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _intelligence_stream(
    request: Request,
    channel: str,
    *,
    surface: str,
    ref: str,
    session: SessionDep,
) -> AsyncGenerator[bytes, None]:
    """Subscribe to the Redis pubsub channel FIRST, then kick off the
    intelligence_builder task. Ordering matters — `BackgroundTasks` can
    schedule `run_intelligence` to begin publishing tokens before the
    pubsub subscriber binds, in which case the first chunk is silently
    dropped. By spawning the task here (after the subscribe inside
    `_channel_stream`'s try block fires) we guarantee no token is
    published before we're listening.
    """
    from app.services.intelligence_builder import run_intelligence

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    # Subscription is in place — only now is it safe to start the builder.
    builder_task = asyncio.create_task(
        run_intelligence(surface=surface, ref=ref, session=session, redis=redis),
    )
    try:
        yield _format_event("hello", {"channel": channel})
        stream_start = asyncio.get_event_loop().time()
        last_kept_alive = stream_start
        while True:
            if await request.is_disconnected():
                return
            # Bounded lifetime — close so the browser reconnects fresh,
            # releasing the request + concurrency slot (see MAX_STREAM_SECONDS).
            if asyncio.get_event_loop().time() - stream_start >= MAX_STREAM_SECONDS:
                yield _format_event("reconnect", {"reason": "max_stream_age"})
                return
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            now = asyncio.get_event_loop().time()
            if msg is None:
                # If the builder finished and there are no more messages
                # buffered, end the stream so the client can close cleanly.
                if builder_task.done() and now - last_kept_alive > 2.0:
                    return
                if now - last_kept_alive >= KEEPALIVE_SECONDS:
                    yield b": keepalive\n\n"
                    last_kept_alive = now
                continue
            data = msg.get("data")
            if isinstance(data, bytes | bytearray):
                data = data.decode("utf-8", errors="replace")
            event_name = "message"
            try:
                parsed = json.loads(data) if isinstance(data, str) else data
                if isinstance(parsed, dict) and "kind" in parsed:
                    event_name = str(parsed["kind"])
            except (TypeError, json.JSONDecodeError):
                parsed = data
            yield _format_event(event_name, parsed)
            last_kept_alive = now
    finally:
        # Cancel the builder if the client disconnected mid-stream so we
        # don't burn Vertex quota generating tokens nobody will read.
        if not builder_task.done():
            builder_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await builder_task
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
        with contextlib.suppress(Exception):
            await pubsub.aclose()


@router.get("/intelligence/{surface}/{ref}")
async def sse_intelligence(
    surface: str,
    ref: str,
    request: Request,
    _user: CurrentUserDep,
    session: SessionDep,
) -> StreamingResponse:
    """Subscribe to a Gemini surface's token stream.

    The builder task is dispatched from inside the generator AFTER the
    pubsub subscriber binds, eliminating the race where the first batch
    of tokens could be published before the subscriber was listening.
    """
    channel = f"dma:sse:gemini:{surface}:{ref}"
    return StreamingResponse(
        _intelligence_stream(
            request, channel, surface=surface, ref=ref, session=session,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
