"""Partial-date resolution for payload fields promoted into DATE columns.

The prompts deliberately accept month and quarter precision ("dated to at
least the month"; "2025-Q4 IS a date"), while the serving tier stores a
DATE. One resolver does the conversion for both the submit-time check and
the promote-time write, with the SAME rule the ingest tier already uses:
a month resolves to its first day, a quarter to its END (the ingest's H7
rule), a bare year to 1 January, and an ISO instant to its date part.

A value this cannot resolve is rejected at submit with the shapes named —
never coerced to a sentinel, and never left to abort the promote.
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
    """A date for any accepted shape, None for an empty value, or the
    string ... sentinel `False` when the value cannot be resolved."""
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
