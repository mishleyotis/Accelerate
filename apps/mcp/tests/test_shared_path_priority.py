"""The tracked copy wins over the staged one, in both loaders.

A build artefact shadowing its own source does not announce itself: the file
is there, it parses, and it is merely old. Measured TWICE on 2026-08-19, once
in each of the two services that resolve `packages/shared`:

  · the api's loader answered a rule from a stale `abbreviations.py` that a
    deploy had written an hour earlier, against a tracked file that plainly
    had it;
  · the connector's loader then did it again with `platform_fit.py`, failing
    a test with "Candidate.__init__() got an unexpected keyword argument
    'relevance'" against a file that declares `relevance` on line 195.

Both had the same two bugs. `insert(0, ...)` over a list in priority order
puts the LAST candidate first, and skipping a candidate "already on the path"
ignores WHERE on the path it is — a caller that put the repo root on first was
overtaken anyway.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp import shared_path  # noqa: E402


def test_the_repo_root_is_the_first_candidate():
    here = ROOT / "apps" / "mcp" / "dma_mcp" / "shared_path.py"
    got = [str(p) for p in shared_path.roots(str(here))]
    assert got[0].endswith("packages/shared"), got


def test_the_image_layout_is_still_reachable():
    """In the image there is no repo copy and the staged directory beside the
    package is the only answer. Dropping it would take every service down."""
    here = ROOT / "apps" / "mcp" / "dma_mcp" / "shared_path.py"
    got = [str(p) for p in shared_path.roots(str(here))]
    assert any(p.endswith("dma_mcp/shared") for p in got), got
    assert any(p.endswith("apps/mcp/shared") for p in got), got


def test_a_path_already_present_is_moved_rather_than_left_where_it_was():
    """The half that made the first fix insufficient."""
    repo = str(ROOT / "packages" / "shared")
    staged = str(ROOT / "apps" / "mcp" / "shared")
    if not Path(staged).exists():                       # nothing staged here
        return
    for p in (repo, staged):
        while p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, repo)          # repo on first...
    sys.path.insert(0, staged)        # ...then overtaken, as a deploy leaves it
    shared_path.ensure(str(ROOT / "apps" / "mcp" / "dma_mcp" / "shared_path.py"))
    assert sys.path.index(repo) < sys.path.index(staged)


def test_the_tracked_engine_is_the_one_that_answers():
    import platform_fit
    assert "packages/shared" in platform_fit.__file__, (
        f"the fit engine resolved from {platform_fit.__file__} — a staged "
        "build artefact is shadowing the tracked source")
