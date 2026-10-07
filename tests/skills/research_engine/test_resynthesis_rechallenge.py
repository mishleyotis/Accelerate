"""A repaired synthesis must be challenged again, and only then scored.

Measured 2026-10-01 (Cross Insurance): an independent challenger FAILed a
cell, its producer re-synthesised it, and the row kept the FAIL. The
challenge batcher skips any row carrying a verdict and `assessment score`
refuses any evidenced row that is not PASS, so the repaired cell could
never be re-challenged nor scored — a stall no round could clear.
"""
from engine import brief, ledger as L
from fixtures import (bank_evidence, challenge, fire_volleys, good_synthesis,
                      new_run)

AUTHOR = "research-p1c1-producer"


def synthesise(wb, cell, record):
    return L.append_synthesis(wb, cell, record, actor=AUTHOR)


def _failed_then_repaired(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = bank_evidence(wb, cell)
    fire_volleys(wb, cell)
    synthesise(wb, cell, good_synthesis(cell, eids))
    challenge(wb, cell, verdict="FAIL")
    assert wb.scoring_row(cell)["Challenge_Verdict"] == "FAIL"
    synthesise(wb, cell, repaired(good_synthesis(cell, eids)))   # the repair
    return run, wb, cell


def repaired(rec: dict) -> dict:
    """A repair CHANGES the text (2026-10-07): the engine refuses a record
    identical to the one the challenger FAILED, because re-sending it only
    buys the same verdict again."""
    out = dict(rec)
    out["What_We_Found"] = rec["What_We_Found"] + (
        " The board pack's quarterly review is the counter-source the "
        "challenger asked for, and it names the same cadence.")
    return out


def test_an_unchanged_resynthesis_under_a_fail_is_refused(tmp_path):
    import pytest
    run = new_run(tmp_path, n=3, prelim=False)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = bank_evidence(wb, cell)
    fire_volleys(wb, cell)
    rec = good_synthesis(cell, eids)
    synthesise(wb, cell, rec)
    challenge(wb, cell, verdict="FAIL")
    with pytest.raises(L.LedgerRefusal, match="identical"):
        synthesise(wb, cell, dict(rec))
    assert wb.scoring_row(cell)["Challenge_Verdict"] == "FAIL"   # nothing cleared


def test_resynthesis_clears_the_stale_verdict(tmp_path):
    _, wb, cell = _failed_then_repaired(tmp_path)
    assert not (wb.scoring_row(cell).get("Challenge_Verdict") or "")
    # the old verdict stays in the log as history
    assert L.challenge_for(wb, cell)["Verdict"] == "FAIL"


def test_repaired_cell_is_back_in_the_challenge_queue(tmp_path):
    run, wb, cell = _failed_then_repaired(tmp_path)
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "ch")
    assert cell in str(out), out


def test_a_fresh_pass_after_repair_is_recorded(tmp_path):
    _, wb, cell = _failed_then_repaired(tmp_path)
    challenge(wb, cell, verdict="PASS")
    assert wb.scoring_row(cell)["Challenge_Verdict"] == "PASS"


def test_a_first_synthesis_has_no_verdict_to_clear(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = bank_evidence(wb, cell)
    fire_volleys(wb, cell)
    synthesise(wb, cell, good_synthesis(cell, eids))
    assert not (wb.scoring_row(cell).get("Challenge_Verdict") or "")
