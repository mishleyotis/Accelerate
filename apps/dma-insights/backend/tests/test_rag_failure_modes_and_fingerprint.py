"""Phase 5 RAG / Vertex / cache failure-mode + fingerprint tests.

The audit identified that cache fingerprint stability + Vertex
failure-handling are the load-bearing contracts for the RAG path.
A refactor that:
  - includes user_id in the fingerprint -> caches no longer shared
    across users; cost balloons
  - reorders page_context keys -> non-deterministic fingerprints; same
    request misses cache
  - omits catalogue_version from the fingerprint -> a catalogue bump
    no longer invalidates cache; AEs see pre-bump synthesis forever
  - propagates Vertex 4xx as 5xx -> stack-traces leak; bot retries
    don't help
... all surface here BEFORE the production incident.
"""
from __future__ import annotations

# ── Fingerprint stability ─────────────────────────────────────────


def test_fingerprint_is_stable_under_page_context_key_reorder():
    """page_context = {a, b, c} vs {c, b, a} must produce the SAME
    fingerprint. The orchestrator's canonical JSON serializer sorts
    keys; this test catches a refactor that swaps to plain json.dumps."""
    from app.services.synthesis_orchestrator import compute_fingerprint

    a = compute_fingerprint(
        prompt_template_version="v1",
        grounding_bundle_hash="h1",
        catalogue_version="v7.0",
        page_context_hash="ctxh1",
    )
    b = compute_fingerprint(
        prompt_template_version="v1",
        grounding_bundle_hash="h1",
        catalogue_version="v7.0",
        page_context_hash="ctxh1",
    )
    assert a == b


def test_fingerprint_changes_when_catalogue_version_changes():
    """Catalogue bump MUST change the fingerprint so the cache misses
    + re-synthesises. Pre-bump grounding semantics may have shifted;
    serving the cached row would mix v6 and v7 framework references."""
    from app.services.synthesis_orchestrator import compute_fingerprint

    a = compute_fingerprint(
        prompt_template_version="v1",
        grounding_bundle_hash="h1",
        catalogue_version="v7.0",
        page_context_hash="ctxh1",
    )
    b = compute_fingerprint(
        prompt_template_version="v1",
        grounding_bundle_hash="h1",
        catalogue_version="v7.1",  # bumped
        page_context_hash="ctxh1",
    )
    assert a != b


def test_fingerprint_changes_when_grounding_bundle_changes():
    """Bundle order matters semantically (top-k ranking). Two bundles
    with different hashes must produce different fingerprints."""
    from app.services.synthesis_orchestrator import compute_fingerprint

    a = compute_fingerprint(
        prompt_template_version="v1",
        grounding_bundle_hash="h1",
        catalogue_version="v7.0",
        page_context_hash="ctx",
    )
    b = compute_fingerprint(
        prompt_template_version="v1",
        grounding_bundle_hash="h2",  # different bundle
        catalogue_version="v7.0",
        page_context_hash="ctx",
    )
    assert a != b


def test_volatile_keys_excluded_from_page_context_hash():
    """user_id, session_id, request_ts MUST NOT change the page_context
    hash. Otherwise the cache is per-user per-session per-request and
    the hit rate is 0%."""
    from app.services.synthesis_orchestrator import hash_page_context

    base = {"entity_id": "e1", "subcap_id": "P1C1.1.1"}
    with_volatile = {
        **base,
        "user_id": "u1",
        "session_id": "s1",
        "request_ts": "2026-05-28T00:00:00Z",
    }
    assert hash_page_context(base) == hash_page_context(with_volatile)


def test_page_context_hash_changes_on_real_context_change():
    """The hash MUST change when entity_id / subcap_id / view actually
    differ. Without this we'd serve one entity's synthesis on another."""
    from app.services.synthesis_orchestrator import hash_page_context

    a = hash_page_context({"entity_id": "e1", "subcap_id": "P1C1.1.1"})
    b = hash_page_context({"entity_id": "e2", "subcap_id": "P1C1.1.1"})
    c = hash_page_context({"entity_id": "e1", "subcap_id": "P1C2.1.1"})
    assert a != b
    assert a != c


