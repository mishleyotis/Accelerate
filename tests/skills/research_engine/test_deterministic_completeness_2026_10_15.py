"""Deterministic first-promotion controls (owner, 2026-10-15: "validate all
the above are fixed such that they never occur in future runs ... deterministic,
not probabilistic controls").

Every control here is arithmetic over the workbook or the payload. Each test
feeds the failing input and asserts the refusal; none depends on an agent.
The AAA WCNY defects, by control:
  no peers served      -> peer score validation, PEER_GATE (SCORING + its
                          done predicate), page check, promote audit
  two platforms/tiles  -> fail-closed shortlist, tile set = top card ranks,
                          cards cover the shortlist top N, promote audit
"""
import json

import pytest

from engine import page_completeness as PC
from engine import pipeline as P
from engine import pipeline_stub as S
from engine import prelim as PR
from fixtures import researched_run


def _pipe(run, tmp_path, reads=None, shipper=None):
    return P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(S.default_handlers()),
                                     reads=reads or S.StubReads(),
                                     shipper=shipper or S.StubShipper(),
                                     push=False, folder_root=tmp_path / "o", ingest_poll_s=0,
                                     sleep=lambda s: None, log=lambda s: None))


SL = {"connector_run": "R", "ready": 7, "tiles_wanted": 5,
      "shortlist": [{"platform": f"P{i}"} for i in range(7)]}
CARDS = [{"platform": f"P{i}", "rank": i + 1, "fit_score": 70.0 - i} for i in range(6)]
GOOD = {
    "overview.scores": {"pillars": [{"pillar_id": "P1", "peer_median": 1.5}]},
    "heatmap.workbook_scores": {"categories": [{"peer_median": 1.4}]},
    "overview.opportunity": {"tiles": [{"platform": c["platform"], "rank": c["rank"],
                                        "composite": c["fit_score"]} for c in CARDS[:5]]},
    "platform.platform_story": {"platforms": CARDS},
}


def _check(page, secs, **kw):
    args = {"shortlist": SL, "connector_run": "R", "peer_categories": 16, **kw}
    return PC.check(page, lambda n: secs.get(n), **args)


# ── the pure function ─────────────────────────────────────────────────────

@pytest.mark.parametrize("page", ["overview", "heatmap", "platform"])
def test_a_complete_payload_passes(page):
    assert _check(page, GOOD) == []


def test_null_peer_anywhere_is_refused():
    bad = {**GOOD, "heatmap.workbook_scores": {"rows": [{"x": {"peer_median": None}}]}}
    out = _check("heatmap", bad)
    assert out and "rows[0].x.peer_median" in out[0][1]


@pytest.mark.parametrize("page", ["overview", "heatmap"])
def test_no_peer_table_is_refused_not_skipped(page):
    out = _check(page, GOOD, peer_categories=0)
    assert any("Peer_Benchmarks carries no median" in m for _, m in out)


@pytest.mark.parametrize("sl,why", [(None, "no full-catalogue platform shortlist"),
                                    ({"error": "HTTP 502"}, "shortlist failed"),
                                    ({**SL, "connector_run": "OTHER"}, "not R")])
@pytest.mark.parametrize("page", ["overview", "platform"])
def test_a_missing_failed_or_stale_shortlist_is_refused(page, sl, why):
    out = _check(page, GOOD, shortlist=sl)
    assert out and why in out[0][1]


def test_two_tiles_are_refused():
    bad = {**GOOD, "overview.opportunity": {"tiles": GOOD["overview.opportunity"]["tiles"][:2]}}
    assert any("2 tile(s)" in m for _, m in _check("overview", bad))


def test_tiles_must_be_the_top_card_ranks_in_order():
    tiles = list(GOOD["overview.opportunity"]["tiles"])
    swapped = [tiles[1], tiles[0]] + tiles[2:]
    assert any("card-rank order" in m for _, m in
               _check("overview", {**GOOD, "overview.opportunity": {"tiles": swapped}}))
    other = tiles[:4] + [{"platform": "P5", "rank": 6, "composite": 65.0}]
    assert any("card-rank order" in m for _, m in
               _check("overview", {**GOOD, "overview.opportunity": {"tiles": other}}))


def test_a_tile_figure_off_its_card_is_cg31():
    tiles = [dict(t) for t in GOOD["overview.opportunity"]["tiles"]]
    tiles[0]["composite"] = 74.0
    out = _check("overview", {**GOOD, "overview.opportunity": {"tiles": tiles}})
    assert any(m.startswith("CG-31") and "74.0" in m for _, m in out)


def test_cards_must_cover_the_shortlist_top_n():
    cards = [c for c in CARDS if c["platform"] != "P2"]
    out = _check("platform", {**GOOD, "platform.platform_story": {"platforms": cards}})
    assert any("missing P2" in m for _, m in out)


# ── peers: validated, and the stage fails closed ──────────────────────────

def _score_file(d, peer, cats, score=2.0):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{peer.lower().replace(' ', '-')}.json").write_text(json.dumps(
        {"peer": peer, "categories": {c: {"score": score} for c in cats}}))


