"""Tests for the pure embedder service — text recipes, candidate
selection, batching, vector validation, and result stitching.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Workers package is one level up from the backend root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.embedder.service import (  # noqa: E402
    EmbedCandidate,
    batchify,
    build_embed_text,
    build_evidence_text,
    build_insight_text,
    build_recommendation_text,
    coalesce_batches_by_kind,
    is_valid_vector,
    select_candidates,
    stitch_batch_result,
    stitch_mixed_batch,
)


class TestTextRecipes:
    def test_evidence_text(self) -> None:
        t = build_evidence_text(
            source_name="2024 Annual Report",
            claim_type="strategic_signal",
            excerpt="AUM grew 8% YoY",
        )
        assert t == "2024 Annual Report · strategic_signal · AUM grew 8% YoY"

    def test_insight_text_filters_empties(self) -> None:
        t = build_insight_text(
            title="Paper-driven",
            what_text="Mostly PDF intake",
            why_text="",
            so_what_text="Member experience suffers",
        )
        assert t == "Paper-driven · Mostly PDF intake · Member experience suffers"

    def test_recommendation_text(self) -> None:
        t = build_recommendation_text(
            title="Adopt nCino",
            description="Replaces 14 manual steps.",
        )
        assert t == "Adopt nCino · Replaces 14 manual steps."

    def test_dispatch_evidence(self) -> None:
        assert "annual" in build_embed_text("evidence", {
            "source_name": "annual",
            "claim_type": "x",
            "excerpt": "y",
        }).lower()

    def test_dispatch_unknown_raises(self) -> None:
        with pytest.raises(ValueError):
            build_embed_text("not_a_kind", {})  # type: ignore[arg-type]

    def test_dispatch_section(self) -> None:
        t = build_embed_text("section", {
            "section_kind": "pillar_deep_dive_p1",
            "heading": "Strategic Posture",
            "body": "Findings show strong governance.",
        })
        assert "pillar_deep_dive_p1" in t
        assert "Strategic Posture" in t
        assert "Findings show strong governance" in t

    def test_section_body_capped_at_6k(self) -> None:
        from workers.embedder.service import build_section_text
        long_body = "x" * 10000
        t = build_section_text(
            section_kind="x", heading="h", body=long_body,
        )
        # 6000 body + small prefix
        assert len(t) <= 6100


class TestSelectCandidates:
    def test_filters_already_embedded(self) -> None:
        artifacts = [
            {"id": "11111111-1111-1111-1111-111111111111", "title": "T1",
             "what_text": "w", "why_text": "w", "so_what_text": "s"},
            {"id": "22222222-2222-2222-2222-222222222222", "title": "T2",
             "what_text": "w", "why_text": "w", "so_what_text": "s"},
            {"id": "33333333-3333-3333-3333-333333333333", "title": "T3",
             "what_text": "w", "why_text": "w", "so_what_text": "s"},
        ]
        existing = {"22222222-2222-2222-2222-222222222222"}
        out = select_candidates(
            artifacts=artifacts, existing_embedded_ids=existing, kind="insight",
        )
        ids = [c.id for c in out]
        assert "11111111-1111-1111-1111-111111111111" in ids
        assert "22222222-2222-2222-2222-222222222222" not in ids
        assert "33333333-3333-3333-3333-333333333333" in ids

    def test_skips_empty_text(self) -> None:
        artifacts = [
            {"id": "11111111-1111-1111-1111-111111111111", "source_name": "",
             "claim_type": "", "excerpt": ""},
            {"id": "22222222-2222-2222-2222-222222222222", "source_name": "ok",
             "claim_type": "x", "excerpt": "y"},
        ]
        out = select_candidates(
            artifacts=artifacts, existing_embedded_ids=set(), kind="evidence",
        )
        assert [c.id for c in out] == ["22222222-2222-2222-2222-222222222222"]

    def test_skips_artifacts_without_id(self) -> None:
        artifacts = [
            {"id": None, "title": "T", "what_text": "w", "why_text": "w", "so_what_text": "s"},
            {"id": "ok-id", "title": "T", "what_text": "w", "why_text": "w", "so_what_text": "s"},
        ]
        out = select_candidates(
            artifacts=artifacts, existing_embedded_ids=set(), kind="insight",
        )
        assert [c.id for c in out] == ["ok-id"]


class TestBatchify:
    def test_splits_into_chunks(self) -> None:
        cands = [
            EmbedCandidate(kind="evidence", id=str(i), text=f"t{i}")
            for i in range(10)
        ]
        batches = batchify(cands, batch_size=3)
        assert [len(b) for b in batches] == [3, 3, 3, 1]
        # IDs preserved in order
        flat = [c.id for batch in batches for c in batch]
        assert flat == [str(i) for i in range(10)]

    def test_empty_input(self) -> None:
        assert batchify([], batch_size=4) == []

    def test_batch_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            batchify([], batch_size=0)


class TestCoalesceByKind:
    def test_groups_separately(self) -> None:
        cands = [
            EmbedCandidate(kind="evidence", id="e1", text="t"),
            EmbedCandidate(kind="insight", id="i1", text="t"),
            EmbedCandidate(kind="recommendation", id="r1", text="t"),
            EmbedCandidate(kind="evidence", id="e2", text="t"),
        ]
        out = coalesce_batches_by_kind(cands)
        assert [c.id for c in out["evidence"]] == ["e1", "e2"]
        assert [c.id for c in out["insight"]] == ["i1"]
        assert [c.id for c in out["recommendation"]] == ["r1"]

    def test_section_kind_has_a_bucket(self) -> None:
        """Regression: 'section' was missing from the coalesce dict — a
        latent KeyError the moment a section candidate arrived (the
        embedder DOES emit section candidates via build_section_text)."""
        cands = [
            EmbedCandidate(kind="section", id="s1", text="t"),
            EmbedCandidate(kind="evidence", id="e1", text="t"),
            EmbedCandidate(kind="section", id="s2", text="t"),
        ]
        out = coalesce_batches_by_kind(cands)
        assert [c.id for c in out["section"]] == ["s1", "s2"]
        assert [c.id for c in out["evidence"]] == ["e1"]

    def test_every_artifact_kind_literal_has_a_bucket(self) -> None:
        """Pin the full-kind contract so a future ArtifactKind addition
        can't reintroduce the KeyError."""
        from typing import get_args

        from workers.embedder.service import ArtifactKind

        out = coalesce_batches_by_kind([])
        assert set(out.keys()) == set(get_args(ArtifactKind))


