"""Gold-standard semantic tier — topical evidence↔capability alignment.

The engine must (a) rank genuinely-supporting evidence above off-topic evidence,
and (b) score misattributed evidence (exec roster / privacy notice under a
sales-response capability) near zero — the misattribution guard the narrative
composers rely on. Asserted in the LEXICAL fallback tier (no torch) so the
contract holds in the shipped image; the MiniLM tier only sharpens the margin.
"""
from __future__ import annotations

import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")  # force the fallback tier for CI determinism

from app.services.nlp.semantic import SemanticIndex, preferred_index

_CAP = "Speed to Lead — sales lead response time and routing"
_CANDS = [
    ("roster", "Executive Committee: Dan Wagner CEO, Kevin Geron CIO, Mark Hanna CRO, Chuck Millhollan COO."),
    ("privacy", "Privacy notice updated Jan 2026 — collects personal info via communications email text chat."),
    ("relevant", "Deployed Salesforce Marketing Cloud to accelerate lead routing and shorten speed-to-lead response for inquiries."),
    ("offtopic", "Allowance for credit losses increased 38% year over year; adversely classified loans rose."),
]


def test_relevant_evidence_outranks_misattributed() -> None:
    idx = preferred_index()
    idx.fit(list(enumerate(t for _, t in _CANDS)))
    ranked = idx.top_k(_CAP, k=4, min_score=0.0)
    assert ranked, "index returned no ranking"
    top_label = _CANDS[ranked[0][0]][0]
    assert top_label == "relevant", f"expected 'relevant' first, got {top_label}"
    scores = {_CANDS[i][0]: s for i, s in ranked}
    # the misattributed roster/privacy must sit well below the real evidence
    assert scores["relevant"] > scores.get("roster", 0.0)
    assert scores["relevant"] > scores.get("privacy", 0.0)


def test_relevance_guard_rejects_offtopic() -> None:
    idx = preferred_index()
    rel = idx.relevance(_CAP, _CANDS[2][1])       # relevant
    roster = idx.relevance(_CAP, _CANDS[0][1])     # misattributed
    assert rel > roster
    assert roster < 0.15, f"roster should be near-zero relevance, got {roster}"


def test_empty_and_degenerate_inputs_never_raise() -> None:
    idx = SemanticIndex()
    idx.fit([])
    assert idx.top_k("anything", 3) == []
    assert idx.relevance("", "x") == 0.0
    assert idx.relevance("x", "") == 0.0
