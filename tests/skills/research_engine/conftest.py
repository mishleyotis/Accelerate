"""Make the in-plugin research engine importable from the repo's test run.

The engine ships inside the plugin so a trigger-fired container that has the
plugin and no checkout can still run it. The repo's CI has the checkout and
not the install, so the path is added here rather than in each test file."""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL = _HERE.parents[2] / "plugins" / "dma-insights" / "skills" / "dma-research"
for _p in (str(_SKILL), str(_HERE)):
    # _HERE too: `fixtures.py` sits beside the tests, and importlib mode
    # gives each test file its own module identity from its path rather than
    # putting its directory on sys.path.
    if _p not in sys.path:
        sys.path.insert(0, _p)
