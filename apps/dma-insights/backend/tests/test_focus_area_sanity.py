"""Focus-area display sanitation (2026-06-10 final-tests census).

Pins the read-path filter that keeps DOCX scaffolding off the D3 focus
view: 75 meta-header rows ("2 Top Findings (with Zennify Relevance)")
and dozens of bare-ID titles ("F-004") were rendering as strategic-
priority cards. All shapes below are VERBATIM from the corpus.
"""
from __future__ import annotations

from app.services.focus_area_sanity import clean_focus_area


def test_meta_header_rows_are_dropped() -> None:
    junk = [
        ("2 Top Findings (with Zennify Relevance)",
         "Seven headline findings — each tied to a triple-validated gap"),
        ("2 Top Findings",
         "Each finding includes: (a) quantified observation with source"),
        ("2 Critical Gaps1.2 Critical Gaps",
         "• Fax still used for CIBC Mellon transactions"),
        ("Near-Term Objectives (2026)", "Near-Term Objectives (2026)"),
        ("All findings aligned to 6 strategic objectives from SEC "
         "filings and earnings calls. SO-1 (Post-Merger Integration)",
         "All findings aligned to 6 strategic objectives from SEC"),
    ]
    for title, quote in junk:
        keep, _ = clean_focus_area(title, quote)
        assert not keep, f"meta row leaked to display: {title!r}"


def test_bare_id_title_salvaged_from_pipe_quote() -> None:
    keep, title = clean_focus_area(
        "F-004",
        "F-004 | Teradata to Databricks modernization in flight | "
        "P3C2 evidence",
    )
    assert keep
    assert title == "Teradata to Databricks modernization in flight"


def test_bare_id_without_statement_dropped() -> None:
    keep, _ = clean_focus_area("G-017", "G-017")
    assert not keep


def test_genuine_focus_area_kept_verbatim() -> None:
    keep, title = clean_focus_area(
        "Post-merger data integration",
        "Integrating the acquired bank's core onto FIS within 18 months",
    )
    assert keep and title == "Post-merger data integration"


def test_sentence_blob_title_clipped_at_clause() -> None:
    long_title = (
        "Chris Livingston promoted to Deputy CISO (March 2025), now "
        "directing the Security Operations and Engineering team and "
        "the broader cyber program"
    )
    keep, title = clean_focus_area(long_title, long_title)
    assert keep
    assert len(title) <= 97  # 96 + ellipsis
    assert not title.endswith(" ")


# ── 2026-06-11 QA audit: preamble / scaffolding / notebook shapes ────

def test_preamble_the_following_dropped() -> None:
    from app.services.focus_area_sanity import clean_focus_area
    keep, _ = clean_focus_area(
        "The following strategic objectives are extracted directly from "
        "SouthState Corporation's public disclosures", "")
    assert keep is False
    keep, _ = clean_focus_area(
        "The following 10 strategic objectives, ordered by recency and "
        "material impact, drive the assessment", "")
    assert keep is False


def test_zennify_implications_commentary_dropped() -> None:
    from app.services.focus_area_sanity import clean_focus_area
    keep, _ = clean_focus_area(
        "Implications for Zennify Engagement Timing: SO-01 (GoBanking "
        "2025 upgrade) creates a window", "")
    assert keep is False


def test_guiding_principles_scaffolding_dropped() -> None:
    from app.services.focus_area_sanity import clean_focus_area
    keep, _ = clean_focus_area(
        "Guiding Principles (CSR Report): Soundness, Profitability, "
        "Growth. Core Values: …", "")
    assert keep is False


def test_notebook_artifacts_dropped() -> None:
    from app.services.focus_area_sanity import clean_focus_area
    keep, _ = clean_focus_area("- if in Colab: `from google.colab import drive`", "")
    assert keep is False
    keep, _ = clean_focus_area("```python setup chunk```", "")
    assert keep is False


def test_real_priorities_still_kept() -> None:
    from app.services.focus_area_sanity import clean_focus_area
    keep, title = clean_focus_area(
        "Digital Account Opening",
        "We are investing to compress account opening from 9 minutes…")
    assert keep is True and title == "Digital Account Opening"
    # Sentences that merely CONTAIN 'following' mid-text are fine.
    keep, _ = clean_focus_area(
        "Deposit growth following the 2025 core conversion", "")
    assert keep is True


