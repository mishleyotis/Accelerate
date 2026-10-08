"""A section file is pass-1 checked the moment it is written (PostToolUse),
so a CG-04/AG-01-class refusal reaches the producer before the next file,
not after a ship."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "dma-insights"
HOOK = PLUGIN / "scripts" / "hooks" / "section_precheck.py"


def _mod():
    spec = importlib.util.spec_from_file_location("section_precheck", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run_hook(path: Path) -> dict:
    env = {"PATH": "/usr/bin:/bin", "DMA_REPO_ROOT": str(REPO)}
    proc = subprocess.run([sys.executable, str(HOOK)],
                          input=json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Write",
                                            "tool_input": {"file_path": str(path)}}),
                          capture_output=True, text=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def test_an_undeclared_section_key_is_named_at_write_time(tmp_path):
    sections = tmp_path / "run" / "08_sections"
    sections.mkdir(parents=True)
    f = sections / "heatmap.cohort_patterns.json"
    f.write_text(json.dumps({"produced_at": "2026-10-07T00:00:00Z", "producer_version": "t@1",
                             "e_ids": [], "internal_only": [], "narrative_thread": "x",
                             "patterns": [{"pattern_id": "cp-1", "r_layer": {"verdict": "WITHDRAWN"}}],
                             "sources_searched": ["an undeclared key"]}))
    out = _run_hook(f)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "heatmap.cohort_patterns" in ctx and "AG-01" in ctx and "WITHDRAWN" in ctx


def test_a_file_outside_a_sections_dir_or_not_a_section_is_ignored(tmp_path):
    m = _mod()
    other = tmp_path / "notes.json"
    other.write_text("{}")
    assert m.section_reasons(other, str(REPO)) is None
    (tmp_path / "08_sections").mkdir()
    stray = tmp_path / "08_sections" / "readme.json"
    stray.write_text("{}")
    assert m.section_reasons(stray, str(REPO)) is None
    assert _run_hook(other) == {}


def test_the_hook_never_blocks_and_says_so_when_the_gates_cannot_run(tmp_path):
    m = _mod()
    sections = tmp_path / "08_sections"
    sections.mkdir()
    f = sections / "overview.hero.json"
    f.write_text("{not json")
    out = m.section_reasons(f, str(REPO))
    assert out and out.get("not_run", "").startswith("assemble")
    assert "did not run" in m.render(out)
    bad = m.section_reasons(f, str(tmp_path))      # a root with no connector
    assert bad and bad.get("not_run")


def test_the_hook_is_registered_for_writes():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    entries = [e for e in hooks["hooks"]["PostToolUse"]
               if any("section_precheck.py" in h["command"] for h in e["hooks"])]
    assert entries and "Write" in entries[0]["matcher"] and "Edit" in entries[0]["matcher"]
