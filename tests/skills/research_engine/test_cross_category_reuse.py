"""Sixteen lanes, one entity, one register — and, until now, no route between
them.

MEASURED IN THIS REPO 2026-09-14. The ledger has always SUPPORTED reuse:
`append_evidence(subcaps=[...])` may span categories, and the floors gate
counts a citation only when the cell cites the row AND the row names the cell
back. Nothing routed it.

  * `brief.reusable` showed a cell two buckets — rows naming the cell itself,
    and rows naming a sibling under the same capability. A row another
    CATEGORY opened was invisible.
  * `brief.handback.leads_for_other_categories` was computed correctly and
    delivered to the PRODUCING category's own re-dispatch packet, which is
    the one lane it cannot help.
  * BM25 in `engine/retrieval.py` never ran over `Evidence_Detail.Excerpt`.

THE GOVERNING CONSTRAINT IS `test_subcap_match_boundary.py`. Automatic
semantic assignment of an excerpt to a cell was measured at 57.7% precision
at its best scope, against a random baseline of 17.7%, and a wrong cell
assignment passes every gate this system has. So the mechanism PROPOSES and
never attaches:

  a LEAD is a registered row whose own `SubCap_IDs` already name one of your
  cells — no inference at all, the lane that registered it said so;
  a PROPOSAL is a ranked suggestion carrying its BM25 score and the query
  terms behind it, which a lane may take with `engine.cli attach`, decline
  with a reason, or ignore;
  the gate term is ADVISORY and blocks nothing.

These tests pin each half, and the boundary between them.
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from engine import brief, contract as C, floors_gate, ledger as L
import fixtures as F


#: The excerpt a P1C1.1.1 ("Digital Strategy Document") lane would want, and
#: the one it must never be shown. Both are registered against ANOTHER
#: category's cell, so neither reaches P1C1 through the register.
RELEVANT = (
    "Acme Credit Union published a three-year digital strategy document in "
    "March 2025 setting out its vision, objectives and success criteria, "
    "approved by the board and refreshed annually by the leadership team.")
IRRELEVANT = (
    "The county fair mascot parade drew record crowds on Saturday afternoon, "
    "with nineteen floats, a marching band from the regional high school and "
    "a pie-judging contest that ran past its scheduled hour.")


def _two_lane_run(tmp_path, run_id="R-REUSE"):
    """A run spanning two categories: P1C1 is 'our' lane, the other is the
    one whose sources we have never seen."""
    run = F.new_run(tmp_path, run_id=run_id,
                    selected=F.two_category_selection())
    wb = run.open()
    cells = wb.selected_subcaps()
    mine = [c for c in cells if c.startswith("P1C1")]
    theirs = [c for c in cells if not c.startswith("P1C1")]
    assert mine and theirs, "the fixture must span two categories"
    return run, wb, mine, theirs


def _register(wb, cell, excerpt, name="Acme 2025 strategy release", **kw):
    return L.append_evidence(
        wb, source_name=name, source_url=kw.pop("url", "https://acme.example/s"),
        tier="T2", excerpt=excerpt, subcaps=[cell] if isinstance(cell, str)
        else list(cell), published="2025-03-01", **kw)


def _cells_named(blob: str, exclude_category: str) -> set[str]:
    """Every catalogue-shaped cell id in `blob` outside `exclude_category`."""
    return {m for m in re.findall(r"P\d+C\d+\.\d+\.[A-Za-z0-9]+", blob)
            if not m.startswith(exclude_category + ".")}


# ── 1 · leads reach the CONSUMING lane ──────────────────────────────────

def test_a_lead_reaches_the_lane_that_can_act_on_it(tmp_path):
    """THE ROUTING DEFECT, inverted. A row registered against one of P1C2's
    cells AND one of P1C1's is a fact about P1C1 that P1C1 could not see: the
    handback carried it to P1C2, which already had it."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, [theirs[0], mine[0]], RELEVANT)

    packet = brief.dispatch(wb, "P1C1", run=run)
    leads = packet["leads_in"]
    assert leads, "P1C1's packet must carry the row that names a P1C1 cell"
    row = next(x for x in leads if x["e_id"] == eid)
    assert row["my_cells"] == [mine[0]]
    assert theirs[0] in row["also_names"]
    assert row["excerpt"] and row["source_name"] and row["tier"]
    assert {"e_id", "url", "source_name", "tier", "recency", "excerpt",
            "my_cells", "also_names"} <= set(row)


