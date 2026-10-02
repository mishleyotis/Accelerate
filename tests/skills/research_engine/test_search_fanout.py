"""One search, several cells — and a ceiling that counts searches, not rows.

Capability grain only pays if the gate can see it. `volley_status` matches
`SubCap_ID` EXACTLY (ledger.py), so one query that genuinely answers five
sibling cells has to land five rows or four of them read as never searched
and `absence_unsearched` blocks them. That is the fan-out.

The fan-out then collides with `SEARCH_OP_CEILING`, which counted raw
Search_Log rows. Measured 2026-09-13 on the real catalogue: at capability
grain a 57-cell category fires 195 searches and writes 627 rows — the raw
count would wall it three times more often than the retrieval it did, and
walling means checkpoint-and-stop, which means re-dispatch, which is the cost
this whole change exists to remove.

The ceiling is a CONTEXT-preservation device: context is spent by the tool
call, not by the ledger write. So it counts the distinct (query, tool, facet)
a conversation put to the world. Sixty genuinely different searches still
hit the wall — that half must not soften (MEM-0338 / R27).
"""
from __future__ import annotations

import pytest

from engine import ledger as L, runstate
from engine.brief import capability_of
from fixtures import CAT, new_run


def _group(tmp_path, n=5):
    run = new_run(tmp_path, n=n, prelim=False)
    wb = run.open()
    cells = wb.selected_subcaps()
    sibs = [c for c in cells if capability_of(c) == capability_of(cells[0])]
    assert len(sibs) >= 3, "the fixture must give this test a capability group"
    return run, wb, cells, sibs


# ── the fan-out ─────────────────────────────────────────────────────────

def test_one_search_lands_a_row_for_every_cell_it_names(tmp_path):
    run, wb, cells, sibs = _group(tmp_path)
    L.append_search(wb, subcap=sibs, facet="works",
                    query='"Acme Credit Union" board digital mandate',
                    tool="exa", hits=4, kept=2, outcome="kept 2")
    rows = wb.rows("Search_Log")
    assert len(rows) == len(sibs)
    assert [str(r["SubCap_ID"]) for r in rows] == sibs
    assert [int(r["Seq"]) for r in rows] == list(range(1, len(sibs) + 1)), (
        "Seq stays dense and sequential — it is how the checkpoint mark "
        "measures its window")


def test_every_sibling_gets_the_volley_credit_the_gate_reads(tmp_path):
    """THE REASON for the fan-out. Without it, four of five cells read as
    never searched however honestly the group was worked."""
    run, wb, cells, sibs = _group(tmp_path)
    L.append_search(wb, subcap=sibs, facet="works", query="group probe q",
                    tool="exa", hits=4, kept=2)
    for c in sibs:
        v = L.volley_status(wb, c)
        assert v["fired"]["works"] == 1, f"{c} lost its volley"
        assert v["enrichment_tools"] == ["exa"], (
            f"{c} must see the connector that was asked — declare_absence "
            f"reads exactly this")


def test_a_scalar_subcap_is_unchanged(tmp_path):
    """Every existing caller passes a string. The sequence form is additive."""
    run, wb, cells, sibs = _group(tmp_path)
    L.append_search(wb, subcap=cells[0], facet="works", query="solo probe q",
                    tool="web_search", hits=1, kept=0)
    rows = wb.rows("Search_Log")
    assert len(rows) == 1 and str(rows[0]["SubCap_ID"]) == cells[0]


def test_a_search_that_names_no_cell_is_still_refused(tmp_path):
    """An empty list is no better than a missing --subcap: a search that
    counts toward nothing the gate measures is the row this refusal exists
    for."""
    run, wb, cells, sibs = _group(tmp_path)
    with pytest.raises(L.LedgerRefusal):
        L.append_search(wb, subcap=[], facet="works", query="q",
                        tool="web_search", hits=0, kept=0)
    with pytest.raises(L.LedgerRefusal):
        L.append_search(wb, subcap=["  "], facet="works", query="q",
                        tool="web_search", hits=0, kept=0)
    assert len(wb.rows("Search_Log")) == 0


