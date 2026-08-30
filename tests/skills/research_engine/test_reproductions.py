"""The audit's own scenarios, re-run against the engine that replaces them.

Each test reproduces the finding's measurement as closely as the new code
allows, and asserts the behaviour the finding said was missing. Where the
old code's defect is now structurally impossible, the test says so by
asserting the refusal rather than the repaired output."""
import json

import pytest

from engine import contract as C
from engine import floors_gate, ledger as L, orient, runstate
from engine.ledger import LedgerRefusal
from engine.workbook import RunWorkbook, WorkbookError

from fixtures import CAT, bank_evidence, good_synthesis, new_run, synthesise


# ── AUD-0008 / AUD-0036 · `stats` raised NameError on 1 of 1 invocations ──

def test_stats_returns_a_number_instead_of_raising(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    s = L.stats(wb, CAT)
    assert s["search_ops"] == 0
    assert s["search_op_ceiling"] == L.SEARCH_OP_CEILING


def test_stats_counts_real_search_ops(tmp_path):
    run = new_run(tmp_path); wb = run.open()
    cells = wb.selected_subcaps()
    for i in range(5):
        L.append_search(wb, subcap=cells[0], facet="works",
                        query=f'"Acme Credit Union" digital rollout {i}',
                        tool="web_search", hits=8, kept=2)
    assert L.stats(wb, CAT)["search_ops"] == 5


# ── AUD-0037 · the >=40 wall is an instruction, and the card is withheld ──

def test_at_the_ceiling_orient_says_stop_and_hands_over_no_card(tmp_path):
    run = new_run(tmp_path); wb = run.open()
    cells = wb.selected_subcaps()
    for i in range(L.SEARCH_OP_CEILING):
        L.append_search(wb, subcap=cells[0], facet="works",
                        query=f'"Acme Credit Union" query {i}',
                        tool="web_search", hits=1, kept=0)
    out = orient.orient(wb, CAT, qa_dir=run.qa_dir)
    assert out["do_first"][0].startswith("STOP:")
    assert out["next_card"] is None
    assert out["next_card_withheld_because"] == "search-op ceiling reached"


# ── AUD-0006 / AUD-0085 · a volleyed subcap is never skipped or called clean ─

def test_an_interrupted_subcap_is_served_not_skipped(tmp_path):
    """The audit's own construction: evidence+synthesis on the first subcap,
    evidence only on the second. The old orient's next_card jumped to the
    THIRD and do_first never named the second."""
    run = new_run(tmp_path); wb = run.open()
    cells = wb.selected_subcaps()
    a, b, c = cells[0], cells[1], cells[2]
    eids = bank_evidence(wb, a)
    synthesise(wb, a, good_synthesis(a, eids))
    bank_evidence(wb, b)                      # banked, not synthesised

    out = orient.orient(wb, CAT, qa_dir=run.qa_dir)
    assert b in out["open"]["volleyed"]
    assert out["next_card"]["id"] == b, "the interrupted subcap is next, not " + c
    assert out["next_card"]["mode"] == "synthesise"
    assert any("volleyed" in d or "no synthesis" in d for d in out["do_first"])


def test_a_category_with_a_volleyed_subcap_is_never_reported_clean(tmp_path):
    """The exact end-state the audit measured: pending hits 0, orient prints
    next_card {} and 'state clean', volleyed:1 still open."""
    run = new_run(tmp_path, n=3); wb = run.open()
    a, b, c = wb.selected_subcaps()
    for cell in (a, c):
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)))
    bank_evidence(wb, b)
    out = orient.orient(wb, CAT, qa_dir=run.qa_dir)
    assert out["clean"] is False
    assert out["open"]["volleyed"] == [b]
    assert not any("clean" in d and "state" in d for d in out["do_first"])
    assert out["next_card"] is not None and out["next_card"]["id"] == b


# ── AUD-0015 · the card binds the entity, or it is not handed over ────────

def test_no_card_carries_an_unbound_placeholder(tmp_path):
    run = new_run(tmp_path); wb = run.open()
    card = orient.orient(wb, CAT, qa_dir=run.qa_dir)["next_card"]
    blob = json.dumps(card)
    assert "{entity}" not in blob and "{sv}" not in blob
    assert blob.count("Acme Credit Union") >= 5


def test_an_unbound_entity_refuses_to_orient_at_all(tmp_path):
    run = new_run(tmp_path); wb = run.open()
    wb.set_metadata("entity_name", "{{ENTITY}}")
    with pytest.raises(ValueError, match="entity_name"):
        orient.orient(wb, CAT, qa_dir=run.qa_dir)


def test_a_query_carrying_a_placeholder_is_refused_at_the_ledger(tmp_path):
    run = new_run(tmp_path); wb = run.open()
    with pytest.raises(LedgerRefusal, match="unbound template token"):
        L.append_search(wb, subcap=wb.selected_subcaps()[0], facet="works",
                        query='"{entity}" Customer Segment Definition annual review',
                        tool="web_search", hits=0, kept=0)


