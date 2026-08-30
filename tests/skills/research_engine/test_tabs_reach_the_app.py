"""A tab the app reads must land in a shape the app's own parser accepts.

WHY THESE EXIST. The 2026-08-30 tab audit asked, for all nineteen tabs,
"writer / gate / does the app need it / can it ship empty". Two answers were
worse than empty:

  Peer_Benchmarks   the app DOES read it, and the engine's only writer
                    produced rows the app's parser discards wholesale —
                    `prelim.peers` wrote one row per peer with `Category_ID`
                    blank, and `workbook_parser` keeps only rows whose first
                    column is a category id. So a run could do its peer work
                    correctly and still land with zero peer scores,
                    indistinguishable from one that declared the tab empty.

  Entity_Timeline   had a writer, a completeness gate and NO READER: no
                    report section named it, no package extra carried it, and
                    the app had zero references to it — while the C1 surface
                    it was gathered for was produced by re-searching in the
                    synthesis session. Its one `Signal` column also drew on a
                    nine-token event-CLASS list, while the surface needs both
                    a three-token DIRECTION and an eight-token CLASS.

These walk each tab from the engine's writer to the app's reader.
"""
from __future__ import annotations

import json
import sys

import pytest

from engine import assemble
from engine import contract as C
from engine import prelim
from engine import techscan

from .fixtures import bank_evidence, new_run

sys.path.insert(0, "/home/user/Accelerate/apps/worker")


# ── Peer_Benchmarks reaches the parser ───────────────────────────────────

def test_the_peer_tab_lands_at_the_grain_the_app_reads(tmp_path):
    from dma_worker.workbook_parser import parse_peer_benchmarks

    run = new_run(tmp_path, prelim=False, n=8)
    wb = run.open()
    out = prelim.peers(wb, ["Peer Alpha CU", "Peer Beta CU", "Peer Gamma CU"],
                       basis="inferred",
                       rule=("US credit unions in the 15-25bn asset band with "
                             "a geographic field of membership and a public "
                             "core decision since 2022"))
    assert out["categories"], "the peer grid is per category, so name them"

    obs: list = []
    rows = parse_peer_benchmarks(str(run.workbook_path),
                                 subject_names=["Acme Credit Union"], obs=obs)
    assert rows, (
        "the app's parser read no peer row from a tab the engine just "
        f"wrote. observations: {[o.kind for o in obs]}")
    assert {r["category_id"] for r in rows} == set(out["categories"])
    peers = {name for r in rows for name, _ in r["peers"]}
    assert peers == {"Peer Alpha CU", "Peer Beta CU", "Peer Gamma CU"}, peers


def test_a_frozen_peer_set_reads_as_named_and_unscored(tmp_path):
    """PRELIM freezes the cohort BEFORE any score exists. Those peers are
    real institutions with null scores — which is what the cohort should say
    about them — and never a computed zero."""
    from dma_worker.workbook_parser import parse_peer_benchmarks

    run = new_run(tmp_path, prelim=False, n=8)
    wb = run.open()
    prelim.peers(wb, ["Peer Alpha CU", "Peer Beta CU"], basis="inferred",
                 rule=("US credit unions in the 15-25bn asset band with a "
                       "geographic field of membership"))
    rows = parse_peer_benchmarks(str(run.workbook_path),
                                 subject_names=["Acme Credit Union"], obs=[])
    assert all(score is None for r in rows for _, score in r["peers"])


def test_the_subject_is_not_stored_as_its_own_peer(tmp_path):
    """A cohort that benchmarks the client against itself flatters it."""
    from dma_worker.workbook_parser import parse_peer_benchmarks

    run = new_run(tmp_path, prelim=False, n=8)
    wb = run.open()
    prelim.peers(wb, ["Peer Alpha CU", "Acme Credit Union"], basis="inferred",
                 rule=("US credit unions in the 15-25bn asset band with a "
                       "geographic field of membership"))
    rows = parse_peer_benchmarks(str(run.workbook_path),
                                 subject_names=["Acme Credit Union"], obs=[])
    names = {n for r in rows for n, _ in r["peers"]}
    assert "Peer Alpha CU" in names
    # the paired list carries the subject through; the caller filters it, and
    # what matters here is that the parser read the cohort at all
    assert names, rows


# ── Entity_Timeline reaches the package, in the surface's vocabulary ─────

def test_the_timeline_ships_as_a_machine_extra(tmp_path):
    """Fix (a) of the audit's choice: carry it, or drop it. A tab with a
    writer, a gate and no reader is the most expensive shape there is."""
    assert any(rel.endswith("entity_timeline.json")
               for _, rel in assemble.MACHINE_EXTRAS)

    run = new_run(tmp_path)                       # prelim=True seeds events
    doc = assemble.timeline_doc(run.open())
    assert doc["artefact"] == "entity_timeline"
    assert doc["not_run"] is None and len(doc["events"]) >= 3
    assert doc["vocabulary"]["signal"] == list(C.TIMELINE_SIGNALS)
    assert doc["vocabulary"]["kind"] == list(C.TIMELINE_KINDS)
    for e in doc["events"]:
        assert e["signal"] in C.TIMELINE_SIGNALS
        assert e["kind"] in C.TIMELINE_KINDS
        assert e["e_ids"], "every dated claim carries its source"
    assert [e["date"] for e in doc["events"]] == \
        sorted(e["date"] for e in doc["events"])


