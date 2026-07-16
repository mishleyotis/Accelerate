"""Cache-wrapped narrative polish for the rendered API surface.

Per the integrated batched plan Batch 6 spec: this is the
endpoint-facing wrapper around ``language_rewrite.rewrite_text`` that
caches the rewritten text via ``vertex_synthesis_cache`` so the
deterministic rewrite is a one-time cost per (target, source_hash)
pair.

Decision flow:

  polish_narrative(text, target_kind, target_id, surface)
   -> if text is empty / very short -> return as-is (no cache work)
   -> compute source_text_hash
   -> lookup vertex_synthesis_cache by
        (target_kind, target_id, surface='language_rewrite',
         input_fingerprint=source_text_hash)
   -> if cache hit + not invalidated -> return cached.output_text
   -> else rewrite_text(text) -> if state in {'applied'}:
        insert_or_supersede into cache + return rewritten
      -> if state in {'no_change_needed', 'validator_rejected',
                      'empty_input'}: return ORIGINAL text (safe
        fallback); cache the no-op so the next read skips the
        rewrite as well.

The wrapper is BEST-EFFORT: any cache / DB error falls back to the
original text. The endpoint NEVER serves broken content.

Design constraints addressed:

  - **Performance**: rewrite is O(N) regex passes (~1ms / KB);
    cache hit is a single SELECT (~1ms). On a large heatmap with
    1085 subcap cells, the first-render cost is ~1s; subsequent
    renders are cache hits.
  - **Safety**: anchor-preservation validator inside rewrite_text
    rejects any rewrite that drops an E-ID / subcap-ID / monetary
    value; the wrapper serves source in that case.
  - **Invalidation**: when the source text changes
    (subcap_scores.rationale UPSERT), the source_text_hash changes
    -> cache automatically misses -> fresh rewrite -> the cache
    UPSERT supersedes the old entry. No manual invalidation
    needed.
  - **Resilience**: the cache backing (synthesis_cache_db) uses
    `safe_*` wrappers that swallow any DB error + log it. The
    endpoint serves source if the cache layer fails.
"""
from __future__ import annotations

import structlog

from app.services.language_rewrite import RewriteResult, rewrite_text
from app.services.synthesis_cache_db import (
    safe_fetch_active,
    safe_insert_or_supersede,
)

_log = structlog.get_logger(__name__)

# Minimum text length to even attempt a rewrite. Below this, the
# overhead of the cache lookup exceeds the gain. 8, not 20: short
# issue TITLES ('No SIEM/SOC') are exactly the deficit-lead class the
# rewrite exists for, and the lookup is ~1ms.
_MIN_REWRITE_LENGTH = 8

# The synthesis_cache surface name reserved for the rewrite layer.
# Distinct from rag_answer / subcap_narrative / meeting_prep / etc.
SURFACE = "language_rewrite"

# vertex_synthesis_cache.target_id is VARCHAR(64); longer composed ids
# (e.g. "{run_id}:{finding title}:{field}") must be clipped BEFORE both
# the fetch and the write or every cache insert fails with
# StringDataRightTruncation and the surface is re-rewritten on each read.
_MAX_TARGET_ID = 64


def _clip_target_id(target_id: str) -> str:
    if len(target_id) <= _MAX_TARGET_ID:
        return target_id
    from hashlib import sha256
    digest = sha256(target_id.encode("utf-8")).hexdigest()[:19]
    return f"{target_id[:_MAX_TARGET_ID - 20]}~{digest}"


