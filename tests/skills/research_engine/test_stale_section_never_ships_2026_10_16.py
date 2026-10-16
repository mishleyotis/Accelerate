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


def test_a_register_page_whose_counts_differ_from_the_sheet_is_stale(tmp_path):
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
    items = [{"product": r["Product"], "status": r["Status"]} for r in reg]
    (sd / "techstack.techstack.json").write_text(json.dumps({"items": items}))
    assert P.Pipeline._section_contradicts_workbook(d, "techstack") is None
    (sd / "techstack.techstack.json").write_text(json.dumps({"items": items[:-1]}))
    why = P.Pipeline._section_contradicts_workbook(d, "techstack")
    assert why and f"{len(reg) - 1} row(s)" in why and f"Tech_Register's {len(reg)}" in why
    counts = {}
    for r in reg:
        counts[str(r["Status"]).upper()] = counts.get(str(r["Status"]).upper(), 0) + 1
    tiles = [{"kind": k, "count": v} for k, v in counts.items()] + [{"kind": "GAPS", "count": 3}]
    (sd / "insights.landscape.json").write_text(json.dumps({"tiles": tiles}))
    assert P.Pipeline._section_contradicts_workbook(d, "insights") is None
    n_conf = counts.get("CONFIRMED", 0)
    tiles = [{"kind": k, "count": (v + 2 if k == "CONFIRMED" else v)} for k, v in counts.items()]
    if "CONFIRMED" not in counts:
        tiles.append({"kind": "CONFIRMED", "count": 2})
    (sd / "insights.landscape.json").write_text(json.dumps({"tiles": tiles}))
    why = P.Pipeline._section_contradicts_workbook(d, "insights")
    assert why and f"CONFIRMED {n_conf + 2} vs {n_conf}" in why


def test_platform_gap_rows_left_cannot_estimate_beside_a_category_median_are_stale(tmp_path):
    run = new_run(tmp_path, n=4)
    d, sd = _driver(run, tmp_path)
    cell = d.wb.selected_subcaps()[0]
    cat = cell.split(".")[0]
    story = {"platforms": [{"platform": "X", "gaps": [
        {"subcap_id": cell, "current_score": 1.0, "peer_score": None,
         "peer_basis": "cannot_estimate", "peer_note": "identified, not scored"}]}]}
    (sd / "platform.platform_story.json").write_text(json.dumps(story))
    assert P.Pipeline._section_contradicts_workbook(d, "platform") is None
    prelim.peer_median(d.wb, category=cat, median=2.0, p25=1.5, p75=2.5, basis="inferred",
                       peer_scores="1.5,2.0,2.5", n=3,
                       source="abbreviated public-evidence scoring of the locked peers, test")
    why = P.Pipeline._section_contradicts_workbook(d, "platform")
    assert why and cell in why
    story["platforms"][0]["gaps"][0].update({"peer_score": 2.0, "peer_basis": "inferred"})
    (sd / "platform.platform_story.json").write_text(json.dumps(story))
    assert P.Pipeline._section_contradicts_workbook(d, "platform") is None