def test_a_prelim_search_still_belongs_to_no_cell(tmp_path):
    run, wb, cells, sibs = _group(tmp_path)
    L.append_search(wb, subcap=None, facet=None, query="institution profile q",
                    tool="web_search", hits=2, kept=1, prelim=True)
    rows = wb.rows("Search_Log")
    assert len(rows) == 1 and not rows[0]["SubCap_ID"]


# ── the ceiling counts searches, not rows ───────────────────────────────

def test_a_fanned_search_is_charged_once(tmp_path):
    run, wb, cells, sibs = _group(tmp_path)
    L.append_search(wb, subcap=sibs, facet="works", query="group probe q",
                    tool="exa", hits=4, kept=2)
    assert len(wb.rows("Search_Log")) == len(sibs)
    assert L._ops_since_checkpoint(wb) == 1, (
        "one tool call is one op, however many cells it bore on — charging "
        "it per row walls a lane for retrieval it never did")
    assert L.stats(wb)["search_ops_since_checkpoint"] == 1, (
        "the report and the wall must read the same number")


def test_each_distinct_search_still_costs_one(tmp_path):
    """The half that must not soften: the wall still measures real work."""
    run, wb, cells, sibs = _group(tmp_path)
    for i, facet in enumerate(("works", "fails", "value")):
        L.append_search(wb, subcap=sibs, facet=facet,
                        query=f"group probe {i}", tool="exa", hits=1, kept=1)
    assert len(wb.rows("Search_Log")) == 3 * len(sibs)
    assert L._ops_since_checkpoint(wb) == 3


def test_the_same_query_at_a_different_facet_is_a_different_op(tmp_path):
    """The facet is part of the op: the same text asked of `works` and of
    `fails` is two questions, and the ceiling counts questions."""
    run, wb, cells, sibs = _group(tmp_path)
    L.append_search(wb, subcap=sibs, facet="works", query="one text",
                    tool="exa", hits=1, kept=1)
    L.append_search(wb, subcap=sibs, facet="fails", query="one text",
                    tool="exa", hits=1, kept=1)
    L.append_search(wb, subcap=sibs, facet="works", query="one text",
                    tool="tavily", hits=1, kept=1)
    assert L._ops_since_checkpoint(wb) == 3


def test_the_wall_still_stops_a_run_that_keeps_searching(tmp_path):
    """THE WALL. Sixty distinct searches, fanned across a capability, still
    refuse the sixty-first — the row count is far higher and irrelevant."""
    run, wb, cells, sibs = _group(tmp_path)
    for i in range(L.SEARCH_OP_CEILING):
        L.append_search(wb, subcap=sibs, facet="works",
                        query=f"distinct probe {i}", tool="exa", hits=1, kept=1)
    assert L._ops_since_checkpoint(wb) == L.SEARCH_OP_CEILING
    with pytest.raises(L.LedgerRefusal) as e:
        L.append_search(wb, subcap=sibs, facet="works", query="one more",
                        tool="exa", hits=1, kept=1)
    assert "search-op ceiling reached" in str(e.value)


def test_a_checkpoint_still_resets_the_window(tmp_path):
    """The ceiling is per CONVERSATION. A run that writes down where it got
    to may legitimately continue — that is the whole mechanism, not a
    loophole."""
    run, wb, cells, sibs = _group(tmp_path)
    for i in range(L.SEARCH_OP_CEILING):
        L.append_search(wb, subcap=sibs, facet="works",
                        query=f"distinct probe {i}", tool="exa", hits=1, kept=1)
    runstate.checkpoint(wb, "worked the P1C1.1 capability group")
    assert L._ops_since_checkpoint(wb) == 0
    L.append_search(wb, subcap=sibs, facet="works", query="after the mark",
                    tool="exa", hits=1, kept=1)
    assert L._ops_since_checkpoint(wb) == 1, (
        "the window measures from the mark, not from run start")


# ── the CLI ─────────────────────────────────────────────────────────────

def test_the_cli_takes_the_group_as_repeated_subcaps():
    """`engine.cli evidence` already repeated `--subcap`; search was the
    asymmetry. Read the parser rather than driving a run."""
    import inspect
    from engine import cli
    text = inspect.getsource(cli.main)
    assert 'q.add_argument("--subcap", action="append"' in text
    assert "subcap=list(a.subcap or [])" in text