def test_the_producing_lane_sees_the_same_row_as_its_own(tmp_path):
    """Symmetry, not duplication: each lane's view names ITS cells in
    `my_cells`. The producer's `also_names` is the consumer's `my_cells`."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, [theirs[0], mine[0]], RELEVANT)
    theirs_cat = theirs[0].split(".")[0]

    consumer = next(x for x in brief.dispatch(wb, "P1C1", run=run)["leads_in"]
                    if x["e_id"] == eid)
    producer = next(x for x in brief.dispatch(wb, theirs_cat, run=run)["leads_in"]
                    if x["e_id"] == eid)
    assert consumer["my_cells"] == producer["also_names"] == [mine[0]]
    assert producer["my_cells"] == consumer["also_names"] == [theirs[0]]


def test_a_single_category_row_is_not_a_lead(tmp_path):
    """The index is rows whose cells SPAN categories. A row naming only
    P1C1 cells is already `names_this_cell`; shipping it twice would make
    the lead section the register."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, [mine[0], mine[1]], RELEVANT)
    assert brief.leads_index(wb) == {}


# ── 2 · computed once per batch ─────────────────────────────────────────

def test_the_leads_index_is_computed_once_per_batch(tmp_path, monkeypatch):
    """It describes the RUN — the same cross-category rows for every lane —
    so rebuilding it per lane walks the whole register once per category to
    hand each one a slice of the same answer. `shared` was hoisted for this
    reason (test_capability_grain.py); this is the same hoist."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, [theirs[0], mine[0]], RELEVANT)
    n = {"calls": 0}
    real = brief.leads_index
    monkeypatch.setattr(brief, "leads_index",
                        lambda w, *a, **k: (n.__setitem__("calls", n["calls"] + 1)
                                            or real(w, *a, **k)))
    out = brief.batch(wb, run=run, out_dir=tmp_path / "b")
    assert out["lanes"] == 2, out
    assert n["calls"] == 1, f"one per batch, not one per lane (got {n['calls']})"


def test_every_lane_in_the_batch_still_gets_its_own_slice(tmp_path):
    """Hoisting changed WHO computes it, never whether the lane gets it."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, [theirs[0], mine[0]], RELEVANT)
    out = brief.batch(wb, run=run, out_dir=tmp_path / "b")
    seen = {}
    for row in out["briefs"]:
        packet = json.loads(
            (tmp_path / "b" / f"{row['category']}.json").read_text())
        seen[row["category"]] = [x["e_id"] for x in packet["leads_in"]]
    assert all(eid in v for v in seen.values()), seen


# ── 3 · the floor bites ─────────────────────────────────────────────────

