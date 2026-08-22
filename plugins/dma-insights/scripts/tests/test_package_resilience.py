"""The messy-corpus safeguards, pinned against measured pathologies.

Every case here is a real package shape from the 2026-08-20 corpus survey
(178 clients): wrapper folders, version stacks with INTERIM copies,
Explorium noise, briefing-only folders, evidence living in CSVs and JSONL
outside any workbook, event dates masquerading as publication dates.
"""
import json
import sys
import zipfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import corpus_search  # noqa: E402
import evidence_normalize  # noqa: E402
import package_map  # noqa: E402
import run_gate  # noqa: E402


def _mk(root: Path, rel: str, content: bytes = b"x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


# ── package_map ──────────────────────────────────────────────────────────

def test_final_beats_versions_beats_plain(tmp_path):
    _mk(tmp_path, "a/Client_DMA_Scoring_Workbook_v2.xlsx")
    _mk(tmp_path, "a/Client_DMA_Scoring_Workbook.xlsx")
    _mk(tmp_path, "FINAL/Client_Scoring_Workbook_FINAL.xlsx")
    m = package_map.map_package(tmp_path)
    assert "FINAL" in m["scoring"]["primary"]


def test_interim_is_never_auto_picked_over_a_live_workbook(tmp_path):
    _mk(tmp_path, "03_scoring_workbook/DMA_Scoring_Workbook_X.xlsx")
    _mk(tmp_path, "02_research_workbook/DMA_Scoring_Workbook_X_INTERIM.xlsx")
    m = package_map.map_package(tmp_path)
    assert m["scoring"]["primary"].endswith("DMA_Scoring_Workbook_X.xlsx")
    # Which ROLE owns the set-aside follows the folder it sits in, so assert
    # the invariant rather than the bookkeeping: an interim never displaces a
    # LIVE workbook of the same role, and is always named. (Here research has
    # nothing else, so the module's deliberate rule applies — it is used under
    # protest rather than dropped, because an interim register still carries
    # real excerpts and losing them is the worse failure.)
    set_aside = m["scoring"]["set_aside"] + m["research"]["set_aside"]
    assert any("INTERIM" in s["path"] for s in set_aside)
    assert "INTERIM" not in m["scoring"]["primary"]
    # "set aside" and "under protest" are the two halves of one rule and
    # never both fire for a role: set aside when a live workbook won, under
    # protest when the interim was all there was. Either way it is on record.
    assert any(("under protest" in a) or ("set aside" in a)
               for a in m["ambiguities"])


def test_explorium_noise_is_auxiliary_not_scoring(tmp_path):
    _mk(tmp_path, "08_appendices/HVCU_Explorium_TechStack_Validation.xlsx")
    _mk(tmp_path, "03_scoring_workbook/Scoring_Workbook.xlsx")
    m = package_map.map_package(tmp_path)
    assert "Explorium" not in (m["scoring"]["primary"] or "")
    assert m["auxiliary_xlsx"]


def test_briefing_only_package_is_named_not_guessed(tmp_path):
    _mk(tmp_path, "Zip_Client_Profile_Briefing.pptx")
    _mk(tmp_path, "Zip_Research_Report.docx")
    m = package_map.map_package(tmp_path)
    assert m["scoring"]["primary"] is None
    assert any("BRIEFING-ONLY" in a for a in m["ambiguities"])


def test_wrapper_folder_is_transparent(tmp_path):
    _mk(tmp_path, "HVCU_DMA_v6.3/03_scoring_workbook/Scoring_Workbook.xlsx")
    m = package_map.map_package(tmp_path)
    assert m["wrapper"] == "HVCU_DMA_v6.3"
    assert m["scoring"]["primary"]


def test_slides_variants_are_excluded_by_pattern(tmp_path):
    _mk(tmp_path, "05_narrative deck/deck.pptx")
    _mk(tmp_path, "Client_DMA_Presentation.pptx")
    _mk(tmp_path, "03_scoring_workbook/Scoring_Workbook.xlsx")
    m = package_map.map_package(tmp_path)
    assert len(m["excluded"]) == 2


def test_jsonl_ledger_is_an_evidence_table(tmp_path):
    _mk(tmp_path, "01_evidence/ledger.jsonl",
        b'{"evidence_id": "E-001", "text": "x"}\n')
    _mk(tmp_path, "data/some_rows.json",
        b'[{"fact_id": "E-002:F1", "text": "y"}]')
    m = package_map.map_package(tmp_path)
    assert "01_evidence/ledger.jsonl" in m["evidence_tables"]
    assert "data/some_rows.json" in m["evidence_tables"]


# ── run_gate G2, wrapper-transparent ─────────────────────────────────────

def _fake_drive(monkeypatch, tree):
    monkeypatch.setattr(run_gate.drive_fetch, "_token", lambda: "tok")
    monkeypatch.setattr(run_gate.drive_fetch, "_find_client_folder",
                        lambda tok, c: {"id": "root", "name": f"{c} - DMA"})
    monkeypatch.setattr(run_gate.drive_fetch, "_list_children",
                        lambda tok, fid: tree.get(fid, []))


def test_g2_passes_a_wrapper_package(monkeypatch):
    F = run_gate.drive_fetch.FOLDER_MIME
    _fake_drive(monkeypatch, {
        "root": [{"id": "w", "name": "HVCU_DMA_v6.3", "mimeType": F}],
        "w": [{"id": "f1", "name": "Scoring_Workbook.xlsx", "mimeType": "x"},
              {"id": "f2", "name": "README.md", "mimeType": "x"}]})
    ok, detail = run_gate.g2_raw_package("hvcu")
    assert ok and "wrapper" in detail


def test_g2_refuses_briefing_only_by_name(monkeypatch):
    _fake_drive(monkeypatch, {
        "root": [{"id": "f1", "name": "Briefing.pptx", "mimeType": "x"},
                 {"id": "f2", "name": "Research_Report.docx",
                  "mimeType": "x"}]})
    ok, detail = run_gate.g2_raw_package("ziphq")
    assert not ok and "NO scoring artefact" in detail


# ── corpus_search ────────────────────────────────────────────────────────

def _docx(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml",
                   f"<w:document><w:p><w:t>{text}</w:t></w:p></w:document>")
    return p


def test_corpus_search_reads_docx_and_skips_slides(tmp_path):
    _docx(tmp_path, "04_reports/Report.docx",
          "The CDO role is held by two conflicting names")
    _mk(tmp_path, "05_narrative_deck/deck.pptx")
    _mk(tmp_path, "01_evidence/index.csv",
        b"evidence_id,url\nE-001,https://x.example/a\n")
    m = corpus_search.build_index(tmp_path)
    assert any("slides" in s["reason"] for s in m["skipped"])
    hits = corpus_search.search(tmp_path, "CDO conflicting")
    assert hits and "04_reports/Report.docx" in hits[0]["file"]


def test_corpus_search_eid_mode_is_exact(tmp_path):
    _mk(tmp_path, "01_evidence/index.csv",
        b"evidence_id,url\nE-001,https://x.example/a\nE-0011,https://y\n")
    corpus_search.build_index(tmp_path)
    hits = corpus_search.search(tmp_path, "E-001", exact=True)
    assert hits


# ── evidence_normalize ───────────────────────────────────────────────────

def test_merge_unifies_stores_and_event_dates_never_win(tmp_path):
    _mk(tmp_path, "01_evidence/evidence_index.csv",
        b"evidence_id,source_name,url\n"
        b"E-001,Annual report,https://x.example/ar\n")
    _mk(tmp_path, "08_appendices/register.jsonl",
        json.dumps({"evidence_id": "E-001",
                    "publish_date": "2026-02-01",
                    "excerpt": "A" * 60}).encode() + b"\n"
        + json.dumps({"evidence_id": "E-001",
                      "date": "1979-01-15",
                      "text": "founding event " * 5}).encode() + b"\n")
    records, conflicts = evidence_normalize.merge(tmp_path)
    rec = records["E-001"]
    assert rec["url"] == "https://x.example/ar"
    assert rec["date"] == "2026-02-01"      # publication beats event date
    assert len(rec["excerpt"]) >= 50
    assert not conflicts


def test_gaps_carry_the_client_prefix_and_unverified_recency(tmp_path):
    _mk(tmp_path, "01_evidence/evidence_index.csv",
        b"evidence_id,source_name\nE-009,Some source\n")
    records, _ = evidence_normalize.merge(tmp_path)
    gaps = evidence_normalize.gaps_out(records, "acme-credit-union")
    assert gaps and gaps[0]["eid"] == "acme-credit-union:E-009"
    assert set(gaps[0]["missing"]) == {"url", "date", "excerpt"}
    assert records["E-009"]["recency"] == "UNVERIFIED"


def test_conflicting_urls_across_stores_are_reported(tmp_path):
    _mk(tmp_path, "01_evidence/evidence_index.csv",
        b"evidence_id,url\nE-002,https://a.example/1\n")
    _mk(tmp_path, "07_governance/evidence_index.csv",
        b"evidence_id,url\nE-002,https://b.example/2\n")
    _, conflicts = evidence_normalize.merge(tmp_path)
    assert conflicts and conflicts[0]["field"] == "url"


def test_g2_accepts_an_export_only_scoring_package(monkeypatch):
    """54 of 177 corpus clients have no workbook — the flattened exports
    are the score authority (measured 2026-08-20)."""
    F = run_gate.drive_fetch.FOLDER_MIME
    _fake_drive(monkeypatch, {
        "root": [{"id": "s", "name": "03_scoring_workbook", "mimeType": F}],
        "s": [{"id": "f1", "name": "export_scoring_detail.csv",
               "mimeType": "x"},
              {"id": "f2", "name": "export_pillar_summary.csv",
               "mimeType": "x"}]})
    ok, detail = run_gate.g2_raw_package("access-credit-union")
    assert ok and "EXPORT-ONLY" in detail


def test_package_map_names_export_only_scoring(tmp_path):
    _mk(tmp_path, "03_scoring_workbook/export_scoring_detail.csv",
        b"subcap_id,score\nP1C1.1,3.2\n")
    _mk(tmp_path, "02_research_workbook/DMA_Research_Workbook_X.xlsx")
    m = package_map.map_package(tmp_path)
    assert m["scoring"]["primary"] is None
    assert m["source_map"]["scores"] == [
        "03_scoring_workbook/export_scoring_detail.csv"]
    assert any("EXPORT-ONLY" in a for a in m["ambiguities"])
    assert not any("BRIEFING-ONLY" in a for a in m["ambiguities"])


def test_a_scoring_named_workbook_in_the_research_folder_IS_the_research_one(
        tmp_path):
    """Shore United Bank and Houlihan Lokey both keep their research workbook
    named DMA_Scoring_Workbook_* inside 02_research_workbook/.

    This test used to assert `research.primary is None` as long as an
    ambiguity was raised, and that assertion is what let the defect ship:
    on 2026-08-22 Houlihan Lokey's research workbook was "flagged" exactly
    as designed and then never opened, so the ONE store carrying verbatim
    Excerpt/Anchor_Quote columns left the pipeline and 462 of 462 excerpts
    were fabricated downstream to fill the vacuum. Noticing is not using.
    The folder names the role; the shared filename template does not."""
    _mk(tmp_path, "03_scoring_workbook/DMA_Scoring_Workbook_X_SCORED.xlsx")
    _mk(tmp_path, "02_research_workbook/DMA_Scoring_Workbook_X.xlsx")
    m = package_map.map_package(tmp_path)
    assert m["research"]["primary"].endswith(
        "02_research_workbook/DMA_Scoring_Workbook_X.xlsx")
    assert m["scoring"]["primary"].endswith(
        "03_scoring_workbook/DMA_Scoring_Workbook_X_SCORED.xlsx")
    # and the research workbook actually reaches the evidence readers
    assert any("02_research_workbook" in s
               for s in m["source_map"]["evidence"])


def test_one_file_never_serves_both_roles(tmp_path):
    """The mirror risk of folder-first classification: a package with a
    single workbook must not have it stand in for the missing role."""
    _mk(tmp_path, "02_research_workbook/DMA_Scoring_Workbook_X.xlsx")
    m = package_map.map_package(tmp_path)
    assert m["research"]["primary"] is not None
    assert m["scoring"]["primary"] is None
    assert m["research"]["primary"] not in (m["source_map"]["scores"] or [])
    assert any("one file never serves both roles" in a
               for a in m["ambiguities"])


def test_a_package_with_no_research_workbook_says_excerpts_will_be_missing(
        tmp_path):
    """An honest absence, and the ambiguity has to name the consequence —
    that the excerpts are gone, not that they should be found elsewhere."""
    _mk(tmp_path, "03_scoring_workbook/DMA_Scoring_Workbook_X.xlsx")
    m = package_map.map_package(tmp_path)
    assert m["research"]["primary"] is None
    amb = " ".join(m["ambiguities"])
    assert "NO RESEARCH WORKBOOK" in amb
    assert "NOT excerpts invented" in amb


# ── the collection-date rung (owner, 2026-08-20: most evidence UNVERIFIED) ──

def test_collection_date_takes_the_latest_package_stamp(tmp_path):
    (tmp_path / "04_reports").mkdir(parents=True)
    (tmp_path / "04_reports" / "DMA_Report_FINAL_2026-05.docx").write_bytes(b"x")
    (tmp_path / "export_scoring_detail.csv").write_text(
        "run,generated\nr1,2026-06-12\n")
    cdate, basis = evidence_normalize.collection_date(tmp_path)
    assert cdate == "2026-06-12"
    assert "export_scoring_detail.csv" in basis


def test_collection_date_never_takes_a_future_stamp(tmp_path):
    (tmp_path / "notes_2099-01.txt").write_bytes(b"x")
    cdate, basis = evidence_normalize.collection_date(tmp_path)
    assert cdate is None
    assert "UNVERIFIED" in basis


def test_apply_collection_date_only_touches_dateless_rows():
    records = {
        "E-001": {"date": "2025-11-03", "url": "https://a"},
        "E-002": {"url": "https://b"},
    }
    n = evidence_normalize.apply_collection_date(
        records, "2026-06-12", "latest package stamp: test")
    assert n == 1
    assert records["E-001"]["date"] == "2025-11-03"       # publication wins
    assert "date_provenance" not in records["E-001"]
    assert records["E-002"]["date"] == "2026-06-12"
    assert records["E-002"]["date_provenance"] == "collection"


def test_collection_dated_rows_still_ask_for_a_publication_date():
    records = {"E-002": {"url": "https://b", "excerpt": "x" * 60,
                         "date": "2026-06-12",
                         "date_provenance": "collection",
                         "date_basis": "latest package stamp: test"}}
    gaps = evidence_normalize.gaps_out(records, "cl")
    assert len(gaps) == 1
    assert "publication_date" in gaps[0]["missing"]
    assert "dated at collection" in gaps[0]["note"]
    assert records["E-002"].get("recency") != "UNVERIFIED"


def test_truly_dateless_rows_stay_unverified(tmp_path):
    records = {"E-003": {"url": "https://c"}}
    gaps = evidence_normalize.gaps_out(records, "cl")
    assert records["E-003"]["recency"] == "UNVERIFIED"
    assert "date" in gaps[0]["missing"]
