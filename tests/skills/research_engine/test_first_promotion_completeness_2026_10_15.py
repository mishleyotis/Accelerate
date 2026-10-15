"""A first promotion in a thin sub-vertical serves peers and a full platform set.

AAA WCNY (2026-10-15): the IB cohort held two assessed entities against a
floor of three, nothing scored the locked peers, so the workbook, both reports
and every page said "no peer benchmark"; and the platform producers scored the
8 platforms the report named while the catalogue held 136 (22 READY), so the
overview served 2 tiles. Both passed every gate — the parity gate only warns
on list length.
"""
import json

import pytest

from engine import pipeline as P
from engine import pipeline_stub as S
from engine import prelim as PR
from fixtures import new_run, researched_run

NAMES = ["Peer A", "Peer B", "Peer C"]
RULE = "regional agencies competing for the same personal-lines households"


def _peered(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False, folder=False)
    PR.peers(run.open(), NAMES, rule=RULE, basis="inferred")
    return run



def test_a_thin_cohort_owes_scores_for_every_locked_peer(tmp_path):
    run = _peered(tmp_path)
    assert PR.peers_owed_scores(run.open()) == NAMES


def test_the_peer_table_is_the_median_of_the_scored_peers(tmp_path):
    run = _peered(tmp_path)
    wb = run.open()
    cats = sorted({str(r["Category_ID"]) for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")})
    d = PR.peer_scores_dir(run)
    d.mkdir(parents=True, exist_ok=True)
    for name, s in zip(NAMES, (1.2, 1.8, 2.4)):
        (d / f"{PR._slug(name)}.json").write_text(json.dumps(
            {"peer": name, "categories": {c: {"score": s} for c in cats}}))
    out = PR.peer_table_from_scores(run.open(), d)
    assert out["categories"] == cats and out["peers"] == NAMES
    row = next(r for r in run.open().rows("Peer_Benchmarks") if r["Category_ID"] == cats[0])
    assert float(row["Peer_Median"]) == 1.8
    assert str(row["Peer_Basis"]).startswith("table:")
    assert row["Peer_Scores"] == "1.20, 1.80, 2.40"
    assert PR.peers_owed_scores(run.open()) == []          # nothing owed once a table exists
    # and a cohort refill never replaces a table row
    assert not PR.peer_row_wants_cohort(row, has_figure=True)


def test_fewer_than_three_scored_peers_is_no_table(tmp_path):
    run = _peered(tmp_path)
    d = PR.peer_scores_dir(run)
    d.mkdir(parents=True, exist_ok=True)
    (d / "peer-a.json").write_text(json.dumps({"peer": "Peer A", "categories": {}}))
    with pytest.raises(PR.PrelimRefusal, match="at least three"):
        PR.peer_table_from_scores(run.open(), d)


def _pipe(run, tmp_path, reads=None):
    return P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(S.default_handlers()),
                                     reads=reads or S.StubReads(), shipper=S.StubShipper(),
                                     push=False, folder_root=tmp_path / "o", ingest_poll_s=0,
                                     sleep=lambda s: None, log=lambda s: None))


class _FitReads(S.StubReads):
    def capability_catalogue(self, run_id):
        return {"l3_platforms": [{"l3_id": f"L3-{i}", "platform_name": f"Platform {i}"}
                                 for i in range(12)]}

    def platform_fit(self, run_id, candidates):
        return {"platforms": [{"platform": c["platform"], "l3_area": c["l3_area"],
                               "state": "READY" if i < 7 else "INSUFFICIENT_EVIDENCE",
                               "rank": i + 1 if i < 7 else None, "fit_score": 70 - i}
                              for i, c in enumerate(candidates)]}


def test_the_shortlist_scores_the_whole_catalogue(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path, reads=_FitReads())
    doc = pl._platform_shortlist("RUN-B")
    assert doc["scored"] == 12 and doc["ready"] == 7 and doc["tiles_wanted"] == 5
    assert [p["platform"] for p in doc["shortlist"]][:2] == ["Platform 0", "Platform 1"]
    assert (run.qa_dir / P.Pipeline.SHORTLIST).is_file()


def test_an_overview_with_too_few_tiles_is_failed_before_submission(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path, reads=_FitReads())
    pl._platform_shortlist("RUN-B")
    sd = pl._sections_dir()
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "overview.opportunity.json").write_text(json.dumps({"tiles": [{"platform": "Platform 0"}] * 2}))
    reasons = pl._completeness("overview")
    assert any("CG-COMPLETE overview.opportunity.tiles: 2 tile(s)" in r for r in reasons)
    (sd / "overview.opportunity.json").write_text(json.dumps({"tiles": [{"platform": "x"}] * 5}))
    assert not [r for r in pl._completeness("overview") if "tiles" in r]
