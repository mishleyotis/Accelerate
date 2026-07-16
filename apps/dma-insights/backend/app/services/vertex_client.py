"""Vertex AI client wrapper — Gemini Flash + Pro + text-embedding-004.

Single async-friendly facade so routers don't import vertex SDK directly.
Each call goes through prompt template lookup + grounding bundle assembly +
post-generation validator. This module exposes the low-level calls; the
high-level orchestration lives inline in the two live paths (rag.py and
intelligence_builder.run_intelligence) + the synthesis_orchestrator
persistence/decision layer. (gemini_orchestrator was dead code — removed
2026-07-04.)

Resilience: `stream()` and `embed()` retry on transient errors (429/500/
ServiceUnavailable) with exponential backoff (2s/4s/8s, 3 attempts).
A peak-hour quota burst should self-heal instead of cascading to all
users as fail-closed fallbacks.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# Retry transient errors with exponential backoff. Not retried:
#   - 400 InvalidArgument (bad prompt / schema)
#   - 401/403 (auth)
#   - hard import errors
_RETRY_BACKOFFS_SEC = (2.0, 4.0, 8.0)


def _is_retryable_vertex_error(exc: BaseException) -> bool:
    """Inspect a Vertex SDK exception to decide whether to retry.

    We retry rate-limit (429) and transient server errors (500, 503).
    Auth + bad-input errors are NOT retryable — surface them immediately
    so the orchestrator can fail-closed.
    """
    name = type(exc).__name__
    # google.api_core.exceptions wraps these by name:
    if name in {
        "ResourceExhausted",      # 429 quota
        "ServiceUnavailable",     # 503
        "DeadlineExceeded",       # 504-ish
        "InternalServerError",    # 500
        "Aborted",                # transient abort
    }:
        return True
    # Some networks raise plain socket / connection errors.
    return name in {"ConnectionError", "TimeoutError", "ConnectionResetError"}


@dataclass
class GeminiCall:
    surface: str
    model: str  # "flash" | "pro"
    prompt: str
    response_schema: dict[str, Any] | None = None
    grounding_bundle: list[dict[str, Any]] | None = None
    max_output_tokens: int = 2048
    temperature: float = 0.2


class VertexClient:
    """Vertex AI wrapper. Real SDK calls are made lazily on first use so the
    package imports cleanly in environments without GCP credentials (tests,
    local migrations).
    """

    def __init__(self) -> None:
        self._initialized = False
        self._flash = None
        self._pro = None
        self._embedder = None

    def _init(self) -> None:
        if self._initialized:
            return
        s = get_settings()
        # Self-healing fast-fail: in a Vertex-cold context (qa-gates, the
        # deterministic-fallback test harness, or any deploy with creds the SA
        # can't actually use) DON'T let the SDK reach a real API call that can
        # HANG with no timeout. When DMA_DISABLE_VERTEX=1 (or no project is
        # configured) raise IMMEDIATELY so every caller's try/except routes to
        # its grounded deterministic fallback in milliseconds instead of
        # blocking until a step/job timeout. Cloud Build sets this on qa-gates
        # because the metadata server supplies SA creds — so the client would
        # otherwise authenticate and then stall on generate_content for the
        # full 300s step budget (the 2026-06-18 qa-gates hang).
        if os.environ.get("DMA_DISABLE_VERTEX", "").strip() in {"1", "true", "TRUE", "yes"}:
            raise RuntimeError("vertex disabled via DMA_DISABLE_VERTEX — using deterministic fallback")
        if not (s.vertex_project_id or "").strip():
            raise RuntimeError("vertex_project_id unset — using deterministic fallback")
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            from vertexai.language_models import TextEmbeddingModel
        except ImportError as e:
            raise RuntimeError(
                "google-cloud-aiplatform not installed; install backend deps"
            ) from e
        vertexai.init(project=s.vertex_project_id, location=s.vertex_location)
        self._flash = GenerativeModel(s.vertex_flash_model)
        self._pro = GenerativeModel(s.vertex_pro_model)
        self._embedder = TextEmbeddingModel.from_pretrained(s.vertex_embedding_model)
        self._initialized = True

    async def stream(self, call: GeminiCall) -> AsyncIterator[str]:
        """Yield token chunks from Gemini for SSE downstream.

        Retries the INITIAL connection on transient errors. Once the
        stream has started yielding tokens we don't retry — partial
        output is partial output, and re-running risks duplicate tokens
        landing in the user's SSE channel.
        """
        self._init()
        model = self._pro if call.model == "pro" else self._flash
        generation_config: dict[str, Any] = {
            "max_output_tokens": call.max_output_tokens,
            "temperature": call.temperature,
        }
        if call.response_schema is not None:
            generation_config["response_mime_type"] = "application/json"
            generation_config["response_schema"] = call.response_schema

        last_exc: BaseException | None = None
        resp = None
        for attempt, backoff in enumerate((*_RETRY_BACKOFFS_SEC, None)):
            try:
                resp = model.generate_content(  # type: ignore[union-attr]
                    call.prompt, generation_config=generation_config, stream=True
                )
                break
            except Exception as exc:
                last_exc = exc
                if not _is_retryable_vertex_error(exc) or backoff is None:
                    raise
                logger.warning(
                    "vertex.stream retryable error (attempt %d/%d): %s — sleeping %.1fs",
                    attempt + 1, len(_RETRY_BACKOFFS_SEC), type(exc).__name__, backoff,
                )
                await asyncio.sleep(backoff)
        if resp is None:
            # Defensive: shouldn't happen — either we got resp or we raised.
            raise RuntimeError("vertex.stream: exhausted retries") from last_exc

        for part in resp:
            if part.text:
                yield part.text

    def probe(self, *, timeout_sec: float = 15.0) -> None:
        """1-token reachability probe — raises on any auth/network/IAM
        failure, returns None on success.

        Used by `assert_production_ready` (startup gate) and
        `qa_gemini_surfaces` (deploy assertions) to prove the deploy can
        actually reach Vertex BEFORE the first AE click. `count_tokens`
        is the cheapest authenticated call the SDK exposes (no
        generation cost, still exercises ADC + IAM + the regional
        endpoint). Runs in a worker thread with a hard timeout so a
        wedged metadata server can't stall startup indefinitely.
        """
        self._init()
        import concurrent.futures

        def _count() -> None:
            self._flash.count_tokens("ping")  # type: ignore[union-attr]

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_count)
            fut.result(timeout=timeout_sec)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed texts. Retries on transient errors with backoff."""
        self._init()
        last_exc: BaseException | None = None
        for attempt, backoff in enumerate((*_RETRY_BACKOFFS_SEC, None)):
            try:
                embeddings = self._embedder.get_embeddings(texts)  # type: ignore[union-attr]
                return [list(e.values) for e in embeddings]
            except Exception as exc:
                last_exc = exc
                if not _is_retryable_vertex_error(exc) or backoff is None:
                    raise
                logger.warning(
                    "vertex.embed retryable error (attempt %d/%d): %s — sleeping %.1fs",
                    attempt + 1, len(_RETRY_BACKOFFS_SEC), type(exc).__name__, backoff,
                )
                await asyncio.sleep(backoff)
        raise RuntimeError("vertex.embed: exhausted retries") from last_exc


def resolve_model_id(alias: str) -> str:
    """Resolve a surface-level model alias ("flash"/"pro") to the real
    Vertex model id from settings — the provenance stamp every cached
    synthesis row carries (`output_json.model_id`). Unknown aliases
    pass through unchanged so already-resolved ids stay intact."""
    s = get_settings()
    if alias == "pro":
        return s.vertex_pro_model
    if alias == "flash":
        return s.vertex_flash_model
    return alias


# Module-level singleton — created lazily so importing this module is cheap.
_client: VertexClient | None = None


def get_vertex_client() -> VertexClient:
    global _client
    if _client is None:
        _client = VertexClient()
    return _client
