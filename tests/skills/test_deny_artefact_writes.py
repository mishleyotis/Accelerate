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


def test_reading_a_retired_writer_is_allowed():
    """Measured 2026-09-04: the rule matched the bare filename, so `sed -n`
    and `grep` on the retired script were denied — the guard blocked reading
    the very file whose refusal it enforces. Only RUNNING one is denied."""
    for cmd in ("sed -n '1,40p' plugins/dma-insights/skills/dma-assessment/scripts/assessment_runner.py",
                "grep -n 'import' skills/dma-research/scripts/populate_workbook.py",
                "cat skills/dma-research/scripts/validate_workbook.py",
                "git log --oneline -- skills/dma-research/scripts/populate_workbook.py"):
        assert _bash(cmd) == {}, cmd
    for cmd in ("python3 skills/dma-research/scripts/validate_workbook.py wb.xlsx",
                "python plugins/dma-insights/skills/dma-assessment/scripts/assessment_runner.py --corpus c",
                "./skills/dma-research/scripts/populate_workbook.py a b"):
        out = _bash(cmd)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny", cmd
        assert "retired writer" in out["hookSpecificOutput"]["permissionDecisionReason"]


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


# ── the one engine command that destroys something ───────────────────────

def _memory_cleanup(cmd: str, status: dict, monkeypatch, tmp_path) -> str | None:
    """`decide` on a cleanup command, with the engine's status stubbed."""
    m = _mod()
    run = tmp_path / "run-memory"
    (run / "07_qa").mkdir(parents=True, exist_ok=True)
    (run / f"DMA_Scoring_Workbook_{run.name}.xlsx").write_bytes(b"stub")
    monkeypatch.setenv("DMA_RUN_ID", run.name)
    monkeypatch.setenv("DMA_RUN_ROOT", str(run))
    import sys as _sys
    _sys.path.insert(0, str(PLUGIN / "scripts" / "hooks"))
    import _runctx as ctx
    memory, = ctx.engine("memory")
    monkeypatch.setattr(memory, "status", lambda r, c=None: status)
    return m.decide({"tool_name": "Bash", "tool_input": {"command": cmd}})


CLEANUP = ("python3 -m engine.memory cleanup --run R --root /runs/R --apply")


def test_cleanup_apply_is_denied_while_a_note_is_unconsolidated(monkeypatch, tmp_path):
    why = _memory_cleanup(CLEANUP, {"unconsolidated": 3, "blocked": 0},
                          monkeypatch, tmp_path)
    assert why and "deletes the Drive backup" in why
    assert "still NOTED" in why
    assert "engine.memory consolidate" in why


def test_cleanup_apply_is_denied_while_an_entry_is_blocked(monkeypatch, tmp_path):
    why = _memory_cleanup(CLEANUP, {"unconsolidated": 0, "blocked": 2},
                          monkeypatch, tmp_path)
    assert why and "BLOCKED" in why


def test_cleanup_apply_is_allowed_once_everything_is_consolidated(monkeypatch, tmp_path):
    assert _memory_cleanup(CLEANUP, {"unconsolidated": 0, "blocked": 0},
                           monkeypatch, tmp_path) is None


def test_the_dry_run_and_the_status_are_never_denied(monkeypatch, tmp_path):
    """`cleanup` without --apply is how a session learns whether the
    conditions are met; denying it would deny the diagnosis."""
    for cmd in ("python3 -m engine.memory cleanup --run R --root /runs/R",
                "python3 -m engine.memory status --run R --root /runs/R"):
        assert _memory_cleanup(cmd, {"unconsolidated": 9, "blocked": 9},
                               monkeypatch, tmp_path) is None, cmd


def test_a_status_that_cannot_be_read_allows_the_call(monkeypatch, tmp_path):
    """Fail OPEN: the engine refuses this on its own, and a guard that denies
    because it could not measure is a guard that stops the work."""
    m = _mod()
    monkeypatch.setenv("DMA_RUN_ROOT", str(tmp_path / "no-run-here"))
    monkeypatch.delenv("DMA_RUN_ID", raising=False)
    assert m.decide({"tool_name": "Bash", "tool_input": {"command": CLEANUP}}) is None
