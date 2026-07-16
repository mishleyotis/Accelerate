"""A2 (2026-07-14 audit): V4 semantic grounding was documented but never
invoked. semantic_grounding_ok re-embeds the response vs the bundle centroid,
catching a fluent paraphrase that reuses no fabricated ids — and ABSTAINS when
no embedding tier is available (never a fail-closed on missing embeddings)."""
from __future__ import annotations

import numpy as np

from app.services import grounding_validator as gv
from app.services.nlp import semantic


def test_abstains_when_no_embedding_tier(monkeypatch):
    monkeypatch.setattr(semantic, "embed", lambda texts: None)
    ok, cos = gv.semantic_grounding_ok("anything", ["bundle a", "bundle b"])
    assert ok is True and cos is None          # abstain, never block


def test_abstains_on_empty_inputs():
    assert gv.semantic_grounding_ok("", ["x"]) == (True, None)
    assert gv.semantic_grounding_ok("x", []) == (True, None)


def test_grounded_response_passes(monkeypatch):
    # every vector aligned (response ∥ bundle centroid) → cosine 1.0
    monkeypatch.setattr(semantic, "embed",
                        lambda texts: np.array([[1.0, 0.0]] * len(texts), dtype=float))
    ok, cos = gv.semantic_grounding_ok("response", ["bundle x", "bundle y"])
    assert ok is True
    assert cos is not None and cos >= gv.V4_COSINE_FLOOR


def test_ungrounded_paraphrase_is_rejected(monkeypatch):
    # response orthogonal to the bundle centroid → cosine 0 < floor
    def fake_embed(texts):
        out = []
        for t in texts:
            out.append([0.0, 1.0] if "response" in t else [1.0, 0.0])
        return np.array(out, dtype=float)
    monkeypatch.setattr(semantic, "embed", fake_embed)
    ok, cos = gv.semantic_grounding_ok("response", ["bundle x", "bundle y"])
    assert ok is False
    assert cos is not None and cos < gv.V4_COSINE_FLOOR


def test_never_raises_on_embed_error(monkeypatch):
    def boom(texts):
        raise RuntimeError("tier blew up")
    monkeypatch.setattr(semantic, "embed", boom)
    ok, cos = gv.semantic_grounding_ok("response", ["bundle x"])
    assert ok is True and cos is None          # swallow → abstain
