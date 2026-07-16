"""Unified synthesis persistence + decision-gate orchestrator.

Replaces the four disparate caches (`gemini_cache`, `ai_enrichments`,
`customer_intelligence_profiles.intelligence_summary_md`, in-memory
dicts on extractor modules) behind a single hard contract:

    Once Vertex interprets information, the output is persisted;
    subsequent reads consume zero tokens until the input
    fingerprint changes.

The fingerprint is a deterministic SHA256 of:
    prompt_template_version
    + grounding_bundle_hash
    + catalogue_version
    + page_context_hash

so any change to the prompt template, the retrieved evidence
bundle, the catalogue, or the request context invalidates the
cache key automatically. No explicit "expire" call is needed for
those cases — the new input simply has a new fingerprint and
misses the cache.

State transitions for `decision_gate`
--------------------------------------
parsed_skipped_llm
    Surface is fully derivable from parsed CSV/DOCX/run_manifest
    data (e.g., raw scores, recommendation titles, leadership
    names). No Vertex call. No row inserted. Token cost = 0.

cache_hit_fresh
    Active `vertex_synthesis_cache` row exists with matching
    fingerprint, `invalidated_at IS NULL`, and `expires_at` either
    NULL or in the future. Returns cached `output_text`. Token
    cost = 0.

cache_hit_invalidated
    Cache row exists but has been invalidated (e.g., by a
    `rerun_invalidate_all` event) OR has expired. Re-synthesize;
    insert a new row; mark the prior row's `superseded_by` to the
    new row's id. Token cost = full.

cache_miss_synthesized
    No row matching fingerprint. Synthesize + insert. Token cost =
    full. (Most common on first-load.)

user_regenerate
    Explicit `force_regenerate=True` (user clicked "Regenerate" on
    a card). Re-synthesize; supersede the prior row. Token cost =
    full.

feedback_invalidated
    A `chat_feedback` row with `rating=-1` AND
    `unhelpful_reason='hallucinated'` invalidates only the
    specific cache row tied to that message. Next equivalent read
    will see `cache_hit_invalidated`. Token cost = full on next
    read.

rerun_invalidate_all_surfaces
    A new run for an entity invalidates the entity's prior cache
    rows lazily — invalidated_at is set on the rows at ingest
    time; the next read sees them as cache_hit_invalidated.

catalogue_bump_invalidate
    A new catalogue version invalidates rows keyed under the prior
    version. With the alias bridge, only subcap-keyed entries need
    re-synthesis; entity-level summaries are unaffected unless
    `catalogue_version` was part of the fingerprint inputs.
"""
from __future__ import annotations

import dataclasses as dc
import enum
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any


class DecisionGate(enum.StrEnum):
    """The 8 decision-gate states. Strings are the values that land
    in `vertex_synthesis_cache.decision_gate` for audit replay."""

    PARSED_NO_LLM = "parsed_skipped_llm"
    CACHE_HIT_FRESH = "cache_hit"
    CACHE_HIT_INVALIDATED = "invalidated_re_synthesized"
    CACHE_MISS = "cache_miss_synthesized"
    USER_REGENERATE = "user_regenerate"
    FEEDBACK_INVALIDATED = "feedback_invalidated"
    RERUN_INVALIDATE_ALL = "rerun_invalidate_all"
    CATALOGUE_BUMP_INVALIDATE = "catalogue_bump_invalidate"