def test_an_out_of_range_or_partial_peer_file_is_rejected(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    rows = [r for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    cats = [str(r["Category_ID"]).upper() for r in rows]
    assert PR.peer_score_file_problems({"peer": "X", "categories": {c: {"score": 7} for c in cats}},
                                       cats)
    assert PR.peer_score_file_problems({"peer": "X", "categories": {}}, cats)
    assert PR.peer_score_file_problems({"peer": "X", "categories": {c: {"score": 0.5} for c in cats}},
                                       cats)
    assert PR.peer_score_file_problems({"peer": "X", "categories": {c: {"score": 1.0} for c in cats}},
                                       cats) == []


def test_three_files_with_one_invalid_is_no_table(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    rows = [r for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    names = PR._grid_names(rows[0])
    if len(names) < 3:
        pytest.skip("fixture peer set under three")
    cats = [str(r["Category_ID"]).upper() for r in rows]
    for r in rows:
        wb.update_row("Peer_Benchmarks", "Category_ID", r["Category_ID"], {"Peer_Median": ""})
    d = tmp_path / "ps"
    _score_file(d, names[0], cats)
    _score_file(d, names[1], cats)
    _score_file(d, names[2], cats, score=9)
    with pytest.raises(PR.PrelimRefusal, match="rejected"):
        PR.peer_table_from_scores(wb, d)
    assert any(g.get("Gate") == "PEER_SCORE_FILE_REJECTED" for g in wb.rows("Gate_Log"))


def test_the_peer_gate_refuses_scoring_without_medians(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path)
    for r in pl.wb.rows("Peer_Benchmarks"):
        if r.get("Category_ID"):
            pl.wb.update_row("Peer_Benchmarks", "Category_ID", r["Category_ID"],
                             {"Peer_Median": ""})
    pl.wb.save()
    with pytest.raises(P.StageRefused, match="PEER_GATE"):
        pl._peer_gate()
    ok, why = pl.done("SCORING")
    assert ok is False
    assert any(g.get("Gate") == "PEER_GATE" for g in run.open().rows("Gate_Log"))


def test_a_partial_cohort_still_owes_the_table():
    class WB:
        def rows(self, tab):
            return [{"Category_ID": "P1C1", "Peer_Median": 2.0, "Peer_Names": "A, B, C"},
                    {"Category_ID": "P1C2", "Peer_Median": "", "Peer_Names": "A, B, C"}]
    assert PR.peers_owed_scores(WB())


# ── the shortlist fails closed ────────────────────────────────────────────

class _BrokenFit(S.StubReads):
    def capability_catalogue(self, run_id):
        return {"l3_platforms": [{"l3_id": "L3-1", "platform_name": "X"}]}

    def platform_fit(self, run_id, candidates):
        raise RuntimeError("connector HTTP 502")


def test_a_failed_fit_engine_writes_an_error_the_page_check_refuses(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path, reads=_BrokenFit())
    pl._set_md("connector_run_id", "R")
    assert pl._platform_shortlist("R") is None
    doc = json.loads((run.qa_dir / P.Pipeline.SHORTLIST).read_text())
    assert "502" in doc["error"]
    assert any("shortlist failed" in m for m in pl._completeness("overview"))


def test_tiles_wanted_is_one_constant():
    assert P.Pipeline.TILES_WANTED == PC.TILES_WANTED


# ── the promote audit reads what the connector STAGED ─────────────────────

class _StagedReads(S.StubReads):
    def __init__(self, staged, **kw):
        super().__init__(**kw)
        self.staged = staged

    def capability_catalogue(self, run_id):
        return {"l3_platforms": []}

    def platform_fit(self, run_id, candidates):
        return {"platforms": []}

    def staged_section(self, run_id, page, section):
        v = self.staged.get(f"{page}.{section}")
        if isinstance(v, Exception):
            raise v
        return v


def _promotable(tmp_path, staged):
    run, wb, cells, ev = researched_run(tmp_path)
    shipper = S.StubShipper()
    pl = _pipe(run, tmp_path, reads=_StagedReads(staged), shipper=shipper)
    pl._set_md("connector_run_id", "R")
    (run.qa_dir / P.Pipeline.SHORTLIST).write_text(json.dumps(SL))
    if not pl._peer_categories():
        rows = [r for r in pl.wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
        pl.wb.update_row("Peer_Benchmarks", "Category_ID", rows[0]["Category_ID"],
                         {"Peer_Median": 1.5})
    pl.wb.save()
    pl.state.setdefault("connector", {})
    return pl, shipper


def test_promote_runs_when_the_staged_payload_is_complete(tmp_path):
    pl, shipper = _promotable(tmp_path, GOOD)
    assert pl._promote_audit("R") == []


@pytest.mark.parametrize("break_it", [
    lambda s: {**s, "overview.scores": {"pillars": [{"peer_median": None}]}},
    lambda s: {**s, "overview.opportunity": {"tiles": s["overview.opportunity"]["tiles"][:2]}},
    lambda s: {**s, "platform.platform_story": {"platforms": CARDS[:2]}},
    lambda s: {**s, "heatmap.workbook_scores": RuntimeError("HTTP 502")},
])
def test_promote_is_refused_on_an_incomplete_staged_payload(tmp_path, break_it):
    pl, shipper = _promotable(tmp_path, break_it(GOOD))
    with pytest.raises(P.StageRefused, match="PROMOTE_AUDIT"):
        pl._stage_promote()
    assert shipper.promotions == []
    gates = [g for g in pl.wb.rows("Gate_Log") if g.get("Gate") == "PROMOTE_AUDIT"]
    assert gates and gates[-1].get("Verdict") == "FAIL"
