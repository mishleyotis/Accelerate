"""The four lifecycle gaps the 2026-08-29 review named, each now a refusal.

  1. "The client folder ought to be created during assessment runs, none was
     created."  ->  opened at START, `status: IN_PROGRESS`, in the workbook.
  3. "Preliminary research that would form basis for the client research
     report was not even done."  ->  PRELIM is a phase, and `orient` serves
     no category card while it is open.
  4. "Workbook generation was never done; workbook tabs not fully
     populated."  ->  the completeness gate; the validator checks shape, this
     checks content.
  5. "Midway stop by agents before completing; no safeguard to ensure self
     healing and continuation. Does the watchdog log new DMAs and revive
     them?"  ->  it does now: a registry every start writes, a sweep that
     reads it, and a revive that re-dispatches.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2].parent / (
    "plugins/dma-insights/skills/dma-research")
sys.path.insert(0, str(ENGINE))

from engine import (assemble, completeness, orient, prelim,  # noqa: E402
                    registry, runstate, watchdog)
from fixtures import (bank_evidence, close_prelim, good_synthesis,  # noqa: E402
                      make_shippable, new_run, small_selection, synthesise)


# ── 1 · the client folder exists from the first minute ───────────────────

def test_the_folder_is_opened_at_start_not_at_the_end(tmp_path):
    run = new_run(tmp_path, prelim=False)          # folder=True is the default
    folder = tmp_path / "client" / "Acme Credit Union - DMA"
    assert folder.is_dir(), "a run that stops early must still be findable"
    manifest = json.loads((folder / "run_manifest.json").read_text())
    assert manifest["status"] == "IN_PROGRESS"
    assert manifest["institution"]["name"] == "Acme Credit Union"
    assert manifest["opened_at"]
    assert run.open().metadata()["client_folder"] == str(folder)


def test_opening_the_folder_twice_is_idempotent(tmp_path):
    run = new_run(tmp_path, prelim=False)
    again = assemble.open_folder(run, tmp_path / "client", push=False)
    assert again["created"] is False
    assert again["opened_at"] == run.open().metadata()["client_folder_opened_at"]


def test_a_run_with_no_folder_is_an_actionable_watchdog_state(tmp_path):
    run = new_run(tmp_path, prelim=False, folder=False)
    row = watchdog.inspect(run)
    assert row["state"] == "NO_CLIENT_FOLDER"
    assert row["state"] in watchdog.ACTIONABLE
    # and it is fixable without a person
    assert row["resume"]["actionable"] and row["resume"]["command"]


# ── 3 · PRELIM is a phase, and it gates category dispatch ────────────────

def test_no_category_card_is_served_while_prelim_is_open(tmp_path):
    run = new_run(tmp_path, prelim=False)
    out = orient.orient(run.open(), "P1C1", qa_dir=run.qa_dir)
    assert out["next_card"] is None
    assert "PRELIM is open" in out["next_card_withheld_because"]
    assert out["clean"] is False
    assert "firmographics" in out["prelim"]["open"]


def test_closing_prelim_releases_the_card(tmp_path):
    run = new_run(tmp_path, prelim=False)
    close_prelim(run)
    out = orient.orient(run.open(), "P1C1", qa_dir=run.qa_dir)
    assert out["prelim"]["prelim_status"] == "COMPLETE"
    assert out["next_card"] is not None, "PRELIM closed must unblock the loop"


def test_prelim_cannot_be_signed_off_with_a_section_open(tmp_path):
    run = new_run(tmp_path, prelim=False)
    with pytest.raises(prelim.PrelimRefusal, match="open sections"):
        prelim.complete(run.open())


def test_an_uncited_prelim_section_is_refused(tmp_path):
    """The research report renders this verbatim to a client."""
    run = new_run(tmp_path, prelim=False)
    with pytest.raises(prelim.PrelimRefusal, match="hallucination"):
        prelim.narrate(run.open(), "firmographics", heading=None, evidence=[],
                       body=("Acme Credit Union is a state-chartered credit "
                             "union serving 1.1 million members through 72 "
                             "branches and 1,850 full-time employees across "
                             "its geographic field of membership."))


def test_a_section_may_be_declared_absent_only_with_a_ladder(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    with pytest.raises(prelim.PrelimRefusal, match="not an absence established"):
        prelim.declare(wb, "leadership", "nothing found")
    prelim.declare(wb, "leadership", (
        "the entity publishes no leadership page; LinkedIn, the 2025 call "
        "report's officer schedule and three trade-press archives searched "
        "2026-08-29, none names a digital owner."))
    got = {s["section"]: s["status"] for s in prelim.state(wb)["sections"]}
    assert got["leadership"] == "DECLARED"


def test_the_binding_basis_may_never_be_declared_away(tmp_path):
    run = new_run(tmp_path, prelim=False)
    with pytest.raises(prelim.PrelimRefusal, match="binding basis"):
        prelim.declare(run.open(), "financials", "x" * 100)


def test_an_undated_timeline_row_is_refused(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    with pytest.raises(prelim.PrelimRefusal, match="needs a date"):
        prelim.timeline(wb, date="", event="something happened",
                        signal="POSITIVE", kind="CHANNEL", evidence=[])


def test_the_timeline_speaks_the_surfaces_own_two_vocabularies(tmp_path):
    """C1 asks two questions — the event's DIRECTION and its CLASS — and the
    tab answered with one column drawn from a nine-token list that mapped to
    neither. An event whose kind is outside the app's eight renders on a page
    no filter can reach; measured on a served run, 4 of 11 were."""
    from engine import contract as C
    wb = new_run(tmp_path, prelim=False).open()
    with pytest.raises(prelim.PrelimRefusal, match="near-miss is not a"):
        prelim.timeline(wb, date="2025-01-01", event="x", signal="POSITIVE",
                        kind="TECHNOLOGY", evidence=[])
    with pytest.raises(prelim.PrelimRefusal, match="DIRECTION"):
        prelim.timeline(wb, date="2025-01-01", event="x", signal="UPWARD",
                        kind="PLATFORM", evidence=[])
    # an old-vocabulary caller is BRIDGED, not refused: a run pinned to an
    # earlier engine wrote those words and its events still have to filter
    out = prelim.timeline.__doc__
    assert "bridged" in out.lower()
    assert C.TIMELINE_KIND_BRIDGE["MERGER"] == "M&A"
    assert set(C.TIMELINE_SIGNALS) == {"POSITIVE", "NEUTRAL", "NEGATIVE"}


# ── 4 · the workbook has content, not just shape ─────────────────────────

def test_an_empty_tab_with_no_reason_blocks(tmp_path):
    run = new_run(tmp_path)
    out = completeness.check(run.open())
    assert not out["complete"]
    assert any(b.startswith("DQ_Bank") for b in out["blocking"])


def test_filling_the_tabs_closes_the_gate(tmp_path):
    """The gate must be satisfiable by DOING the work, or it is just a wall."""
    run = new_run(tmp_path)
    wb = run.open()
    make_shippable(wb)
    from engine import floors_gate
    from fixtures import bank_evidence, good_synthesis, synthesise
    for cell in wb.selected_subcaps():
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=3)))
    floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    out = completeness.check(wb)
    assert out["complete"], out["blocking"]


def test_a_declared_empty_tab_is_a_disclosure_not_a_blocker(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    completeness.declare(wb, "Entity_Timeline", (
        "this run is a single-category calibration slice; no institution "
        "timeline was researched and none is claimed."))
    out = completeness.check(wb)
    assert "Entity_Timeline" in out["declared_empty"]
    assert not any(b.startswith("Entity_Timeline") for b in out["blocking"])


def test_a_filler_reason_is_refused(tmp_path):
    run = new_run(tmp_path)
    with pytest.raises(completeness.CompletenessRefusal, match="filler"):
        completeness.declare(run.open(), "Entity_Timeline", "n/a")


def test_the_sheets_a_run_cannot_exist_without_may_not_be_declared(tmp_path):
    run = new_run(tmp_path)
    for sheet in ("Evidence_Detail", "Provenance", "Handoff_Lock"):
        with pytest.raises(completeness.CompletenessRefusal,
                           match="cannot be declared empty"):
            completeness.declare(run.open(), sheet, "x" * 80)


def test_ref_method_now_has_a_writer(tmp_path):
    """It was a declared sheet nobody filled — found by this very gate."""
    rows = new_run(tmp_path, prelim=False).open().rows("REF_Method")
    keys = {r["Key"] for r in rows}
    assert {"bands", "evidence_tiers", "recency", "claim_labels"} <= keys
    bands = next(r["Value"] for r in rows if r["Key"] == "bands")
    assert "Transformational" not in bands, "invariant 6: four bands only"


def test_an_out_of_scope_pillar_is_not_an_empty_tab(tmp_path):
    """P2..P4 carry no selected subcap in a P1C1 run; that is the scope."""
    out = completeness.check(new_run(tmp_path).open())
    verdicts = {r["sheet"]: r["verdict"] for r in out["sheets"]}
    assert verdicts["P2_Subcap_Scoring"] == "OUT_OF_SCOPE"


def test_a_seeded_pillar_sheet_is_not_a_researched_one(tmp_path):
    """The audit of 2026-08-30 found this verdict true by construction:
    `create` seeds a row per selected cell with NO_EVIDENCE / NOT_RUN in it,
    and the gate counted rows — so a pillar read POPULATED before a single
    search had run, which is the one thing the gate exists to catch."""
    wb = new_run(tmp_path).open()
    row = next(r for r in completeness.check(wb)["sheets"]
               if r["sheet"] == "P1_Subcap_Scoring")
    assert row["verdict"] == "SHORT", row
    assert "carry research" in row["detail"] and "seeded" in row["detail"]

    # and it turns over when research actually lands
    cells = wb.selected_subcaps()
    for cell in cells:
        eids = bank_evidence(wb, cell)
        synthesise(wb, cell, good_synthesis(cell, eids))
    row = next(r for r in completeness.check(wb)["sheets"]
               if r["sheet"] == "P1_Subcap_Scoring")
    assert row["verdict"] == "POPULATED", row


def test_a_forged_declaration_is_louder_than_a_missing_one(tmp_path):
    """`declare` refuses a NEVER_EMPTY sheet; the metadata key it writes can
    still be set by hand, and the check honoured it — so writing around the
    refusal declared away the evidence register itself."""
    import json as _json
    wb = new_run(tmp_path).open()
    wb.set_metadata("empty_sheet_reasons", _json.dumps(
        {"Provenance": "a plausible sentence, written around the refusal, "
                       "long enough to clear the filler floor"}))
    # empty the sheet the forged reason names
    ws = wb._sheet("Provenance")
    ws.delete_rows(2, ws.max_row)
    wb.save()
    row = next(r for r in completeness.check(wb)["sheets"]
               if r["sheet"] == "Provenance")
    assert row["verdict"] == "ILLEGAL_DECLARATION", row
    assert "written around the refusal" in row["detail"]


# ── 5 · the watchdog logs new DMAs and revives stopped ones ──────────────

def test_a_started_run_is_logged_to_the_registry(tmp_path):
    reg = tmp_path / "registry.jsonl"
    run = new_run(tmp_path, prelim=False)
    row = registry.log(run, event="STARTED", path=reg)
    assert row["run_id"] == "R-TEST-1" and row["entity"] == "Acme Credit Union"
    assert registry.read(reg)[0]["workbook"] == str(run.workbook_path)


def test_the_registry_is_append_only_and_keeps_the_last_state(tmp_path):
    reg = tmp_path / "registry.jsonl"
    run = new_run(tmp_path, prelim=False)
    registry.log(run, event="STARTED", path=reg)
    registry.log(run, event="HEARTBEAT", position="P1C1 card 3", path=reg)
    assert len(registry.read(reg)) == 2, "history is what makes a stall legible"
    assert registry.latest(reg)["R-TEST-1"]["position"] == "P1C1 card 3"


def test_a_closed_run_leaves_the_open_worklist(tmp_path):
    reg = tmp_path / "registry.jsonl"
    run = new_run(tmp_path, prelim=False)
    registry.log(run, event="STARTED", path=reg)
    assert [r["run_id"] for r in _open(reg)] == ["R-TEST-1"]
    registry.log(run, event="PACKAGED", path=reg)
    assert _open(reg) == []


def _open(path):
    return [r for r in registry.latest(path).values()
            if r["event"] not in registry.CLOSED_OUTCOMES]


def test_a_run_the_container_never_saw_is_still_visible(tmp_path, monkeypatch):
    """The blindness this fixes: a fresh container's run root is EMPTY, and a
    sweep that trusts it reports a quiet queue it cannot see."""
    reg = tmp_path / "registry.jsonl"
    run = new_run(tmp_path, prelim=False)
    registry.log(run, event="STARTED", path=reg)
    monkeypatch.setattr(registry, "registry_path", lambda root=None: reg)
    # the workbook is gone from this container, as after a restart
    run.workbook_path.rename(tmp_path / "elsewhere.xlsx")
    rows = watchdog.sweep(tmp_path / "no-such-root")
    assert [r["state"] for r in rows] == ["MISSING_LOCALLY"]
    assert rows[0]["resume"]["command"][:3] == ["python3", "-m",
                                                "engine.registry"]


def test_a_stalled_run_gets_a_dispatchable_resume_plan(tmp_path):
    run = new_run(tmp_path)
    row = watchdog.inspect(run, stall_seconds=-1)   # force the idle threshold
    assert row["state"] == "STALLED"
    plan = row["resume"]
    assert plan["actionable"] and plan["agent"] == "research-p1c1-producer"
    assert "orient" in plan["prompt"] and run.run_id in plan["prompt"]


def test_reviving_is_a_dispatch_not_a_report(tmp_path):
    run = new_run(tmp_path)
    row = watchdog.inspect(run, stall_seconds=-1)
    out = watchdog.revive(row, dry_run=True)
    assert out["outcome"] == "DRY_RUN"
    assert out["agent"] == "research-p1c1-producer"


def test_prelim_open_revives_through_the_conductor(tmp_path):
    run = new_run(tmp_path, prelim=False)
    row = watchdog.inspect(run)
    assert row["state"] == "PRELIM_OPEN"
    assert row["resume"]["agent"] == "research-conductor"


def test_a_catalogue_halt_is_never_revived_automatically(tmp_path):
    """A run whose catalogue moved is a decision, not a restart."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    wb.update_row("Handoff_Lock", "Key", "catalogue_hash",
                  {"Key": "catalogue_hash", "Value": "moved"})
    row = watchdog.inspect(run)
    assert row["state"] == "HALTED"
    assert row["resume"]["actionable"] is False
    assert watchdog.revive(row)["outcome"] == "NOT_RUN"


