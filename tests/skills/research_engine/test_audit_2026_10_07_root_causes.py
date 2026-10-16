"""Root causes the Arbor Bank run (2026-10-05..07) exposed, each closed at the
mechanism rather than at the symptom:

  A  the manifest dropped the owner's supplementary sub-vertical binding
  B  a page repaired after a pass with no recorded ship time was "ok"
  G  Search_Log Seq was allocated from the row count and reused numbers
  H  cohort peers filled only blank rows, so placeholders stood
  M  the engine's firmographic must-present set was not the connector's
  O  a resume without --max-usd forgot the owner's approved ceiling
  P  the entity's own site could be filed T1, and nothing could re-tier it
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import assemble, contract as C, ledger as L, pipeline as P, prelim, profile, runstate
from fixtures import CAT, new_run, researched_run


def _cell():
    return list(C.taxonomy().cells_in(CAT))[0]


# ── A ────────────────────────────────────────────────────────────────────

def test_the_manifest_carries_the_supplementary_binding(tmp_path):
    run = runstate.start(
        run_id="R-SUPP", entity_name="Acme Credit Union", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE", reference_date="2026-08-29",
        root=tmp_path / "run", supplementary=["RB"])
    wb = run.open()
    doc = assemble.manifest_doc(wb, status="IN_PROGRESS", stage="OPENED", run=run)
    assert doc["institution"]["supplementary_sub_verticals"] == ["RB"]
    assert assemble.validate_manifest(doc) == []


def test_a_single_binding_states_an_empty_list_not_a_missing_key(tmp_path):
    run = new_run(tmp_path)
    doc = assemble.manifest_doc(run.open(), status="IN_PROGRESS", stage="OPENED", run=run)
    assert doc["institution"]["supplementary_sub_verticals"] == []
    doc["institution"].pop("supplementary_sub_verticals")
    assert assemble.validate_manifest(doc), "the key is required: the worker reads it"


def test_the_worker_reads_the_key_the_engine_writes():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "worker"))
    from dma_worker.persist import _institution
    got = _institution({"institution": {"name": "Acme", "entity_id": "acme", "sub_vertical": "CU",
                                        "supplementary_sub_verticals": ["RB"]}})
    assert got["supplementary_sub_verticals"] == ["RB"]


# ── B ────────────────────────────────────────────────────────────────────

def _driver(tmp_path, rec):
    sections = tmp_path / "08_sections"
    sections.mkdir(exist_ok=True)
    (sections / "heatmap.alerts.json").write_text("{}")
    d = SimpleNamespace(state={"pages": {"heatmap": rec}},
                        run=SimpleNamespace(qa_dir=tmp_path / "qa"))
    d.run.qa_dir.mkdir(exist_ok=True)
    d._page_mtime = lambda page: max(x.stat().st_mtime for x in sections.glob(f"{page}.*.json"))
    return d, sections


def test_a_pass_with_no_ship_time_and_no_verdict_file_ships_again(tmp_path):
    d, _ = _driver(tmp_path, {"versions": {"B": "pass"}})
    assert not P.Pipeline._page_ok(d, "heatmap", "B")


def test_the_verdict_file_stands_in_for_a_missing_ship_time(tmp_path):
    d, sections = _driver(tmp_path, {"versions": {"B": "pass"}})
    vf = d.run.qa_dir / "verdict_heatmap_B.json"
    vf.write_text("{}")
    later = vf.stat().st_mtime + 60
    os.utime(vf, (later, later))
    assert P.Pipeline._page_ok(d, "heatmap", "B")
    f = sections / "heatmap.alerts.json"
    os.utime(f, (later + 60, later + 60))
    assert not P.Pipeline._page_ok(d, "heatmap", "B"), "repaired after the ship: not the passed page"


# ── G ────────────────────────────────────────────────────────────────────

def test_search_seq_is_allocated_past_the_highest_not_from_the_row_count(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    cell = _cell()
    s1 = L.append_search(wb, subcap=cell, facet="primary", query="acme q1", tool="exa",
                         hits=3, kept=1)
    s2 = L.append_search(wb, subcap=cell, facet="primary", query="acme q2", tool="exa",
                         hits=3, kept=1)
    assert s2 == s1 + 1
    # a row removed (a strip, a repair) must not make the next Seq a reuse
    wb.update_row_where("Search_Log", {"Seq": s1}, {"Seq": s2 + 50})
    s3 = L.append_search(wb, subcap=cell, facet="primary", query="acme q3", tool="exa",
                         hits=3, kept=1)
    assert s3 == s2 + 51
    seqs = [int(float(r["Seq"])) for r in wb.rows("Search_Log")]
    assert len(seqs) == len(set(seqs))


# ── H ────────────────────────────────────────────────────────────────────

def _cohort(cats, mean=2.37):
    return {"entities": 5, "floor": 3, "basis": "recomputed", "sub_vertical": "CU",
            "categories": {c: {"n": 5, "mean": mean, "median": mean, "p25": 2.1, "p75": 2.6}
                           for c in cats}}


def test_a_placeholder_is_replaced_by_the_cohort_and_a_table_is_kept(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cats = [r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    cat = cats[0]
    prelim.peer_median(wb, category=cat, median=3.0, basis="inferred",
                       source="placeholder from the template, nobody measured it")
    got = prelim.fill_cohort_peers(wb, _cohort(cats))
    assert cat in got["filled"]
    row = next(r for r in wb.rows("Peer_Benchmarks") if r["Category_ID"] == cat)
    assert float(row["Peer_Median"]) == 2.37
    assert prelim.peer_row_is_cohort_sourced(row)
    # the cohort's own row is not rewritten on the next pass …
    got = prelim.fill_cohort_peers(wb, _cohort(cats, mean=2.9))
    assert cat in got["kept"]
    # … and a hand-recorded TABLE beats the cohort
    prelim.peer_median(wb, category=cat, median=3.1, basis="table",
                       source="NCUA call report table, hand recorded")
    got = prelim.fill_cohort_peers(wb, _cohort(cats))
    assert cat in got["kept"]
    row = next(r for r in wb.rows("Peer_Benchmarks") if r["Category_ID"] == cat)
    assert float(row["Peer_Median"]) == 3.1


def test_a_guess_is_never_replaced_by_a_null(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path / "a")
    cats = [r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    cat = cats[0]
    prelim.peer_median(wb, category=cat, median=3.0, basis="inferred",
                       source="placeholder from the template, nobody measured it")
    below = {**_cohort(cats), "categories": {c: {"n": 1, "mean": None, "reason": "below floor"}
                                              for c in cats}}
    got = prelim.fill_cohort_peers(wb, below)
    assert cat in got["kept"], "a guess stands until the cohort has a figure"
    # a BLANK row below the floor is stated as cannot_estimate with the reason
    run2, wb2, _, _ = researched_run(tmp_path / "b")
    got = prelim.fill_cohort_peers(wb2, below)
    assert cat in got["cannot_estimate"]


def test_the_driver_refills_while_any_row_is_not_the_cohorts(tmp_path):
    from engine import pipeline_stub as S
    run, wb, cells, ev = researched_run(tmp_path)
    cats = [r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    for c in cats:
        prelim.peer_median(wb, category=c, median=3.0, basis="inferred",
                           source="placeholder from the template, nobody measured it")
    reads = S.StubReads() if hasattr(S, "StubReads") else None
    rows = wb.rows("Peer_Benchmarks")
    assert any(prelim.peer_row_wants_cohort(r, has_figure=True) for r in rows)
    got = prelim.fill_cohort_peers(wb, _cohort(cats))
    assert not any(prelim.peer_row_wants_cohort(r, has_figure=True)
                   for r in wb.rows("Peer_Benchmarks")), "once filled, the driver stops"
    assert got["filled"] == cats


# ── M ────────────────────────────────────────────────────────────────────

def test_the_engine_must_present_set_is_the_connectors():
    spec = json.loads((Path(__file__).resolve().parents[3] / "packages" / "shared"
                       / "contracts_data.json").read_text())
    theirs = spec["overview"]["firmographics"]["fields"]["fields"]
    ours = C.firmographics_spec()
    for k in ("must_present", "must_present_any", "must_present_by_subvertical",
              "stated_not_held", "held_ceiling", "must_present_key"):
        assert ours[k] == theirs[k], f"engine/schemas/firmographics_must_present.json drifted on {k}"
    assert "HQ" in C.FIRMOGRAPHIC_MUST_PRESENT and "headquarters" not in C.FIRMOGRAPHIC_MUST_PRESENT
    assert "ownership" not in C.FIRMOGRAPHIC_MUST_PRESENT


def test_missing_firmographics_reads_aliases_and_groups(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    assert profile.missing_firmographics(wb) == []
    eid = next(r["E_ID"] for r in wb.rows("Evidence_Detail") if r.get("E_ID"))
    # CU sub-vertical set: the fixture carries it (PRELIM gates it); a member
    # under any alias of its group satisfies it, a missing one is named
    assert profile.missing_subvertical_firmographics(wb) == []
    wb.update_row("Firmographics", "Field", "net_worth_ratio", {"Field": "nwr_retired"})
    assert profile.missing_subvertical_firmographics(wb) == ["net_worth_ratio"]
    profile.firmographic(wb, field="net worth ratio", value="11.2", unit="percent",
                         as_of="2025-12-31", evidence=eid, confidence="High")
    assert profile.missing_subvertical_firmographics(wb) == []


# ── O ────────────────────────────────────────────────────────────────────

def _budget_driver(max_usd, state):
    return SimpleNamespace(opts=SimpleNamespace(max_usd=max_usd), state=state,
                           wb=SimpleNamespace(selected_subcaps=lambda: ["P1C1.1.1", "P2C1.1.1"]))


def test_an_owner_approved_ceiling_outlives_the_invocation_that_set_it():
    d = _budget_driver(None, {"budget_usd": 475.0, "budget_usd_source": "flag"})
    assert P.Pipeline.budget_usd(d) == 475.0


def test_a_default_ceiling_is_only_ever_an_estimate():
    from engine import cost
    d = _budget_driver(None, {"budget_usd": 20.0, "budget_usd_source": "default"})
    assert P.Pipeline.budget_usd(d) == cost.run_budget_default(2)


def test_a_flag_still_wins():
    d = _budget_driver(300, {"budget_usd": 475.0, "budget_usd_source": "flag"})
    assert P.Pipeline.budget_usd(d) == 300.0


# ── P ────────────────────────────────────────────────────────────────────

def test_the_entitys_own_site_is_never_t1(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    assert "acme.example" in L.own_hosts(wb)
    with pytest.raises(L.LedgerRefusal, match="own domain"):
        L.append_evidence(wb, source_name="Acme about page",
                          source_url="https://www.acme.example/about", tier="T1",
                          subcaps=[cells[0]], published="2025-01-01", excerpt="A" * 80)
    eid = L.append_evidence(wb, source_name="Acme annual report",
                            source_url="https://acme.example/annual-report.pdf", tier="T2",
                            subcaps=[cells[0]], published="2025-01-01", excerpt="B" * 80)
    assert eid


def test_retier_rederives_the_label_and_logs_the_change(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    eid = L.append_evidence(wb, source_name="Trade press", source_url="https://press.example/x",
                            tier="T2", subcaps=[cells[0]], published="2025-01-01",
                            excerpt="C" * 80)
    row = next(r for r in wb.rows("Evidence_Detail") if r["E_ID"] == eid)
    assert row["Claim_Type"] == "FACT"
    out = L.retier_evidence(wb, eid, "T3", reason="reportage, not an official disclosure; mis-filed at registration", run=run)
    assert out["was"] == "T2" and out["claim_type"] == "INFERENCE"
    row = next(r for r in wb.rows("Evidence_Detail") if r["E_ID"] == eid)
    assert row["Tier"] == "T3" and row["Claim_Type"] == "INFERENCE"
    assert any(g.get("Gate") == "RETIER" and g.get("Scope") == eid for g in wb.rows("Gate_Log"))
    assert any(p.get("Step") == "retier" and eid in str(p.get("Detail")) for p in wb.rows("Provenance"))
    with pytest.raises(L.LedgerRefusal):
        L.retier_evidence(wb, eid, "T3", reason="already there, this is a no-op that must refuse", run=run)


def test_retier_refuses_t1_on_the_own_site(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    eid = L.append_evidence(wb, source_name="Acme product page",
                            source_url="https://acme.example/products", tier="T5",
                            subcaps=[cells[0]], published="2025-01-01", excerpt="D" * 80)
    with pytest.raises(L.LedgerRefusal, match="never T1"):
        L.retier_evidence(wb, eid, "T1", reason="somebody wanted the ceiling lifted, which is the point", run=run)



# ── the run-level window decision is the worst CONVERSATION's, named ─────

def test_the_run_level_ceiling_reads_the_worst_conversation_not_the_lifetime(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    cell = _cell()
    cat = cell.split(".")[0]
    for i in range(L.SEARCH_OP_CEILING + 5):
        try:
            # a LANE tool: a connector search with no lane actor is RELAY's window
            L.append_search(wb, subcap=cell, facet="primary", query=f"acme q{i}",
                            tool="web_search", hits=1, kept=1)
        except L.LedgerRefusal:
            break
    assert L._ops_since_checkpoint(wb, cat) >= L.SEARCH_OP_CEILING
    st = L.stats(wb)
    assert st["checkpoint_required"] and st["window_scope"] == cat
    # the category checkpoints: ITS window resets, the lifetime count does not
    runstate.checkpoint(wb, "category done", scope=cat)
    wb = run.open()
    st = L.stats(wb)
    assert not st["checkpoint_required"], st
    assert st["search_ops"] >= L.SEARCH_OP_CEILING, "lifetime spend is still reported"
    assert L.worst_window(wb)[1] < L.SEARCH_OP_CEILING
