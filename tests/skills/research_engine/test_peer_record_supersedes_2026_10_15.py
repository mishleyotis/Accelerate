"""A peer row is ONE row per (product, peer) — the latest reading supersedes.

Verus, 2026-10-15: Kanawha's TS-002 was re-recorded once the portal hrefs
were registered; the stale row (Basis crediting the Orion link target to an
id that carries only the menu label) sat beside the new one. A reader of the
sheet — the platform page's peer card, the report writer — could pick up
either. `peer_record` now rewrites the existing row, and collapses the
duplicates an earlier append left.
"""
from __future__ import annotations

from fixtures import new_run  # noqa: E501

from engine import techscan


def _rows(wb, ts):
    return [r for r in wb.rows("Tech_Peer_Deployments")
            if str(r.get("TS_ID")) == ts and r.get("Peer")]


def test_re_recording_a_peer_rewrites_its_row_instead_of_appending(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cells = wb.selected_subcaps()
    techscan.record(wb, product="Orion Advisor Tech", vendor="Orion", layer="CUST",
                    status="INFERRED", method="public_document",
                    basis="named live on the client portal page with a login link",
                    providers=["exa"], subcaps=[cells[0]], evidence_ids=[],
                    source_urls=["https://acme.example/portal"])
    ts = next(r["TS_ID"] for r in wb.rows("Tech_Register")
              if r.get("Product") == "Orion Advisor Tech")
    techscan.peer_record(wb, ts_id=ts, peer="Kanawha Capital", deployed=True,
                         basis="menu label only, read from the cached text",
                         source_url="https://kancap.example/", as_of="2026-10-14")
    techscan.peer_record(wb, ts_id=ts, peer="Other Peer", deployed=False,
                         basis="client login links a Tamarac portal, not Orion",
                         source_url="https://other.example/")
    before = _rows(wb, ts)
    assert [r["Peer"] for r in before] == ["Kanawha Capital", "Other Peer"]

    st = techscan.peer_record(wb, ts_id=ts, peer="kanawha capital", deployed=True,
                              basis="two portals read from the markup: Orion on the "
                                    "menu [E-212], Satuit on /contact [E-213]",
                              source_url="https://kancap.example/contact",
                              as_of="2026-10-15")
    after = _rows(wb, ts)
    assert len(after) == 2, after
    kan = next(r for r in after if r["Peer"].lower() == "kanawha capital")
    assert "E-212" in kan["Basis"] and kan["As_Of"] == "2026-10-15"
    assert kan["Source_URL"].endswith("/contact")
    other = next(r for r in after if r["Peer"] == "Other Peer")
    assert other["Deployed"] == "no"
    assert st["peers_established"] == 2 and st["peers_deployed"] == 1


def test_duplicates_an_earlier_append_left_are_collapsed_to_one(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cells = wb.selected_subcaps()
    techscan.record(wb, product="Orion Advisor Tech", vendor="Orion", layer="CUST",
                    status="INFERRED", method="public_document",
                    basis="named live on the client portal page with a login link",
                    providers=["exa"], subcaps=[cells[0]], evidence_ids=[],
                    source_urls=["https://acme.example/portal"])
    ts = next(r["TS_ID"] for r in wb.rows("Tech_Register")
              if r.get("Product") == "Orion Advisor Tech")
    for basis in ("first reading, from the cached text only",
                  "second reading, appended beside the first"):
        wb.append("Tech_Peer_Deployments", {
            "TS_ID": ts, "Peer": "Kanawha Capital", "Deployed": "yes",
            "Basis": basis, "Source_URL": "https://kancap.example/",
            "As_Of": "2026-10-14"})
    assert len(_rows(wb, ts)) == 2
    techscan.peer_record(wb, ts_id=ts, peer="Kanawha Capital", deployed=True,
                         basis="settled: both portals read from the raw markup",
                         source_url="https://kancap.example/contact")
    rows = _rows(wb, ts)
    assert len(rows) == 1 and rows[0]["Basis"].startswith("settled")
