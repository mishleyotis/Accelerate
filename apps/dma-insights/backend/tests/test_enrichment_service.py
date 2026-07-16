"""Tests for the AI enrichment service.

Exercises prompt construction, template fallback, validator short-circuit,
supersede decision, and the end-to-end enrich_with_fallback pipeline.
"""
from __future__ import annotations

from app.services.enrichment import (
    EnrichmentInput,
    build_enrichment_prompt,
    enrich_with_fallback,
    should_supersede,
    template_enrichment_text,
    validate_enrichment,
)


def _input(**kw) -> EnrichmentInput:
    base = {
        "target_kind": "subcap_score",
        "target_id": "11111111-1111-1111-1111-111111111111",
        "surface": "subcap_narrative",
        "catalogue_version": "v7.0",
        "grounding_evidence": [
            {"e_id": "E-12", "source_name": "10-K", "excerpt": "x"},
            {"e_id": "E-13", "source_name": "press", "excerpt": "y"},
        ],
        "capability_text": "Sample capability prose",
        "peer_median": 3.2,
        "peer_n": 5,
    }
    base.update(kw)
    return EnrichmentInput(**base)  # type: ignore[arg-type]


class TestPrompt:
    def test_includes_every_e_id(self) -> None:
        p = build_enrichment_prompt(_input())
        assert "E-12" in p
        assert "E-13" in p
        assert "MUST cite every" in p

    def test_peer_median_appears_when_n_ge_3(self) -> None:
        p = build_enrichment_prompt(_input(peer_median=3.2, peer_n=5))
        assert "Peer median" in p

    def test_peer_median_hidden_when_n_lt_3(self) -> None:
        p = build_enrichment_prompt(_input(peer_n=2))
        assert "Peer median" not in p

    def test_handles_empty_evidence(self) -> None:
        p = build_enrichment_prompt(_input(grounding_evidence=[]))
        assert "no evidence supplied" in p


class TestTemplateFallback:
    def test_references_every_e_id(self) -> None:
        text = template_enrichment_text(_input())
        assert "[E-12]" in text
        assert "[E-13]" in text

    def test_handles_empty_evidence(self) -> None:
        text = template_enrichment_text(_input(grounding_evidence=[]))
        assert "Evidence is sparse" in text

    def test_peer_median_inline(self) -> None:
        text = template_enrichment_text(_input(peer_median=3.2, peer_n=5))
        assert "3.20" in text or "Peer median" in text


class TestValidateEnrichment:
    def test_accepts_clean_response(self) -> None:
        clean, fab = validate_enrichment(
            response_text="Refers to [E-12] and [E-13].",
            grounding_evidence_ids=["E-12", "E-13"],
        )
        assert clean is True
        assert fab == []

    def test_rejects_fabricated_e_id(self) -> None:
        clean, fab = validate_enrichment(
            response_text="Refers to [E-12] and [E-99999] (made up).",
            grounding_evidence_ids=["E-12"],
        )
        assert clean is False
        assert fab == ["E-99999"]

    def test_no_e_ids_means_clean(self) -> None:
        clean, _fab = validate_enrichment(
            response_text="Plain text with no IDs.",
            grounding_evidence_ids=["E-12"],
        )
        assert clean is True


class TestEnrichWithFallback:
    def test_empty_grounding_returns_template(self) -> None:
        r = enrich_with_fallback(_input(grounding_evidence=[]))
        assert r.fallback_used is True
        assert r.model == "template"
        assert r.validators_passed is True

    def test_no_generator_returns_template_with_eids(self) -> None:
        r = enrich_with_fallback(_input())
        assert r.fallback_used is True
        assert "E-12" in r.enrichment_text
        assert r.grounding_evidence_ids == ["E-12", "E-13"]

    def test_clean_generator_passes_through(self) -> None:
        def gen(inp: EnrichmentInput) -> str:
            return "Per [E-12] and [E-13], the entity is mid-band."
        r = enrich_with_fallback(_input(), generate_fn=gen)
        assert r.fallback_used is False
        assert r.validators_passed is True
        assert r.model == "flash"

    def test_fabricating_generator_falls_back(self) -> None:
        def gen(inp: EnrichmentInput) -> str:
            return "Per [E-12] and [E-99999] (fake)."
        r = enrich_with_fallback(_input(), generate_fn=gen)
        assert r.fallback_used is True
        assert r.validators_passed is False
        assert r.model == "template"

    def test_raising_generator_falls_back(self) -> None:
        def gen(inp: EnrichmentInput) -> str:
            raise RuntimeError("vertex went down")
        r = enrich_with_fallback(_input(), generate_fn=gen)
        assert r.fallback_used is True
        assert r.model == "template"


class TestShouldSupersede:
    def test_no_prior_no_supersede(self) -> None:
        assert should_supersede(
            prior_catalogue_version=None, new_catalogue_version="v7.0",
        ) is False

    def test_prior_same_version_still_supersedes(self) -> None:
        # Audit-trail principle: any prior row is replaced (supersede chain
        # keeps the history). Tests the documented contract.
        assert should_supersede(
            prior_catalogue_version="v7.0", new_catalogue_version="v7.0",
        ) is True

    def test_prior_different_version_supersedes(self) -> None:
        assert should_supersede(
            prior_catalogue_version="v6.0", new_catalogue_version="v7.0",
        ) is True
