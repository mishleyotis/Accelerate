"""Unit tests for the materiality classifier + manifest hash + diff.

Per the 2026-06-07 operator mandate: "A reingest should strictly be
for the changed artifact, and ONLY if the information influences the
DMA. If it was a cosmetic change, this can just be dropped."

These tests pin the contract:
  - decks / images / search logs / OS cruft ⇒ COSMETIC (no rehash impact)
  - scoring / evidence / DOCX / manifest / qa_verdict / caps /
    recommendations / peer JSONs ⇒ MATERIAL
  - unknown artifacts ⇒ UNKNOWN (treated as material defensively)
  - material_manifest_hash is stable when only cosmetic files flip
  - material_manifest_hash changes when any material file flips
  - diff classifies added / removed / modified material files
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from app.services.artifact_manifest import (
    ALL_TABLES,
    COSMETIC,
    MATERIAL,
    UNKNOWN,
    affected_tables,
    classify_path,
    compute_package_manifest,
    diff_manifests,
    material_changes_count,
    skip_tables_for_diff,
    summarize_diff,
)


def test_classify_material_evidence_index_csv():
    assert classify_path("01_evidence/evidence_index.csv") == MATERIAL


def test_classify_material_evidence_index_json():
    assert classify_path("01_evidence/evidence_index.json") == MATERIAL


def test_classify_material_scoring_csv():
    assert classify_path("03_scoring_workbook/export_scoring_detail.csv") == MATERIAL


def test_classify_material_scoring_xlsx_real_filename():
    # Pentegra ships DMA_Scoring_Workbook_Pentegra.xlsx
    rp = "03_scoring_workbook/DMA_Scoring_Workbook_Pentegra.xlsx"
    assert classify_path(rp) == MATERIAL


def test_classify_material_research_xlsx():
    assert classify_path(
        "02_research_workbook/DMA_Research_Workbook.xlsx"
    ) == MATERIAL


def test_classify_material_assessment_report_docx():
    rp = "04_reports/AlmaBank_DMA_Assessment_Report_FINAL.docx"
    assert classify_path(rp) == MATERIAL


def test_classify_material_client_profile_docx():
    rp = "04_reports/AlmaBank_Client_Profile_Research_Report.docx"
    assert classify_path(rp) == MATERIAL


def test_classify_material_run_manifest_camelcase():
    # Chemung ships 08_appendices/DMA_CCTRUST_Run_Manifest.json
    rp = "08_appendices/DMA_CCTRUST_Run_Manifest.json"
    assert classify_path(rp) == MATERIAL


def test_classify_material_misplaced_run_manifest_in_01_evidence():
    # Pentegra fixture corner case.
    assert classify_path("01_evidence/run_manifest.json") == MATERIAL


def test_classify_material_qa_verdict_with_prefix():
    # Real corpus: 07_governance/qa_verdict.json (canonical),
    # or AlmaBank_QA_Verdict.json variant — both must classify
    # MATERIAL.
    assert classify_path("07_governance/qa_verdict.json") == MATERIAL
    assert classify_path("07_governance/AlmaBank_qa_verdict.json") == MATERIAL


def test_classify_material_caps_applied_log():
    assert classify_path("07_governance/caps_applied_log.csv") == MATERIAL


def test_classify_material_recommendations_detail():
    rp = "08_appendices/recommendations_detail.json"
    assert classify_path(rp) == MATERIAL


def test_classify_material_peer_scores_json():
    assert classify_path("06_peers/peer_scores_Peer_Alpha.json") == MATERIAL


def test_classify_material_manifest_root():
    assert classify_path("MANIFEST.json") == MATERIAL


def test_classify_cosmetic_narrative_deck_pptx():
    rp = "05_narrative_deck/AlmaBank_DMA_Story_Deck.pptx"
    assert classify_path(rp) == COSMETIC


def test_classify_cosmetic_narrative_deck_pdf():
    assert classify_path("05_narrative_deck/Talk_Track.pdf") == COSMETIC


def test_classify_cosmetic_search_log_appendix():
    # Amarillo / Vestgen ship A2_search_log / A9_org_capability_proxies.csv
    assert classify_path("08_appendices/A2_search_log.csv") == COSMETIC
    assert classify_path(
        "08_appendices/A9_Proxy_Search_Log_VESTGEN.csv"
    ) == COSMETIC


def test_classify_cosmetic_embedded_png_image():
    assert classify_path("04_reports/figures/heatmap.png") == COSMETIC


def test_classify_cosmetic_macosx_cruft():
    assert classify_path("__MACOSX/._Assessment_Report.docx") == COSMETIC


def test_classify_cosmetic_ds_store():
    assert classify_path("01_evidence/.DS_Store") == COSMETIC


def test_classify_unknown_arbitrary_file():
    # An unrecognized artifact in a non-canonical subdir falls through
    # to UNKNOWN — backfill treats it as MATERIAL defensively.
    assert classify_path("09_future_artifact/new_thing.txt") == UNKNOWN


def test_manifest_hash_stable_when_only_cosmetic_changes():
    """Touching a deck must NOT change the material_manifest_hash."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_evidence").mkdir()
        (root / "01_evidence" / "evidence_index.csv").write_text(
            "evidence_id,tier\nE-001,T3\n"
        )
        (root / "05_narrative_deck").mkdir()
        deck = root / "05_narrative_deck" / "story.pptx"
        deck.write_bytes(b"original deck bytes")

        m1 = compute_package_manifest(root)

        # Swap the deck -- cosmetic change only.
        deck.write_bytes(b"NEW deck bytes -- totally different layout")

        m2 = compute_package_manifest(root)

        assert m1.material_manifest_hash == m2.material_manifest_hash
        assert m1.material_count == m2.material_count == 1
        assert m2.cosmetic_count == 1


