"""The capability card owes exactly what the floors gate blocks on.

Measured 2026-10-01 on the SWBC run (760 cells, sixteen category workflows):
three readers each had their own idea of an "open" cell. The card owed only
the five catalogue facets — never the toolkit's `primary` question — and
skipped every synthesised cell; the driver's batch planner counted cells with
no Dominant_Claim; the gate blocked 391 cells on `primary_unfired`, 26
synthesised cells on volleys they still owed, and P3C4 on eight boilerplate
absences that no packet named. The card showed `missing: []` and no question,
and it is the only packet a workflow batch agent reads. Separately, it listed
no evidence a cell already held, so agents opened the workbook with raw
openpyxl to find it (166 cells were evidenced and unsynthesised).
"""
from __future__ import annotations

import json

from engine import cli, floors_gate, orient, pipeline as P
from engine import ledger as L
from fixtures import bank_evidence, declare_absent, new_run

FIVE = ("works", "fails", "value", "contradicts", "corroborates")


def _five_volleys(wb, cell):
    for f in FIVE:
        L.append_search(wb, subcap=cell, facet=f, tool="web_search",
                        query=f'"Acme Credit Union" {cell} {f} angle', hits=0,
                        kept=0, outcome="no hits")


def _cap(cell):
    return cell.rsplit(".", 1)[0]


def test_a_cell_whose_five_volleys_fired_still_owes_its_primary(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    _five_volleys(wb, cell)
    card = orient.capability_card(wb, _cap(cell), run=run)
    row = next(c for c in card["open_cells"] if c["cell"] == cell)
    assert row["missing"] == ["primary"], row
    assert row["question"], "the card must carry the toolkit's own question"
    assert cell in card["facets_owed"]["primary"]["cells"]
    gate = floors_gate.run(wb, cell.split(".")[0], require_synthesis=True,
                           qa_dir=run.qa_dir)
    assert cell in gate["primary_unfired"], "card and gate disagree"


def test_the_card_carries_the_evidence_a_cell_already_holds(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = bank_evidence(wb, cell, n=2)
    wb = run.open()
    card = orient.capability_card(wb, _cap(cell), run=run)
    row = next((c for c in card["open_cells"] if c["cell"] == cell), None)
    assert row is not None, "an evidenced, unsynthesised cell is open work"
    held = {e["e_id"] for e in row.get("evidence", [])}
    assert held & set(eids), f"held evidence missing from the card: {row}"
    assert all(len(e["excerpt"]) <= 240 for e in row["evidence"])


def test_a_declared_absence_is_off_the_card_unless_its_finding_is_boilerplate(
        tmp_path, monkeypatch):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    declare_absent(wb, cell)
    wb = run.open()
    card = orient.capability_card(wb, _cap(cell), run=run)
    assert cell not in [c["cell"] for c in card["open_cells"]]
    from engine import quality as Q
    monkeypatch.setattr(Q, "is_boilerplate", lambda v: "names nothing checkable")
    card = orient.capability_card(wb, _cap(cell), run=run)
    row = next(c for c in card["open_cells"] if c["cell"] == cell)
    assert row["rework"].startswith("re-declare the absence")


def test_the_planner_batches_exactly_the_cells_the_cards_list(tmp_path):
    run = new_run(tmp_path, n=8)
    wb = run.open()
    cells = wb.selected_subcaps()
    _five_volleys(wb, cells[0])
    declare_absent(wb, cells[1])
    wb = run.open()
    planned = P._open_capabilities(wb)
    caps = sorted({_cap(c) for c in cells})
    for cap in caps:
        on_card = len(orient.capability_card(wb, cap, run=run)["open_cells"])
        assert planned.get(cap.split(".")[0], {}).get(cap, 0) == on_card, cap


def test_card_category_lists_the_next_batches(tmp_path, capsys):
    run = new_run(tmp_path, n=6)
    cat = run.open().selected_subcaps()[0].split(".")[0]
    rc = cli.main(["card", "--run", run.run_id, "--root", str(run.root),
                   "--category", cat])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["category"] == cat
    assert out["open_cells"] == sum(out["open_capabilities"].values())
    flat = [c for b in out["batches"] for c in b]
    assert sorted(flat) == sorted(out["open_capabilities"])
