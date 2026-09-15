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

---

UPDATE 2026-09-13 — BOTH TERMS ARE NOW ADVISORY (owner: "remove the coverage
rule … what matters is that all categories are scored").

The reporter's concern above was real and stands. The instrument was wrong.
Coverage measures how much the world happened to publish about the client,
which the run does not control — and the floor was never calibrated: measured
on the reference it was supposedly set from, Golden 1 Credit Union fails
`coverage_below_floor` in 9 of its 16 categories in HYBRID, the mode it was
actually run in. On public evidence alone, 13 of 16 fail. No PUBLIC-mode
assessment of a private entity could ever have passed it.

What the reporter asked for — deep searches, the DQs, proxy searches before
an absence — is enforced by the EFFORT terms, which still block:
`volleys_incomplete`, `primary_unfired`, `absence_unsearched`,
`absence_undeclared_empty`, `absence_single_tool`. Those measure the work,
which the run does control.

And the containment against a thin run scoring high already existed
downstream: `assessment.ceiling_for` caps a no-evidence cell at M2 (CAP-T5).
Verified end to end — a declared-absent cell scores 1.0 against a ceiling of
2.0. The floor was redundant protection that blocked honest runs while the
ceiling did the real work.

Both figures are still computed and still reported. These tests now pin that:
the measurement must stay exact, because it is disclosed on every verdict and
anyone re-calibrating reads it.
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


def test_coverage_below_the_floor_is_measured_and_advisory(tmp_path):
    """The reported condition, reproduced — and no longer blocking.

    Four of eight evidenced is 50%, below the 70% floor. Until 2026-09-13 that
    FAILED the gate. It is now computed, reported, and advisory: coverage
    measures how much the world published about the client, which is not a
    judgement about the run.

    What the reporter actually asked for — "no proxy searches were done …
    deep searches and use of the DQs" — is enforced by the EFFORT terms, and
    this fixture shows them doing it: the empty cells here were touched by one
    shallow query, so `volleys_incomplete`, `primary_unfired` and
    `absence_undeclared_empty` all fire. The concern was real; the coverage
    floor was the wrong instrument for it.
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
        "this test needs the ITEM floor met so coverage is isolated")
    assert not v["absence_unsearched"], "every empty cell was searched"

    # measured and disclosed
    assert v["coverage_floor_met"] is False
    assert v["evidence_coverage"].startswith("4/8")
    assert "coverage_below_floor" in v["advisory"]
    # but not blocking
    assert "coverage_below_floor" not in v["blocking"]
    # and the shallow work that DID happen is still caught, by the right terms
    assert {"volleys_incomplete", "primary_unfired",
            "absence_undeclared_empty"} <= set(v["blocking"]), v["blocking"]


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
