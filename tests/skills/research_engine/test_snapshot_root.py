"""A restored run lands where it was snapshotted from.

Measured 2026-10-05 (Susser Bank): the snapshot was restored to the default
root, while its briefs, research handoff and workflow invocations all named
/home/user/dma-runs/susser-bank as an absolute path. Nothing failed loudly;
every later lane would have read a directory that did not exist.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from engine import snapshot as S


def _run_tree(root: Path) -> None:
    (root / "07_qa").mkdir(parents=True)
    (root / "07_qa" / "research_workflow.json").write_text(
        json.dumps({"invocations": [{"root": str(root)}]}))
    (root / "wb.xlsx").write_text("x")


def test_the_snapshot_records_its_root(tmp_path):
    root = tmp_path / "runs" / "acme"
    _run_tree(root)
    assert S.recorded_root(S.build(root)) == str(root.resolve())


def _fake_pull(blob):
    def run(cmd, **kw):
        dest = Path(cmd[cmd.index("--dest") + 1])
        (dest / S.name_for("r1")).write_bytes(blob)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return run


def test_restore_defaults_to_the_recorded_root_and_refuses_another(tmp_path, monkeypatch):
    root = tmp_path / "runs" / "acme"
    _run_tree(root)
    blob = S.build(root)
    for p in sorted(root.rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    monkeypatch.setattr(S.subprocess, "run", _fake_pull(blob))
    wrong = S.restore("r1", tmp_path / "elsewhere", "Acme")
    assert wrong["outcome"] == "REFUSED" and wrong["recorded_root"] == str(root.resolve())
    assert not (tmp_path / "elsewhere").exists()
    ok = S.restore("r1", None, "Acme")
    assert ok["outcome"] == "RESOLVED" and Path(ok["root"]) == root.resolve()
    assert (root / "07_qa" / "research_workflow.json").is_file()
    moved = S.restore("r1", tmp_path / "elsewhere", "Acme", relocate=True)
    assert moved["outcome"] == "RESOLVED"