class TestIsValidVector:
    def test_correct_dim_passes(self) -> None:
        assert is_valid_vector([0.1] * 768) is True

    def test_wrong_dim_fails(self) -> None:
        assert is_valid_vector([0.1] * 512) is False

    def test_all_zero_fails(self) -> None:
        assert is_valid_vector([0.0] * 768) is False

    def test_nan_fails(self) -> None:
        bad = [0.1] * 768
        bad[0] = float("nan")
        assert is_valid_vector(bad) is False


class TestStitchBatchResult:
    def test_pairs_in_order(self) -> None:
        cands = [
            EmbedCandidate(kind="evidence", id="a", text="t1"),
            EmbedCandidate(kind="evidence", id="b", text="t2"),
        ]
        vectors = [[0.1] * 768, [0.2] * 768]
        out = stitch_batch_result(
            kind="evidence", candidates=cands, vectors=vectors,
            model_version="text-embedding-004",
        )
        assert out.ids == ["a", "b"]
        assert out.model_version == "text-embedding-004"
        assert len(out.vectors) == 2

    def test_drops_invalid_vectors(self) -> None:
        cands = [
            EmbedCandidate(kind="evidence", id="a", text="t1"),
            EmbedCandidate(kind="evidence", id="b", text="t2"),
            EmbedCandidate(kind="evidence", id="c", text="t3"),
        ]
        vectors = [
            [0.1] * 768,
            [0.0] * 768,  # all-zero → invalid
            [0.3] * 768,
        ]
        out = stitch_batch_result(
            kind="evidence", candidates=cands, vectors=vectors,
            model_version="text-embedding-004",
        )
        assert out.ids == ["a", "c"]

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            stitch_batch_result(
                kind="evidence",
                candidates=[EmbedCandidate(kind="evidence", id="a", text="t")],
                vectors=[[0.1] * 768, [0.2] * 768],
                model_version="x",
            )


class TestStitchMixedBatch:
    """live.embed_run batchifies ONE flat list spanning artifact kinds;
    persistence is per-kind. stitch_mixed_batch is the seam that groups a
    mixed batch back into per-kind EmbedBatchResults (the 2026-07-06
    `stitch_batch_result() got an unexpected keyword argument 'batch'`
    crash — every live embed run died at its first batch)."""

    @staticmethod
    def _cand(kind, cid, text="some text"):
        return EmbedCandidate(id=cid, kind=kind, text=text)

    def test_mixed_batch_groups_per_kind(self) -> None:
        batch = [
            self._cand("evidence", "e1"),
            self._cand("insight", "i1"),
            self._cand("evidence", "e2"),
            self._cand("recommendation", "r1"),
        ]
        vectors = [[float(n)] * 768 for n in (1, 2, 3, 4)]
        results = stitch_mixed_batch(
            batch=batch, vectors=vectors, model_version="mv-1")
        by_kind = {r.kind: r for r in results}
        assert set(by_kind) == {"evidence", "insight", "recommendation"}
        assert by_kind["evidence"].ids == ["e1", "e2"]
        assert by_kind["insight"].ids == ["i1"]
        assert by_kind["recommendation"].ids == ["r1"]
        # vectors follow their candidates
        assert by_kind["evidence"].vectors[1][0] == 3.0

    def test_single_kind_batch_is_one_result(self) -> None:
        batch = [self._cand("evidence", "e1"), self._cand("evidence", "e2")]
        vectors = [[1.0] * 768, [2.0] * 768]
        results = stitch_mixed_batch(
            batch=batch, vectors=vectors, model_version="mv-1")
        assert len(results) == 1 and results[0].kind == "evidence"
        assert results[0].ids == ["e1", "e2"]

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="length mismatch"):
            stitch_mixed_batch(
                batch=[self._cand("evidence", "e1")],
                vectors=[], model_version="mv-1")

    def test_invalid_vectors_still_skipped_per_kind(self) -> None:
        batch = [self._cand("evidence", "e1"), self._cand("insight", "i1")]
        vectors = [[0.0] * 768, [1.0] * 768]  # all-zero fails is_valid_vector
        results = stitch_mixed_batch(
            batch=batch, vectors=vectors, model_version="mv-1")
        by_kind = {r.kind: r for r in results}
        assert by_kind["evidence"].ids == []  # rejected vector skipped
        assert by_kind["insight"].ids == ["i1"]
