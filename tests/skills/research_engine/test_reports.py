"""Two reports, curated from the workbook, that refuse rather than mislead."""
import re

import pytest
from docx import Document

from engine import ledger as L, report_spec as RS, reports
from engine.reports import ReportRefused

from fixtures import CAT, bank_evidence, good_synthesis, new_run, synthesise

LOREM = ("Acme Credit Union runs member-facing digital banking on Alkami, "
         "live since Q3 2024, with adoption measured at 47 percent within "
         "ninety days and restated at 52 percent in the 2025 annual report "
         "[E-001]. The board reviews the figure quarterly and it is tied to "
         "the 2025 cost-to-serve target, which makes this the channel the "
         "programme leans on rather than a pilot. ")


def _narrate(wb, spec, *, words_per_section=800, cards=RS.INSIGHT_CARD_MIN,
             cite="E-001"):
    body = (LOREM.replace("[E-001]", f"[{cite}]") *
            max(1, words_per_section // 60))
    for sec in spec.sections:
        n = cards if sec.kind == "insight_card" else 1
        for i in range(n):
            wb.append("Report_Narrative", {
                "Report": spec.key, "Section_ID": sec.id,
                "Heading": f"{sec.heading} {i+1}" if n > 1 else sec.heading,
                "Body": body, "Evidence_IDs": cite, "Kind": sec.kind,
                "Author": "test", "Written_At": "2026-08-29T00:00:00Z",
            }, save=False)
    wb.save()


def _run_with_content(tmp_path, n=8):
    run = new_run(tmp_path, n=n)
    wb = run.open()
    for cell in wb.selected_subcaps():
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)))
    wb.append("Entity_Timeline", {
        "Event_Date": "2024-09-01", "Event": "Alkami go-live",
        "Signal": "EXPANSION", "SubCap_IDs": wb.selected_subcaps()[0],
        "Evidence_IDs": "E-001"})
    from engine import floors_gate
    floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    return run, wb


# ── AUD-0003 · both artefacts have a producer, and an ingestible name ─────

def test_both_reports_render_to_docx(tmp_path):
    run, wb = _run_with_content(tmp_path)
    out = []
    for spec in RS.SPECS.values():
        _narrate(wb, spec)
        out.append(reports.render(wb, spec, run.deliverables))
    assert all(r["path"].endswith(".docx") for r in out)
    assert all(Document(r["path"]).paragraphs for r in out)


