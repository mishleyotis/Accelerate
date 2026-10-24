"""rank.rank_chunks: BM25 stage, abstain, exact offsets, dense skipped offline."""
from __future__ import annotations

import hashlib

from evidence_engine import rank
from evidence_engine.config import reset_settings
from evidence_engine.types import Document

ON_TOPIC = (
    "Example Federal Credit Union launched digital onboarding with identity verification in March. "
    "New members can open an account from a phone in minutes. The credit union said adoption "
    "exceeded its first-quarter target.\n\n"
    "The branch network remains at fourteen locations. Hours are unchanged for the summer. "
    "Members may still visit a branch to open an account."
)
OFF_TOPIC = (
    "The county fair opens Friday with livestock judging and a pie contest. Parking is free "
    "after six. The mascot will greet visitors at the gate. Weather is expected to be fair."
)


def _doc(url, text):
    return Document(url=url, final_url=url, text=text, verify_text=text,
                    content_hash="sha256:" + hashlib.sha256(text.encode()).hexdigest())


DOCS = [_doc("https://springfield-daily.test/fair", OFF_TOPIC), _doc("https://www.cutimes.com/2026/03/04/example/", ON_TOPIC)]
QUESTION = "digital onboarding identity verification new members open an account"


def test_question_terms_outrank_and_offsets_are_exact():
    out = rank.rank_chunks(QUESTION, DOCS, top_k=5)
    assert out["rerank"] == "bm25-only"
    assert out["ranked"], out
    top = out["ranked"][0]
    assert top["url_key"] == "cutimes.com/2026/03/04/example"
    assert "digital onboarding" in top["text"]
    assert top["stages"]["bm25_norm"] == 1.0 and top["score"] == 1.0
    for c in out["ranked"] + out["below_floor"]:
        doc = next(d for d in DOCS if rank.url_key(d.url) == c["url_key"])
        assert doc.text[c["chunk_start"]:c["chunk_end"]] == c["text"]
        assert set(c["stages"]) == {"bm25", "bm25_norm"}


def test_abstain_path():
    out = rank.rank_chunks(QUESTION, DOCS, top_k=5)
    below = out["below_floor"]
    assert any(c["url_key"] == "springfield-daily.test/fair" for c in below)
    assert all(c["url_key"] != "springfield-daily.test/fair" for c in out["ranked"])
    assert all(c["score"] < rank.FLOOR or c["stages"]["bm25"] == 0 for c in below)
    assert out["floor"] == 0.05


def test_chunks_are_three_sentence_windows_with_exact_offsets():
    doc = DOCS[1]
    chunks = rank.chunks_of(doc)
    assert len(chunks) == 2
    assert chunks[0]["text"].startswith("Example Federal Credit Union launched")
    assert chunks[1]["text"].startswith("The branch network")
    assert all(doc.text[c["chunk_start"]:c["chunk_end"]] == c["text"] for c in chunks)


def test_dense_skipped_cleanly_without_models(monkeypatch):
    monkeypatch.setenv("EE_MODELS_DIR", "")
    reset_settings()
    usable, reason = rank.dense_available()
    assert not usable and "EE_MODELS_DIR" in reason
    out = rank.rank_chunks(QUESTION, DOCS, top_k=3)
    assert out["rerank"] == "bm25-only" and out["rerank_reason"] == reason


def test_dense_skipped_when_models_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("EE_MODELS_DIR", str(tmp_path / "no-such-models"))
    reset_settings()
    usable, reason = rank.dense_available()
    assert not usable and "does not exist" in reason
    out = rank.rank_chunks(QUESTION, DOCS, top_k=3)
    assert out["rerank"] == "bm25-only"


def test_models_dir_present_but_empty_falls_back_without_download(monkeypatch, tmp_path):
    """The directory exists but holds no model: the loader must fail offline
    and the ranker must report bm25-only rather than download anything."""
    d = tmp_path / "models"
    d.mkdir()
    monkeypatch.setenv("EE_MODELS_DIR", str(d))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    reset_settings()
    monkeypatch.setattr(rank, "_dense_scores", lambda q, t: None)   # never reach the network in CI
    out = rank.rank_chunks(QUESTION, DOCS, top_k=3)
    assert out["rerank"] == "bm25-only" and "not loadable" in out["rerank_reason"]


def test_dense_path_combines_when_scores_are_available(monkeypatch, tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    monkeypatch.setenv("EE_MODELS_DIR", str(d))
    reset_settings()
    monkeypatch.setattr(rank, "_dense_scores", lambda q, texts: [float(i) for i in range(len(texts))][::-1])
    out = rank.rank_chunks(QUESTION, DOCS, top_k=3)
    assert out["rerank"] == "dense+cross-encoder"
    top = out["ranked"][0]
    assert set(top["stages"]) == {"bm25", "bm25_norm", "rerank", "rerank_norm"}
    assert abs(top["score"] - (0.5 * top["stages"]["bm25_norm"] + 0.5 * top["stages"]["rerank_norm"])) < 1e-3


def test_deterministic_and_empty():
    a = rank.rank_chunks(QUESTION, DOCS, top_k=5)
    b = rank.rank_chunks(QUESTION, list(reversed(DOCS)), top_k=5)
    assert [(c["url_key"], c["chunk_start"]) for c in a["ranked"]] == [(c["url_key"], c["chunk_start"]) for c in b["ranked"]]
    assert rank.rank_chunks(QUESTION, [], top_k=5)["ranked"] == []
