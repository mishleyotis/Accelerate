"""An intake document is cited by its source of record, never its cache.

MEASURED 2026-10-11 (R-INTERAC-20261010). RESEARCH closed 16/16 categories
and HANDOFF refused the workbook on contract rule 5: 19 cells cited
evidence with no URL in Source_URLs. 46 internal rows carried the local
`01_intake/` path (38 bare, 8 file://) though `intake_manifest.json` holds
each document's Drive URL, five more carried none, and one Clay reading
(E-031) was registered with no URL at all. Nothing at the write said so;
the contract said so two stages and $220 later.

Now: the ledger verifies an intake span against the landed document and
records the manifest's URL; a local path with no source of record, and a
connector reading with no URL, are refused at the write. `rehome-intake` and
`cite-record` repair a register written before the rule.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine import intake as I
from engine import ledger as L
from engine import validator as V

from fixtures import new_run

ENGINE = Path(__file__).resolve().parents[3] / "plugins/dma-insights/skills/dma-research"
DRIVE = "https://docs.google.com/document/d/18deU7hTuDegoWH21w5zjSxmMXgyJisu"
DOC = ("Meeting summary.\n\nThe client said its revenue reporting is "
       "assembled by hand each month from three Salesforce orgs and a finance "
       "spreadsheet, and that leadership wants one view of revenue by Q2.\n")
SPAN = ("its revenue reporting is assembled by hand each month from three "
        "Salesforce orgs and a finance spreadsheet")


def _land(run, tmp_path, *, source_url=DRIVE, name="notes.md"):
    src = tmp_path / name
    src.write_text(DOC)
    I.add(run.root, src, title="Client meeting summary", source_url=source_url)
    return Path(run.root) / I.INTAKE_DIR / name


def _cell(run):
    return run.open().selected_subcaps()[0]


def _rule5(wb):
    import openpyxl
    book = openpyxl.load_workbook(wb.path)
    return [f for f in V._rule5_evidence_and_urls(book) if "no URL" in str(f)]


@pytest.mark.parametrize("form", ["path", "file"])
def test_a_local_intake_path_is_recorded_as_its_source_of_record(tmp_path, form):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    path = _land(run, tmp_path)
    url = str(path) if form == "path" else f"file://{path}"
    wb = run.open()
    cell = _cell(run)
    eid = L.append_evidence(wb, source_name="Client meeting summary",
                            source_url=url, tier="T2", excerpt=SPAN,
                            subcaps=[cell], origin="internal",
                            verify_excerpts=True)
    wb = run.open()
    assert wb.evidence_index()[eid]["Source_URL"] == DRIVE
    assert wb.scoring_row(cell)["Source_URLs"] == DRIVE
    assert not _rule5(wb)


def test_the_span_is_verified_against_the_landed_document(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    path = _land(run, tmp_path)
    with pytest.raises(L.LedgerRefusal, match="excerpt_not_verbatim"):
        L.append_evidence(run.open(), source_name="Client meeting summary",
                          source_url=str(path), tier="T2",
                          excerpt=SPAN.replace("three", "four"),
                          subcaps=[_cell(run)], origin="internal")


def test_a_local_path_with_no_source_of_record_is_refused(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    path = _land(run, tmp_path, source_url=None)
    with pytest.raises(L.LedgerRefusal, match="no source of record"):
        L.append_evidence(run.open(), source_name="Client meeting summary",
                          source_url=str(path), tier="T2", excerpt=SPAN,
                          subcaps=[_cell(run)], origin="internal")


def test_a_local_path_outside_the_manifest_is_refused(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    with pytest.raises(L.LedgerRefusal, match="names no document"):
        L.append_evidence(run.open(), source_name="Client meeting summary",
                          source_url="/tmp/elsewhere/notes.md", tier="T2",
                          excerpt=SPAN, subcaps=[_cell(run)], origin="internal")


def test_a_connector_reading_with_no_url_is_refused(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    with pytest.raises(L.LedgerRefusal, match="connector reading with no URL"):
        L.append_evidence(
            run.open(), source_name="Clay company Tech Stack, acme.example",
            source_url=None, tier="T1", origin="connector",
            excerpt=("Imperva, Facebook SDK, SSL by Default, Typekit, "
                     "CookieYes, React, DocuSign, Cloudflare"),
            subcaps=[_cell(run)])


def test_an_internal_row_with_no_url_is_still_admitted(tmp_path):
    """Unchanged: a document nobody can link to is labelled internal."""
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    eid = L.append_evidence(run.open(), source_name="Board pack Q3",
                            source_url=None, tier="T2", excerpt=SPAN,
                            subcaps=[_cell(run)], origin="internal")
    assert eid.startswith("E")


def _legacy_rows(run, tmp_path):
    """Rows as the Interac register held them: written straight to the
    sheets, the way the ledger accepted them before the rule."""
    path = _land(run, tmp_path)
    wb = run.open()
    cells = wb.selected_subcaps()[:2]
    for eid, url, cell, origin in (("E-901", str(path), cells[0], "internal"),
                                   ("E-902", None, cells[1], "internal"),
                                   ("E-903", None, cells[1], "connector")):
        wb.append("Evidence_Detail", {
            "E_ID": eid, "Fact_ID": "F1", "Source_Name": "legacy",
            "Source_URL": url, "Tier": "T2", "Claim_Type": "INFERENCE",
            "Excerpt": SPAN if origin == "internal" else
            "Imperva, Cloudflare, React, DocuSign and CookieYes detected on site",
            "SubCap_IDs": cell, "Origin": origin}, save=False)
    wb.set_scoring(cells[0], {"Evidence_IDs": "E-901:F1",
                              "Source_URLs": str(path)}, save=False)
    wb.set_scoring(cells[1], {"Evidence_IDs": "E-902:F1, E-903:F1",
                              "Source_URLs": None}, save=False)
    wb.save()
    return cells


def test_rehome_repairs_a_register_written_before_the_rule(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    cells = _legacy_rows(run, tmp_path)
    out = L.rehome_intake_urls(run.open(), why="intake rows written before "
                               "the source-of-record rule", actor="owner")
    assert {r["e_id"] for r in out["rehomed"]} == {"E-901", "E-902"}
    assert set(out["cells"]) == set(cells)
    wb = run.open()
    assert wb.scoring_row(cells[0])["Source_URLs"] == DRIVE
    assert wb.scoring_row(cells[1])["Source_URLs"] == DRIVE
    steps = [r for r in wb.rows("Provenance") if r.get("Step") == "rehome_intake"]
    assert len(steps) == 2


def test_rehome_leaves_a_span_no_document_quotes(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    _legacy_rows(run, tmp_path)
    wb = run.open()
    wb.update_row("Evidence_Detail", "E_ID", "E-902",
                  {"Excerpt": "a sentence that no landed intake document contains "
                              "anywhere in its text at all"})
    out = L.rehome_intake_urls(run.open(), why="intake rows written before "
                               "the source-of-record rule")
    assert [u["e_id"] for u in out["unresolved"]] == ["E-902"]


def test_cite_record_gives_a_connector_reading_its_url(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    cells = _legacy_rows(run, tmp_path)
    L.rehome_intake_urls(run.open(), why="intake rows written before the "
                         "source-of-record rule")
    out = L.cite_connector_record(run.open(), "E-903", "https://www.acme.example",
                                  why="Clay web-crawl reading of the client's site")
    assert out["cells"] == [cells[1]]
    wb = run.open()
    assert "https://www.acme.example" in wb.scoring_row(cells[1])["Source_URLs"]
    with pytest.raises(L.LedgerRefusal, match="already cites"):
        L.cite_connector_record(wb, "E-903", "https://x.example",
                                why="a second URL is never written over")
    with pytest.raises(L.LedgerRefusal, match="only a connector"):
        L.cite_connector_record(wb, "E-901", "https://x.example",
                                why="an internal row is re-homed, not cited")


def test_the_cli_commands_are_wired(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    _legacy_rows(run, tmp_path)
    base = [sys.executable, "-m", "engine.cli"]
    where = ["--run", run.run_id, "--root", str(run.root)]
    r = subprocess.run(base + ["rehome-intake", *where, "--why",
                               "intake rows written before the rule"],
                       cwd=ENGINE, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert len(json.loads(r.stdout)["rehomed"]) == 2
    r = subprocess.run(base + ["cite-record", *where, "--e-id", "E-903",
                               "--url", "https://www.acme.example", "--why",
                               "Clay web-crawl reading of the client's site"],
                       cwd=ENGINE, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── a re-strike rewrites its conclusion (same run, SCORING) ──────────────
#
# R-INTERAC-20261010, P3: the critic moved 8 rows; the rescore prefixed the
# critic's reason to the old rationale, so 7 of 8 ended "final 3 (Competing)"
# or "final 2.5" beside a struck 2.0-2.5. The critic passed the scores and
# could not move the text. The write now refuses a "final N" that is not the
# score struck, and the rescore prompt rewrites the ending.

from engine import assessment as A

WORKFLOW = Path(__file__).resolve().parents[3] / \
    "plugins/dma-insights/workflows/dma-pillar-scoring.js"


@pytest.mark.parametrize("text,sc", [
    ("M2 Building; gap to M3: no KPIs. ceiling 3.0, final 3 (Competing)", 2.5),
    ("M2 Building; missing measured outcomes. final score: 2.75", 2.25),
    ("M2 Building; gap to M3. capped, final = 2.5", 2.0),
])
def test_a_final_figure_that_is_not_the_struck_score_is_refused(text, sc):
    assert any("concludes at final" in p for p in A.rubric_problems(text, sc, [], set()))


@pytest.mark.parametrize("text,sc", [
    ("M2 Building; gap to M3: no KPIs. ceiling 2.5, final 2.5", 2.5),
    ("M2 Building; gap to M3: no KPIs. final 2.50", 2.5),
    ("M2 Building; the gap to M3 is a documented framework", 2.0),
])
def test_a_final_figure_on_the_struck_score_or_none_passes(text, sc):
    assert not any("concludes at final" in p for p in A.rubric_problems(text, sc, [], set()))


def test_the_rescore_prompt_rewrites_rather_than_prefixes():
    src = WORKFLOW.read_text()
    assert "at the head of the existing rationale" not in src
    assert "REWRITE the rationale" in src and "IMMEDIATELY above" in src


# ── an adjustment the prose applies is one the write records ─────────────
#
# Same run, same rescore: P2C1.8.3, P3C3.1.1 and P4C3.2.2 argued "ADJ_STALE
# -0.3" while Caps_Applied read "none applied". A hand-struck score may state
# its adjustment in prose (the ADJ_STALE rule admits it), so the write records
# it rather than refusing it.

from fixtures import RATIONALE, researched_run, score_cell


def _scoring(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path, n=3, absent=0)
    A.open_stage(wb, run.qa_dir)
    return wb, cells[0], ev[cells[0]]


def _rat(eids, tail):
    from engine import rubric
    return RATIONALE.format(e0=eids[0], e1=eids[1], lvl=rubric.maturity_level(2.0)) + tail


def test_a_stated_adjustment_is_recorded_in_caps_applied(tmp_path):
    wb, cell, eids = _scoring(tmp_path)
    out = score_cell(wb, cell, eids, score=2.0,
                     rationale=_rat(eids, " ADJ_STALE -0.3 applied for 2022 evidence."))
    assert out["caps_applied"] == "ADJ_STALE -0.3 (stated in the rationale)"
    assert wb.scoring_row(cell)["Caps_Applied"] == out["caps_applied"]


def test_an_adjustment_already_recorded_is_not_recorded_twice(tmp_path):
    wb, cell, eids = _scoring(tmp_path)
    out = score_cell(wb, cell, eids, score=2.0, caps="ADJ_STALE:-0.3 (2022 evidence)",
                     rationale=_rat(eids, " ADJ_STALE -0.3 applied for 2022 evidence."))
    assert out["caps_applied"] == "ADJ_STALE:-0.3 (2022 evidence)"


def test_an_adjustment_named_as_not_owed_is_not_recorded(tmp_path):
    wb, cell, eids = _scoring(tmp_path)
    out = score_cell(wb, cell, eids, score=2.0,
                     rationale=_rat(eids, " ADJ_STALE not applied: both sources are dated 2025."))
    assert out["caps_applied"] == "none applied"


# ── every intake document is cited or declared read ─────────────────────
#
# R-INTERAC-20261010: one cited document of seven satisfied the old check
# while the largest (a 133 KB proposal deck, mostly another client's slides)
# went unread and unrecorded.

def _hybrid(run):
    wb = run.open()
    wb.set_metadata("evidence_mode", "HYBRID")
    return wb


def test_a_silent_intake_document_blocks_the_handoff(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    path = _land(run, tmp_path)
    other = tmp_path / "deck.md"
    other.write_text("A deck about another institution entirely, with no Acme content at all.\n")
    I.add(run.root, other, title="Unrelated deck", source_url="https://docs.google.com/x/deck")
    L.append_evidence(_hybrid(run), source_name="Client meeting summary", source_url=str(path),
                      tier="T2", excerpt=SPAN, subcaps=[_cell(run)], origin="internal")
    msg = I.handoff_blocker(run.open(), run.root)
    assert msg and "deck.md" in msg and "notes.md" not in msg
    with pytest.raises(ValueError):
        I.declare_read(run.root, "deck.md", reason="short", actor="x")
    I.declare_read(run.root, "deck.md", actor="research-conductor",
                   reason="A deck about another institution; nothing in it is about this client.")
    assert I.handoff_blocker(run.open(), run.root) is None
