"""A run whose lock no longer matches the engine is refused, not reported.

Measured 28-09-2026 (QA audit F-F06-009, F-F10-032, fault injections F-05
and F-06 on a plugin copy): with one catalogue cell's tier mutated, `resume`
reported the drift and `orient` served the card and `search` wrote a row;
with the workbook contract set to v8, `validate` returned FAILS=0. Every one
of those is a write or a decision taken against a run the engine cannot
vouch for. Now the lock is checked where it matters: the card, the write,
the resume, the handoff and rule 7.
"""
import pytest

from engine import assessment as A
from engine import contract as C
from engine import ledger as L
from engine import orient, runstate, validator
from fixtures import CAT, new_run


def _cell():
    return list(C.taxonomy().cells_in(CAT))[0]


def _move_the_catalogue(monkeypatch):
    monkeypatch.setattr(C, "catalogue_hash", lambda: "0" * 64)


def test_orient_refuses_a_card_against_a_moved_catalogue(tmp_path, monkeypatch):
    run = new_run(tmp_path)
    wb = run.open()
    assert orient.orient(wb, CAT, qa_dir=run.qa_dir)        # served before
    _move_the_catalogue(monkeypatch)
    with pytest.raises(ValueError, match="REFUSED: the run's lock no longer matches"):
        orient.orient(wb, CAT, qa_dir=run.qa_dir)


def test_the_ledger_writes_nothing_into_a_drifted_run(tmp_path, monkeypatch):
    run = new_run(tmp_path)
    wb = run.open()
    cell = _cell()
    searches, evidence = len(wb.rows("Search_Log")), len(wb.rows("Evidence_Detail"))
    _move_the_catalogue(monkeypatch)
    with pytest.raises(L.LedgerRefusal, match="lock no longer matches"):
        L.append_search(wb, subcap=[cell], facet=sorted(C.DQ_FACETS)[0], query="q",
                        tool=sorted(C.SEARCH_TOOLS)[0], hits=1, kept=1)
    with pytest.raises(L.LedgerRefusal, match="lock no longer matches"):
        L.append_evidence(wb, source_name="x", source_url="https://x.example",
                          tier="T2", subcaps=[cell], published="2025-01-01",
                          excerpt="A" * 80)
    assert len(wb.rows("Search_Log")) == searches
    assert len(wb.rows("Evidence_Detail")) == evidence


def test_resume_refuses_rather_than_reports(tmp_path, monkeypatch):
    run = new_run(tmp_path)
    _move_the_catalogue(monkeypatch)
    with pytest.raises(runstate.RunDrift) as e:
        runstate.resume(run.run_id, run.root)
    assert e.value.divergences and "catalogue has moved" in e.value.divergences[0]
    assert "DMA_CATALOGUE" in str(e.value)


def test_a_moved_contract_fails_rule7_and_blocks_the_handoff(tmp_path, monkeypatch):
    run = new_run(tmp_path)
    wb = run.open()
    monkeypatch.setattr(C, "WORKBOOK_CONTRACT", "v8")
    fails = validator.validate(wb.path)
    assert any(f["rule"] == 7 and "workbook contract" in f["detail"] for f in fails)
    blockers = A.research_ready(wb, run.qa_dir)
    assert any("lock no longer matches" in b for b in blockers)