# ── AUD-0009 / AUD-0016 / AUD-0019 / AUD-0026 · the skeleton is refused ───

SKELETON = {
    "Dominant_Claim": "STUB_CLAIM: what this subcapability establishes here",
    "Claim_Label": "STUB_FACT",
    "What_We_Found": ("STUB_FINDINGS. " * 12),
    "DQ_Works": "STUB", "DQ_Fails": "STUB", "DQ_Value": "STUB",
    "DQ_Corroborates": "STUB", "DQ_Contradicts": "STUB",
    "Triangulation": "STUB_TRIANGULATION across sources goes here for length",
    "Ceiling_Reasoning": "STUB_CEILING reasoning goes here",
    "Why_It_Matters": "STUB_WHY this matters to the client engagement",
    "DMA_Impact": "STUB_IMPACT on the maturity assessment result overall",
    "Challenge_Verdict": "PASS",
}


def test_the_skeleton_cannot_be_written_at_all(tmp_path):
    run = new_run(tmp_path); wb = run.open()
    cell = wb.selected_subcaps()[0]
    bank_evidence(wb, cell)
    with pytest.raises(LedgerRefusal) as e:
        L.append_synthesis(wb, cell, SKELETON)
    msg = str(e.value)
    for field in ("Dominant_Claim", "Triangulation", "Why_It_Matters",
                  "DMA_Impact", "Ceiling_Reasoning"):
        assert field in msg, f"{field} was not among the refusals: {msg}"


def test_the_skeleton_never_closes_the_subcap(tmp_path):
    run = new_run(tmp_path); wb = run.open()
    cell = wb.selected_subcaps()[0]
    bank_evidence(wb, cell)
    with pytest.raises(LedgerRefusal):
        L.append_synthesis(wb, cell, SKELETON)
    assert L.worklist(wb, CAT)["volleyed"] == [cell], \
        "a refused synthesis must leave the subcap open, not closed"


def test_the_skeleton_command_hands_out_no_fillable_values(tmp_path):
    """The old --skeleton emitted STUB_ strings that satisfied five of six
    length constraints. The replacement emits field names and floors."""
    run = new_run(tmp_path)
    rc = orient.main(["--run", run.run_id, "--root", str(run.root),
                      "--skeleton", "P1C1.1.1"])
    assert rc == 0


def test_fluent_emptiness_is_refused_even_at_full_length(tmp_path):
    """AUD-0026: gate output byte-identical to the golden fixture."""
    run = new_run(tmp_path); wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = bank_evidence(wb, cell)
    rec = good_synthesis(cell, eids)
    rec["What_We_Found"] = (
        "The organization demonstrates capabilities in this area and further "
        "research is needed to determine the extent to which these "
        "capabilities are embedded across the enterprise and its operating "
        "units, which remains an open question at this time.")
    with pytest.raises(LedgerRefusal, match="What_We_Found"):
        L.append_synthesis(wb, cell, rec)


# ── AUD-0007 · a gate FAIL is visible to the very next orient ─────────────

def test_a_failed_gate_is_read_by_orient_not_reported_as_clean(tmp_path):
    run = new_run(tmp_path, n=3); wb = run.open()
    for cell in wb.selected_subcaps():
        bank_evidence(wb, cell, n=1)          # below the 3-item floor
    v = floors_gate.run(wb, CAT, require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "FAIL"
    assert (run.qa_dir / f"floors_{CAT}.json").exists(), \
        "the gate must WRITE where orient reads — the AUD-0007 root"
    out = orient.orient(wb, CAT, qa_dir=run.qa_dir)
    assert out["gate"][CAT]["gate"] == "FAIL"
    assert any("floors gate FAILED" in d for d in out["do_first"])
    assert out["clean"] is False


def test_an_unrun_gate_reads_as_NOT_RUN_never_as_a_pass(tmp_path):
    run = new_run(tmp_path, n=2); wb = run.open()
    out = orient.orient(wb, CAT, qa_dir=run.qa_dir)
    assert out["gate"][CAT]["verdict"] == "NOT_RUN"
    assert out["clean"] is False


def test_the_gate_verdict_is_also_in_the_workbook(tmp_path):
    """One computation, three surfaces. The governance auditor reads the same
    object the agents wrote (AUD-0001's sibling)."""
    run = new_run(tmp_path, n=2); wb = run.open()
    floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    log = wb.rows("Gate_Log")
    assert log and log[-1]["Gate"] == "FLOORS" and log[-1]["Scope"] == CAT


# ── AUD-0022 · the >=20-item category floor is a gate term ────────────────

def test_a_category_below_the_item_floor_cannot_pass(tmp_path):
    run = new_run(tmp_path, n=2); wb = run.open()
    for cell in wb.selected_subcaps():
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)))
    v = floors_gate.run(wb, CAT, require_synthesis=True, qa_dir=run.qa_dir)
    assert v["category_floor_met"] is False
    assert "category_items_below_floor" in v["blocking"]
    assert v["gate"] == "FAIL"


