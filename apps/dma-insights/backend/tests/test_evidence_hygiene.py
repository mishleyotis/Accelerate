"""Evidence-annotation normalizer (nlp/evidence_hygiene.py). The ~30% of
evidence_index rows carrying ingest artifacts — multi-EID/truncated e_id cells,
":F<n>" suffixes, and "[CEILING…]/[E-…]/(T#, STATUS):" excerpt wrappers — must
reduce to a citable E-ID and the human sentence.
"""
from __future__ import annotations

from app.services.nlp.evidence_hygiene import (
    clean_and_dedupe_evidence,
    clean_excerpt,
    clean_finding_items,
    clean_finding_text,
    primary_eid,
)


def test_primary_eid_takes_first_complete_token() -> None:
    # a comma cell: the FIRST token is intact, the trailing one is column-cut
    assert primary_eid("E-031,E-032,E-03") == "E-031"
    assert primary_eid("E-072:F2, E-072:") == "E-072"
    assert primary_eid("E-004:F1,E-023:F") == "E-004"
    assert primary_eid("E-086:F1") == "E-086"
    assert primary_eid("E-918, E-228") == "E-918"


def test_primary_eid_falls_back_to_excerpt_citation_block() -> None:
    assert primary_eid("", "[CEILING: L3.5] [E-006:F1, E-007:F1] Net Zero: text") == "E-006"
    assert primary_eid(None, "no id here") is None
    assert primary_eid("garbage", "") is None


def test_clean_excerpt_strips_annotation_header_and_tier_marker() -> None:
    raw = ("[ERS: 4.60] [FACT] [E-041:F1] Access CU 2025 Annual Report — "
           "Digital Banking (T2, CURRENT): FY2025 new digital features deployed.")
    out = clean_excerpt(raw)
    assert out == "FY2025 new digital features deployed."
    assert "[" not in out and "(T2" not in out and "ERS" not in out


def test_clean_excerpt_strips_ceiling_and_trailing_markers() -> None:
    raw = ("[CEILING: L3.5 ±0.3] [E-006:F1, E-007:F1, E-007:F3] "
           "Net Zero Pathway: Defined pathway to net zero emissions "
           "[PRESENCE ≠ UTILIZATION]")
    out = clean_excerpt(raw)
    assert out == "Net Zero Pathway: Defined pathway to net zero emissions"
    assert "CEILING" not in out and "PRESENCE" not in out


def test_clean_excerpt_strips_analyst_validation_prefix() -> None:
    raw = "Invalidated E-055/F4: Acuity HAS straight-through processing for auto claims."
    out = clean_excerpt(raw)
    assert out == "Acuity HAS straight-through processing for auto claims."
    assert "Invalidated" not in out
    # a legitimate sentence that merely contains "validated" mid-text is kept
    keep = "The vendor validated the model against 2024 loss data across all lines."
    assert clean_excerpt(keep) == keep


def test_clean_excerpt_splits_pipe_row_and_strips_inline_annotation() -> None:
    raw = ("341 employees, 327 FTEs as of March 2 2026 | [ERS:4.65] [FACT] "
           "[E-016:F2] 26 full-service banking offices across 12 CA counties | "
           "[ERS:3.66] [E-019:F2] CWB Mobile app is available on iOS and Android")
    out = clean_excerpt(raw)
    assert "[ERS" not in out and "[FACT]" not in out and "|" not in out
    assert "26 full-service banking offices across 12 CA counties." in out
    assert "CWB Mobile app is available on iOS and Android." in out


def test_clean_excerpt_leaves_clean_text_untouched() -> None:
    raw = "The bank runs a single unified mobile app with modern journeys."
    assert clean_excerpt(raw) == raw
    assert clean_excerpt("") == ""
    assert clean_excerpt(None) == ""


def test_clean_excerpt_does_not_eat_midsentence_parenthetical() -> None:
    # a "(T3 ...)" AFTER a real sentence is not a header marker — a sentence
    # break before it protects the prose from being stripped.
    raw = ("Rolled out to all branches in 2024. A later tier update "
           "(T3, PLANNED): trails the roadmap.")
    out = clean_excerpt(raw)
    assert out.startswith("Rolled out to all branches")


# ── the evidence-drawer read-time pass (clean_and_dedupe_evidence) ──────────
# Mirrors the real corpus shapes the 95-client stress-test surfaced so the AE's
# verification surface never shows a truncated citation, an annotation blob, a
# duplicate, or a "(no excerpt)" stub.

