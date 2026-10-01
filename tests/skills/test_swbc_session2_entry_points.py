"""Entry-point defects found taking SWBC through /run-assessment (2026-10-01).

Each one sat between the command a person runs and the engine behind it:
the router slugged the command's own flags into the client name (a
duplicate engagement), the doctor could not see the baseline step 1 had just
written, the markdown brief never listed a HYBRID run's internal documents,
and a budget stop told the operator to re-run the command that had just
refused.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "dma-insights"
SCRIPTS = PLUGIN / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_router_parses_the_commands_own_flags_off_the_client():
    rc = _load("route_client", SCRIPTS / "route_client.py")
    assert rc.split_command_args("SWBC --entity-id swbc --website https://www.swbc.com") \
        == ("SWBC", "swbc")
    assert rc.split_command_args('"Acme Credit Union" --website=https://acme.org') \
        == ("Acme Credit Union", None)
    assert rc.split_command_args("Acme Credit Union") == ("Acme Credit Union", None)
    assert rc.split_command_args("--entity-id=acme-cu") == ("", "acme-cu")


def test_the_doctor_reads_the_baseline_at_the_root_it_is_given(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    tools = "\n".join(["mcp__Exa__web_search_exa", "mcp__Tavily__tavily_search",
                       "mcp__Clay__search-contacts"])
    env = {k: v for k, v in os.environ.items() if k != "DMA_RUN_ROOT"}
    subprocess.run([sys.executable, str(SCRIPTS / "connector_contract.py"), "baseline",
                    "--tools", "-", "--root", str(root)], input=tools, text=True,
                   check=True, capture_output=True, env=env)
    out = subprocess.run([sys.executable, str(SCRIPTS / "doctor.py"), "--no-probe",
                          "--json", "--root", str(root)], text=True,
                         capture_output=True, env=env, timeout=300)
    import json
    rows = {c["check"]: c for c in json.loads(out.stdout)["checks"]}
    row = rows["connector contract"]
    assert row["ok"], row
    assert "UNVERIFIED" not in row["detail"]


def test_the_command_runs_the_doctor_against_the_run_root():
    text = (PLUGIN / "commands" / "run-assessment.md").read_text()
    assert 'doctor.py" --heal --root <ROOT>' in text
    assert text.count("To stop it") == 1, "the stop paragraph is duplicated"
    assert "run_snapshot_CURRENT.json" in text


def test_the_markdown_brief_lists_internal_documents(tmp_path):
    sys.path.insert(0, str(PLUGIN / "skills" / "dma-research"))
    sys.path.insert(0, str(REPO / "tests" / "skills" / "research_engine"))
    from engine import brief, intake
    from fixtures import new_run
    run = new_run(tmp_path, n=3)
    doc = tmp_path / "ctx.md"
    doc.write_text("# Context\n\nThe client's own account of its platforms.\n")
    intake.add(run.root, doc, title="Context write-up")
    wb = run.open()
    wb.set_metadata("evidence_mode", "HYBRID")
    cat = wb.selected_subcaps()[0].split(".")[0]
    md = brief.as_markdown(brief.dispatch(wb, cat, run=run)) \
        if hasattr(brief, "as_markdown") else None
    if md is None:
        from engine import cli  # noqa: F401 — the CLI renders the markdown
        r = subprocess.run([sys.executable, "-m", "engine.brief", "dispatch", "--run",
                            run.run_id, "--root", str(run.root), "--category", cat],
                           cwd=str(PLUGIN / "skills" / "dma-research"),
                           capture_output=True, text=True, timeout=300)
        md = r.stdout
    assert "Internal documents" in md and "Context write-up" in md


def test_a_budget_stop_names_the_raise_it_needs():
    src = (PLUGIN / "skills" / "dma-research" / "engine" / "pipeline.py").read_text()
    i = src.index('outcome="STOPPED_BUDGET"')
    assert "--max-usd <new ceiling>" in src[i:i + 900]


def test_a_routine_aimed_at_a_superseded_run_is_reported():
    """I-63: an hourly Routine for superseded run 9fcee059 was still enabled
    and relaunching lane batches two weeks later."""
    sr = _load("stale_run_routines", SCRIPTS / "stale_run_routines.py")
    trig = [
        {"id": "trig_old", "name": "SWBC DMA round-3 check-in", "enabled": True,
         "derived_state": {"prompt": "SWBC DMA run 9fcee059-1c89-4769-88df-594c2bce20e6 …"}},
        {"id": "trig_now", "name": "SWBC check-in", "enabled": True,
         "derived_state": {"prompt": "SWBC run DMA-RES-SWBC-20260930-0001 …"}},
        {"id": "trig_paused", "name": "old, paused", "enabled": False,
         "derived_state": {"prompt": "SWBC run 9fcee059-1c89-4769-88df-594c2bce20e6"}},
        {"id": "trig_other", "name": "another client", "enabled": True,
         "derived_state": {"prompt": "Acme run DMA-RES-ACME-20260901-0001"}},
    ]
    got = sr.stale(trig, "DMA-RES-SWBC-20260930-0001", client="SWBC")
    assert [g["id"] for g in got] == ["trig_old"]
    assert "enabled=false" in got[0]["action"]
