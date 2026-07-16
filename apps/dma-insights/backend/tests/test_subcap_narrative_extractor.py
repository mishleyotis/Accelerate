"""Tests for the per-subcap narrative extractor.

State-transition coverage matrix (all 4 branches in
parsers.subcap_narrative_extractor.ExtractorState):

  - full_match
      → test_full_llm_coverage_returns_llm_source
  - partial_match_with_warnings
      → test_partial_match_strips_fabricated_subcap
      → test_alma_p1_12_subcaps_10_llm_2_heuristic
  - validator_rejected_template_fallback
      → test_no_llm_payload_falls_back_to_heuristic
      → test_all_fabricated_falls_back
  - empty_input
      → test_empty_subcap_list_returns_empty
"""
from __future__ import annotations

import asyncio
import json

from app.services.parsers.subcap_narrative_extractor import (
    PerSubcapNarrative,
    build_prompt,
    cache_key,
    extract_per_subcap_narrative,
    heuristic_per_subcap,
    merge_llm_and_heuristic,
    parse_llm_text,
    validate,
)


class _FakeVertexGood:
    """Returns a structured-output JSON wrapper as a single chunk."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.call_count = 0

    async def stream(self, call):
        self.call_count += 1
        yield json.dumps(self.payload)


class _FakeVertexBad:
    async def stream(self, call):
        raise RuntimeError("offline")
        yield ""


class _FakeCache:
    """In-process dict masquerading as Redis-async client."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int = 0):
        self.store[key] = value


# ---------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------


class TestCacheKey:
    def test_same_inputs_same_key(self) -> None:
        a = cache_key(pillar_id="P1", body_text="x", run_id="r")
        b = cache_key(pillar_id="P1", body_text="x", run_id="r")
        assert a == b
        assert a.startswith("subcap_narrative:")

    def test_diff_body_diff_key(self) -> None:
        a = cache_key(pillar_id="P1", body_text="x", run_id="r")
        b = cache_key(pillar_id="P1", body_text="y", run_id="r")
        assert a != b


class TestBuildPrompt:
    def test_lists_valid_subcaps(self) -> None:
        out = build_prompt(
            pillar_id="P1", body_text="body",
            valid_subcap_ids=["P1C1.1.1", "P1C1.1.2"],
            valid_evidence_ids=["E-1"],
        )
        assert "P1C1.1.1" in out
        assert "P1C1.1.2" in out
        assert "E-1" in out

    def test_body_included(self) -> None:
        out = build_prompt(
            pillar_id="P1", body_text="UNIQUE_BODY_TOKEN",
            valid_subcap_ids=["P1C1.1.1"],
            valid_evidence_ids=[],
        )
        assert "UNIQUE_BODY_TOKEN" in out


class TestValidate:
    def test_drops_fabricated_subcap(self) -> None:
        raw = {"per_subcap_narrative": [
            {"subcap_id": "P1C1.1.1", "narrative_md": "real",
             "evidence_anchors": [], "confidence": 0.9},
            {"subcap_id": "P9C9.9.9", "narrative_md": "fake",
             "evidence_anchors": [], "confidence": 0.9},
        ]}
        kept, rejected, _ = validate(
            raw, valid_subcap_ids=["P1C1.1.1"],
        )
        assert len(kept) == 1
        assert kept[0].subcap_id == "P1C1.1.1"
        assert rejected == ["P9C9.9.9"]

    def test_strips_fabricated_anchor(self) -> None:
        raw = {"per_subcap_narrative": [
            {"subcap_id": "P1C1.1.1", "narrative_md": "x",
             "evidence_anchors": ["E-1", "E-FAKE"], "confidence": 1.0},
        ]}
        kept, _, rejected_anchors = validate(
            raw, valid_subcap_ids=["P1C1.1.1"],
            valid_evidence_ids=["E-1"],
        )
        assert kept[0].evidence_anchors == ["E-1"]
        assert rejected_anchors == ["E-FAKE"]

    def test_empty_narrative_dropped(self) -> None:
        raw = {"per_subcap_narrative": [
            {"subcap_id": "P1C1.1.1", "narrative_md": "  ",
             "evidence_anchors": []},
        ]}
        kept, _, _ = validate(raw, valid_subcap_ids=["P1C1.1.1"])
        assert kept == []