def test_manifest_hash_changes_when_evidence_csv_edited():
    """A 1-byte edit to the evidence CSV MUST change the material hash."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_evidence").mkdir()
        ev = root / "01_evidence" / "evidence_index.csv"
        ev.write_text("evidence_id,tier\nE-001,T3\n")

        m1 = compute_package_manifest(root)
        ev.write_text("evidence_id,tier\nE-001,T2\n")  # 1-char score change
        m2 = compute_package_manifest(root)

        assert m1.material_manifest_hash != m2.material_manifest_hash


def test_manifest_hash_changes_when_scoring_xlsx_swapped():
    """Scoring XLSX swap must trigger re-ingest."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "03_scoring_workbook").mkdir()
        sw = root / "03_scoring_workbook" / "Scoring.xlsx"
        sw.write_bytes(b"old workbook bytes")
        m1 = compute_package_manifest(root)
        sw.write_bytes(b"new workbook bytes (score changes)")
        m2 = compute_package_manifest(root)
        assert m1.material_manifest_hash != m2.material_manifest_hash


def test_diff_manifests_first_ingest_lists_all_material():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_evidence").mkdir()
        (root / "01_evidence" / "evidence_index.csv").write_text("x,y\n")
        (root / "05_narrative_deck").mkdir()
        (root / "05_narrative_deck" / "deck.pptx").write_bytes(b"deck")
        m = compute_package_manifest(root)
        d = diff_manifests(None, m)
        assert d["added"] == ["01_evidence/evidence_index.csv"]
        assert d["removed"] == []
        assert d["modified"] == []
        assert material_changes_count(d) == 1


