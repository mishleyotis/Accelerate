"""Pass 2 runs locally before a submission is spent (owner, 2026-10-07: "You
ought to be sure when submitting a page").

The replay imports the connector's own `validate_pass2` and answers its
database reads from read-only connector tools. These tests pin the three
properties that make it trustworthy: it reports the server's refusals, it
never guesses an answer it does not hold, and ship_page.py refuses to submit
on anything but a clean run of both passes.
"""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[4]
RUN = "00000000-0000-0000-0000-00000000aaaa"
ENTITY = "00000000-0000-0000-0000-00000000eeee"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _row(e_id, excerpt, links=("P1C1.1.1",), **kw):
    return {"e_id": e_id, "stored_id": e_id, "entity_id": ENTITY,
            "source_name": "NCUA 5300 call report", "source_url": "https://ncua.gov/x",
            "excerpt": excerpt, "claim_type": "FACT", "tier": "T1",
            "published_date": "2025-12-31", "recency_band": "CURRENT", "ers": 4.0,
            "origin": "package", "customer_attribution": None, "split_of": None,
            "connector": None, "linked_subcap_ids": list(links),
            "seen_in_runs": [RUN], **kw}


ROWS = {
    "E-1": _row("E-1", "Total assets at 31 December 2025 were 13,083,594,321 dollars for the "
                       "credit union, per the NCUA 5300 call report account 010."),
}


def fake_call(rows=ROWS, calls=None):
    def call(tool, args):
        if calls is not None:
            calls.append(tool)
        if tool == "get_report_bundle":
            return {"entity_id": ENTITY, "entity_name": "Example FCU", "request_id": "DMA-X",
                    "run_seq": 1, "sub_vertical": "CU", "supplementary_sub_verticals": [],
                    "scores": [{"subcap_id": "P1C1.1.1", "score": 2.0}],
                    "rollups": {}, "peer_table": [], "recommendations": []}
        if tool == "get_evidence":
            ids = args["e_ids"]
            return {"found": [rows[i] for i in ids if i in rows],
                    "not_found": [i for i in ids if i not in rows], "foreign": []}
        if tool in ("list_pending_runs", "list_withdrawn_runs"):
            return {"pending": [{"entity_name": "Some Other Bank Of Nowhere"}]}
        if tool == "get_staged_payload":
            return {"sections": []}
        return {"_error": f"unexpected {tool}"}
    return call


def _series(value, e_id="E-1"):
    return {"financial_series": {
        "series": [{"period": "FY2025", "value": value, "unit": "USD billions",
                    "as_of": "2025-12-31", "source_e_id": e_id,
                    "basis": "Total assets, period-end"}],
        "trend": None, "verified_sparse": True, "e_ids": [e_id], "internal_only": []}}


def test_a_quoted_figure_passes_and_a_computed_one_is_refused():
    p2 = _load("pass2_replay")
    ok = p2.replay(RUN, "overview", _series(13.083594321), repo=str(REPO), call=fake_call())
    assert ok["status"] == "pass", ok
    bad = p2.replay(RUN, "overview", _series(29.530380576), repo=str(REPO), call=fake_call())
    assert bad["status"] == "fail" and bad["by_gate"].get("CG-38") == 1, bad


def test_an_unresolvable_citation_is_refused_as_the_server_would():
    p2 = _load("pass2_replay")
    r = p2.replay(RUN, "overview", _series(13.083594321, e_id="E-404"), repo=str(REPO),
                  call=fake_call())
    assert r["status"] == "fail" and "ET-01" in r["by_gate"], r


def test_a_query_the_snapshot_cannot_answer_is_never_guessed(monkeypatch):
    p2 = _load("pass2_replay")
    cur = p2.Cursor(p2.Snapshot.__new__(p2.Snapshot))
    cur.s.unanswered, cur.s.bundle = [], {}
    with pytest.raises(p2.Unanswered):
        cur.execute("SELECT secret FROM somewhere_new WHERE run_id = %s", (RUN,))
    assert cur.s.unanswered, "an unanswered query is recorded, not swallowed"


def test_the_connector_being_unreachable_is_not_run_never_pass():
    p2 = _load("pass2_replay")
    r = p2.replay(RUN, "overview", _series(13.083594321), repo=str(REPO),
                  call=lambda tool, args: {"_error": "connector down"})
    assert r["status"] == "not_run", r


def test_supersession_follows_the_newest_family_member_with_links():
    p2 = _load("pass2_replay")
    rows = {"E-X-005": _row("E-X-005", "x" * 60, links=()),
            "E-X-005-R2": _row("E-X-005-R2", "y" * 60, links=("P1C1.1.1", "P1C1.1.2"))}
    snap = p2.Snapshot.__new__(p2.Snapshot)
    snap.call, snap.run_id = fake_call(rows), RUN
    snap.ev, snap.missing, snap.foreign = {}, set(), {}
    assert snap.successor("E-X-005") == [("E-X-005-R2", 2)]
    assert snap.successor("E-X-005-R2") == []


def _sections(tmp_path, value):
    d = tmp_path / "sections"
    d.mkdir()
    (d / "overview.financial_series.json").write_text(json.dumps(_series(value)["financial_series"]))
    return d


def test_ship_page_does_not_submit_when_pass2_could_not_run(tmp_path, monkeypatch, capsys):
    sp = _load("ship_page")
    sent = []
    monkeypatch.setattr(sp, "local_precheck",
                        lambda page, payload, repo=None: {"status": "pass", "reasons": [],
                                                          "gates_from": "test"})
    monkeypatch.setattr(sp, "mcp", lambda tool, args: sent.append(tool) or {"_error": "down"})
    rc = sp.main([RUN, "overview", "--sections", str(_sections(tmp_path, 13.083594321)),
                  "--repo", str(REPO), "--verdicts-out", str(tmp_path / "v.json")])
    out = capsys.readouterr().out
    assert rc == 1 and "submit_page_payload" not in sent, out
    assert "NOT SUBMITTED" in out
    v = json.loads((tmp_path / "v.json").read_text())
    assert v["overview"]["status"] == "local_precheck_not_run"


def test_ship_page_does_not_submit_a_page_pass2_refuses(tmp_path, monkeypatch, capsys):
    sp = _load("ship_page")
    sent = []
    monkeypatch.setattr(sp, "local_precheck",
                        lambda page, payload, repo=None: {"status": "pass", "reasons": [],
                                                          "gates_from": "test"})
    call = fake_call(calls=sent)
    monkeypatch.setattr(sp, "mcp", call)
    rc = sp.main([RUN, "overview", "--sections", str(_sections(tmp_path, 29.530380576)),
                  "--repo", str(REPO), "--verdicts-out", str(tmp_path / "v.json")])
    assert rc == 1 and "submit_page_payload" not in sent
    v = json.loads((tmp_path / "v.json").read_text())
    assert v["overview"]["status"] == "local_precheck_fail"
    assert v["overview"]["stage"] == "pass2" and v["overview"]["n_reasons"] >= 1
