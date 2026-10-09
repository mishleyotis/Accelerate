"""The page gates read against the workbook, before any page agent runs —
and a stage that needs a lost connector says so instead of failing late.

Owner, 2026-10-07 (First Tech): "Connectors keep on getting lost with no self
heal. Also, isn't such enrichment supposed to happen at prelim and be
recorded in the scoring workbook to be reused for later stages?" PRELIM
closed on five web-found rows; the connector refused the techstack page three
times at PAGES_A (ET-12, CG-40, CG-50) in a session holding no Clay or Vibe.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from engine import ledger as L, page_preflight as PP, techscan, watchdog
from fixtures import new_run, scored_run

ROOT = Path(__file__).resolve().parents[3]


def _first_tech_shape(wb):
    """Five web rows, one citing an excerpt that never names its product."""
    named = L.append_evidence(
        wb, source_name="American Banker, Credit Union Journal",
        source_url="https://example.test/ab", tier="T2",
        excerpt=("Although Fiserv DNA, the credit union's core banking platform, "
                 "isn't cloud-enabled yet, it makes extensive use of the cloud."),
        subcaps=[], published="2022-03-22")
    other = L.append_evidence(
        wb, source_name="Vendor press release",
        source_url="https://example.test/pr", tier="T2",
        excerpt=("The credit union consolidated 7.2 million member records into "
                 "2.4 million profiles, a 62 percent reduction in duplicates."),
        subcaps=[], published="2024-05-01")
    techscan.record(wb, product="Fiserv DNA", vendor="Fiserv", layer="OPS",
                    status="INFERRED", method="public_document", basis="named as the core banking platform in 2022 trade press",
                    providers=["web"], subcaps=[], evidence_ids=[named],
                    source_urls=["https://example.test/ab"], as_of="2022-03-22")
    techscan.record(wb, product="Reltio Connected Data Platform", vendor="Reltio",
                    layer="DATA", status="CONFIRMED", method="vendor_announcement",
                    basis="named in a vendor release on member-record consolidation", providers=["web"], subcaps=[],
                    evidence_ids=[other], source_urls=["https://example.test/pr"],
                    as_of="2024-05-01")
    return named, other


def test_the_first_tech_register_is_refused_before_any_page_agent(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    _first_tech_shape(wb)
    gates = {b["gate"]: b for b in PP.preflight(wb)}
    assert set(gates) == {"ET-12", "CG-40", "CG-50"}
    assert gates["ET-12"]["needs_connector"] and gates["CG-40"]["needs_connector"]
    assert not gates["CG-50"]["needs_connector"]
    assert "Reltio" in gates["CG-50"]["detail"]


def test_a_declared_not_run_answers_et12_and_excuses_the_depth_floor(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    _first_tech_shape(wb)
    for tool in ("clay", "vibe"):
        PP.declare_not_run(wb, tool=tool, reason=(
            f"{tool} has no technographic profile for this domain, checked "
            f"2026-10-05; stated on the page as NOT_RUN"))
    assert PP.machine_scan(wb)["state"] == "DECLARED"
    assert [b["gate"] for b in PP.preflight(wb)] == ["CG-50"]


def test_a_not_run_needs_its_reason(tmp_path):
    import pytest
    run = new_run(tmp_path, prelim=False)
    with pytest.raises(ValueError):
        PP.declare_not_run(run.open(), tool="clay", reason="no")


def test_the_engine_and_the_connector_hold_the_same_cg50_tokens():
    src = (ROOT / "apps/mcp/dma_mcp/validation2.py").read_text()
    block = re.search(r'_GENERIC_PRODUCT_TOKENS = frozenset\("""(.*?)"""', src, re.S)
    assert block, "CG-50's stoplist moved in the connector"
    assert frozenset(block.group(1).split()) == PP._GENERIC_PRODUCT_TOKENS
    assert re.search(r"^_MIN_TOKEN = (\d+)", src, re.M).group(1) == str(PP._MIN_TOKEN)
    floor = re.search(r'\("techstack", "techstack"\): \(\s*(\d+),', src)
    assert floor and int(floor.group(1)) == PP.TECHSTACK_FLOOR


def test_cg50_reads_product_phrases_only_as_the_connector_does(tmp_path):
    """B1 Bank, 2026-10-08: both scans say only 'Q2'. CG-20 refuses vendor ==
    product, and the mirror read the VENDOR's phrase ('q2 software') where the
    connector reads the product's alone — so the preflight refused a row the
    connector passed, and halted PAGES_A."""
    src = (ROOT / "apps/mcp/dma_mcp/validation2.py").read_text()
    assert "phrases = _name_phrases(product)\n" in src, \
        "the connector's CG-50 phrase rule moved — re-mirror it here"
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    scan = L.append_evidence(
        wb, source_name="Clay company Tech Stack technographic scan",
        source_url="https://example.test/scan", tier="T1",
        excerpt=("Facebook, Instagram, LinkedIn, LinkedIn Ads, LinkedIn Insights, "
                 "HSTS, Q2, Slack, CrUX Dataset, CrUX Top 1m, Glia"),
        subcaps=[], published="2026-10-08")
    for product, vendor in (("Q2", "Q2 Software"),
                            ("Q2 Digital Banking Platform", "Q2 Holdings")):
        techscan.record(wb, product=product, vendor=vendor, layer="CUST",
                        status="INFERRED", method="public_document",
                        basis="listed by the company technographic scan",
                        providers=["clay"], subcaps=[], evidence_ids=[scan],
                        as_of="2026-10-08")
    flagged = [u["product"] for u in PP.unnamed_products(wb)]
    assert flagged == ["Q2 Digital Banking Platform"]


def test_the_driver_stops_needs_connector_at_pages_and_the_watchdog_says_why(tmp_path):
    from engine import pipeline as P, pipeline_stub as S, preflight
    from fixtures import preflight_doc
    run = new_run(tmp_path, n=6, prelim=False)
    preflight.record(run, preflight_doc())
    opts = P.Options(dispatcher=S.StubDispatcher.fixture_backed(), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None,
                     until="REPORTS")
    assert P.Pipeline(run, opts).run_all()["outcome"] == "STOPPED_AT_UNTIL"
    # the register loses its scan reading: what a PRELIM run in a session
    # without the connector would have banked
    wb = run.open()
    idx = wb.evidence_index()
    for r in wb.rows("Tech_Register"):
        keep = [e.strip() for e in str(r.get("Evidence_IDs") or "").split(",")
                if e.strip() and "Clay" not in str((idx.get(e.strip()) or {}).get("Source_Name"))]
        wb.update_row("Tech_Register", "TS_ID", r["TS_ID"], {"Evidence_IDs": ", ".join(keep)})
    assert PP.machine_scan(run.open())["state"] == "MISSING"
    opts.until = None
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "NEEDS_CONNECTOR" and out["stage"] == "PAGES_A", out
    assert "ET-12" in out["reason"] and out["connectors"] == ["clay", "vibe"]
    assert opts.shipper.ships == []
    assert not [c for c in opts.dispatcher.calls if c["stage"] == "PAGES_A"]
    gate = [g for g in run.open().rows("Gate_Log") if g.get("Gate") == "PAGE_PREFLIGHT"]
    assert gate and gate[-1]["Verdict"] == "FAIL"
    row = watchdog.inspect(run)
    assert row["state"] == "NEEDS_CONNECTOR_SESSION", row
    assert row["state"] not in watchdog.AGENT_ADVANCEABLE
    assert row["resume"]["needs"] == "connector_session"
    assert watchdog.revive(row, dry_run=True)["outcome"] == "NOT_RUN"


def test_a_prelim_signed_off_before_the_rule_is_not_reopened(tmp_path):
    from engine import prelim
    run, wb, cells, ev = scored_run(tmp_path)
    for r in wb.rows("Tech_Register"):
        wb.update_row("Tech_Register", "TS_ID", r["TS_ID"], {"Evidence_IDs": ""})
    st = prelim.state(run.open())
    assert st["prelim_status"] == "COMPLETE" and "tech_baseline" not in st["open"]