def test_diff_manifests_modified_only_modified():
    """Editing an existing material file lands in ``modified``, not added."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_evidence").mkdir()
        ev = root / "01_evidence" / "evidence_index.csv"
        ev.write_text("v1\n")
        m_prior = compute_package_manifest(root)
        ev.write_text("v2\n")
        m_curr = compute_package_manifest(root)
        d = diff_manifests(m_prior, m_curr)
        assert d["modified"] == ["01_evidence/evidence_index.csv"]
        assert d["added"] == []
        assert d["removed"] == []


def test_diff_manifests_removed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_evidence").mkdir()
        ev = root / "01_evidence" / "evidence_index.csv"
        ev.write_text("v1\n")
        m_prior = compute_package_manifest(root)
        ev.unlink()
        m_curr = compute_package_manifest(root)
        d = diff_manifests(m_prior, m_curr)
        assert d["removed"] == ["01_evidence/evidence_index.csv"]


def test_summarize_diff_human_readable():
    s = summarize_diff(
        {"added": ["a"], "removed": [], "modified": ["b", "c"],
         "cosmetic_changed": ["d"]}
    )
    assert "+1 added" in s
    assert "~2 modified" in s
    assert "1 cosmetic" in s
    assert "removed" not in s  # zero-removed is omitted


def test_summarize_diff_no_changes():
    assert summarize_diff(
        {"added": [], "removed": [], "modified": [], "cosmetic_changed": []}
    ) == "(no changes)"


def test_real_world_pentegra_layout_classifies_correctly():
    """Pentegra's actual files: run_manifest in 01_evidence (misplaced),
    caps_applied_log.csv in 07_governance, scoring XLSX, deck PPTX in
    05_narrative_deck, and search log appendices.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for d in ["01_evidence", "03_scoring_workbook", "05_narrative_deck",
                  "07_governance", "08_appendices"]:
            (root / d).mkdir()
        (root / "01_evidence" / "run_manifest.json").write_text("{}")  # misplaced
        (root / "01_evidence" / "evidence_index.csv").write_text("e\n")
        (root / "03_scoring_workbook" / "Scoring.xlsx").write_bytes(b"xlsx")
        (root / "05_narrative_deck" / "deck.pptx").write_bytes(b"deck")
        (root / "07_governance" / "caps_applied_log.csv").write_text("c\n")
        (root / "07_governance" / "qa_verdict.json").write_text("{}")
        (root / "08_appendices" / "A2_search_log.csv").write_text("s\n")
        m = compute_package_manifest(root)
        assert m.material_count == 5  # evidence, run_manifest, xlsx, caps, qa
        assert m.cosmetic_count == 2  # deck pptx + A2_search_log
        assert m.material_manifest_hash != ""


# ── Selective per-artifact re-ingest (Batch 2) ────────────────────────


def test_affected_tables_scoring_csv_only():
    """Only the scoring CSV changed -> only score-derived tables.

    The 13 tables in skip_tables_for_diff() are the tables that must
    NOT re-fire when only the scoring CSV changed: evidence_index +
    document_sections + focus_areas + caps_applied_log +
    recommendations + ... were correct prior; leaving them alone is
    the whole point of the selective re-ingest.
    """
    diff = {
        "added": [], "removed": [],
        "modified": ["03_scoring_workbook/exports/export_scoring_detail.csv"],
        "cosmetic_changed": [],
    }
    aff = affected_tables(diff)
    # Must include score-derived tables.
    assert "subcap_scores" in aff
    assert "peer_benchmarks" in aff
    assert "platform_scores" in aff
    # Must NOT include independent surfaces.
    assert "evidence_index" not in aff
    assert "document_sections" not in aff
    assert "focus_areas" not in aff
    assert "caps_applied_log" not in aff
    assert "recommendations" not in aff
    # Always-on surfaces (entity / run touch + cache invalidation +
    # parser_observations).
    assert "entities" in aff
    assert "runs" in aff
    assert "vertex_synthesis_cache_invalidate" in aff
    assert "parser_observations" in aff


def test_affected_tables_evidence_includes_dedup_triple():
    """01_evidence/* MUST include the dedup TRIPLE -- skipping any of
    the three risks state corruption."""
    diff = {
        "added": [], "removed": [],
        "modified": ["01_evidence/evidence_index.csv"],
        "cosmetic_changed": [],
    }
    aff = affected_tables(diff)
    assert "evidence_index" in aff
    assert "evidence_run_links" in aff
    assert "dedup_audit" in aff


