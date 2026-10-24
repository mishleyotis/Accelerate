"""'Identified, not scored' is not 'no peers' (SWBC gold audit 2026-10-04,
RC-10; D-08, D-17).

SWBC: the report locks three peers (Assurant, Fortegra, TruStage — peer
IDENTIFICATION only, no peer scoring). 6 of 8 platform tiles carried no
peer_deployments; Service Cloud had 2 rows and Slack 1, so 37 of 40
peer x tile verdicts were absent rather than deployed:null; peer_synthesis
was on Data Cloud alone; and O1's proxy_disclosure said "the comparison
organisations identified" without naming one. Every peer gate keyed off
peer SCORES, which were empty by owner decision, so none fired.

The run holds a named peer set when the bundle's peer table or locked set
names one, or any page carries a peer_deployments row. Given a set, every
platform tile carries one row per named peer (deployed true/false/null,
each with a basis — null is honest with its ladder) and a peer_synthesis,
and O1 names the cohort wherever it discloses that no peer median exists.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _consistency as cc  # noqa: E402

PEERS = ["Assurant", "Fortegra", "TruStage"]


def _row(peer, deployed=None, basis="searched the peer's newsroom and Salesforce case studies; nothing found"):
    return {"peer": peer, "deployed": deployed, "basis": basis, "as_of": None}


def _tile(name, rank, rows=None, synth=None):
    t = {"platform": name, "l3_area": f"[L3-X-{rank}] {name}", "rank": rank,
         "state": "READY", "fit_score": 40.0 - rank}
    if rows is not None:
        t["peer_deployments"] = rows
    if synth is not None:
        t["peer_synthesis"] = synth
    return t


def _swbc_tiles():
    return [
        _tile("MuleSoft Anypoint Platform", 1),
        _tile("Salesforce Data Cloud", 2, synth="Looked for at Assurant, Fortegra and TruStage."),
        _tile("Slack", 5, rows=[_row("Assurant", True)]),
        _tile("Salesforce Service Cloud", 6, rows=[_row("Assurant", True), _row("Fortegra", False)]),
    ]


def _o1(disclosure):
    return {"scores": {"composite": 2.01, "pillars": [
        {"pillar_id": f"P{i}", "score": 2.0, "peer_median": None,
         "peer_basis": "cannot_estimate", "proxy_disclosure": disclosure}
        for i in range(1, 5)]}}


BUNDLE = {"sub_vertical": "IB", "supplementary_sub_verticals": [],
          "locked_peer_set": PEERS, "peer_table": []}


def test_swbc_platform_tiles_without_a_row_per_named_peer_are_refused(tmp_path):
    pages = {"platform": {"platform_story": {"platforms": _swbc_tiles()}}}
    _, out = cc.run(cc.rundir(tmp_path, pages, bundle=BUNDLE))
    msgs = cc.blocks(out, "P1 peers")
    joined = "\n".join(msgs)
    assert "MuleSoft Anypoint Platform" in joined and "TruStage" in joined, out
    assert "peer_synthesis" in joined, out


def test_the_set_is_identified_from_rows_when_the_bundle_names_none(tmp_path):
    """No locked set in the bundle: the rows on Slack/Service Cloud still
    prove the run identified peers, so the bare tiles are refused."""
    pages = {"platform": {"platform_story": {"platforms": _swbc_tiles()}}}
    _, out = cc.run(cc.rundir(tmp_path, pages, bundle={"sub_vertical": "IB"}))
    assert any("MuleSoft" in m for m in cc.blocks(out, "P1 peers")), out


def test_one_row_per_peer_with_unknowns_as_null_passes(tmp_path):
    tiles = [_tile(n, r, rows=[_row(p) for p in PEERS], synth="Not established at any of the three.")
             for n, r in (("MuleSoft Anypoint Platform", 1), ("Salesforce Data Cloud", 2))]
    pages = {"platform": {"platform_story": {"platforms": tiles}},
             "overview": _o1("Assurant, Fortegra and TruStage were identified, not scored, "
                             "so no peer median exists for this pillar.")}
    _, out = cc.run(cc.rundir(tmp_path, pages, bundle=BUNDLE))
    assert not cc.blocks(out, "P1 peers"), out
    assert not cc.blocks(out, "O1 peers"), out


def test_a_null_row_without_its_ladder_is_refused(tmp_path):
    rows = [_row(p) for p in PEERS]
    rows[2]["basis"] = ""
    tiles = [_tile("MuleSoft Anypoint Platform", 1, rows=rows, synth="x")]
    pages = {"platform": {"platform_story": {"platforms": tiles}}}
    _, out = cc.run(cc.rundir(tmp_path, pages, bundle=BUNDLE))
    assert any("basis" in m for m in cc.blocks(out, "P1 peers")), out


def test_swbc_o1_disclosure_that_names_no_peer_is_refused(tmp_path):
    pages = {"overview": _o1("No peer comparison is shown for this pillar. The comparison "
                             "organisations identified for this assessment were not scored "
                             "against the same cells, so no like-for-like median exists.")}
    _, out = cc.run(cc.rundir(tmp_path, pages, bundle=BUNDLE))
    msgs = cc.blocks(out, "O1 peers")
    assert msgs and "Assurant" in msgs[0], out


def test_a_run_with_no_peer_set_is_left_alone(tmp_path):
    pages = {"platform": {"platform_story": {"platforms": [_tile("Slack", 1)]}},
             "overview": _o1("No peer set was identified this engagement.")}
    _, out = cc.run(cc.rundir(tmp_path, pages, bundle={"sub_vertical": "IB"}))
    assert not cc.blocks(out, "P1 peers") and not cc.blocks(out, "O1 peers"), out


BAXTER_PEERS = ["Alliant CU", "CEFCU", "Consumers CU", "GreenState CU",
                "Lake Michigan CU"]


def _baxter_bundle(locked=None):
    """Baxter c1351d25's peer table shape (read-only get_report_bundle):
    five credit unions plus three STATISTIC rows, one category shown."""
    b = {"sub_vertical": "CU",
         "peer_table": [{"peer_name": n, "category_id": "P1C1", "score": 3.0}
                        for n in BAXTER_PEERS + ["Median", "P25", "P75"]]}
    if locked is not None:
        b["locked_peer_set"] = locked
    return b


def test_statistic_rows_in_the_peer_table_are_not_peers(tmp_path):
    """Baxter's peer table carries Median, P25 and P75 beside its five credit
    unions; read verbatim, every tile was refused for having no row about
    three statistics. The connector's rule (dma_mcp/peer_set.py) is the
    checker's rule."""
    tiles = [_tile(n, r, rows=[_row(p) for p in BAXTER_PEERS], synth="Compared.")
             for n, r in (("MuleSoft Anypoint Platform", 1), ("Salesforce Data Cloud", 2))]
    pages = {"platform": {"platform_story": {"platforms": tiles}}}
    _, out = cc.run(cc.rundir(tmp_path, pages, bundle=_baxter_bundle()))
    assert not cc.blocks(out, "P1 peers"), out
    assert "Median" not in out and "P25" not in out, out


def test_the_bundle_locked_set_is_the_set_where_present(tmp_path):
    """A stated lock wins over the scored table: the peer table's extra name
    is not asked for when the workbook locked three."""
    tiles = [_tile("MuleSoft Anypoint Platform", 1,
                   rows=[_row(p) for p in PEERS], synth="Compared.")]
    bundle = {"sub_vertical": "IB", "locked_peer_set": PEERS,
              "peer_table": [{"peer_name": "Unlocked Insurer", "score": 2.0}]}
    pages = {"platform": {"platform_story": {"platforms": tiles}}}
    _, out = cc.run(cc.rundir(tmp_path, pages, bundle=bundle))
    assert not cc.blocks(out, "P1 peers"), out
