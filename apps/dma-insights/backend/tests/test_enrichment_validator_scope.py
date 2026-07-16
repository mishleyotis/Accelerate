"""Enrichment-sweep validator scope (2026-07-06 fix).

The live sweep logged validator_blocked=219 of 273 Vertex calls. Root
cause: `enrich_corpus._allowed_e_ids` scoped the legal-citation set to the
`recent_evidence` / `gap_evidence` bundle ONLY, while the why_now /
platform_story prompts ALSO embed the run's why-now signals and SCQA
situation — both full of REAL, DB-derived inline E-ID citations for the
same entity. Gemini naturally cited those ids; the validator flagged them
as fabricated and fail-closed ~80% of otherwise-grounded outputs.

The fix widens the allowed set to every E-ID the rendered prompt context
carries (all ctx fields). The anti-hallucination property is unchanged and
pinned here: an id the model was never shown anywhere still blocks.
"""
from __future__ import annotations

from app.scripts.enrich_corpus import _E_ID_RE, _allowed_e_ids


def _why_now_ctx() -> dict:
    """A realistic why_now prompt context: the evidence bundle carries two
    ids; the signals + SCQA carry three MORE real inline citations."""
    return {
        "entity_name": "Interactive Brokers Group",
        "overall_score": "2.1",
        "scqa_situation": ("The deepest capability gap is Data Foundation at "
                           "1.9/5 against a 2.8 peer median [E-141]."),
        "why_now_signals": ("MIGRATION: The core conversion closes Q3 2027 "
                            "[E-055, E-060]; GAP: Digital Marketing Strategy "
                            "runs 1.4/5 vs a 3.2 median."),
        "recent_evidence": ("- E-001 (T2, 3mo, 10-K): three production cores\n"
                            "- E-002 (T3, 5mo, careers page): data engineers"),
    }


def test_allowed_ids_cover_the_whole_prompt_context() -> None:
    allowed = _allowed_e_ids(_why_now_ctx())
    # bundle ids AND the signal/SCQA inline citations are all legal
    assert allowed == {"E-001", "E-002", "E-055", "E-060", "E-141"}


def test_signal_cited_output_is_no_longer_a_false_positive() -> None:
    # The exact production failure shape: Gemini cites an id it saw in the
    # why-now signals blob, not in the recent-evidence bundle.
    out_text = ("The core conversion closes Q3 2027 [E-055], while digital "
                "maturity averages 2.1/5 [E-001] — the window to shape the "
                "integration layer is open now.")
    cited = sorted(set(_E_ID_RE.findall(out_text)))
    fabricated = [e for e in cited if e not in _allowed_e_ids(_why_now_ctx())]
    assert fabricated == []


def test_genuinely_fabricated_ids_still_block() -> None:
    # An id shown NOWHERE in the prompt is still fabricated — the
    # anti-hallucination gate is not weakened.
    out_text = "Peers already migrated [E-999]."
    cited = sorted(set(_E_ID_RE.findall(out_text)))
    fabricated = [e for e in cited if e not in _allowed_e_ids(_why_now_ctx())]
    assert fabricated == ["E-999"]


def test_empty_and_none_fields_are_tolerated() -> None:
    assert _allowed_e_ids({"recent_evidence": None, "x": ""}) == set()
