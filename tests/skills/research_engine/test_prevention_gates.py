"""Preventive gates: the driver refuses or records BEFORE a lane, a report
writer or a submit spends on what the connector would refuse later (owner,
2026-10-07: "I want preventive measures, hooks")."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import contract as C, pipeline as P, prelim, profile
from fixtures import new_run, researched_run


# ── the pages preflight refills peers before any lane ─────────────────────

def test_the_pages_prepare_refills_peers_before_any_lane(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    calls = []
    d = SimpleNamespace(wb=wb, run=run, opts=SimpleNamespace(log=lambda *a: None, reads=None),
                        state={}, _cohort_peers=lambda: calls.append("peers"))
    P.Pipeline._pages_prepare(d, P.PAGES_A)
    P.Pipeline._pages_prepare(d, ("overview",))
    assert calls == ["peers", "peers"]


# ── PRELIM gates the sub-vertical set while the run can still act ─────────

def test_prelim_names_the_subvertical_members_cg18c_would_hold(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    assert C.stage_of(wb.metadata()) == "research"
    assert profile.missing_subvertical_firmographics(wb) == []
    row = next(r for r in wb.rows("Firmographics") if r["Field"] == "net_worth_ratio")
    wb.update_row("Firmographics", "Field", "net_worth_ratio", {"Field": "nwr_retired"})
    st = prelim.state(run.open())
    firm = next(s for s in st["sections"] if s["section"] == "firmographics")
    assert firm["status"] == "OPEN" and "net_worth_ratio" in firm["detail"] and "CG-18c" in firm["detail"]
    assert "firmographics" in st["open"]


def test_an_absent_member_with_a_route_satisfies_the_gate(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    wb.update_row("Firmographics", "Field", "net_worth_ratio", {"Field": "nwr_retired"})
    profile.firmographic(run.open(), field="net_worth_ratio", state="ABSENT",
                         reason="the credit union publishes no net worth ratio outside the call report",
                         route="NCUA 5300 call report Q4-2025, searched 2026-10-07")
    st = prelim.state(run.open())
    assert "firmographics" not in st["open"]


# ── a connector deploy mid-run is seen, not debugged page by page ─────────

def test_contract_drift_stales_pages_passed_under_the_old_version():
    state = {"pages": {"heatmap": {"versions": {"A": "pass"}, "contract_version": {"A": "cr-old"}},
                       "overview": {"versions": {"B": "fail"}, "contract_version": {"B": "cr-old"}}},
             "stages": {"REPORTS": {"status": "PASS"}, "PAGES_A": {"status": "PASS"}}}
    assert P.mark_contract_drift(state, "cr-old", page="heatmap", version="A", now="t0") is None
    drift = P.mark_contract_drift(state, "cr-new", page="overview", version="B", now="t1")
    assert drift["was"] == "cr-old" and drift["stale_pages"] == ["heatmap vA"]
    assert drift["stages_under_old"] == ["PAGES_A", "REPORTS"]
    assert state["pages"]["heatmap"]["versions"]["A"] == "stale_contract"
    assert state["contract_version"] == "cr-new" and state["connector_drift"][0] is drift
    assert P.mark_contract_drift(state, "cr-new", page="overview", version="B", now="t2") is None


def test_contract_version_is_read_from_either_progress_shape():
    assert P._contract_version_of({"pages": [{"page": "heatmap", "contract_version": "cr-1"}]}, "heatmap") == "cr-1"
    assert P._contract_version_of({"pages": {"heatmap": {"page": "heatmap", "contract_version": "cr-2"}}}, "heatmap") == "cr-2"
    assert P._contract_version_of({"pages": []}, "heatmap") is None
    assert P._contract_version_of("garbage", "heatmap") is None


# ── the enforcement sweep runs before the writers, as a logged gate ───────

def test_the_sweep_writes_the_rung_file_and_logs_a_gate(tmp_path, monkeypatch):
    run, wb, cells, ev = researched_run(tmp_path)
    import subprocess as sp
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        out = Path(cmd[cmd.index("--out") + 1])
        out.write_text(json.dumps({"verified": True, "actions_found": False,
                                   "counts": {"VERIFIED_ABSENT": 2, "RESOLVED": 0, "NOT_RUN": 0},
                                   "sources_searched": [{"source": "CFPB", "outcome": "VERIFIED_ABSENT"},
                                                        {"source": "NE orders", "outcome": "VERIFIED_ABSENT"}]}))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(sp, "run", fake_run)
    d = SimpleNamespace(wb=wb, run=run, opts=SimpleNamespace(log=lambda *a: None, enforcement_sweep=True),
                        _md=lambda: wb.metadata())
    doc = P.Pipeline._enforcement_sweep(d, force=True)
    assert doc["verified"]
    cmd = calls[0]
    assert "--name" in cmd and "Acme Credit Union" in cmd and "--no-fdic" in cmd   # a CU is NCUA's
    assert "--state" in cmd and cmd[cmd.index("--state") + 1] == "CA"              # from HQ "Sacramento, CA"
    assert (run.qa_dir / "enforcement_rungs.json").is_file()
    assert any(g.get("Gate") == "ENFORCEMENT_SWEEP" and g.get("Verdict") == "PASS"
               for g in run.open().rows("Gate_Log"))
    # a second call reuses the fresh file: no second network sweep
    P.Pipeline._enforcement_sweep(d, force=True)
    assert len(calls) == 1


def test_a_sweep_that_cannot_run_is_a_not_run_gate_never_a_stop(tmp_path, monkeypatch):
    run, wb, cells, ev = researched_run(tmp_path)
    import subprocess as sp
    monkeypatch.setattr(sp, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("node missing")))
    d = SimpleNamespace(wb=wb, run=run, opts=SimpleNamespace(log=lambda *a: None, enforcement_sweep=True),
                        _md=lambda: wb.metadata())
    assert P.Pipeline._enforcement_sweep(d, force=True) is None
    g = next(g for g in run.open().rows("Gate_Log") if g.get("Gate") == "ENFORCEMENT_SWEEP")
    assert g["Verdict"] == "NOT_RUN" and "node missing" in g["Detail"]


def test_under_pytest_the_sweep_never_touches_the_network(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    d = SimpleNamespace(wb=wb, run=run, opts=SimpleNamespace(log=lambda *a: None, enforcement_sweep=True),
                        _md=lambda: wb.metadata())
    assert P.Pipeline._enforcement_sweep(d) is None
    assert not (run.qa_dir / "enforcement_rungs.json").exists()
