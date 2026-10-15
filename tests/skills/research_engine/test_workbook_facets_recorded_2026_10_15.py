"""Converted facets are recorded in the enrichment ledger before promote.

AAA WCNY (2026-10-15): firmographics and techstack are CONVERT sections —
formatted from the workbook, enriched by Clay and the web passes — so no page
producer called record_enrichment for them. They promoted at version 0, the
connector served them as `never_enriched`, and the client could not be
called done. The driver now records them from the workbook's own provenance.
"""
import inspect

from engine import pipeline as P
from engine import pipeline_stub as S
from fixtures import researched_run


def _pipe(run, tmp_path, reads=None):
    sh = S.StubShipper()
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=reads or S.StubReads(),
                     shipper=sh, push=False, folder_root=tmp_path / "o",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None)
    return P.Pipeline(run, opts), sh


def test_both_converted_facets_are_recorded_with_their_provenance(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl, sh = _pipe(run, tmp_path)
    out = pl._record_workbook_facets("RUN-B")
    assert [r["facet"] for r in out] == ["firmographics", "techstack"]
    assert all(r["recorded"] for r in out)
    sent = {e["facet"]: e for e in sh.enrichments}
    assert sent["firmographics"]["source"] and sent["techstack"]["source"]
    assert sent["techstack"]["run_id"] == "RUN-B"
    assert sum(1 for r in run.open().rows("Gate_Log") if r.get("Gate") == "ENRICHMENT_RECORDED") == 2


def test_a_facet_the_connector_holds_current_is_not_recorded_again(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)

    class Reads(S.StubReads):
        def client_state(self, display_id):
            return {"enrichment": {"facets": [{"facet": "firmographics", "state": "current"},
                                              {"facet": "techstack", "state": "never_enriched"}]}}
    pl, sh = _pipe(run, tmp_path, reads=Reads())
    out = pl._record_workbook_facets("RUN-B")
    assert [r["facet"] for r in out] == ["techstack"]


def test_promote_records_the_facets_first():
    src = inspect.getsource(P.Pipeline._stage_promote)
    assert src.index("_record_workbook_facets") < src.index("shipper.promote")