# Surface → default TTL (seconds). Sourced from plan §⑫. The
# orchestrator reads the active value from `system_config` at
# call-time; this dict is the bootstrap default for in-memory
# tests + the seed values in migration 019.
DEFAULT_TTL_SEC: dict[str, int] = {
    "rag_answer": 900,                      # 15 min — most user-driven
    "subcap_narrative": 604_800,            # 7 days
    "platform_story": 259_200,              # 3 days
    "insight_explanation": 259_200,         # 3 days
    "meeting_prep": 86_400,                 # 1 day
    "why_now": 86_400,                      # 1 day
    "intelligence_summary": 604_800,        # 7 days
    "recommendation_explainer": 259_200,    # 3 days
    "enrichment": 0,                        # persisted forever (only catalogue bump invalidates)
    # Gemini gap-fill extractions land in domain tables (firmographics.
    # parsed_facts / thought_leadership) AND here; both are enrichments
    # under the "persisted forever" contract (2026-07-02 — the cache row
    # is the provenance record for the deploy-time assertions in
    # qa_gemini_surfaces, so it must not silently expire after a day).
    "firmographics_extraction": 0,
    "thought_leadership_extraction": 0,
    # Batch 6 (2026-06-07): deterministic-regex rewrite of bot-emitted
    # narrative into Zennify product voice. Source-content-hash keyed,
    # so a source UPSERT (subcap_scores.rationale change) auto-misses
    # the cache. 7-day TTL is conservative -- the rewrite is pure-
    # function so re-running is cheap when needed.
    "language_rewrite": 604_800,            # 7 days
}

# Surfaces that are PARSED, never synthesized. The orchestrator
# returns DecisionGate.PARSED_NO_LLM and never touches the cache.
PARSED_ONLY_SURFACES: frozenset[str] = frozenset({
    "leadership_panel",
    "tech_stack_list",
    "score_ring",
    "evidence_drawer_raw",
    "recommendation_metadata",
    "run_manifest_facts",
})


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

