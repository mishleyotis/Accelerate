"""Evidence freshness banding + per-entity rollups.

Per the user mandate: "Staleness should always be flagged, especially
if evidence has surpassed 3 years." Today is the reference date; the
3-year staleness window for the current commit starts at
2026-05-23 minus 3y = 2023-05-23.

The DB-side authority is the GENERATED columns added in migration
018: ``evidence_index.is_stale`` and ``evidence_index.freshness_band``.
This service mirrors that logic in Python so:

  - Tests don't need a database round-trip to assert banding.
  - The persistence layer can pre-compute a band before the row is
    inserted (for warnings / parser_warnings) without re-querying.
  - The customer_intelligence service can roll up bands from in-
    memory evidence lists.

State branches (the 4 freshness bands):

  1. ``current`` — published in the last 12 months (or recency_months
     ≤ 12). Green badge in EvidenceDrawer.
  2. ``aging``  — 12 < age ≤ 24 months. Amber.
  3. ``dated``  — 24 < age ≤ 36 months. Orange.
  4. ``stale``  — age > 36 months. Red, with the "⚠ >3y" disclaimer.

Plus one sentinel: ``undated`` when published_date is NULL AND
recency_months is NULL. Surfaced to the UI as a grey "undated" badge.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Literal


# Calendar-aware year arithmetic. `timedelta(days=365*3+1)` was the
# previous Python equivalent but drifts ±1 day on the 3-year boundary
# whenever the window crosses 0 or 2 leap years (1096 days hardcodes
# exactly one leap). SQL `INTERVAL '3 years'` is calendar-aware; we
# match it via `replace(year=year-3)` with month-end safety.
def _years_ago(d: date, years: int) -> date:
    """Calendar-aware subtraction matching Postgres `INTERVAL 'N years'`.

    Edge: feb-29 → feb-28 when target year is not leap (matches PG).
    """
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        # Only triggered by feb-29 on non-leap target year.
        return d.replace(year=d.year - years, day=28)

FreshnessBand = Literal["current", "aging", "dated", "stale", "undated"]


def _months_between(d: date, ref: date) -> float:
    """Days/30.4375 — close enough for banding boundaries."""
    return (ref - d).days / 30.4375


def compute_band(
    *,
    published_date: date | None,
    recency_months: int | None,
    today: date,
) -> FreshnessBand:
    """Mirrors the SQL ``compute_evidence_freshness_band`` function
    verbatim. Migration 018 declares this contract:

        IF (pd IS NOT NULL AND pd >= now - 1y) OR (rm IS NOT NULL AND rm <= 12)
        THEN current

    i.e. the OR semantics — EITHER signal of freshness wins. An old
    ``published_date`` does NOT veto a recent ``recency_months`` (a
    crawl that re-captured the same URL last week is still "current"
    even if the article itself is from 2020).

    Prior to fix (2026-05-26) the Python helper used an ``if/else``
    that gave ``published_date`` absolute priority — diverging from
    the SQL trigger by one band on rows where both signals were
    present. A test_evidence_staleness regression now pins both
    sides against the same matrix.

    Boundaries: ``<=`` is inclusive on the YOUNG end, matching the
    SQL ``>=`` cutoffs (current ≤ 12, aging ≤ 24, dated ≤ 36).
    """
    if published_date is None and recency_months is None:
        return "undated"

    def _pd_within(months: int) -> bool:
        if published_date is None:
            return False
        return _months_between(published_date, today) <= months

    def _rm_within(months: int) -> bool:
        return recency_months is not None and recency_months <= months

    if _pd_within(12) or _rm_within(12):
        return "current"
    if _pd_within(24) or _rm_within(24):
        return "aging"
    if _pd_within(36) or _rm_within(36):
        return "dated"
    return "stale"


def is_stale(
    *,
    published_date: date | None,
    recency_months: int | None,
    today: date,
) -> bool:
    """The 3-year flag — matches the SQL trigger `evidence_freshness_trigger`
    verbatim:

        NEW.is_stale := (
            (pd IS NOT NULL AND pd < CURRENT_DATE - INTERVAL '3 years')
            OR (rm IS NOT NULL AND rm > 36)
        )

    Calendar-aware via `_years_ago` (not `timedelta(days=1096)`) so
    leap years don't introduce ±1-day drift between the Python helper
    and the SQL trigger on certain date pairs.
    """
    if published_date is not None and published_date < _years_ago(today, 3):
        return True
    return recency_months is not None and recency_months > 36


@dataclass(slots=True)
class FreshnessRollup:
    current_count: int
    aging_count: int
    dated_count: int
    stale_count: int
    undated_count: int
    total: int
    median_age_months: float | None
    oldest_published_date: date | None
    stale_pct: float

    def as_dict(self) -> dict:
        return {
            "current_count": self.current_count,
            "aging_count": self.aging_count,
            "dated_count": self.dated_count,
            "stale_count": self.stale_count,
            "undated_count": self.undated_count,
            "total": self.total,
            "median_age_months": (
                round(self.median_age_months, 1)
                if self.median_age_months is not None else None
            ),
            "oldest_published_date": (
                self.oldest_published_date.isoformat()
                if self.oldest_published_date else None
            ),
            "stale_pct": round(self.stale_pct, 2),
        }


def rollup_freshness(
    rows: list[dict],
    *,
    today: date,
) -> FreshnessRollup:
    """Aggregate band counts + median age + stale_pct for one entity.

    Each row must have ``published_date`` (date|None) and
    ``recency_months`` (int|None).
    """
    bands: Counter[FreshnessBand] = Counter()
    ages: list[float] = []
    oldest: date | None = None
    for r in rows:
        pd = r.get("published_date")
        rm = r.get("recency_months")
        bands[compute_band(published_date=pd, recency_months=rm, today=today)] += 1
        if pd is not None:
            ages.append(_months_between(pd, today))
            if oldest is None or pd < oldest:
                oldest = pd
        elif rm is not None:
            ages.append(float(rm))
    total = sum(bands.values())
    stale = bands["stale"]
    median = None
    if ages:
        sorted_ages = sorted(ages)
        mid = len(sorted_ages) // 2
        if len(sorted_ages) % 2 == 1:
            median = sorted_ages[mid]
        else:
            median = (sorted_ages[mid - 1] + sorted_ages[mid]) / 2
    stale_pct = (stale / total * 100.0) if total else 0.0
    return FreshnessRollup(
        current_count=bands["current"],
        aging_count=bands["aging"],
        dated_count=bands["dated"],
        stale_count=stale,
        undated_count=bands["undated"],
        total=total,
        median_age_months=median,
        oldest_published_date=oldest,
        stale_pct=stale_pct,
    )


def bundle_stale_pct(bundle_rows: list[dict], *, today: date) -> float:
    """For RAG bundles: % of retrieved evidence with band == 'stale'.

    Used by `/rag/answer` to attach a `bundle_stale_pct` metadata
    field; when > 40 the UI surfaces a "⚠ Most evidence is dated"
    disclaimer above the response.
    """
    if not bundle_rows:
        return 0.0
    stale = sum(
        1 for r in bundle_rows
        if compute_band(
            published_date=r.get("published_date"),
            recency_months=r.get("recency_months"),
            today=today,
        ) == "stale"
    )
    return round(stale / len(bundle_rows) * 100.0, 2)
