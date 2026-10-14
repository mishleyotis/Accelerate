"""A locked peer set can be REPLACED by its owner while no figure rests on it.

AAA Western and Central New York (2026-10-14): the PRELIM conductor locked
five other AAA clubs; the owner ruled "No AAA clubs at all". `widen-peers`
only adds, so the decision had no path short of withdrawing the run.
`engine.prelim replace-peers` swaps the set wholesale under the same guards:
every Peer_Median, quartile and Peer_Scores cell blank, the owner named, the
reason and the new rule recorded — and no grid row keeps the old rule.
"""
import pytest

from engine import prelim as PR
from engine import brief

from fixtures import new_run

OLD_RULE = ("AAA motor clubs that run their own insurance agency arm, "
            "comparable membership footprint")
NEW_RULE = ("non-AAA upstate New York insurance agencies and brokers "
            "competing for the same personal-lines households")


def _locked(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False, folder=False)
    wb = run.open()
    PR.peers(wb, ["Club A", "Club B", "Club C"], rule=OLD_RULE, basis="inferred")
    return run


def _replace(wb, peers=("Agency X", "Agency Y", "Agency Z"), **kw):
    args = dict(rule=NEW_RULE, owner="dma@zennify.com",
                why="owner ruled no AAA clubs in the peer set")
    args.update(kw)
    return PR.replace_peers(wb, list(peers), **args)


def test_the_owner_replaces_a_set_no_figure_rests_on(tmp_path):
    run = _locked(tmp_path)
    out = _replace(run.open())
    assert out["was"] == ["Club A", "Club B", "Club C"]
    assert out["locked_peer_set"] == ["Agency X", "Agency Y", "Agency Z"]
    wb = run.open()
    lock = wb.handoff_lock()
    assert lock["locked_peer_set"] == "Agency X|Agency Y|Agency Z"
    assert int(lock["peer_n"]) == 3
    assert lock["peer_basis"] == "inferred"          # the token stays locked
    grid = [r for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    assert grid
    for r in grid:
        assert "Club" not in r["Peer_Names"]
        assert r["Peer_Basis"] == f"inferred: {NEW_RULE}"
    assert any(r.get("Gate") == "PEER_SET_REPLACED" for r in wb.rows("Gate_Log"))
    assert any(r.get("Step") == "replace_peers" for r in wb.rows("Provenance"))
    assert not [b for b in brief.report_preflight(wb) if b["kind"] == "owner"]


def test_a_set_with_a_figure_written_is_not_replaced(tmp_path):
    run = _locked(tmp_path)
    wb = run.open()
    cid = next(r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID"))
    wb.update_row("Peer_Benchmarks", "Category_ID", cid, {"Peer_Median": 2.5})
    with pytest.raises(PR.PrelimRefusal, match="peer figures are already written"):
        _replace(run.open())
    assert run.open().handoff_lock()["locked_peer_set"] == "Club A|Club B|Club C"


def test_replacing_needs_owner_reason_rule_and_a_different_set(tmp_path):
    run = _locked(tmp_path)
    with pytest.raises(PR.PrelimRefusal, match="nothing to replace"):
        _replace(run.open(), peers=["Club C", "Club A", "Club B"])
    with pytest.raises(PR.PrelimRefusal, match="engagement owner"):
        _replace(run.open(), owner="")
    with pytest.raises(PR.PrelimRefusal, match="why"):
        _replace(run.open(), why="short")
    with pytest.raises(PR.PrelimRefusal, match="selection rule"):
        _replace(run.open(), rule="too short")
    with pytest.raises(PR.PrelimRefusal, match="replacement peers"):
        _replace(run.open(), peers=[" "])


def test_replace_refuses_with_no_lock(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False, folder=False)
    with pytest.raises(PR.PrelimRefusal, match="no peer set is locked"):
        _replace(run.open())
