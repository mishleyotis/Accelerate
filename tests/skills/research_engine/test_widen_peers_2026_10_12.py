"""A locked peer set can be WIDENED by its owner while no figure rests on it.

R-INTERAC-20261010 (2026-10-12): PRELIM locked one peer; REPORTS refused
(client_research §4 fails below three) with "the engagement owner widens the
set" — and `lock_peer_set` refused any different set, so nothing could.
`engine.prelim widen-peers` only adds, only while every Peer_Median,
quartile and Peer_Scores cell is blank, and records the owner and reason.
"""
import pytest

from engine import prelim as PR
from engine import brief

from fixtures import new_run

RULE = ("national debit and real-time payment scheme operators serving "
        "financial institutions in comparable markets")


def _locked(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False, folder=False)
    wb = run.open()
    PR.peers(wb, ["Peer A"], rule=RULE, basis="cannot_estimate")
    return run


def _widen(wb, add=("Peer B", "Peer C"), **kw):
    args = dict(rule=RULE, owner="dma@zennify.com",
                why="client_research §4 requires three peers; owner approved")
    args.update(kw)
    return PR.widen_peers(wb, list(add), **args)


def test_the_owner_widens_a_set_no_figure_rests_on(tmp_path):
    run = _locked(tmp_path)
    out = _widen(run.open())
    assert out["locked_peer_set"] == ["Peer A", "Peer B", "Peer C"]
    wb = run.open()
    lock = wb.handoff_lock()
    assert lock["locked_peer_set"] == "Peer A|Peer B|Peer C"
    assert int(lock["peer_n"]) == 3
    assert all(int(r["Peer_N"]) == 3 and "Peer C" in r["Peer_Names"]
               for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID"))
    assert any(r.get("Gate") == "PEER_SET_WIDENED" for r in wb.rows("Gate_Log"))
    assert not [b for b in brief.report_preflight(wb) if b["kind"] == "owner"]


def test_a_set_with_a_figure_written_is_not_widened(tmp_path):
    run = _locked(tmp_path)
    wb = run.open()
    cid = next(r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID"))
    wb.update_row("Peer_Benchmarks", "Category_ID", cid, {"Peer_Median": 2.5})
    with pytest.raises(PR.PrelimRefusal, match="peer figures are already written"):
        _widen(run.open())


def test_widening_never_removes_and_needs_owner_and_reason(tmp_path):
    run = _locked(tmp_path)
    with pytest.raises(PR.PrelimRefusal, match="already in the locked set"):
        _widen(run.open(), add=["Peer A"])
    with pytest.raises(PR.PrelimRefusal, match="engagement owner"):
        _widen(run.open(), owner="")
    with pytest.raises(PR.PrelimRefusal, match="why"):
        _widen(run.open(), why="short")
    out = _widen(run.open(), add=["Peer B"])
    assert "Peer A" in out["locked_peer_set"]
