"""A section file on disk that contradicts the workbook never ships.

Verus, 2026-10-16: the lanes path shipped `heatmap.workbook_scores` written
the day before (every peer_median null, an empty_state saying the peers
"were not scored") seven hours after the peers were scored, and a techstack
register of 10 rows against the sheet's 13 — and the run promoted. "On
disk, shipping first" never asked whether the file still agreed with the
workbook it claimed to render.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from fixtures import new_run  # noqa: E501

from engine import pipeline as P
from engine import prelim, techscan


def _driver(run, tmp_path):
    sd = tmp_path / "08_sections"
    sd.mkdir(exist_ok=True)
    d = SimpleNamespace(wb=run.open(), state={"pages": {}, "connector": {}},
                        opts=SimpleNamespace(log=lambda *a, **k: None))
    d._sections_dir = lambda: sd
    d._section_contradicts_workbook = lambda page: P.Pipeline._section_contradicts_workbook(d, page)
    d._produced_for = lambda page, version: True
    d._stale_on_disk = lambda page, version: P.Pipeline._stale_on_disk(d, page, version)
    return d, sd


def test_a_peer_grid_with_null_medians_the_workbook_now_carries_is_stale(tmp_path):
    run = new_run(tmp_path, n=4)
    d, sd = _driver(run, tmp_path)
    cats = sorted({c.split(".")[0] for c in d.wb.selected_subcaps()})
    cat = cats[0]
    grid = {"pillars": {cat[:2]: {"score": 1.1, "peer_median": None}},
            "categories": {c: {"score": 1.0, "peer_median": None} for c in cats},
            "empty_state": {"reason": "peers identified, not scored"}}
    (sd / "heatmap.workbook_scores.json").write_text(json.dumps(grid))
    # no median anywhere: the grid is honest, nothing is stale
    assert P.Pipeline._section_contradicts_workbook(d, "heatmap") is None
    prelim.peer_median(d.wb, category=cat, median=2.0, p25=1.5, p75=2.5, basis="inferred",
                       peer_scores="1.5,2.0,2.5", n=3,
                       source="abbreviated public-evidence scoring of the locked peers, test")
    why = P.Pipeline._section_contradicts_workbook(d, "heatmap")
    assert why and cat in why and cat[:2] in why and "peer_median null" in why
    assert P.Pipeline._stale_on_disk(d, "heatmap", "B") == why
    # a restaged page of a re-open ships from disk by design
    d.state["reopen"] = {"restage": ["heatmap"]}
    assert P.Pipeline._stale_on_disk(d, "heatmap", "B") is None
    d.state["reopen"] = {}
    # the grid carrying the figure is current
    grid["categories"][cat]["peer_median"] = 2.0
    grid["pillars"][cat[:2]]["peer_median"] = 2.0
    (sd / "heatmap.workbook_scores.json").write_text(json.dumps(grid))
    assert P.Pipeline._section_contradicts_workbook(d, "heatmap") is None
    # files older than the ingest are stale whatever they say
    d._produced_for = lambda page, version: False
    assert "predate" in P.Pipeline._stale_on_disk(d, "heatmap", "B")


def test_a_register_page_that_disagrees_with_the_sheet_is_stale(tmp_path):
    run = new_run(tmp_path, n=4)
    d, sd = _driver(run, tmp_path)
    cells = d.wb.selected_subcaps()
    techscan.record(d.wb, product="Orion Advisor Tech", vendor="Orion", layer="CUST",
                    status="INFERRED", method="public_document",
                    basis="named on the client portal page with a login link",
                    providers=["exa"], subcaps=[cells[0]], evidence_ids=[],
                    source_urls=["https://acme.example/portal"])
    techscan.record(d.wb, product="Calendly scheduling", vendor="Calendly", layer="CUST",
                    status="INFERRED", method="technographic_scan",
                    basis="Let's Talk button links to a calendly.com booking page",
                    providers=["web"], subcaps=[cells[0]], evidence_ids=[],
                    source_urls=["https://acme.example/"])
    reg = [r for r in d.wb.rows("Tech_Register") if r.get("TS_ID")]
    items = [{"ts_id": r["TS_ID"], "product": r["Product"], "status": r["Status"]} for r in reg]
    (sd / "techstack.techstack.json").write_text(json.dumps({"items": items}))
    assert P.Pipeline._section_contradicts_workbook(d, "techstack") is None
    # a row the producer dropped WITH its reason naming the workbook id is not stale
    last = items[-1]
    (sd / "techstack.techstack.json").write_text(json.dumps(
        {"items": items[:-1],
         "dropped": [{"product": f"{last['product']} (workbook {last['ts_id']})",
                      "reason": "a category, not a named product"}]}))
    assert P.Pipeline._section_contradicts_workbook(d, "techstack") is None
    # silently missing: stale
    (sd / "techstack.techstack.json").write_text(json.dumps({"items": items[:-1]}))
    why = P.Pipeline._section_contradicts_workbook(d, "techstack")
    assert why and last["ts_id"] in why and "neither served nor named" in why
    # a status the sheet no longer carries (Calendly restruck): stale
    cal = next(r for r in reg if r["Product"] == "Calendly scheduling")
    techscan.restrike(d.wb, ts_id=cal["TS_ID"], status="CLAIMED", method="technographic_scan",
                      providers=["web"], evidence_ids=[],
                      basis="the vendor's own case study names the firm; no second source yet")
    (sd / "techstack.techstack.json").write_text(json.dumps({"items": items}))
    why = P.Pipeline._section_contradicts_workbook(d, "techstack")
    assert why and f"{cal['TS_ID']} served INFERRED vs sheet CLAIMED" in why
    # the landscape recounts the techstack FILE, not the sheet
    items2 = [dict(it, status=("CLAIMED" if it["ts_id"] == cal["TS_ID"] else it["status"]))
              for it in items]
    (sd / "techstack.techstack.json").write_text(json.dumps({"items": items2}))
    counts = {}
    for it in items2:
        counts[it["status"].upper()] = counts.get(it["status"].upper(), 0) + 1
    tiles = [{"kind": k, "count": v} for k, v in counts.items()] + [{"kind": "GAPS", "count": 0}]
    (sd / "insights.landscape.json").write_text(json.dumps({"tiles": tiles}))
    assert P.Pipeline._section_contradicts_workbook(d, "insights") is None
    tiles = [{"kind": k, "count": (v - 1 if k == "CLAIMED" else v)} for k, v in counts.items()]
    (sd / "insights.landscape.json").write_text(json.dumps({"tiles": tiles}))
    why = P.Pipeline._section_contradicts_workbook(d, "insights")
    assert why and f"CLAIMED {counts['CLAIMED'] - 1} vs {counts['CLAIMED']}" in why


def test_a_contradicting_section_is_not_submitted_and_becomes_the_repair_reason(tmp_path):
    """Produced in the first group while the register was produced after it,
    the landscape strip counted the previous register and shipped. At ship
    time the contradiction is the page's verdict, never a submission."""
    run = new_run(tmp_path, n=4)
    d, sd = _driver(run, tmp_path)
    cells = d.wb.selected_subcaps()
    techscan.record(d.wb, product="Orion Advisor Tech", vendor="Orion", layer="CUST",
                    status="INFERRED", method="public_document",
                    basis="named on the client portal page with a login link",
                    providers=["exa"], subcaps=[cells[0]], evidence_ids=[],
                    source_urls=["https://acme.example/portal"])
    reg = [r for r in d.wb.rows("Tech_Register") if r.get("TS_ID")]
    items = [{"ts_id": r["TS_ID"], "product": r["Product"], "status": r["Status"]} for r in reg]
    (sd / "techstack.techstack.json").write_text(json.dumps({"items": items}))
    (sd / "insights.landscape.json").write_text(json.dumps(
        {"tiles": [{"kind": "CONFIRMED", "count": 99}, {"kind": "INFERRED", "count": 0}]}))
    logged = []
    d.opts = SimpleNamespace(log=logged.append)
    verdicts = {}
    why = P.Pipeline._refuse_stale_ship(d, "insights", "B", verdicts)
    assert why and "tiles disagree" in why
    assert verdicts["insights"] == [why]
    rec = d.state["pages"]["insights"]
    assert rec["status"] == "local_precheck_fail" and rec["attempts_by_version"]["B"] == 1
    assert rec["n_history"][-1][:2] == ["B", "local_precheck_fail"]
    assert any("not submitted" in m for m in logged)
    # a page that agrees ships: no verdict written
    assert P.Pipeline._refuse_stale_ship(d, "techstack", "B", verdicts) is None
    assert "techstack" not in verdicts