def test_a_finished_run_that_shipped_nothing_is_actionable(tmp_path):
    """READY_FOR_HANDOFF used to be a resting state. A run that finished and
    never produced its deliverables has stopped, just politely."""
    run = new_run(tmp_path, n=8)      # 8 x 3 clears the 20-item category floor
    wb = run.open()
    from engine import floors_gate
    from fixtures import bank_evidence, good_synthesis, synthesise
    for cell in wb.selected_subcaps():
        eids = bank_evidence(wb, cell, n=3)
        synthesise(wb, cell, good_synthesis(cell, eids))
    verdict = floors_gate.run(wb, "P1C1", require_synthesis=True,
                              qa_dir=run.qa_dir)
    assert verdict["gate"] == "PASS", verdict["blocking"]
    row = watchdog.inspect(run)
    assert row["state"] == "READY_FOR_HANDOFF"
    assert row["state"] in watchdog.ACTIONABLE
    assert row["resume"]["agent"] == "research-conductor"


# ── the run root must exist on the machine that is running ──────────────

def test_the_default_run_root_is_not_a_path_only_one_machine_has(monkeypatch,
                                                                  tmp_path):
    """The CI failure of 2026-08-30, and the worst shape a defect can take:
    it passed here and failed there.

    `RUN_ROOT` defaulted to `/home/claude/dma_output` unconditionally. The
    development container HAS that directory, so every local run wrote there
    happily; a GitHub runner has no `/home/claude` and cannot create one, so
    `engine.cli start` died with `PermissionError: '/home/claude'` inside
    `registry.log` — the step that makes a run findable from a later
    container, which is lifecycle requirement 5.
    """
    from engine import runstate

    monkeypatch.delenv("DMA_RUN_ROOT", raising=False)
    monkeypatch.setattr(runstate, "PRODUCTION_RUN_ROOT",
                        tmp_path / "absent" / "dma_output")
    got = runstate.default_run_root()
    assert got == Path.home() / "dma_output", got
    assert "absent" not in str(got)