class TestParseLLMText:
    def test_plain_json(self) -> None:
        assert parse_llm_text('{"per_subcap_narrative":[]}') == {
            "per_subcap_narrative": []
        }

    def test_code_fence(self) -> None:
        out = parse_llm_text(
            "```json\n" + '{"per_subcap_narrative":[]}' + "\n```"
        )
        assert out == {"per_subcap_narrative": []}

    def test_bad_json(self) -> None:
        assert parse_llm_text("not json") is None


class TestHeuristic:
    def test_finds_paragraph_mentioning_subcap(self) -> None:
        body = "Intro paragraph.\n\nP1C1.1.1 maturity is low.\n\nSummary."
        out = heuristic_per_subcap(
            body_text=body, valid_subcap_ids=["P1C1.1.1"],
        )
        assert len(out) == 1
        assert "P1C1.1.1" in out[0].narrative_md

    def test_skip_subcap_with_no_mention(self) -> None:
        body = "No subcaps mentioned."
        out = heuristic_per_subcap(
            body_text=body, valid_subcap_ids=["P1C1.1.1"],
        )
        assert out == []


class TestMergeLLMAndHeuristic:
    def test_full_llm_returns_llm(self) -> None:
        llm = [
            PerSubcapNarrative(subcap_id="P1C1.1.1", narrative_md="x"),
        ]
        out, src = merge_llm_and_heuristic(
            llm_narratives=llm,
            valid_subcap_ids=["P1C1.1.1"],
            body_text="",
        )
        assert src == "llm"
        assert out == llm

    def test_mixed(self) -> None:
        llm = [
            PerSubcapNarrative(subcap_id="P1C1.1.1", narrative_md="x"),
        ]
        body = "P1C1.1.2 something.\n\nNo other mentions."
        out, src = merge_llm_and_heuristic(
            llm_narratives=llm,
            valid_subcap_ids=["P1C1.1.1", "P1C1.1.2"],
            body_text=body,
        )
        assert src == "mixed"
        assert len(out) == 2
        ids = {n.subcap_id for n in out}
        assert ids == {"P1C1.1.1", "P1C1.1.2"}


# ---------------------------------------------------------------------
# extract_per_subcap_narrative — 4 state branches
# ---------------------------------------------------------------------