def _canonical_json(obj: Any) -> str:
    """Deterministic JSON encode (sorted keys, fixed separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def hash_grounding_bundle(bundle: list[dict[str, Any]]) -> str:
    """SHA256 over the deterministic JSON of the bundle.

    The bundle is the list of grounding items (evidence + section +
    insight). Order matters in the cache key — caller MUST sort by
    a stable field (e.g. `id`) before calling. We do not re-sort
    here because the bundle's order is semantically meaningful
    (top-k ranking) and re-sorting would hide reranking changes
    from the fingerprint."""
    return hashlib.sha256(_canonical_json(bundle).encode()).hexdigest()


def hash_page_context(page_context: dict[str, Any]) -> str:
    """SHA256 over the page-context dict. Used to differentiate
    per-route cache rows for the same target."""
    # Strip volatile fields that should not affect the cache key
    # (e.g., user_id is not part of the fingerprint — different
    # users with the same context should share the cache).
    stripped = {k: v for k, v in page_context.items()
                if k not in ("user_id", "session_id", "request_ts")}
    return hashlib.sha256(_canonical_json(stripped).encode()).hexdigest()


def compute_fingerprint(
    *,
    prompt_template_version: str,
    grounding_bundle_hash: str,
    catalogue_version: str,
    page_context_hash: str,
) -> str:
    """SHA256 of the four inputs concatenated. Stable across
    process restarts; identical inputs → identical fingerprint."""
    raw = (
        f"{prompt_template_version}|{grounding_bundle_hash}|"
        f"{catalogue_version}|{page_context_hash}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Result + Decision dataclasses
# ---------------------------------------------------------------------------

@dc.dataclass(frozen=True)
class CacheRow:
    """In-memory representation of a `vertex_synthesis_cache` row."""

    id: str
    target_kind: str
    target_id: str
    surface: str
    model: str
    input_fingerprint: str
    prompt_template_version: str
    grounding_bundle_hash: str
    catalogue_version: str
    output_text: str
    output_json: dict[str, Any] | None
    cited_evidence_ids: list[str] | None
    cited_subcap_ids: list[str] | None
    validators_passed: bool
    confidence: float | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    created_at: datetime
    last_accessed_at: datetime
    access_count: int
    expires_at: datetime | None
    invalidated_at: datetime | None
    invalidation_reason: str | None
    superseded_by: str | None
    decision_gate: str


@dc.dataclass(frozen=True)
class SynthesisRequest:
    """Caller-supplied inputs to `decide_synthesis_path`."""

    target_kind: str
    target_id: str
    surface: str
    prompt_template_version: str
    grounding_bundle: list[dict[str, Any]]
    catalogue_version: str
    page_context: dict[str, Any]
    force_regenerate: bool = False


@dc.dataclass(frozen=True)
class SynthesisDecision:
    """The decision the orchestrator made for a SynthesisRequest.

    `existing_row` is non-None only when the decision involves an
    existing cache row (CACHE_HIT_*, USER_REGENERATE, etc.) and
    None for cache misses + parsed-only surfaces."""

    gate: DecisionGate
    fingerprint: str
    existing_row: CacheRow | None
    reason: str


# ---------------------------------------------------------------------------
# Pure decision-gate logic
# ---------------------------------------------------------------------------

def decide_synthesis_path(
    req: SynthesisRequest,
    *,
    lookup_existing: Callable[[str, str, str, str], CacheRow | None],
    now: datetime | None = None,
) -> SynthesisDecision:
    """Pure decision engine — given a request + a row-lookup function,
    return which gate applies. Does NOT mutate anything.

    The caller is responsible for executing the decision (calling
    Vertex, writing the new row, marking the prior row as superseded).
    This function is pure for testability."""
    if now is None:
        now = datetime.now(UTC)

    # Gate 1: parsed-only surfaces never touch the cache.
    if req.surface in PARSED_ONLY_SURFACES:
        return SynthesisDecision(
            gate=DecisionGate.PARSED_NO_LLM,
            fingerprint="",
            existing_row=None,
            reason=f"surface '{req.surface}' is parsed-only",
        )

    fingerprint = compute_fingerprint(
        prompt_template_version=req.prompt_template_version,
        grounding_bundle_hash=hash_grounding_bundle(req.grounding_bundle),
        catalogue_version=req.catalogue_version,
        page_context_hash=hash_page_context(req.page_context),
    )

    # Gate 2: explicit user regenerate forces synthesis regardless of cache.
    if req.force_regenerate:
        existing = lookup_existing(
            req.target_kind, req.target_id, req.surface, fingerprint,
        )
        return SynthesisDecision(
            gate=DecisionGate.USER_REGENERATE,
            fingerprint=fingerprint,
            existing_row=existing,
            reason="force_regenerate=True",
        )

    existing = lookup_existing(
        req.target_kind, req.target_id, req.surface, fingerprint,
    )

    # Gate 3: cache miss — no row exists for this fingerprint.
    if existing is None:
        return SynthesisDecision(
            gate=DecisionGate.CACHE_MISS,
            fingerprint=fingerprint,
            existing_row=None,
            reason="no row with matching fingerprint",
        )

    # Gate 4: row was explicitly invalidated.
    if existing.invalidated_at is not None:
        return SynthesisDecision(
            gate=DecisionGate.CACHE_HIT_INVALIDATED,
            fingerprint=fingerprint,
            existing_row=existing,
            reason=f"invalidated at {existing.invalidated_at.isoformat()} "
                   f"({existing.invalidation_reason or 'unspecified'})",
        )

    # Gate 5: row has expired.
    if existing.expires_at is not None and existing.expires_at < now:
        return SynthesisDecision(
            gate=DecisionGate.CACHE_HIT_INVALIDATED,
            fingerprint=fingerprint,
            existing_row=existing,
            reason=f"expired at {existing.expires_at.isoformat()}",
        )

    # Gate 6: fresh cache hit.
    return SynthesisDecision(
        gate=DecisionGate.CACHE_HIT_FRESH,
        fingerprint=fingerprint,
        existing_row=existing,
        reason="active cache row, not expired, not invalidated",
    )


# ---------------------------------------------------------------------------
# Token accounting helpers
# ---------------------------------------------------------------------------

# Per 1K-token USD rates (Gemini 2.5 family, as of Q2 2026). Used by
# /admin/vertex-budget to compute `spent_usd` from cached `prompt_tokens`
# + `completion_tokens` totals. Keep older 2.0 + alias rows so projects
# with mixed model access still get accurate pricing for historical
# cache rows.
MODEL_RATES_USD_PER_1K = {
    # 2.5 family — current canonical surfaces
    "gemini-2.5-pro": {"prompt": 0.00125, "completion": 0.005},
    "gemini-2.5-flash": {"prompt": 0.000075, "completion": 0.0003},
    # 2.0 family — kept for projects that pinned the older flash
    "gemini-2.0-flash": {"prompt": 0.000075, "completion": 0.0003},
    "gemini-2.0-flash-001": {"prompt": 0.000075, "completion": 0.0003},
    # Generic aliases the legacy code paths sometimes set
    "gemini-flash": {"prompt": 0.000075, "completion": 0.0003},
    "gemini-pro": {"prompt": 0.00125, "completion": 0.005},
    "text-embedding-004": {"prompt": 0.00001, "completion": 0.0},
    "text-embedding-005": {"prompt": 0.00001, "completion": 0.0},
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from token counts. Returns 0.0 for unknown
    models so unknown surfaces never crash the budget panel."""
    rates = MODEL_RATES_USD_PER_1K.get(model)
    if not rates:
        return 0.0
    return (
        (prompt_tokens / 1000.0) * rates["prompt"]
        + (completion_tokens / 1000.0) * rates["completion"]
    )


