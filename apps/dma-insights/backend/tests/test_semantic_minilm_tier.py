"""Gold-standard MiniLM semantic tier — exercised LIVE (not the lexical
fallback that test_semantic_alignment.py pins for determinism).

The shipped backend + worker images bake the all-MiniLM-L6-v2 weights
(Dockerfiles → DMA_ST_MODEL_DIR), so these run there; in a bare dev venv
without the baked model they skip (the ONLY environment where the tier
legitimately isn't present — CI/prod always have it, so no skip fires in
backend-tests-live-pg or qa-gates).

Contract: the semantic tier fixes the lexical misattribution TF-IDF cannot.
A privacy notice and the real underwriting evidence share the word
"member"; TF-IDF is fooled by that overlap, MiniLM binds by MEANING.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture()
def sem():
    """Enable the semantic tier for this test and reset the lazy singleton.

    A sibling module (test_semantic_alignment) sets DMA_DISABLE_SEMANTIC=1
    process-wide for determinism; undo it here and clear the cached model so
    the real MiniLM weights load fresh, then restore on teardown.
    """
    prev = os.environ.pop("DMA_DISABLE_SEMANTIC", None)
    import app.services.nlp.semantic as _sem
    _sem._reset_load_state()
    try:
        yield _sem
    finally:
        _sem._reset_load_state()
        if prev is not None:
            os.environ["DMA_DISABLE_SEMANTIC"] = prev


def test_minilm_is_baked_and_selected(sem) -> None:
    if not sem.model_available():
        pytest.skip("all-MiniLM-L6-v2 not baked (bare dev venv; the image bakes it)")
    # with the model present, preferred_index() must return the MiniLM tier,
    # not the lexical fallback.
    assert type(sem.preferred_index()).__name__ == "SemanticIndex"


def test_minilm_binds_evidence_by_meaning_not_word_overlap(sem) -> None:
    if not sem.model_available():
        pytest.skip("all-MiniLM-L6-v2 not baked (bare dev venv; the image bakes it)")
    from app.services.nlp.similarity import LexicalIndex

    cands = [
        ("underwriting", "Loan officers hand-key underwriting decisions; approvals take 9 days."),
        ("privacy", "Privacy notice: collects member personal info via email and chat."),
        ("balance", "Total assets reached $2.5 billion at fiscal year end."),
    ]
    query = "Streamline slow, staff-driven credit approvals to speed member lending."

    idx = sem.SemanticIndex()
    idx.fit(list(cands))
    ranked = idx.top_k(query, k=3, min_score=0.0)
    scores = dict(ranked)
    # semantic binds to the real underwriting evidence…
    assert ranked[0][0] == "underwriting", f"semantic top was {ranked[0][0]}"
    # …with a clear margin over the word-overlap decoy ("member" in privacy).
    assert scores["underwriting"] > scores["privacy"]

    # the guard has teeth: the LEXICAL tier is fooled by the shared word
    # "member" into ranking the privacy notice above the real evidence —
    # this is exactly the misattribution the MiniLM tier exists to fix.
    lex = LexicalIndex()
    lex.fit(list(cands))
    lex_ranked = lex.top_k(query, k=3, min_score=0.0)
    assert lex_ranked, "lexical index returned nothing"
    assert lex_ranked[0][0] == "privacy", (
        "expected the lexical tier to be fooled by 'member' overlap; "
        f"got {lex_ranked[0][0]} — if the fixtures changed, re-verify the contrast"
    )
