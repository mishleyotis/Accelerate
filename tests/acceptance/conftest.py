"""The acceptance suite runs the SHIPPED engine against the OWNER'S OWN
complaints, one test per sentence they wrote.

REPORTED 2026-09-03: "Most of the above has not been done or stress tested.
In fact, I do not see how the agents have been orchestrated to ensure that
all the above works harmoniously. The above does not even have acceptance
tests."

That is a fair reading of what a unit suite proves. `tests/skills/
research_engine` proves each refusal in isolation; it cannot show that the
eight complaints are answered TOGETHER by one run walking the real path. So
these tests are written from the complaints rather than from the modules:
each one names the reported failure, reproduces the shape that produced it,
and asserts the engine now refuses it — and then asserts the corrected
shape passes, because a gate that nothing can pass is a wall, not a gate.

They import the same fixtures the unit suite uses, deliberately: a second
set of fixtures is a second definition of "a real run", and the two drift.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
_SKILL = _ROOT / "plugins" / "dma-insights" / "skills" / "dma-research"
_UNIT = _ROOT / "tests" / "skills" / "research_engine"
for _p in (str(_SKILL), str(_UNIT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
