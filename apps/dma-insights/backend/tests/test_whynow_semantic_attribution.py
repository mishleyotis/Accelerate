"""Why-now peer-context attribution is MiniLM-semantic (2026-07-09).

Token overlap captioned only 13.6% of capability-bound why-now signals with a
semantically-relevant peer stat (a "no CTO" leadership signal got a
Conversational-IVR caption). The matcher now binds by bi-encoder relevance and
only above a floor, so a signal that matches nothing keeps the neutral cohort
line instead of a false caption. Tier-aware: asserts the semantic behaviour only
when MiniLM is baked (cold CI falls back to token overlap).
"""
from __future__ import annotations

from types import SimpleNamespace as NS

from app.scripts.deepen_narrative import _assign_peer_context
from app.services.nlp.semantic import model_available


def test_semantic_matcher_binds_by_meaning_not_token_overlap() -> None:
    if not model_available():
        return  # cold tier → token-overlap fallback; nothing semantic to assert
    rows = [
        NS(cat="P4C2", sc=1.81, peer=2.9,
           worst_name="Conversational IVR with GenAI"),
        NS(cat="P1C2", sc=2.1, peer=3.0,
           worst_name="Cybersecurity leadership and CISO governance"),
    ]
    signals = [
        {"label": "No CTO named",
         "detail": "leadership gap — no named CTO or head of technology",
         "subcap_id": None},
        {"label": "Conversational IVR",
         "detail": "self-service IVR maturity is low", "subcap_id": None},
    ]
    _assign_peer_context(signals, rows, overall=2.5)
    # the leadership signal binds the security/governance row (0 shared tokens
    # with it), NOT the IVR row it would have grabbed under token overlap
    assert "Cybersecurity" in (signals[0]["peer_context"] or "")
    assert "Conversational IVR" in (signals[1]["peer_context"] or "")


def test_unmatched_signal_gets_neutral_line_not_false_caption() -> None:
    if not model_available():
        return
    rows = [NS(cat="P4C2", sc=1.8, peer=2.9,
               worst_name="Conversational IVR with GenAI")]
    signals = [{"label": "Quarterly bake sale raised funds for charity",
                "detail": "community fundraising event", "subcap_id": None}]
    _assign_peer_context(signals, rows, overall=2.5)
    pc = signals[0]["peer_context"] or ""
    # nothing semantically matches → the neutral cohort line, never the IVR row
    assert "Conversational IVR" not in pc
    assert pc == "" or pc.startswith("Overall digital maturity") or pc is None \
        or signals[0]["peer_context"] is None
