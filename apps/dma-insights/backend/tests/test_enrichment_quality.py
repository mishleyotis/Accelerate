"""The enrichment quality gate (services/enrichment_quality): consultant-grade
language (no accusatory tone), text cleanup, and contradiction surfacing — so a
stored enrichment reads like consultant prose and a conflict with the corpus is
brought out, never brushed under the rug.
"""
from __future__ import annotations

from app.services.enrichment_quality import (
    contradiction,
    soften_tone,
    tone_flags,
    vet_text,
)


def test_accusatory_tone_is_flagged_and_softened() -> None:
    raw = ("The bank's failure to modernize and its poor, lagging data platform "
           "reflect negligent governance.")
    flags = tone_flags(raw)
    assert "failure" in flags and "poor" in flags and "lagging" in flags
    out = soften_tone(raw)
    for bad in ("failure", "poor", "lagging", "negligent"):
        assert bad not in out.lower()
    # the fact survives, reframed as gaps/opportunities
    assert "gaps" in out and "data platform" in out


def test_vet_text_cleans_annotation_and_returns_flags() -> None:
    raw = "[ERS: 4.6] [E-021:F1] Poor mobile adoption (T2, CURRENT): a real gap."
    cleaned, flags = vet_text(raw)
    assert "[ERS" not in cleaned and "(T2, CURRENT)" not in cleaned
    assert "limited mobile adoption" in cleaned.lower()   # "poor" -> "limited"
    assert "poor" in flags


def test_vet_text_leaves_clean_neutral_prose_untouched() -> None:
    raw = "Manual underwriting adds 9 days to loan decisions; automation is the play"
    cleaned, flags = vet_text(raw)
    # no tone flags, content preserved (clean_finding_text may trim trailing punct)
    assert flags == []
    assert cleaned.startswith("Manual underwriting adds 9 days")
    assert "automation is the play" in cleaned


def test_contradiction_surfaces_numeric_conflict() -> None:
    # enriched headcount 1,200 vs a corpus value of 325 → surfaced
    note = contradiction("1,200 employees", "325 employees")
    assert note and "CONTRADICTION" in note
    # within tolerance → no note
    assert contradiction("330 employees", "325 employees") is None
    # $ magnitudes
    assert contradiction("$4.3B", "$2.5B") is not None
    assert contradiction("$2.55B", "$2.5B") is None


def test_contradiction_handles_text_and_empties() -> None:
    assert contradiction("Poughkeepsie, NY", "Reno, NV") is not None
    assert contradiction("Poughkeepsie, NY", "Poughkeepsie") is None   # one contains other
    assert contradiction("", "325") is None                            # nothing to compare
    assert contradiction("325", "") is None
