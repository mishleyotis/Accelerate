"""The retired workbook writers refuse and point at the engine.

`skills/dma-research/scripts/populate_workbook.py` built a second, 10-sheet
workbook from a JSON plane; `skills/dma-assessment/scripts/assessment_runner.py`
built a fresh openpyxl.Workbook() with an 11-column layout — and both skills'
SKILL.md still told an agent to run them (measured 2026-09-03). That is the
"workbook defaults to the wrong structure every run" defect. The files stay so
an old reference fails LOUD, naming the engine, rather than silently.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "dma-insights"


def _run(script: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, timeout=60)


def test_populate_workbook_refuses_and_names_the_engine(tmp_path):
    r = _run(PLUGIN / "skills" / "dma-research" / "scripts" / "populate_workbook.py",
             str(tmp_path / "idx.json"), str(tmp_path / "dq.json"),
             "--entity", "X", "--subvertical", "CU")
    assert r.returncode == 1
    assert "REFUSED" in r.stderr and "engine.cli start" in r.stderr
    assert "ONE writer" in r.stderr
    assert not list(tmp_path.glob("*.xlsx"))


def test_assessment_runner_refuses_and_names_the_engine(tmp_path):
    r = _run(PLUGIN / "skills" / "dma-assessment" / "scripts" / "assessment_runner.py",
             "--corpus", "c", "--index-dir", "i", "--pillar-dir", "p",
             "--institution", "X", "--sub-vertical", "CU", "--size-tier", "T1",
             "--out-dir", str(tmp_path))
    assert r.returncode == 1
    assert "REFUSED" in r.stderr and "engine.assessment score" in r.stderr
    assert not list(tmp_path.glob("*.xlsx"))


def test_validate_workbook_refuses_and_names_the_engine(tmp_path):
    """The legacy validator judged the 22-column layout: it FAILS the
    engine's real workbook and PASSES the retired populate_workbook's — so a
    skill that ran it would be told the wrong workbook was the right one."""
    r = _run(PLUGIN / "skills" / "dma-research" / "scripts" / "validate_workbook.py",
             str(tmp_path / "x.xlsx"))
    assert r.returncode == 1
    assert "REFUSED" in r.stderr and "engine.cli validate" in r.stderr


def test_the_audit_script_flags_a_skill_that_names_a_retired_writer(tmp_path):
    """`audit_skills.py` is the CI-side half: the same rule, run on every
    SKILL.md, with an exit code."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_skills", PLUGIN / "scripts" / "audit_skills.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.retired_writers_audit(str(PLUGIN / "skills")) == []
    bad = tmp_path / "bad-skill"; bad.mkdir()
    (bad / "SKILL.md").write_text(
        "6. run `scripts/populate_workbook.py` to build the workbook\n"
        "7. `scripts/validate_workbook.py` is retired; use engine.cli validate\n")
    hits = m.retired_writers_audit(str(tmp_path))
    assert [h["line"] for h in hits] == [1]


def test_no_skill_tells_an_agent_to_run_a_retired_writer():
    """The prose half: a SKILL.md that names a retired writer as a step is
    an instruction to go around the pipeline."""
    offenders = []
    for skill in (PLUGIN / "skills").glob("*/SKILL.md"):
        text = skill.read_text()
        for line in text.splitlines():
            if any(w in line for w in ("populate_workbook.py", "validate_workbook.py",
                                       "assessment_runner.py")) \
                    and "retired" not in line.lower() and "refuse" not in line.lower():
                offenders.append(f"{skill.parent.name}: {line.strip()[:100]}")
    assert offenders == [], offenders
