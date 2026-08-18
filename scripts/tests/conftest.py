"""Make `scripts/` importable so `python3 -m pytest scripts` works from the
repo root without a package or an installed distribution."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
