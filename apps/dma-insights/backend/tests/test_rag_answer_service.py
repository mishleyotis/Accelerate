"""Tests for the pure-logic RAG /answer service helpers.

These exercise the deterministic surfaces — token-cap, cache-key, cohort
fallback, fallback-text rendering, citation extraction — without any DB
or Vertex IO.
"""
from __future__ import annotations

from app.services.rag_answer import (
    APPROX_CHARS_PER_TOKEN,
    MAX_GROUNDING_TOKENS,
    RATE_LIMITS_PER_DAY,
    SURFACE_CACHE_TTL,
    GroundingBundle,
    RetrievedItem,
    build_answer_prompt,
    cache_key_for_answer,
    cap_bundle_by_tokens,
    cohort_from_profile,
    daily_rate_limit_key,
    estimate_tokens,
    extract_citations,
    fallback_answer,
    model_for_style,
)


class TestEstimateTokens:
    def test_short_string(self) -> None:
        assert estimate_tokens("hello") == 1  # min 1

    def test_long_string(self) -> None:
        s = "x" * 4000
        assert estimate_tokens(s) == 4000 // APPROX_CHARS_PER_TOKEN

    def test_empty(self) -> None:
        # max(1, 0 // 4) = 1
        assert estimate_tokens("") == 1


class TestCapBundleByTokens:
    def test_returns_empty_for_empty_input(self) -> None:
        assert cap_bundle_by_tokens([]) == []

    def test_keeps_all_under_cap(self) -> None:
        items = [
            RetrievedItem(kind="evidence", ref_id=f"E-{i}",
                          text="short item " + str(i), similarity=1.0 - i * 0.01)
            for i in range(10)
        ]
        kept = cap_bundle_by_tokens(items, max_tokens=1000)
        assert len(kept) == 10
        # Sorted by similarity desc
        assert kept[0].ref_id == "E-0"
        assert kept[-1].ref_id == "E-9"

    def test_drops_lowest_similarity_when_exceeded(self) -> None:
        big_text = "x" * 4001  # ~1000 tokens
        items = [
            RetrievedItem(kind="evidence", ref_id=f"E-{i}",
                          text=big_text, similarity=1.0 - i * 0.1)
            for i in range(5)
        ]
        kept = cap_bundle_by_tokens(items, max_tokens=2500)
        # Each big_text ≈ 1000 tokens, so we can fit 2 only
        assert len(kept) == 2
        assert kept[0].ref_id == "E-0"
        assert kept[1].ref_id == "E-1"

    def test_default_cap_is_16k(self) -> None:
        assert MAX_GROUNDING_TOKENS == 16_000


class TestCohortFromProfile:
    def test_no_entity_returns_catalogue_only(self) -> None:
        mode, insuf = cohort_from_profile(
            entity_id=None, subvertical=None, n_in_cohort=0,
        )
        assert mode == "catalogue_only"
        assert insuf is False

    def test_no_subvertical_returns_catalogue_only(self) -> None:
        mode, insuf = cohort_from_profile(
            entity_id="e1", subvertical=None, n_in_cohort=5,
        )
        assert mode == "catalogue_only"
        assert insuf is False

    def test_small_cohort_returns_cross_vertical(self) -> None:
        mode, insuf = cohort_from_profile(
            entity_id="e1", subvertical="CU", n_in_cohort=2,
        )
        assert mode == "cross_vertical"
        assert insuf is True

    def test_full_cohort_returns_single(self) -> None:
        mode, insuf = cohort_from_profile(
            entity_id="e1", subvertical="CU", n_in_cohort=3,
        )
        assert mode == "single"
        assert insuf is False

    def test_large_cohort_returns_single(self) -> None:
        mode, insuf = cohort_from_profile(
            entity_id="e1", subvertical="CU", n_in_cohort=42,
        )
        assert mode == "single"
        assert insuf is False


