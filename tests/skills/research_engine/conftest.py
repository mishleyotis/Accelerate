"""Make the in-plugin research engine importable from the repo's test run.

The engine ships inside the plugin so a trigger-fired container that has the
plugin and no checkout can still run it. The repo's CI has the checkout and
not the install, so the path is added here rather than in each test file."""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
_SKILL = _REPO / "plugins" / "dma-insights" / "skills" / "dma-research"
# The app's worker package too (`job_main`, `dma_worker`): the tests that
# prove the engine's output reaches the app import it. Six test files used
# to insert it themselves with THIS CONTAINER'S absolute path, which passed
# only while a file with the repo-relative path imported first in the same
# pytest process; the W3 shard reshuffle (28-09-2026) put two of them in a
# process where nothing did, and CI failed with ModuleNotFoundError on
# /home/runner. The path has one owner now, and it is relative.
_WORKER = _REPO / "apps" / "worker"
for _p in (str(_WORKER), str(_SKILL), str(_HERE)):
    # _HERE too: `fixtures.py` sits beside the tests, and importlib mode
    # gives each test file its own module identity from its path rather than
    # putting its directory on sys.path.
    if _p not in sys.path:
        sys.path.insert(0, _p)