def test_a_relevant_row_from_another_category_is_proposed(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    got = brief.reusable(wb, mine[0])
    props = got["proposed_from_other_categories"]
    assert props, "a row about this cell's own subject must be offered"
    p = props[0]
    assert p["e_id"] == eid and p["proposed"] is True
    assert p["bm25_vs_question"] >= brief.REUSE_PROPOSE_FLOOR
    assert p["matched_terms"], "a score with no terms behind it is unauditable"
    assert "attach" in p["how_to_use"] and mine[0] in p["how_to_use"]


def test_an_irrelevant_row_abstains(tmp_path):
    """AUD-0075's mapper filed county-fair mascots under Fair Lending
    Governance because it had no abstain path. This one does."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, theirs[0], IRRELEVANT, name="County Fair Gazette",
              url="https://fair.example/parade")
    got = brief.reusable(wb, mine[0])
    assert got["proposed_from_other_categories"] == []


def test_the_floor_is_what_separates_them(tmp_path):
    """Not a ranking cut-off: with the floor removed the irrelevant row
    ranks too, which is why the floor and not the top-N is the containment."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    good = _register(wb, theirs[0], RELEVANT)
    bad = _register(wb, theirs[1], IRRELEVANT, name="County Fair Gazette",
                    url="https://fair.example/parade")
    props = brief.reusable(wb, mine[0])["proposed_from_other_categories"]
    assert [p["e_id"] for p in props] == [good]
    assert bad not in [p["e_id"] for p in props]


def test_a_proposal_is_capped_and_marked(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    for i, cell in enumerate(theirs[:4]):
        _register(wb, cell, RELEVANT, name=f"Strategy coverage {i}",
                  url=f"https://acme.example/s{i}")
    props = brief.reusable(wb, mine[0])["proposed_from_other_categories"]
    assert len(props) <= brief.PROPOSALS_PER_CELL
    assert all(p["proposed"] is True for p in props)


def test_a_proposal_names_no_cell_of_another_category(tmp_path):
    """A proposal carries NO register link to this cell — that is what makes
    it a proposal — so naming the other lane's cell would put an unearned
    cell id in front of a lane that may not write it."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, theirs[0], RELEVANT)
    p = brief.reusable(wb, mine[0])["proposed_from_other_categories"][0]
    assert p["from_categories"] == [theirs[0].split(".")[0]]
    assert _cells_named(json.dumps(p), "P1C1") == set()


# ── 4 · a proposal is a read, never a write ─────────────────────────────

def test_computing_proposals_never_writes_to_the_workbook(tmp_path):
    """THE WHOLE CONTAINMENT IN ONE ASSERTION. A machine that silently
    attributes one category's evidence to another's cell is worse than no
    reuse at all, and the only structural guarantee is that the proposer
    cannot write."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, theirs[0], RELEVANT)
    before_bytes = hashlib.sha256(run.workbook_path.read_bytes()).hexdigest()
    before_rows = len(wb.rows("Evidence_Detail"))
    before_cites = {c: (wb.scoring_row(c) or {}).get("Evidence_IDs")
                    for c in mine}
    before_prov = len(wb.rows("Provenance"))

    brief.reusable(wb, mine[0])
    brief.dispatch(wb, "P1C1", run=run)
    brief.correlate(wb, "P1C1")
    brief.gaps(wb, run)
    brief.leads_index(wb)

    wb2 = run.open()
    assert len(wb2.rows("Evidence_Detail")) == before_rows
    assert len(wb2.rows("Provenance")) == before_prov
    assert {c: (wb2.scoring_row(c) or {}).get("Evidence_IDs")
            for c in mine} == before_cites
    assert hashlib.sha256(
        run.workbook_path.read_bytes()).hexdigest() == before_bytes, (
        "computing a proposal touched the workbook")


# ── 5 · attach cites; it does not mint ──────────────────────────────────

def test_attach_cites_an_existing_row_without_minting_a_duplicate(tmp_path):
    """`append_evidence` would mint a SECOND E-id for the same document — a
    register where one source is two identities, and `single_source_fact`
    cannot tell."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    before = len(wb.rows("Evidence_Detail"))

    out = L.attach_evidence(wb, eid, [mine[0]], actor="research-p1c1-producer")

    assert out["minted"] is False and out["e_id"] == eid
    assert len(wb.rows("Evidence_Detail")) == before, "attach must not mint"
    assert eid in str(wb.scoring_row(mine[0])["Evidence_IDs"])


def test_attach_writes_the_link_both_ways(tmp_path):
    """The floors gate counts a citation only when the cell cites the row AND
    the row names the cell back (`_named_by`, AUD-0115). A one-way attach
    looks like consolidation and counts as nothing."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    L.attach_evidence(wb, eid, [mine[0]], actor="research-p1c1-producer")
    named = str(wb.evidence_index()[eid]["SubCap_IDs"])
    assert mine[0] in named and theirs[0] in named


def test_attach_is_recorded_so_the_run_can_measure_reuse(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    L.attach_evidence(wb, eid, [mine[0]], actor="research-p1c1-producer")
    dec = L.reuse_decisions(wb, "P1C1")
    assert [d["e_id"] for d in dec["attached"]] == [eid]
    assert dec["attached"][0]["subcap"] == mine[0]
    assert dec["declined"] == []


def test_an_attached_row_stops_being_proposed(tmp_path):
    """It is now `names_this_cell` and cited, which is the strong bucket."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    L.attach_evidence(wb, eid, [mine[0]], actor="research-p1c1-producer")
    got = brief.reusable(wb, mine[0])
    assert eid not in [p["e_id"] for p in got["proposed_from_other_categories"]]
    assert eid in got["cites_now"]


# ── 6 · the four refusals, one test each ────────────────────────────────

def test_attach_refuses_an_unknown_evidence_id(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    with pytest.raises(L.LedgerRefusal) as e:
        L.attach_evidence(wb, "E-999", [mine[0]], actor="research-p1c1-producer")
    msg = str(e.value)
    assert "E-999" in msg, "the refusal must name WHAT was refused"
    assert "does not create one" in msg or "CITES a row" in msg, (
        "and WHY: attach cites, it does not register")


def test_attach_refuses_a_cell_outside_this_run(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    in_run = set(wb.selected_subcaps())
    outside = next(c for c in C.taxonomy().cells_in("P1C1")
                   if c not in in_run)
    with pytest.raises(L.LedgerRefusal) as e:
        L.attach_evidence(wb, eid, [outside], actor="research-p1c1-producer")
    msg = str(e.value)
    assert outside in msg and "engagement set" in msg


def test_attach_refuses_a_duplicate_pair(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    L.attach_evidence(wb, eid, [mine[0]], actor="research-p1c1-producer")
    with pytest.raises(L.LedgerRefusal) as e:
        L.attach_evidence(wb, eid, [mine[0]], actor="research-p1c1-producer")
    msg = str(e.value)
    assert eid in msg and mine[0] in msg
    assert "already cited" in msg and "counted twice" in msg


def test_attach_refuses_a_lane_reaching_into_another_category(tmp_path):
    """`attach` is the ONE cross-category write a lane may make, and only to
    its OWN category's cells: it cites another lane's SOURCE, never writes
    another lane's ROW. Same table, same wording as every other write
    (engine/scope.py)."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, mine[0], RELEVANT)
    with pytest.raises(L.LedgerRefusal) as e:
        L.attach_evidence(wb, eid, [theirs[0]], actor="research-p1c1-producer")
    msg = str(e.value)
    assert "only P1C1 cells" in msg and theirs[0] in msg


def test_attach_names_a_cell_or_is_refused(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    with pytest.raises(L.LedgerRefusal) as e:
        L.attach_evidence(wb, eid, [], actor="research-p1c1-producer")
    assert "names no cell" in str(e.value)


def test_the_servicing_tier_may_attach_anywhere(tmp_path):
    """The correlation point, unchanged: a conductor draining a relay batch
    consolidates across the run and forms no judgement."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, mine[0], RELEVANT)
    out = L.attach_evidence(wb, eid, [theirs[0]], actor="research-conductor")
    assert out["e_id"] == eid


def test_a_decline_is_recorded_with_its_reason(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    L.decline_evidence(wb, eid, mine[0], why="it describes the P1C2 payments "
                       "roadmap, not a board-approved digital strategy",
                       actor="research-p1c1-producer")
    dec = L.reuse_decisions(wb, "P1C1")
    assert dec["attached"] == [] and [d["e_id"] for d in dec["declined"]] == [eid]
    assert eid not in str(wb.scoring_row(mine[0])["Evidence_IDs"] or ""), (
        "a decline records a judgement; it does not cite")


def test_a_decline_with_no_reason_is_refused(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    with pytest.raises(L.LedgerRefusal) as e:
        L.decline_evidence(wb, eid, mine[0], why="  ",
                           actor="research-p1c1-producer")
    assert "indistinguishable from ignoring" in str(e.value)


# ── 7 · the gate term is advisory ───────────────────────────────────────

def _worked_but_unsynthesised(tmp_path):
    """A P1C1 that clears every EFFORT term — five volleys per cell, evidence
    on every cell — with its cells still open, plus one relevant row another
    category opened. The gate PASSes without `--require-synthesis`."""
    run, wb, mine, theirs = _two_lane_run(tmp_path, run_id="R-REUSE-GATE")
    for cell in mine:
        F.bank_evidence(wb, cell, n=5)
    _register(wb, theirs[0], RELEVANT, name="Peer strategy coverage",
              url="https://acme.example/strategy-2025")
    return run, wb, mine, theirs


def test_reuse_ignored_fires_when_proposals_go_untouched(tmp_path):
    run, wb, mine, theirs = _worked_but_unsynthesised(tmp_path)
    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert v["reuse_ignored"], (
        "proposals were offered to open cells and the lane neither attached "
        "nor declined one")


def test_reuse_ignored_never_blocks(tmp_path):
    """ADVISORY, the same way `coverage_below_floor` is: computed, reported
    in `advisory`, absent from `blocking`, and the verdict unchanged. A gate
    that blocked on a BM25 ranking would pay a lane to agree with a ranker it
    is right to overrule."""
    run, wb, mine, theirs = _worked_but_unsynthesised(tmp_path)
    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert "reuse_ignored" in v["advisory"]
    assert "reuse_ignored" not in v["blocking"]
    assert v["gate"] == "PASS", v["blocking"]


def test_reuse_ignored_is_in_the_named_advisory_set(tmp_path):
    """Kept in `ADVISORY_TERMS` rather than special-cased, so anyone arguing
    it should block can see its real hit rate first."""
    assert "reuse_ignored" in floors_gate.ADVISORY_TERMS


def test_declining_every_proposal_clears_the_term(tmp_path):
    """Judging a proposal irrelevant IS the lane doing its job; only 'nobody
    looked' fires the term."""
    run, wb, mine, theirs = _worked_but_unsynthesised(tmp_path)
    offered = brief.correlate(wb, "P1C1")["proposals"]
    assert offered
    for p in offered:
        L.decline_evidence(wb, p["e_id"], p["subcap"],
                           why="it bears on the payments roadmap, not this cell",
                           actor="research-p1c1-producer")
    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert not v["reuse_ignored"]


# ── 8 · a packet for X names no cell outside X, bar one key ─────────────

def test_a_packet_names_no_foreign_cell_except_in_also_names(tmp_path):
    """`leads_in[].also_names` is the ONE place. There the register itself
    already links the row to a cell of X, and the other cells are shown so
    the lane can see why the source was opened — everywhere else a foreign
    cell id in front of a lane that may not write it is an invitation."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, [theirs[0], mine[0]], RELEVANT)
    _register(wb, theirs[1], RELEVANT, name="Second strategy source",
              url="https://acme.example/s2")
    packet = brief.dispatch(wb, "P1C1", run=run)
    assert packet["leads_in"] and any(x["also_names"] for x in packet["leads_in"])

    stripped = json.loads(json.dumps(packet, default=str))
    for row in stripped["leads_in"]:
        row["also_names"] = []
    stray = _cells_named(json.dumps(stripped), "P1C1")
    assert stray == set(), f"a P1C1 packet named {sorted(stray)}"


def test_the_rendered_brief_holds_the_same_boundary(tmp_path):
    """The markdown is what the lane actually reads."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, [theirs[0], mine[0]], RELEVANT)
    packet = brief.dispatch(wb, "P1C1", run=run)
    md = brief.as_markdown(packet)
    assert "Sources other lanes opened that name your cells" in md
    assert "engine.cli attach" in md
    # every foreign cell in the markdown must sit on an "also names" line
    for line in md.splitlines():
        if _cells_named(line, "P1C1") and "also names" not in line:
            pytest.fail(f"foreign cell outside the also-names line: {line}")


def test_a_correlate_prompt_names_no_foreign_cell(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, theirs[0], RELEVANT)
    got = brief.correlate(wb, "P1C1")
    assert got, "the fixture must have something to correlate"
    assert _cells_named(got["prompt"], "P1C1") == set()


# ── 9 · the conductor's gap instrument ──────────────────────────────────

def test_gaps_matches_the_substrate_after_a_lane_leaves_cells_open(tmp_path):
    """Computed from the workbook, the relay queue and pipeline_state.json —
    never from a lane's report of itself, which is precisely the document
    that disagrees when something went wrong."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    worked = mine[0]
    # `append_synthesis` WITHOUT the fixture's challenge step, because
    # "synthesised and not yet challenged" is one of the gaps under test.
    L.append_synthesis(wb, worked,
                       F.good_synthesis(worked, F.bank_evidence(wb, worked)),
                       actor="research-p1c1-producer")
    F.declare_absent(wb, mine[1])

    g = brief.gaps(wb, run)["categories"]["P1C1"]
    assert worked not in g["open_cells"]
    assert mine[1] not in g["open_cells"], "a declared absence is not open"
    assert set(g["open_cells"]) == set(mine[2:])
    assert worked not in g["undeclared_empty"] and mine[1] not in g["undeclared_empty"]
    assert set(g["undeclared_empty"]) == set(mine[2:])
    assert g["challenge_deferred"] == [worked], (
        "synthesised and unchallenged is a gap the lane cannot report")
    assert g["unserviced_requests"] == 0
    assert g["stalled_rounds"] == 0


def test_gaps_reports_the_run_level_ceilings(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    g = brief.gaps(wb, run)
    assert g["rounds_remaining"] >= 1
    assert g["budget_remaining_usd"] is not None
    assert g["budget_remaining_usd"] <= g["budget_usd"]


def test_gaps_reads_the_rounds_the_pipeline_actually_recorded(tmp_path):
    """`contract.stage_of` names the stage in lower case and the pipeline
    keys `pipeline_state.json` by the driver's upper-case stage. Looking one
    up under the other reported "no rounds spent" on every run that had spent
    some, which is the opposite of what a ceiling instrument is for."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    g = brief.gaps(wb, run, state={"stages": {"RESEARCH": {"rounds": 4}},
                                   "spent_usd": 1.25, "budget_usd": 5.0})
    assert g["stage"].upper() == "RESEARCH"
    assert g["rounds_done_this_stage"] == 4
    assert g["rounds_remaining"] == 6
    assert g["budget_remaining_usd"] == 3.75


def test_gaps_counts_unattached_proposals_per_category(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, theirs[0], RELEVANT)
    eid = _register(wb, theirs[1], RELEVANT, name="Second strategy source",
                    url="https://acme.example/s2")
    before = brief.gaps(wb, run)["categories"]["P1C1"]["proposals_unattached"]
    assert before >= 1
    L.attach_evidence(wb, eid, [mine[0]], actor="research-p1c1-producer")
    after = brief.gaps(wb, run)["categories"]["P1C1"]["proposals_unattached"]
    assert after < before, "an attached proposal is no longer a gap"


def test_gaps_is_callable_in_process_by_the_driver(tmp_path):
    """A sibling stream feature-detects `getattr(brief, "gaps", None)`."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    fn = getattr(brief, "gaps", None)
    assert callable(fn)
    assert isinstance(fn(wb, run), dict)


# ── 10 · correlate: one category, and empty means empty ─────────────────

def test_correlate_is_scoped_to_one_category(tmp_path):
    """Targeted, never broadcast. A run-wide correlation map in sixteen
    contexts is the bloat this mechanism exists to avoid."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, theirs[0], RELEVANT)
    got = brief.correlate(wb, "P1C1")
    assert got["category"] == "P1C1"
    assert {p["subcap"].split(".")[0] for p in got["proposals"]} == {"P1C1"}


def test_correlate_is_empty_when_there_is_nothing_to_correlate(tmp_path):
    """Empty must mean the conductor dispatches NOTHING — not a prompt that
    says 'nothing to do', which costs a turn to say so and a lane's read to
    find out."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    assert brief.correlate(wb, "P1C1") == {}
    _register(wb, theirs[0], IRRELEVANT, name="County Fair Gazette",
              url="https://fair.example/parade")
    assert brief.correlate(wb, "P1C1") == {}, "an abstained row is not an offer"


def test_correlate_skips_cells_that_are_already_closed(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, theirs[0], RELEVANT)
    for cell in mine:
        F.synthesise(wb, cell, F.good_synthesis(cell, F.bank_evidence(wb, cell)))
    assert brief.correlate(wb, "P1C1") == {}


def test_correlate_stays_under_its_ceiling_and_carries_the_commands(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    for i, cell in enumerate(theirs):
        _register(wb, cell, RELEVANT, name=f"Strategy source {i}",
                  url=f"https://acme.example/s{i}")
    got = brief.correlate(wb, "P1C1")
    assert got["prompt_chars"] <= brief.CORRELATE_CHAR_CEILING
    assert got["shown"] >= 1 and got["shown"] <= got["offered"]
    for p in got["proposals"]:
        assert f"--e-id {p['e_id']} --subcap {p['subcap']}" in got["prompt"]


def test_correlate_drops_a_proposal_once_it_is_decided(tmp_path):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    first = brief.correlate(wb, "P1C1")["proposals"]
    for p in first:
        L.decline_evidence(wb, p["e_id"], p["subcap"], why="not this cell",
                           actor="research-p1c1-producer")
    assert brief.correlate(wb, "P1C1") == {}


# ── 11 · the handback reports the measurement ───────────────────────────

def test_the_handback_reports_offered_and_attached(tmp_path):
    """So the next argument about whether reuse is worth its complexity is
    settled with a number rather than an assertion."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    hb = brief.handback(wb, "P1C1")
    assert hb["proposals_offered"] >= 1
    assert hb["proposals_attached"] == 0 and hb["proposals_declined"] == 0

    L.attach_evidence(wb, eid, [mine[0]], actor="research-p1c1-producer")
    hb = brief.handback(wb, "P1C1")
    assert hb["proposals_attached"] == 1


def test_the_handback_still_computes_leads_for_other_categories(tmp_path):
    """Kept: the conductor reads a handback when a stage FAILs, and 'who
    opened what for whom' is the question it answers. It is no longer the
    ROUTE — `leads_index` is."""
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, [mine[0], theirs[0]], RELEVANT)
    hb = brief.handback(wb, "P1C1")
    other = theirs[0].split(".")[0]
    assert hb["leads_for_other_categories"].get(other) == [eid]


# ── 12 · the CLI ────────────────────────────────────────────────────────

def test_the_attach_cli_cites_and_refuses(tmp_path, capsys):
    from engine import cli
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    eid = _register(wb, theirs[0], RELEVANT)
    argv = ["attach", "--run", run.run_id, "--root", str(run.root),
            "--e-id", eid, "--subcap", mine[0],
            "--actor", "research-p1c1-producer"]
    assert cli.main(argv) == 0
    assert eid in str(run.open().scoring_row(mine[0])["Evidence_IDs"])
    assert cli.main(argv) == 1, "a duplicate pair must be refused, not repeated"
    assert "REFUSED" in capsys.readouterr().err


def test_the_brief_cli_serves_gaps_and_correlate(tmp_path, capsys):
    run, wb, mine, theirs = _two_lane_run(tmp_path)
    _register(wb, theirs[0], RELEVANT)
    assert brief.main(["gaps", "--run", run.run_id, "--root",
                       str(run.root), "--json"]) == 0
    assert "categories" in capsys.readouterr().out
    assert brief.main(["correlate", "--run", run.run_id, "--root",
                       str(run.root), "--category", "P1C1"]) == 0
    assert "engine.cli attach" in capsys.readouterr().out
