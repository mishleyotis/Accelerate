"""The technographic scan's sources are the app's sources, not whatever the
web happened to yield.

WHY THESE EXIST. The deployed app declares the techstack facet's sources as
exactly `{explorium, clay}` — `apps/api/dma_api/computed.py` says so and
`apps/api/tests/test_enrichment_status.py` asserts it. Until 2026-08-30 the
research-side scanner carried neither, said so in its own text, and produced
a register out of Exa and Tavily hits. Two systems, two different estates,
and no field in the workbook could even record which was which.

These pin the four properties that make the register reconcilable:

  1. every row names the PROVIDER(S) that saw it, and `web` is one of them
  2. a row whose only providers are brokers may not wear CONFIRMED — two
     brokers reselling one crawl is one observation, not corroboration
  3. an Explorium export is importable, and its unmappable rows are
     REPORTED rather than guessed into a layer
  4. the rendered scan states RAN or NOT_RUN per contracted source, so a
     provider that never ran is a stated finding and not a smaller number
"""
from __future__ import annotations

import json

import pytest
from openpyxl import Workbook

from engine import contract as C
from engine import techscan
from engine.techscan import ScanRefused

from .fixtures import bank_evidence, new_run


def _run(tmp_path):
    """PRELIM off, because closing it seeds a Tech_Register row of its own
    and these tests count the rows they write themselves."""
    run = new_run(tmp_path, n=6, prelim=False)
    wb = run.open()
    return run, wb, wb.selected_subcaps()


# ── 1. the provider is not optional ──────────────────────────────────────

def test_a_row_with_no_provider_is_refused(tmp_path):
    run, wb, cells = _run(tmp_path)
    with pytest.raises(ScanRefused, match="PROVIDER"):
        techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                        status="CLAIMED", method="technographic_scan",
                        basis="a fifteen character basis clause here")


def test_an_unknown_provider_is_refused(tmp_path):
    run, wb, cells = _run(tmp_path)
    with pytest.raises(ScanRefused, match="not in"):
        techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                        status="CLAIMED", method="technographic_scan",
                        providers=["builtwith"],
                        basis="a fifteen character basis clause here")


def test_web_is_a_provider_not_an_exemption(tmp_path):
    """The failure mode this closes: 'a search found it' recorded as though
    provenance did not apply to it."""
    run, wb, cells = _run(tmp_path)
    ts = techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                         status="CLAIMED", method="technographic_scan",
                         providers=["web"],
                         basis="the client's login page is served by Alkami")
    row = [r for r in wb.rows("Tech_Register") if r["TS_ID"] == ts][0]
    assert row["Providers"] == "web"


def test_providers_are_deduplicated_in_order(tmp_path):
    run, wb, cells = _run(tmp_path)
    ts = techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                         status="CLAIMED", method="technographic_scan",
                         providers=["clay", "web", "clay", "CLAY"],
                         basis="the client's login page is served by Alkami")
    row = [r for r in wb.rows("Tech_Register") if r["TS_ID"] == ts][0]
    assert row["Providers"] == "clay, web"


# ── 2. a broker row is a claim, however many brokers agree ───────────────

def test_broker_only_confirmed_is_refused(tmp_path):
    run, wb, cells = _run(tmp_path)
    eids = bank_evidence(wb, cells[0])
    with pytest.raises(ScanRefused, match="brokers only"):
        techscan.record(wb, product="Snowflake", vendor="Snowflake",
                        layer="DATA", status="CONFIRMED",
                        method="technographic_scan",
                        providers=["clay", "explorium"], evidence_ids=eids,
                        basis="both broker rows name Snowflake for this "
                              "domain")


def test_a_non_broker_provider_unlocks_confirmed(tmp_path):
    """The repair the refusal asks for: go and find the source that saw it
    independently, then record BOTH providers."""
    run, wb, cells = _run(tmp_path)
    eids = bank_evidence(wb, cells[0])
    ts = techscan.record(wb, product="Snowflake", vendor="Snowflake",
                         layer="DATA", status="CONFIRMED",
                         method="vendor_announcement",
                         providers=["clay", "exa"], evidence_ids=eids,
                         basis="Snowflake's own customer page names the "
                               "client, and Clay carries the row")
    row = [r for r in wb.rows("Tech_Register") if r["TS_ID"] == ts][0]
    assert row["Status"] == "CONFIRMED" and row["Evidence_Level"] == "L1"


def test_a_broker_row_may_be_claimed_and_inferred(tmp_path):
    run, wb, cells = _run(tmp_path)
    for status in ("CLAIMED", "INFERRED"):
        techscan.record(wb, product=f"Product {status}", vendor="V",
                        layer="OPS", status=status,
                        method="technographic_scan", providers=["explorium"],
                        basis="the Explorium export carries this row")
    got = {r["Status"] for r in wb.rows("Tech_Register")}
    assert got == {"CLAIMED", "INFERRED"}


# ── 3. the Explorium export has one door, and it does not guess ──────────

