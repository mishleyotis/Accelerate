"""Two validators reviewing different sections of one workbook at once keep
both verdicts (EPIC, 2026-10-18: `narrative.review` saved outside the
workbook lock, and a client-research §4 PASS was overwritten by a concurrent
assessment review's save)."""
from engine import narrative as N, report_spec as RS

from fixtures import scored_run
from test_reports import _narrate

DIMS = {d: "PASS" for d in N.REVIEW_DIMENSIONS}
NOTE = ("Checked every figure against the sheets, opened each citation, and "
        "found the weighing names its rejected reading.")


def test_a_stale_handle_does_not_erase_another_reviewers_verdict(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path, n=6)
    _narrate(wb, RS.SPECS["client_research"])
    a, b = run.open(), run.open()          # two validators, both loaded now
    secs = [s.id for s in RS.SPECS["client_research"].sections][:2]
    N.review(a, "client_research", secs[0], verdict="PASS", actor="validator-a",
             dimensions=DIMS, note=NOTE)
    N.review(b, "client_research", secs[1], verdict="PASS", actor="validator-b",
             dimensions=DIMS, note=NOTE)  # b's copy predates a's save
    rows = {str(r["Section_ID"]): r for r in run.open().rows("Report_Narrative")
            if r.get("Report") == "client_research"}
    assert rows[secs[0]]["Review_Verdict"] == "PASS"
    assert rows[secs[0]]["Review_Actor"] == "validator-a"
    assert rows[secs[1]]["Review_Actor"] == "validator-b"
