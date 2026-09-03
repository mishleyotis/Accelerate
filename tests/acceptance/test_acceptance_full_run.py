"""Acceptance: one run, start to package, in order — the harmony test.

REPORTED 2026-09-03: "I do not see how the agents have been orchestrated to
ensure that all the above works harmoniously."

Every other test in this suite proves one refusal. This one proves the
refusals compose: a single run walks the whole path — start, PRELIM,
research, category gate, the client's own facts, the scoring stage, the
scoring gate, incremental shipping, both reports, the grains, the package —
and each stage is asserted to be BLOCKED before its predecessor is done and
OPEN after. If any two stages disagree about what "done" means, this test
fails, and no unit test can see it.

It is deliberately one long test. Splitting it would need the walk repeated
per assertion, which is both slow and a weaker claim: the point is that ONE
run reaches the end, not that each stage can be reached from a fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import assemble, assessment as A, brief, completeness
from engine import contract as C, floors_gate, grains
from engine import narrative as N, report_spec as RS, reports
from engine import ship, template as T, validator

from fixtures import (bank_evidence, bank_peer_medians, client_facts,
                      declare_absent, good_synthesis, make_shippable, new_run,
                      score_stage, section_record, sign_off_sections,
                      synthesise, write_report)


def test_one_run_walks_the_whole_path_and_every_stage_gates_its_predecessor(tmp_path):
    # ── STAGE 0 · the run exists, bound to the pinned templates ──────────
    run = new_run(tmp_path, n=8)                  # start + PRELIM, for real
    wb = run.open()
    cells = wb.selected_subcaps()
    assert str(wb.metadata()["template_binding"]).strip(), "unbound run"
    assert T.binding_state(wb)["current"] is True
    assert C.stage_of(wb.metadata()) == "research"

    # nothing downstream is available yet, and each says why
    assert N.stage_preconditions(wb, "assessment", run.qa_dir)
    with pytest.raises(A.ScoringRefusal, match="not ready to be scored"):
        A.open_stage(wb, run.qa_dir)
    assert "heatmap" not in ship.state(wb)["ready_pages"]

    # ── STAGE 1 · research: every cell synthesised or declared absent ────
    ev = {}
    for cell in cells[:-1]:
        ev[cell] = bank_evidence(wb, cell, n=4)
        synthesise(wb, cell, good_synthesis(cell, ev[cell]))
    declare_absent(wb, cells[-1])                 # the honest empty cell
    client_facts(wb, cells, ev)                   # §1/§6/§7 tabs

    # the brief and the handback agree with the sheets
    hb = brief.handback(wb, "P1C1")
    assert hb["done"] is True
    assert len(hb["synthesised"]) == len(cells) - 1
    assert hb["declared_absent"] == [cells[-1]]
    assert brief.unattached(wb, "P1C1") == []

    # ── STAGE 2 · the category gate, then the run-wide validator ────────
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    wb.save()
    fails = validator.validate(run.workbook_path, run_id=run.run_id)
    assert fails == [], fails

    # ── STAGE 3 · scoring opens only now, and its gate is its own ───────
    bank_peer_medians(wb, median=3.0)             # so the gap is computed
    score_stage(run, wb, cells, ev)
    assert C.stage_of(wb.metadata()) == "assessment"
    sg = [g for g in wb.rows("Gate_Log") if g.get("Gate") == "SCORING"]
    assert sg and sg[-1]["Verdict"] == "PASS"

    # every scored row carries its name, its rationale and its overlay
    scored = [r for r in wb.rows("Subcap_Scores") if r.get("subcap_id")]
    assert len(scored) == len(cells)
    for r in scored:
        assert str(r.get("subcap_name") or "").strip()
        assert str(r.get("rationale") or "").strip()

    # the rollup states every grain, and the gap is a number now
    ps = {r["Pillar"]: r for r in wb.rows("Pillar_Summary")}
    assert ps["OVERALL"]["Maturity"]
    assert float(ps["P1"]["Peer_Median"]) == 3.0
    assert ps["P1"]["Gap_to_Peer"] is not None

    # ── STAGE 4 · the app can ingest a SCORED run mid-flight ───────────
    st = ship.state(wb)
    assert "heatmap" in st["ready_pages"], st
    ck = assemble.checkpoint(run, tmp_path / "ship", push=False,
                             stage_reached="SCORED")
    man = json.loads((Path(ck["folder"]) / "run_manifest.json").read_text())
    assert man["status"] == "IN_PROGRESS" and man["stage_reached"] == "SCORED"

    # ── STAGE 5 · the reports, under their own preconditions ───────────
    make_shippable(wb)
    assert N.stage_preconditions(wb, "assessment", run.qa_dir) == []
    assert N.stage_preconditions(wb, "client_research", run.qa_dir) == []
    eids = [e for c in cells for e in ev.get(c, [])][:10]
    for key in RS.SPECS:
        write_report(wb, key, eids, run=run)
    sign_off_sections(wb)
    state = N.state(wb)
    assert state["ready"], state["blocking"]

    rendered = {}
    for key, spec in RS.SPECS.items():
        out = reports.render(wb, spec, run.deliverables)
        rendered[key] = Path(out["path"])
        assert rendered[key].is_file()
        assert out["unresolved"] == []

    # ── STAGE 6 · the fourth deliverable, and the grains the app reads ──
    from engine import techscan
    scan = techscan.render(wb, run.deliverables)
    assert Path(scan["docx"]).is_file() and Path(scan["json"]).is_file()
    assert scan["forced"] is False and scan["detections"] >= 4

    got = grains.recommendations(wb)
    assert got["rows"] >= 5
    assert all(str(r.get("Rationale") or "").strip()
               for r in wb.rows("Recommendations") if r.get("Rec_ID"))

    # ── STAGE 7 · the workbook is complete, and the package verifies ───
    comp = completeness.check(wb)
    assert comp["complete"], comp["blocking"]
    pkg = assemble.package(run, tmp_path / "packages")
    assert pkg["verified"] is True, pkg["verification"]
    folder = Path(tmp_path / "packages" / "Acme Credit Union - DMA")
    assert folder.is_dir()
    for _label, pattern, _kind in assemble.DELIVERABLES:
        assert list(folder.glob(pattern)), pattern


def test_the_stages_cannot_be_reordered(tmp_path):
    """The same claim from the other side: each stage refuses when its
    predecessor has not happened, on a run that has done nothing."""
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]

    # research → gate
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "FAIL"

    # gate → scoring
    with pytest.raises(A.ScoringRefusal):
        A.open_stage(wb, run.qa_dir)

    # scoring → reports
    with pytest.raises(N.NarrativeRefusal):
        N.write(wb, "assessment", "4",
                section_record("4", bank_evidence(wb, cell, n=3),
                               report="assessment"),
                actor="report-assessment-producer", run=run)

    # reports → the tab the app reads
    with pytest.raises(grains.GrainRefused):
        grains.recommendations(wb)

    # anything → the package
    with pytest.raises(SystemExit):
        assemble.package(run, tmp_path / "packages")


def test_a_focused_engagement_is_a_valid_run_not_a_broken_one(tmp_path):
    """The opposite failure to guard: a run scoped to ONE pillar must reach
    the end, with its scope STATED rather than refused. Every floor that
    scales — the pillar deep dives, the report word counts — scales with the
    pillars in scope, or a focused engagement could never pass."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    in_scope = sorted({c[:2] for c in wb.selected_subcaps()})
    assert in_scope == ["P1"]

    sec = RS.SPECS["assessment"].section("5")
    assert sec.card_floor == 4                       # the Doc's floor
    assert N.card_floor_for(wb, sec) == 1            # this run's floor
    assert N.min_words_for(wb, sec) == sec.card_min_words
    assert N.report_min_words_for(wb, RS.SPECS["assessment"]) < \
        RS.SPECS["assessment"].min_words

    with pytest.raises(N.NarrativeRefusal, match="no selected subcapability"):
        N.write(wb, "assessment", "5",
                section_record("5", [], report="assessment"),
                actor="report-assessment-producer", card="P3")
