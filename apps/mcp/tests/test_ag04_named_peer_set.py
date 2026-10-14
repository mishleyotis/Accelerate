"""AG-04 keys off the IDENTIFIED peer set, not peer scores (SWBC gold audit
2026-10-04, RC-10; D-08).

The owner decision is that peers are not SCORED this engagement. SWBC still
has a locked peer set — Assurant, Fortegra, TruStage, in the research
workbook's Handoff_Lock and the report — and peer rows in the evidence store.
CG-51's "run holds peers" read only `peer_scores` (empty by decision) and
AG-04 skipped any tile with neither peer_coverage nor peer_deployments
(`if cov is None and not rows: continue`), so 6 of 8 bare platform tiles
were invisible to it and 37 of 40 peer x tile verdicts were absent rather
than `deployed: null`.

The set is defined once (`dma_mcp/peer_set.py`): peer_scores rows, OR the
workbook's locked_peer_set (run_manifest.payload.workbook_metadata), OR any
peer_deployments row on this payload or the run's live platform/techstack
submissions. Given a set, every platform tile carries exactly one row per
named peer — deployed true/false/null, each with a non-empty basis (null is
honest with its ladder; silence is not).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import peer_set as PS          # noqa: E402

PEERS = {"assurant": "Assurant", "fortegra": "Fortegra", "trustage": "TruStage"}


def row(peer, deployed=None, basis="Newsroom, case studies and postings searched "
                                    "2026-10-03; nothing establishes it"):
    return {"peer": peer, "deployed": deployed, "basis": basis, "as_of": None}


def tile(name, rows=None):
    t = {"platform": name, "rank": 1, "state": "READY", "fit_score": 50.0,
         "peer_synthesis": "x"}
    if rows is not None:
        t["peer_deployments"] = rows
    return t


def swbc_story():
    """SWBC platform_story 45a861d1, cut to the peer fields: 8 tiles, Slack
    with 1 row and Service Cloud with 2, six with none."""
    names = ["MuleSoft Anypoint Platform", "Salesforce Data Cloud",
             "Salesforce Financial Services Cloud", "Salesforce Shield",
             "Slack", "Salesforce Service Cloud", "Salesforce Agentforce",
             "Governance, risk and compliance platform"]
    tiles = [tile(n) for n in names]
    tiles[4]["peer_deployments"] = [row("Assurant", True)]
    tiles[5]["peer_deployments"] = [row("Assurant", True), row("Fortegra", False)]
    return {"platform_story": {"platforms": tiles}}


def test_swbc_platform_story_is_refused():
    out = PS.named_peer_findings("platform", swbc_story(), PEERS)
    assert out and {r["gate_id"] for r in out} == {"AG-04"}
    bare = [r for r in out if "MuleSoft" in r["message"]]
    assert bare and "TruStage" in bare[0]["message"]
    # every tile is short of at least one named peer
    assert len({r["path"] for r in out}) == 8


def test_one_row_per_named_peer_with_unknowns_as_null_passes():
    story = {"platform_story": {"platforms": [
        tile("MuleSoft Anypoint Platform",
             [row("Assurant"), row("Fortegra"), row("TruStage/CUNA Mutual")])]}}
    assert PS.named_peer_findings("platform", story, PEERS) == []


def test_a_null_row_without_its_ladder_is_refused():
    story = {"platform_story": {"platforms": [
        tile("MuleSoft Anypoint Platform",
             [row("Assurant"), row("Fortegra"), row("TruStage", basis=" ")])]}}
    out = PS.named_peer_findings("platform", story, PEERS)
    assert len(out) == 1 and "basis" in out[0]["message"]


def test_no_named_set_is_silent():
    assert PS.named_peer_findings("platform", swbc_story(), {}) == []


def test_other_pages_are_untouched():
    for page in ("overview", "heatmap", "techstack", "context", "insights"):
        assert PS.named_peer_findings(page, swbc_story(), PEERS) == []


def test_the_set_is_read_from_rows_when_nothing_is_recorded():
    """No DB: the rows on Slack and Service Cloud are themselves proof."""
    found = PS.run_peer_set(None, "run-1", swbc_story())
    assert set(found) == {"assurant", "fortegra"}


def test_the_locked_set_splits_the_workbook_spelling():
    assert PS.split_locked("TruStage/CUNA Mutual|Assurant|Fortegra") == [
        "TruStage/CUNA Mutual", "Assurant", "Fortegra"]
    assert PS.split_locked(["Assurant", " ", None]) == ["Assurant"]
    assert PS.split_locked(None) == []


def test_the_wrapper_runs_without_a_connection():
    out = PS.check_named_peer_set(None, "run-1", "platform", swbc_story())
    # rows-only set {Assurant, Fortegra}: six bare tiles plus Slack (no Fortegra)
    assert len(out) == 7


def test_pass2_runs_the_named_set_check():
    """Wired into the submit path, beside the coverage half of AG-04."""
    import inspect
    import dma_mcp.validation2 as V2
    src = inspect.getsource(V2.validate_pass2)
    assert "check_named_peer_set(conn, run_id, page, payload)" in src
