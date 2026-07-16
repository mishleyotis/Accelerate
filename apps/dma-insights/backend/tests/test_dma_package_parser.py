"""End-to-end package parser tests against real DMA fixtures.

The fixtures ship under `/tmp/dma-fixtures/{alma,wsfs}` (extracted from
the user-provided AlmaBank + WSFS Complete Package zips). When the
fixtures aren't on the runner (CI sandbox without /tmp/dma-fixtures),
these tests skip — we keep the assertions specific so the moment the
fixtures land, parser regressions surface.
"""
from __future__ import annotations

from pathlib import Path

from app.services.parsers.dma_package import parse_package
from app.services.parsers.package_csvs import (
    parse_category_summary_csv,
    parse_evidence_csv,
    parse_issue_register_csv,
    parse_pillar_summary_csv,
    parse_scoring_detail_csv,
)
from app.services.parsers.package_json import (
    parse_qa_verdict,
    parse_recommendations,
    parse_run_manifest,
    parse_top_manifest,
)

# Real DMA packages committed under tests/fixtures/dma_packages_real_samples/.
# (Previously these pointed at /tmp/dma-fixtures/{alma,wsfs} — paths that only
# existed on a developer's machine, so the round-trip tests permanently
# SKIPPED in CI. The packages are committed, so we run them for real.)
_REAL_SAMPLES = Path(__file__).resolve().parent / "fixtures" / "dma_packages_real_samples"
ALMA_ROOT = _REAL_SAMPLES / "Alma_Bank__DMA"
WSFS_ROOT = _REAL_SAMPLES / "WSFS_Bank__DMA"

# Warning prefixes that denote a PARSE FAILURE (must never appear). Benign
# provenance notes — `firmographics_from_client_profile_docx` (firmographics
# sourced from the Client Profile DOCX when no research_handoff.json ships)
# and `used variant ...` (a file found under a non-canonical filename) — are
# expected on the committed samples and are NOT failures.
_PARSE_FAILURE_PREFIXES = (
    "json_corrupt:", "schema_mismatch:", "io_error:",
    "client_profile_docx_parse_failed:", "catalogue_unresolved:",
    "catalogue_empty_for_version:",
)


def _assert_no_parse_failures(pkg) -> None:
    bad = [
        w for w in pkg.parser_warnings
        if any(w.startswith(p) for p in _PARSE_FAILURE_PREFIXES)
    ]
    assert not bad, f"parse-failure warnings present: {bad}"


# ── pure CSV parsers ────────────────────────────────────────────────────

def test_scoring_detail_strips_provenance_comment() -> None:
    txt = (
        "# run_id: DMA-ASM-X-20260101-0001\n"
        "SubCap_ID,Category,Score,Evidence_Ceiling,Caps_Applied,Confidence\n"
        "P1C1.1.1,P1C1,2.5,4.5,,HIGH\n"
    )
    rows = parse_scoring_detail_csv(txt)
    assert len(rows) == 1
    assert rows[0].subcap_id == "P1C1.1.1"
    assert rows[0].score == 2.5
    assert rows[0].confidence == "HIGH"


def test_evidence_csv_handles_entity_profile_sentinel() -> None:
    txt = (
        "Evidence_ID,Source_Name,URL,Tier,ERS,Publish_Date,"
        "Subcap_Mappings,Excerpt\n"
        "E-001,LinkedIn,https://example.com,T3,2.0,2024,"
        "\"ENTITY_PROFILE,P3C3,P1C2\",Some excerpt\n"
    )
    rows = parse_evidence_csv(txt)
    assert len(rows) == 1
    assert rows[0].tier == 3
    assert "ENTITY_PROFILE" in rows[0].subcap_mappings
    assert "P3C3" in rows[0].subcap_mappings


def test_evidence_csv_recovers_excerpt_from_header_variants() -> None:
    """Real packages sometimes ship the excerpt under `Claim_Excerpt`,
    `Fact`, `Finding`, or `Summary` instead of `Excerpt`. Without the
    aliases the excerpt was persisted as "(no excerpt)" — the audit
    traced this to thin EvidenceDrawer rows on header-variant clients."""
    txt = (
        "Evidence_ID,Source_Name,URL,Tier,Claim_Excerpt\n"
        "E-010,10-K,https://sec.gov/x,T1,Revenue grew 12% YoY\n"
    )
    rows = parse_evidence_csv(txt)
    assert rows[0].excerpt == "Revenue grew 12% YoY"

    for header in ("Fact", "Finding", "Summary"):
        txt = (
            f"Evidence_ID,Source_Name,Tier,{header}\n"
            f"E-011,Press,T2,Some {header.lower()} text\n"
        )
        rows = parse_evidence_csv(txt)
        assert rows[0].excerpt == f"Some {header.lower()} text", (
            f"excerpt alias for `{header}` header lost"
        )


