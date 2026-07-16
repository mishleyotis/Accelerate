"""S15 pack-gate prose checks + cohesion para_break class (2026-07-14).

The audit found the exec summary (narrative.scqa_md) entirely unscanned
by the enforced pack gate while two real defect classes shipped: a
paragraph break landing mid-name ("EverBank, N.A.¶¶can put …") and
register-severity parentheticals welded into prose ("(high severity)"
on 16 of 28 sampled clients). Pure-logic, no DB.
"""
from __future__ import annotations

from app.scripts.pack_quality_gate import (
    _SEV_PAREN_RE,
    ENFORCED_CEILINGS,
    headline_defects,
    para_break_defects,
)
from app.scripts.qa_paragraph_cohesion import check_paragraph
from app.services.startup_enrich import finding_headline

_CLEAN = (
    "EverBank, N.A. can put TCFD Alignment first and hold the line on "
    "governance across the next two quarters of remediation work.\n\n"
    "The peer set holds a meaningful lead on data foundations, and closing "
    "that spread is the next phase's core work for the leadership team."
)


def test_clean_two_paragraph_prose_passes() -> None:
    assert para_break_defects(_CLEAN) == []
    assert "para_break" not in check_paragraph(_CLEAN)


def test_mid_name_paragraph_break_is_flagged() -> None:
    bad = (
        "Momentum, adjacency and clean capabilities collect their share. "
        "EverBank, N.A.\n\ncan put TCFD Alignment first while the register "
        "stays open on two governance items across the coming quarters."
    )
    defects = para_break_defects(bad)
    assert defects and "abbreviation" in defects[0]
    assert "para_break" in check_paragraph(bad)


def test_break_after_vs_abbreviation_is_flagged() -> None:
    bad = (
        "The spread is widest facing the P2 pillar (Customer Experience: "
        "2.13 vs.\n\n3.1 for the peer set), and that is where the first "
        "phase of remediation work concentrates for the coming year."
    )
    assert para_break_defects(bad)


def test_break_mid_clause_without_punctuation_is_flagged() -> None:
    bad = (
        "The assessment ranks the data foundation gap most binding for the "
        "institution\n\nbecause every dependent investment inherits it "
        "across the transformation roadmap."
    )
    defects = para_break_defects(bad)
    assert defects and "non-sentence-end" in defects[0]


def test_break_after_citation_bracket_is_clean() -> None:
    ok = (
        "The register carries two open governance items the file grounds "
        "plainly [E-095, E-098].\n\nThe peer set holds a meaningful lead "
        "on data foundations across every scored capability area."
    )
    assert para_break_defects(ok) == []


def test_severity_parenthetical_detector() -> None:
    assert _SEV_PAREN_RE.search("no confirmed replacement (high severity) [E-095]")
    assert _SEV_PAREN_RE.search("board gap (Critical severity)")
    # prose-carried severity is the sanctioned form — never flagged
    assert not _SEV_PAREN_RE.search(
        "The issue register adds a high-severity item: succession risk.")


def test_s15_segments_are_enforced_at_zero() -> None:
    assert ENFORCED_CEILINGS["S15_para_break_mid_sentence"] == 0
    assert ENFORCED_CEILINGS["S15_severity_label"] == 0


# ── S16 headline / label hygiene (W7, 2026-07-14) ───────────────────────────

def test_headline_flags_mid_thought_clip() -> None:
    # a source-title ingest ellipsis clip, and a bare dangling connective
    assert "mid_thought" in headline_defects(
        "MetricStream GRC Implementation: Bank OZK went live on")
    assert "mid_thought" in headline_defects(
        "HVCU Charitable Foundation launched Feb/March 2025 as…")


def test_headline_flags_score_recital() -> None:
    assert "score_quoting" in headline_defects(
        "AI Use Case Pipeline sits at 1.55/5 vs a 3.00 peer median")


def test_clean_headline_passes() -> None:
    assert headline_defects(
        "3 live data & tech roles open at Capital Farm Credit") == []
    assert headline_defects(
        "AI Use Case Pipeline trails the Strategy & Governance peer set") == []
    # a legitimate bank-name suffix ("N.A") is NOT a dangling connective
    assert headline_defects("1 live data & tech role open at EverBank, N.A") == []
    # Title-Case hyphenated tails ("Lock-In", "Opt-In") are whole words, not
    # a dangling "in" — the case-sensitive + hyphen-aware guard (W7 false-pos)
    assert headline_defects(
        "Salesforce Data Cloud — Displace Bespoke CDP Before Vendor Lock-In") == []
    assert headline_defects("Drive Member Opt-In") == []


def test_finalize_card_title_clears_s16_classes() -> None:
    from app.scripts.derive_insights import _finalize_card_title
    # ingest-clipped evidence title → dangling tail stripped
    assert headline_defects(_finalize_card_title(
        "RESG Concentration Risk: Real Estate Specialties Group declining from peak to",
        "RESG book declining from peak to trough over the cycle")) == []
    # score-leading sentiment title → score lead dropped, capability kept
    out = _finalize_card_title(
        "Culture score 3.4/5 — the Innovation Vision opportunity",
        "Glassdoor ratings surface the innovation vision opportunity")
    assert headline_defects(out) == [] and "3.4/5" not in out
    assert "Innovation Vision" in out


def test_finding_headline_declips_ingest_truncated_name() -> None:
    # the analyst name arrives clipped at a connective — it must not pass
    # through mid-thought (the exact S16 defects the 94-client audit found).
    for clipped in (
        "MetricStream GRC Implementation: Bank OZK went live on",
        "STCU’s strategic direction under CEO Lindsey Myhre centers on",  # noqa: RUF001
    ):
        h = finding_headline(clipped, "P1C1", 2.0, 2.8, what="")
        assert headline_defects(h) == [], f"still clipped: {h!r}"


def test_s16_segments_are_enforced_at_zero() -> None:
    assert ENFORCED_CEILINGS["S16_headline_mid_thought"] == 0
    assert ENFORCED_CEILINGS["S16_headline_score_quoting"] == 0
