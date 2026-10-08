"""One product is one Tech_Register row, and one TS_ID names one row.

WHY THESE EXIST (B1 Bank, 2026-10-08). The driver's PRELIM technographic
scanner and a relay scanner recorded into one workbook at the same time.
`techscan.record` read the row count outside the workbook lock and minted
`TS-{count+1}`, so eight ids (TS-004, -007, -009, -011, -017, -020, -024,
-027) each named two rows — Salesforce CRM and Banno shared one — and seven
products (Salesforce, SAS, SQL Server, SAP BusinessObjects, Google
Analytics, Fortinet, Entra ID) sat on the register twice, some with
disagreeing statuses. A peer-record against any shared id was ambiguous.
"""
from __future__ import annotations

import pytest

from engine import techscan
from engine.techscan import ScanRefused

from .fixtures import new_run

BASIS = "a fifteen character basis clause here"


def _wb(tmp_path):
    run = new_run(tmp_path, n=6, prelim=False)
    return run.open()


def _rec(wb, product, status="INFERRED", providers=("clay",), **kw):
    return techscan.record(wb, product=product, vendor=kw.pop("vendor", None),
                           layer=kw.pop("layer", "CUST"), status=status,
                           method="technographic_scan", basis=BASIS,
                           providers=list(providers), **kw)


def test_ids_are_allocated_past_the_highest_never_from_the_count(tmp_path):
    wb = _wb(tmp_path)
    a = _rec(wb, "Glia Digital Customer Service")
    b = _rec(wb, "Zendesk support desk")
    # a row removed from the middle must not let the next id collide with b
    wb.delete_rows_where("Tech_Register", {"TS_ID": a})
    c = _rec(wb, "HubSpot Marketing Hub")
    assert c != b
    assert techscan._ts_num(c) == techscan._ts_num(b) + 1


def test_a_stale_view_cannot_mint_a_duplicate_id(tmp_path):
    run = new_run(tmp_path, n=6, prelim=False)
    first, second = run.open(), run.open()      # two processes' views
    _rec(first, "Glia Digital Customer Service")
    _rec(second, "Zendesk support desk")        # second's view predates the first write
    ids = [r["TS_ID"] for r in run.open().rows("Tech_Register")]
    assert len(ids) == len(set(ids)) == 2


@pytest.mark.parametrize("again", ["SAP Business Objects", "sap businessobjects",
                                   "SAP BusinessObjects (BI suite)"])
def test_the_same_product_twice_is_refused_and_names_the_row(tmp_path, again):
    wb = _wb(tmp_path)
    ts = _rec(wb, "SAP BusinessObjects", layer="DATA")
    with pytest.raises(ScanRefused, match=f"already on the register as {ts}"):
        _rec(wb, again, status="CLAIMED", layer="DATA")


def test_dedupe_merges_a_product_onto_its_strongest_row_keeping_every_citation(tmp_path):
    wb = _wb(tmp_path)
    # write the B1 state directly: two rows, one product, two statuses
    techscan._append_register_row(
        wb, "TS-020", product="Google Analytics", vendor=None, layer="DATA",
        status="CLAIMED", basis=BASIS, method="technographic_scan",
        provs=["explorium"], subcaps=None, eids=["E-078"], source_urls=None,
        as_of=None, impact=None)
    techscan._append_register_row(
        wb, "TS-020", product="Google Analytics", vendor=None, layer="DATA",
        status="INFERRED", basis=BASIS, method="technographic_scan",
        provs=["clay"], subcaps=None, eids=["E-079"], source_urls=None,
        as_of=None, impact=None)
    out = techscan.dedupe(wb)
    rows = wb.rows("Tech_Register")
    assert len(rows) == 1 and rows[0]["Status"] == "INFERRED"
    assert set(rows[0]["Evidence_IDs"].split(", ")) == {"E-078", "E-079"}
    assert set(rows[0]["Providers"].split(", ")) == {"explorium", "clay"}
    assert out["duplicate_ids_left"] == []


def test_dedupe_renumbers_a_shared_id_past_the_highest_and_never_reuses_one(tmp_path):
    wb = _wb(tmp_path)
    for tid, prod in (("TS-007", "Salesforce CRM"), ("TS-007", "Banno Digital Platform"),
                      ("TS-009", "Q2 web platform")):
        techscan._append_register_row(
            wb, tid, product=prod, vendor=None, layer="CUST", status="INFERRED",
            basis=BASIS, method="technographic_scan", provs=["clay"], subcaps=None,
            eids=None, source_urls=None, as_of=None, impact=None)
    out = techscan.dedupe(wb)
    ids = {r["Product"]: r["TS_ID"] for r in wb.rows("Tech_Register")}
    assert ids["Salesforce CRM"] == "TS-007"
    assert ids["Banno Digital Platform"] == "TS-010"
    assert out["renumbered"] == [{"was": "TS-007", "now": "TS-010",
                                  "product": "Banno Digital Platform"}]


def test_dedupe_folds_a_named_alias_and_repoints_its_peer_rows(tmp_path):
    wb = _wb(tmp_path)
    for tid, prod in (("TS-021", "Microsoft Entra ID (Azure Active Directory)"),
                      ("TS-025", "Microsoft Azure Active Directory")):
        techscan._append_register_row(
            wb, tid, product=prod, vendor=None, layer="INFRA", status="INFERRED",
            basis=BASIS, method="technographic_scan", provs=["clay"], subcaps=None,
            eids=None, source_urls=None, as_of=None, impact=None)
    techscan.peer_record(wb, ts_id="TS-025", peer="Origin Bancorp", deployed=None,
                         basis="no reading for this peer in either scan")
    techscan.dedupe(wb, same=[("Microsoft Entra ID (Azure Active Directory)",
                               "Microsoft Azure Active Directory")])
    assert [r["TS_ID"] for r in wb.rows("Tech_Register")] == ["TS-021"]
    assert {r["TS_ID"] for r in wb.rows("Tech_Peer_Deployments")} == {"TS-021"}
