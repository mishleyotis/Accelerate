"""Event-date resolution + urgency-window extraction.

Why: the timeline audit found 88% of the 1,097 events carried a
defaulted date (26 dots piled on 2026-04-01 for one client) because
scripts fell straight to ``publish_date``. This module makes the ladder
explicit — textual day > month > quarter > fiscal/bare year — and only
then ``publish_date``, ALWAYS labelled with a ``precision`` so the
frontend can jitter/cluster honestly:

    day | month | quarter | year | publish_fallback | none

Quarter anchoring: "Q3 2025" resolves to the FIRST day of the quarter's
MIDDLE month (2025-08-01) — the least-wrong single date for a
three-month span. Fiscal/bare years anchor mid-year (YYYY-07-01);
"early/mid/late YYYY" anchor Feb/Jun/Oct 15.

:func:`extract_windows` mines urgency windows for why-now signals:
explicit quarter targets ("by Q2 2026"), rolling clocks ("within 18
months"), and deadline cues ("closes", "deadline", "go-live", "target
completion").
"""
from __future__ import annotations

import re
from datetime import date

from app.services.nlp.segment import sentences

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_ALT = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
)

_ISO_RE = re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b")
_MDY_RE = re.compile(
    rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{{2}})\b"
)
_DMY_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_ALT})\.?,?\s+((?:19|20)\d{{2}})\b")
_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/((?:19|20)\d{2})\b")
_MONTH_YEAR_RE = re.compile(rf"\b({_MONTH_ALT})\.?\s+((?:19|20)\d{{2}})\b")
_QUARTER_RE = re.compile(
    r"\bQ([1-4])\s*(?:of\s+)?(?:FY\s*)?((?:19|20)\d{2}|\d{2})\b"
    r"|\b([1-4])Q\s*((?:19|20)\d{2}|\d{2})\b",
    re.IGNORECASE,
)
_FISCAL_RE = re.compile(r"\bFY\s?((?:19|20)\d{2}|\d{2})\b", re.IGNORECASE)
_PART_YEAR_RE = re.compile(r"\b(early|mid|late)[-\s]((?:19|20)\d{2})\b", re.IGNORECASE)
_BARE_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

# Middle month of each quarter — first day of it is the anchor.
_QUARTER_MID_MONTH = {1: 2, 2: 5, 3: 8, 4: 11}
_PART_YEAR_ANCHOR = {"early": (2, 15), "mid": (6, 15), "late": (10, 15)}


def _year(raw: str) -> int:
    y = int(raw)
    return 2000 + y if y < 100 else y


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def resolve_event_date(
    text: str, publish_date: date | None = None
) -> tuple[date | None, str]:
    """Resolve the best event date in ``text`` → ``(date, precision)``.

    Ladder: explicit day > month-year > quarter > fiscal/partial/bare
    year > ``publish_date`` (precision ``publish_fallback``) > ``(None,
    "none")``. Never raises; malformed candidates are skipped.
    """
    if text:
        m = _ISO_RE.search(text)
        if m:
            resolved = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if resolved:
                return resolved, "day"
        m = _MDY_RE.search(text)
        if m:
            month = _MONTHS[m.group(1).lower().rstrip(".")]
            resolved = _safe_date(int(m.group(3)), month, int(m.group(2)))
            if resolved:
                return resolved, "day"
        m = _DMY_RE.search(text)
        if m:
            month = _MONTHS[m.group(2).lower().rstrip(".")]
            resolved = _safe_date(int(m.group(3)), month, int(m.group(1)))
            if resolved:
                return resolved, "day"
        m = _SLASH_RE.search(text)
        if m:
            resolved = _safe_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
            if resolved:
                return resolved, "day"
        m = _MONTH_YEAR_RE.search(text)
        if m:
            month = _MONTHS[m.group(1).lower().rstrip(".")]
            resolved = _safe_date(int(m.group(2)), month, 1)
            if resolved:
                return resolved, "month"
        m = _QUARTER_RE.search(text)
        if m:
            q = int(m.group(1) or m.group(3))
            y = _year(m.group(2) or m.group(4))
            resolved = _safe_date(y, _QUARTER_MID_MONTH[q], 1)
            if resolved:
                return resolved, "quarter"
        m = _PART_YEAR_RE.search(text)
        if m:
            month, day = _PART_YEAR_ANCHOR[m.group(1).lower()]
            resolved = _safe_date(int(m.group(2)), month, day)
            if resolved:
                return resolved, "year"
        m = _FISCAL_RE.search(text)
        if m:
            resolved = _safe_date(_year(m.group(1)), 7, 1)
            if resolved:
                return resolved, "year"
        m = _BARE_YEAR_RE.search(text)
        if m:
            resolved = _safe_date(int(m.group(1)), 7, 1)
            if resolved:
                return resolved, "year"
    if publish_date is not None:
        return publish_date, "publish_fallback"
    return None, "none"


# --- urgency windows ------------------------------------------------------

_QUARTER_CUE_RE = re.compile(
    r"\b(?:by|before|until|through|no\s+later\s+than|ahead\s+of|targeting|for)\s+"
    r"(Q[1-4]\s*(?:of\s+)?(?:FY\s*)?(?:(?:19|20)\d{2}|\d{2}))\b",
    re.IGNORECASE,
)
_CLOCK_RE = re.compile(
    r"\b(?:within|over|in)\s+(?:the\s+next\s+)?(\d{1,3})\s+(months?|years?|weeks?|days?)\b"
    r"|\b(\d{1,3})[-\s]month\s+(?:clock|window|timeline|deadline|runway|horizon)\b",
    re.IGNORECASE,
)
_DEADLINE_CUE_RE = re.compile(
    r"\b(deadline|go[-\s]live|target\s+completion|closes?|closing|due\s+(?:by|date)|"
    r"expires?|expiration|sunset(?:s|ting)?|cutover|conversion\s+date)\b",
    re.IGNORECASE,
)

_UNIT_TO_MONTHS = {"month": 1.0, "year": 12.0, "week": 12.0 / 52.0, "day": 12.0 / 365.0}


def _months_from(raw_n: str, raw_unit: str) -> int:
    unit = raw_unit.lower().rstrip("s")
    return max(1, round(int(raw_n) * _UNIT_TO_MONTHS.get(unit, 1.0)))


def extract_windows(text: str) -> list[dict]:
    """Mine urgency windows → ``[{kind, text, date, months}, ...]``.

    ``kind`` ∈ ``deadline | quarter | clock``. Quarters/deadlines carry a
    resolved ``date`` (or None); clocks carry ``months``. Deadline cues
    take precedence over a quarter mention in the same sentence ("closes
    in Q2 2026" is one deadline window, not two entries).
    """
    out: list[dict] = []
    if not text or not text.strip():
        return out
    for sent in sentences(text):
        for m in _CLOCK_RE.finditer(sent):
            n, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), "months")
            out.append(
                {"kind": "clock", "text": m.group(0).strip(), "date": None,
                 "months": _months_from(n, unit)}
            )
        deadline = _DEADLINE_CUE_RE.search(sent)
        if deadline:
            resolved, precision = resolve_event_date(sent)
            out.append(
                {"kind": "deadline", "text": sent.strip()[:160],
                 "date": resolved if precision != "none" else None, "months": None}
            )
            continue  # quarter mention in this sentence belongs to the deadline
        for m in _QUARTER_CUE_RE.finditer(sent):
            resolved, _precision = resolve_event_date(m.group(1))
            out.append(
                {"kind": "quarter", "text": m.group(0).strip(), "date": resolved,
                 "months": None}
            )
    return out
