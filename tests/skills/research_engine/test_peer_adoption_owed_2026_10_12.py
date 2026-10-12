"""Every locked peer is searched for every recommended platform before the
platform page ships — and a widening re-opens the search.

R-INTERAC-20261010 (2026-10-12): the adoption search ran against ONE peer;
the owner then widened the set to five; nothing re-opened the search
(SCORING's duty fired only while Platform_Peer_Adoption was EMPTY), and the
platform page promoted 28 of 35 (product, peer) pairs reading "Not searched".
A page re-shipped after the promotion was then never re-promoted, because
PROMOTE's done-test read only "was it ever promoted".
"""
import pytest

from engine import assessment as A
from engine import page_preflight as PP
from engine import prelim as PR

from fixtures import new_run

RULE = ("national debit and real-time payment scheme operators serving "
        "financial institutions in comparable markets")
EMPTY = "searched 2026-10-12: no source names this peer as a customer of the product"


def _run(tmp_path, peers=("Peer A",)):
    run = new_run(tmp_path, n=4, prelim=False, folder=False)
    wb = run.open()
    PR.peers(wb, list(peers), rule=RULE, basis="cannot_estimate")
    wb.set_metadata("stage", "assessment")
    wb.append("Solution_Catalogue", {"solution_id": "SOL-01", "solution_name": "Integration platform",
                                     "platform": "MuleSoft Anypoint", "categories": "P4C3",
                                     "rec_id": "SOL-01"})
    return run


def test_a_peer_with_no_adoption_row_is_owed(tmp_path):
    run = _run(tmp_path, peers=("Peer A", "Peer B"))
    wb = run.open()
    A.peer_adoption(wb, product="MuleSoft Anypoint", peer="Peer A", verdict="UNKNOWN", basis=EMPTY, source="")
    gaps = A.peer_adoption_gaps(run.open())
    assert [(g["product"], g["peer"]) for g in gaps] == [("MuleSoft Anypoint", "Peer B")]
    A.peer_adoption(run.open(), product="MuleSoft Anypoint", peer="Peer B", verdict="N",
                    basis="the peer's API platform is Kong Gateway, a competing product",
                    source="https://example.com/kong-peer-b")
    assert A.peer_adoption_gaps(run.open()) == []


def test_an_unknown_that_was_never_searched_is_refused_and_counted_owed(tmp_path):
    run = _run(tmp_path)
    with pytest.raises(A.ScoringRefusal, match="never searched"):
        A.peer_adoption(run.open(), product="MuleSoft Anypoint", peer="Peer A",
                        verdict="UNKNOWN", basis="Not searched in this run: the search covered another peer only", source="")
    # a row written before this rule existed still counts as owed
    run.open().append("Platform_Peer_Adoption", {
        "Product / Layer": "MuleSoft Anypoint", "Peer": "Peer A", "Verdict": "UNKNOWN",
        "Basis": "Not searched for MuleSoft Anypoint in this run", "Source": "not established"})
    assert [g["why"] for g in A.peer_adoption_gaps(run.open())] == [
        "row records the pair was never searched"]


def test_an_advisory_line_is_closed_as_not_applicable(tmp_path):
    run = _run(tmp_path)
    run.open().append("Solution_Catalogue", {"solution_id": "SOL-02", "solution_name": "Strategy workshop",
                                             "platform": "Digital Strategy Workshop",
                                             "categories": "P1C1", "rec_id": "SOL-02"})
    A.peer_adoption(run.open(), product="MuleSoft Anypoint", peer="Peer A", verdict="UNKNOWN", basis=EMPTY, source="")
    A.peer_adoption(run.open(), product="Digital Strategy Workshop", peer="Peer A", verdict="NA",
                    basis="an advisory engagement has no vendor deployment to establish", source="")
    assert A.peer_adoption_gaps(run.open()) == []


def test_widening_the_set_logs_the_owed_searches(tmp_path):
    run = _run(tmp_path)
    A.peer_adoption(run.open(), product="MuleSoft Anypoint", peer="Peer A", verdict="UNKNOWN", basis=EMPTY, source="")
    out = PR.widen_peers(run.open(), ["Peer B", "Peer C"], rule=RULE, owner="dma@zennify.com",
                         why="client_research §4 requires three peers; owner approved")
    assert out["adoption_owed"] == 2
    rows = [r for r in run.open().rows("Gate_Log") if r.get("Gate") == "PEER_ADOPTION_OWED"]
    assert rows and "Peer B" in rows[-1]["Detail"] and str(rows[-1]["Blocking"]).lower() in ("true", "1")


def test_the_platform_page_preflight_blocks_on_owed_pairs(tmp_path):
    run = _run(tmp_path, peers=("Peer A", "Peer B"))
    A.peer_adoption(run.open(), product="MuleSoft Anypoint", peer="Peer A", verdict="UNKNOWN", basis=EMPTY, source="")
    found = [b for b in PP.preflight(run.open(), ("platform",)) if b["gate"] == "PEER-ADOPT"]
    assert found and found[0].get("severity", "block") == "block"
    assert "MuleSoft Anypoint x Peer B" in found[0]["detail"]
    assert not [b for b in PP.preflight(run.open(), ("overview",)) if b["gate"] == "PEER-ADOPT"]


# ── a page re-shipped after the promotion re-opens PROMOTE ───────────────

from engine import pipeline as P
from engine import pipeline_stub as S
from fixtures import researched_run


def test_a_page_reshipped_after_promotion_owes_a_new_promotion(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None)
    pl = P.Pipeline(run, opts)
    pl._set_md("promoted_at", "2026-10-12T16:47:39.688633+00:00")
    pl.state["pages"] = {"platform": {"status": "pass", "at": "2026-10-12T16:30:00Z"}}
    assert pl.done("PROMOTE")[0] is True
    pl.state["pages"]["platform"]["at"] = "2026-10-12T18:05:00Z"
    ok, why = pl.done("PROMOTE")
    assert ok is False and "platform" in why


# ── the tech register's peer rows owe the same searches ──────────────────

from engine import techscan as T


def _register(run):
    wb = run.open()
    wb.append("Tech_Register", {"TS_ID": "TS-001", "Product": "Dynatrace", "Vendor": "Dynatrace",
                                "Layer": "INFRA", "Status": "INFERRED"})
    return run


def test_a_register_row_compared_to_one_peer_owes_the_rest(tmp_path):
    run = _register(_run(tmp_path, peers=("Peer A", "Peer B")))
    T.peer_record(run.open(), ts_id="TS-001", peer="Peer A", deployed=None,
                  basis="searched 2026-10-12: nothing names it")
    gaps = A.tech_peer_gaps(run.open())
    assert [(g["ts_id"], g["peer"]) for g in gaps] == [("TS-001", "Peer B")]
    found = [b for b in PP.preflight(run.open(), ("techstack",)) if b["gate"] == "PEER-ADOPT"]
    assert found and "TS-001 x Peer B" in found[0]["detail"]
    # advisory: a register row the producer drops on materiality owes nothing;
    # the connector refuses a SERVED row that says it was never searched
    assert found[0]["severity"] == "warn"


def test_the_interac_wording_is_refused_at_the_write(tmp_path):
    run = _register(_run(tmp_path))
    with pytest.raises(T.ScanRefused, match="never searched"):
        T.peer_record(run.open(), ts_id="TS-001", peer="Peer A", deployed=None,
                      basis="No search for this peer on this product is recorded in this run, "
                            "so deployment is not established.")
