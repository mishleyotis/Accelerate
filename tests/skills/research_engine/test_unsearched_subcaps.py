"""A subcap marked no-evidence without a search is unresearched, not empty.

REPORTED 2026-08-30 against a live workbook, in two parts:

    "the agents seem not to be running concurrently with enrichment
     connectors not being called by the agents for enrichment purposes
     before close of a category"

    "the research agents have a huge issue of leaving most subcaps
     unresearched and just marking no evidence without doing deep searches"

Both were true and neither was catchable. The gate computed `search_ops` per
category, printed it, and did not use it — the same shape AUD-0022 records
for the per-category item floor. And a subcap with zero evidence hit only
`closed_below_floor`, which is ADVISORY, before

    if not synthesised:
        continue

skipped every remaining check for it: absence declaration, DQ coverage, the
contradicts probe, all of them. So a category could PASS on twenty items
contributed by a handful of worked subcaps while the rest sat empty, and the
verdict said so in a field nobody read.

Two terms now block, and the distinction between them is the point:

    category_never_searched  nobody looked at this CATEGORY at all
    absence_unsearched       this SUBCAP is empty and nobody looked at it

"We looked and found nothing" is a finding. "Nobody looked" is not, and only
the first may close a subcap.

WHY THE FLOOR IS ZERO SEARCHES AND NOT SOME OTHER NUMBER. A higher threshold
would need calibration nobody has, and inventing one here would be a number
no one measured — which is the failure being fixed. What a thin-but-nonzero
category gets instead is `tools_used` and `subcaps_searched` in the verdict,
so "searched, but never through an enrichment connector" is visible to a
reader even where it does not block.
"""
from pathlib import Path

import pytest

from engine import floors_gate
from fixtures import (bank_evidence, good_synthesis, new_run, synthesise)


def _worked(tmp_path, n=8):
    """A run where every selected subcap was actually researched."""
    run = new_run(tmp_path, n=n)
    wb = run.open()
    for cell in wb.selected_subcaps():
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=3)))
    return run, wb


def test_a_worked_category_still_passes(tmp_path):
    """The gate has to be satisfiable by doing the work, or it is a wall."""
    run, wb = _worked(tmp_path)
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    assert not v["absence_unsearched"]


def test_a_category_nobody_searched_cannot_pass(tmp_path):
    """The reported condition, reproduced: a category closed on recall."""
    run = new_run(tmp_path, n=8)
    wb = run.open()
    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert "category_never_searched" in v["blocking"], (
        f"a category with zero Search_Log rows passed the gate: {v['blocking']}")
    assert v["gate"] == "FAIL"


def test_an_empty_subcap_nobody_searched_is_named(tmp_path):
    """Most subcaps empty, a few worked — the exact reported workbook shape.

    The worked subcaps supply enough items to clear the category floor, which
    is how this used to PASS. Every unworked cell must now be named.
    """
    run = new_run(tmp_path, n=8)
    wb = run.open()
    cells = list(wb.selected_subcaps())
    worked, left = cells[:3], cells[3:]
    for cell in worked:
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=8)))

    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert v["category_floor_met"], (
        "this test needs the ITEM floor met, so the only thing that can fail "
        "the gate is the unsearched-subcap term it exists to prove")
    assert set(v["absence_unsearched"]) == set(left), (
        f"expected every unworked cell named; got {v['absence_unsearched']}")
    assert "absence_unsearched" in v["blocking"]
    assert v["gate"] == "FAIL"


def test_looked_and_found_nothing_is_not_the_same_as_nobody_looked(tmp_path):
    """The distinction the whole term rests on.

    A subcap searched honestly that yielded nothing is a finding and must NOT
    be named. If this ever fails, the gate has started punishing real
    negative results, which would push agents toward inventing evidence — the
    opposite of the intent.
    """
    from engine import ledger as L
    run = new_run(tmp_path, n=8)
    wb = run.open()
    cells = list(wb.selected_subcaps())
    for cell in cells[:3]:
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=8)))
    empty = cells[3]
    L.append_search(wb, subcap=empty, facet="works",
                    query=f"{empty} — searched, nothing published",
                    tool="web_search", hits=0, kept=0, outcome="no hits")

    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert empty not in v["absence_unsearched"], (
        "a subcap that WAS searched and honestly found nothing was reported "
        "as unresearched — that punishes negative findings and pushes an "
        "agent toward inventing evidence instead")


def test_the_verdict_shows_which_tools_ever_ran(tmp_path):
    """'Were the connectors called before the category closed' must be
    answerable FROM the verdict — it is the question that was asked."""
    run, wb = _worked(tmp_path)
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["tools_used"], "the verdict does not say what tools ran"
    assert v["subcaps_searched"].endswith(f"/{v['subcaps']}")
    searched, total = (int(x) for x in v["subcaps_searched"].split("/"))
    assert searched == total


def test_the_verdict_publishes_its_own_key_set(tmp_path):
    """The KeyError reported on 2026-08-30.

    A caller wrote `d['findings']['synthesis_missing']` and got KeyError,
    because the finding lists are spread FLAT. The shape is now published in
    the verdict rather than left to be read out of the source.
    """
    run, wb = _worked(tmp_path)
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert "findings" not in v, (
        "a nested `findings` key would silently un-break the callers that "
        "guessed it while breaking every reader of the flat shape")
    for k in v["finding_keys"]:
        assert k in v, f"finding_keys advertises {k!r} but the verdict lacks it"
    for k in ("synthesis_missing", "absence_unsearched", "evidence_smear"):
        assert k in v["finding_keys"]


def test_advisory_terms_are_named_rather_than_silently_absent(tmp_path):
    """Five terms are computed and do not block. That is a calibration
    choice; until it was named, a fired-but-advisory finding looked exactly
    like one that never fired."""
    run = new_run(tmp_path, n=8)
    wb = run.open()
    cells = list(wb.selected_subcaps())
    # One item against a floor of three, and NOT synthesised. Banking fewer
    # than three and then synthesising is refused upstream — good_synthesis
    # cites a figure only the third excerpt carries, and the grounding gate
    # catches it — so the thin cell is left unsynthesised, which is the
    # shape that actually produces a below-floor advisory in a real run.
    bank_evidence(wb, cells[0], n=1)
    for cell in cells[1:]:
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=3)))
    v = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert "closed_below_floor" in v["advisory"], (
        "one item against a floor of three did not register as advisory")
    assert "closed_below_floor" not in v["blocking"]
    assert set(v["advisory"]) <= set(floors_gate.ADVISORY_TERMS)


def test_the_recorded_file_carries_the_same_verdict(tmp_path):
    """AUD-0007: the gate's output had three readers and no writer. The new
    keys have to reach the file too, not just the return value."""
    import json
    run, wb = _worked(tmp_path)
    floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    on_disk = json.loads((run.qa_dir / "floors_P1C1.json").read_text())
    for k in ("tools_used", "subcaps_searched", "advisory", "finding_keys",
              "absence_unsearched"):
        assert k in on_disk, f"{k} never reached floors_P1C1.json"
