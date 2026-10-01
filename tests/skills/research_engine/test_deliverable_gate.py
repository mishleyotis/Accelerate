"""The template and gold-standard gates run from a hook, not from prose.

Measured 28-09-2026 (QA audit F-M08-013): `engine.template` and
`engine.gold_standard` existed as tools and no hook called either; the
enforcement was "run the gate on your own output" in the agents'
manifests. These tests drive the hook the way the harness does — a JSON
event on stdin, the run named by environment — and pin: a deliverable
write records verdicts in the Gate_Log (which the manifest's `gates`
reads); a push is denied while a verdict is not PASS or none exists; the
session is refused a stop once at PACKAGE while a verdict is not PASS;
and `engine.assemble package --push` does not push an unverified package.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from engine import assemble, ledger as L
from fixtures import scored_run, write_both_reports

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
HOOK = PLUGIN / "scripts" / "hooks" / "deliverable_gate.py"


def _hook(event: dict, run) -> dict:
    env = dict(os.environ, DMA_RUN_ID=run.run_id, DMA_RUN_ROOT=str(run.root))
    env.pop("DMA_STAGE_GUARD", None)
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                       capture_output=True, text=True, timeout=300, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else {}


def _bash(hook, cmd):
    return {"hook_event_name": hook, "tool_name": "Bash", "tool_input": {"command": cmd}}


def test_a_report_write_records_verdicts_in_the_gate_log_and_the_manifest(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    write_both_reports(run, wb, cells, ev, render=True)
    out = _hook(_bash("PostToolUse", f"python3 -m engine.cli report --run {run.run_id} "
                                     f"--root {run.root} --report assessment"), run)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "deliverable gate on" in ctx and "TEMPLATE:binding" in ctx
    assert "GS:workbook" in ctx and "GS:report:research" in ctx and "GS:report:assessment" in ctx
    wb = run.open()
    rows = [r for r in wb.rows("Gate_Log") if r.get("Gate") in ("GS", "TEMPLATE")]
    assert {r["Scope"] for r in rows} >= {"binding", "workbook", "report:research", "report:assessment"}
    assert all(r["Verdict"] in ("PASS", "FAIL") for r in rows)
    doc = assemble.manifest_doc(wb, status="IN_PROGRESS", stage="REPORTS", run=run)
    assert "GS:workbook" in doc["gates"] and "TEMPLATE:binding" in doc["gates"]
    assemble.validate_manifest(doc)


def test_a_command_that_writes_no_deliverable_records_nothing(tmp_path):
    run, wb, *_ = scored_run(tmp_path)
    out = _hook(_bash("PostToolUse", f"python3 -m engine.cli status --root {run.root}"), run)
    assert out == {}
    assert not [r for r in run.open().rows("Gate_Log") if r.get("Gate") == "GS"]


def test_a_push_is_denied_without_a_verdict_and_with_a_failing_one(tmp_path):
    run, wb, *_ = scored_run(tmp_path)
    push = _bash("PreToolUse", "python3 scripts/drive_fetch.py push-package --client 'Acme' "
                               "--file 'Acme - DMA'")
    out = _hook(push, run)
    d = out["hookSpecificOutput"]
    assert d["permissionDecision"] == "deny" and "no gold-standard verdict" in d["permissionDecisionReason"]
    L.append_gate(wb, gate="GS", scope="workbook", verdict="FAIL",
                  detail="2 finding(s): GS-WB-SCORES: P1C1.1.1 unscored", blocking=True)
    out = _hook(push, run)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "GS:workbook: FAIL" in out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "F-M08-013" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_push_is_allowed_once_every_verdict_is_pass(tmp_path):
    run, wb, *_ = scored_run(tmp_path)
    for scope in ("workbook", "report:research", "report:assessment", "scan"):
        L.append_gate(wb, gate="GS", scope=scope, verdict="FAIL", detail="earlier", blocking=True)
        L.append_gate(wb, gate="GS", scope=scope, verdict="PASS", detail="PASS — 0 findings", blocking=True)
    L.append_gate(wb, gate="TEMPLATE", scope="binding", verdict="PASS", detail="bound", blocking=True)
    out = _hook(_bash("PreToolUse", "python3 scripts/drive_fetch.py push-final --client Acme "
                                    "--file x.docx"), run)
    assert out == {}, "the latest verdict per scope decides, and every one is PASS"
    # a push that names no deliverable is not this hook's business
    out = _hook(_bash("PreToolUse", "python3 scripts/drive_fetch.py push-memory --client Acme"), run)
    assert out == {}


def test_the_stop_is_refused_once_at_package_while_a_verdict_fails(tmp_path):
    run, wb, *_ = scored_run(tmp_path)
    run.qa_dir.mkdir(parents=True, exist_ok=True)
    (run.qa_dir / "pipeline_state.json").write_text(json.dumps({"stage": "PACKAGE"}))
    L.append_gate(wb, gate="GS", scope="report:assessment", verdict="FAIL",
                  detail="1 finding(s): GS-RPT-NOTOKENS: leftover {{token}}", blocking=True)
    out = _hook({"hook_event_name": "Stop"}, run)
    assert out["decision"] == "block" and "GS:report:assessment: FAIL" in out["reason"]
    assert _hook({"hook_event_name": "Stop"}, run) == {}, "the same state twice may stop"
    assert _hook({"hook_event_name": "Stop", "stop_hook_active": True}, run) == {}
    L.append_gate(wb, gate="GS", scope="report:assessment", verdict="PASS",
                  detail="PASS — 0 findings", blocking=True)
    assert _hook({"hook_event_name": "Stop"}, run) == {}


def test_a_stop_away_from_package_is_not_this_hooks_business(tmp_path):
    run, wb, *_ = scored_run(tmp_path)
    L.append_gate(wb, gate="GS", scope="workbook", verdict="FAIL", detail="x", blocking=True)
    assert _hook({"hook_event_name": "Stop"}, run) == {}


def test_assemble_package_does_not_push_an_unverified_package(monkeypatch):
    src = (PLUGIN / "skills/dma-research/engine/assemble.py").read_text()
    body = src[src.index("def package("):src.index("def checkpoint(")]
    assert 'if push and not report["complete"]:' in body
    assert body.index('if push and not report["complete"]') < body.index("_push(dest, entity)")


def test_the_hook_is_wired_on_all_three_events():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    def bound(ev):
        return [e for e in hooks[ev] if any("deliverable_gate" in h["command"] for h in e["hooks"])]
    assert bound("PostToolUse")[0]["matcher"] == "Bash"
    assert bound("Stop")
    # PreToolUse on Bash runs through bash_guard.py (one process for every
    # Bash guard, F-H01-023), ahead of the approver it names last.
    src = (PLUGIN / "scripts" / "hooks" / "bash_guard.py").read_text()
    order = src[src.index("ORDER = ("):src.index("APPROVER =")]
    assert "deliverable_gate.py" in order
    pre = hooks["PreToolUse"]
    gate = next(i for i, e in enumerate(pre) if any("bash_guard" in h["command"] for h in e["hooks"]))
    approve = next(i for i, e in enumerate(pre) if any("autoapprove_builtins" in h["command"] for h in e["hooks"]))
    assert gate < approve, "a denial is decided before anything can approve"


def test_a_working_file_push_followed_by_a_shell_operator_is_still_exempt():
    """N-07 (2026-10-01, Northwest Bank): `--name preflight.json; echo …`
    captured `preflight.json;` and the step-3 preflight push was denied with
    'no run is in hand'. The exemption reads the token, not the operator."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("deliverable_gate", HOOK)
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    base = ("python3 scripts/drive_fetch.py push-package --client 'Acme' "
            "--file /r/acme/preflight.json --name preflight.json")
    for tail in ("", "; echo \"exit=$?\"", " && echo ok", "&& echo ok", "|| true",
                 ";echo done"):
        assert g.push_verdict(base + tail)[0] == "pass", tail
    # a deliverable riding the same shape is still judged
    assert g.push_verdict("python3 scripts/drive_fetch.py push-package --client 'Acme' "
                          "--file /r/wb.xlsx --name wb.xlsx; echo ok")[0] == "deny"
