"""Synthesis orchestrator — decision-gate state machine + token economics.

State coverage per test
-----------------------
test_fingerprint_stable             — same inputs → same fingerprint regardless of dict key order
test_fingerprint_changes_on_bundle  — bundle reorder → new fingerprint (rerank visible to cache)
test_page_context_strips_volatile   — user_id / session_id do not affect fingerprint
test_parsed_only_surface_skipped    — DecisionGate.PARSED_NO_LLM; no lookup performed
test_cache_miss_then_hit            — first call MISS, second identical call HIT, zero tokens
test_user_regenerate_bypasses       — force_regenerate=True always returns USER_REGENERATE
test_invalidated_row_re_synth       — invalidated_at set → CACHE_HIT_INVALIDATED
test_expired_row_re_synth           — expires_at in past → CACHE_HIT_INVALIDATED
test_invalidation_for_new_run       — rerun invalidation spec covers entity + affected subcaps
test_invalidation_for_cat_bump      — catalogue bump spec includes renamed subcaps + version-wide
test_invalidation_for_feedback      — feedback spec targets a single cache row id
test_estimate_cost_usd              — token totals → USD per per-1K rates
test_cache_hit_rate                 — boundary cases (0 calls, all hits, all misses)
test_compute_expires_at_ttl_zero    — TTL 0 → None (persist forever)
test_compute_expires_at_uses_surface— TTL pulled from override map when present
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.synthesis_orchestrator import (
    CacheRow,
    DecisionGate,
    SynthesisRequest,
    build_invalidation_for_catalogue_bump,
    build_invalidation_for_feedback,
    build_invalidation_for_new_run,
    compute_cache_hit_rate,
    compute_expires_at,
    compute_fingerprint,
    decide_synthesis_path,
    estimate_cost_usd,
    estimate_tokens_saved,
    hash_grounding_bundle,
    hash_page_context,
    ttl_for_surface,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(
    *,
    target_kind="entity",
    target_id="ent-1",
    surface="rag_answer",
    fingerprint="fp-xxx",
    invalidated_at: datetime | None = None,
    invalidation_reason: str | None = None,
    expires_at: datetime | None = None,
    superseded_by: str | None = None,
) -> CacheRow:
    now = datetime.now(UTC)
    return CacheRow(
        id="row-1",
        target_kind=target_kind,
        target_id=target_id,
        surface=surface,
        model="gemini-2.0-flash",
        input_fingerprint=fingerprint,
        prompt_template_version="v1",
        grounding_bundle_hash="bh-1",
        catalogue_version="v7.0",
        output_text="cached answer",
        output_json={"cited_evidence_ids": ["E-1"]},
        cited_evidence_ids=["E-1"],
        cited_subcap_ids=None,
        validators_passed=True,
        confidence=0.9,
        prompt_tokens=500,
        completion_tokens=200,
        latency_ms=1200,
        created_at=now - timedelta(minutes=5),
        last_accessed_at=now - timedelta(minutes=1),
        access_count=3,
        expires_at=expires_at,
        invalidated_at=invalidated_at,
        invalidation_reason=invalidation_reason,
        superseded_by=superseded_by,
        decision_gate=DecisionGate.CACHE_MISS.value,
    )


def _req(
    *,
    surface="rag_answer",
    target_id="ent-1",
    bundle=None,
    page_context=None,
    catalogue_version="v7.0",
    force_regenerate=False,
) -> SynthesisRequest:
    return SynthesisRequest(
        target_kind="entity",
        target_id=target_id,
        surface=surface,
        prompt_template_version="v1",
        grounding_bundle=bundle if bundle is not None else [
            {"id": "E-1", "kind": "evidence", "text": "..."},
        ],
        catalogue_version=catalogue_version,
        page_context=page_context if page_context is not None else {
            "route": "/clients/ent-1/overview",
            "entity_id": "ent-1",
        },
        force_regenerate=force_regenerate,
    )


# ---------------------------------------------------------------------------
# Fingerprint stability + sensitivity
# ---------------------------------------------------------------------------

def test_fingerprint_stable() -> None:
    """Same logical inputs in different dict-key orders → identical fingerprint."""
    fp_a = compute_fingerprint(
        prompt_template_version="v1",
        grounding_bundle_hash=hash_grounding_bundle([{"id": "E-1", "x": 1}]),
        catalogue_version="v7.0",
        page_context_hash=hash_page_context({"route": "/x", "entity_id": "e"}),
    )
    fp_b = compute_fingerprint(
        prompt_template_version="v1",
        grounding_bundle_hash=hash_grounding_bundle([{"x": 1, "id": "E-1"}]),
        catalogue_version="v7.0",
        page_context_hash=hash_page_context({"entity_id": "e", "route": "/x"}),
    )
    assert fp_a == fp_b


def test_fingerprint_changes_on_bundle_reorder() -> None:
    """Bundle order is semantically meaningful (top-k) — reorder MUST
    change the fingerprint so reranking is visible to the cache."""
    a = hash_grounding_bundle([{"id": "E-1"}, {"id": "E-2"}])
    b = hash_grounding_bundle([{"id": "E-2"}, {"id": "E-1"}])
    assert a != b


def test_page_context_strips_volatile_fields() -> None:
    """user_id / session_id / request_ts must not appear in fingerprint
    so users sharing the same view share cached answers."""
    a = hash_page_context({"route": "/x", "user_id": "alice"})
    b = hash_page_context({"route": "/x", "user_id": "bob"})
    c = hash_page_context({"route": "/x"})
    assert a == b == c


# ---------------------------------------------------------------------------
# Decision-gate state machine
# ---------------------------------------------------------------------------

def test_parsed_only_surface_skipped() -> None:
    """leadership_panel etc. → PARSED_NO_LLM; lookup never called."""
    lookup_calls = []

    def lookup(_kind, _id, _surface, _fp):
        lookup_calls.append((_kind, _id, _surface, _fp))
        return None

    decision = decide_synthesis_path(
        _req(surface="leadership_panel"), lookup_existing=lookup,
    )
    assert decision.gate == DecisionGate.PARSED_NO_LLM
    assert decision.existing_row is None
    assert decision.fingerprint == ""
    assert lookup_calls == [], "lookup must NOT fire for parsed-only surface"


def test_cache_miss_then_hit_zero_tokens() -> None:
    """First call → MISS (caller would synthesize + write). Same
    inputs second call → HIT, caller returns cached row WITHOUT
    spending tokens. This is the core token-savings assertion."""
    saved_rows: dict[str, CacheRow] = {}

    def lookup(kind, tid, surface, fp):
        return saved_rows.get(f"{kind}:{tid}:{surface}:{fp}")

    req = _req()

    # First call — no row yet.
    first = decide_synthesis_path(req, lookup_existing=lookup)
    assert first.gate == DecisionGate.CACHE_MISS
    assert first.existing_row is None
    assert first.fingerprint != ""

    # Caller would now invoke Vertex, get back text + token counts,
    # and persist the row. Simulate that.
    persisted = _row(
        surface=req.surface, target_id=req.target_id,
        fingerprint=first.fingerprint,
    )
    saved_rows[
        f"{req.target_kind}:{req.target_id}:{req.surface}:{first.fingerprint}"
    ] = persisted

    # Second identical call — must hit cache.
    second = decide_synthesis_path(req, lookup_existing=lookup)
    assert second.gate == DecisionGate.CACHE_HIT_FRESH
    assert second.existing_row is persisted
    assert second.fingerprint == first.fingerprint
    # The whole point: the caller would now return `persisted.output_text`
    # WITHOUT invoking Vertex. Zero tokens consumed on this call.


def test_user_regenerate_bypasses_cache() -> None:
    """force_regenerate=True → USER_REGENERATE even when a fresh row exists."""
    fresh = _row()

    def lookup(_kind, _id, _surface, _fp):
        return fresh

    decision = decide_synthesis_path(
        _req(force_regenerate=True), lookup_existing=lookup,
    )
    assert decision.gate == DecisionGate.USER_REGENERATE
    assert decision.existing_row is fresh   # caller uses it for supersede chain


def test_invalidated_row_triggers_re_synth() -> None:
    """invalidated_at set → CACHE_HIT_INVALIDATED (re-synthesize)."""
    inv = _row(
        invalidated_at=datetime.now(UTC) - timedelta(minutes=10),
        invalidation_reason="rerun_invalidate_all",
    )

    def lookup(_kind, _id, _surface, _fp):
        return inv

    decision = decide_synthesis_path(_req(), lookup_existing=lookup)
    assert decision.gate == DecisionGate.CACHE_HIT_INVALIDATED
    assert "rerun_invalidate_all" in (decision.reason or "")


def test_expired_row_triggers_re_synth() -> None:
    """expires_at in past → CACHE_HIT_INVALIDATED."""
    expired = _row(
        expires_at=datetime.now(UTC) - timedelta(hours=2),
    )

    def lookup(_kind, _id, _surface, _fp):
        return expired

    decision = decide_synthesis_path(_req(), lookup_existing=lookup)
    assert decision.gate == DecisionGate.CACHE_HIT_INVALIDATED
    assert "expired" in (decision.reason or "")


def test_active_unexpired_row_is_fresh_hit() -> None:
    """expires_at in future, invalidated_at NULL → CACHE_HIT_FRESH."""
    future = _row(expires_at=datetime.now(UTC) + timedelta(hours=2))

    def lookup(_kind, _id, _surface, _fp):
        return future

    decision = decide_synthesis_path(_req(), lookup_existing=lookup)
    assert decision.gate == DecisionGate.CACHE_HIT_FRESH


# ---------------------------------------------------------------------------
# Invalidation specs
# ---------------------------------------------------------------------------

def test_invalidation_for_new_run_includes_entity_and_subcaps() -> None:
    """A new run for an entity invalidates entity-level rows + any
    subcap-keyed row for subcaps whose evidence changed."""
    specs = build_invalidation_for_new_run(
        entity_id="ent-1",
        affected_subcap_ids=["P1C1.1.1", "P2C3.2.4"],
    )
    assert len(specs) == 2
    entity_spec, subcap_spec = specs
    assert entity_spec.target_kind == "entity"
    assert entity_spec.target_ids == ("ent-1",)
    assert subcap_spec.target_kind == "subcap"
    assert subcap_spec.target_ids == ("P1C1.1.1", "P2C3.2.4")


def test_invalidation_for_new_run_without_subcaps() -> None:
    """Entity-only invalidation when no subcap evidence changed."""
    specs = build_invalidation_for_new_run("ent-1", None)
    assert len(specs) == 1
    assert specs[0].target_kind == "entity"


def test_invalidation_for_new_run_entity_scoped_subcap_prefix() -> None:
    """A rerun invalidates the WHOLE entity's subcap surface via a display_id
    PREFIX — subcap rows are keyed ``{display_id}:{subcap_id}:…`` so a bare-id
    match never hit them (2026-07-14 audit)."""
    specs = build_invalidation_for_new_run(
        entity_id="ent-1", entity_display_id="alma-bank-0001",
    )
    assert len(specs) == 2
    entity_spec, subcap_spec = specs
    assert entity_spec.target_kind == "entity"
    assert subcap_spec.target_kind == "subcap"
    assert subcap_spec.target_id_prefix == "alma-bank-0001:"
    assert subcap_spec.target_ids is None       # prefix match, not id set


def test_mark_invalidated_prefix_builds_escaped_like(monkeypatch) -> None:
    """The prefix spec compiles to a LIKE with escaped metacharacters so a
    display_id containing % or _ cannot over-match."""
    from app.services import synthesis_cache_db as db
    from app.services.synthesis_orchestrator import InvalidationSpec

    captured: dict = {}

    class _Res:
        rowcount = 3

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params):
            captured["sql"] = str(sql)
            captured["params"] = params
            return _Res()

    class _Eng:
        def begin(self):
            return _Conn()

    monkeypatch.setattr(db, "_get_engine", lambda: _Eng())
    n = db.mark_invalidated(InvalidationSpec(
        reason="rerun_invalidate_all_surfaces",
        target_kind="subcap",
        target_id_prefix="a_b%c:",
    ))
    assert n == 3
    assert "target_id LIKE" in captured["sql"]
    assert captured["params"]["tidp"] == r"a\_b\%c:%"   # _ and % escaped


def test_invalidation_for_catalogue_bump() -> None:
    """Catalogue bump includes renamed subcap specs + a version-wide spec."""
    specs = build_invalidation_for_catalogue_bump(
        old_version="v7.0",
        renamed_subcap_ids=["P9C9.9.9"],
    )
    assert len(specs) == 2
    renamed_spec, version_spec = specs
    assert renamed_spec.target_kind == "subcap"
    assert renamed_spec.target_ids == ("P9C9.9.9",)
    assert renamed_spec.catalogue_version == "v7.0"
    assert version_spec.catalogue_version == "v7.0"
    assert version_spec.target_kind is None     # all kinds


def test_invalidation_for_feedback_single_row() -> None:
    """Feedback invalidation targets exactly one cache row."""
    spec = build_invalidation_for_feedback("row-abc")
    assert spec.cache_row_id == "row-abc"
    assert spec.target_kind is None
    assert spec.reason == "feedback_invalidated"


# ---------------------------------------------------------------------------
# Token economics
# ---------------------------------------------------------------------------

def test_estimate_cost_usd_flash() -> None:
    """Gemini Flash @ 0.075/1K prompt + 0.3/1K completion (per 1M tokens)."""
    cost = estimate_cost_usd("gemini-2.0-flash", 10_000, 5_000)
    expected = (10_000 / 1000.0) * 0.000075 + (5_000 / 1000.0) * 0.0003
    assert abs(cost - expected) < 1e-9


def test_estimate_cost_usd_unknown_model() -> None:
    """Unknown model → 0.0, never crashes the budget panel."""
    assert estimate_cost_usd("future-llm-x", 1000, 1000) == 0.0


def test_cache_hit_rate_bounds() -> None:
    """Hit rate must be in [0, 1] and handle zero-call edge case."""
    assert compute_cache_hit_rate(0, 0) == 0.0
    assert compute_cache_hit_rate(10, 0) == 1.0
    assert compute_cache_hit_rate(10, 10) == 0.0
    assert compute_cache_hit_rate(10, 3) == 0.7


def test_estimate_tokens_saved() -> None:
    """50 hits x 1000 avg tokens = 50_000 tokens saved."""
    saved = estimate_tokens_saved(
        cache_hits=50,
        avg_prompt_tokens_per_call=700.0,
        avg_completion_tokens_per_call=300.0,
    )
    assert saved == 50_000


# ---------------------------------------------------------------------------
# TTL + expires_at
# ---------------------------------------------------------------------------

def test_ttl_for_surface_uses_overrides() -> None:
    """TTL override (from system_config read) wins over default."""
    overrides = {"rag_answer": 60}
    assert ttl_for_surface("rag_answer", overrides) == 60
    # Surface not in overrides falls back to DEFAULT_TTL_SEC.
    assert ttl_for_surface("subcap_narrative", overrides) == 604_800


def test_ttl_for_surface_default_fallback() -> None:
    """Unknown surface gets a safe 1-day default."""
    assert ttl_for_surface("never_heard_of_it") == 86_400


def test_compute_expires_at_for_zero_ttl_is_none() -> None:
    """TTL 0 = persist forever (only invalidation events displace).
    This is what `enrichment` surface relies on."""
    exp = compute_expires_at("enrichment")
    assert exp is None


def test_compute_expires_at_uses_surface_ttl() -> None:
    """expires_at is now + TTL for surfaces with a positive TTL."""
    now = datetime(2026, 5, 23, tzinfo=UTC)
    exp = compute_expires_at("rag_answer", now=now)
    assert exp == now + timedelta(seconds=900)


# ---------------------------------------------------------------------------
# Cross-step integration: full miss → hit → invalidate → re-synth flow
# ---------------------------------------------------------------------------

def test_full_lifecycle_miss_hit_invalidate_re_synth() -> None:
    """Sequence:
      1. CACHE_MISS (caller synthesizes + writes row)
      2. CACHE_HIT_FRESH (zero tokens)
      3. Caller invalidates via rerun → invalidated_at set
      4. CACHE_HIT_INVALIDATED (caller re-synthesizes)
      5. CACHE_HIT_FRESH again (next reader)
    """
    saved: dict[str, CacheRow] = {}

    def lookup(kind, tid, surface, fp):
        return saved.get(f"{kind}:{tid}:{surface}:{fp}")

    req = _req()

    # Step 1: miss
    d1 = decide_synthesis_path(req, lookup_existing=lookup)
    assert d1.gate == DecisionGate.CACHE_MISS
    row1 = _row(fingerprint=d1.fingerprint)
    saved[f"entity:ent-1:rag_answer:{d1.fingerprint}"] = row1

    # Step 2: fresh hit
    d2 = decide_synthesis_path(req, lookup_existing=lookup)
    assert d2.gate == DecisionGate.CACHE_HIT_FRESH

    # Step 3: simulate rerun invalidation — caller does an UPDATE SET
    # invalidated_at=NOW(), invalidation_reason='rerun_invalidate_all'
    saved[f"entity:ent-1:rag_answer:{d1.fingerprint}"] = _row(
        fingerprint=d1.fingerprint,
        invalidated_at=datetime.now(UTC),
        invalidation_reason="rerun_invalidate_all",
    )

    # Step 4: invalidated hit (caller re-synthesizes)
    d3 = decide_synthesis_path(req, lookup_existing=lookup)
    assert d3.gate == DecisionGate.CACHE_HIT_INVALIDATED
    # Caller writes a fresh row with the SAME fingerprint
    # (same inputs); the prior row's superseded_by gets set.
    saved[f"entity:ent-1:rag_answer:{d1.fingerprint}"] = _row(
        fingerprint=d1.fingerprint,
    )

    # Step 5: fresh hit again
    d4 = decide_synthesis_path(req, lookup_existing=lookup)
    assert d4.gate == DecisionGate.CACHE_HIT_FRESH
