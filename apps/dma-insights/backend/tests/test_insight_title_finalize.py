"""Insight-card title finalizer (derive_insights._finalize_card_title).

The 2026-07-09 deep-QA challenge over the 94-client corpus found three
AE-worthiness title defects that reached the persisted cards because the
card-persist chokepoint passed `title` RAW: a bare [E-id] citation marker in
the title (14 cards), a scaffolding "Capability dimension N" (1), and the
title==body case where the "title" was just the leading (mid-word-truncated)
run of the WHAT (110). These pin the fix at that chokepoint.
"""
from __future__ import annotations

from app.scripts.derive_insights import _finalize_card_title


def test_strips_evidence_marker_from_title() -> None:
    out = _finalize_card_title(
        "Acuity runs IBM AIX on-premises as its core system [E-089]",
        "Acuity runs IBM AIX on-premises as its core system, with Salesforce CRM.")
    assert "[E-089]" not in out and "[E-" not in out
    assert out and out[0].isupper()


def test_strips_marker_variants_incl_space_and_tag_forms() -> None:
    # "[E-295 F3]" (space + finding tag) and "[E-021:F1]" must both be stripped
    for title in (
        "Claude notes May 6 2025 [E-295 F3]: FSC PAC contribution pattern shifts",
        "Persona segmentation with defined journeys [E-021:F1] across channels",
    ):
        out = _finalize_card_title(title, "A substantive finding body sentence here.")
        assert "[E-" not in out, f"marker leaked: {out!r}"


def test_scaffolding_title_is_crafted_from_body() -> None:
    out = _finalize_card_title(
        "Capability dimension 30",
        "Illinois law requires AG notification for breaches affecting 500+ people; "
        "no Acuity notification process was found.")
    assert out.lower() != "capability dimension 30"
    assert "dimension 30" not in out.lower()
    assert len(out) >= 6


def test_title_equals_body_is_replaced_with_clean_headline() -> None:
    # the "title" is the leading run of the WHAT, cut mid-word ("directi")
    out = _finalize_card_title(
        "Cost-Optimized Cloud Strategy. CTO Adrian Glace directi",
        "Cost-Optimized Cloud Strategy. CTO Adrian Glace directing a migration to "
        "reduce infrastructure spend.")
    assert not out.endswith("directi")          # no mid-word truncation
    assert "…" not in out or out.count("…") <= 1
    assert out.rstrip(". ") != \
        "Cost-Optimized Cloud Strategy. CTO Adrian Glace directi".rstrip(". ")


def test_good_title_is_preserved() -> None:
    # a real crafted headline that is NOT a prefix of the body stays untouched
    out = _finalize_card_title(
        "Digital Lending Modernization",
        "Manual underwriting adds 9 days to loan decisions across the retail book.")
    assert out == "Digital Lending Modernization"


def test_empty_title_falls_back_to_body_headline() -> None:
    out = _finalize_card_title(
        "", "Three core banking systems run in parallel with no canonical profile.")
    assert out and len(out) >= 6
