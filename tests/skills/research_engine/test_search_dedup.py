"""The same question is not asked twice.

Measured 28-09-2026 (QA audit F-D05-033): `engine.cli search` accepted the
same query twice into the Search_Log — rows 1 and 2 identical — and the
only dedupe anywhere was the relay's, over relay requests. A repeated
search pays for the answer the log already holds. These tests pin the
refusal at the write, the one legitimate extension (the same search logged
against a cell it was not logged against), the identity rule (case,
whitespace, outer quotes; the tool is part of it), and the exclusion list
the brief states.
"""
import pytest

from engine import ledger as L
from engine import quality as Q
from fixtures import new_run


def _one(wb, q, *, cell="P1C1.1.1", tool="web_search", facet="works"):
    return L.append_search(wb, subcap=cell, facet=facet, query=q, tool=tool,
                           hits=3, kept=1, outcome="kept 1")


def test_the_same_query_through_the_same_tool_is_refused_naming_the_prior_row(tmp_path):
    wb = new_run(tmp_path).open()
    seq = _one(wb, '"Acme Credit Union" P1C1.1.1 digital strategy document')
    before = len(wb.rows("Search_Log"))
    with pytest.raises(L.LedgerRefusal) as e:
        _one(wb, '"Acme Credit Union" P1C1.1.1 digital strategy document')
    msg = str(e.value)
    assert f"seq {seq}" in msg and "F-D05-033" in msg
    assert "rephrase" in msg.lower() or "different" in msg.lower(), (
        "the refusal must name the way out")
    assert len(wb.rows("Search_Log")) == before, "nothing was written"


def test_the_identity_ignores_case_whitespace_and_outer_quotes(tmp_path):
    wb = new_run(tmp_path).open()
    _one(wb, '"Acme Credit Union"   P1C1.1.1 Digital Strategy')
    for variant in ('acme credit union" p1c1.1.1 digital strategy',
                    '"ACME CREDIT UNION" P1C1.1.1 DIGITAL STRATEGY"',
                    '  "Acme Credit Union" P1C1.1.1 digital   strategy  '):
        with pytest.raises(L.LedgerRefusal):
            _one(wb, variant)
    assert Q.norm_query(' "A  b" ') == "a b"


def test_a_different_facet_is_a_different_question_and_the_same_one_is_refused(tmp_path):
    """The facet is part of the op (test_search_fanout: the same text asked
    of `works` and of `fails` is two questions, and the ceiling counts
    questions). The identity the log refuses on is (query, tool, facet)."""
    wb = new_run(tmp_path).open()
    _one(wb, '"Acme Credit Union" P1C1.1.1 roadmap', facet="works")
    _one(wb, '"Acme Credit Union" P1C1.1.1 roadmap', facet="value")
    with pytest.raises(L.LedgerRefusal):
        _one(wb, '"Acme Credit Union" P1C1.1.1 roadmap', facet="value")
    # the facet-blind reading still sees both
    assert len(L.prior_searches(wb, '"Acme Credit Union" P1C1.1.1 roadmap', "web_search")) == 2
    assert len(L.prior_searches(wb, '"Acme Credit Union" P1C1.1.1 roadmap', "web_search",
                                facet="works")) == 1


def test_a_different_tool_is_a_different_search(tmp_path):
    wb = new_run(tmp_path).open()
    _one(wb, '"Acme Credit Union" P1C1.1.1 roadmap', tool="web_search")
    _one(wb, '"Acme Credit Union" P1C1.1.1 roadmap', tool="exa")
    assert len(L.prior_searches(wb, '"Acme Credit Union" P1C1.1.1 roadmap', "exa")) == 1


def test_extending_a_search_to_a_new_cell_writes_only_the_new_row(tmp_path):
    """One call that bore on two cells but was logged against one: the
    second cell may be added (one row), the first is not written again."""
    wb = new_run(tmp_path).open()
    _one(wb, '"Acme Credit Union" board technology committee', cell="P1C1.1.1")
    n = len(wb.rows("Search_Log"))
    L.append_search(wb, subcap=["P1C1.1.1", "P1C1.1.2"], facet="works",
                    query='"Acme Credit Union" board technology committee',
                    tool="web_search", hits=3, kept=1)
    rows = [r for r in wb.rows("Search_Log")
            if "board technology committee" in str(r.get("Query"))]
    assert len(wb.rows("Search_Log")) == n + 1
    assert sorted(str(r["SubCap_ID"]) for r in rows) == ["P1C1.1.1", "P1C1.1.2"]


def test_prior_queries_is_the_exclusion_list_for_a_cell(tmp_path):
    wb = new_run(tmp_path).open()
    _one(wb, '"Acme Credit Union" P1C1.1.1 strategy', cell="P1C1.1.1")
    _one(wb, '"Acme Credit Union" P1C1.1.1 strategy', cell="P1C1.1.1", tool="exa")
    _one(wb, '"Acme Credit Union" P1C1.1.2 alignment', cell="P1C1.1.2")
    got = L.prior_queries(wb, ["P1C1.1.1"])
    assert [(g["tool"], g["query"]) for g in got] == [
        ("web_search", '"Acme Credit Union" P1C1.1.1 strategy'),
        ("exa", '"Acme Credit Union" P1C1.1.1 strategy')]
    assert all(g["cells"] == ["P1C1.1.1"] for g in got)
    assert got[0]["hits"] == 3 and got[0]["kept"] == 1
    # run-level rows only when asked
    L.append_search(wb, subcap=None, facet="works", query="acme annual report 2025",
                    tool="web_search", hits=1, kept=1, prelim=True)
    # The fixture's PRELIM pass logs its own issue-register sweep (facet
    # "issues"); this test's run-level row is the one under "works".
    assert [g["query"] for g in L.prior_queries(wb, prelim=True)
            if g.get("facet") != "issues"] == ["acme annual report 2025"]
    assert "acme annual report 2025" not in [g["query"] for g in L.prior_queries(wb, ["P1C1.1.1"])]


def test_the_cli_refuses_with_rc_1_and_says_refused(tmp_path):
    from engine import cli
    run = new_run(tmp_path)
    argv = ["search", "--run", run.run_id, "--root", str(run.root),
            "--subcap", "P1C1.1.1", "--facet", "works", "--tool", "web_search",
            "--query", '"Acme Credit Union" P1C1.1.1 rollout', "--hits", "2",
            "--kept", "1", "--actor", "research-p1c1-producer"]
    assert cli.main(argv) == 0
    assert cli.main(argv) == 1