def test_live_corpus_machine_suffix_and_pipes_stripped() -> None:
    # 2026-06-11 operator screenshots (United Federal Credit Union):
    # titles arrived as full pipe-delimited analyst lines with routing
    # suffixes. Display title = first segment, suffix/quotes stripped.
    from app.services.focus_area_sanity import clean_focus_area
    raw = ('"Commercial/SBA growth cornerstone outpaces relationship '
           'infrastructure (→OBJ-1, HIGH) | Commercial & SBA lending '
           'named the growth cornerstone — CCO→SLT (Jul 2025) '
           '[E-022, E-070]"')
    keep, shown = clean_focus_area(raw, raw)
    assert keep is True
    assert shown == ("Commercial/SBA growth cornerstone outpaces "
                     "relationship infrastructure")
    keep, shown = clean_focus_area(
        "AI governance is in place; activation surface is missing "
        "(→OBJ-2, HIGH)", "")
    assert keep and shown == ("AI governance is in place; activation "
                              "surface is missing")


# ── Subvertical scope: subvertical-NA capability dropped (2026-07 FCMA) ──────
# "AI Claims Estimation" (subcap P2C3.2.IC1 — an INSURANCE-CARRIER overlay
# leaf) leaked as a focus area on Farm-Credit-Mid-America (SV3 Commercial
# Lending). Verbatim from the batch_15 A5 Subvertical-NA log.
_SV3 = "SV3 Commercial Lending + Farm Credit GSE Cooperative"
_A5_NA = {"P2C2.3.7", "P2C2.5.5", "P2C2.8.2", "P2C3.2.IC1"}


def test_subcap_out_of_scope_ic_leaf_on_lending_entity() -> None:
    from app.services.focus_area_sanity import subcap_out_of_scope
    # insurance-carrier (.IC1) overlay leaf is out of scope for a lender
    assert subcap_out_of_scope("P2C3.2.IC1", subvertical=_SV3) is True
    # a normal in-scope subcap is kept
    assert subcap_out_of_scope("P2C3.1.1", subvertical=_SV3) is False
    # authoritative A5-NA membership also drops it
    assert subcap_out_of_scope("P2C2.3.7", na_subcap_ids=_A5_NA) is True


def test_unknown_subvertical_judges_nothing() -> None:
    from app.services.focus_area_sanity import subcap_out_of_scope
    # honest floor — no subvertical + no NA list ⇒ nothing dropped
    assert subcap_out_of_scope("P2C3.2.IC1") is False


def test_ai_claims_estimation_focus_dropped() -> None:
    # by involved subcap id (A5-NA) …
    keep, _ = clean_focus_area(
        "AI Claims Estimation", "AI-driven claims estimation capability",
        ["P2C3.2.IC1"], subvertical=_SV3, na_subcap_ids=_A5_NA)
    assert keep is False
    # … and by the carrier-only capability NAME on a non-carrier entity
    keep, _ = clean_focus_area(
        "AI Claims Estimation", "claims estimation and adjudication",
        subvertical=_SV3)
    assert keep is False


def test_in_scope_focus_kept_for_lender() -> None:
    keep, title = clean_focus_area(
        "Modernize member experience",
        "Unify servicing channels for the ag lending cooperative",
        ["P2C3.1.1"], subvertical=_SV3)
    assert keep and title == "Modernize member experience"


def test_carrier_focus_kept_for_carrier_subvertical() -> None:
    # the SAME capability IS in scope for an insurance carrier — never
    # over-drop when the subvertical actually matches the LOB.
    keep, _ = clean_focus_area(
        "AI Claims Estimation", "claims estimation automation",
        ["P2C3.2.IC1"], subvertical="SV12 Insurance Carrier")
    assert keep is True


# ── Title-split "| Rosie": strip F-0NN, first non-empty pipe segment ─────────
def test_title_from_finding_row_strips_id_and_takes_first_segment() -> None:
    from app.services.focus_area_sanity import title_from_finding_row
    head, body = title_from_finding_row(
        "F-003 | ROSIE-Salesforce NBA | ROSIE = 22 ML models")
    assert head == "ROSIE-Salesforce NBA"
    assert body == "ROSIE = 22 ML models"


def test_pipe_row_title_never_yields_leading_pipe() -> None:
    keep, title = clean_focus_area(
        "F-003 | ROSIE-Salesforce NBA | ROSIE = 22 ML models",
        "F-003 | ROSIE-Salesforce NBA | ROSIE = 22 ML models")
    assert keep is True
    assert not title.startswith("|")
    assert title == "ROSIE-Salesforce NBA"
