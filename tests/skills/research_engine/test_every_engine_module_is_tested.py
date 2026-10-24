"""Every engine module is imported by at least one test.

The audit's engine census (28-09-2026) found 42 modules and one — `rubric`
— that no test imported. Regression seed 6 is exactly that shape: a green
suite over a minority of modules hiding a crash on the untested path. This
row fails naming the module the moment coverage drops, so the gap cannot
reopen silently.

Matching is on IMPORT FORMS, not on the bare word: `test_gold_standard.py`
says "rubric" in prose, which is not a test of the module.
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ENGINE = REPO / "plugins" / "dma-insights" / "skills" / "dma-research" / "engine"
TEST_DIRS = (HERE, REPO / "plugins" / "dma-insights" / "scripts" / "tests")

#: Modules that are not units of the engine: the package marker, and the
#: chaos stub that `scripts/stress_pipeline_stub.py` drives instead of a
#: test file.
EXEMPT = {"__init__", "pipeline_stub"}


def _modules():
    return sorted(p.stem for p in ENGINE.glob("*.py") if p.stem not in EXEMPT)


def _corpus():
    out = []
    for d in TEST_DIRS:
        for p in d.rglob("*.py"):
            if p.name != Path(__file__).name:
                out.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(out)


def _imported(mod: str, corpus: str) -> bool:
    forms = (
        rf"from engine import [^\n]*\b{mod}\b",
        rf"from engine\.{mod} import",
        rf"import engine\.{mod}\b",
        rf"\bengine\.{mod}\b",
        rf"engine\(\s*[\"']{mod}[\"']\s*\)",
        rf"-m\s+engine\.{mod}\b",
    )
    return any(re.search(f, corpus) for f in forms)


def test_every_engine_module_is_imported_by_some_test():
    corpus = _corpus()
    untested = [m for m in _modules() if not _imported(m, corpus)]
    assert not untested, (
        f"engine modules no test imports: {untested} — add a test file that "
        f"imports each (regression seed 6: the untested path is where the "
        f"crash hides)")
