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


def test_a_page_edited_after_it_passed_is_shipped_again(tmp_path):
    sections = tmp_path / "08_sections"
    sections.mkdir()
    f = sections / "overview.why_now.json"
    f.write_text("{}")
    shipped = f.stat().st_mtime
    d = SimpleNamespace(state={"pages": {"overview": {
        "versions": {"B": "pass"}, "shipped_mtime": {"B": shipped}}}})
    d._page_mtime = lambda page: max(x.stat().st_mtime for x in sections.glob(f"{page}.*.json"))
    assert P.Pipeline._page_ok(d, "overview", "B")
    import os
    os.utime(f, (shipped + 60, shipped + 60))
    assert not P.Pipeline._page_ok(d, "overview", "B"), "a repaired page is not the passed one"


def test_a_repair_that_cleared_pass_1_and_first_met_pass_2_is_not_a_stall():
    """ship_page.py runs pass 2 only once pass 1 is clean, so the first pass-2
    verdict counts gates pass 1 had hidden. Verus Financial Partners,
    2026-10-15: techstack went 1 (pass1) -> 9 (pass2) and was halted."""
    advanced = {"version": "A", "status": "local_precheck_fail", "n_reasons": 9,
                "n_history": [["A", "local_precheck_fail", 1, 0, "pass1"],
                              ["A", "local_precheck_fail", 9, 0, "pass2"]]}
    assert _why(advanced) is None
    stuck_in_pass2 = {"version": "A", "status": "local_precheck_fail", "n_reasons": 9,
                      "n_history": [["A", "local_precheck_fail", 9, 0, "pass2"],
                                    ["A", "local_precheck_fail", 9, 0, "pass2"]]}
    assert "did not converge" in _why(stuck_in_pass2)
    assert "pass2" in _why(stuck_in_pass2)
    legacy = {"version": "A", "status": "local_precheck_fail", "n_reasons": 9,
              "n_history": [["A", "local_precheck_fail", 1, 0],
                            ["A", "local_precheck_fail", 9, 0]]}
    assert "did not converge" in _why(legacy), "no pass recorded: the plain comparison stands"


def test_a_deferred_page_with_files_older_than_the_ingest_is_produced_not_shipped(tmp_path):
    """Verus (2026-10-15): techstack and heatmap deferred A->B still carried
    their version-A files; the workflow path shipped them against B before any
    producer had run for B, spending a ship and downgrading the handoff to an
    assembler-only repair."""
    import os
    sections = tmp_path / "08_sections"
    sections.mkdir()
    f = sections / "techstack.techstack.json"
    f.write_text("{}")
    old = 1_700_000_000.0
    os.utime(f, (old, old))
    d = SimpleNamespace(state={"connector": {"ingest_b": {"at": "2023-11-15T00:00:00Z"}},
                               "pages": {}})
    d._page_mtime = lambda page: max((x.stat().st_mtime for x in sections.glob(f"{page}.*.json")),
                                     default=0.0)
    d._version_ingested_at = lambda version: P.Pipeline._version_ingested_at(d, version)
    ingested = P.Pipeline._version_ingested_at(d, "B")
    assert ingested is not None and ingested > old, "the fixture's file predates the ingest"
    assert not P.Pipeline._produced_for(d, "techstack", "B")
    # produced after the ingest: this version's content
    os.utime(f, (ingested + 60, ingested + 60))
    assert P.Pipeline._produced_for(d, "techstack", "B")
    # no ingest record: the files are taken as this version's
    none = SimpleNamespace(state={"connector": {}, "pages": {}}, _page_mtime=d._page_mtime)
    none._version_ingested_at = lambda version: P.Pipeline._version_ingested_at(none, version)
    assert P.Pipeline._produced_for(none, "techstack", "B")
    assert P.Pipeline._version_ingested_at(none, "B") is None
