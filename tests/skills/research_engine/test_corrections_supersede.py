"""A validator's correction has a write path that supersedes, not duplicates.

2026-10-01 (Cross Insurance): `peer-adoption`, `prelim timeline` and `prelim
peers` only appended, so correcting a Y verdict to UNKNOWN left both rows, and
correcting "first CIO" or "27th" had no path at all.
"""
import pytest

from engine import assessment as A
from engine import prelim as P
from fixtures import new_run


def test_peer_adoption_supersedes_the_same_pair(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    wb.set_metadata("stage", "assessment")
    A.peer_adoption(wb, product="Applied Epic", peer="Hub International", verdict="Y",
                    basis="2014 press release announcing deployment", source="globenewswire")
    out = A.peer_adoption(wb, product="Applied Epic", peer="hub international",
                          verdict="UNKNOWN", basis="the press release was never registered", source="")
    rows = [r for r in wb.rows("Platform_Peer_Adoption") if r.get("Peer")]
    assert out.get("superseded") and len(rows) == 1 and rows[0]["Verdict"] == "UNKNOWN"
    A.peer_adoption(wb, product="AMS360", peer="Hub International", verdict="UNKNOWN",
                    basis="nothing public names this deployment", source="")
    assert len([r for r in wb.rows("Platform_Peer_Adoption") if r.get("Peer")]) == 2


def test_amend_rewrites_prose_in_place_and_logs_why(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    before = len([r for r in wb.rows("Entity_Timeline") if r.get("Title")])
    title = next(r["Title"] for r in wb.rows("Entity_Timeline") if r.get("Title"))
    word = title.split()[0]
    out = P.amend(wb, sheet="Entity_Timeline", column="Title", find=word,
                  replace=word + "X", why="validator: the source does not say this")
    assert out["rows_amended"] >= 1
    rows = [r for r in wb.rows("Entity_Timeline") if r.get("Title")]
    assert len(rows) == before and any(r["Title"].startswith(word + "X") for r in rows)
    assert any(r.get("Gate") == "PRELIM_AMEND" for r in wb.rows("Gate_Log"))


def test_amend_refuses_identity_columns_and_misses(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    with pytest.raises(P.PrelimRefusal):
        P.amend(wb, sheet="Peer_Benchmarks", column="Peer_Names", find="a",
                replace="b", why="renaming a peer is a re-bind, not a fix")
    with pytest.raises(P.PrelimRefusal):
        P.amend(wb, sheet="Entity_Timeline", column="Body", find="zzz-not-there",
                replace="b", why="nothing to correct here at all")


def test_peer_adoption_collapses_existing_duplicates(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    wb.set_metadata("stage", "assessment")
    for v in ("Y", "UNKNOWN"):  # the pre-fix state: two rows for one pair
        wb.append("Platform_Peer_Adoption", {"Product / Layer": "Applied Epic",
                  "Peer": "Hub International", "Verdict": v, "Basis": "x" * 25,
                  "Source": "s", "As at": "2026-10-01"})
    A.peer_adoption(wb, product="Applied Epic", peer="Hub International",
                    verdict="UNKNOWN", basis="the press release was never registered", source="")
    rows = [r for r in wb.rows("Platform_Peer_Adoption") if r.get("Peer")]
    assert [r["Verdict"] for r in rows] == ["UNKNOWN"]
