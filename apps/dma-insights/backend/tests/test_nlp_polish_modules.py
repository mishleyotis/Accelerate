"""Tests for the retrieval/composition polish modules: BM25 hybrid recall,
MMR diversity, corpus-IDF distinctiveness, and the cross-process embedding
disk cache."""
from __future__ import annotations

import pytest

from app.services.nlp import distinctiveness as dist
from app.services.nlp.bm25 import BM25Index

# ── BM25 ────────────────────────────────────────────────────────────────

def test_bm25_exact_term_beats_paraphrase() -> None:
    idx = BM25Index()
    idx.fit([
        ("ncino", "nCino commercial onboarding rollout completed in Q2"),
        ("para", "digital account opening experience improved this year"),
        ("noise", "quarterly dividend declared by the board of directors"),
    ])
    hits = idx.top_k("nCino onboarding", k=3)
    assert hits and hits[0][0] == "ncino"
    assert hits[0][1] == 1.0                      # normalized by top hit
    assert all(0.0 < s <= 1.0 for _, s in hits)


def test_bm25_empty_and_missing_terms() -> None:
    idx = BM25Index()
    assert idx.top_k("anything", 3) == []          # unfitted
    idx.fit([("a", "alpha beta"), ("b", "gamma delta")])
    assert idx.top_k("zzz unseen", 3) == []        # no posting → no hits
    assert idx.top_k("", 3) == []


def test_bm25_idf_downweights_ubiquitous_terms() -> None:
    idx = BM25Index()
    idx.fit([
        ("a", "bank services bank clients with bank products"),
        ("b", "bank launches Zelle instant payments"),
        ("c", "bank opens new branch downtown"),
    ])
    hits = idx.top_k("bank Zelle", k=3)
    assert hits[0][0] == "b"                       # rare term dominates


# ── distinctiveness ─────────────────────────────────────────────────────

def test_distinctiveness_prefers_client_specifics() -> None:
    dist.fit_corpus([
        "the bank continues to invest in digital capabilities",
        "we will invest in digital transformation for our customers",
        "digital capabilities remain a strategic priority",
        "Zelle volume grew 41% to 12.3M transactions at Coastal FCU",
    ])
    try:
        generic = dist.distinctiveness(
            "the bank continues to invest in digital capabilities")
        specific = dist.distinctiveness(
            "Zelle volume grew 41% to 12.3M transactions at Coastal FCU")
        assert specific > generic
        assert 0.0 <= generic <= 1.0 and 0.0 <= specific <= 1.0
    finally:
        dist.reset()


def test_distinctiveness_unfitted_is_neutral_zero() -> None:
    dist.reset()
    assert dist.distinctiveness("anything at all, even 42% specific") == 0.0


def test_distinctiveness_refit_replaces_table() -> None:
    try:
        assert dist.fit_corpus(["alpha beta gamma"]) == 1
        assert dist.fit_corpus(["one two three", "four five six"]) == 2
    finally:
        dist.reset()


# ── MMR diversity in EntityKnowledge ────────────────────────────────────

def _mk_knowledge(texts: dict[str, str]):
    from app.services.nlp.knowledge import EntityKnowledge, Evidence
    return EntityKnowledge(
        [Evidence(e_id=k, text=v, tier=2, owned=True)
         for k, v in texts.items()])



@pytest.fixture()
def warm_semantic(monkeypatch):
    """Re-probe the REAL semantic tier. Four suite modules set
    DMA_DISABLE_SEMANTIC=1 at IMPORT time, which pytest collection makes
    process-global — so these tests read the tier as cold inside a fully
    warm image and the live-pg no-skips gate fails (2026-07-13 diagnosis:
    the fc6e5dd image loads MiniLM fine in a fresh process). Clear the
    leak and reset the module memo before probing."""
    from app.services.nlp import semantic as sem
    monkeypatch.delenv("DMA_DISABLE_SEMANTIC", raising=False)
    monkeypatch.setattr(sem, "_MODEL_TRIED", False)
    monkeypatch.setattr(sem, "_MODEL", None)
    monkeypatch.setattr(sem, "_LAST_ATTEMPT_MONO", None)
    monkeypatch.setattr(sem, "_ATTEMPTS", 0)
    return sem


def test_mmr_displaces_near_duplicates(warm_semantic) -> None:
    if not warm_semantic.model_available():
        pytest.skip("semantic tier cold — MMR is identity on lexical fallback")
    kn = _mk_knowledge({
        "d1": "The credit union launched Zelle instant payments in 2025.",
        "d2": "Zelle instant payments launched at the credit union in 2025.",
        "d3": "The credit union also modernized its lending origination stack.",
    })
    ranked = [("d1", 0.9), ("d2", 0.88), ("d3", 0.55)]
    out = kn._mmr(ranked, k=2)
    assert out[0][0] == "d1"
    assert out[1][0] == "d3", "the near-duplicate must be displaced by breadth"


def test_mmr_identity_on_tiny_lists() -> None:
    kn = _mk_knowledge({"d1": "alpha", "d2": "beta"})
    ranked = [("d1", 0.9), ("d2", 0.8)]
    assert kn._mmr(ranked, k=2) == ranked


def test_hybrid_recall_surfaces_exact_name_material() -> None:
    """A rare exact token present in evidence must be retrievable even when
    the paraphrase tier under-ranks it."""
    kn = _mk_knowledge({
        "exact": "The board approved the nCino rollout for commercial lending.",
        "fluffy": "Digital account opening improved onboarding this year.",
        "noise": "The annual charity golf tournament raised record funds.",
    })
    hits = kn.supporting_evidence("nCino commercial lending rollout",
                                  k=2, min_score=0.2)
    assert any(eid == "exact" for eid, _ in hits)


# ── embedding disk cache ────────────────────────────────────────────────

def test_disk_cache_roundtrip(tmp_path, monkeypatch, warm_semantic) -> None:
    sem = warm_semantic
    if not sem.model_available():
        pytest.skip("semantic tier cold")
    monkeypatch.setenv("DMA_EMB_CACHE", str(tmp_path / "emb.sqlite"))
    # reset module cache state so the env var takes effect
    monkeypatch.setattr(sem, "_DISK_TRIED", False)
    monkeypatch.setattr(sem, "_DISK_CONN", None)
    monkeypatch.setattr(sem, "_EMB_CACHE", {})
    idx = sem.SemanticIndex()
    idx.fit([("a", "deposit growth strategy for the credit union")])
    # second process simulation: wipe the in-memory cache, keep the disk
    monkeypatch.setattr(sem, "_EMB_CACHE", {})
    idx2 = sem.SemanticIndex()
    idx2.fit([("a", "deposit growth strategy for the credit union")])
    hits = idx2.top_k("growing deposits", k=1, min_score=0.0)
    assert hits and hits[0][0] == "a"
    v1, v2 = idx.vector("a"), idx2.vector("a")
    # float16 storage round-trip stays within cosine tolerance (pure-Python
    # dot avoids a numpy test-import the infra gate would flag as undeclared)
    dot = sum(float(a) * float(b) for a, b in zip(v1, v2, strict=False))
    assert dot > 0.999


def test_disk_cache_disabled_by_empty_env(tmp_path, monkeypatch) -> None:
    from app.services.nlp import semantic as sem
    monkeypatch.setenv("DMA_EMB_CACHE", "")
    monkeypatch.setattr(sem, "_DISK_TRIED", False)
    monkeypatch.setattr(sem, "_DISK_CONN", None)
    assert sem._disk_cache() is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