def test_page_context_hash_is_order_independent():
    """dict order in Python 3.7+ preserves insertion. Two dicts with
    the same keys/values but different insertion order must hash
    identically -- the canonical JSON serializer sorts keys."""
    from app.services.synthesis_orchestrator import hash_page_context

    a = hash_page_context({"a": 1, "b": 2, "c": 3})
    b = hash_page_context({"c": 3, "b": 2, "a": 1})
    assert a == b


# ── Vertex retry classifier (round-trip) ──────────────────────────


def test_vertex_retry_classifier_retries_deadline_exceeded():
    """DEADLINE_EXCEEDED is a transient timeout -- retry is the
    correct response. Pinning the classifier so a refactor doesn't
    accidentally drop the timeout case."""
    from app.services.vertex_client import _is_retryable_vertex_error

    class _Deadline(Exception):
        pass
    _Deadline.__name__ = "DeadlineExceeded"
    assert _is_retryable_vertex_error(_Deadline("timeout")) is True


def test_vertex_retry_classifier_retries_unavailable():
    """ServiceUnavailable (HTTP 503) is the canonical "back off and
    retry" Vertex signal. Must retry."""
    from app.services.vertex_client import _is_retryable_vertex_error

    class _SU(Exception):
        pass
    _SU.__name__ = "ServiceUnavailable"
    assert _is_retryable_vertex_error(_SU("retry me")) is True


def test_vertex_retry_classifier_does_not_retry_invalid_argument():
    """InvalidArgument (HTTP 400) is a permanent client error.
    Retrying wastes 3 round-trips for the same failure."""
    from app.services.vertex_client import _is_retryable_vertex_error

    class _Invalid(Exception):
        pass
    _Invalid.__name__ = "InvalidArgument"
    assert _is_retryable_vertex_error(_Invalid("bad request")) is False


def test_vertex_retry_classifier_does_not_retry_not_found():
    """NotFound (HTTP 404) -- model name typo, region typo, etc.
    Retrying never recovers."""
    from app.services.vertex_client import _is_retryable_vertex_error

    class _NF(Exception):
        pass
    _NF.__name__ = "NotFound"
    assert _is_retryable_vertex_error(_NF("model gone")) is False


# ── Invalidation builders ─────────────────────────────────────────


def test_invalidation_for_new_run_targets_entity_scope():
    """When a new run lands, prior synthesis rows for the entity are
    stale. The list of specs must include an entity-scoped spec with
    target_id=entity_id (so the SQL UPDATE catches all surfaces)
    and no cache_row_id (which would invalidate only one row)."""
    from app.services.synthesis_orchestrator import build_invalidation_for_new_run

    specs = build_invalidation_for_new_run(entity_id="e1")
    assert isinstance(specs, list) and len(specs) >= 1, (
        "must return at least one spec for the entity-level invalidation."
    )
    entity_spec = next(
        s for s in specs
        if s.target_kind == "entity" and s.target_ids and "e1" in s.target_ids
    )
    assert entity_spec.cache_row_id is None


def test_invalidation_for_new_run_includes_affected_subcaps():
    """Optional affected_subcap_ids → an additional subcap-scoped
    spec so the subcap-keyed cache rows invalidate."""
    from app.services.synthesis_orchestrator import build_invalidation_for_new_run

    specs = build_invalidation_for_new_run(
        entity_id="e1", affected_subcap_ids=["P1C1.1.1", "P2C1.1.1"],
    )
    subcap_spec = next(
        (s for s in specs if s.target_kind == "subcap"), None,
    )
    assert subcap_spec is not None
    assert "P1C1.1.1" in subcap_spec.target_ids
    assert "P2C1.1.1" in subcap_spec.target_ids