def polish_narrative(
    text: str | None,
    *,
    target_kind: str,
    target_id: str,
    catalogue_version: str = "n/a",
    use_cache: bool = True,
) -> str:
    """Return the polished version of ``text`` (or text unchanged when
    rewrite is a no-op / validator-rejected).

    Inputs:
      text              -- the source narrative to polish. May be
                           None / empty / very short -- handled
                           gracefully.
      target_kind       -- 'subcap' | 'entity' | 'recommendation' |
                           'section' (matches synthesis_cache schema)
      target_id         -- e.g. 'P1C1.1.1' for a subcap-rationale
                           polish; entity_id for an entity-level
                           SCQA polish.
      catalogue_version -- the catalogue version pinned for this
                           render (so a catalogue bump invalidates
                           the polish via the standard cache
                           invalidation contract).
      use_cache         -- pass False to bypass the cache (test mode).

    Always returns a STRING. NEVER raises. On any internal error
    (rewrite crash, cache crash) the wrapper logs + serves the
    source text.
    """
    if text is None or not isinstance(text, str):
        return text or ""
    if len(text) < _MIN_REWRITE_LENGTH:
        return text
    target_id = _clip_target_id(target_id)

    try:
        if use_cache:
            row = safe_fetch_active(
                target_kind=target_kind,
                target_id=target_id,
                surface=SURFACE,
                fingerprint=_source_fingerprint(text),
            )
            if row is not None and row.output_text:
                return row.output_text

        result = rewrite_text(text)
        # Decide what to serve + what to cache.
        served = (
            result.rewritten_text
            if result.state == "applied"
            else text
        )
        if use_cache:
            _safe_cache_write(
                result=result,
                served=served,
                target_kind=target_kind,
                target_id=target_id,
                catalogue_version=catalogue_version,
                fingerprint=_source_fingerprint(text),
            )
        return served
    except Exception as e:
        # Defense in depth: any unexpected failure -> serve source.
        _log.warning(
            "narrative_polish.failed",
            target_kind=target_kind,
            target_id=target_id,
            err=str(e),
        )
        return text


def polish_many(
    texts: dict[str, str | None],
    *,
    target_kind: str,
    catalogue_version: str = "n/a",
    use_cache: bool = True,
) -> dict[str, str]:
    """Polish a batch of texts keyed by target_id.

    Same semantics as ``polish_narrative`` per entry. Returns dict
    with same keys; values are polished or original text.
    """
    out: dict[str, str] = {}
    for tid, text in texts.items():
        out[tid] = polish_narrative(
            text, target_kind=target_kind, target_id=tid,
            catalogue_version=catalogue_version, use_cache=use_cache,
        )
    return out


def _source_fingerprint(text: str) -> str:
    """The cache key derives from the source text AND the ruleset version.

    A change to the source (e.g. subcap_scores.rationale UPSERT in
    Batch 2's selective re-ingest path) changes the hash -> cache
    miss -> fresh rewrite. The ruleset version is folded in for the
    same reason: a rule release must reach text whose OLD rewrite is
    already cached (without it, S2_accusatory sat frozen across a rule
    release — every insight body served from stale rewrite rows).
    Catalogue-bump invalidation runs through the existing
    build_invalidation_for_catalogue_bump SPEC + the
    `catalogue_version` index on vertex_synthesis_cache.
    """
    from hashlib import sha256

    from app.services.language_rewrite import RULESET_VERSION
    return sha256(f"{RULESET_VERSION}\n{text}".encode()).hexdigest()


def _safe_cache_write(
    *,
    result: RewriteResult,
    served: str,
    target_kind: str,
    target_id: str,
    catalogue_version: str,
    fingerprint: str,
) -> None:
    """Cache the polished text. Best-effort; failure is logged + swallowed.

    We cache BOTH the 'applied' rewrites AND the no-ops (state in
    {'no_change_needed', 'validator_rejected'}) so subsequent reads
    of identical source skip the rewrite + the validator entirely.
    The cache row stores the served text (which IS the source for
    no-ops), so a cache hit is a single SELECT + serve.
    """
    try:
        safe_insert_or_supersede(
            target_kind=target_kind,
            target_id=target_id,
            surface=SURFACE,
            model="deterministic-regex-v1",
            # the SAME versioned fingerprint the fetch uses — result.
            # source_hash is text-only and would never be read back
            input_fingerprint=fingerprint,
            prompt_template_version="rewrite-v1",
            grounding_bundle_hash="",
            catalogue_version=catalogue_version,
            output_text=served,
            output_json=None,
            cited_evidence_ids=None,
            cited_subcap_ids=None,
            validators_passed=result.validation_passed,
            confidence=None,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            decision_gate=("cache_miss_synthesized"
                           if result.state == "applied"
                           else "parsed_skipped_llm"),
        )
    except Exception as e:
        _log.warning(
            "narrative_polish.cache_write_failed",
            target_kind=target_kind, target_id=target_id, err=str(e),
        )