def ttl_for_surface(surface: str, ttl_overrides: dict[str, int] | None = None) -> int:
    """Return TTL seconds for a surface. Caller passes
    `ttl_overrides` from `system_config` reads; falls back to
    DEFAULT_TTL_SEC. Returns 0 to mean "persist forever" (only the
    catalogue/rerun invalidation paths will displace the row)."""
    if ttl_overrides and surface in ttl_overrides:
        return ttl_overrides[surface]
    return DEFAULT_TTL_SEC.get(surface, 86_400)


def compute_expires_at(
    surface: str,
    *,
    now: datetime | None = None,
    ttl_overrides: dict[str, int] | None = None,
) -> datetime | None:
    """Returns expires_at timestamp for a new cache row. None when
    TTL is 0 (persist forever; only invalidation events can
    displace)."""
    if now is None:
        now = datetime.now(UTC)
    ttl_sec = ttl_for_surface(surface, ttl_overrides)
    if ttl_sec == 0:
        return None
    return now + timedelta(seconds=ttl_sec)


# ---------------------------------------------------------------------------
# Invalidation helpers (pure-logic; caller writes the SQL)
# ---------------------------------------------------------------------------

@dc.dataclass(frozen=True)
class InvalidationSpec:
    """Describes a set of rows to invalidate. Caller turns this
    into a SQL UPDATE on `vertex_synthesis_cache`."""

    reason: str
    target_kind: str | None = None        # None = all kinds
    target_ids: tuple[str, ...] | None = None
    target_id_prefix: str | None = None   # LIKE 'prefix%' (entity-scoped subcaps)
    surfaces: tuple[str, ...] | None = None
    catalogue_version: str | None = None
    cache_row_id: str | None = None       # for single-row invalidation


