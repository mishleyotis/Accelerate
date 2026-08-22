"""No module may compute a repo-layout path that cannot exist in its image.

THE DEFECT, three times, by me, in three files.

Every deployable image copies its package to `/app/<pkg>/`, so a module there is
`/app/<pkg>/<name>.py` and has exactly THREE parents: `/app/<pkg>`, `/app`, `/`.
`Path(__file__).resolve().parents[3]` raises IndexError. In the repo the same
module is four or five deep, so it resolves fine and every test passes.

  1  apps/api/dma_api/computed.py — the api served every computed section with
     `computed_error: IndexError` and no enrichment_status anywhere.
  2  apps/mcp/dma_mcp/gaps.py — deploy 8's mcp container died on its startup
     probe. I diagnosed it as a missing COPY, fixed that, and redeployed.
  3  the same file again — deploy 9 died identically, because the missing COPY
     was real but was not the whole cause. The traceback named parents[3].

And apps/worker/dma_worker/enrichment.py carried it too, unshipped, so the
enrichment job would have died the same way on its first scheduled run.

TWO THINGS MAKE IT BITE, and a fix needs both:

  * the INDEX is too deep for the image layout, and
  * the candidate list is built EAGERLY — a tuple literal evaluates every entry
    before the loop body runs, so the IndexError fires before the image path,
    which is listed FIRST and exists, is ever tried.

A test pinned to one file cannot catch the next file. This one scans every
module in every deployable, which is why it is here in scripts/tests rather
than beside any one of them.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The trees that become container images. `/app/<pkg>/<mod>.py` is the deepest
# any of them places a module, hence three parents.
DEPLOYABLE_PACKAGES = [
    "apps/api/dma_api", "apps/mcp/dma_mcp", "apps/worker/dma_worker",
    "packages/shared",
]
MAX_PARENTS_IN_IMAGE = 3

PARENTS = re.compile(r"\.parents\[(\d+)\]")


def _modules():
    for d in DEPLOYABLE_PACKAGES:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts or "test" in p.name:
                continue
            yield p


def test_no_module_indexes_parents_beyond_the_image_depth_unguarded():
    """A `parents[N]` with N >= 3 must be reachable only behind a length check.

    Not banned outright: reading the repo root is legitimate for a module that
    ALSO has an image path, which is the whole pattern here. What is banned is
    reaching for it without first asking whether it exists.
    """
    offenders = []
    for path in _modules():
        text = path.read_text(encoding="utf-8", errors="replace")
        if not PARENTS.search(text):
            continue
        guarded = ("len(" in text and "parents" in text) or "_shared_roots" in text
        for m in PARENTS.finditer(text):
            if int(m.group(1)) < MAX_PARENTS_IN_IMAGE:
                continue
            line = text.count("\n", 0, m.start()) + 1
            if not guarded:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{line} uses parents[{m.group(1)}] "
                    "with no length guard; in the image the module is three "
                    "deep and this raises IndexError at import")
    assert not offenders, (
        "modules that would raise IndexError in their own container:\n  "
        + "\n  ".join(offenders))


def test_candidate_roots_are_not_built_eagerly():
    """The second half, and the one that made the fix non-obvious.

    `for c in (a_that_works, b_that_raises):` raises before the loop body ever
    sees `a`. So a module can list its IMAGE path first, correctly, and still
    die on the repo path it would never have needed. Any module iterating a
    literal tuple/list of candidate roots must build them in a function
    instead.
    """
    bad = []
    for path in _modules():
        text = path.read_text(encoding="utf-8", errors="replace")
        # `for <var> in (` … `parents[` … `)` on one logical statement
        for m in re.finditer(r"for\s+\w+\s+in\s*\((?:[^()]|\([^()]*\))*?\)",
                             text, re.S):
            if "parents[" in m.group(0):
                line = text.count("\n", 0, m.start()) + 1
                bad.append(f"{path.relative_to(ROOT)}:{line}")
    assert not bad, (
        "candidate roots built eagerly in a tuple — the entry that raises is "
        "evaluated before the entry that works:\n  " + "\n  ".join(bad))


def test_every_shared_importer_finds_the_module_at_image_depth():
    """Simulate the image layout and prove the resolver still yields a usable
    first candidate. The unit tests for these modules all pass in the repo,
    where the module is deep enough — which is precisely why none of them
    caught any of the three occurrences."""
    import sys

    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    sys.path.insert(0, str(ROOT / "apps" / "worker"))
    from dma_mcp import gaps
    from dma_worker import enrichment

    for mod, pkg in ((gaps, "dma_mcp"), (enrichment, "dma_worker")):
        fn = getattr(mod, "_shared_roots", None)
        assert fn, f"{pkg} has no _shared_roots(); the lazy builder is the fix"
        real = mod.__file__
        try:
            mod.__file__ = f"/app/{pkg}/{Path(real).name}"
            roots = [str(r) for r in fn()]
            assert roots, f"{pkg} yields no candidate roots at image depth"
            assert roots[0] == "/app/shared" or "/app/shared" in roots, (
                f"{pkg} does not look beside the package in the image: {roots}")
        finally:
            mod.__file__ = real
