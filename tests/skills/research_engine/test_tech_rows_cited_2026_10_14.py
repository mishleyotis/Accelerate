"""A technology register row cites what saw it — before PRELIM closes.

AAA Western and Central New York (2026-10-14): ten Tech_Register rows went in
with a Source_URL and no Evidence_IDs. PRELIM's tech_baseline closed on row
count alone, and the report validator found the gap in REPORTS, where the
evidence register is frozen and nothing could be registered to repair it.
"""
from engine import ledger as L
from engine import prelim, techscan

from fixtures import new_run

URL = "https://careers.example-club.com/jobs/data-engineer"
SPAN = ("The Data Engineer will build pipelines in Databricks on Azure and publish "
        "governed datasets to Power BI for the club's insurance and travel teams.")


def _setup(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False, folder=False)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.append_evidence(wb, source_name="Example Club careers — Data Engineer",
                      source_url=URL, tier="T5", excerpt=SPAN,
                      subcaps=[cell], origin="public")
    eid = next(e for e, r in run.open().evidence_index().items()
               if r.get("Source_URL") == URL)
    return run, eid


def _row(run, ts):
    return next(r for r in run.open().rows("Tech_Register") if r["TS_ID"] == ts)


def test_a_url_only_row_links_the_registered_span_that_names_it(tmp_path):
    run, eid = _setup(tmp_path)
    ts = techscan.record(run.open(), product="Databricks Lakehouse", vendor="Databricks",
                         layer="DATA", status="INFERRED", method="job_posting",
                         basis="a data engineer posting names Databricks on Azure",
                         providers=["web"], source_urls=[URL + "/"])
    assert _row(run, ts)["Evidence_IDs"] == eid


def test_a_span_on_the_same_page_about_something_else_is_not_linked(tmp_path):
    run, _ = _setup(tmp_path)
    ts = techscan.record(run.open(), product="Cloudflare CDN", vendor="Cloudflare",
                         layer="INFRA", status="INFERRED", method="job_posting",
                         basis="response headers name Cloudflare on the careers host",
                         providers=["web"], source_urls=[URL])
    assert not _row(run, ts)["Evidence_IDs"]


def test_prelim_tech_baseline_stays_open_while_a_row_is_uncited(tmp_path, monkeypatch):
    from engine import page_preflight as PP
    monkeypatch.setattr(PP, "machine_scan", lambda wb: {"state": "RUN", "detail": ""})
    run, _ = _setup(tmp_path)
    for layer, prod in (("OPS", "UKG Pro Recruiting"), ("CUST", "Drupal CMS"),
                        ("DATA", "Tableau Desktop"), ("INFRA", "Akamai Edge")):
        techscan.record(run.open(), product=prod, vendor=None, layer=layer,
                        status="INFERRED", method="job_posting",
                        basis=f"a posting names {prod} in the stack",
                        providers=["web"], source_urls=[URL])
    sec = next(x for x in prelim.state(run.open())["sections"]
               if x["section"] == "tech_baseline")
    assert sec["status"] == "OPEN", sec
    assert "cite no registered evidence" in sec["detail"]
    assert "restrike" in sec["fix"]


def test_the_validator_packet_names_the_upstream_items_to_recheck(tmp_path, monkeypatch):
    import json
    from engine import brief, narrative as N
    run = new_run(tmp_path, n=3, prelim=False, folder=False)
    ups = [{"report": "client_research", "section": "5", "kind": "evidence",
            "detail": "Tech_Register TS-003 has no Evidence_IDs; register it and link it"}]
    real = N.state
    monkeypatch.setattr(N, "state", lambda wb, *a, **k: {**real(wb, *a, **k), "upstream": ups})
    b = brief.report_batch(run.open(), run=run, out_dir=tmp_path / "b", validator=True)
    lanes = b.get("lanes") or json.loads((tmp_path / "b" / "batch_reports.json").read_text())["lanes"]
    text = json.dumps(lanes) + "".join(
        p.read_text() for p in (tmp_path / "b").rglob("*") if p.is_file())
    assert "upstream_to_recheck" in text and "TS-003" in text


def test_the_validator_packet_carries_owner_decisions(tmp_path):
    import json
    from engine import brief, ledger as L
    run = new_run(tmp_path, n=3, prelim=False, folder=False)
    L.append_gate(run.open(), gate="OWNER_DECISION_RUBRIC", scope="Maturity_Rubric",
                  verdict="PASS", blocking=False, detail="GSY-11 stands: five rubric levels")
    brief.report_batch(run.open(), run=run, out_dir=tmp_path / "b", validator=True)
    text = "".join(p.read_text() for p in (tmp_path / "b").rglob("*") if p.is_file())
    assert "OWNER_DECISION_RUBRIC" in text and "GSY-11 stands" in text


def test_focus_evidence_is_linked_before_pages_never_at_the_prelim_write(tmp_path):
    """AAA WCNY: FA-01/02/03 cited E-002/E-013/E-008, which named no cell, and
    PAGES_A refused three pages on ET-07. The link is written before the page
    lanes; the PRELIM write leaves research cells untouched."""
    from engine import profile
    from engine.workbook import _split_ids
    run, eid = _setup(tmp_path)
    wb = run.open()
    cells = [c for c in wb.selected_subcaps()[1:3]]
    profile.focus(wb, fa_id="FA-01", title="Build a modern data platform",
                  quote="We are building pipelines in Databricks on Azure so every "
                        "team works from one governed set of member data.",
                  document="Club newsroom release", page="1", cells=cells,
                  evidence=eid, currency="AGING")
    wb = run.open()
    for c in cells:   # the PRELIM write did not touch the research cells
        assert eid not in [i.split(":")[0] for i in _split_ids(wb.scoring_row(c)["Evidence_IDs"])]
    out = profile.link_focus_evidence(wb)
    assert out and out[0]["e_id"] == eid
    wb = run.open()
    for c in cells:
        assert eid in [i.split(":")[0] for i in _split_ids(wb.scoring_row(c)["Evidence_IDs"])]


def test_the_driver_links_focus_evidence_in_page_prep():
    import inspect
    from engine import pipeline as P
    assert "link_focus_evidence" in inspect.getsource(P.Pipeline._pages_prepare)
