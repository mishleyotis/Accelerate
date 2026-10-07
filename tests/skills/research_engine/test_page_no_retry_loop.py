"""A page is not retried when a retry cannot be sure of a different outcome.

Owner, 2026-10-07: "Do not keep ingesting and this failure loop. You ought to
be sure when submitting a page." ship_page.py submits only after both
validation passes ran locally and found nothing; the driver then stops
instead of looping when (a) the server refused the page twice on one
version, (b) the local check could not run at all, or (c) a repair left the
local refusal no smaller than before.
"""
from types import SimpleNamespace

from engine import pipeline as P


def _why(rec):
    return P.Pipeline._no_retry(SimpleNamespace(state={"pages": {"overview": rec}}),
                                "overview")


def test_one_server_refusal_earns_one_repair_the_second_halts():
    one = {"version": "B", "status": "fail", "n_history": [["B", "fail", 3]]}
    assert _why(one) is None
    two = {"version": "B", "status": "fail",
           "n_history": [["B", "fail", 3], ["B", "fail", 2]]}
    assert "refused it 2 times" in _why(two)


def test_a_check_that_could_not_run_is_never_retried_by_a_lane():
    rec = {"version": "B", "status": "local_precheck_not_run",
           "reasons": ["the local pass2 check could not run — connector down"],
           "n_history": [["B", "local_precheck_not_run", 0]]}
    assert "could not run" in _why(rec)


def test_a_repair_that_does_not_shrink_the_refusal_stops_the_loop():
    shrinking = {"version": "B", "status": "local_precheck_fail", "n_reasons": 4,
                 "n_history": [["B", "local_precheck_fail", 9], ["B", "local_precheck_fail", 4]]}
    assert _why(shrinking) is None
    stuck = {"version": "B", "status": "local_precheck_fail", "n_reasons": 9,
             "n_history": [["B", "local_precheck_fail", 9], ["B", "local_precheck_fail", 9]]}
    assert "did not converge" in _why(stuck)


def test_history_from_another_version_does_not_count():
    rec = {"version": "B", "status": "fail",
           "n_history": [["A", "fail", 3], ["B", "fail", 2]]}
    assert _why(rec) is None


def test_an_sg_v4_prose_repair_that_does_not_lower_the_count_stops():
    better = {"version": "B", "status": "sg_v4_over_budget",
              "n_history": [["B", "sg_v4_over_budget", 0, 340], ["B", "sg_v4_over_budget", 0, 310]]}
    assert _why(better) is None
    stuck = {"version": "B", "status": "sg_v4_over_budget",
             "n_history": [["B", "sg_v4_over_budget", 0, 306], ["B", "sg_v4_over_budget", 0, 306]]}
    assert "did not converge" in _why(stuck)
