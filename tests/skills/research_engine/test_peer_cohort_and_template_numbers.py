"""Owner, 2026-10-06 (First Tech, Client Research §4 failed four rounds on
"3 to 5 peers" against a six-peer locked set):

  "Template having 5 does not make 5 a constant for you to fail the report;
   fix the code. Then research metrics only for areas of focus with peer
   scores being an average of current entities in the same subvert already
   assessed."
"""
from __future__ import annotations

import json
from pathlib import Path

from engine import brief, prelim, relay
from engine import report_spec as RS
from fixtures import researched_run

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"


# ── the template's numbers are guidance ─────────────────────────────────

def test_no_section_fails_on_a_peer_count_ceiling():
    for key, spec in RS.SPECS.items():
        for sec in spec.sections:
            text = f"{sec.fail_if} {sec.min_data if hasattr(sec, 'min_data') else ''}"
            assert "more than 5 peers" not in text, (key, sec.id)
    doc = json.loads((PLUGIN / "references/templates/report_templates.json").read_text())
    blob = json.dumps(doc)
    assert "more than 5 peers" not in blob
    assert "Between 3 and 5 peers" not in blob and "3 to 5 peers" not in blob
    cr4 = doc["reports"]["client_research"]["sections"][3]
    assert "Handoff_Lock" in cr4["fail_if"] and "Handoff_Lock" in cr4["minimum_data"]
    assert "focus areas only" in cr4["minimum_data"]


def test_the_markdown_docs_say_what_the_json_enforces():
    for f in ("client_profile_template.md", "assessment_report_template.md"):
        md = (PLUGIN / "references/templates" / f).read_text()
        assert "more than 5 peers" not in md and "between 3 and 5" not in md, f


def test_validators_and_writers_are_told_template_numbers_are_not_constants(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    for validator in (False, True):
        out = brief.report_batch(wb, run=run, out_dir=tmp_path / f"b{validator}",
                                 validator=validator)
        for b in out["briefs"]:
            text = Path(b["prompt_file"]).read_text()
            assert "guidance, not constants" in text, b["prompt_file"]
    agent = (PLUGIN / "agents/reports/report-validator.md").read_text()
    assert "## The template's numbers are guidance, not constants" in agent


# ── peer scores: the sub-vertical cohort mean ───────────────────────────

def _cohort(cats, *, missing=()):
    return {"sub_vertical": "CU", "entities": 5, "floor": 3,
            "categories": {c: ({"n": 2, "mean": None, "reason": "2 assessed entities "
                                "in the cohort for this category; the floor is 3"}
                               if c in missing else
                               {"n": 5, "mean": 2.37, "median": 2.4, "p25": 2.1, "p75": 2.6})
                           for c in cats}}


def test_the_cohort_mean_becomes_every_blank_peer_figure(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cats = [r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    assert cats and all(not str(r.get("Peer_Median") or "").strip()
                        for r in wb.rows("Peer_Benchmarks"))
    got = prelim.fill_cohort_peers(wb, _cohort(cats))
    assert got["filled"] == cats and not got["cannot_estimate"]
    rows = {r["Category_ID"]: r for r in wb.rows("Peer_Benchmarks")}
    first = rows[cats[0]]
    assert float(first["Peer_Median"]) == 2.37 and int(first["Peer_N"]) == 5
    assert str(first["Peer_Basis"]).startswith("recomputed: sub-vertical cohort (CU)")
    # below the cohort floor: cannot_estimate with the reason, never imputed
    got = prelim.fill_cohort_peers(wb, _cohort(cats, missing=cats), overwrite=True)
    assert got["cannot_estimate"] == cats
    last = {r["Category_ID"]: r for r in wb.rows("Peer_Benchmarks")}[cats[-1]]
    assert str(last["Peer_Median"] or "") == "" and str(last["Peer_Basis"]).startswith(
        "cannot_estimate:") and "floor is 3" in str(last["Peer_Basis"])
    # the named peer set is untouched: identified, not scored
    assert first["Peer_Names"] and not str(first.get("Peer_Scores") or "").strip()


def test_a_figure_already_recorded_is_kept(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cats = [r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    prelim.peer_median(wb, category=cats[0], median=3.1, basis="table",
                       source="NCUA call report table, hand recorded")
    got = prelim.fill_cohort_peers(wb, _cohort(cats))
    assert cats[0] in got["kept"] and cats[0] not in got["filled"]
    row = next(r for r in wb.rows("Peer_Benchmarks") if r["Category_ID"] == cats[0])
    assert float(row["Peer_Median"]) == 3.1


def test_the_driver_fills_from_the_connector_and_survives_its_absence(tmp_path):
    from engine import pipeline as P, pipeline_stub as S
    run, wb, cells, ev = researched_run(tmp_path)
    reads = S.StubReads()
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=reads,
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None)
    pipe = P.Pipeline(run, opts)
    pipe._cohort_peers()
    assert reads.cohort_calls == 1
    assert all(str(r.get("Peer_Median") or "").strip()
               for r in run.open().rows("Peer_Benchmarks") if r.get("Category_ID"))
    # filled: no second call
    P.Pipeline(run, opts)._cohort_peers()
    assert reads.cohort_calls == 1

    run2, wb2, *_ = researched_run(tmp_path / "two")

    class Down(S.StubReads):
        def cohort_benchmarks(self, *a, **k):
            return {"_error": "connector unreachable"}
    opts2 = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=Down(),
                      shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o2",
                      ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None)
    P.Pipeline(run2, opts2)._cohort_peers()          # no raise, blanks stay blank
    assert all(not str(r.get("Peer_Median") or "").strip()
               for r in run2.open().rows("Peer_Benchmarks"))


# ── peer metrics are researched on the focus areas only ─────────────────

def test_peer_metric_probes_cover_each_peer_on_each_focus_area_and_nothing_else(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    fas = [r for r in wb.rows("Focus_Areas") if r.get("ID")]
    peers = [p for p in str((wb.handoff_lock() or {}).get("locked_peer_set") or "").split("|")
             if p.strip()]
    assert fas and peers
    relay.report_probes(run, wb)
    focus = [r for r in relay.requests(run).values()
             if str(r.get("proves") or "").startswith(relay.PEER_FOCUS)]
    assert len(focus) == len(fas) * len(peers)
    fa_ids = {str(f["ID"]) for f in fas}
    for r in focus:
        assert any(f" | {i} " in r["proves"] for i in fa_ids), r["proves"]
