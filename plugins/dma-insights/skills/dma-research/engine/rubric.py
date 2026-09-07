#!/usr/bin/env python3
"""The maturity SCORE scale (1.0-5.0) and its level labels — the workbook's
own axis, distinct from the four display BANDS.

Both exist on purpose. The rubric is what the scoring stage states beside a
score ("2.25 (M2)", as the Golden 1 reference does throughout) and the bands
are what the app renders (charter invariant 6: four bands, strict less-than,
on the raw score). A fifth BAND word must never appear in code, enum or
prose; the fifth score LEVEL is a rubric row and is named here without the
banned word (owner adjudication GSY-11, 2026-09-01).
"""
from __future__ import annotations

#: (name, range, meaning) for levels 1..5 — dma-assessment SKILL.md's rubric,
#: with the fifth level named "Leading" (the assessment skill's own
#: "Industry-leading" meaning) rather than the banned band word.
_LEVELS = (
    ("Foundational", "1.0-1.4", "Absent or ad hoc"),
    ("Developing", "1.5-2.4", "Basic, inconsistent"),
    ("Established", "2.5-3.4", "Standardized, documented"),
    ("Advanced", "3.5-4.4", "Optimized, data-driven"),
    ("Leading", "4.5-5.0", "Industry-leading"),
)
#: (level, name, range, meaning) rows, as the Maturity_Rubric tab carries them.
RUBRIC = tuple((f"M{i}", n, r, m) for i, (n, r, m) in enumerate(_LEVELS, start=1))
_CUTS = (1.5, 2.5, 3.5, 4.5)


def maturity_level(score) -> str:
    """The M-level for a score on the 1-5 scale. Null in, '' out — never a
    default that looks like data (invariant 9)."""
    try:
        x = float(score)
    except (TypeError, ValueError):
        return ""
    for i, cut in enumerate(_CUTS, start=1):
        if x < cut:
            return f"M{i}"
    return f"M{len(_CUTS) + 1}"


def level_name(level: str) -> str:
    for lv, name, _, _ in RUBRIC:
        if lv == level:
            return name
    return ""
