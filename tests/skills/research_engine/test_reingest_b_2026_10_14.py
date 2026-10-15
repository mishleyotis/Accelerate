"""A repair made after INGEST_B reaches the connector only through a new ingest.

AAA WCNY (2026-10-14): the server reads evidence and its cell links at ingest,
so ET-07 kept refusing rows the workbook had linked after version B, and a
held firmographic whose evidence was registered after B could not resolve.
`--reingest-b WHY` supersedes B — once, recorded — and every page reships.
The prevention: PACKAGE links focus and timeline evidence before it builds.
"""
import inspect

import pytest

from engine import pipeline as P
from engine import pipeline_stub as S
from fixtures import researched_run


def _pipe(run, tmp_path, **kw):
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None, **kw)
    return P.Pipeline(run, opts)


def _as_if_b_ingested(pl):
    pl._set_md("connector_run_id_prev", "run-A")
    pl._set_md("connector_run_id", "run-B")
    pl.state.setdefault("pages", {})["heatmap"] = {
        "version": "B", "status": "pass", "versions": {"A": "pass", "B": "pass"},
        "shipped_mtime": {"A": 1.0, "B": 2.0}, "n_history": [["A", "pass"], ["B", "pass"]]}
    pl.state["package"] = {"folder": "/x", "verified": True}
    pl._save_state()


def test_reingest_supersedes_b_and_resets_every_page(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path)
    _as_if_b_ingested(pl)
    assert pl.done("INGEST_B")[0]
    out = pl.reingest_b("links added after version B must reach the connector's ET-07")
    assert out == {"reingest": True, "superseded": "run-B"}
    assert not pl.done("INGEST_B")[0]           # run-B no longer counts
    assert not pl.done("PACKAGE")[0]            # the package is rebuilt and pushed
    rec = pl.state["pages"]["heatmap"]
    assert "B" not in rec["versions"] and rec["versions"]["A"] == "pass"
    assert any(r.get("Gate") == "REINGEST_B" for r in run.open().rows("Gate_Log"))


def test_reingest_needs_a_reason_and_never_touches_a_promoted_run(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path)
    _as_if_b_ingested(pl)
    with pytest.raises(P.StageRefused, match="reason"):
        pl.reingest_b("short")
    pl._set_md("promoted_at", "2026-10-14T00:00:00Z")
    with pytest.raises(P.StageRefused, match="promoted"):
        pl.reingest_b("links added after version B must reach the connector's ET-07")


def test_reingest_is_applied_once_per_reason():
    src = inspect.getsource(P.Pipeline.run_all)
    assert "reingest_reasons" in src


def test_package_links_focus_and_timeline_evidence_first():
    src = inspect.getsource(P.Pipeline._stage_package)
    assert src.index("link_focus_evidence") < src.index("assemble.package")