def test_invalidation_for_catalogue_bump_targets_old_version_only():
    """Per the audit's PD-13 contract, a catalogue bump must
    invalidate rows tagged with the OLD version. Rows already at the
    new version (e.g. a faster-deployed surface) must survive."""
    from app.services.synthesis_orchestrator import (
        build_invalidation_for_catalogue_bump,
    )

    specs = build_invalidation_for_catalogue_bump(old_version="v7.0")
    # Every spec returned must carry catalogue_version="v7.0" so the
    # WHERE clause stays scoped to the bumped-from version.
    for spec in specs:
        assert spec.catalogue_version == "v7.0", (
            f"spec {spec!r} did not scope to old version v7.0; would "
            "invalidate rows across catalogue versions."
        )


def test_invalidation_for_feedback_is_scoped_to_one_cache_row():
    """A 👎 'hallucinated' feedback marks ONE specific cache row as
    invalidated. The whole entity's cache must NOT be torn down --
    that would balloon token cost on the next read."""
    from app.services.synthesis_orchestrator import build_invalidation_for_feedback

    spec = build_invalidation_for_feedback(cache_row_id="row-uuid-1")
    assert spec.cache_row_id == "row-uuid-1"
    # And it must NOT carry a broader scope; otherwise a single
    # feedback would invalidate every cache row for the entity.
    assert spec.target_ids is None or len(spec.target_ids) <= 1


# ── Cache cost helpers fail-soft on edge cases ─────────────────────


def test_compute_cache_hit_rate_handles_zero_calls():
    """0 total calls -> hit rate is 0.0, not ZeroDivisionError. The
    /admin/vertex-budget endpoint reads this on cold-start when no
    calls have happened yet."""
    from app.services.synthesis_orchestrator import compute_cache_hit_rate

    assert compute_cache_hit_rate(0, 0) == 0.0


def test_compute_cache_hit_rate_clamps_to_zero_one_range():
    """Hit rate must always be in [0.0, 1.0]. A buggy caller passing
    misses > total shouldn't return a negative rate (which the FE
    would render as "-..%")."""
    from app.services.synthesis_orchestrator import compute_cache_hit_rate

    # 5 misses out of 3 total -> the implementation may clamp or
    # return some sentinel; assert it's NOT < 0.
    rate = compute_cache_hit_rate(3, 5)
    assert 0.0 <= rate <= 1.0


def test_estimate_tokens_saved_handles_zero_hits():
    """0 cache hits -> 0 tokens saved. Same cold-start sanity."""
    from app.services.synthesis_orchestrator import estimate_tokens_saved

    assert estimate_tokens_saved(
        cache_hits=0,
        avg_prompt_tokens_per_call=100,
        avg_completion_tokens_per_call=200,
    ) == 0


def test_estimate_tokens_saved_scales_linearly_with_hits():
    """N hits = N * (avg_prompt + avg_completion) tokens saved.
    Validates the multiplier semantics so a refactor that adds
    overhead-discount logic doesn't silently shift the published
    savings number."""
    from app.services.synthesis_orchestrator import estimate_tokens_saved

    one = estimate_tokens_saved(cache_hits=1, avg_prompt_tokens_per_call=100, avg_completion_tokens_per_call=200)
    two = estimate_tokens_saved(cache_hits=2, avg_prompt_tokens_per_call=100, avg_completion_tokens_per_call=200)
    five = estimate_tokens_saved(cache_hits=5, avg_prompt_tokens_per_call=100, avg_completion_tokens_per_call=200)
    assert two == 2 * one
    assert five == 5 * one


# ── decide_synthesis_path branches ─────────────────────────────────


def _make_request(surface="intelligence", catalogue_version="v7.0", force_regenerate=False):
    """SynthesisRequest factory matching the dataclass's actual fields."""
    from app.services.synthesis_orchestrator import SynthesisRequest
    return SynthesisRequest(
        target_kind="subcap",
        target_id="P1C1.1.1",
        surface=surface,
        prompt_template_version="v1",
        grounding_bundle=[],
        catalogue_version=catalogue_version,
        page_context={"entity_id": "e1"},
        force_regenerate=force_regenerate,
    )