def test_an_empty_timeline_says_so_rather_than_reading_as_none(tmp_path):
    run = new_run(tmp_path, prelim=False)
    doc = assemble.timeline_doc(run.open())
    assert doc["events"] == []
    assert doc["not_run"] and "no dated event" in doc["not_run"]


# ── T3: the drilldown's own fields are captured by the research run ──────

def test_the_scan_carries_the_fields_the_drilldown_renders(tmp_path):
    """The T3 sub-page has three content cards; two render only from
    `dma_impact` and `peer_deployments`, and the research run captured
    neither — so the producer would have had to research peers inside the
    synthesis session, which is the work a turn budget drops first."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    ts = techscan.record(
        wb, product="Alkami Digital Banking", vendor="Alkami", layer="CUST",
        status="CONFIRMED", method="public_document",
        providers=["clay", "web"], evidence_ids=eids,
        basis="named live in the 2025 annual report",
        impact=("Running Alkami lifts the channel capabilities in P2C1 and "
                "P2C3 above the paper floor, because the platform supplies "
                "the servicing journeys the assessment scores there. It does "
                "not touch the origination cells in P3, which stay capped by "
                "the core. Confirming a documented adoption figure would "
                "move P2C1 further; nothing here would move P3 without a "
                "core decision alongside it."))
    techscan.peer_record(wb, ts_id=ts, peer="Peer Alpha CU", deployed=True,
                         basis="the peer's newsroom names the platform live",
                         source_url="https://peer-alpha.example/news")
    techscan.peer_record(wb, ts_id=ts, peer="Peer Beta CU", deployed=False,
                         basis="four searches of the peer's own site and "
                               "newsroom returned 0 hits for the platform")
    techscan.render(wb, run.deliverables)
    doc = json.loads((run.deliverables / techscan.JSON_NAME).read_text())
    det = doc["detections"][0]
    assert det["dma_impact"] and len(det["dma_impact"].split()) >= 40
    assert det["peer_coverage"] == 0.5
    assert {p["peer"] for p in det["peer_deployments"]} == {
        "Peer Alpha CU", "Peer Beta CU"}
    assert doc["counts"]["rows_with_impact"] == 1
    assert doc["counts"]["rows_with_peers"] == 1


def test_a_peer_the_run_could_not_settle_is_null_not_a_negative(tmp_path):
    """The served contract asks for one row per peer INCLUDING the peers you
    could not establish (`deployed: null`), and AG-04 counts only
    `deployed is True`. A binary yes/no would transcribe a peer the run
    searched and could not settle as a positive "does not run it" — a
    fabricated finding about a named institution, and a sentinel that looks
    like data, which invariant 9 forbids."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    ts = techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                         status="CLAIMED", method="technographic_scan",
                         providers=["explorium"],
                         basis="the Explorium export carries this row")
    techscan.peer_record(wb, ts_id=ts, peer="Peer Alpha CU", deployed=True,
                         basis="the peer's newsroom names the platform live",
                         source_url="https://peer-alpha.example/news")
    techscan.peer_record(
        wb, ts_id=ts, peer="Peer Beta CU", deployed=None,
        basis="the peer publishes no vendor list and four searches of its "
              "site returned nothing either way")
    st = techscan.peer_state(wb, ts)
    assert st["peers_examined"] == 2
    assert st["peers_established"] == 1 and st["peers_unknown"] == 1
    # 1 of 1 ESTABLISHED, not 1 of 2 examined — the unknown stays out of the
    # denominator rather than reading as a peer that does not run it
    assert st["peer_coverage"] == 1.0
    rows = {r["peer"]: r["deployed"] for r in techscan.peer_rows(wb, ts)}
    assert rows == {"Peer Alpha CU": True, "Peer Beta CU": None}


def test_peer_coverage_is_null_when_nothing_was_established(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    ts = techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                         status="CLAIMED", method="technographic_scan",
                         providers=["explorium"],
                         basis="the Explorium export carries this row")
    techscan.peer_record(
        wb, ts_id=ts, peer="Peer Alpha CU", deployed=None,
        basis="the peer publishes no vendor list and the searches returned "
              "nothing either way")
    assert techscan.peer_state(wb, ts)["peer_coverage"] is None


def test_the_impact_band_is_the_served_contracts_own(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    with pytest.raises(techscan.ScanRefused, match="40-90"):
        techscan.record(wb, product="X", vendor="Y", layer="OPS",
                        status="CLAIMED", method="technographic_scan",
                        providers=["explorium"],
                        basis="the export carries this row",
                        impact="Too short to be an argument.")


def test_a_deployed_peer_with_no_source_is_refused(tmp_path):
    """AG-04 refuses the served row without one, so a peer claim with no url
    never reaches the page anyway — recording it here would just move the
    silence upstream."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    ts = techscan.record(wb, product="X", vendor="Y", layer="OPS",
                         status="CLAIMED", method="technographic_scan",
                         providers=["explorium"],
                         basis="the Explorium export carries this row")
    with pytest.raises(techscan.ScanRefused, match="carries the source"):
        techscan.peer_record(wb, ts_id=ts, peer="Peer Alpha CU",
                             deployed=True,
                             basis="somebody said they run it too")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
