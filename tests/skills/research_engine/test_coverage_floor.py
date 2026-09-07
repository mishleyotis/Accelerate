"""A category is not researched until most of its subcaps carry evidence.

REPORTED 2026-09-01 against a live run (AUD-0115): all sixteen categories
passed the floors gate at 35% coverage — 241 of 688 subcaps carrying any
evidence, the rest closed as "no evidence". The reporter was precise about the
cause: "that is so low considering no proxy searches were done ... for each
category the rate of evidence coverage should be at least 70% with deep
searches and use of the DQs".

The item floors (>=3 per subcap, >=20 per category) measure DEPTH and let a
category pass on a handful of heavily-worked subcaps while the long tail sits
empty. `absence_unsearched` measures whether an empty cell was looked at AT
ALL, and one shallow zero-hit query clears it. Neither measures BREADTH — the
fraction of the category actually carrying evidence. `coverage_below_floor`
does, and it is a blocking term: to clear 70% an agent has to work the tail
with the diagnostic-question-driven deep search the failure was skipping.

The floor is a fraction of SUBCAPS; FLOOR_CATEGORY_ITEMS is a count of ITEMS.
The two together refuse both "few subcaps, many citations" and "many subcaps,
one citation each". This term proves the breadth half.
"""
from engine import floors_gate
from engine import ledger as L
from engine.workbook import COVERAGE_FLOOR
from fixtures import bank_evidence, good_synthesis, new_run, synthesise


def _work(wb, cell, n=5):
    synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=n)))


def _searched_empty(wb, cell):
    """A subcap looked at honestly that yielded nothing — searched, no evidence.

    This is the shape that clears `absence_unsearched` but must NOT count
    toward coverage: it is exactly the cell the deep-search directive wants
    worked further, not a cell that is done.
    """
    L.append_search(wb, subcap=cell, facet="works",
                    query=f"{cell} — searched across four queries, nothing published",
                    tool="web_search", hits=0, kept=0, outcome="no hits")


def test_a_fully_covered_category_passes(tmp_path):
    """The floor has to be satisfiable by doing the work, or it is a wall."""
    run = new_run(tmp_path, n=8)
    wb = run.open()
    for cell in wb.selected_subcaps():
        _work(wb, cell)
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    assert v["coverage_floor_met"] is True
    assert "coverage_below_floor" not in v["blocking"]
    assert v["evidence_coverage"].startswith("8/8")


def test_coverage_below_seventy_percent_fails(tmp_path):
    """The reported condition, reproduced: most subcaps empty but SEARCHED.

    The worked cells clear the per-subcap and per-category item floors, and
    every empty cell was searched — so the ONLY thing that can fail the gate
    is the coverage term this test exists to prove. Four of eight evidenced is
    50%, below the 70% floor.
    """
    run = new_run(tmp_path, n=8)
    wb = run.open()
    cells = list(wb.selected_subcaps())
    for cell in cells[:4]:
        _work(wb, cell)
    for cell in cells[4:]:
        _searched_empty(wb, cell)

    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert v["category_floor_met"], (
        "this test needs the ITEM floor met so coverage is the only failure")
    assert not v["absence_unsearched"], (
        "every empty cell was searched — absence_unsearched must not fire, or "
        "it is masking the coverage term")
    assert "coverage_below_floor" in v["blocking"], (
        f"50% coverage passed the gate: {v['blocking']}")
    assert v["gate"] == "FAIL"
    assert v["evidence_coverage"].startswith("4/8")


def test_coverage_at_or_above_the_floor_passes(tmp_path):
    """Six of eight evidenced is 75% — clears the floor with empties present."""
    run = new_run(tmp_path, n=8)
    wb = run.open()
    cells = list(wb.selected_subcaps())
    for cell in cells[:6]:
        _work(wb, cell)
    for cell in cells[6:]:
        _searched_empty(wb, cell)

    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert "coverage_below_floor" not in v["blocking"], v["blocking"]
    assert v["coverage_floor_met"] is True
    assert v["evidence_coverage"].startswith("6/8")


def test_exactly_the_floor_passes(tmp_path):
    """The boundary is inclusive: >= the floor passes, not strictly greater.

    Seven of ten is exactly 70%. If this ever flips to FAIL, the comparison
    has silently become strict and every category sitting right on the line
    would be pushed to over-research or to invent one extra citation.
    """
    run = new_run(tmp_path, n=10)
    wb = run.open()
    cells = list(wb.selected_subcaps())
    n_evidenced = round(COVERAGE_FLOOR * len(cells))
    assert n_evidenced == 7
    for cell in cells[:n_evidenced]:
        _work(wb, cell)
    for cell in cells[n_evidenced:]:
        _searched_empty(wb, cell)

    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert v["coverage_floor_met"] is True, v["evidence_coverage"]
    assert "coverage_below_floor" not in v["blocking"]


def test_a_dead_citation_does_not_count_toward_coverage(tmp_path):
    """Coverage is RESOLVABLE evidence, not the presence of an id string.

    A subcap whose only citation resolves to nothing is not covered — it is
    an unresolved citation, which already blocks. If a dead id counted toward
    coverage, an agent could clear the breadth floor by writing id strings
    that point nowhere, which is the opposite of the intent.
    """
    run = new_run(tmp_path, n=8)
    wb = run.open()
    cells = list(wb.selected_subcaps())
    for cell in cells[:6]:
        _work(wb, cell)
    # The seventh: a scoring row citing an id that was never registered.
    from engine import ledger as L2
    L2.append_search(wb, subcap=cells[6], facet="works",
                     query=f"{cells[6]} probe", tool="web_search",
                     hits=1, kept=1, outcome="kept 1")
    wb.update_row("P1_Subcap_Scoring", "SubCap_ID", cells[6],
                  {"Evidence_IDs": "E-does-not-exist"})
    _searched_empty(wb, cells[7])

    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    # Six real + one dead-cited: coverage must count only the six.
    assert v["evidence_coverage"].startswith("6/8"), v["evidence_coverage"]
    assert "unresolved_citations" in v["blocking"]


def test_the_coverage_verdict_reaches_the_recorded_file(tmp_path):
    """AUD-0007: a gate term that does not reach floors_{cat}.json is invisible
    to the three downstream readers of that file."""
    import json
    run = new_run(tmp_path, n=8)
    wb = run.open()
    for cell in wb.selected_subcaps():
        _work(wb, cell)
    floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    on_disk = json.loads((run.qa_dir / "floors_P1C1.json").read_text())
    for k in ("evidence_coverage", "coverage_floor", "coverage_floor_met"):
        assert k in on_disk, f"{k} never reached floors_P1C1.json"
    assert on_disk["coverage_floor"] == COVERAGE_FLOOR