class TestExtractStateMatrix:
    def test_empty_subcap_list_returns_empty(self) -> None:
        result = asyncio.run(
            extract_per_subcap_narrative(
                pillar_id="P1", body_text="anything",
                valid_subcap_ids=[],
                vertex_client=_FakeVertexGood({"per_subcap_narrative": []}),
            )
        )
        assert result.state == "empty_input"
        assert result.narratives == []

    def test_full_llm_coverage_returns_llm_source(self) -> None:
        vertex = _FakeVertexGood({"per_subcap_narrative": [
            {"subcap_id": "P1C1.1.1", "narrative_md": "valid narrative",
             "evidence_anchors": ["E-1"], "confidence": 0.9},
        ]})
        result = asyncio.run(
            extract_per_subcap_narrative(
                pillar_id="P1", body_text="ignored",
                valid_subcap_ids=["P1C1.1.1"],
                valid_evidence_ids=["E-1"],
                vertex_client=vertex,
            )
        )
        assert result.state == "full_match"
        assert result.data_source == "llm"
        assert len(result.narratives) == 1

    def test_partial_match_strips_fabricated_subcap(self) -> None:
        vertex = _FakeVertexGood({"per_subcap_narrative": [
            {"subcap_id": "P1C1.1.1", "narrative_md": "real",
             "evidence_anchors": [], "confidence": 0.9},
            {"subcap_id": "P9C9.9.9", "narrative_md": "fabricated subcap",
             "evidence_anchors": [], "confidence": 0.9},
        ]})
        result = asyncio.run(
            extract_per_subcap_narrative(
                pillar_id="P1", body_text="",
                valid_subcap_ids=["P1C1.1.1"],
                vertex_client=vertex,
            )
        )
        assert result.state == "partial_match_with_warnings"
        assert "P9C9.9.9" in result.rejected_subcap_ids
        ids = {n.subcap_id for n in result.narratives}
        assert "P9C9.9.9" not in ids
        assert "P1C1.1.1" in ids

    def test_alma_p1_12_subcaps_10_llm_2_heuristic(self) -> None:
        """AlmaBank-style: 12 subcap_ids, LLM returns narratives for 10.
        Heatmap drill shows 10 LLM narratives + 2 heuristic fallbacks
        (when body paragraphs mention them)."""
        twelve = [f"P1C1.1.{i}" for i in range(1, 13)]
        ten_payload = [
            {"subcap_id": f"P1C1.1.{i}", "narrative_md": f"llm-{i}",
             "evidence_anchors": [], "confidence": 0.8}
            for i in range(1, 11)
        ]
        vertex = _FakeVertexGood({"per_subcap_narrative": ten_payload})
        # Body contains mentions of the remaining 11 + 12.
        body = (
            "First paragraph mentions P1C1.1.11 a lot.\n\n"
            "Second paragraph references P1C1.1.12 specifically.\n\n"
            "More general text without subcap codes."
        )
        result = asyncio.run(
            extract_per_subcap_narrative(
                pillar_id="P1", body_text=body,
                valid_subcap_ids=twelve, vertex_client=vertex,
            )
        )
        assert result.state == "partial_match_with_warnings"
        assert result.data_source == "mixed"
        ids = sorted({n.subcap_id for n in result.narratives})
        assert ids == sorted(twelve)
        # 10 LLM + 2 heuristic.
        llm_ids = {n.subcap_id for n in result.narratives
                   if n.narrative_md.startswith("llm-")}
        heuristic_ids = {n.subcap_id for n in result.narratives
                         if "paragraph" in n.narrative_md.lower()}
        assert len(llm_ids) == 10
        assert len(heuristic_ids) == 2

    def test_no_llm_payload_falls_back_to_heuristic(self) -> None:
        """Vertex offline → state=validator_rejected_template_fallback."""
        result = asyncio.run(
            extract_per_subcap_narrative(
                pillar_id="P1",
                body_text="P1C1.1.1 is weak.",
                valid_subcap_ids=["P1C1.1.1"],
                vertex_client=_FakeVertexBad(),
            )
        )
        assert result.state == "validator_rejected_template_fallback"
        assert result.data_source == "heuristic"
        assert len(result.narratives) == 1

    def test_all_fabricated_falls_back(self) -> None:
        # LLM returns only fabricated subcap IDs.
        vertex = _FakeVertexGood({"per_subcap_narrative": [
            {"subcap_id": "P9C9.9.9", "narrative_md": "fake",
             "evidence_anchors": []},
        ]})
        result = asyncio.run(
            extract_per_subcap_narrative(
                pillar_id="P1",
                body_text="P1C1.1.1 mention.",
                valid_subcap_ids=["P1C1.1.1"],
                vertex_client=vertex,
            )
        )
        assert result.state == "validator_rejected_template_fallback"
        assert "P9C9.9.9" in result.rejected_subcap_ids


# ---------------------------------------------------------------------
# Cache integration
# ---------------------------------------------------------------------


