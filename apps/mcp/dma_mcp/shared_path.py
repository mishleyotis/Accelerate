"""Find `packages/shared` from inside whichever image is running.

The repo layout is optional; the IMAGE layout is not. A container copies the
shared files in beside the package (`…/dma_mcp/shared/`) or one level up
(`…/shared/`), and only a developer's checkout has `packages/shared` three
directories above. A bare `from x import y` finds whichever appears on
`sys.path` first, which is how the api died once and the mcp container twice.

Extracted from `gaps.py`, which wrote this inline and then had to be trusted
not to drift when a second module needed the same three candidate roots.
"""
from __future__ import annotations

import sys
from pathlib import Path


def roots(module_file: str) -> list[Path]:
    """Highest priority first: the tracked source, then the staged copies."""
    here = Path(module_file).resolve()
    out = []
    if len(here.parents) > 3:
        out.append(here.parents[3] / "packages" / "shared")
    out += [here.parent / "shared", here.parent.parent / "shared"]
    return out


def ensure(module_file: str) -> None:
    """Lay the existing candidate roots on `sys.path` in PRIORITY order.

    THE REPO COPY WINS WHERE THERE IS ONE. In the image there is no repo copy,
    so the staged one is the only answer and nothing changes; in a checkout
    the staged directory is a gitignored artefact that deploy.sh wrote, and it
    can be an old copy of a file a human has since fixed.

    Measured 2026-08-19, twice. The api's loader had this backwards and a
    stale `abbreviations.py` answered a rule the tracked file plainly had.
    Then this one did it again with `platform_fit.py`: a test failed with
    "Candidate.__init__() got an unexpected keyword argument 'relevance'"
    against a file that declares `relevance` on line 195.

    Two mistakes, one shape. `insert(0, ...)` in order puts the LAST candidate
    first, and "already on the path" is not the same as "on the path in the
    right order" — a caller that had put the repo root on first was overtaken
    by the staged one anyway. So: drop every occurrence, then lay them down.
    """
    wanted = [str(c) for c in roots(module_file) if c.exists()]
    for path in wanted:
        while path in sys.path:
            sys.path.remove(path)
    for path in reversed(wanted):
        sys.path.insert(0, path)