class TestCacheKey:
    def test_same_inputs_same_key(self) -> None:
        k1 = cache_key_for_answer(
            question="What is X?", entity_id="e1",
            subcap_id="P1C1.1.1", catalogue_version="v7.0",
            response_style="concise",
        )
        k2 = cache_key_for_answer(
            question="What is X?", entity_id="e1",
            subcap_id="P1C1.1.1", catalogue_version="v7.0",
            response_style="concise",
        )
        assert k1 == k2
        assert k1.startswith("rag:answer:")

    def test_case_insensitive_question(self) -> None:
        k1 = cache_key_for_answer(
            question="What is X?", entity_id=None,
            subcap_id=None, catalogue_version="v7.0",
            response_style="concise",
        )
        k2 = cache_key_for_answer(
            question="WHAT IS X?", entity_id=None,
            subcap_id=None, catalogue_version="v7.0",
            response_style="concise",
        )
        assert k1 == k2

    def test_different_catalogue_version_changes_key(self) -> None:
        k1 = cache_key_for_answer(
            question="Q", entity_id="e1", subcap_id=None,
            catalogue_version="v7.0", response_style="concise",
        )
        k2 = cache_key_for_answer(
            question="Q", entity_id="e1", subcap_id=None,
            catalogue_version="v8.0", response_style="concise",
        )
        assert k1 != k2

    def test_different_entity_changes_key(self) -> None:
        k1 = cache_key_for_answer(
            question="Q", entity_id="e1", subcap_id=None,
            catalogue_version="v7.0", response_style="concise",
        )
        k2 = cache_key_for_answer(
            question="Q", entity_id="e2", subcap_id=None,
            catalogue_version="v7.0", response_style="concise",
        )
        assert k1 != k2

    def test_style_changes_key(self) -> None:
        k1 = cache_key_for_answer(
            question="Q", entity_id="e1", subcap_id=None,
            catalogue_version="v7.0", response_style="concise",
        )
        k2 = cache_key_for_answer(
            question="Q", entity_id="e1", subcap_id=None,
            catalogue_version="v7.0", response_style="deeper",
        )
        assert k1 != k2


class TestModelForStyle:
    def test_concise_is_flash(self) -> None:
        assert model_for_style("concise") == "flash"

    def test_deeper_is_pro(self) -> None:
        assert model_for_style("deeper") == "pro"

    def test_unknown_falls_back_to_flash(self) -> None:
        assert model_for_style("?") == "flash"


class TestBuildAnswerPrompt:
    def test_empty_bundle_indicates_no_grounding(self) -> None:
        bundle = GroundingBundle(items=[], cohort_mode="catalogue_only")
        p = build_answer_prompt(
            question="Hi", bundle=bundle, style="concise",
            max_paragraphs=3, conversation_tail=None,
        )
        # Empty bundle still surfaces a sentinel marker so the model
        # knows there's no grounding — wrapped in the new <evidence>
        # tag scheme for prompt-injection consistency.
        assert "no grounding bundle" in p
        # Question is now wrapped in <question>…</question> tags (2026-06
        # prompt-injection guard). Pin the new shape.
        assert "<question>Hi</question>" in p

    def test_conversation_tail_truncates_to_4(self) -> None:
        bundle = GroundingBundle(items=[], cohort_mode="catalogue_only")
        tail = [("user", f"q{i}") for i in range(10)]
        p = build_answer_prompt(
            question="Hi", bundle=bundle, style="concise",
            max_paragraphs=3, conversation_tail=tail,
        )
        # Only last 4 included
        assert "q9" in p
        assert "q5" not in p

    def test_evidence_items_appear_in_prompt(self) -> None:
        bundle = GroundingBundle(
            items=[
                RetrievedItem(kind="evidence", ref_id="E-12",
                              text="cited excerpt here", similarity=0.9),
            ],
            cohort_mode="single",
        )
        p = build_answer_prompt(
            question="Hi", bundle=bundle, style="concise", max_paragraphs=2,
        )
        assert "E-12" in p
        assert "cited excerpt here" in p


class TestFallbackAnswer:
    def test_no_grounding_message(self) -> None:
        b = GroundingBundle()
        text = fallback_answer(question="Hi", bundle=b, reason="no_grounding")
        assert "don't have enough grounded evidence" in text

    def test_rate_limited_message(self) -> None:
        b = GroundingBundle()
        text = fallback_answer(question="Hi", bundle=b, reason="rate_limited")
        assert "rate-limited" in text or "rate-limit" in text.lower()

    def test_validator_rejected_default(self) -> None:
        b = GroundingBundle()
        text = fallback_answer(question="Hi", bundle=b)
        assert "validators" in text.lower() or "validator" in text.lower()


class TestExtractCitations:
    def test_finds_e_ids(self) -> None:
        s = "Per [E-12] and E-99, see also [E-12] again."
        assert extract_citations(s) == ["E-12", "E-99"]

    def test_no_citations_returns_empty(self) -> None:
        assert extract_citations("Plain text") == []

    def test_dedupes(self) -> None:
        assert extract_citations("E-1 E-1 E-1") == ["E-1"]


class TestRateLimitKey:
    def test_includes_components(self) -> None:
        k = daily_rate_limit_key(user_id="abc", surface="meeting_prep", ymd="20260523")
        assert "meeting_prep" in k
        assert "abc" in k
        assert "20260523" in k


class TestConstants:
    def test_meeting_prep_rate_limited(self) -> None:
        assert RATE_LIMITS_PER_DAY["meeting_prep"] == 20

    def test_surface_cache_ttl_keys(self) -> None:
        # All expected surfaces have a TTL
        for s in ("rag_answer", "subcap_narrative", "meeting_prep"):
            assert s in SURFACE_CACHE_TTL
            assert SURFACE_CACHE_TTL[s] > 0
