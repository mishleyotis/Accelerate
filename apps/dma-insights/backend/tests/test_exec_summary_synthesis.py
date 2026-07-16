"""Exec-summary reasoning-layer fix (2026-07-15).

Two regressions the operator caught in the shipped corpus:
  1. the summaries ENUMERATE evidence ("a second reading… one reading straight
     from the evidence: [fact] [E-047]") and pad citations with a hollow
     sentence ("the assessment's evidence base reads the same way [E-003]")
     instead of SYNTHESIZING evidence into an argument;
  2. the Vertex LLM "reasoning" composer (which DOES synthesize) was discarded
     by ``deepen_narrative._scqa_ok`` because a focused, woven narrative failed
     the >=4-source-family floor + the score-echo rubric — floors the
     enumerating template satisfies by construction. So the template shipped.

These tests pin the fix: a synthesized narrative clears the RELAXED gate
criteria, and the deterministic fallback no longer emits the hollow
citation-floor sentence or double-bracket citations.
"""
from __future__ import annotations

from app.services.nlp.quality import rubric_score
from app.services.startup_enrich import compose_scqa_deep, scqa_family_count

# A synthesized, story-first narrative like the Vertex reasoning layer emits:
# ONE maturity anchor, standing described in words, evidence woven into cause
# and effect, two RELEVANT ids — exactly what the old gate rejected.
_SYNTHESIZED = (
    "American Airlines Federal Credit Union runs ahead of comparable "
    "institutions on vendor oversight, yet the capability that decides its "
    "next chapter — competitive analysis — sits well behind the peer line "
    "[E-050]. With the Wings and Ent merger closing in 2028, that gap "
    "compounds: without a standing read on rival pricing and launches, the "
    "combined book will move blind [E-016]. The question is whether to bolt on "
    "point tools or build the muscle once. Leading with Financial Services "
    "Cloud, sequenced ahead of MuleSoft, gives that read a home and lets the "
    "merger integration ride the same backbone."
)


def test_synthesized_narrative_clears_relaxed_gate():
    # >=2 real ids (grounding floor kept)
    import re
    ids = set(re.findall(r"E-\d+", _SYNTHESIZED))
    assert len(ids) >= 2
    # the OLD floor (>=4 families) would have REJECTED this focused narrative…
    fams = scqa_family_count(_SYNTHESIZED)
    assert fams < 4          # documents the old-gate failure mode
    # …the RELAXED floor (>=2) admits it
    assert fams >= 2
    # score-echo relaxation: passes without being forced to recite a score
    v = rubric_score(_SYNTHESIZED, evidence_ids=ids, numbers_in_scope=(),
                     enforce_score_echo=False)
    assert v["pass"] is True


def _bundle():
    return {
        "client_key": "aafcu-0001",
        "name": "American Airlines Federal Credit Union", "overall": 2.4,
        "gaps": [
            {"name": "Competitive Analysis", "score": 1.0, "peer": 3.0,
             "eids": ["E-050"], "excerpt": "Competitor benchmarking is ad hoc; "
             "no standing process tracks rival launches or pricing moves."},
            {"name": "BaaS API Management", "score": 1.0, "peer": 2.8,
             "eids": ["E-132", "E-127"]},
        ],
        "strength": {"name": "Vendor Due Diligence", "score": 3.5, "peer": 2.5},
        "strengths": [{"name": "Vendor Due Diligence", "score": 3.5, "peer": 2.5}],
        "issues": [],
        "extra_facts": [{"fact": "Wings ($9.6B) + Ent ($10B, 580K members) merger "
                         "announced Apr 2025; full systems integration by 2028",
                         "eids": ["E-016"]}],
        "leadership": {"new_hires": [], "gap_roles": [], "n": 3},
        "platforms": [
            {"name": "Financial Services Cloud", "recommended": True, "fit": 58.0,
             "integration_effort": "MEDIUM", "top_subcap": "Competitive Analysis",
             "lens": None, "incumbent": None, "seq_after": [], "gate": None},
            {"name": "MuleSoft", "recommended": True, "fit": None,
             "integration_effort": None, "top_subcap": None, "lens": None,
             "incumbent": None, "seq_after": [], "gate": None},
        ],
        "base_eids": ["E-002", "E-016", "E-050", "E-132"],
    }


def test_deterministic_fallback_no_hollow_dump_or_broken_cite():
    md = compose_scqa_deep(_bundle())["md"]
    # the hollow citation-floor sentence is gone
    for hollow in ("reads the same way", "corroborated across the assessment",
                   "One reading straight from the evidence",
                   "underlying evidence index points to the same pattern"):
        assert hollow not in md, f"hollow evidence-dump still present: {hollow!r}"
    # no double-bracket citation debris
    assert "[[" not in md
    # not a score recap: at most two maturity-score recitals
    import re
    assert len(re.findall(r"\b\d(?:\.\d)?\s*/\s*5\b", md)) <= 2
    # still grounded + multi-paragraph
    assert len([p for p in md.split("\n\n") if p.strip()]) >= 2
    assert scqa_family_count(md) >= 2


def test_extra_fact_is_woven_not_stapled():
    md = compose_scqa_deep(_bundle())["md"]
    # the merger fact appears connected to the argument (a dash-joined clause),
    # never as a bare "here is a fact" announcement
    assert "merger" in md.lower()
    assert "One reading straight from the evidence" not in md
