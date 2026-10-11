"""The date the PAGE states for itself — or nothing.

Order, and why: (1) the page's own publication metadata — the same regex
table the research engine reads (`engine/fetch.py _META_DATE`:
article:published_time, datePublished, JSON-LD, a <time> that says it is
the publication); (2) a date in the URL path, which is the publisher's own
filing of it; (3) a dateline in the first lines of the extracted prose
("ANYTOWN, ST, March 3, 2026 –", "March 3, 2026 —"); (4) `htmldate` with
`extensive_search=False`, which reads structural date markers only.

NOT read, on purpose: a modified/updated date, a copyright year, the
retrieval date, or htmldate's extensive heuristics (they GUESS from any
date-shaped string on the page, and a guessed date bands a page CURRENT
that nobody dated — invariant 9). A date in the future is not a
publication date and is dropped. Output is ISO `YYYY-MM-DD` with a stated
basis, so a challenger can see which rung produced it.
"""
from __future__ import annotations

import datetime as _dt
import re

_META_DATE = (
    (r'<meta[^>]+(?:property|name|itemprop)=["\'](?:article:published_time|datePublished|'
     r'og:published_time|publish[_-]?date|pubdate|date|dc\.date(?:\.issued)?|'
     r'sailthru\.date|parsely-pub-date)["\'][^>]*content=["\']([^"\']+)', "meta"),
    (r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\']'
     r'(?:article:published_time|datePublished|publish[_-]?date|pubdate)["\']', "meta"),
    (r'"datePublished"\s*:\s*"([^"]+)"', "json-ld datePublished"),
    (r'<time[^>]*(?:pubdate|itemprop=["\']datePublished["\'])[^>]*datetime=["\']([^"\']+)',
     "time element"),
    (r'<time[^>]*datetime=["\']([^"\']+)["\'][^>]*(?:pubdate|itemprop=["\']datePublished["\'])',
     "time element"),
)

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9

_DATELINE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b")
_DATELINE_DMY = re.compile(
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+((?:19|20)\d{2})\b")


def iso_day(v: str) -> str | None:
    """`YYYY-MM-DD` from an ISO-ish string, or None."""
    m = re.match(r"\s*((?:19|20)\d{2})-(\d{2})-(\d{2})", v or "")
    if not m:
        return None
    try:
        d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return d.isoformat()


def _not_future(iso: str | None, today: _dt.date | None = None) -> str | None:
    if not iso:
        return None
    today = today or _dt.date.today()
    try:
        return iso if _dt.date.fromisoformat(iso) <= today else None
    except ValueError:
        return None


def from_metadata(markup: str) -> tuple[str | None, str | None]:
    for pat, basis in _META_DATE:
        m = re.search(pat, markup or "", re.I)
        if m:
            d = iso_day(m.group(1))
            if d:
                return d, basis
    return None, None


def from_url(url: str) -> tuple[str | None, str | None]:
    m = (re.search(r"/((?:19|20)\d{2})[/-](0[1-9]|1[0-2])[/-](0[1-9]|[12]\d|3[01])(?:/|\b)", url or "")
         or re.search(r"/((?:19|20)\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])/", url or ""))
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "url path"
    m = re.search(r"/((?:19|20)\d{2})/(0[1-9]|1[0-2])/", url or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-01", "url path (month)"
    return None, None


def from_dateline(text: str, head_chars: int = 600) -> tuple[str | None, str | None]:
    head = (text or "")[:head_chars]
    m = _DATELINE.search(head)
    if m:
        mon = _MONTHS.get(m.group(1).lower().rstrip("."))
        try:
            return _dt.date(int(m.group(3)), mon, int(m.group(2))).isoformat(), "dateline"
        except (ValueError, TypeError):
            return None, None
    m = _DATELINE_DMY.search(head)
    if m:
        mon = _MONTHS.get(m.group(2).lower())
        try:
            return _dt.date(int(m.group(3)), mon, int(m.group(1))).isoformat(), "dateline"
        except (ValueError, TypeError):
            return None, None
    return None, None


_NOT_PUBLICATION = re.compile(
    r"<meta[^>]+(?:modified|updated|copyright|dcterms\.modified|revised)[^>]*>|"
    r"<time(?![^>]*(?:pubdate|datePublished))[^>]*>.*?</time>|"
    r"(?:©|&copy;|copyright)\s*(?:19|20)\d{2}", re.I | re.S)


def _strip_non_publication(markup: str) -> str:
    """htmldate reads a modified/updated meta and a copyright line as date
    signals even in structural mode; neither is a publication date, so they
    are removed before it looks."""
    return _NOT_PUBLICATION.sub(" ", markup or "")


def from_htmldate(markup: str, url: str = "") -> tuple[str | None, str | None]:
    try:
        from htmldate import find_date  # type: ignore
        markup = _strip_non_publication(markup)
        d = find_date(markup, url=url or None, original_date=True,
                      extensive_search=False, outputformat="%Y-%m-%d")
        return (d, "htmldate (structural)") if d else (None, None)
    except Exception:  # noqa: BLE001
        return (None, None)


def published_date(markup: str | None, url: str = "", text: str = "",
                   *, today: _dt.date | None = None) -> tuple[str | None, str | None]:
    """(YYYY-MM-DD, basis) or (None, None). Never guessed, never future."""
    for fn, arg in ((from_metadata, markup or ""), (from_url, url or "")):
        d, basis = fn(arg)
        d = _not_future(d, today)
        if d:
            return d, basis
    d, basis = from_dateline(text or "")
    d = _not_future(d, today)
    if d:
        return d, basis
    if markup:
        d, basis = from_htmldate(markup, url)
        d = _not_future(d, today)
        if d:
            return d, basis
    return None, None
