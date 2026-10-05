"""A person's recorded waiver of a research gap (engine.waiver, MEM-0591).

arbor-bank-2026-10-05: the driver withheld three stalled categories and said
"a person decides whether to repair at the source or accept the gap" — and no
mechanism could record the second answer. These pin what a waiver is: named
cells, a person, a reason, only content failures, re-opened by any new
failure, the cells left UNSCORED (null) and disclosed."""
from __future__ import annotations

import pytest

from engine import assessment as A, brief, floors_gate, waiver
from fixtures import (bank_evidence, good_synthesis, new_run, synthesise,
                      two_category_selection)

REASON = ("Accepted after two stalled repair rounds; the cell goes to scoring "
          "unscored and the gap is disclosed to the client.")


def _failing(tmp_path, n_fail=1):
    run = new_run(tmp_path, selected=two_category_selection(3))
    wb = run.open()
    cat = wb.selected_subcaps()[0].split(".")[0]
    cells = [c for c in wb.selected_subcaps() if c.startswith(cat)]
    for i, c in enumerate(cells):
        synthesise(wb, c, good_synthesis(c, bank_evidence(wb, c, n=5)),
                   verdict="FAIL" if i < n_fail else "PASS")
    floors_gate.run(wb, cat, require_synthesis=True, qa_dir=run.qa_dir)
    return run, wb, cat, cells


def test_a_waiver_is_a_persons_named_bounded_decision(tmp_path):
    run, wb, cat, cells = _failing(tmp_path)
    bad = cells[0]
    with pytest.raises(waiver.WaiverRefusal, match="person"):
        waiver.record(wb, category=cat, cells=[bad], by="research-challenger",
                      reason=REASON)
    with pytest.raises(waiver.WaiverRefusal, match="reason"):
        waiver.record(wb, category=cat, cells=[bad], by="Jo Analyst", reason="ok")
    with pytest.raises(waiver.WaiverRefusal, match="not failing"):
        waiver.record(wb, category=cat, cells=[cells[1]], by="Jo Analyst",
                      reason=REASON)
    with pytest.raises(waiver.WaiverRefusal, match="name the cells"):
        waiver.record(wb, category=cat, cells=[], by="Jo Analyst", reason=REASON)
    out = waiver.record(wb, category=cat, cells=[bad], by="Jo Analyst", reason=REASON)
    assert out["covers_category"] and out["terms"][bad] == ["challenge_failed"]


def test_an_unwaivable_blocker_is_refused_by_name(tmp_path, monkeypatch):
    run, wb, cat, cells = _failing(tmp_path)
    monkeypatch.setattr(waiver, "live_blocking", lambda wb, c: (
        {"challenge_failed", "synthesis_missing"},
        {"challenge_failed": {cells[0]}, "synthesis_missing": {cells[1]}}))
    with pytest.raises(waiver.WaiverRefusal, match="synthesis_missing"):
        waiver.record(wb, category=cat, cells=[cells[0]], by="Jo Analyst",
                      reason=REASON)


def test_a_waiver_passes_dispatch_until_a_new_cell_fails(tmp_path):
    run, wb, cat, cells = _failing(tmp_path)
    assert cat in brief.categories_needing_dispatch(wb)["dispatch"]
    waiver.record(wb, category=cat, cells=[cells[0]], by="Jo Analyst", reason=REASON)
    need = brief.categories_needing_dispatch(run.open())
    assert cat in need["passed"] and cat in need["waived"]
    wb2 = run.open()
    synthesise(wb2, cells[1], good_synthesis(cells[1], bank_evidence(wb2, cells[1], n=5)),
               verdict="FAIL")
    assert cat in brief.categories_needing_dispatch(run.open())["dispatch"], \
        "a failure outside the waiver must re-open the category"


def test_scoring_opens_on_a_waived_category_and_leaves_the_cell_null(tmp_path):
    run, wb, cat, cells = _failing(tmp_path)
    blockers = A.research_ready(wb, run.qa_dir)
    assert any(cat in b for b in blockers), blockers
    waiver.record(wb, category=cat, cells=[cells[0]], by="Jo Analyst", reason=REASON)
    assert not any(cat in b for b in A.research_ready(run.open(), run.qa_dir))
    wb2 = run.open()
    g = A.gate(wb2)
    assert cells[0] in g["unscored"], "undisclosed, a waived cell still counts"
    assert waiver.disclose_in_caps_log(wb2) == [cells[0]]
    wb3 = run.open()
    row = {r["subcap_id"]: r for r in wb3.rows("Caps_Applied_Log")}[cells[0]]
    assert row["final_score"] in (None, "") and "UNSCORED" in row["caps_applied"]
    assert "Jo Analyst" in row["caps_applied"]
    assert wb3.scoring_row(cells[0]).get("Score") in (None, "")
    g = A.gate(wb3)
    assert cells[0] not in g["unscored"]
    assert cells[1] in g["unscored"], "only the waived cell is exempt"
