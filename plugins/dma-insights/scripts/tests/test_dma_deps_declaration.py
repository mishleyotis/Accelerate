"""A dependency you declare must be one the documented fix can install.

Found in production, 2026-08-23: a session ran the install doctor, got a red
"skill script dependencies" row naming `pypdf`, ran the fix the row printed —
`scripts/dma-deps install` — and pypdf was still missing. It was declared in
`dma-deps` MODULES and absent from the `requirements.txt` that `install`
installs from, so the two halves of the same tool disagreed about what the
plugin needs and the documented remedy was a dead end. The session had to
`pip install pypdf` by hand and report the plugin as defective.

That is a whole class, not one package: MODULES and requirements.txt are two
hand-maintained lists of the same set, and nothing compared them. These tests
compare them, in both directions, plus the constraints files that pin them.

The directions are not symmetric in consequence:

  * MODULES ⊄ requirements  — `check` reports a gap `install` cannot close.
    This is the one that shipped.
  * requirements ⊄ MODULES  — the package installs and nothing checks it, so
    a missing import surfaces as a traceback inside a skill script rather
    than as a row in the doctor.
  * constraints ⊄ requirements — a pin that constrains nothing. Harmless
    until it is a typo of a name that does matter, which is invisible.
"""
import importlib.machinery
import importlib.util
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
PLUGIN = HERE.parent
REQS = PLUGIN / "requirements.txt"
CONSTRAINTS = sorted(PLUGIN.glob("constraints-py3*.txt"))

#: `dma-deps` has no .py suffix — it is invoked by path, because claude.ai
#: rejects a plugin that adds executables to PATH. Load it by loader rather
#: than re-implementing MODULES here, which would be the same duplication
#: this file exists to catch.
_spec = importlib.util.spec_from_loader(
    "dma_deps", importlib.machinery.SourceFileLoader(
        "dma_deps", str(HERE / "dma-deps")))
dma_deps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dma_deps)


def norm(name: str) -> str:
    """PEP 503 normalisation. `rank-bm25`, `rank_bm25` and `Rank.BM25` are
    one distribution, and a comparison that misses that reports a phantom
    gap — which is worse than no comparison, because it gets muted."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse(path: Path) -> dict:
    """distribution name -> the line it came from."""
    out = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~;\[]", line, 1)[0].strip()
        if name:
            out[norm(name)] = raw.strip()
    return out


DECLARED = {norm(pip): imp for imp, (pip, _) in dma_deps.MODULES.items()}
REQUIRED = parse(REQS)


# ── the defect that shipped ───────────────────────────────────────────────

@pytest.mark.parametrize("dist", sorted(DECLARED))
def test_every_declared_module_is_installable_by_the_documented_fix(dist):
    """`dma-deps check` names a module; `dma-deps install` must be able to
    supply it. `install` runs `pip install -r requirements.txt` and nothing
    else, so "in MODULES" and "in requirements.txt" have to be one set."""
    assert dist in REQUIRED, (
        f"{dist} is declared in dma-deps MODULES (import name "
        f"{DECLARED[dist]!r}) but is not in {REQS.name}. `dma-deps check` "
        f"reports it missing and `dma-deps install` cannot install it — the "
        f"fix the doctor prints does not work. Add it to {REQS.name}.")


@pytest.mark.parametrize("dist", sorted(REQUIRED))
def test_every_requirement_is_checked_by_the_doctor(dist):
    """The other direction. A requirement absent from MODULES installs
    silently and is never verified, so its absence surfaces as a traceback
    inside a skill script instead of a row in `dma-deps check`."""
    assert dist in DECLARED, (
        f"{dist} is required by {REQS.name} but is not declared in dma-deps "
        f"MODULES, so nothing checks whether it is importable. Add it to "
        f"MODULES with its import name and what it blocks.")


def test_the_two_lists_are_the_same_set():
    """Named separately from the parametrised pair so a whole-set drift
    reads as one failure rather than N."""
    assert set(DECLARED) == set(REQUIRED), (
        f"only in MODULES: {sorted(set(DECLARED) - set(REQUIRED))}\n"
        f"only in requirements.txt: {sorted(set(REQUIRED) - set(DECLARED))}")


def test_pypdf_specifically():
    """The instance that reached a user. Pinned by name because
    corpus_search imports pypdf and NOT pdfplumber, and the two are easy to
    conflate — a reader who sees pdfplumber in requirements concludes PDFs
    are covered. Without pypdf every PDF in a package reports "no extractor
    for this type", the reports never enter the corpus index, and a producer
    is sent to the web for a document the package already holds."""
    assert "pypdf" in REQUIRED, "corpus_search's PDF path needs pypdf"
    assert "pypdf" in DECLARED, "and dma-deps check must verify it"


# ── the pins ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", CONSTRAINTS, ids=lambda p: p.name)
def test_constraints_pin_only_things_that_are_required(path):
    """A constraint on a package no requirement mentions is inert. That is
    fine right up until the name is a typo of one that matters, and then it
    is an unpinned dependency that looks pinned."""
    extra = sorted(set(parse(path)) - set(REQUIRED))
    assert not extra, (
        f"{path.name} pins {extra}, which {REQS.name} does not require — "
        f"the pin does nothing. Either require it or drop the pin.")


def test_the_measured_interpreter_is_fully_pinned():
    """constraints-py311.txt documents itself as "the measured working set".
    A requirement missing from it is not measured, whatever the header says —
    and the reader cannot tell which."""
    py311 = PLUGIN / "constraints-py311.txt"
    missing = sorted(set(REQUIRED) - set(parse(py311)))
    assert not missing, (
        f"{py311.name} calls itself the measured working set but does not "
        f"pin {missing}. Pin the version actually measured, or stop calling "
        f"the file complete.")


def test_constraints_are_exact_pins():
    """`-c` with a range is a constraint that permits drift; the whole point
    of these files is that the resolution is reproducible."""
    for path in CONSTRAINTS:
        for dist, line in parse(path).items():
            assert "==" in line, (
                f"{path.name}: {line!r} is not an exact pin")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
