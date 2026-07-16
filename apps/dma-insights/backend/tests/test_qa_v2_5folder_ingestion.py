"""v2 QA — contract tests for the 5-real-client-folder ingestion findings.

These tests pin the F1 + F2 + F3 + F4 fixes from
`docs/qa/qa_5folder_live_findings.md`. Each test asserts an
end-to-end parse outcome against the real fixture; reverting the
fix makes the test fail (TDD-by-revert discipline per Batches 7-9).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parsers.dma_package import parse_package

FIXTURES_ROOT = (
    Path(__file__).parent / "fixtures" / "dma_packages_real_samples"
)


def _has_fixtures() -> bool:
    return (FIXTURES_ROOT / "Alma_Bank__DMA").exists()


pytestmark = pytest.mark.skipif(
    not _has_fixtures(),
    reason="real-sample fixtures not present on this branch",
)


# =========================================================================
# Gate-2 entry baselines — what parse_package returns TODAY
# =========================================================================


def test_alma_bank_baseline_pinned():
    """Pin Alma_Bank to its Gate-2 baseline on the default branch.

    Any future parser change that drifts Alma's counts must update this
    pin AND document the cascade impact. Catches accidental regressions
    in folders we already ingest correctly.
    """
    pkg = parse_package(FIXTURES_ROOT / "Alma_Bank__DMA")
    assert pkg.run_manifest is not None
    assert pkg.run_manifest.run_id == "DMA-ASM-ALMA-20260519-0001"
    assert len(pkg.evidence) == 105
    assert len(pkg.subcap_scores) == 698
    assert len(pkg.recommendations) == 7
    assert len(pkg.report_sections) == 72
    # Warnings on default branch include self-improvement observation
    # side-effects PLUS the 2026-06 enrichment breadcrumbs
    # (xlsx_name_enrichment, scqa_from_report_synthesis_md,
    # peer_benchmarks_filled, insights_derived_from_*,
    # research_workbook_evidence) — informative provenance lines, not
    # errors. Ceiling raised 4 -> 12 for those feature emitters
    # (2026-06-10 deploy simulation re-pin; Alma observed at 10).
    # Part 12.6 (2026-07): INFO/pattern_gap breadcrumbs (one per
    # unconsumed artifact shape the knowledge miner generic-mined) are
    # a LEARNING signal that scales with the package's appendix count,
    # not a parser-health signal — excluded from the ceiling.
    non_gap = [
        w for w in pkg.parser_warnings
        if not str(w).startswith("INFO/pattern_gap")
    ]
    assert len(non_gap) <= 12


def test_wsfs_bank_baseline_pinned():
    """Pin WSFS baseline. Recs come from the DOCX §9 fallback (F4
    revised: WSFS ships no recs JSON but the Assessment_Report.docx
    has the 5 rec definitions inline in the §9 region).
    """
    pkg = parse_package(FIXTURES_ROOT / "WSFS_Bank__DMA")
    assert pkg.run_manifest is not None
    assert pkg.run_manifest.run_id == "DMA-ASM-WSFS-20260519-0001"
    assert len(pkg.evidence) == 106
    assert len(pkg.subcap_scores) == 708
    # F4 revised (2026-06-07): 5 recs from DOCX §9 extraction
    # (REC-001..REC-005); was 0 before the DOCX fallback landed.
    assert len(pkg.recommendations) == 5
    # 68 sections (was 56 before the F4 dedup-scoping fix; the 5 cycles
    # of `[ROOT CAUSE]` / `[SOLUTION]` / `[EXPECTED OUTCOMES]` heading-3
    # blocks are no longer collapsed into one).
    assert len(pkg.report_sections) == 68
    # WSFS today emits 4 warnings:
    #  - research_workbook_evidence enrichment
    #  - used variant issue register (08_appendices A9 variant)
    #  - used docx-extracted recommendations (F4 revised; replaces the
    #    earlier `no_recommendations_source` warning)
    #  - firmographics_leadership_merged_from_docx (F5b-1)
    # Ceiling raised 5 -> 12 for the 2026-06 enrichment breadcrumbs
    # (research_workbook_evidence, financial_highlights_from_client_report,
    # sentiment_from_csv, scqa_from_report_synthesis_md, ...) — see the
    # Alma pin's comment (2026-06-10 deploy simulation re-pin; WSFS
    # observed at 9). Part 12.6 (2026-07): INFO/pattern_gap learning
    # breadcrumbs excluded — see the Alma pin.
    non_gap = [
        w for w in pkg.parser_warnings
        if not str(w).startswith("INFO/pattern_gap")
    ]
    assert len(non_gap) <= 12


# =========================================================================
# F1 — Nicola_Wealth ingestion via synthesize_run_manifest_from_handoff
# =========================================================================
# NOTE: F1 on the feature branch was "make qa_verdict glob case-
# insensitive". On the DEFAULT branch the right path is already wired
# — `_synthesize_run_manifest_from_handoff` reads
# `02_research_workbook/NicolaWealth_research_handoff.json` and produces
# a richer RunManifest than the QAVerdict file can. We pin that path
# here so a future refactor that drops synthesis-from-handoff in favor
# of QAVerdict-as-manifest gets caught.


def test_f1_nicola_wealth_synthesizes_run_manifest_from_handoff():
    """F1: Nicola has NO `run_manifest.json` and only a capital-QA
    `NicolaWealth_L2_QAVerdict.json`. The right path is to skip the
    variant-cased QAVerdict file (it lacks institution_name + scoring)
    and synthesize the manifest from
    `02_research_workbook/NicolaWealth_research_handoff.json`.
    """
    pkg = parse_package(FIXTURES_ROOT / "Nicola_Wealth__DMA")
    assert pkg is not None
    assert pkg.run_manifest is not None
    # The synthesized manifest carries institution_name + DMA-RES run_id.
    assert pkg.run_manifest.institution_name == "Nicola Wealth Management Ltd."
    assert pkg.run_manifest.run_id.startswith("DMA-RES-NICW")
    # Warning surfaces that synthesis happened.
    assert any(
        "synthesized run_manifest from handoff" in w
        for w in pkg.parser_warnings
    ), f"expected synthesize warning; got: {pkg.parser_warnings!r}"


# =========================================================================
# F2 — Odlum_Brown nested 07_governance/scoring_exports/ dir
# =========================================================================


def test_f2_odlum_brown_finds_nested_scoring_exports():
    """F2: Odlum ships final scoring CSVs at
    `07_governance/scoring_exports/export_*.csv` instead of
    `03_scoring_workbook/export_*.csv`. Parser at line 744 only
    scans 03_; the 63 KB of cap-applied final scoring exports
    are skipped → subcap_scores empty → HeatmapPage empty.

    Fix: include `07_governance/scoring_exports/` and
    `08_appendices/` in the export-CSV scan candidate list.
    Revert-test: remove the new candidate dirs → this test fails
    with subcap_scores empty.
    """
    pkg = parse_package(FIXTURES_ROOT / "Odlum_BROWN__DMA")
    assert pkg is not None
    assert pkg.run_manifest is not None
    # The nested export_scoring_detail.csv has 60+ subcaps in Odlum.
    # Conservative threshold: ≥ 40 subcaps after fix (currently 0).
    assert len(pkg.subcap_scores) >= 40, (
        f"F2 fix not applied: subcap_scores={len(pkg.subcap_scores)} "
        f"(expected ≥40 from 07_governance/scoring_exports/)"
    )


def test_f2_alma_bank_unchanged_by_f2_fix():
    """Cascade-guard for F2: Alma's 03_scoring_workbook/export_*.csv
    must still be preferred over any 07/scoring_exports/ files (Alma
    has none in 07, but the dir-priority order matters).

    Catches a regression where the new candidate-dirs loop accidentally
    overwrites Alma's already-correct subcap_scores with empty 07
    data.
    """
    pkg = parse_package(FIXTURES_ROOT / "Alma_Bank__DMA")
    # Alma baseline holds after F2 fix.
    assert len(pkg.subcap_scores) == 698


def test_f2_wsfs_bank_unchanged_by_f2_fix():
    """Cascade-guard for F2: WSFS scoring CSVs are in
    03_scoring_workbook/; must still parse fine after F2.
    """
    pkg = parse_package(FIXTURES_ROOT / "WSFS_Bank__DMA")
    assert len(pkg.subcap_scores) == 708


# =========================================================================
# F3 — Calprivate XLSX fallback (default-branch path already works)
# =========================================================================


def test_f3_calprivate_extracts_subcaps_from_xlsx_fallback():
    """F3: Calprivate ships only DMA_Assessment_Workbook_CPB_…xlsx +
    calculation_chain.json in 03_scoring_workbook/. The default branch
    handles this via the `_scoring_from_xlsx_fallback` path below the
    multi-dir CSV loop in dma_package.py.

    This test pins that path so a future refactor of the multi-dir
    candidate loop doesn't accidentally shadow the canonical
    03_scoring_workbook reference used by the XLSX fallback (which is
    exactly the bug we just fixed by capturing
    `canonical_scoring_dir`).
    """
    pkg = parse_package(FIXTURES_ROOT / "Calprivate_Bank__DMA")
    # ≥ 690 subcaps via XLSX fallback (audit acceptance bar from
    # tests/test_dma_package_real_samples_audit.py).
    assert len(pkg.subcap_scores) >= 690, (
        f"F3 XLSX fallback shadowed: subcap_scores={len(pkg.subcap_scores)} "
        f"(expected ≥690 via _scoring_from_xlsx_fallback)"
    )


# =========================================================================
# F5b — leadership extraction across all 5 real packages
# =========================================================================


def test_f5b_leadership_extracted_across_all_5_folders():
    """F5b: every real client package's DOCX has a leadership table; the
    parser must surface ≥3 executives per folder onto
    `IngestedPackage.firmographics.leadership`.

    Two integrated fixes:
      1. `client_profile.py::_extract_leadership_from_tables` accepts
         `Executive`-as-first-column tables (WSFS/Calprivate shape)
         and tables with a single `Name / Title` combined column
         (Nicola shape); iterates ALL matching tables (WSFS has 4)
         and dedupes by name.
      2. `dma_package.py` merges client-profile leadership into the
         handoff-derived Firmographics even when `firm` is already
         non-None (Nicola/WSFS/Calprivate path — handoff sets firm,
         but never carries the executive list).
    """
    expected_minimums = {
        "Alma_Bank__DMA": 8,
        "WSFS_Bank__DMA": 8,
        "Nicola_Wealth__DMA": 8,
        "Odlum_BROWN__DMA": 8,
        "Calprivate_Bank__DMA": 5,
    }
    actuals: dict[str, int] = {}
    for name, floor in expected_minimums.items():
        pkg = parse_package(FIXTURES_ROOT / name)
        firm = pkg.firmographics
        leadership = firm.leadership if firm and firm.leadership else []
        actuals[name] = len(leadership)
        assert len(leadership) >= floor, (
            f"F5b leadership under-extraction for {name}: "
            f"got {len(leadership)}, expected ≥{floor}"
        )


# =========================================================================
# F4 (revised 2026-06-07) — DOCX §9 recommendations fallback
# =========================================================================
# REVISION HISTORY:
#   - 2026-06-06 (original F4): diagnosed WSFS / Nicola / Calprivate as a
#     source-side gap (no recs JSON shipped) and surfaced a warning. The
#     analyst-prose Assessment_Report.docx §9 was overlooked.
#   - 2026-06-07 (user feedback "all clients have recommendations in
#     the assessment report under the roadmap"): added a DOCX §9
#     fallback (`report_recommendations.extract_recommendations_from_report_sections`)
#     that mines the Assessment_Report DOCX prose. Three shapes handled:
#     Alma-style heading-2-per-rec, Nicola-style heading + sub-blocks,
#     WSFS/Calprivate/Odlum-style body-inline IDs with `[ROOT CAUSE]` /
#     `[SOLUTION]` / `[EXPECTED OUTCOMES]` sub-block markers.
#   - F4 dedup-scoping fix: the `seen_kinds` dedup in dma_package.py was
#     collapsing WSFS's 5 cycles of `[ROOT CAUSE]` / `[SOLUTION]` /
#     `[EXPECTED OUTCOMES]` heading-3 blocks (one per rec) into one,
#     losing 4 of 5 rec bodies. Scoped to ACROSS-DOCX-only.


def test_f4_recs_extracted_from_docx_for_source_gap_folders():
    """F4 (revised): WSFS / Nicola / Calprivate ship no JSON rec source
    but the Assessment_Report.docx §9 carries the rec prose. The DOCX
    fallback must extract ≥4 recs for each.
    """
    expected_floors = {
        "WSFS_Bank__DMA": 4,        # 5 total; floor 4 to absorb minor extraction drift
        "Nicola_Wealth__DMA": 6,    # 7 total
        "Calprivate_Bank__DMA": 7,  # 8 total
    }
    for name, floor in expected_floors.items():
        pkg = parse_package(FIXTURES_ROOT / name)
        assert len(pkg.recommendations) >= floor, (
            f"{name}: DOCX §9 fallback failed — got "
            f"{len(pkg.recommendations)} recs; expected ≥{floor}"
        )
        # The DOCX-extraction warning must fire (operator visibility).
        assert any(
            "used docx-extracted recommendations" in w
            for w in pkg.parser_warnings
        ), (
            f"{name}: expected DOCX-extraction warning; "
            f"got {pkg.parser_warnings!r}"
        )
        # And `no_recommendations_source` must NOT fire (the recs were
        # found, even if via DOCX rather than JSON).
        assert not any(
            "no_recommendations_source" in w for w in pkg.parser_warnings
        ), (
            f"{name}: stale `no_recommendations_source` warning leaked"
        )


def test_f4_json_rec_path_still_preferred_when_present():
    """F4 cascade-guard: Alma (canonical
    `recommendations_detail.json`) and Odlum (variant
    `recommendations_register.json`) must continue to use the JSON
    path and NOT trigger the DOCX fallback. The JSON is richer than
    the DOCX-extracted text (root_cause / solution / expected_outcomes
    as structured dicts vs the DOCX's flat text).
    """
    for name, expected_recs in (
        ("Alma_Bank__DMA", 7),
        ("Odlum_BROWN__DMA", 6),
    ):
        pkg = parse_package(FIXTURES_ROOT / name)
        assert len(pkg.recommendations) == expected_recs, (
            f"{name}: expected {expected_recs} recs; got "
            f"{len(pkg.recommendations)}"
        )
        # JSON-derived recs have structured root_cause/solution as dicts;
        # DOCX-extracted recs have those as None (with a `source_body`
        # extra). If the DOCX fallback fired, root_cause would be a
        # `{"text": …}` dict synthesized by the extractor.
        # Catch by asserting the DOCX warning did NOT fire.
        assert not any(
            "used docx-extracted recommendations" in w
            for w in pkg.parser_warnings
        ), (
            f"{name}: JSON path should win; DOCX fallback should not "
            f"have fired. warnings={pkg.parser_warnings!r}"
        )


def test_f4_persistence_cascade_every_rec_has_real_description():
    """F4 persistence cascade-guard: every extracted rec must produce a
    real description (not just `title` fallback) via
    `package_persist._rec_description`. Catches three regression classes:

    1. DOCX extractor populates `root_cause/solution` with the WRONG key
       names (e.g. `{"text": ...}` instead of `{"gap_description": ...}`).
       `_rec_description` reads `gap_description` / `finding` / `description`;
       a mismatched key would return only the title.
    2. JSON variant (Odlum's `recommendations_register.json`) uses
       `root_cause.finding` (not `gap_description`); a regression in the
       fallback logic would drop Odlum's 6 rec bodies.
    3. New sub-block patterns drift (e.g. Calprivate `Root Cause:` vs.
       WSFS `[ROOT CAUSE]`) and `_extract_sub_blocks` falls behind.

    All 33 recs across all 5 fixtures must persist with non-title
    description content; floor is 100% to catch silent fidelity drift.
    """
    from app.services.parsers.package_persist import _rec_description

    total_recs = 0
    total_with_real_desc = 0
    per_folder: dict[str, tuple[int, int]] = {}
    for name in (
        "Alma_Bank__DMA",
        "Calprivate_Bank__DMA",
        "Nicola_Wealth__DMA",
        "Odlum_BROWN__DMA",
        "WSFS_Bank__DMA",
    ):
        pkg = parse_package(FIXTURES_ROOT / name)
        with_desc = 0
        for r in pkg.recommendations:
            d = _rec_description(r)
            if d and d != r.title and len(d) > len(r.title):
                with_desc += 1
        per_folder[name] = (with_desc, len(pkg.recommendations))
        total_recs += len(pkg.recommendations)
        total_with_real_desc += with_desc

    # 100% coverage required.
    assert total_recs > 0, "no recs extracted from any fixture; F4 regression"
    assert total_with_real_desc == total_recs, (
        f"persistence cascade gap: {total_with_real_desc}/{total_recs} "
        f"recs have real desc; per-folder breakdown: {per_folder}"
    )


def test_f4_rec_id_fits_persistence_column_width():
    """F4 cascade-guard: `package_persist.py:1046` truncates `rec.id`
    to 16 chars when inserting into `recommendations.rec_id`. Every
    extracted rec ID across the 5 fixtures must fit without truncation.
    """
    for name in (
        "Alma_Bank__DMA",
        "Calprivate_Bank__DMA",
        "Nicola_Wealth__DMA",
        "Odlum_BROWN__DMA",
        "WSFS_Bank__DMA",
    ):
        pkg = parse_package(FIXTURES_ROOT / name)
        for r in pkg.recommendations:
            assert len(r.id) <= 16, (
                f"{name} {r.id!r}: id length {len(r.id)} > 16-char "
                f"truncation cap in package_persist.py:1046; persistence "
                f"would silently drop {len(r.id) - 16} chars."
            )


# =========================================================================
# C9 — entity_profile.json prefers structured JSON over DOCX regex
# =========================================================================


def test_c9_calprivate_firmographics_use_entity_profile_json():
    """C9: when `08_appendices/entity_profile.json` is present (Calprivate
    among the 5 real fixtures), the parser prefers it over the DOCX
    regex path. The structured JSON carries ticker / founded date /
    branch_count / total_assets that the prose-regex extractor doesn't
    surface reliably.

    Cascade-guards:
      - The other 4 folders (which don't ship entity_profile.json)
        continue to use the handoff JSON → DOCX regex path as before.
      - The F5b leadership-merge from DOCX still fires even when
        firmographics came from JSON (additive merge per F5b-1).
    """
    pkg = parse_package(FIXTURES_ROOT / "Calprivate_Bank__DMA")
    firm = pkg.firmographics
    assert firm is not None
    dumped = firm.model_dump()
    # Fields that the regex path didn't produce but entity_profile.json
    # does. Each is a tight assertion to catch silent extraction drift.
    assert dumped.get("legal_name") == "CalPrivate Bank"
    assert dumped.get("ticker") == "OTCQX:PBAM"
    assert dumped.get("founded") == 2006
    assert dumped.get("hq") == "La Jolla, CA"
    assert dumped.get("primary_regulator") == "FDIC"
    # total_assets comes from financial_baseline (latest available
    # quarter). Calprivate's q3_2025 figure is $2.58B.
    assert dumped.get("total_assets") == "$2.58B"
    # `employees_approx` is a string per the schema contract (DOCX
    # regex produces strings; we match that).
    assert dumped.get("employees_approx") == "210"
    # `branches` is an extra field surfaced via `extra='allow'`.
    assert dumped.get("branches") == "8"
    # Operator-visibility warning fires.
    assert any(
        "firmographics_from_entity_profile_json" in w
        for w in pkg.parser_warnings
    ), f"expected C9 warning; got {pkg.parser_warnings!r}"


def test_c9_other_folders_unaffected_by_entity_profile_path():
    """C9 cascade-guard: the 4 folders without entity_profile.json
    (Alma / WSFS / Nicola / Odlum) must continue to use the existing
    handoff JSON / DOCX-regex paths and emit unchanged firmographics.
    """
    # Spot-check legal_name + at least one canonical field per folder.
    expected = {
        "Alma_Bank__DMA": ("Alma Bank", None),  # handoff path
        "WSFS_Bank__DMA": ("WSFS Financial Corporation", "WSFS"),
        "Nicola_Wealth__DMA": ("Nicola Wealth Management Ltd.", None),
        "Odlum_BROWN__DMA": ("Odlum Brown Limited", None),
    }
    for name, (expected_legal, expected_ticker) in expected.items():
        pkg = parse_package(FIXTURES_ROOT / name)
        f = pkg.firmographics
        assert f is not None
        d = f.model_dump()
        assert d.get("legal_name") == expected_legal, (
            f"{name}: legal_name regressed; got {d.get('legal_name')!r}"
        )
        # The entity_profile.json warning must NOT fire for these
        # folders (they don't ship the file).
        assert not any(
            "firmographics_from_entity_profile_json" in w
            for w in pkg.parser_warnings
        ), (
            f"{name}: entity_profile.json warning falsely fired; "
            f"warnings={pkg.parser_warnings!r}"
        )
        # WSFS-specific ticker pin (handoff JSON path produces it).
        if expected_ticker is not None:
            assert d.get("ticker") == expected_ticker


# =========================================================================
# C10 — caps_applied_log parsed across 4 of 5 folders
# =========================================================================


def test_c10_caps_applied_log_parses_across_all_4_folders_shipping_it():
    """C10: `07_governance/caps_applied_log.csv` parsed end-to-end. 4 of 5
    real fixtures ship the log; WSFS doesn't (it embeds equivalent
    semantics in `subcap_scores.caps_applied`).

    Pins the minimum row count per folder. Header-name variants
    (Alma's `Log_ID, SubCap_ID, Cap_Type, …` vs the other 3's
    `cap_id, cap_type, trigger_reason, affected_subcap, …`) all go
    through the alias table; this test catches a regression where a
    column-name shift drops one or more folders to 0.
    """
    expected = {
        "Alma_Bank__DMA": 8,
        "Calprivate_Bank__DMA": 100,  # 115 actual; floor 100 absorbs drift
        "Nicola_Wealth__DMA": 8,
        "Odlum_BROWN__DMA": 10,
    }
    for name, floor in expected.items():
        pkg = parse_package(FIXTURES_ROOT / name)
        actual = len(pkg.caps_applied_log)
        assert actual >= floor, (
            f"{name}: caps_applied_log = {actual}; expected ≥{floor}. "
            f"Likely a column-name shift; check `_HEADER_ALIASES` in "
            f"`caps_applied_log.py`."
        )
        # Operator-visibility warning fires.
        assert any(
            "caps_applied_log" in w and "parsed" in w
            for w in pkg.parser_warnings
        ), (
            f"{name}: expected `caps_applied_log: N parsed` warning; "
            f"got {pkg.parser_warnings!r}"
        )


def test_c10_wsfs_has_no_caps_applied_log_file_no_warning():
    """C10 cascade-guard: WSFS doesn't ship `caps_applied_log.csv`;
    the parser must NOT emit a parse warning for it. Catches a
    regression where the parser block falsely treats absence as a
    parser failure.
    """
    pkg = parse_package(FIXTURES_ROOT / "WSFS_Bank__DMA")
    assert len(pkg.caps_applied_log) == 0
    assert not any(
        "caps_applied_log" in w for w in pkg.parser_warnings
    ), (
        f"WSFS: spurious caps_applied_log warning; "
        f"warnings={pkg.parser_warnings!r}"
    )


def test_c10_caps_applied_log_row_shape_round_trips_model_dump():
    """C10 cascade-serialization guard: `CapsAppliedRow.model_dump()`
    must surface every declared field as JSON-serializable. This is
    the contract the persistence layer + API both use. Catches a
    regression where a field is renamed and the dump silently drops
    it.
    """
    pkg = parse_package(FIXTURES_ROOT / "Alma_Bank__DMA")
    assert len(pkg.caps_applied_log) >= 1
    cap = pkg.caps_applied_log[0]
    dumped = cap.model_dump()
    for k in (
        "log_id", "subcap_id", "cap_type", "trigger_condition",
        "cap_ceiling", "trigger_evidence", "affected_categories",
        "severity", "date_applied", "recalc_verified",
    ):
        assert k in dumped, (
            f"CapsAppliedRow.model_dump missing key {k!r}; schema regression"
        )
    # `trigger_evidence` should split CSV multi-value cells into a list.
    assert isinstance(dumped["trigger_evidence"], list)
    # `log_id` + `subcap_id` are required; must be non-empty strings.
    assert dumped["log_id"]
    assert dumped["subcap_id"]


def test_c10_persistence_field_widths_fit_db_columns():
    """C10 persistence cascade-guard: migration 028 sets per-column
    VARCHAR widths (log_id 64, subcap_id 64, cap_type 64, cap_ceiling
    32, severity 32, date_applied 32, recalc_verified 32). Every real-
    fixture value must fit; over-length values would silently get
    truncated in `package_persist`.
    """
    widths = {
        "log_id": 64,
        "subcap_id": 64,
        "cap_type": 64,
        "cap_ceiling": 32,
        "severity": 32,
        "date_applied": 32,
        "recalc_verified": 32,
    }
    for name in (
        "Alma_Bank__DMA",
        "Calprivate_Bank__DMA",
        "Nicola_Wealth__DMA",
        "Odlum_BROWN__DMA",
    ):
        pkg = parse_package(FIXTURES_ROOT / name)
        for cap in pkg.caps_applied_log:
            for field, max_len in widths.items():
                value = getattr(cap, field) or ""
                assert len(value) <= max_len, (
                    f"{name} {cap.log_id} {field}={value!r} "
                    f"({len(value)} chars) exceeds DB VARCHAR({max_len}); "
                    f"persistence would truncate."
                )


# =========================================================================
# C7 — bot governance audit logs (reasoning chain + contradictions)
# =========================================================================


def test_c7_audit_logs_extracted_per_folder():
    """C7: 2 of 5 fixtures ship at least one audit log component.
    Nicola: 12 reasoning chains + 3 contradictions; Odlum: 3
    contradictions (no reasoning chain file). Other 3 ship nothing.
    """
    expected = {
        "Alma_Bank__DMA": (None, None),
        "Calprivate_Bank__DMA": (None, None),
        # Nicola: reasoning_chain=12, contradictions=3
        "Nicola_Wealth__DMA": (12, 3),
        # Odlum: no reasoning chain file, but 3 contradictions
        "Odlum_BROWN__DMA": (0, 3),
        "WSFS_Bank__DMA": (None, None),
    }
    for name, (expected_chain, expected_contra) in expected.items():
        pkg = parse_package(FIXTURES_ROOT / name)
        if expected_chain is None and expected_contra is None:
            assert pkg.audit_logs is None, (
                f"{name}: audit_logs should be None when no files shipped"
            )
            continue
        assert pkg.audit_logs is not None
        actual_chain = len(pkg.audit_logs.reasoning_chain)
        actual_contra = len(pkg.audit_logs.contradictions)
        assert actual_chain == expected_chain, (
            f"{name}: reasoning_chain={actual_chain}; "
            f"expected {expected_chain}"
        )
        assert actual_contra == expected_contra, (
            f"{name}: contradictions={actual_contra}; "
            f"expected {expected_contra}"
        )


def test_c7_audit_warning_fires_when_logs_present():
    """C7 operator-observability: parser surfaces
    `governance_audit_logs: reasoning_chain=N contradictions=M`
    warning when audit files are found.
    """
    for name in ("Nicola_Wealth__DMA", "Odlum_BROWN__DMA"):
        pkg = parse_package(FIXTURES_ROOT / name)
        assert any(
            "governance_audit_logs" in w and "reasoning_chain" in w
            for w in pkg.parser_warnings
        ), (
            f"{name}: expected governance_audit_logs warning; "
            f"got {pkg.parser_warnings!r}"
        )


def test_c7_no_warning_when_no_audit_files():
    """C7 cascade-guard: folders without any audit log file must
    NOT emit a governance_audit_logs warning.
    """
    for name in (
        "Alma_Bank__DMA",
        "Calprivate_Bank__DMA",
        "WSFS_Bank__DMA",
    ):
        pkg = parse_package(FIXTURES_ROOT / name)
        assert pkg.audit_logs is None
        assert not any(
            "governance_audit_logs" in w for w in pkg.parser_warnings
        ), (
            f"{name}: spurious governance_audit_logs warning; "
            f"warnings={pkg.parser_warnings!r}"
        )


def test_c7_health_response_surfaces_audit_logs_field():
    """C7 API contract: HealthResponse declares `audit_logs` as a
    nullable AuditLogsOut field. Catches a regression that would
    leave the frontend AuditTab silently rendering an empty state.
    """
    from app.schemas.health import AuditLogsOut, HealthResponse
    assert "audit_logs" in HealthResponse.model_fields, (
        "HealthResponse.audit_logs missing; schema regression"
    )
    # AuditLogsOut accepts empty defaults.
    a = AuditLogsOut()
    assert a.reasoning_chain == []
    assert a.contradictions == []


def test_c7_reasoning_chain_row_has_decision_path_steps():
    """C7 cascade-serialization: each reasoning_chain row must have a
    non-empty decision_path list (the bot's actual reasoning steps).
    Catches a regression where the parser drops the field name or
    the JSON shape changes.
    """
    pkg = parse_package(FIXTURES_ROOT / "Nicola_Wealth__DMA")
    assert pkg.audit_logs is not None
    assert len(pkg.audit_logs.reasoning_chain) >= 1
    for chain in pkg.audit_logs.reasoning_chain:
        assert chain.subcap_id, (
            "reasoning_chain row missing subcap_id"
        )
        assert isinstance(chain.decision_path, list)
        # Each chain has at least 1 step in real fixtures (Nicola has 5).
        assert len(chain.decision_path) >= 1, (
            f"{chain.subcap_id}: empty decision_path; parser regression"
        )


# =========================================================================
# F5c D5 cascade-audit — narrative_md flows to D5 Context API contract
# =========================================================================


def test_f5c_d5_context_response_surfaces_narrative_md_when_present():
    """F5c follow-up: D5 ContextResponse must include `narrative_md`
    in the firmographics dict when the column is populated. This was
    a half-shipped state before the audit — D1 Overview surfaced it,
    but D5 Context's SELECT FROM firmographics didn't pull the column,
    so the ContextPage AboutCard rendered nothing.

    Pins the API schema is the right shape; the actual SELECT live-fires
    in the env-specific integration tests.
    """
    # No public schema for ContextResponse; verify the firmographics
    # dict shape by directly inspecting the column read in context.py
    # via a regex-grep guard. (Pure-Python tests can't hit a live DB.)
    import pathlib
    src = pathlib.Path(
        "app/routers/context.py"
    ).read_text(encoding="utf-8")
    assert "narrative_md" in src, (
        "context.py no longer references narrative_md; F5c follow-up "
        "regression — D5 AboutCard will go empty."
    )
    # And firmographics dict must include narrative_md when populated.
    assert "firmographics[\"narrative_md\"]" in src, (
        "context.py must inject narrative_md into the firmographics "
        "response dict so the frontend AboutCard can render it."
    )


# =========================================================================
# C8 — Alma scoring_scratchpad reclassification
# =========================================================================


def test_c8_alma_subcap_rationale_already_100pct_populated():
    """C8 cascade-guard: under-leveraged matrix §C8 hypothesized that
    Alma's `01_evidence/scoring_scratchpad.json` carried per-subcap
    rationale the parser ignored. Verified 2026-06-07: 100% of Alma's
    698 subcaps already carry the 700+ char rationale via the XLSX-
    enrichment path. C8 is mooted — no parser change needed.

    This test pins that the rationale IS being populated so a future
    contributor doesn't re-open C8 with the same mis-diagnosis.
    """
    pkg = parse_package(FIXTURES_ROOT / "Alma_Bank__DMA")
    total = len(pkg.subcap_scores)
    assert total == 698, (
        f"Alma subcap count drift: {total} != 698; update C8 pin floor."
    )
    with_rationale = sum(
        1 for s in pkg.subcap_scores
        if s.rationale and len(s.rationale) >= 100
    )
    # Floor 95% (664) absorbs minor XLSX drift without false alarms.
    assert with_rationale >= 664, (
        f"Alma subcap rationale coverage regressed: "
        f"{with_rationale}/{total} have ≥100 char rationale; "
        f"expected ≥664. If XLSX enrichment broke, C8 may need to "
        f"reopen via scoring_scratchpad.json parsing as a fallback."
    )


# =========================================================================
# C11 — assumptions register across the 5 real fixtures
# =========================================================================


def test_c11_assumptions_register_parses_per_folder():
    """C11: analyst's assumptions register. 2 of 5 fixtures ship it:
    Calprivate (5 entries, JSON) and Nicola (8 entries, CSV).
    The other 3 ship nothing -> empty list.
    """
    expected = {
        "Alma_Bank__DMA": 0,
        "Calprivate_Bank__DMA": 5,
        "Nicola_Wealth__DMA": 8,
        "Odlum_BROWN__DMA": 0,
        "WSFS_Bank__DMA": 0,
    }
    for name, expected_n in expected.items():
        pkg = parse_package(FIXTURES_ROOT / name)
        actual = len(pkg.assumptions_register)
        assert actual == expected_n, (
            f"{name}: assumptions_register = {actual}; expected {expected_n}. "
            f"If shape drifted, update parser aliases in "
            f"`assumptions_register.py`."
        )


def test_c11_assumptions_register_row_shape_round_trips():
    """C11 cascade-serialization guard: every parsed row must have
    `id` + `assumption` (the required schema fields) and round-trip
    through `model_dump()` cleanly. Catches a regression where the
    JSON or CSV parser drops one of the required fields.
    """
    for name in ("Calprivate_Bank__DMA", "Nicola_Wealth__DMA"):
        pkg = parse_package(FIXTURES_ROOT / name)
        assert len(pkg.assumptions_register) >= 1
        for row in pkg.assumptions_register:
            assert row.id, f"{name}: empty id on assumption row"
            assert row.assumption, (
                f"{name}: empty assumption text on row {row.id!r}"
            )
            dumped = row.model_dump()
            assert "id" in dumped and "assumption" in dumped
            # Basis + confidence are typed-but-optional; surface in dump
            # only when populated (Pydantic's standard behavior).
            assert isinstance(dumped, dict)


def test_c11_assumptions_warning_fires_when_register_present():
    """C11 operator-observability: parser surfaces an
    `assumptions_register: N parsed` warning when a register file is
    found. Admin import-audit picks it up.
    """
    for name in ("Calprivate_Bank__DMA", "Nicola_Wealth__DMA"):
        pkg = parse_package(FIXTURES_ROOT / name)
        assert any(
            "assumptions_register" in w and "parsed" in w
            for w in pkg.parser_warnings
        ), (
            f"{name}: expected assumptions_register parsed warning; "
            f"got {pkg.parser_warnings!r}"
        )


def test_c11_no_warning_when_register_absent():
    """C11 cascade-guard: folders without an assumptions register
    file must NOT emit a parser_warning. Catches a regression where
    the parser block falsely treats absence as a failure.
    """
    for name in ("Alma_Bank__DMA", "Odlum_BROWN__DMA", "WSFS_Bank__DMA"):
        pkg = parse_package(FIXTURES_ROOT / name)
        assert len(pkg.assumptions_register) == 0
        assert not any(
            "assumptions_register" in w for w in pkg.parser_warnings
        ), (
            f"{name}: spurious assumptions_register warning; "
            f"warnings={pkg.parser_warnings!r}"
        )


def test_c11_entity_overview_response_surfaces_assumptions_field():
    """C11 API contract: EntityOverviewResponse exposes
    `assumptions_register` as a declared Pydantic field with a
    default of empty list. Catches a regression where the field
    is dropped, which would make the frontend AssumptionsRegisterCard
    silently never render.
    """
    from app.schemas.entities import EntityOverviewResponse
    assert "assumptions_register" in EntityOverviewResponse.model_fields, (
        "EntityOverviewResponse.assumptions_register missing; "
        "schema regression"
    )


# =========================================================================
# C5 — L1/L2 QA verdict chain across the 5 real fixtures
# =========================================================================


def test_c5_l1_l2_verdict_chain_extracted_per_folder():
    """C5: 2-stage QA verdict chain. Two folders ship both verdicts
    (Odlum + Calprivate); the other 3 ship only L2. Pin both sides
    of the cascade.
    """
    expected = {
        "Alma_Bank__DMA": (None, "PASS_WITH_NOTES"),
        "Calprivate_Bank__DMA": ("PASS", "PASS_WITH_NOTES"),
        "Nicola_Wealth__DMA": (None, "PASS_WITH_NOTES"),
        "Odlum_BROWN__DMA": ("PASS", "PASS_WITH_NOTES"),
        "WSFS_Bank__DMA": (None, "PASS_WITH_NOTES"),
    }
    for name, (expected_l1, expected_l2) in expected.items():
        pkg = parse_package(FIXTURES_ROOT / name)
        l1 = pkg.qa_verdict_l1.verdict if pkg.qa_verdict_l1 else None
        l2 = pkg.qa_verdict.verdict if pkg.qa_verdict else None
        assert l1 == expected_l1, (
            f"{name}: qa_verdict_l1.verdict expected {expected_l1!r}, "
            f"got {l1!r}"
        )
        assert l2 == expected_l2, (
            f"{name}: qa_verdict (L2).verdict expected {expected_l2!r}, "
            f"got {l2!r}"
        )


def test_c5_escalation_warning_fires_when_both_verdicts_present():
    """C5: when L1 + L2 both ship, the parser surfaces a
    `qa_verdict_l1_l2_pair` warning capturing the escalation chain.
    Catches a regression where the warning is dropped (admin
    import-audit observability).
    """
    for name in ("Calprivate_Bank__DMA", "Odlum_BROWN__DMA"):
        pkg = parse_package(FIXTURES_ROOT / name)
        assert pkg.qa_verdict_l1 is not None
        assert pkg.qa_verdict is not None
        assert any(
            "qa_verdict_l1_l2_pair" in w for w in pkg.parser_warnings
        ), (
            f"{name}: expected qa_verdict_l1_l2_pair warning; "
            f"got {pkg.parser_warnings!r}"
        )


def test_c5_health_response_surfaces_l1_l2_verdict_fields():
    """C5 API contract: HealthResponse exposes both qa_verdict_l1
    and qa_verdict_l2 as declared Pydantic fields. Catches a
    regression where either field is dropped from the schema, which
    would make the frontend VerdictChainCard silently render null.
    """
    from app.schemas.health import HealthResponse, QaVerdictOut
    for f in ("qa_verdict_l1", "qa_verdict_l2"):
        assert f in HealthResponse.model_fields, (
            f"HealthResponse.{f} missing; schema regression"
        )
    # Round-trip QaVerdictOut serialization.
    sample = QaVerdictOut(
        verdict="PASS_WITH_NOTES",
        recommendation="DELIVER",
        verdict_basis="all checks satisfied",
    )
    dumped = sample.model_dump()
    for k in (
        "verdict", "recommendation", "verdict_basis",
        "governance_skill_version",
    ):
        assert k in dumped, (
            f"QaVerdictOut.model_dump missing key {k!r}"
        )


def test_c5_l1_verdict_filename_variants_recognized():
    """C5 cascade-guard: the parser's L1 detection must recognize
    BOTH `L1_qa_verdict.json` (Odlum) AND `Layer1_qa_verdict.json`
    (Calprivate). A regression where one variant is dropped would
    lose half the L1 coverage.
    """
    odlum = parse_package(FIXTURES_ROOT / "Odlum_BROWN__DMA")
    calprivate = parse_package(FIXTURES_ROOT / "Calprivate_Bank__DMA")
    assert odlum.qa_verdict_l1 is not None, (
        "Odlum L1_qa_verdict.json not recognized — filename variant drift"
    )
    assert calprivate.qa_verdict_l1 is not None, (
        "Calprivate Layer1_qa_verdict.json not recognized — variant drift"
    )


def test_c10_health_response_surfaces_caps_applied_field():
    """C10 API contract: `HealthResponse.caps_applied` is a declared
    Pydantic field. Catches a regression where the field is dropped
    from the schema, which would make the frontend Caps tab silently
    render the empty state for every entity.
    """
    from app.schemas.health import CapsAppliedOut, HealthResponse
    assert "caps_applied" in HealthResponse.model_fields, (
        "HealthResponse.caps_applied missing; schema regression. "
        "Frontend Caps tab depends on this field."
    )
    # Empty default works (HealthResponse can be constructed without
    # passing caps_applied).
    hr = HealthResponse(entity_display_id="test")
    assert hr.caps_applied == []
    # Round-trip serialization round-trips through model_dump.
    sample = CapsAppliedOut(
        log_id="IR-001",
        subcap_id="P3C3",
        cap_type="REGULATORY",
        trigger_condition="severity cap triggered",
        cap_ceiling="3.0",
        trigger_evidence=["E-004", "E-016"],
        affected_categories=["P3C3"],
        severity="HIGH",
    )
    dumped = sample.model_dump()
    for k in (
        "log_id", "subcap_id", "cap_type", "trigger_condition",
        "cap_ceiling", "trigger_evidence", "affected_categories",
        "severity", "date_applied", "recalc_verified",
    ):
        assert k in dumped, (
            f"CapsAppliedOut.model_dump missing key {k!r}"
        )


def test_f4_rec_titles_are_clean_strings():
    """F4 cascade-guard: extracted titles must not retain leading
    title-separator characters (em-dash, en-dash, ASCII hyphen, or
    colon). A regression here means `_split_title_from_heading` is
    leaving the title-separator on the front of the title.
    """
    for name in ("WSFS_Bank__DMA", "Nicola_Wealth__DMA",
                 "Calprivate_Bank__DMA"):
        pkg = parse_package(FIXTURES_ROOT / name)
        for r in pkg.recommendations:
            t = (r.title or "").strip()
            # em-dash (U+2014), en-dash (U+2013), ASCII hyphen, colon —
            # the title-separator chars `_TITLE_SEP_RE` strips.
            assert not t.startswith(("—", "–", "-", ":")), (  # noqa: RUF001
                f"{name} rec {r.id}: title starts with a separator: {t!r}"
            )
            assert len(t) >= 5, (
                f"{name} rec {r.id}: title too short ({len(t)} chars): {t!r}"
            )


# =========================================================================
# F5c — firmographics.narrative_md threaded parser → schema → API
# =========================================================================


def test_f5c_narrative_md_populated_across_all_5_folders():
    """F5c: every real client's Client Profile DOCX has an Entity Profile
    section; client_profile.py extracts it as `firmographics_narrative_md`
    (198-1583 chars), and the dma_package parser now threads it onto
    `IngestedPackage.firmographics.narrative_md` (was discarded prior).

    Conservative floor: each folder ≥ 100 chars. Catches a regression
    where the parser stops mining the section, or the schema field is
    dropped, or the F5b merge block accidentally clears the prior value.
    """
    expected_floors = {
        "Alma_Bank__DMA": 200,
        "WSFS_Bank__DMA": 100,
        "Nicola_Wealth__DMA": 500,
        "Odlum_BROWN__DMA": 1000,
        "Calprivate_Bank__DMA": 200,
    }
    for name, floor in expected_floors.items():
        pkg = parse_package(FIXTURES_ROOT / name)
        firm = pkg.firmographics
        assert firm is not None, f"{name}: firmographics is None"
        narrative = getattr(firm, "narrative_md", None) or ""
        assert len(narrative) >= floor, (
            f"{name}: narrative_md too short ({len(narrative)} chars; "
            f"expected ≥{floor})"
        )


def test_f5c_narrative_md_field_is_pydantic_declared():
    """Cascade-guard: `narrative_md` must be a declared Pydantic field
    on `Firmographics` (not just an extra). Catches a regression where
    the schema drops the field and the API SELECT then fails.
    """
    from app.schemas.package import Firmographics
    assert "narrative_md" in Firmographics.model_fields, (
        "narrative_md missing from Firmographics.model_fields; "
        "schema regression — re-add the typed field."
    )


# =========================================================================
# C1 reclassification — Nicola per-pillar XLSX is a subvertical TOOLKIT,
# not evidence
# =========================================================================
# See `docs/qa/qa_ingestion_under_leveraged.md` §C1 for the full
# reclassification writeup. The original under-leveraged matrix
# hypothesized that Nicola's 4 `Nicola_Wealth_P{1,2,3,4}_Research.xlsx`
# files were P1C1..P4C4 splits of the canonical research workbook and
# that the parser was losing 3/4 of the evidence. Verification on the
# real fixture proves they're subvertical-keyed scoring toolkits
# (Credit Unions, Regional Banks, Lending, …) with capability-mapping
# rubrics — NOT assessment-specific evidence about Nicola.


def test_c1_nicola_per_pillar_xlsx_is_subvertical_toolkit_not_evidence():
    """C1 cascade-guard: `parse_per_pillar_sheets` returns 0 rows on
    each of Nicola's per-pillar XLSX files because the sheets are
    subvertical-keyed toolkits, not evidence. A future contributor
    must not "fix" this by globbing all 4 files and feeding them
    through the canonical research-workbook parser — that pipeline
    is shape-incompatible.

    If Nicola's package switches to the canonical shape (1 XLSX with
    P1C1..P4C4 sheets) this test will start surfacing rows and
    SHOULD be updated to assert non-zero. Until then, this is the
    pin that prevents the wrong fix.
    """
    from openpyxl import load_workbook

    from app.services.parsers.research_workbook import parse_per_pillar_sheets

    rw_dir = FIXTURES_ROOT / "Nicola_Wealth__DMA" / "02_research_workbook"
    xlsx_files = sorted(rw_dir.glob("*.xlsx"))
    assert len(xlsx_files) == 4, (
        f"expected 4 per-pillar XLSX files; got {len(xlsx_files)}"
    )
    for xlsx in xlsx_files:
        wb = load_workbook(xlsx, data_only=True)
        result = parse_per_pillar_sheets(wb)
        assert len(result.rows) == 0, (
            f"{xlsx.name}: per-pillar parser yielded {len(result.rows)} "
            f"rows — Nicola's package shape may have changed from "
            f"subvertical toolkit to canonical P1C1..P4C4 split; "
            f"update C1 in qa_ingestion_under_leveraged.md."
        )


# =========================================================================
# Cascade integration — schema serialization for F5b leadership + F5c
# narrative_md round-trips through `IngestedPackage.model_dump()` so the
# JSONB persistence + API response paths can't accidentally drop them.
# =========================================================================


def test_cascade_firmographics_dumps_leadership_and_narrative_md():
    """Cascade integration guard: `Firmographics.model_dump()` (the
    serialization the API + persistence layers both use) must include
    the F5b leadership list AND the F5c narrative_md field for all 5
    real fixtures.

    Catches a regression where `model_config["extra"]="allow"` lets a
    field exist on the instance but `model_dump()` silently drops it
    (e.g. someone changes the field to be a computed-property rather
    than a declared field).
    """
    for name in (
        "Alma_Bank__DMA",
        "WSFS_Bank__DMA",
        "Nicola_Wealth__DMA",
        "Odlum_BROWN__DMA",
        "Calprivate_Bank__DMA",
    ):
        pkg = parse_package(FIXTURES_ROOT / name)
        firm = pkg.firmographics
        assert firm is not None
        dumped = firm.model_dump()
        assert "leadership" in dumped, (
            f"{name}: leadership key missing from model_dump"
        )
        assert "narrative_md" in dumped, (
            f"{name}: narrative_md key missing from model_dump"
        )
        # narrative_md must be a string with non-trivial content
        # (every real fixture has ≥100 chars; <100 indicates extraction
        # regression).
        assert isinstance(dumped["narrative_md"], str), (
            f"{name}: narrative_md not a string: "
            f"{type(dumped['narrative_md']).__name__}"
        )
        assert len(dumped["narrative_md"]) >= 100, (
            f"{name}: narrative_md too short ({len(dumped['narrative_md'])} chars)"
        )
        # leadership must be a non-empty list of dicts (each with name + title).
        assert isinstance(dumped["leadership"], list), (
            f"{name}: leadership not a list"
        )
        for L in dumped["leadership"][:3]:
            assert isinstance(L, dict), f"{name}: leadership entry not a dict"
            assert "name" in L, f"{name}: leadership entry missing `name`"
            assert "title" in L, f"{name}: leadership entry missing `title`"


def test_f5b_leadership_names_are_clean_strings():
    """F5b cascade-guard: names must not carry embedded newlines or
    semicolons — that's a sign the combined-cell split fell through.
    """
    pkg = parse_package(FIXTURES_ROOT / "Nicola_Wealth__DMA")
    firm = pkg.firmographics
    assert firm is not None
    for L in (firm.leadership or []):
        assert "\n" not in L.name, (
            f"unsplit name on Nicola: {L.name!r}"
        )
        # title may carry tenure data on a newline (Odlum shape) — that's
        # acceptable; only `name` is required to be a clean string.




# =========================================================================
# Validation corpus (real committed packages) — parser-robustness
# =========================================================================
# The 2026-06-07 DMA batch uploads (35 real client packages) are
# committed under `tests/fixtures/dma_packages_batches/`. These tests
# pin the robustness fixes against the REAL packages (no synthetic
# dummy fixtures). They skip cleanly when the corpus isn't present.

CORPUS_ROOT = (
    Path(__file__).parent / "fixtures" / "dma_packages_batches"
)


def _corpus_root(client_glob: str) -> Path | None:
    """Resolve a client folder (by name fragment) to its canonical
    package root within the committed corpus, or None if absent."""
    if not CORPUS_ROOT.is_dir():
        return None
    hits = sorted(CORPUS_ROOT.glob(f"*/{client_glob}*"))
    if not hits:
        return None
    cl = hits[0]
    for sub in [cl] + [d for d in cl.rglob("*") if d.is_dir()]:
        try:
            kids = {x.name for x in sub.iterdir() if x.is_dir()}
        except OSError:
            continue
        if any(k.startswith(("01_evidence", "03_scoring", "04_report")) for k in kids):
            return sub
    return cl


def test_corpus_clean_institution_from_folder_strips_dma_suffixes():
    """Inst-name folder-fallback (A1): `Ameris Bank - DMA` / `SPG - DMA`
    / `Valley Bank - DMA` / `ZipHQ - DMA` previously rendered as mangled
    `Ameris Bank   DMA` (triple space + retained DMA) in every page
    header. The cleaner strips the suffix + collapses whitespace.
    Pure-function test — no fixture needed.
    """
    from app.services.parsers.dma_package import _clean_institution_from_folder
    cases = {
        "Ameris Bank - DMA": "Ameris Bank",
        "SPG - DMA": "SPG",
        "Valley Bank - DMA": "Valley Bank",
        "ZipHQ - DMA": "ZipHQ",
        "Penderfund DMA": "Penderfund",
        "Empower_FCU_DMA_Full_Package": "Empower FCU",
        "Amarillo_National_Bank_DMA_Complete_Package": "Amarillo National Bank",
        "First Citizens - DMA": "First Citizens",
    }
    for folder, expected in cases.items():
        got = _clean_institution_from_folder(folder)
        assert got == expected, (
            f"_clean_institution_from_folder({folder!r}) = {got!r}; "
            f"expected {expected!r}"
        )
    for folder in cases:
        out = _clean_institution_from_folder(folder)
        assert "  " not in out, f"double space leaked: {out!r}"
        assert not out.endswith(" DMA"), f"DMA suffix retained: {out!r}"


def test_corpus_evidence_rows_from_json_helper_shapes():
    """Unit (A4): `_evidence_rows_from_json` tolerates items-wrapped,
    `evidence_items`-wrapped (Zions), and top-level-list JSON + the
    key-alias set. Pure-function test — no fixture needed.
    """
    import json as _json
    import tempfile

    from app.services.parsers.dma_package import _evidence_rows_from_json
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump({"items": [
            {"e_id": "E-1", "source_name": "S1", "tier": "T2",
             "subcap_mappings": ["P1C1.1.1"]},
        ]}, f)
        wrapped_path = Path(f.name)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump([
            {"evidence_id": "E-2", "source_file": "S2", "tier": 3,
             "mapped_subcaps": ["P2C1.1.1"]},
        ], f)
        list_path = Path(f.name)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump({"evidence_items": [
            {"evidence_id": "E-3", "source_name": "S3", "tier": 1},
        ]}, f)
        items_path = Path(f.name)
    warns: list[str] = []
    wrapped = _evidence_rows_from_json(wrapped_path, warns)
    listed = _evidence_rows_from_json(list_path, warns)
    zions_shape = _evidence_rows_from_json(items_path, warns)
    assert len(wrapped) == 1 and wrapped[0].e_id == "E-1"
    assert wrapped[0].tier == 2  # "T2" -> 2
    assert len(listed) == 1 and listed[0].e_id == "E-2"
    assert listed[0].source_name == "S2"  # source_file alias
    assert "P2C1.1.1" in listed[0].subcap_mappings  # mapped_subcaps alias
    assert len(zions_shape) == 1 and zions_shape[0].e_id == "E-3"  # evidence_items
    for p in (wrapped_path, list_path, items_path):
        p.unlink()


def test_corpus_alliant_recovered_via_synthesis():
    """A2/A3 (real corpus): Alliant ships NO run_manifest/qa_verdict —
    only `07_governance/00_parameters.json` + `01_evidence/research_
    handoff.json`. Either synthesis path (handoff wins the order here,
    yielding DMA-RES; 00_parameters is the DMA-ASM fallback) must
    fully recover the package. Was a hard FAIL before these fixes."""
    root = _corpus_root("Alliant Insurance")
    if root is None:
        pytest.skip("Alliant not in committed corpus")
    pkg = parse_package(root)
    assert pkg.run_manifest is not None
    assert "ALLI" in pkg.run_manifest.run_id
    assert pkg.run_manifest.institution_name == "Alliant Insurance Services"
    assert len(pkg.subcap_scores) >= 600
    assert len(pkg.evidence) >= 100
    # A synthesis fallback (handoff or 00_parameters) must have fired.
    assert any(
        "synthesized run_manifest" in w or "00_parameters" in w
        for w in pkg.parser_warnings
    ), f"no synthesis warning; got {pkg.parser_warnings!r}"


def test_corpus_00_parameters_synthesizer_unit():
    """A2 unit: `_synthesize_run_manifest_from_parameters` reads
    assessment_id + entity + subvertical + integer pillar_weights from
    a 07_governance/00_parameters.json and normalizes weights to 0-1.
    Direct pure-function test on a temp dir (no fixture)."""
    import json as _json
    import tempfile

    from app.services.parsers.dma_package import (
        _synthesize_run_manifest_from_parameters,
    )
    with tempfile.TemporaryDirectory() as td:
        gov = Path(td) / "07_governance"
        gov.mkdir()
        (gov / "00_parameters.json").write_text(_json.dumps({
            "assessment_id": "DMA-ASM-UNIT-20260607-0001",
            "research_id": "DMA-RES-UNIT-20260607-0001",
            "entity": "Unit Test Entity",
            "subvertical": "SV3",
            "evidence_mode": "HYBRID",
            "pillar_weights": {"P1": 20, "P2": 35, "P3": 20, "P4": 25},
        }))
        warns: list[str] = []
        rm = _synthesize_run_manifest_from_parameters(Path(td), warns)
    assert rm is not None
    assert rm.run_id == "DMA-ASM-UNIT-20260607-0001"
    assert rm.institution_name == "Unit Test Entity"
    assert rm.subvertical_code == "SV3"
    assert rm.pillar_weights is not None
    assert abs(sum(rm.pillar_weights.values()) - 1.0) < 0.001


def test_corpus_rockland_toplevel_list_json_evidence():
    """A4 (real corpus): Rockland ships `evidence_index_master.json` as
    a top-level list with `evidence_id`/`mapped_subcaps` keys."""
    root = _corpus_root("Rockland Trust")
    if root is None:
        pytest.skip("Rockland not in committed corpus")
    pkg = parse_package(root)
    assert len(pkg.evidence) >= 200, (
        f"Rockland evidence under-extracted: {len(pkg.evidence)}"
    )


def test_corpus_chemung_camelcase_run_manifest():
    """CamelCase fix (real corpus): Chemung's only manifest is
    `08_appendices/DMA_CCTRUST_Run_Manifest.json` (CamelCase) — was a
    hard FAIL under the case-sensitive glob."""
    root = _corpus_root("Chemung Canal Trust")
    if root is None:
        pytest.skip("Chemung not in committed corpus")
    pkg = parse_package(root)
    assert pkg.run_manifest is not None
    assert pkg.run_manifest.run_id.startswith("DMA-ASM-CCTRUST")
    assert len(pkg.subcap_scores) >= 600


def test_corpus_first_citizens_root_detection_and_misplaced_evidence():
    """§B (real corpus): First Citizens ships `06_peers/MANIFEST.json`
    (MANIFEST inside a numbered subfolder) + `evidence_index.csv` inside
    `03_scoring_workbook/`. Root-detection must NOT re-root onto
    06_peers, and the misplaced-evidence fallback must recover evidence."""
    root = _corpus_root("First Citizens")
    if root is None:
        pytest.skip("First Citizens not in committed corpus")
    pkg = parse_package(root)
    # Root-detection fix: subcaps populate (would be 0 if re-rooted onto 06_peers).
    assert len(pkg.subcap_scores) >= 600, (
        f"First Citizens root mis-detected: {len(pkg.subcap_scores)} subcaps"
    )
    # Misplaced-evidence fallback: evidence populates from 03_scoring/.
    assert len(pkg.evidence) >= 100, (
        f"First Citizens evidence not recovered: {len(pkg.evidence)}"
    )
    assert pkg.run_manifest.institution_name.startswith("First Citizens")


def test_corpus_zions_consolidated_xlsx_scoring_sheet():
    """§B (real corpus): Zions ships a single consolidated
    `Scoring_Workbook` sheet (not per-pillar sheets) + an
    `evidence_items`-keyed evidence_index.json. Both must parse."""
    root = _corpus_root("Zions Bancorporation")
    if root is None:
        pytest.skip("Zions not in committed corpus")
    pkg = parse_package(root)
    assert len(pkg.subcap_scores) >= 100, (
        f"Zions consolidated XLSX sheet not parsed: {len(pkg.subcap_scores)}"
    )
    assert len(pkg.evidence) >= 50, (
        f"Zions evidence_items not parsed: {len(pkg.evidence)}"
    )


def test_corpus_camelcase_verdict_manifest_fallback_unit():
    """Stress corpus (Farm Credit / IBKR / Vornado / ANBTX): a package
    whose ONLY manifest is a CamelCase `*_QA_Verdict.json` or
    `DMA_GovernanceVerdict_*.json` (no run_manifest / handoff /
    00_parameters) was a hard FAIL. The late case-insensitive verdict
    fallback recovers it; a verdict file lacking an institution name
    falls back to the cleaned folder name.

    Pure-function test on a temp dir — exercises the fallback without a
    committed fixture.
    """
    import json as _json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "Acme Bank - DMA"
        gov = root / "07_governance"
        sc = root / "03_scoring_workbook"
        gov.mkdir(parents=True)
        sc.mkdir(parents=True)
        # CamelCase verdict file, run_id only (no institution_name).
        (gov / "DMA_GovernanceVerdict_ACME_20260607.json").write_text(
            _json.dumps({
                "run_id": "DMA-RES-ACME-20260607-0001",
                "verdict": "PASS",
                "action": "DELIVER",
            })
        )
        (sc / "export_scoring_detail.csv").write_text(
            "SubCap_ID,Category,Score,Evidence_Ceiling,Caps_Applied,Confidence\n"
            "P1C1.1.1,P1C1,2.5,4.5,,HIGH\n"
        )
        pkg = parse_package(root)
    assert pkg.run_manifest is not None
    assert pkg.run_manifest.run_id == "DMA-RES-ACME-20260607-0001"
    # Institution fell back to the cleaned folder name (verdict had none).
    assert pkg.run_manifest.institution_name == "Acme Bank"
    assert len(pkg.subcap_scores) == 1
    assert any("verdict fallback" in w for w in pkg.parser_warnings)


def test_corpus_evidence_json_bounds_oversized_fields():
    """Stress corpus (Kitsap 55-char / SL Green 525-char mapped_subcaps,
    Sunflower 58-char e_id): `_evidence_rows_from_json` must drop
    over-length / non-subcap-shaped mappings (col VARCHAR(32)[]) and
    bound e_id to 16 chars (col VARCHAR(16)) so persistence never
    StringDataRightTruncation-aborts the ingest. Pure-function test.
    """
    import json as _json
    import tempfile

    from app.services.parsers.dma_package import _evidence_rows_from_json
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump([
            {
                "evidence_id": "E-" + ("X" * 60),  # 62-char malformed id
                "source_name": "S",
                "tier": 3,
                "mapped_subcaps": [
                    "P1C1.1.1",                       # valid, keep
                    "P2C3 " + ("y" * 60),            # 65-char garbage, drop
                    "not-a-subcap",                   # wrong shape, drop
                ],
            },
        ], f)
        p = Path(f.name)
    warns: list[str] = []
    rows = _evidence_rows_from_json(p, warns)
    p.unlink()
    assert len(rows) == 1
    r = rows[0]
    assert len(r.e_id) <= 16, f"e_id not bounded: {len(r.e_id)}"
    # Only the well-formed, in-width subcap survives.
    assert r.subcap_mappings == ["P1C1.1.1"], r.subcap_mappings
    for s in r.subcap_mappings:
        assert len(s) <= 32


def test_tier_canonical_taxonomy_or_none_all_layers():
    """Evidence tier must land in the CANONICAL taxonomy [1, 7] or be None.

    The 2026-06-07 corpus (Amarillo National Bank E-050) ships synthetic
    proxy-synthesis tiers — ``T10``, ``T10-CONTRADICTORY``, ``T7-PROXY``,
    ``T4-PROXY``. The old contract CLAMPED out-of-range labels (T10 → 8)
    and DEFAULTED missing ones to 5 — both fabricated tiers that polluted
    the live evidence drawer's distribution ("Tier 8" rows, 2026-07-06 QA;
    no research-workbook taxonomy defines a T8). New contract at every
    layer — CSV (``_tier_int``), JSON (``_evidence_rows_from_json``), and
    the universal keystone (``EvidenceRow``'s validator): faithful tiers
    (T7-PROXY → 7) survive; out-of-taxonomy / missing → honest None
    (nullable column per migration 055 — ingest still never aborts).
    """
    import json as _json
    import tempfile

    from app.schemas.package import EvidenceRow
    from app.services.parsers.dma_package import _evidence_rows_from_json
    from app.services.parsers.package_csvs import _tier_int

    # ── CSV layer ──────────────────────────────────────────────────
    assert _tier_int("T10") is None             # out of taxonomy — no clamp
    assert _tier_int("T10-CONTRADICTORY") is None
    assert _tier_int("T7-PROXY") == 7           # suffixed, faithful
    assert _tier_int("T4-PROXY") == 4           # suffixed, faithful
    assert _tier_int("T1") == 1
    assert _tier_int("T8") is None              # no taxonomy defines T8
    assert _tier_int("10") is None              # bare numeric out of range
    assert _tier_int("T0") is None              # below floor — not clamped up
    assert _tier_int(None) is None              # missing → honest-absent
    assert _tier_int("HIGH") is None            # confidence word, not a tier
    assert _tier_int("T1, T2, T3") is None      # ambiguous SET cell
    assert _tier_int("T2, T2") == 2             # repeated single value

    # ── JSON layer ─────────────────────────────────────────────────
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump([
            {"evidence_id": "E-050", "source_name": "S", "tier": "T10"},
            {"evidence_id": "E-051", "source_name": "S", "tier": "T7-PROXY"},
            {"evidence_id": "E-052", "source_name": "S", "tier": 99},
        ], f)
        p = Path(f.name)
    rows = _evidence_rows_from_json(p, [])
    p.unlink()
    by_id = {r.e_id: r.tier for r in rows}
    assert by_id == {"E-050": None, "E-051": 7, "E-052": None}, by_id

    # ── Keystone: EvidenceRow validator (covers all paths + stubs) ──
    for raw, expected in [(10, None), (99, None), (0, None), (-3, None),
                          (8, None), (7, 7), (1, 1), (None, None),
                          ("T3", 3), ("garbage", None)]:
        got = EvidenceRow(e_id="E", source_name="s", tier=raw, excerpt="x").tier
        assert got == expected, f"tier={raw} -> {got}, want {expected}"