def test_drawer_normalizes_dirty_fragment_and_keeps_passthrough_fields() -> None:
    rows = [{"e_id": "E-006:F1, E-007:", "tier": 2,
             "excerpt": "[CEILING: L3.5 ±0.3] [E-006:F1, E-007:F1] Net Zero "
                        "Pathway: Defined pathway to net zero emissions by 2040."}]
    out = clean_and_dedupe_evidence(rows)
    assert len(out) == 1
    assert out[0]["e_id"] == "E-006"                     # citable id recovered
    assert out[0]["excerpt"].startswith("Net Zero Pathway")   # human sentence
    assert "[CEILING" not in out[0]["excerpt"]
    assert out[0]["tier"] == 2                           # passthrough preserved


def test_drawer_preserves_non_edigit_id_scheme() -> None:
    # E-INT-#### internal-data rows must NOT be dropped (regression guard: they
    # yield None from primary_eid's E-<digit> matcher).
    rows = [{"e_id": "E-INT-0201",
             "excerpt": "Hubbl flows.csv: 326 rows. Columns: id, itemId, label, status."}]
    out = clean_and_dedupe_evidence(rows)
    assert len(out) == 1 and out[0]["e_id"] == "E-INT-0201"


def test_drawer_drops_unquotable_stubs() -> None:
    rows = [{"e_id": "E-1", "excerpt": "(no excerpt)"},
            {"e_id": "E-2", "excerpt": "NEGATIVE PROXY:"},
            {"e_id": "E-3", "excerpt": "[CEILING: L2.0]"}]      # annotation-only
    assert clean_and_dedupe_evidence(rows) == []


def test_drawer_dedupes_preferring_canonical_over_fragment() -> None:
    rows = [
        # the column-cut fragment sorts first but is the weaker chip
        {"e_id": "E-006:F1, E-007:", "tier": 3,
         "excerpt": "[CEILING: L3.5] [E-006:F1] A short ceiling annotation fact."},
        # the canonical E-006 row carries the real evidence quote
        {"e_id": "E-006", "tier": 1,
         "excerpt": "Access CU compliant with capital and liquidity reserve "
                    "requirements per DGCM audited consolidated financials."},
    ]
    out = clean_and_dedupe_evidence(rows)
    assert len(out) == 1                                 # deduped to one E-006
    assert out[0]["e_id"] == "E-006"
    assert out[0]["tier"] == 1                           # canonical row won
    assert "compliant with capital" in out[0]["excerpt"]


def test_drawer_respects_limit() -> None:
    rows = [{"e_id": f"E-{i}", "excerpt": f"A quotable evidence sentence number {i} here."}
            for i in range(1, 20)]
    assert len(clean_and_dedupe_evidence(rows, limit=8)) == 8


# ── finding-prose hygiene (top_findings read-time clean) ────────────────────

def test_clean_finding_text_strips_inline_annotation() -> None:
    raw = ("The linked evidence records: [ERS: 4.60] [FACT] [E-021:F1] CBC News "
           "— Celero cyber incident (T1, LEGACY): June 2022 outage.")
    out = clean_finding_text(raw)
    assert "[ERS" not in out and "[FACT]" not in out and "[E-021:F1]" not in out
    assert "(T1, LEGACY)" not in out
    assert "Celero cyber incident" in out and "June 2022 outage" in out


def test_clean_finding_text_leaves_clean_prose_and_plain_citations() -> None:
    raw = "Fraud tooling confirmed — Verafin AML/BSA platform [E-804, E-805]."
    out = clean_finding_text(raw)
    assert "Verafin AML/BSA platform" in out
    assert "[E-804, E-805]" in out                 # plain citation list preserved


def test_clean_finding_items_drops_scaffold_and_strips_annotation() -> None:
    items = [
        {"title": "Each includes the evidence basis",
         "body": "Each includes the evidence basis, maturity implication, and "
                 "Salesforce solution alignment.", "why": ""},
        {"title": "Gap Priority 1 items",
         "why": "[ERS: 4.60] [FACT] [E-021:F1] A real grounded finding sentence."},
        "not-a-dict",
    ]
    out = clean_finding_items(items)
    assert len(out) == 2                            # scaffold dropped, dict+passthrough kept
    assert out[0]["title"] == "Gap Priority 1 items"
    assert "[ERS" not in out[0]["why"] and "grounded finding sentence" in out[0]["why"]
    assert out[1] == "not-a-dict"                   # non-dict passes through
