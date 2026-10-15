"""A first promotion in a thin sub-vertical serves peers and a full platform set.

AAA WCNY (2026-10-15): the IB cohort held two assessed entities against a
floor of three, nothing scored the locked peers, so the workbook, both reports
and every page said "no peer benchmark"; and the platform producers scored the
8 platforms the report named while the catalogue held 136 (22 READY), so the
overview served 2 tiles. Both passed every gate — the parity gate only warns
on list length.
"""
import inspect
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
    # five tiles are not enough: they must be the top five platform cards,
    # in card-rank order, with the card's figures (deterministic)
    (sd / "overview.opportunity.json").write_text(json.dumps({"tiles": [{"platform": "x"}] * 5}))
    assert [r for r in pl._completeness("overview") if "tiles" in r]
    cards = [{"platform": f"Platform {i}", "rank": i + 1, "fit_score": 70 - i} for i in range(5)]
    (sd / "platform.platform_story.json").write_text(json.dumps({"platforms": cards}))
    (sd / "overview.opportunity.json").write_text(json.dumps({"tiles": [
        {"platform": c["platform"], "rank": c["rank"], "composite": c["fit_score"]} for c in cards]}))
    assert not [r for r in pl._completeness("overview") if "tiles" in r or "CG-31" in r]


# ── the owed section goes to its OWNER, never to the assembler alone ──────

def test_section_owners_come_from_the_roster():
    from engine import brief
    own = brief.section_owners("overview")
    assert own["overview.opportunity"] == "overview-opportunity-producer"
    assert own["overview.scores"] == "overview-hero-producer"
    assert brief.section_owners("platform")["platform.platform_story"] == "platform-fit-producer"


def test_a_page_on_disk_that_owes_a_section_is_produced_not_restaged(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path)
    sd = pl._sections_dir()
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "overview.ceilings.json").write_text("{}")          # on disk, partly
    owed = pl._owed_sections("overview")
    assert "overview.opportunity" in owed and "overview.scores" in owed
    assert "overview.ceilings" not in owed
    src = inspect.getsource(P.Pipeline._ship_pages)
    assert "only_sections" in src and "_owed_sections" in src
    # a retry of an owing page runs the producer phases, not assemble alone
    assert "_platform_first([p for p in todo if p in owed])" in src


def test_fragments_dispatch_only_the_owners_of_owed_sections(tmp_path):
    from engine import brief
    run, wb, cells, ev = researched_run(tmp_path)
    out = brief.page_batch(wb, run=run, out_dir=tmp_path / "b", connector_run="r-1",
                           contract_file=tmp_path / "c.json", pages=["overview"],
                           phase="fragments", sections_dir=tmp_path / "s",
                           only_sections={"overview": ["overview.opportunity",
                                                       "overview.scores"]})
    names = " ".join(str(w) for w in out["briefs"])
    assert "overview-opportunity-producer" in names and "overview-hero-producer" in names
    assert "overview-people-producer" not in names and out["lanes"] == 2


def test_platform_with_fewer_cards_than_tiles_is_not_shipped(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path, reads=_FitReads())
    (run.qa_dir / P.Pipeline.SHORTLIST).write_text(json.dumps(
        {"tiles_wanted": 5, "ready": 22, "shortlist": []}))
    sd = pl._sections_dir(); sd.mkdir(parents=True, exist_ok=True)
    (sd / "platform.platform_story.json").write_text(json.dumps({"platforms": [{}, {}]}))
    det = pl._completeness_detail("platform")
    assert det and det[0][0] == "platform.platform_story" and "CG-COMPLETE" in det[0][1]


def test_platform_is_produced_before_the_overview():
    g = P.Pipeline._platform_first(["overview", "platform", "insights"])
    assert [x[1] for x in g] == [["platform"], ["overview", "insights"]]
    assert P.Pipeline._platform_first(["overview"])[0][1] == ["overview"]


def test_a_tile_off_its_card_is_held_locally_cg31(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path)
    (run.qa_dir / P.Pipeline.SHORTLIST).write_text(json.dumps(
        {"tiles_wanted": 1, "ready": 22, "shortlist": []}))
    sd = pl._sections_dir(); sd.mkdir(parents=True, exist_ok=True)
    (sd / "overview.opportunity.json").write_text(json.dumps(
        {"tiles": [{"platform": "MuleSoft Anypoint Platform", "rank": 1, "composite": 74.0}]}))
    (sd / "platform.platform_story.json").write_text(json.dumps(
        {"platforms": [{"platform": "MuleSoft Anypoint Platform", "rank": 2, "fit_score": 62.9}]}))
    det = [m for s_, m in pl._completeness_detail("overview") if s_ == "overview.opportunity"]
    assert det and "CG-31" in det[0] and "rank 1 vs card 2" in det[0] and "62.9" in det[0]
    (sd / "overview.opportunity.json").write_text(json.dumps(
        {"tiles": [{"platform": "MuleSoft Anypoint Platform", "rank": 2, "composite": 62.9}]}))
    assert not [m for s_, m in pl._completeness_detail("overview") if "CG-31" in m]


def test_a_shared_section_dispatches_every_owner():
    from engine import brief
    owners = brief.section_owner_sets("techstack")["techstack.techstack"]
    assert set(owners) == {"techstack-layers-producer", "techstack-register-producer"}