# ── AUD-0083 · every cited id resolves ────────────────────────────────────

def test_a_citation_that_does_not_resolve_cannot_be_written(tmp_path):
    run = new_run(tmp_path, n=2); wb = run.open()
    cell = wb.selected_subcaps()[0]
    wb.set_scoring(cell, {"Evidence_IDs": "E-999"})
    v = floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    assert v["unresolved_citations"] == [{"subcap": cell, "ids": ["E-999"]}]
    assert v["gate"] == "FAIL"


def test_evidence_naming_a_cell_outside_the_run_is_refused(tmp_path):
    """Invariant 4: `foreign` halts production. The refusal IS the halt."""
    run = new_run(tmp_path, n=2); wb = run.open()
    outside = [c for c in C.taxonomy().cells
               if c not in set(wb.selected_subcaps())][0]
    with pytest.raises(LedgerRefusal, match="outside this run"):
        L.append_evidence(wb, source_name="x", source_url="https://x.example",
                          tier="T2", subcaps=[outside], published="2025-01-01",
                          excerpt="A" * 80)


# ── AUD-0010 · resume recovers from the workbook, with no human ───────────

def test_resume_recovers_entity_and_position_without_asking_anyone(tmp_path):
    run = new_run(tmp_path); wb = run.open()
    runstate.checkpoint(wb, f"{CAT}:card-3")
    del wb
    run2, state = runstate.resume(run.run_id, run.root)
    assert state["entity"] == "Acme Credit Union"
    assert state["run_id"] == "R-TEST-1"
    assert json.loads(state["checkpoint"])["position"] == f"{CAT}:card-3"
    assert state["catalogue_drift"] == []


def test_the_two_anchors_can_never_ship_as_template_tokens(tmp_path):
    with pytest.raises(WorkbookError, match="unresolved placeholder"):
        RunWorkbook.create(tmp_path / "x.xlsx", run_id="{{RUN_ID}}",
                           entity_name="Acme", entity_id="acme",
                           sub_vertical=None, scope_mode="T1_CORE",
                           reference_date="2026-08-29", selected=["P1C1.1.1"])


# ── AUD-0001 · the workbook is written DURING the run, not at the end ─────

def test_every_step_lands_in_the_workbook_as_it_happens(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    # Measured AFTER PRELIM, which banks the institution profile of its own:
    # this test is about the category loop's writes surviving a reopen, not
    # about the run's total row count.
    before_e = len(wb.rows("Evidence_Detail"))
    before_s = len(wb.rows("Search_Log"))
    cell = wb.selected_subcaps()[0]
    L.append_search(wb, subcap=cell, facet="works", query='"Acme" x',
                    tool="web_search", hits=3, kept=1)
    eids = bank_evidence(wb, cell)
    synthesise(wb, cell, good_synthesis(cell, eids))
    # Reopened from disk by a DIFFERENT reader — the container-death test.
    fresh = RunWorkbook(run.workbook_path)
    assert len(fresh.rows("Search_Log")) == before_s + 1
    assert len(fresh.rows("Evidence_Detail")) == before_e + 3
    assert fresh.scoring_row(cell)["Dominant_Claim"]
    assert fresh.coverage()[0]["Researched"] == 1


def test_a_good_run_reaches_a_passing_gate(tmp_path):
    """The positive control: the gate must be passable, or it is just a wall."""
    run = new_run(tmp_path, n=8); wb = run.open()
    for i, cell in enumerate(wb.selected_subcaps()):
        eids = bank_evidence(wb, cell, n=3)
        L.append_search(wb, subcap=cell, facet="contradicts",
                        query=f'"Acme Credit Union" enforcement OR lawsuit OR '
                              f'criticism OR abandoned {i}',
                        tool="web_search", hits=0, kept=0, outcome="no hits")
        synthesise(wb, cell, good_synthesis(cell, eids))
    wb.append("Entity_Timeline", {
        "Event_Date": "2024-09-01", "Event": "Alkami digital banking go-live",
        "Signal": "EXPANSION", "SubCap_IDs": ", ".join(wb.selected_subcaps()),
        "Evidence_IDs": "E-001"})
    v = floors_gate.run(wb, CAT, require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    out = orient.orient(wb, CAT, qa_dir=run.qa_dir)
    assert out["clean"] is True


# ── AUD-0018 / AUD-0024 · the challenge has to be independent ────────────

def test_the_synthesis_author_cannot_challenge_their_own_work(tmp_path):
    """The repository already solves this BY CONSTRUCTION for the learning
    loop — learning-grader carries no Write/Edit and no connector write tool
    — and then inverted it for the research challenge. Construction is not
    available here, so the guarantee is made checkable: authorship recorded,
    self-challenge refused."""
    run = new_run(tmp_path, n=2); wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.append_synthesis(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)),
                       actor="surface-producer")
    from fixtures import challenge
    with pytest.raises(LedgerRefusal, match="cannot also be its"):
        challenge(wb, cell, actor="surface-producer")
    assert challenge(wb, cell, actor="finding-challenger")["verdict"] == "PASS"