def test_evidence_csv_recovers_subcaps_and_url_from_header_variants() -> None:
    """`Subcaps_Supported` / `Mapped_Subcaps` / `Capabilities` carry the
    subcap link on some exports, and `Link` carries the URL — aliasing
    them preserves the heatmap-cell → evidence grounding that was being
    dropped (81% empty linked_subcap_ids in the audit)."""
    for header in ("Subcaps_Supported", "Mapped_Subcaps", "Capabilities"):
        txt = (
            f"Evidence_ID,Source_Name,Link,{header}\n"
            f'E-012,Vendor,https://acme.io,"P1C1,P2C3"\n'
        )
        rows = parse_evidence_csv(txt)
        assert rows[0].source_url == "https://acme.io", (
            f"`Link` URL alias lost alongside `{header}`"
        )
        assert "P1C1" in rows[0].subcap_mappings, (
            f"subcap alias for `{header}` header lost"
        )
        assert "P2C3" in rows[0].subcap_mappings


def test_evidence_csv_canonical_headers_win_over_aliases() -> None:
    """When BOTH the canonical and an alias header are present, the
    canonical column must win so a stray alias never shadows the real
    value."""
    txt = (
        "Evidence_ID,Source_Name,Excerpt,Fact,URL,Link\n"
        "E-013,Src,canonical excerpt,alias fact,"
        "https://canonical.example,https://alias.example\n"
    )
    rows = parse_evidence_csv(txt)
    assert rows[0].excerpt == "canonical excerpt"
    assert rows[0].source_url == "https://canonical.example"


def test_category_summary_tolerates_lowercase_headers() -> None:
    txt = (
        "category_id,category_name,pillar,score,peer_p25,peer_median,peer_p75\n"
        "P1C1,Digital Strategy,P1,3.5,3.0,3.25,3.875\n"
    )
    rows = parse_category_summary_csv(txt)
    assert rows[0].pillar_id == "P1"
    assert rows[0].peer_median == 3.25


def test_pillar_summary_extracts_pid_from_label() -> None:
    txt = "Pillar,Score,Weight\nPillar 1,2.3,0.25\n"
    rows = parse_pillar_summary_csv(txt)
    assert rows[0].pillar_id == "P1"


def test_issue_csv_normalizes_material_severity_and_cap_value() -> None:
    txt = (
        "id,severity,description,capabilities_affected,cap_value\n"
        "ISS-001,MATERIAL,Fragmented data,\"['P4C1.3', 'P2C4.1']\",3.0\n"
    )
    rows = parse_issue_register_csv(txt)
    assert rows[0].severity == "HIGH"
    assert rows[0].cap_ceiling == 3.0
    assert rows[0].affected_categories == ["P4C1.3", "P2C4.1"]


# ── Cap-centric layout (2026-06 fixture-mined promotions) ────────────


def test_issue_csv_accepts_cap_id_as_row_key() -> None:
    """Cap-centric layouts use `cap_id` as the row identifier instead
    of `issue_id` / `id`. The mining survey showed 37 occurrences of
    `cap_id` across the fixture set; without this alias every row in
    those packages drops silently."""
    txt = (
        "cap_id,cap_severity,description,capabilities_affected\n"
        "CAP-P3C2-001,HIGH,Manual reconciliation cap,\"['P3C2.1']\"\n"
    )
    rows = parse_issue_register_csv(txt)
    assert len(rows) == 1
    assert rows[0].issue_id == "CAP-P3C2-001"
    assert rows[0].severity == "HIGH"
    assert rows[0].affected_categories == ["P3C2.1"]


def test_issue_csv_accepts_cap_severity_as_severity() -> None:
    """`cap_severity` (17 occurrences) is the severity column on
    cap-centric layouts. Same MEDIUM/HIGH/CRITICAL enum semantics."""
    txt = (
        "issue_id,cap_severity,description\n"
        "ISS-002,CRITICAL,Vendor lock-in\n"
    )
    rows = parse_issue_register_csv(txt)
    assert rows[0].severity == "CRITICAL"


def test_issue_csv_routes_cap_source_to_type() -> None:
    """`cap_source` (17 occurrences) carries the document name or
    analyst attribution — surfaces on `type` when no explicit `type`
    column ships."""
    txt = (
        "issue_id,severity,description,cap_source\n"
        "ISS-003,MEDIUM,Stale governance docs,Risk Committee Memo 2024-Q3\n"
    )
    rows = parse_issue_register_csv(txt)
    assert rows[0].type == "Risk Committee Memo 2024-Q3"


def test_issue_csv_explicit_type_wins_over_cap_source() -> None:
    """When BOTH `type` and `cap_source` ship, the explicit `type`
    must win — the cap_source alias is fallback-only, mirroring the
    issue_id → id → cap_id priority chain elsewhere in this parser."""
    txt = (
        "issue_id,type,cap_source,severity,description\n"
        "ISS-004,Regulatory,Memo 2024,LOW,doc gap\n"
    )
    rows = parse_issue_register_csv(txt)
    assert rows[0].type == "Regulatory"