class TestCacheIntegration:
    def test_cache_hit_skips_vertex(self) -> None:
        # Pre-populate cache with a known-good payload.
        cache = _FakeCache()
        key = cache_key(pillar_id="P1", body_text="b", run_id="r")
        cache.store[key] = json.dumps({"per_subcap_narrative": [
            {"subcap_id": "P1C1.1.1", "narrative_md": "from-cache",
             "evidence_anchors": [], "confidence": 0.9},
        ]})
        vertex = _FakeVertexGood({"per_subcap_narrative": []})  # would fail
        result = asyncio.run(
            extract_per_subcap_narrative(
                pillar_id="P1", body_text="b",
                valid_subcap_ids=["P1C1.1.1"], run_id="r",
                vertex_client=vertex, cache=cache,
            )
        )
        # Vertex not invoked.
        assert vertex.call_count == 0
        assert result.state == "full_match"
        assert result.narratives[0].narrative_md == "from-cache"

    def test_cache_miss_writes_back(self) -> None:
        cache = _FakeCache()
        vertex = _FakeVertexGood({"per_subcap_narrative": [
            {"subcap_id": "P1C1.1.1", "narrative_md": "fresh",
             "evidence_anchors": [], "confidence": 0.9},
        ]})
        key = cache_key(pillar_id="P1", body_text="b", run_id="r")
        assert key not in cache.store
        _ = asyncio.run(
            extract_per_subcap_narrative(
                pillar_id="P1", body_text="b",
                valid_subcap_ids=["P1C1.1.1"], run_id="r",
                vertex_client=vertex, cache=cache,
            )
        )
        # Now cached.
        assert key in cache.store


# ---------------------------------------------------------------------
# section_routing integration — `build_narrative_heatmap` accepts overrides
# ---------------------------------------------------------------------


class TestBuildNarrativeHeatmapWithLLM:
    def test_llm_override_wins_over_paragraph_split(self) -> None:
        from app.services.section_routing import (
            SectionPayload,
            build_narrative_heatmap,
        )
        sec = SectionPayload(
            kind="pillar_deep_dive_p1",
            heading="P1 Deep Dive",
            body_md=(
                "Paragraph mentioning P1C1.1.1 and other context.\n\n"
                "Another paragraph mentioning P1C1.1.2."
            ),
            linked_subcap_ids=["P1C1.1.1", "P1C1.1.2"],
            linked_e_ids=[],
        )
        llm = {
            "P1C1.1.1": {
                "narrative_md": "LLM-curated narrative for P1C1.1.1",
                "evidence_anchors": ["E-1"],
                "confidence": 0.9,
                "data_source": "llm",
            },
        }
        out = build_narrative_heatmap([sec], llm_narratives=llm)
        assert out is not None
        # P1C1.1.1 → LLM (overrides paragraph split). The served value is
        # jargon-scrubbed, so the raw subcap code is stripped from the
        # narrative text while the dict KEY (the lookup id) is preserved.
        assert out["per_subcap_meta"]["P1C1.1.1"] == "llm"
        v1 = out["per_subcap_md"]["P1C1.1.1"]
        assert v1.startswith("LLM-curated narrative for")
        assert "P1C1.1.1" not in v1  # internal code scrubbed from display text
        # P1C1.1.2 → heuristic (LLM didn't cover it); code likewise scrubbed.
        assert out["per_subcap_meta"]["P1C1.1.2"] == "heuristic"
        v2 = out["per_subcap_md"]["P1C1.1.2"]
        assert "Another paragraph mentioning" in v2
        assert "P1C1.1.2" not in v2

    def test_no_llm_argument_unchanged_behavior(self) -> None:
        # Backward compat: omitting llm_narratives reproduces old shape.
        from app.services.section_routing import (
            SectionPayload,
            build_narrative_heatmap,
        )
        sec = SectionPayload(
            kind="pillar_deep_dive_p1",
            heading="P1",
            body_md="P1C1.1.1 paragraph",
            linked_subcap_ids=["P1C1.1.1"],
            linked_e_ids=[],
        )
        out = build_narrative_heatmap([sec])
        assert out is not None
        # Routing is unchanged (heuristic paragraph split); the served
        # narrative is jargon-scrubbed so the raw P#C# code no longer
        # appears in the display text, though the key is retained.
        assert "P1C1.1.1" in out["per_subcap_md"]  # key (lookup id) preserved
        assert out["per_subcap_md"]["P1C1.1.1"] == "paragraph"
        assert out["per_subcap_meta"]["P1C1.1.1"] == "heuristic"