def test_the_filenames_are_the_ones_the_app_classifies(tmp_path):
    """AUD-0003: the produced report was `client_profile.md`, and
    classify() returns None for it, so it was uningestable."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__)
                           .resolve().parents[3] / "apps" / "worker"))
    from dma_worker.classification import classify
    run, wb = _run_with_content(tmp_path)
    for spec in RS.SPECS.values():
        _narrate(wb, spec)
        r = reports.render(wb, spec, run.deliverables)
        c = classify(r["path"].rsplit("/", 1)[-1])
        assert c is not None, f"{r['path']} is unclassifiable"
    assert classify("client_profile.md") is None   # the old output


# ── AUD-0033 · a dead citation refuses the render ────────────────────────

def test_one_unresolvable_citation_refuses_the_whole_report(tmp_path):
    run, wb = _run_with_content(tmp_path)
    spec = RS.SPECS["assessment"]
    _narrate(wb, spec, cite="E-999")
    with pytest.raises(ReportRefused, match="do not resolve"):
        reports.render(wb, spec, run.deliverables)


def test_the_citation_list_at_the_back_resolves_to_the_register(tmp_path):
    run, wb = _run_with_content(tmp_path)
    spec = RS.SPECS["assessment"]
    _narrate(wb, spec)
    r = reports.render(wb, spec, run.deliverables)
    assert r["unresolved"] == []
    text = "\n".join(p.text for p in Document(r["path"]).paragraphs)
    for e in set(re.findall(r"\[(E-\d+)\]", text)):
        assert f"[{e}]" in text and "https://" in text


# ── AUD-0105 · the word minimums are measured ────────────────────────────

def test_a_short_section_refuses_and_says_which(tmp_path):
    run, wb = _run_with_content(tmp_path)
    spec = RS.SPECS["assessment"]
    _narrate(wb, spec, words_per_section=30)
    with pytest.raises(ReportRefused) as e:
        reports.render(wb, spec, run.deliverables)
    assert "blocking minimum" in str(e.value)
    assert "Report_Narrative" in str(e.value)


# ── AUD-0145 · the insight-card floor is the template's, not 3 ───────────

def test_seven_insight_cards_is_not_enough(tmp_path):
    run, wb = _run_with_content(tmp_path)
    spec = RS.SPECS["client_research"]
    _narrate(wb, spec, cards=RS.INSIGHT_CARD_MIN - 1)
    with pytest.raises(ReportRefused, match="insight cards against the"):
        reports.render(wb, spec, run.deliverables)


def test_three_insight_cards_the_old_floor_is_refused(tmp_path):
    run, wb = _run_with_content(tmp_path)
    spec = RS.SPECS["client_research"]
    _narrate(wb, spec, cards=3)
    with pytest.raises(ReportRefused, match="insight cards"):
        reports.render(wb, spec, run.deliverables)


# ── AUD-0052 · the numbers in the report ARE the numbers in the sheets ───

def test_the_coverage_table_is_read_from_the_workbook_at_render_time(tmp_path):
    run, wb = _run_with_content(tmp_path)
    spec = RS.SPECS["assessment"]
    _narrate(wb, spec)
    r = reports.render(wb, spec, run.deliverables)
    doc = Document(r["path"])
    cov = wb.coverage()[0]
    seen = [t for t in doc.tables
            if t.rows[0].cells[0].text == "Category_ID"]
    assert seen, "the coverage table must be in the document"
    body = [c.text for row in seen[0].rows for c in row.cells]
    assert str(cov["Selected"]) in body and cov["Category_ID"] in body


def test_changing_the_workbook_changes_the_report(tmp_path):
    """The property that makes 'one substrate' true rather than asserted."""
    run, wb = _run_with_content(tmp_path)
    spec = RS.SPECS["assessment"]
    _narrate(wb, spec)
    before = reports.render(wb, spec, run.deliverables)["citations"]
    L.append_evidence(wb, source_name="NCUA call report 2025",
                      source_url="https://ncua.example/cr25", tier="T1",
                      excerpt="Digital channel volumes for Acme Credit Union "
                              "rose 31 percent year over year in 2025 filings.",
                      subcaps=[wb.selected_subcaps()[0]], published="2025-09-30")
    r = reports.render(wb, spec, run.deliverables)
    doc = Document(r["path"])
    text = "\n".join(p.text for p in doc.paragraphs) + "".join(
        c.text for t in doc.tables for row in t.rows for c in row.cells)
    assert "NCUA call report 2025" in text
    assert before == r["citations"]  # the narrative's citations, unchanged


# ── AUD-0107 · a section with no source says so, it does not render empty ─

def test_a_section_whose_inputs_are_all_empty_is_named_in_the_refusal(tmp_path):
    """AUD-0107: thirteen sheets named as INPUTS by the templates do not
    exist, 'leaving §3.2 and §3.3 with no source at all'. A section whose
    every input is empty must say so."""
    run = new_run(tmp_path, n=2)
    wb = run.open()
    spec = RS.from_json({
        "key": "assessment", "title": "Probe", "min_words": 10,
        "filename": "DMA_Assessment_Report_{entity}_{date}.docx",
        "sections": [{"id": "9", "heading": "Acquisition history",
                      "min_words": 10, "inputs": ["Entity_Timeline"],
                      "requires_citation": False}],
    })
    wb.append("Report_Narrative", {
        "Report": "assessment", "Section_ID": "9", "Heading": "Acquisition",
        "Body": "Acme Credit Union completed no acquisitions in the period "
                "under review, on the evidence gathered.",
        "Kind": "section"})
    with pytest.raises(ReportRefused) as e:
        reports.render(wb, spec, run.deliverables)
    assert "no source at all" in str(e.value)
    assert "Entity_Timeline" in str(e.value)


def test_a_focused_engagement_states_its_scope_instead_of_refusing(tmp_path):
    """The opposite error to AUD-0107's: a run scoped to one pillar
    legitimately leaves three pillar sheets empty, and refusing that would
    reject a correct run."""
    run, wb = _run_with_content(tmp_path)
    spec = RS.SPECS["assessment"]
    _narrate(wb, spec)
    r = reports.render(wb, spec, run.deliverables)
    text = "\n".join(p.text for p in Document(r["path"]).paragraphs)
    assert "Not in this engagement's scope" in text
    assert "P4_Subcap_Scoring" in text


def test_forcing_marks_the_gaps_in_the_document_rather_than_hiding_them(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    spec = RS.SPECS["assessment"]
    r = reports.render(wb, spec, run.deliverables, force=True)
    assert r["forced"] and r["problems"]
    text = "\n".join(p.text for p in Document(r["path"]).paragraphs)
    assert "NO SOURCE" in text