# ── JSON parsers ────────────────────────────────────────────────────────

def test_top_manifest_parses_minimum_fields() -> None:
    pm = parse_top_manifest(
        '{"engagement":"X","run_id":"DMA-ASM-X-20260101-0001",'
        '"overall_score":1.5}'
    )
    assert pm.run_id == "DMA-ASM-X-20260101-0001"
    assert pm.overall_score == 1.5


def test_run_manifest_handles_wsfs_keys() -> None:
    blob = (
        '{"$schema":"run_manifest_v2",'
        '"assessment_id":"DMA-RES-X-20260101-0001",'
        '"l1_run_id":"DMA-ASM-X-20260101-0001",'
        '"entity":"X Co","subvertical":"CL","subvertical_code":"CL",'
        '"skill_version":"dma-assessment v5.5"}'
    )
    rm = parse_run_manifest(blob)
    assert rm.run_id == "DMA-ASM-X-20260101-0001"
    assert rm.institution_name == "X Co"
    assert rm.subvertical_code == "CL"
    assert rm.skill_version == "dma-assessment v5.5"


def test_qa_verdict_handles_wsfs_keys() -> None:
    blob = (
        '{"overall_verdict":"PASS_WITH_NOTES",'
        '"recommended_action":"DELIVER","verdict_note":"all good",'
        '"pass1_results":{"organic_critical":0,"organic_high":2}}'
    )
    qa = parse_qa_verdict(blob)
    assert qa.verdict == "PASS_WITH_NOTES"
    assert qa.recommendation == "DELIVER"
    assert qa.issue_count_genuine_only == {
        "CRITICAL": 0, "HIGH": 2, "MEDIUM": 0, "LOW": 0,
    }


def test_recommendations_normalizes_short_id() -> None:
    blob = '{"recommendations":[{"id":"R7","title":"Workshop"}]}'
    rs = parse_recommendations(blob)
    assert rs[0].id == "REC-07"


# ── full fixture round-trip ─────────────────────────────────────────────

def test_alma_package_round_trip() -> None:
    pkg = parse_package(ALMA_ROOT)
    rm = pkg.run_manifest
    assert rm.run_id == "DMA-ASM-ALMA-20260519-0001"
    assert rm.institution_name == "Alma Bank"
    assert pkg.pillar_weights == {"P1": 0.25, "P2": 0.3, "P3": 0.2, "P4": 0.25}
    assert len(pkg.subcap_scores) == 698
    assert len(pkg.evidence) == 105
    assert len(pkg.peers) == 5
    assert len(pkg.recommendations) == 7
    assert len(pkg.issue_register) >= 9
    assert pkg.qa_verdict is not None and pkg.qa_verdict.verdict == "PASS_WITH_NOTES"
    assert len(pkg.tech_stack) >= 30
    # No PARSE FAILURES (benign provenance notes are allowed — the
    # committed sample sources firmographics from the Client Profile DOCX).
    _assert_no_parse_failures(pkg)
    # focus_areas now propagate end-to-end (2026-05-29 finalization).
    assert len(pkg.focus_areas) >= 1


def test_wsfs_package_round_trip() -> None:
    pkg = parse_package(WSFS_ROOT)
    rm = pkg.run_manifest
    assert rm.run_id == "DMA-ASM-WSFS-20260519-0001"
    assert rm.institution_name == "WSFS Financial Corporation"
    assert rm.subvertical_code == "CL"
    assert pkg.pillar_weights == {"P1": 0.2, "P2": 0.2, "P3": 0.35, "P4": 0.25}
    assert len(pkg.subcap_scores) == 708
    assert len(pkg.evidence) == 106
    assert len(pkg.peers) == 4
    # WSFS ships issues only in the A9 appendix CSV.
    assert len(pkg.issue_register) >= 4
    assert pkg.firmographics is not None
    assert pkg.firmographics.legal_name == "WSFS Financial Corporation"
    assert pkg.qa_verdict is not None
    assert pkg.qa_verdict.verdict == "PASS_WITH_NOTES"
    # WSFS package omits `recommendations_detail.json` but per the F4
    # revision (2026-06-07), the parser now falls back to mining the
    # Assessment_Report.docx §9 prose. WSFS has 5 recs (REC-001..REC-005)
    # inline in the recs region of the DOCX. Pin ≥4 to absorb any
    # minor extraction drift without re-churning the test.
    assert len(pkg.recommendations) >= 4
    rec_ids = {r.id for r in pkg.recommendations}
    # First and last rec IDs must always be present — those bracket the
    # extraction window. Loss of either signals an extraction regression.
    assert "REC-001" in rec_ids, (
        f"REC-001 missing from WSFS DOCX-extracted recs: {rec_ids}"
    )
    _assert_no_parse_failures(pkg)
