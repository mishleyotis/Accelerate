"""Acceptance, issue 10: "plugin portability — invokable in a Routine or a
plain Claude Code session."

Measured 2026-09-03: plugin.json declared no `commands`; the only commands
were doctor and setup-routines; none of the six Routines ran research; the
binding needed a live AskUserQuestion; a stale install refused nothing.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from engine import cli, pipeline as P, preflight, template as T

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "dma-insights"
SKILL = PLUGIN / "skills" / "dma-research"


def test_issue10_the_command_is_declared_and_runs_the_pipeline():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert "./commands/run-assessment.md" in manifest["commands"]
    for c in manifest["commands"]:
        assert (PLUGIN / c).is_file(), c
    text = (PLUGIN / "commands" / "run-assessment.md").read_text()
    head = text.split("---")[1]
    assert "description:" in head and "argument-hint:" in head
    # the order a person is walked through, and the commands each step runs
    for must in ("doctor.py", "--heal", "engine.pipeline env", "route_client.py",
                 "engine.preflight init", "AskUserQuestion", "engine.preflight check",
                 "push-package", "engine.cli start", "engine.cost estimate",
                 "engine.cost schedule", "engine.pipeline run", "--max-wall-min",
                 "engine.pipeline status", "--watch", "engine.cost report"):
        assert must in text, must
    steps = text[text.index("## 1 ·"):]                 # the walk itself, after the preamble
    pos = [steps.index(k) for k in ("doctor.py", "route_client.py", "engine.preflight init",
                                    "engine.cli start", "engine.pipeline run --run")]
    assert pos == sorted(pos), "the steps are out of order"
    assert "--force" in text and "Never `--force`" in text
    assert "--resume" in text


def test_issue10_the_canon_carries_a_research_intake_that_only_reuses_an_answered_binding():
    canon = (PLUGIN / "docs" / "ROUTINES.md").read_text()
    i = canon.index("### 2h")
    sec = canon[i:canon.index("### Model, and why it is in the diff")]
    head = sec.splitlines()[0]
    assert "dma-research-intake" in head and "45 */4 * * *" in head
    assert "NOT CREATED" in head, "a Routine nobody created must say so"
    body = sec[sec.index("```") + 3:sec.rindex("```")]
    # resume first, then answered preflights, then start + drive
    at = {k: body.index(k) for k in ("STEP 1 — RESUME FIRST", "STEP 2 — THEN THE ANSWERED PREFLIGHTS",
                                     "STEP 3 — START AND RUN")}
    assert at["STEP 1 — RESUME FIRST"] < at["STEP 2 — THEN THE ANSWERED PREFLIGHTS"] < at["STEP 3 — START AND RUN"]
    assert "engine.pipeline run --run <RUN_ID> --root <ROOT> --max-wall-min 240" in body
    assert "engine.preflight check" in body and "REFUSES an unanswered one" in body
    assert "NEVER edit a preflight" in body and "never write `auto_bound`" in body
    assert "bind a sub-vertical without a recorded human answer" in body
    assert "doctor.py --heal" in body and "engine.pipeline env" in body
    assert "engine.cost estimate" in body and "over budget" in body
    assert "registry.py list --open-only" in body and "get_client_state" in body
    assert "Pass `--allow-stale-install`" in body        # in the NEVER list
    # and §2g's own prompt now names the driver as what runs a started run
    g = canon[canon.index("### 2g"):canon.index("### 2h")]
    assert "engine.pipeline run" in g


def test_issue10_a_stale_install_refuses_research(monkeypatch, tmp_path):
    from fixtures import new_run
    monkeypatch.setattr(cli, "install_state",
                        lambda: {"ok": False, "status": "STALE",
                                 "_summary": "STALE: installed 0.9.12 (47 agents) vs published 1.17.0 (73 agents)"})
    text = cli.refuse_on_stale_install()
    assert text and "STALE" in text and "doctor.py --heal" in text
    run = new_run(tmp_path, n=2)
    from engine import pipeline_stub as S
    out = P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher.fixture_backed(),
                                    reads=S.StubReads(), shipper=S.StubShipper(),
                                    push=False, log=lambda s: None)).run_all()
    assert out["outcome"] == "REFUSED" and "STALE" in out["reason"]
    # the session brief tells the person the same thing, before any dispatch
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "session_brief", PLUGIN / "scripts" / "hooks" / "session_brief.py")
    sb = importlib.util.module_from_spec(spec); spec.loader.exec_module(sb)
    import types
    monkeypatch.setitem(sys.modules, "plugin_version", types.SimpleNamespace(
        compare=lambda: {"ok": False, "status": "STALE"},
        summary=lambda v: "STALE: installed 0.9.12 vs published 1.17.0"))
    assert "IS REFUSED" in sb.install_warning()


def test_issue10_a_recorded_answer_is_reused_headless(tmp_path):
    """The owner's decision: a headless run reuses a RECORDED preflight
    answer; an unanswered one stops with the named blocker."""
    from fixtures import preflight_doc
    doc = preflight_doc()
    pf = tmp_path / "preflight.json"
    pf.write_text(json.dumps(doc))
    got = preflight.require(str(pf))
    b = preflight.bases(got["doc"], got["report"])
    assert b["sub_vertical"] == "CU" and b["evidence_mode"]
    assert doc["binding_question"]["answered_by"]
    # `engine.cli start` from the command line, no human present
    r = subprocess.run([sys.executable, "-m", "engine.cli", "start", "--run", "R-HEADLESS",
                        "--root", str(tmp_path / "run"), "--entity", "Acme Credit Union",
                        "--entity-id", "acme-cu", "--reference-date", "2026-08-29",
                        "--preflight", str(pf), "--no-push", "--folder-root", str(tmp_path / "c")],
                       capture_output=True, text=True, cwd=str(SKILL), timeout=600)
    assert r.returncode == 0, r.stderr[-800:]
    from engine import runstate
    md = runstate.locate("R-HEADLESS", tmp_path / "run").open().metadata()
    assert md["preflight_sha"] and "CU" in str(md["sub_vertical"])
    assert not str(md["sv_basis"]).upper().startswith("UNSTATED")
    # the same file with the question un-asked is refused by name
    doc["binding_question"]["asked"] = False
    (tmp_path / "unasked.json").write_text(json.dumps(doc))
    with pytest.raises(preflight.PreflightRefusal):
        preflight.require(str(tmp_path / "unasked.json"))
    r = subprocess.run([sys.executable, "-m", "engine.cli", "start", "--run", "R-UNASKED",
                        "--root", str(tmp_path / "run2"), "--entity", "Acme Credit Union",
                        "--entity-id", "acme-cu", "--reference-date", "2026-08-29",
                        "--preflight", str(tmp_path / "unasked.json"), "--no-push",
                        "--folder-root", str(tmp_path / "c2")],
                       capture_output=True, text=True, cwd=str(SKILL), timeout=600)
    assert r.returncode == 1 and "REFUSED" in r.stderr
    assert not (tmp_path / "run2").exists() or not list((tmp_path / "run2").rglob("*.xlsx"))


def test_issue10_env_check_names_every_hard_dependency():
    out = P.env_check()
    names = {c["check"] for c in out["checks"]}
    for must in ("python:openpyxl", "python:docx", "claude CLI", "agent_run.py", "mcp_raw.py",
                 "ship_page.py", "drive_fetch.py", "connector identity", "toolkits",
                 "templates vs manifest", "install"):
        assert must in names, must
    for c in out["checks"]:
        assert c["detail"], c["check"]               # every row says what it measured
    # toolkits absent is a stated fallback, never a hard failure
    assert "toolkits" not in out["hard_failures"]


def test_issue10_the_zip_and_the_checkout_carry_the_same_version():
    """One version in three places: both manifests and the templates' pin."""
    plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["name"] == "dma-insights")
    assert plugin == entry["version"] == T.templates_require() == "1.17.0"
    assert T.zip_guard()["ok"]