def build_invalidation_for_new_run(
    entity_id: str,
    affected_subcap_ids: list[str] | None = None,
    entity_display_id: str | None = None,
) -> list[InvalidationSpec]:
    """A new run for an entity invalidates:
      • entity-level rows (intelligence_summary, why_now, meeting_prep)
      • ALL of the entity's subcap-level rows — a rerun re-scores every
        capability, so every per-subcap narrative/rationale/enrichment must
        re-synthesize.

    Subcap cache rows are keyed ENTITY-QUALIFIED (``{display_id}:{subcap_id}:
    …`` — see routers/heatmap.py), so the correct match is a ``display_id:``
    PREFIX, not a bare-subcap-id set (2026-07-14 audit: the prior
    ``affected_subcap_ids`` path passed bare ids that matched nothing and, at
    the ingest layer, was always None — subcap rows never invalidated on
    rerun). Pass ``entity_display_id`` to emit the prefix spec; the legacy
    bare-id spec is still emitted when ``affected_subcap_ids`` is given (used
    by the catalogue-bump path with globally-keyed ids).

    Returns a list of InvalidationSpec for the caller to execute."""
    specs: list[InvalidationSpec] = [
        InvalidationSpec(
            reason="rerun_invalidate_all_surfaces",
            target_kind="entity",
            target_ids=(entity_id,),
        ),
    ]
    if entity_display_id:
        specs.append(InvalidationSpec(
            reason="rerun_invalidate_all_surfaces",
            target_kind="subcap",
            target_id_prefix=f"{entity_display_id}:",
        ))
    if affected_subcap_ids:
        specs.append(InvalidationSpec(
            reason="rerun_invalidate_all_surfaces",
            target_kind="subcap",
            target_ids=tuple(affected_subcap_ids),
        ))
    return specs


def build_invalidation_for_catalogue_bump(
    old_version: str,
    renamed_subcap_ids: list[str] | None = None,
) -> list[InvalidationSpec]:
    """A new catalogue version invalidates:
      • all subcap-keyed rows under the old version (they'll be
        re-keyed to the new IDs via the alias bridge on next read).
      • entity-level rows ONLY when catalogue_version was part of
        the fingerprint (which it always is — see compute_fingerprint).

    With the alias bridge, the next read will already produce a
    new fingerprint, so this invalidation is technically belt-and-
    suspenders. We do it anyway to make the audit trail explicit."""
    specs: list[InvalidationSpec] = []
    if renamed_subcap_ids:
        specs.append(InvalidationSpec(
            reason="catalogue_bump_invalidate",
            target_kind="subcap",
            target_ids=tuple(renamed_subcap_ids),
            catalogue_version=old_version,
        ))
    # All rows tagged with the old version (cheap to scope by index).
    specs.append(InvalidationSpec(
        reason="catalogue_bump_invalidate",
        catalogue_version=old_version,
    ))
    return specs


def build_invalidation_for_feedback(cache_row_id: str) -> InvalidationSpec:
    """A 👎 with `unhelpful_reason='hallucinated'` invalidates only
    the specific row tied to that response. Sibling rows untouched."""
    return InvalidationSpec(
        reason="feedback_invalidated",
        cache_row_id=cache_row_id,
    )


# ---------------------------------------------------------------------------
# Public summary dataclasses (used by /admin/vertex-budget callers)
# ---------------------------------------------------------------------------

@dc.dataclass(frozen=True)
class BudgetRollup:
    """Aggregated cache+token statistics over a time window. Caller
    populates by querying `vertex_synthesis_cache` group-by surface
    + model + day."""

    period: str                           # e.g. '2026-05'
    spent_usd: float
    budget_usd: float
    cache_hit_rate: float                 # 0..1
    tokens_saved_by_cache: int
    by_surface: list[dict[str, Any]]
    by_user: list[dict[str, Any]]
    by_entity: list[dict[str, Any]]
    daily_trend: list[dict[str, Any]]


def compute_cache_hit_rate(total_calls: int, cache_misses: int) -> float:
    """Returns hit rate in [0, 1]. Zero calls → 0.0 (so the chart
    doesn't NaN)."""
    if total_calls <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (cache_misses / total_calls)))


def estimate_tokens_saved(
    *,
    cache_hits: int,
    avg_prompt_tokens_per_call: float,
    avg_completion_tokens_per_call: float,
) -> int:
    """Estimate tokens saved BY the cache (i.e. tokens that would
    have been spent if every read was a miss). Multiplies hit
    count by average per-call cost."""
    return int(
        cache_hits
        * (avg_prompt_tokens_per_call + avg_completion_tokens_per_call)
    )
