"""Partial-date resolution — the engine's copy of the app's rule.

The page contract (H7) says a quarter IS a date: "'2025-Q4' IS a date.
Resolve to the quarter end for age and render the quarter as given."
Measured 28-09-2026 (QA audit F-L11-031): `ledger.recency_band('2025-Q4')`
returned UNVERIFIED, because the ledger parsed ISO dates only — so a
quarter-dated filing, which the prompts deliberately accept, banded as
undated in the workbook while the app banded it as CURRENT.

ONE rule, in two places by necessity: the engine ships inside the plugin
and cannot import `apps/mcp/dma_mcp/dates.py`, so this file mirrors it —
a month resolves to its first day, a quarter to its END, a bare year to 1
January, an ISO instant to its date part — and
`tests/skills/research_engine/test_recency_partial_dates.py` holds the two
equal on one case table. Change one, and that test names the other.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_QUARTER = re.compile(r"^(\d{4})-?Q([1-4])$", re.I)
_YEAR = re.compile(r"^(\d{4})$")
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}

ACCEPTED = "YYYY-MM-DD · YYYY-MM · YYYY-Qn · YYYY · an ISO-8601 instant"


def resolve(value):
    """A `date` for any accepted shape, None for an empty value, or `False`
    when the value cannot be resolved — never a sentinel date."""
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return False
    v = value.strip()
    m = _ISO.match(v)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return False
    m = _MONTH.match(v)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return False
    m = _QUARTER.match(v)
    if m:
        mo, day = _QUARTER_END[int(m.group(2))]
        return date(int(m.group(1)), mo, day)
    m = _YEAR.match(v)
    if m:
        return date(int(m.group(1)), 1, 1)
    return False
