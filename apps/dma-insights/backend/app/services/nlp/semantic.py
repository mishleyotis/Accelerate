"""Gold-standard semantic tier — MiniLM sentence embeddings, offline.

The deterministic derive chain must decide *which evidence actually supports a
capability* without a network call (cold, credential-less regen). TF-IDF
(:class:`~app.services.nlp.similarity.LexicalIndex`) only sees lexical overlap,
so it mis-selects evidence that shares words but not meaning — the root cause of
the "insight card WHAT is an exec roster / privacy notice / balance-sheet fact"
misattribution the 2026-07-08 stress-test surfaced.

:class:`SemanticIndex` embeds text with ``all-MiniLM-L6-v2`` (384-dim,
l2-normalized so dot product IS cosine) and exposes the SAME ``fit`` / ``top_k``
interface as ``LexicalIndex`` — call sites swap tiers freely. It self-degrades:
if ``sentence-transformers`` or the baked model is unavailable (a core install
without the heavy nlp extra) it transparently delegates to ``LexicalIndex``, so
the "NLP layer never raises" contract holds. The model is lazy-loaded ONCE and
never imported on the serve path unless a caller actually asks for a tier —
torch stays out of API cold-start.

Model resolution (offline-first): ``DMA_ST_MODEL_DIR`` (a baked local dir) wins;
else ``DMA_ST_MODEL`` name under ``HF_HOME`` cache; default
``sentence-transformers/all-MiniLM-L6-v2``.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from collections.abc import Sequence
from typing import Any

from app.services.nlp.similarity import LexicalIndex

_log = logging.getLogger("dma.nlp.semantic")

_MODEL: Any = None
_MODEL_TRIED = False       # sticky True ONLY after a successful load or explicit disable
# Observability for the silent-degrade resilience gap (2026-07-14 audit): why is
# the semantic tier not active? None once loaded OK; "disabled_by_env" when the
# operator turned it off (expected, no alarm); "load_failed: …" when the baked
# model is missing/broken (the alarm case — logged once, surfaced via
# tier_health / DMA_REQUIRE_SEMANTIC).
_DEGRADE_REASON: str | None = None
# Self-heal (2026-07-14): a FAILED load no longer locks out permanently. We
# record the last-attempt time + count so a transient failure (slow disk, cold
# race) recovers on a later call after a cooldown, while a persistently-missing
# model stops retrying after _MAX_ATTEMPTS so we never hammer the loader.
_LAST_ATTEMPT_MONO: float | None = None
_ATTEMPTS = 0
_EMB_CACHE: dict[str, Any] = {}
_CACHE_CAP = 20000


def _retry_cooldown_sec() -> float:
    try:
        return float(os.environ.get("DMA_SEMANTIC_RETRY_COOLDOWN_SEC") or 60.0)
    except (TypeError, ValueError):
        return 60.0


def _max_load_attempts() -> int:
    try:
        return int(os.environ.get("DMA_SEMANTIC_MAX_LOAD_ATTEMPTS") or 5)
    except (TypeError, ValueError):
        return 5

# ── Cross-process embedding cache ───────────────────────────────────────
# The derive chain is many PROCESSES (deepen → subcap narratives → export)
# each re-embedding the same ~50k evidence excerpts from scratch — the
# in-memory cache dies with each step. A tiny sqlite blob store (sha1 →
# float16 vector) makes step N+1 start warm. Fully best-effort: any
# sqlite failure (readonly fs, corruption, concurrent writer) silently
# degrades to compute-only. Path override: DMA_EMB_CACHE (empty string
# disables).
_DISK_TRIED = False
_DISK_CONN: Any = None


def _disk_cache() -> Any:
    global _DISK_TRIED, _DISK_CONN
    if _DISK_TRIED:
        return _DISK_CONN
    _DISK_TRIED = True
    path = os.environ.get("DMA_EMB_CACHE")
    if path == "":
        return None
    if not path:
        import tempfile
        path = os.path.join(tempfile.gettempdir(), "dma_emb_cache.sqlite")
    try:
        import sqlite3
        conn = sqlite3.connect(path, timeout=2.0)
        conn.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v BLOB)")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
        _DISK_CONN = conn
    except Exception:
        _DISK_CONN = None
    return _DISK_CONN


def _disk_get_many(keys: list[str]) -> dict[str, Any]:
    conn = _disk_cache()
    if conn is None or not keys:
        return {}
    import numpy as np
    out: dict[str, Any] = {}
    try:
        for start in range(0, len(keys), 500):
            chunk = keys[start:start + 500]
            rows = conn.execute(
                f"SELECT k, v FROM emb WHERE k IN ({','.join('?' * len(chunk))})",
                chunk).fetchall()
            for k, blob in rows:
                vec = np.frombuffer(blob, dtype=np.float16).astype(np.float32)
                if vec.shape == (384,):
                    out[k] = vec
    except Exception:
        return {}
    return out


def _disk_put_many(items: list[tuple[str, Any]]) -> None:
    conn = _disk_cache()
    if conn is None or not items:
        return
    import contextlib

    import numpy as np
    with contextlib.suppress(Exception):
        conn.executemany(
            "INSERT OR REPLACE INTO emb (k, v) VALUES (?, ?)",
            [(k, np.asarray(v, dtype=np.float16).tobytes()) for k, v in items])
        conn.commit()


def model_src() -> str:
    """The configured MiniLM source (baked dir or HF name) — for diagnostics."""
    return os.environ.get("DMA_ST_MODEL_DIR") or os.environ.get(
        "DMA_ST_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def _construct_model(src: str) -> Any:
    """Build the SentenceTransformer (isolated so retry + tests can drive it)."""
    hf_home = os.environ.get("DMA_HF_HOME") or os.environ.get("HF_HOME") or "/install/hf"
    os.environ["HF_HOME"] = hf_home
    # Baked model → never touch the network at derive/serve time (the model
    # is vendored into the image; a HEAD to huggingface.co only fails).
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(src, cache_folder=hf_home)


def _load_model() -> Any:
    """Lazy load with bounded SELF-HEALING retry.

    Success/disable is sticky (``_MODEL_TRIED``). A load FAILURE degrades to
    lexical but leaves the tier retry-eligible: the next call after a cooldown
    re-attempts, so a transient failure recovers in-process instead of locking
    out until restart. After ``_MAX_ATTEMPTS`` consecutive failures it stops
    retrying (no hammering) until ``force_reload()`` or a restart.
    """
    global _MODEL, _MODEL_TRIED, _DEGRADE_REASON, _LAST_ATTEMPT_MONO, _ATTEMPTS
    if _MODEL_TRIED:
        return _MODEL
    if os.environ.get("DMA_DISABLE_SEMANTIC") == "1":
        _MODEL_TRIED = True
        _DEGRADE_REASON = "disabled_by_env"
        return None
    # Cooldown gate on the failure-retry path (skipped on the very first
    # attempt, where _LAST_ATTEMPT_MONO is None).
    if _LAST_ATTEMPT_MONO is not None:
        if _max_load_attempts() <= _ATTEMPTS:
            return None
        if (time.monotonic() - _LAST_ATTEMPT_MONO) < _retry_cooldown_sec():
            return None
    _LAST_ATTEMPT_MONO = time.monotonic()
    _ATTEMPTS += 1
    src = model_src()
    try:
        _MODEL = _construct_model(src)
        _MODEL_TRIED = True                     # success → sticky
        _DEGRADE_REASON = None
        _LAST_ATTEMPT_MONO = None               # clear retry state on success
        _ATTEMPTS = 0
    except Exception as e:  # no lib / no baked model / bad load → lexical (retry-eligible)
        _MODEL = None
        _DEGRADE_REASON = (f"load_failed (attempt {_ATTEMPTS}/{_max_load_attempts()}): "
                           f"{type(e).__name__}: {str(e)[:160]}")
        # ALARM: the degrade to TF-IDF used to be silent at runtime — if the
        # baked model is missing the WHOLE corpus quietly loses semantic
        # relevance. Loud + self-healing (retries after the cooldown).
        _log.warning(
            "semantic_tier_unavailable — degrading to lexical TF-IDF; will retry "
            "after %ss. reason=%s model_src=%s "
            "(set DMA_REQUIRE_SEMANTIC=1 to fail-loud in prod)",
            _retry_cooldown_sec(), _DEGRADE_REASON, src)
    return _MODEL


def force_reload() -> Any:
    """Reset the retry state and attempt a fresh load NOW — the self-heal hook a
    health check / preflight calls to recover a transiently-failed tier. No-op
    once loaded or when disabled by env."""
    global _MODEL_TRIED, _LAST_ATTEMPT_MONO, _ATTEMPTS
    if _MODEL_TRIED and _MODEL is not None:
        return _MODEL
    if os.environ.get("DMA_DISABLE_SEMANTIC") == "1":
        return None
    _MODEL_TRIED = False
    _LAST_ATTEMPT_MONO = None
    _ATTEMPTS = 0
    return _load_model()


def _reset_load_state() -> None:
    """Test hook: forget any loaded/failed/disabled state so the next
    ``_load_model`` attempts fresh."""
    global _MODEL, _MODEL_TRIED, _DEGRADE_REASON, _LAST_ATTEMPT_MONO, _ATTEMPTS
    _MODEL = None
    _MODEL_TRIED = False
    _DEGRADE_REASON = None
    _LAST_ATTEMPT_MONO = None
    _ATTEMPTS = 0


def model_available() -> bool:
    return _load_model() is not None


def degrade_reason() -> str | None:
    """None when the semantic tier is loaded and active; else why it isn't
    (``disabled_by_env`` — expected/quiet, or ``load_failed: …`` — the alarm)."""
    _load_model()
    return _DEGRADE_REASON


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()  # cache key only, not security


def _encode(model: Any, texts: list[str]) -> Any:
    import numpy as np
    out: list[Any] = [None] * len(texts)
    todo, todo_idx = [], []
    for i, t in enumerate(texts):
        v = _EMB_CACHE.get(_key(t))
        if v is None:
            todo.append(t)
            todo_idx.append(i)
        else:
            out[i] = v
    if todo:
        # second rung: the cross-process disk cache (warm after the first
        # chain step touches these texts)
        disk = _disk_get_many([_key(t) for t in todo])
        still, still_idx = [], []
        for j, i in enumerate(todo_idx):
            v = disk.get(_key(todo[j]))
            if v is not None:
                out[i] = v
                if len(_EMB_CACHE) < _CACHE_CAP:
                    _EMB_CACHE[_key(todo[j])] = v
            else:
                still.append(todo[j])
                still_idx.append(i)
        todo, todo_idx = still, still_idx
    if todo:
        vecs = model.encode(todo, normalize_embeddings=True, show_progress_bar=False,
                            convert_to_numpy=True)
        fresh: list[tuple[str, Any]] = []
        for j, i in enumerate(todo_idx):
            v = vecs[j]
            out[i] = v
            k = _key(todo[j])
            fresh.append((k, v))
            if len(_EMB_CACHE) < _CACHE_CAP:
                _EMB_CACHE[k] = v
        _disk_put_many(fresh)
    return np.vstack(out)


class SemanticIndex:
    """Cosine top-k over an id→text corpus, MiniLM tier with lexical fallback.

    ``min_score`` defaults to 0.30 — MiniLM cosines run higher and denser than
    TF-IDF, so the 0.08 lexical floor would admit noise. Callers may override.
    """

    def __init__(self) -> None:
        self._ids: list[Any] = []
        self._matrix: Any = None
        self._texts: list[str] = []
        self._fallback: LexicalIndex | None = None

    def fit(self, docs: Sequence[tuple[Any, str]]) -> None:
        self._ids = [d for d, _ in docs]
        self._texts = [t or "" for _, t in docs]
        self._matrix = None
        self._fallback = None
        model = _load_model()
        if model is None or not self._texts:
            self._fallback = LexicalIndex()
            self._fallback.fit(docs)
            return
        try:
            self._matrix = _encode(model, self._texts)
        except Exception as e:  # encode failure → degrade to lexical, never raise
            _log.warning("semantic_encode_failed — degrading this index to "
                         "lexical TF-IDF. reason=%s", f"{type(e).__name__}: {e}")
            self._matrix = None
            self._fallback = LexicalIndex()
            self._fallback.fit(docs)

    def top_k(self, query: str, k: int, min_score: float = 0.30) -> list[tuple[Any, float]]:
        if self._fallback is not None:
            # lexical floor differs; scale the caller's semantic floor down
            return self._fallback.top_k(query, k, min_score=min(min_score, 0.10))
        if self._matrix is None or not query or k <= 0:
            return []
        model = _load_model()
        if model is None:
            return []
        import numpy as np
        q = _encode(model, [query])[0]
        scores = self._matrix @ q
        order = np.argsort(scores)[::-1][:k]
        return [(self._ids[i], float(scores[i])) for i in order if scores[i] >= min_score]

    def vector(self, doc_id: Any) -> Any:
        """The fitted document's normalized embedding (None on lexical
        fallback / unknown id) — lets callers run diversity math (MMR)
        without re-encoding."""
        if self._matrix is None:
            return None
        try:
            return self._matrix[self._ids.index(doc_id)]
        except (ValueError, IndexError):
            return None

    def relevance(self, query: str, candidate: str) -> float:
        """Single-pair cosine in [0,1]; 0.0 when a tier is unavailable."""
        if not query or not candidate:
            return 0.0
        model = _load_model()
        if model is None:
            idx = LexicalIndex()
            idx.fit([(0, candidate)])
            hits = idx.top_k(query, 1, min_score=0.0)
            return hits[0][1] if hits else 0.0
        import numpy as np
        m = _encode(model, [query, candidate])
        return float(np.dot(m[0], m[1]))


def embed(texts: Sequence[str]) -> Any:
    """L2-normalized MiniLM embeddings for ``texts`` as an (N, 384) float array,
    or **None** when the semantic tier is unavailable (no lib / no baked model /
    disabled). Callers that want an offline-first vector (e.g. the V4 grounding
    check) use this and ABSTAIN when it returns None — never fail-closed just
    because embeddings aren't available. Never raises."""
    items = [t or "" for t in texts]
    if not items:
        return None
    model = _load_model()
    if model is None:
        return None
    try:
        return _encode(model, items)
    except Exception as e:
        _log.warning("semantic_embed_failed reason=%s", f"{type(e).__name__}: {e}")
        return None


def preferred_index() -> SemanticIndex:
    """Factory: the best available tier behind the common interface."""
    return SemanticIndex()
