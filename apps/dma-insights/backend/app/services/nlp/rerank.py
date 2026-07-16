"""Intelligence tier — cross-encoder re-ranking of evidence↔capability SUPPORT.

The bi-encoder (``semantic.SemanticIndex``, MiniLM) is *recall*: it embeds the
capability and every candidate evidence INDEPENDENTLY and ranks by cosine. That
is fast but "basic semantic matching" — it is fooled by word-overlap decoys (a
privacy notice out-ranks the real underwriting evidence on the shared word
"member"), and its scores plateau around ~0.5 even for a true match.

This tier adds *precision + calibrated confidence*: a CROSS-ENCODER reads the
(capability, evidence) pair JOINTLY with cross-attention and scores how strongly
the evidence supports the capability. Joint attention is what lets it reason
about the RELATIONSHIP (not just shared tokens), so decoys collapse to ~0 while
genuine support scores high. The two tiers compose as the textbook
retrieve-then-rerank pipeline:

    bi-encoder top-N (recall)  →  cross-encoder re-rank (precision)  →  fuse

``fuse`` blends the cross-encoder relevance with the bi-encoder cosine into a
single calibrated ``support`` in [0, 1]: near-verbatim support saturates toward
~0.95, a looser paraphrase lands ~0.5-0.7 (honest — it IS a looser match), and a
topical-but-unsupported decoy falls to ~0. Callers gate on ``support`` instead
of raw cosine, which is what kills the misattribution.

Resilience: the model is lazy-loaded ONCE from a baked, OFFLINE dir
(``DMA_CE_MODEL_DIR``, default ``/install/st-ce``); torch stays off the API
serve path (only a re-rank call loads it). Any failure (no lib / no baked model
/ encode error) degrades to bi-encoder-only fusion — the "NLP never raises"
contract holds. Set ``DMA_DISABLE_RERANK=1`` to force the bi-encoder tier.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

_log = logging.getLogger("dma.nlp.rerank")

_CE: Any = None
_CE_TRIED = False          # sticky True ONLY after a successful load or explicit disable
# Why the cross-encoder precision tier isn't active (parallels semantic.py):
# None once loaded; "disabled_by_env"; "load_failed: …" (the alarm case).
_CE_DEGRADE_REASON: str | None = None
# Self-heal (2026-07-14): a FAILED CE load retries after a cooldown instead of
# locking out until restart; stops after _MAX_ATTEMPTS to avoid hammering.
_CE_LAST_ATTEMPT_MONO: float | None = None
_CE_ATTEMPTS = 0


def _ce_retry_cooldown_sec() -> float:
    try:
        return float(os.environ.get("DMA_RERANK_RETRY_COOLDOWN_SEC") or 60.0)
    except (TypeError, ValueError):
        return 60.0


def _ce_max_load_attempts() -> int:
    try:
        return int(os.environ.get("DMA_RERANK_MAX_LOAD_ATTEMPTS") or 5)
    except (TypeError, ValueError):
        return 5

# ── Deploy safeguard: cumulative cross-encoder wall-clock budget per process ──
# The cross-encoder is the one heavy step in the derive hot path. On a 94-client
# regen it must NEVER let a derive step blow DERIVE_STEP_TIMEOUT_SEC and get
# SIGKILLed (which would lose every card the step produced). Once this process
# has spent the budget inside the cross-encoder, further calls transparently
# return None → callers degrade to the bi-encoder cosine (still correct, just
# less precise) and the step finishes fast. The bulk of the work still gets the
# precision lift; only the tail (if the box is slow — e.g. the 2 vCPU
# post-deploy job) degrades.
#
# The budget AUTO-SCALES to half the derive step timeout when not set
# explicitly, so it always leaves the other half for the bi-encoder +
# composition and can never itself cause a timeout — on any CPU, in any deploy
# path (regen / qa-gates / post-deploy-refresh all set DERIVE_STEP_TIMEOUT_SEC).
def _envfloat(name: str, default: float) -> float:
    """Parse a float env var, never raising at import on a malformed value —
    the "NLP tier never raises" contract must hold even for a bad config."""
    try:
        v = os.environ.get(name)
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _default_ce_budget() -> float:
    """<= 0 (e.g. DMA_RERANK_BUDGET_SEC=0) means UNLIMITED — the budget never
    exhausts. The budget is a DERIVE-chain guard (degrade to bi-encoder
    instead of a SIGKILL near DERIVE_STEP_TIMEOUT_SEC); processes whose
    output is COMPARED or BAKED (export_startup_pages, qa_pack_parity) must
    run unlimited, or the pack captures a degraded tier while the parity
    gate's fresh process serves the full one (build 5d3f7f78: insights
    linked_e_ids 9!=11 — the sweep exhausted the process-global budget
    before the late-alphabet clients exported)."""
    explicit = os.environ.get("DMA_RERANK_BUDGET_SEC")
    if explicit not in (None, ""):
        v = _envfloat("DMA_RERANK_BUDGET_SEC", 180.0)
        return float("inf") if v <= 0 else v
    step = _envfloat("DERIVE_STEP_TIMEOUT_SEC", 300.0)
    return max(60.0, min(900.0, 0.5 * step))


_CE_BUDGET_SEC = _default_ce_budget()
_CE_SPENT = 0.0
_CE_EXHAUSTED = False
# Chunk the cross-encoder predict so the wall-clock budget is re-checked between
# chunks — one large claim can't overshoot the budget (and DERIVE_STEP_TIMEOUT_SEC)
# inside a single predict before the guard trips.
_CE_CHUNK = int(_envfloat("DMA_RERANK_CHUNK", 48.0))
# Band-limit: the cross-encoder only changes the verdict in the AMBIGUOUS cosine
# band (word-overlap decoys live here). A very high cosine is already clearly
# supported and a very low one clearly unrelated — skipping the cross-encoder on
# those cuts most of the calls with no accuracy loss. Callers pass bi_cos.
_CE_BAND_LO = _envfloat("DMA_RERANK_BAND_LO", 0.15)
_CE_BAND_HI = _envfloat("DMA_RERANK_BAND_HI", 0.82)


def ce_src() -> str:
    """The configured cross-encoder source dir — for diagnostics."""
    return os.environ.get("DMA_CE_MODEL_DIR", "/install/st-ce")


def _construct_ce(src: str) -> Any:
    """Build the CrossEncoder (isolated so retry + tests can drive it)."""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from sentence_transformers import CrossEncoder
    # max_length caps the joint pair so a long evidence blob can't blow up
    # latency; 256 covers a finding + an evidence excerpt comfortably.
    return CrossEncoder(src, max_length=256)


def _load_ce() -> Any:
    """Lazy load with bounded SELF-HEALING retry (parallels semantic._load_model).

    Success/disable is sticky; a load FAILURE degrades to bi-encoder-only but
    retries after a cooldown so a transient failure recovers in-process, up to
    _MAX_ATTEMPTS.
    """
    global _CE, _CE_TRIED, _CE_DEGRADE_REASON, _CE_LAST_ATTEMPT_MONO, _CE_ATTEMPTS
    if _CE_TRIED:
        return _CE
    if os.environ.get("DMA_DISABLE_RERANK") == "1" or os.environ.get("DMA_DISABLE_SEMANTIC") == "1":
        _CE_TRIED = True
        _CE_DEGRADE_REASON = "disabled_by_env"
        return None
    if _CE_LAST_ATTEMPT_MONO is not None:
        if _ce_max_load_attempts() <= _CE_ATTEMPTS:
            return None
        if (time.monotonic() - _CE_LAST_ATTEMPT_MONO) < _ce_retry_cooldown_sec():
            return None
    _CE_LAST_ATTEMPT_MONO = time.monotonic()
    _CE_ATTEMPTS += 1
    src = ce_src()
    try:
        _CE = _construct_ce(src)
        _CE_TRIED = True                        # success → sticky
        _CE_DEGRADE_REASON = None
        _CE_LAST_ATTEMPT_MONO = None
        _CE_ATTEMPTS = 0
    except Exception as e:  # no lib / no baked model / load error → bi-encoder-only
        _CE = None
        _CE_DEGRADE_REASON = (f"load_failed (attempt {_CE_ATTEMPTS}/{_ce_max_load_attempts()}): "
                              f"{type(e).__name__}: {str(e)[:160]}")
        # ALARM: precision re-rank silently dropping to the bi-encoder is a
        # quality regression the runtime never surfaced. Loud + self-healing.
        _log.warning(
            "cross_encoder_unavailable — degrading to bi-encoder-only fusion; will "
            "retry after %ss. reason=%s model_src=%s",
            _ce_retry_cooldown_sec(), _CE_DEGRADE_REASON, src)
    return _CE


def force_reload() -> Any:
    """Reset retry state + attempt a fresh CE load NOW (self-heal hook)."""
    global _CE_TRIED, _CE_LAST_ATTEMPT_MONO, _CE_ATTEMPTS
    if _CE_TRIED and _CE is not None:
        return _CE
    if os.environ.get("DMA_DISABLE_RERANK") == "1" or os.environ.get("DMA_DISABLE_SEMANTIC") == "1":
        return None
    _CE_TRIED = False
    _CE_LAST_ATTEMPT_MONO = None
    _CE_ATTEMPTS = 0
    return _load_ce()


def _reset_load_state() -> None:
    """Test hook: forget loaded/failed/disabled state for a fresh attempt."""
    global _CE, _CE_TRIED, _CE_DEGRADE_REASON, _CE_LAST_ATTEMPT_MONO, _CE_ATTEMPTS
    _CE = None
    _CE_TRIED = False
    _CE_DEGRADE_REASON = None
    _CE_LAST_ATTEMPT_MONO = None
    _CE_ATTEMPTS = 0


def available() -> bool:
    return _load_ce() is not None


def degrade_reason() -> str | None:
    """None when the cross-encoder is active; else ``disabled_by_env`` (quiet)
    or ``load_failed: …`` (alarm)."""
    _load_ce()
    return _CE_DEGRADE_REASON


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def cross_scores(capability: str, texts: list[str]) -> list[float] | None:
    """Cross-encoder relevance of ``capability`` to each text, in [0, 1].

    Returns None when the tier is unavailable so callers fall back to the
    bi-encoder. Never raises.
    """
    global _CE_SPENT, _CE_EXHAUSTED
    if not capability or not texts or _CE_EXHAUSTED:
        return None
    # Start the clock BEFORE the (possibly 10-40s) cold model load so the load
    # counts against the budget — otherwise the first call is unbudgeted.
    t0 = time.monotonic()
    ce = _load_ce()
    if ce is None:
        return None
    try:
        raw: list = []
        pairs = [(capability, t or "") for t in texts]
        # chunk + re-check the budget between chunks so a single large claim
        # can't overshoot DERIVE_STEP_TIMEOUT_SEC before the guard trips.
        for i in range(0, len(pairs), max(1, _CE_CHUNK)):
            raw.extend(ce.predict(pairs[i:i + max(1, _CE_CHUNK)]))
            _CE_SPENT = _CE_SPENT + (time.monotonic() - t0)
            t0 = time.monotonic()
            if _CE_SPENT >= _CE_BUDGET_SEC:
                _CE_EXHAUSTED = True
                break
        if _CE_EXHAUSTED and len(raw) < len(pairs):
            # budget tripped mid-claim → degrade the whole call to bi-encoder
            print(f"[nlp.rerank] cross-encoder budget {_CE_BUDGET_SEC:.0f}s spent — "
                  f"remaining alignment degrades to the bi-encoder (deploy safeguard)",
                  flush=True)
            return None
    except Exception:
        return None
    if _CE_EXHAUSTED:
        print(f"[nlp.rerank] cross-encoder budget {_CE_BUDGET_SEC:.0f}s spent — "
              f"remaining alignment degrades to the bi-encoder (deploy safeguard)",
              flush=True)
    # stsb cross-encoders emit a normalized [0,1] similarity; clamp defensively
    # (some checkpoints emit the 0-5 STS scale — rescale those).
    out: list[float] = []
    for v in raw:
        f = float(v)
        if f > 1.0:  # 0-5 STS scale → 0-1
            f = f / 5.0
        out.append(_clamp01(f))
    return out


def fuse(cross: float, bi_cos: float) -> float:
    """Calibrated support in [0,1] from the cross-encoder relevance + the
    bi-encoder cosine.

    Design: the cross-encoder is the primary (precision) signal, boosted so a
    modest-but-real paraphrase score lifts while decoys stay near zero
    (``cross ** 0.7``); the bi-encoder cosine, rescaled off its ~0.15 noise
    floor, is the corroborating semantic signal. Both strong → saturates toward
    ~0.95; decoy (both low) → ~0.
    """
    sem = _clamp01((bi_cos - 0.15) / 0.55)
    ce_boost = _clamp01(cross) ** 0.7
    return _clamp01(0.55 * ce_boost + 0.45 * sem)


def _fused_batch(capability: str, items: list[tuple[str, float]]) -> list[float]:
    """``[(evidence_text, bi_cos)]`` → ``[fused support]``, in one pass.

    Speed safeguards (accuracy-preserving): (1) BAND-LIMIT — the cross-encoder
    is only run on the AMBIGUOUS cosine band ``[_CE_BAND_LO, _CE_BAND_HI]`` where
    word-overlap decoys live; a very high cosine is taken as supported and a very
    low one as unrelated without a call. (2) BATCH — every ambiguous pair for
    this claim goes through ONE ``predict``. (3) BUDGET — if the per-process
    cross-encoder budget is already spent, ``cross_scores`` returns None and the
    band pairs degrade to their raw bi-encoder cosine (never a wrong ~0). Assumes
    the tier is available; callers needing the zero-regression path check first.
    """
    band = [i for i, (_t, bc) in enumerate(items) if _CE_BAND_LO <= bc <= _CE_BAND_HI]
    cs = cross_scores(capability, [items[i][0] for i in band]) if band else []
    have = cs is not None and len(cs) == len(band)
    cmap = {band[j]: cs[j] for j in range(len(band))} if have else {}
    bandset = set(band)
    out: list[float] = []
    for i, (_t, bc) in enumerate(items):
        if i in cmap:
            out.append(fuse(cmap[i], bc))          # cross-encoder verified
        elif i in bandset:
            out.append(_clamp01(bc))               # budget spent → raw bi-encoder
        elif bc > _CE_BAND_HI:
            out.append(fuse(0.9, bc))              # clearly supported (skip CE)
        else:
            out.append(fuse(0.0, bc))              # below band → ~0 (skip CE)
    return out


def rerank(
    capability: str, candidates: list[tuple[Any, str, float]],
) -> list[tuple[Any, float]] | None:
    """Re-rank ``(id, text, bi_cos)`` candidates by fused support, desc.

    Returns None only when the cross-encoder tier is UNAVAILABLE (caller keeps
    the bi-encoder order). Band-limited + batched + budget-aware. Never raises.
    """
    if not candidates:
        return []
    if not available():
        return None
    vals = _fused_batch(capability, [(t, bc) for _cid, t, bc in candidates])
    fused = [(candidates[i][0], vals[i]) for i in range(len(candidates))]
    fused.sort(key=lambda x: x[1], reverse=True)
    return fused


def support_scores(capability: str, items: list[tuple[str, float]]) -> list[float]:
    """Batched calibrated support for many ``(evidence_text, bi_cos)`` under ONE
    claim. Returns the RAW bi-encoder cosines when the tier is unavailable
    (zero-regression). This is the batched twin of ``support_score`` — call it
    once per claim instead of once per citation to keep the derive path fast."""
    if not items:
        return []
    if not available():
        return [bc for _t, bc in items]
    return _fused_batch(capability, items)


def support_score(capability: str, evidence_text: str, bi_cos: float) -> float:
    """Single-pair calibrated support in [0,1].

    When the cross-encoder tier is unavailable this returns the RAW bi-encoder
    cosine unchanged — so callers gating on it behave EXACTLY as before the
    re-rank tier existed (zero regression on a cold regen or a lexical-forced
    test). Only when the cross-encoder is baked does the calibrated fusion
    apply."""
    if not available():
        return bi_cos
    return _fused_batch(capability, [(evidence_text, bi_cos)])[0]