def test_affected_tables_assessment_report_drives_section_triple():
    diff = {
        "added": [], "removed": [],
        "modified": [
            "04_reports/AlmaBank_DMA_Assessment_Report_FINAL.docx"
        ],
        "cosmetic_changed": [],
    }
    aff = affected_tables(diff)
    assert "document_sections" in aff
    assert "document_lineage" in aff
    assert "document_evidence_items" in aff
    assert "focus_areas" not in aff
    assert "firmographics" not in aff


def test_affected_tables_client_profile_drives_focus_and_firmo():
    """Client_Profile DOCX produces BOTH focus_areas AND firmographics."""
    diff = {
        "added": [], "removed": [],
        "modified": [
            "04_reports/AlmaBank_Client_Profile_Research_Report.docx"
        ],
        "cosmetic_changed": [],
    }
    aff = affected_tables(diff)
    assert "focus_areas" in aff
    assert "firmographics" in aff
    # Also triggers document_sections (any *report*.docx pattern).
    assert "document_sections" in aff


def test_affected_tables_caps_log_only():
    diff = {
        "added": [], "removed": [],
        "modified": ["07_governance/caps_applied_log.csv"],
        "cosmetic_changed": [],
    }
    aff = affected_tables(diff)
    assert "caps_applied_log" in aff
    assert "subcap_scores" not in aff


def test_affected_tables_recommendations_only():
    diff = {
        "added": [], "removed": [],
        "modified": ["08_appendices/recommendations_detail.json"],
        "cosmetic_changed": [],
    }
    aff = affected_tables(diff)
    assert "recommendations" in aff
    assert "subcap_scores" not in aff
    assert "evidence_index" not in aff


def test_affected_tables_unknown_path_returns_all_tables_safely():
    """Defense-in-depth: an unrecognized artifact returns the FULL
    table set so the safe fallback is 'persist everything' rather than
    'silently drop the new artifact's effects'."""
    diff = {
        "added": ["09_future_artifact/new_thing.txt"],
        "removed": [], "modified": [], "cosmetic_changed": [],
    }
    aff = affected_tables(diff)
    assert aff == set(ALL_TABLES)


def test_affected_tables_no_material_change_returns_empty():
    """A cosmetic-only diff produces NO affected tables -- the entire
    persist path can be skipped."""
    diff = {
        "added": [], "removed": [], "modified": [],
        "cosmetic_changed": ["05_narrative_deck/talk_track.pptx",
                             "04_reports/figures/heatmap.png"],
    }
    assert affected_tables(diff) == set()


def test_skip_tables_complement_of_affected():
    diff = {
        "added": [], "removed": [],
        "modified": ["03_scoring_workbook/scoring.csv"],
        "cosmetic_changed": [],
    }
    aff = affected_tables(diff)
    skip = skip_tables_for_diff(diff)
    assert aff & skip == set()           # disjoint
    assert aff | skip == set(ALL_TABLES) # together cover the universe


def test_affected_tables_multiple_classes_unions():
    """When scoring AND evidence both change, the union of their
    affected tables fires."""
    diff = {
        "added": [], "removed": [],
        "modified": [
            "03_scoring_workbook/exports/export_scoring_detail.csv",
            "01_evidence/evidence_index.csv",
        ],
        "cosmetic_changed": [],
    }
    aff = affected_tables(diff)
    # Score tables.
    assert "subcap_scores" in aff
    assert "peer_benchmarks" in aff
    # Evidence triple.
    assert "evidence_index" in aff
    assert "evidence_run_links" in aff
    assert "dedup_audit" in aff
    # But document_sections / focus_areas still excluded.
    assert "document_sections" not in aff
    assert "focus_areas" not in aff
