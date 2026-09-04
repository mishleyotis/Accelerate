"""The deliverables have one writer, and the hook makes that mechanical.

Measured 2026-09-03: no PreToolUse hook denied
`openpyxl.Workbook().save("DMA_Scoring_Workbook_x.xlsx")`, so every gate the
engine carries could be walked around with one inline python — the goeasy
root cause ("the work went around the pipeline"). These pin the guard:
deny the out-of-engine write, allow the engine, the suites and reads, and
fail OPEN on malformed input like every sibling hook.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "dma-insights"
HOOK = PLUGIN / "scripts" / "hooks" / "deny_artefact_writes.py"


def _mod():
    spec = importlib.util.spec_from_file_location("deny_artefact_writes", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(payload) -> dict:
    p = subprocess.run([sys.executable, str(HOOK)], input=payload,
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else {}


def _bash(cmd: str) -> dict:
    return _run(json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))


def test_a_direct_xlsx_write_is_denied():
    out = _run(json.dumps({"tool_name": "Write",
                           "tool_input": {"file_path": "/root/dma_output/R/DMA_Scoring_Workbook_x.xlsx",
                                          "content": "..."}}))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "engine.cli evidence" in out["hookSpecificOutput"]["permissionDecisionReason"]
    out = _run(json.dumps({"tool_name": "Edit",
                           "tool_input": {"file_path": "/x/Client_Profile_Research_a.docx"}}))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_an_inline_openpyxl_save_is_denied():
    out = _bash("python3 -c \"from openpyxl import Workbook; wb=Workbook(); "
                "wb.save('DMA_Scoring_Workbook_x.xlsx')\"")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    out = _bash("python3 -c \"import docx; d=docx.Document(); "
                "d.save('09_deliverables/DMA_Assessment_Report_x.docx')\"")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    out = _bash("python3 skills/dma-research/scripts/populate_workbook.py idx.json dq.json --entity X --subvertical CU")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "retired writer" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_an_engine_command_is_allowed():
    for cmd in (
        "cd plugins/dma-insights/skills/dma-research && python3 -m engine.cli evidence --run R --subcap P1C1.1.1 --source s --url https://x --tier T2 --excerpt '...'",
        "python3 -m engine.cli report --run R --root ROOT",
        "python3 -m engine.assessment score --run R --subcap P1C1.1.1 --score 2.5",
        "python3 -m pytest tests/skills -q",
        "python3 plugins/dma-insights/scripts/stress_run_lifecycle.py",
        "python3 -m engine.gold_standard workbook DMA_Scoring_Workbook_x.xlsx",
        "ls 09_deliverables/*.docx",
        "python3 -c \"import openpyxl; wb=openpyxl.load_workbook('DMA_Scoring_Workbook_x.xlsx', read_only=True); print(wb.sheetnames)\"",
    ):
        assert _bash(cmd) == {}, cmd


def test_a_scratch_file_that_is_not_a_deliverable_is_allowed():
    assert _run(json.dumps({"tool_name": "Write",
                            "tool_input": {"file_path": "/tmp/notes.md", "content": "x"}})) == {}
    assert _bash("python3 -c \"print('hello')\"") == {}


def test_malformed_input_fails_open():
    assert _run("not json at all") == {}
    assert _run(json.dumps([1, 2, 3])) == {}
    assert _run(json.dumps({"tool_name": "Bash", "tool_input": {"command": 42}})) == {}
    assert _run(json.dumps({"tool_name": "Bash"})) == {}


def test_the_hook_is_registered_for_both_tool_families():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    pre = hooks["hooks"]["PreToolUse"]
    matchers = {spec.get("matcher") for spec in pre
                if any("deny_artefact_writes.py" in h["command"] for h in spec["hooks"])}
    assert "Bash" in matchers
    assert "Write|Edit|MultiEdit|NotebookEdit" in matchers
    m = _mod()
    assert m.decide({"tool_name": "Bash", "tool_input": {"command": "cat x"}}) is None
