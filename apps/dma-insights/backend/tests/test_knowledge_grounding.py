"""Shared knowledge + adversarial grounding (nlp/knowledge.py).

Asserted in the LEXICAL fallback tier (no torch) so the contract holds in the
shipped image; MiniLM only sharpens the margins.
"""
from __future__ import annotations

import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.nlp.knowledge import (
    Claim,
    EntityKnowledge,
    Evidence,
    _opposes,
    resolve_contradictions,
)

_EVIDENCE = [
    Evidence("E-lead", "Deployed Salesforce Marketing Cloud to accelerate lead routing and shorten speed to lead response for inquiries.", tier=2, year=2026, owned=True),
    Evidence("E-roster", "Executive Committee: Dan Wagner CEO, Kevin Geron CIO, Mark Hanna CRO, Chuck Millhollan COO.", tier=3, year=2026, owned=True),
    Evidence("E-peer", "Peer benchmark: FCSA reports a Net Promoter Score of 60, leader among Farm Credit peers.", tier=2, year=2025, owned=False),
]


def _k() -> EntityKnowledge:
    return EntityKnowledge(_EVIDENCE)


def test_challenge_keeps_aligned_drops_misattributed_and_peer_and_missing() -> None:
    k = _k()
    c = Claim(
        text="Speed to Lead is the binding gap; lead response is slow.",
        capability="Speed to Lead sales lead response routing",
        e_ids=["E-roster", "E-lead", "E-peer", "E-does-not-exist"],
    )
    k.challenge(c, min_support=0.15)
    assert c.e_ids == ["E-lead"], c.e_ids          # only the topically-aligned, owned, resolvable one
    assert c.verdict == "grounded"
    assert c.support > 0.15


def test_challenge_marks_ungrounded_when_no_aligned_evidence() -> None:
    k = _k()
    c = Claim(text="Speed to Lead gap", capability="Speed to Lead sales response",
              e_ids=["E-roster", "E-peer"])
    k.challenge(c, min_support=0.15)
    assert c.e_ids == []
    assert c.verdict == "ungrounded"


def test_supporting_evidence_is_ownership_checked_and_ranked() -> None:
    k = _k()
    hits = k.supporting_evidence("speed to lead response routing", k=3, min_score=0.10)
    ids = [e for e, _ in hits]
    assert "E-lead" in ids
    assert "E-peer" not in ids   # peer-owned excluded by the ownership fence


def test_resolve_contradictions_keeps_stronger_grounded_claim() -> None:
    ev = [
        Evidence("E-filled", "The CISO role is fully staffed under Tiffany Smith, a strong security leader.", tier=2, year=2026, owned=True),
        Evidence("E-gap", "The institution lacks a CISO; this critical security leadership seat is an unfilled gap.", tier=6, year=2024, owned=True),
    ]
    filled = Claim(text=ev[0].text, capability="CISO security leadership", e_ids=["E-filled"])
    gap = Claim(text=ev[1].text, capability="CISO security leadership", e_ids=["E-gap"])
    # sanity: presence-vs-absence is genuinely opposing
    assert _opposes(filled.text, gap.text)
    survivors, notes = resolve_contradictions([filled, gap], ev, sim_threshold=0.10)
    kept = {c.text for c in survivors}
    assert ev[0].text in kept and ev[1].text not in kept   # higher-tier 'filled' wins
    assert notes