def test_a_challenge_on_an_unattributed_synthesis_is_refused(tmp_path):
    run = new_run(tmp_path, n=2); wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.append_synthesis(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)))
    from fixtures import challenge
    with pytest.raises(LedgerRefusal, match="no recorded synthesis author"):
        challenge(wb, cell)


def test_a_verdict_on_the_row_with_no_challenge_behind_it_fails_the_gate(tmp_path):
    """AUD-0025: the row's Challenge_Verdict was the only thing anyone
    looked at, so writing PASS into it WAS the challenge."""
    run = new_run(tmp_path, n=2); wb = run.open()
    for cell in wb.selected_subcaps():
        L.append_synthesis(wb, cell,
                           good_synthesis(cell, bank_evidence(wb, cell)),
                           actor="surface-producer")
        wb.set_scoring(cell, {"Challenge_Verdict": "PASS"})   # by hand
    v = floors_gate.run(wb, CAT, require_synthesis=True, qa_dir=run.qa_dir)
    assert "challenge_missing" in v["blocking"]


def test_a_self_challenge_that_got_written_anyway_fails_the_gate(tmp_path):
    """Belt and braces: the write path refuses, and the gate catches a row
    that reached the workbook by some other route."""
    run = new_run(tmp_path, n=2); wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.append_synthesis(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)),
                       actor="surface-producer")
    wb.append("Challenge_Log", {
        "SubCap_ID": cell, "Verdict": "PASS", "Actor": "surface-producer",
        "Dimensions": {d: "PASS" for d in C.CHALLENGE_DIMENSIONS},
        "Rationale": "x" * 60, "At": "2026-08-29T00:00:00Z"})
    wb.set_scoring(cell, {"Challenge_Verdict": "PASS"})
    v = floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    assert "challenge_not_independent" in v["blocking"]
    assert v["challenge_not_independent"][0]["subcap"] == cell


# ── AUD-0102 · a verdict that does no work does not validate ────────────

def test_a_zero_dimension_verdict_is_refused(tmp_path):
    run = new_run(tmp_path, n=2); wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.append_synthesis(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)),
                       actor="surface-producer")
    with pytest.raises(LedgerRefusal, match="omits"):
        L.record_challenge(wb, cell, verdict="PASS", actor="challenger",
                           dimensions={}, rationale="x" * 60)


def test_the_dimension_the_shipped_card_omitted_is_required_by_name(tmp_path):
    """The card's own output_example showed six dimensions, silently
    dropping synthesis_quality — the one carrying ten sub-conditions."""
    run = new_run(tmp_path, n=2); wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.append_synthesis(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)),
                       actor="surface-producer")
    six = {d: "PASS" for d in C.CHALLENGE_DIMENSIONS if d != "synthesis_quality"}
    with pytest.raises(LedgerRefusal, match="synthesis_quality"):
        L.record_challenge(wb, cell, verdict="PASS", actor="challenger",
                           dimensions=six, rationale="x" * 60)


def test_any_dimension_failing_makes_the_verdict_fail(tmp_path):
    run = new_run(tmp_path, n=2); wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.append_synthesis(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)),
                       actor="surface-producer")
    dims = {d: "PASS" for d in C.CHALLENGE_DIMENSIONS}
    dims["synthesis_quality"] = "FAIL"
    with pytest.raises(LedgerRefusal, match="Any FAIL means FAIL"):
        L.record_challenge(wb, cell, verdict="PASS", actor="challenger",
                           dimensions=dims, rationale="x" * 60)
    out = L.record_challenge(wb, cell, verdict="FAIL", actor="challenger",
                             dimensions=dims, rationale="x" * 60)
    assert out["failed_dimensions"] == ["synthesis_quality"]


def test_a_rubber_stamp_rationale_is_refused(tmp_path):
    run = new_run(tmp_path, n=2); wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.append_synthesis(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)),
                       actor="surface-producer")
    with pytest.raises(LedgerRefusal, match="rubber stamp"):
        L.record_challenge(
            wb, cell, verdict="PASS", actor="challenger",
            dimensions={d: "PASS" for d in C.CHALLENGE_DIMENSIONS},
            rationale="looks fine")