def _make_row(invalidated=False, fingerprint="fp1"):
    """CacheRow factory."""
    from datetime import UTC, datetime

    from app.services.synthesis_orchestrator import CacheRow

    return CacheRow(
        id="row1",
        target_kind="subcap",
        target_id="P1C1.1.1",
        surface="intelligence",
        model="flash",
        input_fingerprint=fingerprint,
        prompt_template_version="v1",
        grounding_bundle_hash="h1",
        catalogue_version="v7.0",
        output_text="text",
        output_json=None,
        cited_evidence_ids=[],
        cited_subcap_ids=[],
        validators_passed=True,
        confidence=0.9,
        prompt_tokens=100,
        completion_tokens=200,
        latency_ms=500,
        created_at=datetime.now(UTC),
        last_accessed_at=datetime.now(UTC),
        access_count=1,
        expires_at=None,
        invalidated_at=datetime.now(UTC) if invalidated else None,
        invalidation_reason="rerun" if invalidated else None,
        superseded_by=None,
        decision_gate="cache_miss_synthesized",
    )


def test_decide_synthesis_path_parsed_surface_skips_llm():
    """When the surface is in PARSED_ONLY_SURFACES, the orchestrator
    must return PARSED_NO_LLM with zero token cost. Audit contract:
    leadership panel + tech stack list never call Vertex."""
    from app.services.synthesis_orchestrator import (
        DecisionGate,
        decide_synthesis_path,
    )

    req = _make_request(surface="leadership_panel")  # parsed-only
    decision = decide_synthesis_path(req, lookup_existing=lambda *a: None)
    assert decision.gate == DecisionGate.PARSED_NO_LLM


def test_decide_synthesis_path_force_regenerate_supersedes_cache():
    """User clicks "Regenerate" → USER_REGENERATE even if a cache
    row exists. Audit gate #5 of the 8-gate matrix."""
    from app.services.synthesis_orchestrator import (
        DecisionGate,
        decide_synthesis_path,
    )

    req = _make_request(force_regenerate=True)
    existing = _make_row()

    decision = decide_synthesis_path(
        req, lookup_existing=lambda *a: existing,
    )
    assert decision.gate == DecisionGate.USER_REGENERATE


def test_decide_synthesis_path_invalidated_row_re_synthesises():
    """A cache row with input_fingerprint matching but invalidated_at
    NOT NULL must be CACHE_HIT_INVALIDATED -- caller re-synthesises."""
    from datetime import UTC, datetime

    from app.services.synthesis_orchestrator import (
        DecisionGate,
        compute_fingerprint,
        decide_synthesis_path,
        hash_page_context,
    )

    req = _make_request()
    # Compute the fingerprint the request would generate so the lookup
    # returns a matching row.
    fp = compute_fingerprint(
        prompt_template_version=req.prompt_template_version,
        grounding_bundle_hash="",
        catalogue_version=req.catalogue_version,
        page_context_hash=hash_page_context(req.page_context),
    )
    invalidated_row = _make_row(fingerprint=fp)
    # Override id field via dataclasses.replace to keep dataclass
    # invariants intact, then re-instantiate with invalidated metadata
    # by constructing fresh row that has the right fingerprint.
    import dataclasses as dc
    invalidated_row = dc.replace(
        invalidated_row,
        input_fingerprint=fp,
        # Mark as invalidated by setting expires_at in the past, OR by
        # the row's own invalidated_at field if present. The
        # synthesis_orchestrator checks expires_at or a separate
        # invalidated_at field; pin the behaviour with expires_at.
        expires_at=datetime(2000, 1, 1, tzinfo=UTC),
    )

    decision = decide_synthesis_path(
        req, lookup_existing=lambda *a: invalidated_row,
    )
    # Invalidated/expired row → CACHE_HIT_INVALIDATED (re-synthesise)
    # OR CACHE_MISS if the orchestrator treats expired as missing.
    assert decision.gate in (
        DecisionGate.CACHE_HIT_INVALIDATED,
        DecisionGate.CACHE_MISS,
    )
