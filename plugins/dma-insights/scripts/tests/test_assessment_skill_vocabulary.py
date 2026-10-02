"""The assessment skill runs on the engine's state, not a checkpoint plane.

Measured 28-09-2026 (prompt-craft scorecard row 3, 3/10): the skill's
operating procedure described `$DMA_ROOT/checkpoints/00…06_*.json`, a
scoring scratchpad "converted to an XLSX with ALL 11 sheets" and seven
checkpoint templates nothing read — beside a first rule that the skill
BUILDS NO WORKBOOK. Rewritten 29-09-2026: the workbook is the state,
`engine.assessment state` is the resume, the run tree is
`engine.runstate.SUBDIRS`.
"""
import re
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
ASSESS = PLUGIN / "skills" / "dma-assessment"
sys.path.insert(0, str(PLUGIN / "skills" / "dma-research"))
from engine import contract as C, runstate  # noqa: E402

STALE = re.compile(r"\$DMA_ROOT/checkpoints|\{DMA_ROOT\}/checkpoints|0[0-6]_[a-z_]+\.json|"
                   r"scoring_scratchpad|JSON → XLSX|ALL 11 sheets|/home/claude/")


def _docs():
    return [ASSESS / "SKILL.md"] + sorted((ASSESS / "references").glob("*.md"))


def test_no_checkpoint_plane_survives_in_the_skill_or_its_references():
    hits = []
    for f in _docs():
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if STALE.search(line) and "retired" not in line.lower() and "rewritten" not in line.lower():
                hits.append(f"{f.name}:{n}: {line.strip()[:90]}")
    assert hits == [], hits


def test_the_checkpoint_templates_are_gone():
    left = sorted(p.name for p in (ASSESS / "templates").glob("*_template.json"))
    assert left == [], left
    assert not (ASSESS / "templates" / "evidence_index.md").exists()


def test_the_operating_procedure_names_the_engines_state_and_tree():
    op = (ASSESS / "references" / "operating_procedure.md").read_text(encoding="utf-8")
    assert "engine.assessment state" in op and "07_qa/scoring.json" in op
    assert f"{len(C.SHEETS)} sheets" in op
    for d in runstate.SUBDIRS:
        assert f"`{d}`" in op, d
    assert "engine.brief scoring-batch" in op