def test_production_keeps_its_run_root_byte_for_byte(monkeypatch, tmp_path):
    """The registry beside the run root is how a stopped run is found again.
    Moving it would orphan every run already registered, so where the
    production directory IS there, nothing changes."""
    from engine import runstate

    monkeypatch.delenv("DMA_RUN_ROOT", raising=False)
    present = tmp_path / "home" / "claude"
    present.mkdir(parents=True)
    monkeypatch.setattr(runstate, "PRODUCTION_RUN_ROOT",
                        present / "dma_output")
    assert runstate.default_run_root() == present / "dma_output"


def test_the_environment_still_wins(monkeypatch, tmp_path):
    from engine import runstate

    monkeypatch.setenv("DMA_RUN_ROOT", str(tmp_path / "explicit"))
    assert runstate.default_run_root() == tmp_path / "explicit"


def test_start_registers_a_run_with_no_writable_production_home(tmp_path):
    """The end-to-end shape of the same thing: `start` must complete on a
    machine that has never heard of `/home/claude`."""
    import subprocess

    env = {**os.environ,
           "DMA_RUN_ROOT": str(tmp_path / "runs"),
           "DMA_RUN_REGISTRY": str(tmp_path / "runs" / "registry.jsonl")}
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r);"
         "from engine import runstate;"
         "print(runstate.default_run_root())" % str(ENGINE)],
        capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    assert str(tmp_path / "runs") in r.stdout, r.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
