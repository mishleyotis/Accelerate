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
    here = Path(module_file).resolve()
    out = [here.parent / "shared", here.parent.parent / "shared"]
    if len(here.parents) > 3:
        out.append(here.parents[3] / "packages" / "shared")
    return out


def ensure(module_file: str) -> None:
    """Put every existing candidate root on `sys.path`, image layout first."""
    for cand in roots(module_file):
        if cand.exists() and str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