def _export(tmp_path, rows, *, sheet="Confirmed_Tech_Stack", preamble=False):
    """Build an export in the shape the app's own parser has met in the
    field — a preamble above the header is the Nicola variant."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    if preamble:
        ws.append(["Source: Explorium Live Technographics"])
        ws.append([])
    ws.append(["Category", "Vendor / Product", "Confidence"])
    for r in rows:
        ws.append(list(r))
    path = tmp_path / "Acme_Explorium_Tech_Stack.xlsx"
    wb.save(path)
    return path


def test_an_export_imports_as_claimed_with_the_explorium_provider(tmp_path):
    run, wb, cells = _run(tmp_path)
    path = _export(tmp_path, [
        ("Core Banking", "Fiserv DNA", 0.9),
        ("Data Warehouse", "Snowflake", 0.8),
        ("Cloud Hosting", "Amazon AWS", 0.7),
    ])
    out = techscan.import_explorium(wb, path)
    assert len(out["recorded"]) == 3, out
    rows = wb.rows("Tech_Register")
    assert {r["Status"] for r in rows} == {"CLAIMED"}
    assert {r["Providers"] for r in rows} == {"explorium"}
    assert {r["Layer"] for r in rows} == {"OPS", "DATA", "INFRA"}


def test_the_preamble_variant_still_finds_its_header(tmp_path):
    run, wb, cells = _run(tmp_path)
    path = _export(tmp_path, [("Core Banking", "Fiserv DNA", 0.9)],
                   preamble=True)
    out = techscan.import_explorium(wb, path)
    assert len(out["recorded"]) == 1, out


def test_an_unmappable_row_is_reported_not_guessed(tmp_path):
    """A mis-layered row moves a gap from one pillar to another, so the
    importer hands it back instead of picking."""
    run, wb, cells = _run(tmp_path)
    path = _export(tmp_path, [
        ("Core Banking", "Fiserv DNA", 0.9),
        ("Miscellaneous", "Some Unclassifiable Thing", 0.4),
    ])
    out = techscan.import_explorium(wb, path)
    assert len(out["recorded"]) == 1
    assert [r["product"] for r in out["unmapped_layer"]] == [
        "Some Unclassifiable Thing"]
    assert len(wb.rows("Tech_Register")) == 1, (
        "an unmappable row must not reach the register with a guessed layer")


def test_an_export_that_parses_to_nothing_is_refused(tmp_path):
    """An unreadable file is a file problem, never a clean estate."""
    run, wb, cells = _run(tmp_path)
    path = _export(tmp_path, [])
    with pytest.raises(ScanRefused, match="not a clean estate"):
        techscan.import_explorium(wb, path)


def test_layer_for_declines_rather_than_reaching(tmp_path):
    assert techscan.layer_for("Core Banking", "Fiserv DNA") == "OPS"
    assert techscan.layer_for("CRM", "Salesforce") == "CUST"
    assert techscan.layer_for(None, "Snowflake data warehouse") == "DATA"
    assert techscan.layer_for("Identity", "Okta SSO") == "INFRA"
    assert techscan.layer_for("Miscellaneous", "Widget") is None


# ── 4. an unreached source is a stated NOT_RUN ───────────────────────────

def test_the_state_counts_providers_and_names_the_ones_that_never_ran(
        tmp_path):
    run, wb, cells = _run(tmp_path)
    techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                    status="CLAIMED", method="technographic_scan",
                    providers=["clay"],
                    basis="Clay's Tech Stack data point carries this row")
    techscan.record(wb, product="Snowflake", vendor="Snowflake", layer="DATA",
                    status="INFERRED", method="job_posting",
                    providers=["indeed"],
                    basis="two 2026 postings name Snowflake administration")
    st = techscan.scan_state(wb)
    assert st["by_provider"]["clay"] == 1
    assert st["by_provider"]["indeed"] == 1
    assert st["broker_rows"] == 1 and st["broker_share"] == 0.5
    assert st["providers_never_run"] == ["explorium"]


def test_the_rendered_scan_states_ran_or_not_run_per_contracted_source(
        tmp_path):
    run, wb, cells = _run(tmp_path)
    techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                    status="CLAIMED", method="technographic_scan",
                    providers=["clay"],
                    basis="Clay's Tech Stack data point carries this row")
    techscan.render(wb, run.deliverables)
    doc = json.loads((run.deliverables / techscan.JSON_NAME).read_text())
    assert doc["sources"]["clay"]["status"] == "RAN"
    assert doc["sources"]["explorium"]["status"] == "NOT_RUN"
    assert "no key in Secret Manager" in doc["sources"]["explorium"]["reason"]
    assert doc["detections"][0]["providers"] == ["clay"]
    assert set(doc["vocabulary"]["brokers"]) == set(C.TECH_BROKERS)


def test_the_app_side_parser_still_reads_the_machine_copy(tmp_path):
    """The providers column is additive: the app's parser must not care."""
    import sys
    sys.path.insert(0, "/home/user/Accelerate/apps/worker")
    from dma_worker.workbook_parser import parse_technographic_scan

    run, wb, cells = _run(tmp_path)
    techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                    status="CLAIMED", method="technographic_scan",
                    providers=["clay"],
                    basis="Clay's Tech Stack data point carries this row")
    techscan.render(wb, run.deliverables)
    obs: list = []
    n = parse_technographic_scan(
        str(run.deliverables / techscan.JSON_NAME), obs)
    assert n >= 1, obs


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
