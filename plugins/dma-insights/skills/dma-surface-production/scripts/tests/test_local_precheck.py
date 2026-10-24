"""The server's pass-1 gates run locally before a submission is spent, and
CG-15 is among them (QA audit F-O07-010: replayed over the audit's 102
cells, pass 1 caught 45 of the 46 server refusals).
"""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[4]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SAME = ("Within Governance and Risk Appetite, the evidenced cells speak to the platform "
        "this capability runs on but not to this capability itself, so the score rests "
        "on presence rather than observed use across the institution.")


def _cells(n, text=SAME):
    return [{"subcap_id": f"P1C2.1.{i}", "synthesis": text, "e_ids": [], "items": [],
             "grounded_on": 0, "thin": True, "reach_note": "no cell-specific item"}
            for i in range(1, n + 1)]


def _sections(tmp_path, cells):
    d = tmp_path / "sections"
    d.mkdir()
    (d / "heatmap.cell_evidence.json").write_text(json.dumps({
        "cells": cells, "linking_stats": {"cells_scored": len(cells), "cells_linked": 0,
                                          "rows_unlinkable": 0}}))
    return d


def test_ship_page_refuses_a_page_the_pass1_gates_refuse(tmp_path, capsys, monkeypatch):
    sp = _load("ship_page")
    sent = []
    monkeypatch.setattr(sp, "mcp", lambda tool, args: sent.append(tool) or {"verdict": {"status": "pass"}})
    d = _sections(tmp_path, _cells(4))
    rc = sp.main(["run-1", "heatmap", "--sections", str(d), "--repo", str(REPO),
                  "--verdicts-out", str(tmp_path / "v.json")])
    out = capsys.readouterr().out
    assert rc == 1 and sent == [], "a locally refused page is never submitted"
    assert "NOT SUBMITTED" in out and "CG-15" in out
    v = json.loads((tmp_path / "v.json").read_text())
    assert v["heatmap"]["status"] == "local_precheck_fail"
    assert any(r["gate_id"] == "CG-15" for r in v["heatmap"]["reasons"])


def test_no_precheck_submits_anyway(tmp_path, monkeypatch):
    sp = _load("ship_page")
    sent = []
    monkeypatch.setattr(sp, "mcp", lambda tool, args: sent.append(tool) or {"verdict": {"status": "pass"}})
    d = _sections(tmp_path, _cells(4))
    assert sp.main(["run-1", "heatmap", "--sections", str(d), "--no-precheck"]) == 0
    assert sent == ["submit_page_payload"]


def test_local_precheck_is_not_run_without_the_connector_package(tmp_path):
    """Run in a fresh interpreter so an already-imported dma_mcp cannot
    answer for a container that does not have it: a check that could not
    run is disclosed as not_run, never as a pass."""
    import subprocess
    import sys
    code = (
        "import json, sys, importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('ship_page', {str(SCRIPTS / 'ship_page.py')!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "print(json.dumps(m.local_precheck('heatmap', {'cell_evidence': {'cells': []}}, "
        f"repo={str(tmp_path)!r})))\n")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(tmp_path), env=env, timeout=120)
    assert p.returncode == 0, p.stderr
    pre = json.loads(p.stdout.strip().splitlines()[-1])
    assert pre["status"] == "not_run" and pre["reasons"] == []
    assert "cannot reach" in pre["why"] or "apps/mcp" in pre["why"]


def test_self_heal_runs_cg15_and_blocks_on_it(tmp_path, capsys):
    sh = _load("self_heal")
    d = _sections(tmp_path, _cells(4))
    rc = sh.main(["--sections", str(d), "--page", "heatmap", "--repo", str(REPO),
                  "--entity", "Acme Credit Union"])
    out = capsys.readouterr().out
    assert rc == 1 and "CG-15:" in out and "BLOCKING" in out


def test_self_heal_states_not_run_rather_than_passing(tmp_path, capsys):
    sh = _load("self_heal")
    distinct = [{**c, "synthesis": f"Cell {i} has its own argument about a different artefact "
                                   f"number {i} with its own evidence position and consequence."}
                for i, c in enumerate(_cells(3))]
    d = _sections(tmp_path, distinct)
    rc = sh.main(["--sections", str(d), "--page", "heatmap", "--no-cg15"])
    out = capsys.readouterr().out
    assert rc == 0 and "CG-15 NOT RUN" in out and "NOT RUN is not a pass" in out


@pytest.mark.parametrize("replay", [REPO / "qa_audit" / "2026-09-28"])
def test_the_measured_catch_rate_is_recorded(replay):
    text = (replay / "findings_register.csv").read_text()
    assert "F-O07-010" in text
