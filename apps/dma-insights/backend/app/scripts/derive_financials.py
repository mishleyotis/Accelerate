"""Financial-highlights derive (self-healing, grounded — no fabrication).

The Context "Financial trajectory" card was empty for 63 of 94 clients: only the
31 entities whose package shipped a structured `latest_ratios` / `entity_profile`
financial block had `firmographics.financial_highlights`. Yet the analyst report
states the figures for nearly all of them — usually as a multi-year table
(`2020  $0.99B  $155.2B  …  2025  $2.10B  ~$160B`) and/or in prose ("ROA of
1.52%", "efficiency ratio 44.1%", "total assets of $15.6 billion").

This pass reads each entity's persisted report prose (`document_sections`) and:
  * parses the multi-year Net Income / Total Assets table into a year-keyed
    series (powers the card's bar chart) + a latest total-assets metric;
  * extracts the standard ratios (ROA/ROE/NIM/efficiency/Tier-1) as floats —
    word-boundaried so "ROAdmap"/"miNIMum" can't false-match — with sanity
    bounds; falls back to scalar $ figures when there is no table.

Everything is the report's OWN number (never invented). Fill-if-empty: the 31
structured blocks are never overwritten; a report with no figures stays
honest-empty. Self-correcting + idempotent (re-derives its own prior output via
the `parsed_facts.fin_src` marker / string-typed currency).

Usage: DATABASE_URL=... python -m app.scripts.derive_financials
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import sys

from sqlalchemy import text

from app.database import get_sessionmaker

# ratio key → keyword (word-boundaried in the compiled pattern) → sane [lo, hi].
# Keys MUST match deepen_narrative._pct (roa_pct/roe_pct/efficiency_ratio_pct/
# tier_1_risk_based_pct) so the Overview why-now FINANCIAL signal reuses them.
_RATIOS: list[tuple[str, str, float, float]] = [
    ("roa_pct", r"ROAA|ROA|return on (?:average )?assets", 0.0, 5.0),
    ("roe_pct", r"ROAE|ROE|return on (?:average )?equity", 0.0, 40.0),
    ("nim_pct", r"NIM|net interest margin", 0.5, 8.0),
    ("efficiency_ratio_pct", r"efficiency ratio", 20.0, 99.0),
    ("tier_1_risk_based_pct",
     r"tier[ -]?1 risk[- ]based|tier[ -]?1 capital|tier[ -]?1 leverage|CET[ -]?1|tier[ -]?1", 4.0, 25.0),
]
_CASH: list[tuple[str, str]] = [
    ("net_income", r"net income"),
    ("total_assets", r"total assets"),
    ("deposits", r"total deposits|deposits"),
]
_UNIT = {"trillion": "T", "t": "T", "billion": "B", "bn": "B", "b": "B",
         "million": "M", "mm": "M", "m": "M"}
_MULT = {"T": 1e12, "B": 1e9, "M": 1e6}
# a multi-year table row: "<year>  $<v1><unit>  [$<v2><unit>]" (no % between).
_YEAR_ROW = re.compile(
    r"\b(20[12]\d)\b[^\n%]{0,12}?\$?~?\s*(\d{1,4}(?:\.\d{1,2})?)\s*([BMT])\b"
    r"(?:[^\n%]{0,12}?\$?~?\s*(\d{1,4}(?:\.\d{1,2})?)\s*([BMT])\b)?", re.I)


def _usd_num(val: str, unit: str) -> float:
    return float(val.replace(",", "")) * _MULT[unit.upper()]


def _usd_str(val: str, unit: str) -> str:
    return f"${float(val.replace(',', '')):g}{unit.upper()}"


def _usd_compact(n: float) -> str:
    a = abs(n)
    if a >= 1e12:
        return f"${n / 1e12:.1f}T"
    if a >= 1e9:
        return f"${n / 1e9:.1f}B"
    if a >= 1e6:
        return f"${n / 1e6:.0f}M"
    return f"${n:,.0f}"


def _ratio(prose: str, kw: str, lo: float, hi: float) -> float | None:
    m = re.search(rf"\b(?:{kw})\b[^%\d]{{0,40}}?(\d{{1,2}}(?:\.\d{{1,2}})?)\s*%", prose, re.I)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    return v if lo <= v <= hi else None


def _cash(prose: str, kw: str) -> str | None:
    m = re.search(rf"\b(?:{kw})\b[^$\d]{{0,40}}?\$?\s*([\d][\d.,]*)\s*(trillion|billion|million|bn|mm|[BMT])\b",
                  prose, re.I)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = _UNIT.get(m.group(2).lower())
    return f"${v:g}{unit}" if unit and v > 0 else None


def _year_rows(prose: str) -> list[tuple[int, float | None, float | None]]:
    """All `<year> $V1 [$V2]` rows, ONE per year. When a year appears more
    than once, the row with MORE populated $-columns wins — a stray inline
    mention ("… net income (2024)\t$480M …" in a bullet list) must never
    shadow the real two-column table row for that year. (The Compeer
    2026-07-06 QA defect: the stray single-value 2024 row consumed the
    year first, and its lone $480M then landed in the ASSETS column,
    charting FY2024 at $0.48B for a $33B institution.)"""
    best: dict[int, tuple[float | None, float | None]] = {}
    for yr, v1, u1, v2, u2 in _YEAR_ROW.findall(prose):
        y = int(yr)
        a = _usd_num(v1, u1) if v1 and u1 else None
        b = _usd_num(v2, u2) if v2 and u2 else None
        cur = best.get(y)
        n_new = (a is not None) + (b is not None)
        n_cur = -1 if cur is None else (cur[0] is not None) + (cur[1] is not None)
        if n_new > n_cur:   # first-seen wins ties (document order)
            best[y] = (a, b)
    return [(y, *best[y]) for y in sorted(best)]


def _plausible_series(s: dict[int, float], *, max_jump: float = 50.0) -> dict[int, float]:
    """Drop parse-error magnitudes from a year series.

    A real balance sheet never moves 50x between the years of one series —
    a point that far from the series median is a wrong-column / wrong-unit
    grab, not data. With ≥3 points the median votes the outlier out; with
    exactly 2 points that disagree by >max_jump there is no way to tell
    which one is wrong, so the whole series is honestly dropped (empty)
    rather than charting a fabricated cliff."""
    if len(s) < 2:
        return dict(s)
    vals = sorted(v for v in s.values() if v > 0)
    if len(vals) != len(s):        # non-positive values: keep conservative
        return dict(s)
    if len(s) == 2:
        lo, hi = vals
        return {} if hi / lo > max_jump else dict(s)
    med = vals[len(vals) // 2]
    return {y: v for y, v in s.items() if med / max_jump <= v <= med * max_jump}


def _assign_year_columns(
    parsed: list[tuple[int, float | None, float | None]],
) -> tuple[dict[int, float], dict[int, float]]:
    """(year→net_income, year→total_assets) from parsed year rows.

    Two-column rows are disambiguated by MAGNITUDE — total assets is always
    far larger than net income for a bank. A single-value row (a stray
    prose mention, or a table row whose second cell is "In progress") joins
    the cluster its magnitude matches — never blindly the positional
    column, which is how $480M of net income got charted as $0.48B of
    assets (Compeer, 2026-07-06 QA). Both series then pass the 50x
    plausibility guard."""
    if len(parsed) < 2:
        return {}, {}
    both = [(a, b) for _, a, b in parsed if a is not None and b is not None]
    ni_mean = ta_mean = None
    if len(both) >= 2:
        mean1 = sum(a for a, _ in both) / len(both)
        mean2 = sum(b for _, b in both) / len(both)
        ni_is_col1 = mean1 <= mean2
        ni_mean, ta_mean = (mean1, mean2) if ni_is_col1 else (mean2, mean1)
    else:
        ni_is_col1 = True
    ni_s: dict[int, float] = {}
    ta_s: dict[int, float] = {}
    for y, a, b in parsed:
        if a is not None and b is not None:
            ni, ta = (a, b) if ni_is_col1 else (b, a)
            ni_s[y] = ni
            ta_s[y] = ta
        else:
            v = a if a is not None else b
            if v is None or v <= 0:
                continue
            if ni_mean and ta_mean and ni_mean != ta_mean:
                d_ni = abs(math.log(v) - math.log(ni_mean))
                d_ta = abs(math.log(v) - math.log(ta_mean))
                (ni_s if d_ni <= d_ta else ta_s)[y] = v
            elif ni_is_col1:
                ni_s[y] = v
            else:
                ta_s[y] = v
    return _plausible_series(ni_s), _plausible_series(ta_s)


def _year_series(prose: str) -> tuple[dict[int, float], str | None]:
    """Parse the multi-year Net Income / Total Assets table → (year→net_income,
    latest total_assets string). Column assignment + plausibility guards in
    `_assign_year_columns`."""
    ni_s, ta_s = _assign_year_columns(_year_rows(prose))
    latest_ta = _usd_compact(ta_s[max(ta_s)]) if ta_s else None
    return ni_s, latest_ta


def _year_series_full(prose: str) -> tuple[dict[int, float], dict[int, float]]:
    """Both columns of the multi-year table → (year→net_income, year→assets).
    Column assignment + plausibility guards in `_assign_year_columns`."""
    return _assign_year_columns(_year_rows(prose))


def _median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None and x > 0)
    return xs[len(xs) // 2] if xs else None


def _closer_to(v: float, first_med: float, second_med: float) -> str:
    """Which median is `v` nearer to in LOG space (scale-aware)."""
    import math
    try:
        return ("first" if abs(math.log(v / first_med))
                <= abs(math.log(v / second_med)) else "second")
    except (ValueError, ZeroDivisionError):
        return "first"


# ── Labelled fiscal-year progression parser (year-slotting fix, audit bug 3) ──
# The magnitude/position year table (`_year_series_full`) mis-slots a "current"
# banner into an earlier FY: FCMA's "$29B in FY 2020 to $48.9B current (H1
# 2026)" bound $48.9B to FY2020, and the AR's own 5-year progression TABLE
# ("FY 2020 ~$29B ~$385M … FY 2024 $44.1B $600.4M (record) … H1 2026 $48.9B")
# was ignored. This parser prefers that AR-stated chained/table series: each
# value binds to its OWN labelled period, a "current"/"H1"/"in-period" banner
# can never occupy a prior year, and per-row driver notes ("post-Midsouth
# merger", "record") are captured as fy-keyed events.

# A period label (FY/CY/H1/H2/Q#) + 4-digit year, IMMEDIATELY followed (≤12
# chars, no %/$ in the gap) by a $-money — the row-start signature of a
# progression table. The money is a look-ahead so the row body is parsed apart.
_PERIOD_ANCHOR_RE = re.compile(
    r"\b(FY|CY|H1|H2|Q[1-4])?\s*((?:19|20)\d{2})\b"
    r"(?=[^\n%$]{0,12}?\$\s*~?\s*\d)", re.I)
_ROW_MONEY_RE = re.compile(r"\$\s*~?\s*(\d{1,4}(?:\.\d{1,2})?)\s*([BMT])\b", re.I)
# banner (non-annual "as-of" / interim) — must never land in a labelled FY slot
_BANNER_WORD_RE = re.compile(r"\bcurrent\b|\bin[- ]?period\b|\blatest\b|\bytd\b"
                             r"|\bas of\b|\binterim\b", re.I)
_RECORD_WORD_RE = re.compile(r"\brecord\b", re.I)
# a short per-row driver note (the "Key Driver" column / parenthetical event)
_ROW_DRIVER_RE = re.compile(r"\(([^()%$]{4,60}?)\)")


def _progression_series(prose: str) -> tuple[dict[int, float], dict[int, float], dict]:
    """AR-stated labelled-FY progression → (primary_series, net_income_series,
    meta). ``primary_series`` is the larger-magnitude column (assets / earning
    assets / EAOM), ``net_income_series`` the smaller. Each value is bound to
    the fiscal year of the row it sits in — an interim/"current" banner row
    (H1 2026) keeps its OWN year and never displaces an earlier FY.

    Returns empty series when no clustered ≥3-row progression table exists (the
    caller then falls back to the looser `_year_series_full`). ``meta`` carries
    ``events`` ({fy: driver_note}) and ``record_years`` for the card."""
    anchors: list[tuple[int, int, int, str | None]] = []  # (start, year_end, yr, prefix)
    for m in _PERIOD_ANCHOR_RE.finditer(prose or ""):
        y = int(m.group(2))
        if 2005 <= y <= 2035:
            anchors.append((m.start(), m.end(), y, (m.group(1) or "").upper() or None))
    if len(anchors) < 3:
        return {}, {}, {}
    # cluster: consecutive anchors whose row bodies sit within 150 chars form a
    # table; scattered exec-summary year-mentions fall into singleton clusters.
    clusters: list[list[tuple[int, int, int, str | None]]] = [[anchors[0]]]
    for a in anchors[1:]:
        if a[0] - clusters[-1][-1][1] <= 150:
            clusters[-1].append(a)
        else:
            clusters.append([a])
    table = max(clusters, key=len)
    if len(table) < 3:
        return {}, {}, {}
    # per-row: body from the year-end to the next row's label start; parse ≤2
    # money columns + a driver note. First-seen year wins (dedup).
    rows: list[tuple[int, list[tuple[float, str]], str | None, bool, bool]] = []
    seen: set[int] = set()
    for i, (_start, year_end, yr, prefix) in enumerate(table):
        if yr in seen:
            continue
        seen.add(yr)
        # last row window is TIGHT (its own value line only) so trailing
        # section prose ("Key Financial Signals: • Record profitability…")
        # can't leak a spurious record/driver into the final FY.
        body_end = table[i + 1][0] if i + 1 < len(table) else min(len(prose), year_end + 40)
        body = prose[year_end:body_end]
        cols = [(float(v), u.upper()) for v, u in _ROW_MONEY_RE.findall(body)][:2]
        if not cols:
            continue
        driver = None
        dm = _ROW_DRIVER_RE.search(body)
        if (dm and not _BANNER_WORD_RE.search(dm.group(1))
                and dm.group(1).strip().lower() != "record"):
            driver = dm.group(1).strip()
        is_record = bool(_RECORD_WORD_RE.search(body))
        is_banner = bool(prefix in {"H1", "H2", "Q1", "Q2", "Q3", "Q4"}
                         or _BANNER_WORD_RE.search(body))
        rows.append((yr, cols, driver, is_record, is_banner))
    if len(rows) < 2:
        return {}, {}, {}
    # column disambiguation by magnitude: the larger-mean column is the primary
    # (assets/EAOM), the smaller is net income.
    two = [(c[0][0] * _MULT[c[0][1]], c[1][0] * _MULT[c[1][1]])
           for _, c, *_ in rows if len(c) >= 2]
    if two:
        primary_is_col1 = (sum(a for a, _ in two) / len(two)) >= \
            (sum(b for _, b in two) / len(two))
    else:
        primary_is_col1 = True
    prim_vals = [(a if primary_is_col1 else b) for a, b in two]
    ni_vals = [(b if primary_is_col1 else a) for a, b in two]
    prim_med = _median(prim_vals)
    ni_med = _median(ni_vals)
    primary: dict[int, float] = {}
    ni: dict[int, float] = {}
    events: dict[int, str] = {}
    record_years: list[int] = []
    for yr, cols, driver, is_record, _banner in rows:
        usd = [c[0] * _MULT[c[1]] for c in cols]
        if len(usd) >= 2:
            p, n = (usd[0], usd[1]) if primary_is_col1 else (usd[1], usd[0])
            primary[yr], ni[yr] = p, n
        else:  # single value → the series its magnitude fits (log-nearest)
            v = usd[0]
            if prim_med and ni_med and _closer_to(v, ni_med, prim_med) == "first":
                ni[yr] = v
            else:
                primary[yr] = v
        if driver:
            events[yr] = driver[:90]
        elif is_record:
            events[yr] = "Record net income"
        if is_record:
            record_years.append(yr)
    return primary, ni, {"events": events, "record_years": record_years}


_CAGR_METRIC_KW = (
    ("assets", r"EAOM|earning asset|owned (?:and|&) managed|total asset|\basset"),
    ("net income", r"net income|earnings"),
    ("revenue", r"revenue|premium"),
    ("loans", r"loan"),
    ("deposits", r"deposit"),
)


def _stated_cagr(prose: str) -> tuple[float, str] | None:
    """The report's OWN stated CAGR + the metric it applies to (audit bug 4):
    "EAOM growing … a compound annual growth rate of 11.2%" → (11.2, "assets").
    The card must prefer this over a recomputed asset CAGR. Peer/industry lines
    are skipped; the metric is read from the ≤90 chars preceding the phrase."""
    for m in re.finditer(
            r"(?:compound annual growth(?: rate)?|CAGR)\s*(?:of|was|:)?\s*"
            r"~?(\d{1,2}(?:\.\d{1,2})?)\s*%"
            r"|~?(\d{1,2}(?:\.\d{1,2})?)\s*%\s*(?:net[- ]income\s+)?"
            r"(?:CAGR|compound annual)", prose or "", re.I):
        ctx_before = (prose or "")[max(0, m.start() - 90): m.start()]
        if re.search(r"\bpeer|\bindustry|\bmedian|\bbenchmark", ctx_before, re.I):
            continue
        try:
            val = float(m.group(1) or m.group(2))
        except (TypeError, ValueError):
            continue
        if not 0 < val < 60:
            continue
        # metric label: a keyword ADJACENT to the phrase wins ("net-income
        # CAGR"); else look further back for the subject of the sentence
        # (FCMA: "EAOM growing … a compound annual growth rate of 11.2%").
        tight = (prose or "")[max(0, m.start() - 40): m.end() + 40]
        label = next((lab for lab, kw in _CAGR_METRIC_KW
                      if re.search(kw, tight, re.I)), None)
        if label is None:
            wide = (prose or "")[max(0, m.start() - 170): m.start()]
            label = next((lab for lab, kw in _CAGR_METRIC_KW
                          if re.search(kw, wide, re.I)), "")
        return round(val, 2), label
    return None


# ── Discrete-highlights + ratings miner (PARTIAL-trend fix, audit bug 1) ──────
# When no ≥2-year assets/NI series exists (Capital Farm: five_year_trend
# "PARTIAL"), the package still carries real depth — loans, patronage, credit
# quality, agency ratings — in the report prose + evidence findings. These
# populate the card's HIGHLIGHTS/ratings variant instead of a null "trend gap".
_HL_MONEY = r"\$\s*([\d.,]+)\s*(trillion|billion|million|bn|[BMT])\b"
_HL_MONEY_RE = re.compile(_HL_MONEY, re.I)
# entity-own scale metrics (loans/total assets) — bound tightly to the keyword.
_HL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("loans", rf"{_HL_MONEY}[^.\n$]{{0,22}}?(?:in\s+)?(?:total\s+|net\s+)?loans"
              rf"|(?:total\s+|net\s+)?loans?(?:\s+portfolio)?[^.\n$]{{0,22}}?{_HL_MONEY}"),
    ("total_assets", rf"{_HL_MONEY}[^.\n$]{{0,18}}?(?:in\s+)?total\s+assets"
                     rf"|total\s+assets[^.\n$]{{0,18}}?{_HL_MONEY}"),
    ("net_income", rf"net income[^.\n$]{{0,26}}?{_HL_MONEY}"
                   rf"|{_HL_MONEY}[^.\n$]{{0,14}}?net income"),
)
# metrics whose figure is often a PARENT/holding-company number in the same
# prose (Capital Farm: FCBT parent $39.5B assets, $51.6M Q1 net income) — those
# are guarded out so the card never mislabels a parent's balance sheet as the
# client's. loans/patronage are the entity's OWN and are not guarded.
_HL_PARENT_GUARDED = {"total_assets", "net_income"}
_HL_PARENT_CUE = re.compile(
    r"parent|FCBT|Bank of Texas|holding compan|bancorp|AgriBank"
    r"|\bpeer\b|\bbenchmark\b|\bQ[1-4]\b", re.I)
_HL_CREDIT_Q_RE = re.compile(
    r"(?:credit quality|asset quality)[^.\n%]{0,26}?(\d{1,3}(?:\.\d)?)\s*%"
    r"|(\d{1,3}(?:\.\d)?)\s*%\s*(?:acceptable|asset quality|credit quality)", re.I)
_PATRONAGE_CUMULATIVE_RE = re.compile(
    r"cumulativ|\bsince\b|over\s+\d+\+?\s*year|\bto date\b", re.I)
_PATRONAGE_TOTAL_RE = re.compile(r"\btotal\b|distribut|returned|paid", re.I)
_RATING_AGENCY_RE = re.compile(
    r"(Fitch|Moody'?s|S&P|Standard\s*&\s*Poor'?s|DBRS|Kroll|AM\s*Best)", re.I)
_RATING_GRADE_RE = re.compile(
    r"\b(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?"
    r"|Aaa|Aa[123]|A[123]|Baa[123]|Ba[123])\b")
_RATING_OUTLOOK_RE = re.compile(r"\b(Stable|Positive|Negative)\b", re.I)
_AGENCY_CANON = {"fitch": "Fitch", "moody": "Moody's", "moodys": "Moody's",
                 "s&p": "S&P", "standard": "S&P", "dbrs": "DBRS",
                 "kroll": "Kroll", "am best": "AM Best"}


def _hl_usd(num: str, unit: str) -> float | None:
    try:
        v = float(str(num).replace(",", ""))
    except ValueError:
        return None
    mult = {"t": 1e12, "trillion": 1e12, "b": 1e9, "bn": 1e9, "billion": 1e9,
            "m": 1e6, "million": 1e6}.get((unit or "").lower(), 1e9)
    return v * mult if v > 0 else None


def _mine_patronage(text: str) -> float | None:
    """The ANNUAL patronage distributed (the "$189.6M total for 2024" figure),
    never the cumulative "$2.9B since 2006". Prefers a value tagged
    total/distributed; excludes cumulative-context values."""
    best_total: float | None = None
    best_any: float | None = None
    for pm in re.finditer(r"patronage", text or "", re.I):
        window = text[max(0, pm.start() - 90): pm.end() + 90]
        for mm in _HL_MONEY_RE.finditer(window):
            usd = _hl_usd(mm.group(1), mm.group(2))
            if not usd or usd <= 1e6:
                continue
            # examine only THIS figure's own clause — forward to the next $ or
            # sentence end — so a neighbour's cumulative tail ("$189.6M total …
            # $2.9B since 2006") can't disqualify the annual figure.
            fwd = re.split(r"\$|\. |; ", window[mm.end(): mm.end() + 35],
                           maxsplit=1)[0]
            clause = window[max(0, mm.start() - 15): mm.end()] + " " + fwd
            if _PATRONAGE_CUMULATIVE_RE.search(clause):
                continue        # cumulative "$2.9B since 2006" — not annual
            if _PATRONAGE_TOTAL_RE.search(clause):
                best_total = usd if best_total is None else max(best_total, usd)
            best_any = usd if best_any is None else max(best_any, usd)
    return best_total if best_total is not None else best_any


def _mine_ratings(text: str) -> dict[str, str]:
    """Agency credit ratings → {agency: "GRADE (outlook[, parent])"}. Each
    agency mention binds to the CLOSEST grade within ±55 chars in EITHER
    direction ("BBB Fitch" → Fitch BBB, not the Aa3 further along); a
    parent-entity context ("Farm Credit Bank of Texas rated Aa3") is
    labelled parent."""
    out: dict[str, str] = {}
    for am in _RATING_AGENCY_RE.finditer(text or ""):
        lo, hi = max(0, am.start() - 55), am.end() + 55
        best_gm, best_dist = None, 10**9
        for gm in _RATING_GRADE_RE.finditer(text, lo, hi):
            dist = (am.start() - gm.end()) if gm.end() <= am.start() \
                else (gm.start() - am.end())
            if 0 <= dist < best_dist:
                best_gm, best_dist = gm, dist
        if best_gm is None:
            continue
        raw = am.group(1).lower()
        agency = _AGENCY_CANON.get(
            "moody" if raw.startswith("moody") else
            "standard" if raw.startswith("standard") else raw, am.group(1))
        # outlook + parent flag are GRADE-local (±22 chars): "BBB Fitch … Aa3
        # parent rating" must not tag Fitch's BBB as parent from a later Aa3.
        gspan = text[max(0, best_gm.start() - 22): best_gm.end() + 22]
        outlook = _RATING_OUTLOOK_RE.search(gspan)
        is_parent = bool(re.search(r"parent|Bank of Texas|FCBT|holding|bancorp",
                                   gspan, re.I))
        extra = []
        if outlook:
            extra.append(outlook.group(1).title())
        if is_parent:
            extra.append("parent")
        label = f"{best_gm.group(1)} ({', '.join(extra)})" if extra else best_gm.group(1)
        out.setdefault(agency, label)
    return out


def _mine_highlights(text: str) -> dict:
    """Discrete latest-year financial values + ratings from prose/evidence.
    Everything is the source's OWN number; absent metrics stay absent (honest
    null, never coerced). Parent/holding-company figures are guarded out so a
    parent's balance sheet is never mislabelled the client's. Keys land on
    `financial_highlights` so the card's highlights/ratings variant renders
    instead of an empty 'trend data gap'."""
    fh: dict = {}
    for key, pat in _HL_PATTERNS:
        best: float | None = None
        for m in re.finditer(pat, text or "", re.I):
            if key in _HL_PARENT_GUARDED and _HL_PARENT_CUE.search(
                    text[max(0, m.start() - 70): m.end() + 20]):
                continue     # a parent/quarterly/peer figure — never the client's
            groups = [g for g in m.groups() if g is not None]
            for i in range(len(groups) - 1):   # each alt yields a (num, unit) pair
                usd = _hl_usd(groups[i], groups[i + 1])
                if usd and usd > 1e6 and (best is None or usd > best):
                    best = usd
                    break
        if best is not None:
            fh[key] = best
    patronage = _mine_patronage(text or "")
    if patronage is not None:
        fh["patronage"] = patronage
    cq = _HL_CREDIT_Q_RE.search(text or "")
    if cq:
        try:
            v = float(cq.group(1) or cq.group(2))
            if 50.0 <= v <= 100.0:
                fh["credit_quality_pct"] = round(v, 1)
        except (TypeError, ValueError):
            pass
    ratings = _mine_ratings(text or "")
    if ratings:
        fh["ratings"] = ratings
    return fh


def compute_cagr(series: dict[int, float]) -> float | None:
    """Compound annual growth from a ≥2-period year series (fraction)."""
    if len(series) < 2:
        return None
    years = sorted(series)
    y0, y1 = years[0], years[-1]
    v0, v1 = series[y0], series[y1]
    span = y1 - y0
    if span <= 0 or v0 <= 0 or v1 <= 0:
        return None
    try:
        rate = (v1 / v0) ** (1.0 / span) - 1.0
    except (OverflowError, ZeroDivisionError):
        return None
    return round(rate, 4) if -0.6 < rate < 0.6 else None


_USD_UNIT_MULT = {"t": 1e12, "b": 1e9, "m": 1e6}
_STRICT_ASSETS_RE = re.compile(
    r"\$\s*([\d.,]+)\s*(trillion|billion|million|[bmt])\b[^.\n$]{0,22}?total\s+assets"
    r"|total\s+assets[^.\n$]{0,22}?\$\s*([\d.,]+)\s*(trillion|billion|million|[bmt])\b",
    re.I)


def _parse_usd_amount(s: object) -> float | None:
    """A '$3.2B' / '$10.23 billion' string → USD float (None when unparseable)."""
    m = re.search(r"\$?\s*([\d.,]+)\s*(trillion|billion|million|[bmt])\b", str(s or ""), re.I)
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return n * _USD_UNIT_MULT.get((m.group(2) or "").lower()[:1], 1e9)


def _strict_total_assets(prose: str) -> float | None:
    """The entity's OWN total-assets figure — only a '$N.NB … total assets'
    adjacency counts (so a '2.8 peer median' score or a bare '$8.9B cohort' is
    never misread as a balance sheet). Returns the largest such figure in USD."""
    best: float | None = None
    for m in _STRICT_ASSETS_RE.finditer(prose or ""):
        num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            usd = float(str(num).replace(",", "")) * _USD_UNIT_MULT.get(
                (unit or "").lower()[:1], 1e9)
        except (ValueError, TypeError):
            continue
        if usd > 1e6 and (best is None or usd > best):
            best = usd
    return best


# External-anchor plausibility bands (2026-07-06 deploy review wave 2).
# Cross-field scale mismatches the intra-series median guard cannot see
# (alliant charted a $5.1B-topping series against a $47B balance sheet;
# american-homes charted [0.44, 0.48]B against $11.7B) are caught by
# checking every point against the entity's OWN firmographics anchor.
_ANCHOR_TA_BAND = (0.2, 5.0)        # assets point vs anchor (scalar anchor)
_ANCHOR_TA_BAND_TIER = (0.1, 10.0)  # looser band for the coarse tier anchor
_ANCHOR_NI_BAND = (0.0003, 0.08)    # net income as a share of the anchor
# representative mid-band anchors ($B) per entity_healing.derive_size_tier.
_SIZE_TIER_ANCHOR_B = {"small": 0.4, "community": 3.0, "mid-size": 22.0,
                       "large": 110.0, "mega": 600.0}


_PRIMARY_LABELS = {
    "total_assets": "assets", "revenue": "revenue", "premium": "premium placed",
    "premium_placed": "premium placed", "aum": "AUM", "loans": "loans",
    "deposits": "deposits",
}


def build_trajectory(*, ta_series: dict[int, float] | None,
                     ni_series: dict[int, float] | None,
                     branches: int | None, regulator: str | None,
                     geography: str | None, headcount: int | None,
                     source: str, anchor_usd: float | None = None,
                     size_tier: str | None = None,
                     max_fy: int | None = None,
                     primary_key: str = "total_assets",
                     stated_cagr: tuple[float, str] | None = None,
                     events_by_fy: dict[int, str] | None = None) -> dict | None:
    """The normalized FinancialTrajectoryCard shape (plan 4.6):
    ``{currency, unit, fy[], series{<primary_key>[], net_income_m[]},
    branches, regulator, geography, headline, events[], derived_from,
    anomalies[], anomaly_details[]}``.
    Requires ≥2 real periods on at least one metric; series are aligned to
    the fy axis with nulls for missing points; units normalized ($B / $M).

    ``primary_key`` selects the headline series by line-of-business (audit
    bug 2/6): banks/CUs chart ``total_assets``; insurance brokers / asset
    managers chart ``revenue`` / ``premium`` — the asset-anchor plausibility
    bands (which assume the series ≈ the balance-sheet anchor) apply ONLY to
    ``total_assets``. ``stated_cagr`` (value, metric-label) is the report's
    OWN CAGR and is preferred verbatim over a recomputed one (audit bug 4).
    ``events_by_fy`` seeds the fy-keyed timeline (progression "Key Driver"
    column) so events align to the SAME fiscal years as the series.

    ``anchor_usd`` is the entity's own firmographics scale anchor (aum_usd
    or the total-assets scalar); ``size_tier`` is the coarse fallback band.
    ``max_fy`` caps the axis at the assessment year + 1 — projection years
    mined from forward-looking prose (vestgen charted FY2028) are dropped
    and recorded, never charted as actuals."""
    from datetime import date

    ta = dict(ta_series or {})
    ni = dict(ni_series or {})
    details: list[dict] = []
    cap_fy = max_fy if max_fy is not None else date.today().year + 1
    for nmap, label in ((ta, primary_key), (ni, "net_income_m")):
        for y in sorted(y for y in nmap if y > cap_fy):
            details.append({
                "metric": label, "fy": y, "value": nmap.pop(y),
                "action": "dropped", "basis": "assessment_horizon",
                "note": f"{label} FY{y} dropped (beyond assessment "
                        f"horizon FY{cap_fy} — projection, not an actual)"})
    years = sorted(set(ta) | set(ni))
    years = [y for y in years if 2005 <= y <= 2035]
    if len(years) < 2:
        return None
    # unit normalization: assets in $B; a series stored as bare numbers <1e4
    # is ALREADY in $B (the CSV convention); raw USD is scaled.
    def _to_b(v: float) -> float:
        return round(v / 1e9, 2) if v >= 1e6 else round(v, 2)

    def _to_m(v: float) -> float:
        return round(v / 1e6, 1) if v >= 1e6 else round(v, 1)

    # Series-consistency guard (2026-07-06 deploy review: Compeer charted
    # total_assets [29.5, 30.8, 32.1, 0.48, 34.3] — a $480M net-income figure
    # inside a $30B series). A point off the series median by more than
    # `max_jump`x in NORMALIZED space is first tested for a pure unit mistake
    # (x1000 / /1000 landing within 2x of the median → rescale), else DROPPED
    # and recorded in `anomalies` so QA + the Gemini outlier-confirm rung can
    # audit every intervention. The band is PER METRIC: 5x for balance-sheet-
    # scale series (a real balance sheet never moves 5x between the years of
    # one series — and a wild point must be dropped HERE, before the anchor
    # rung below can double-error-"rescue" it x1000 into the band), but 50x
    # for net income, which legitimately swings in loss years — 50x still
    # catches the 66x Compeer misgrab. Dropped years render as an honest gap
    # (None); the Gemini financial_series_confirm rung can reinstate a
    # verified value via apply_series_verdicts. This is the last line of
    # defence regardless of caller, so the persisted trajectory the Overview
    # card AND the D5 Context chart both read is always consistent.
    def _guard(nmap: dict[int, float], label: str,
               *, max_jump: float | None = None) -> tuple[dict[int, float], list[str]]:
        if max_jump is None:
            max_jump = 50.0 if label == "net_income_m" else 5.0
        notes: list[str] = []
        med = _median(list(nmap.values()))
        if med is None or len(nmap) < 3:
            return nmap, notes
        out: dict[int, float] = {}
        for y, v in sorted(nmap.items()):
            if v <= 0 or (1.0 / max_jump) <= v / med <= max_jump:
                out[y] = v
                continue
            rescued = next((round(v * f, 2) for f in (1000.0, 0.001)
                            if 0.5 <= (v * f) / med <= 2.0), None)
            if rescued is not None:
                notes.append(
                    f"{label} FY{y}: {v} rescaled to {rescued} "
                    f"(unit mismatch vs series median {round(med, 2)})")
                details.append({"metric": label, "fy": y, "value": v,
                                "action": "rescaled", "rescaled_to": rescued,
                                "basis": "series_median", "note": notes[-1]})
                out[y] = rescued
            else:
                notes.append(
                    f"{label} FY{y}: {v} dropped "
                    f"({round(v / med, 3)}x the series median {round(med, 2)} "
                    f"— cross-metric or misparse)")
                details.append({"metric": label, "fy": y, "value": v,
                                "action": "dropped", "basis": "series_median",
                                "note": notes[-1]})
        return out, notes

    # External-anchor rung (wave 2): every surviving point is checked
    # against the firmographics scale anchor — the ONLY guard that can see
    # a whole-series scale mismatch, or a wrong point in a 2-point series
    # the median guard must skip. Pure unit mistakes rescale; contradicted
    # points drop (honest gap). Without an anchor, a >10x step in a short
    # series is FLAGGED (kept, never silently dropped — real post-merger
    # jumps exist) for the financial_series_confirm Gemini rung to audit.
    anchor_b = None
    tier_band = False
    if anchor_usd and anchor_usd > 1e6:
        anchor_b = anchor_usd / 1e9
    elif size_tier in _SIZE_TIER_ANCHOR_B:
        anchor_b = _SIZE_TIER_ANCHOR_B[size_tier]
        tier_band = True

    def _anchor_guard(nmap: dict[int, float], label: str,
                      notes: list[str]) -> dict[int, float]:
        if anchor_b is None or not nmap:
            return nmap
        if label == "total_assets":
            lo, hi = _ANCHOR_TA_BAND_TIER if tier_band else _ANCHOR_TA_BAND
            lo_v, hi_v = lo * anchor_b, hi * anchor_b
        else:  # net income ($M) plausibility as a share of the anchor
            lo_v = _ANCHOR_NI_BAND[0] * anchor_b * 1e3
            hi_v = _ANCHOR_NI_BAND[1] * anchor_b * 1e3
        # Net income rescues only go DOWNWARD (/1000 — a $M series point
        # mistakenly carrying $K/raw magnitudes). An NI value a
        # thousandfold too SMALL is indistinguishable from a cross-metric
        # misparse (southstate: $2.0M "net income" on a $45B book — a
        # 0.004% ROA is not a unit slip), so it drops as an honest gap.
        factors = (1000.0, 0.001) if label == "total_assets" else (0.001,)
        # Whole-series metric-mislabel guard (2026-07-06 deploy review wave 3
        # — "even Guaranteed Rate has an unusual financial trajectory"). An
        # ISOLATED point 1000x the net-income band is a unit slip and is
        # rescued /1000 below; but when EVERY point of a >=3-point net-income
        # series sits uniformly at ~1000x the band (i.e. at balance-sheet /
        # deposit / origination-volume scale, raw ~= the anchor itself), the
        # series is not net income at all — a different metric captured under
        # the label. Rescaling each point /1000 mints a plausible-but-
        # fabricated net-income line: Rate charted its $73B->$20B origination
        # VOLUME as "$73M..$20M net income" (aum anchor 24.7B == a raw series
        # point — circular), and 7 more entities (wsfs/ccu/members-1st/…)
        # charted total-assets/deposit figures the same way. Drop the whole
        # series as an honest gap and record the mislabel with its own basis
        # so the financial_series_confirm Gemini rung can reinstate a
        # correctly-labelled value — never chart the fabricated one.
        if label == "net_income_m":
            positive = [v for v in nmap.values() if v > 0]
            all_rescuable = bool(positive) and all(
                not (lo_v <= v <= hi_v)
                and any(lo_v <= v * f <= hi_v for f in factors)
                for v in positive)
            if len(positive) >= 3 and all_rescuable:
                kept: dict[int, float] = {}
                for y, v in sorted(nmap.items()):
                    if v <= 0:
                        kept[y] = v
                        continue
                    notes.append(
                        f"{label} FY{y}: {v} dropped (entire net-income "
                        f"series sits at balance-sheet scale vs firmographics "
                        f"anchor {round(anchor_b, 2)}B — metric mislabel, not "
                        f"a per-point unit slip)")
                    details.append({
                        "metric": label, "fy": y, "value": v,
                        "action": "dropped", "basis": "scale_anchor_mislabel",
                        "note": notes[-1]})
                return kept
        out: dict[int, float] = {}
        for y, v in sorted(nmap.items()):
            if v <= 0 or lo_v <= v <= hi_v:
                out[y] = v
                continue
            rescued = next((round(v * f, 2) for f in factors
                            if lo_v <= v * f <= hi_v), None)
            if rescued is not None:
                notes.append(
                    f"{label} FY{y}: {v} rescaled to {rescued} "
                    f"(unit mismatch vs firmographics scale anchor "
                    f"{round(anchor_b, 2)}B)")
                details.append({"metric": label, "fy": y, "value": v,
                                "action": "rescaled", "rescaled_to": rescued,
                                "basis": "scale_anchor", "note": notes[-1]})
                out[y] = rescued
            else:
                notes.append(
                    f"{label} FY{y}: {v} dropped (inconsistent with "
                    f"firmographics scale anchor {round(anchor_b, 2)}B "
                    f"— cross-field mismatch)")
                details.append({"metric": label, "fy": y, "value": v,
                                "action": "dropped", "basis": "scale_anchor",
                                "note": notes[-1]})
        return out

    def _flag_unanchored_step(nmap: dict[int, float], label: str,
                              notes: list[str]) -> None:
        if anchor_b is not None or len(nmap) != 2:
            return
        (y0, v0), (y1, v1) = sorted(nmap.items())
        if v0 > 0 and v1 > 0 and max(v0, v1) / min(v0, v1) > 10.0:
            notes.append(
                f"{label} FY{y0}→FY{y1}: {v0} → {v1} flagged "
                f"(>10x step, no external anchor to adjudicate)")
            details.append({"metric": label, "fy": y1, "value": v1,
                            "action": "flagged", "basis": "unanchored_step",
                            "note": notes[-1]})

    ta_n, notes_ta = _guard({y: _to_b(v) for y, v in ta.items()}, primary_key)
    ni_n, notes_ni = _guard({y: _to_m(v) for y, v in ni.items()}, "net_income_m")
    # asset-anchor bands are balance-sheet-specific; only guard total_assets
    # against them (a revenue/premium series has no such anchor — median guard
    # still catches its wild outliers).
    if primary_key == "total_assets":
        ta_n = _anchor_guard(ta_n, "total_assets", notes_ta)
        _flag_unanchored_step(ta_n, "total_assets", notes_ta)
    ni_n = _anchor_guard(ni_n, "net_income_m", notes_ni)
    _flag_unanchored_step(ni_n, "net_income_m", notes_ni)
    anomalies = notes_ta + notes_ni
    if not ta_n and not ni_n:
        return None      # every point suppressed — honest empty, no chart

    # horizon drops surface in the flat `anomalies` strings too (one list
    # feeds QA; `anomaly_details` is the structured Gemini-confirm input).
    anomalies = [d["note"] for d in details
                 if d["basis"] == "assessment_horizon"] + anomalies
    series_out: dict = {"net_income_m": [(ni_n.get(y)) for y in years] if ni_n else None}
    series_out[primary_key] = [(ta_n.get(y)) for y in years] if ta_n else None
    traj: dict = {
        "currency": "USD", "unit": "B",
        "fy": [f"FY{y}" for y in years],
        "series": series_out,
        "branches": branches, "regulator": regulator, "geography": geography,
        "employees": headcount, "events": [], "derived_from": source,
        "anomalies": anomalies,
        "anomaly_details": details,
    }
    plabel = _PRIMARY_LABELS.get(primary_key, "")
    head_bits = []
    if ta_n:
        last_y = max(ta_n)
        head_bits.append(f"{_usd_compact(ta_n[last_y] * 1e9)} {plabel} · FY{last_y}")
        if stated_cagr is not None:      # report's OWN CAGR wins (audit bug 4)
            cg_v, cg_metric = stated_cagr
            traj["cagr"] = f"{cg_v:g}%"
            traj["cagr_basis"] = "report_prose"
            head_bits.append(f"+{cg_v:g}% {cg_metric or plabel} CAGR".replace("+-", "-"))
        else:
            cg = compute_cagr(ta_n)
            if cg is not None:
                head_bits.append(f"{'+' if cg >= 0 else ''}{cg * 100:.1f}% CAGR")
    elif ni_n:
        last_y = max(ni_n)
        head_bits.append(f"{_usd_compact(ni_n[last_y] * 1e6)} net income · FY{last_y}")
        if stated_cagr is not None:
            cg_v, cg_metric = stated_cagr
            traj["cagr"] = f"{cg_v:g}%"
            traj["cagr_basis"] = "report_prose"
            head_bits.append(f"+{cg_v:g}% {cg_metric or 'net income'} CAGR".replace("+-", "-"))
    traj["headline"] = " · ".join(head_bits) if head_bits else None
    # fy-keyed events (progression "Key Driver" column) — same fiscal years as
    # the series; the caller may append timeline events after.
    if events_by_fy:
        axis_years = {int(y[2:]) for y in traj["fy"]}
        for y in sorted(events_by_fy):
            if y in axis_years and len(traj["events"]) < 4:
                traj["events"].append({"fy": f"FY{y}", "label": str(events_by_fy[y])[:90]})
    return traj


def _traj_headline(traj: dict) -> str | None:
    """Recompute the trajectory headline from the CURRENT series arrays —
    used after a Gemini-confirmed reinstatement changes the charted points."""
    fy_years = [int(str(f)[2:]) for f in traj.get("fy") or []]
    head_bits: list[str] = []
    series = traj.get("series") or {}
    # primary = the first non-null series key that is not net income (LOB-aware)
    primary_key = next((k for k, arr in series.items()
                        if k != "net_income_m" and isinstance(arr, list)
                        and any(v is not None for v in arr)), None)
    ta = {y: v for y, v in zip(fy_years, series.get(primary_key) or [], strict=False)
          if v is not None} if primary_key else {}
    ni = {y: v for y, v in zip(fy_years, series.get("net_income_m") or [], strict=False)
          if v is not None}
    if ta:
        last_y = max(ta)
        head_bits.append(f"{_usd_compact(ta[last_y] * 1e9)} "
                         f"{_PRIMARY_LABELS.get(primary_key, '')} · FY{last_y}")
        cg = compute_cagr(ta)
        if cg is not None:
            head_bits.append(f"{'+' if cg >= 0 else ''}{cg * 100:.1f}% CAGR")
    elif ni:
        last_y = max(ni)
        head_bits.append(f"{_usd_compact(ni[last_y] * 1e6)} net income · FY{last_y}")
    return " · ".join(head_bits) if head_bits else None


def apply_series_verdicts(fh: dict, verdicts: list[dict]) -> bool:
    """Fold validator-accepted ``financial_series_confirm`` verdicts into
    ``fh['trajectory']`` (mutates in place; returns True when anything
    changed). Contract (the Gemini outlier-confirm rung, user mandate
    "unusual outliers should be flagged and even confirmed"):

      * every verdict is stamped onto its matching ``anomaly_details``
        entry (idempotent — an entry with a verdict is never re-stamped);
      * ``keep`` / ``rescale`` reinstate the confirmed value into the
        charted series at that fiscal year (the honest gap closes with a
        grounded number — never an invented one; the acceptor already
        verified the value against the anomaly candidate + a verbatim
        quote);
      * ``drop`` leaves the gap — identical to the cold/deterministic
        behaviour, now with a cited reason attached.

    Projection drops (basis ``assessment_horizon``) are never reinstated:
    a forward-looking year stays off the actuals axis by design."""
    traj = fh.get("trajectory") if isinstance(fh, dict) else None
    if not isinstance(traj, dict):
        return False
    detail_list = traj.get("anomaly_details")
    if not isinstance(detail_list, list):
        return False
    changed = False
    fy_axis = [str(f) for f in traj.get("fy") or []]
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        match = next(
            (d for d in detail_list
             if isinstance(d, dict) and d.get("metric") == v.get("metric")
             and d.get("fy") == v.get("fy") and not d.get("verdict")),
            None)
        if match is None:
            continue
        verdict = str(v.get("verdict") or "").lower()
        match["verdict"] = verdict
        match["verdict_reason"] = str(v.get("reason") or "")[:240]
        changed = True
        if verdict not in ("keep", "rescale") \
                or match.get("basis") == "assessment_horizon":
            continue
        try:
            value = float(v.get("value"))
        except (TypeError, ValueError):
            continue
        series = traj.get("series") or {}
        arr = series.get(str(match.get("metric")))
        fy_key = f"FY{match.get('fy')}"
        if isinstance(arr, list) and fy_key in fy_axis:
            arr[fy_axis.index(fy_key)] = round(value, 2)
            match["verdict_value"] = round(value, 2)
    if changed:
        traj["headline"] = _traj_headline(traj)
    return changed


def _extract(prose: str) -> dict:
    fh: dict = {}
    year_ni, latest_ta = _year_series(prose)
    if len(year_ni) >= 2:
        for y, v in year_ni.items():
            fh[str(y)] = v          # year-keyed → the card's multi-year bar chart
        if latest_ta:
            fh["total_assets"] = latest_ta
    for key, kw, lo, hi in _RATIOS:
        v = _ratio(prose, kw, lo, hi)
        if v is not None:
            fh[key] = v
    for key, kw in _CASH:
        if key in fh or (key == "net_income" and year_ni):
            continue
        s = _cash(prose, kw)
        if s:
            fh[key] = s
    return fh


async def _amain() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    from app.services.entity_healing import REVENUE_SUBVERTICALS, prose_revenue
    from app.services.parsers.package_financials import sanitize_metric_keys

    sm = get_sessionmaker()
    filled = scanned = skipped_have = no_signal = 0
    traj_n = cagr_n = trend_n = rev_n = sanitized_n = 0
    aum_n = footprint_n = size_tier_n = hq_n = 0
    async with sm() as session:
        # Self-correct: clear our OWN prior prose-derivations (marker, or the
        # string-typed currency only this script writes) so improved rules fully
        # re-apply. Structured/Clay blocks (numeric currency, no marker) untouched.
        await session.execute(text(
            """
            UPDATE firmographics SET financial_highlights='{}'::jsonb
            WHERE financial_highlights IS NOT NULL AND (
                COALESCE(parsed_facts->>'fin_src','')='report_prose'
                OR jsonb_typeof(financial_highlights->'net_income')='string'
                OR jsonb_typeof(financial_highlights->'total_assets')='string'
                OR jsonb_typeof(financial_highlights->'deposits')='string')
            """))
        rows = (await session.execute(text(
            """
            SELECT e.id::text eid, e.display_id, e.name, e.subvertical,
                   r.id::text rid, r.assessment_date,
                   f.financial_highlights fh, f.aum_usd, f.revenue_usd,
                   f.headcount, f.primary_regulator, f.parsed_facts pf,
                   f.hq_address
            FROM entities e
            JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
            LEFT JOIN firmographics f ON f.entity_id=e.id
            WHERE e.status='ACTIVE' ORDER BY e.display_id
            """))).all()
        for row in rows:
            scanned += 1
            fh = dict(row.fh or {})
            pf = dict(row.pf or {}) if isinstance(row.pf, dict) else {}
            prose = (await session.execute(text(
                "SELECT string_agg(body, ' ') FROM document_sections WHERE run_id=CAST(:rid AS uuid)"
            ), {"rid": row.rid})).scalar() or ""
            ev_blob = ""

            async def _evidence(eid: str = row.eid) -> str:
                return (await session.execute(text(
                    """
                    SELECT string_agg(excerpt, E'\n') FROM evidence_index
                    WHERE entity_id=CAST(:e AS uuid) AND excerpt IS NOT NULL
                    """), {"e": eid})).scalar() or ""

            # 1. Prose-key sanitation on already-persisted highlights (the
            #    parser now kills them at source; this heals old rows).
            clean = sanitize_metric_keys(fh)
            if clean != fh:
                fh = clean
                sanitized_n += 1

            # 2. Fill-if-empty extraction from report prose (unchanged).
            if not fh:
                extracted = _extract(prose)
                if not extracted and row.aum_usd:
                    basis = pf.get("aum_basis") or "total_assets"
                    label = {"aum": "assets_under_management",
                             "aua": "assets_under_administration",
                             "total_assets": "total_assets"}.get(basis, "total_assets")
                    extracted = {label: _usd_compact(float(row.aum_usd))}
                if extracted:
                    fh = extracted
                    pf["fin_src"] = "report_prose"
                    filled += 1
                else:
                    no_signal += 1
            else:
                skipped_have += 1

            # 3. Normalized trajectory (plan 4.6) — year series assembled from
            #    the trends-CSV `series`, this script's own year-keyed net
            #    income, and the prose year table (guarded alignment).
            from app.services.nlp.quantities import (
                extract_metric_year_pairs,
                extract_year_series,
            )
            # LOB branch (audit bug 2): insurance brokers / broker-dealers chart
            # REVENUE (their scale metric), never total_assets. The unit-guard
            # once mis-rescaled a coerced revenue series to ~0 "K".
            subv = (row.subvertical or "").upper()
            is_broker = subv in {"IB", "RIA"}
            primary_key = "revenue" if is_broker else "total_assets"

            ni_prose, ta_prose = _year_series_full(prose)
            # AR-stated labelled-FY progression table wins over the looser
            # positional parse (audit bug 3): each value binds to its OWN fiscal
            # year; a "current"/H1/in-period banner never displaces an older FY.
            prog_primary, prog_ni, prog_meta = _progression_series(prose)
            recon_warn: str | None = None
            events_by_fy: dict[int, str] = {}
            if not is_broker and len(prog_primary) >= 2:
                for y in sorted(set(prog_primary) & set(ta_prose)):
                    a, b = prog_primary[y], ta_prose[y]
                    if a > 0 and b > 0 and abs(a - b) / max(a, b) > 0.10:
                        recon_warn = (
                            f"assets FY{y}: AR-stated table {_usd_compact(a)} vs "
                            f"positional-parse {_usd_compact(b)} diverge >10% "
                            f"— charted the AR-stated series")
                        break
                ta_prose = prog_primary
                ni_prose = prog_ni or ni_prose
                events_by_fy = prog_meta.get("events") or {}
            stated = _stated_cagr(prose)

            ni_fh = extract_year_series(
                {k: v for k, v in fh.items() if isinstance(v, int | float)})
            csv_series = fh.get("series") if isinstance(fh.get("series"), dict) else {}
            ta_csv = extract_year_series(csv_series or {})
            if is_broker:
                # A3 trends CSV headline series IS revenue for a broker; keep it
                # (raw $B numbers), else the prose year table. Not total_assets.
                ta_series = ta_csv or ta_prose
                ni_series = ni_fh or ni_prose
            else:
                ta_series = ta_csv or ta_prose
                ni_series = ni_fh or ni_prose
            # 3b. Evidence-excerpt mining (2026-07-04 deep search: 67 clients'
            #     multi-year series live ONLY in evidence lines — raw-thousands
            #     + parenthesised dates, "$X (2024) vs $Y (2023)", date-first
            #     NCUA rollups). Nearest-keyword bound, peer-guarded,
            #     magnitude-clustered. LAST fallback — table/CSV always win.
            if len(ta_series) < 2 or len(ni_series) < 2:
                ev_blob = await _evidence()
                mined = extract_metric_year_pairs(
                    ev_blob + "\n" + "\n".join(
                        str(x) for x in fh.get("lines", []) or []),
                    entity_name=row.name or "")
                # The 50x plausibility guard also gates the mined series —
                # mixed-magnitude grabs are parse errors, not YoY moves (the
                # median/anchor trajectory guards below adjudicate the rest).
                # Brokers chart revenue-first (audit bug 2).
                ta_mined = _plausible_series(
                    (mined.get("revenue") or mined.get("total_assets")
                     or mined.get("aum") or {}) if is_broker else (
                        mined.get("total_assets") or mined.get("aum")
                        or mined.get("revenue") or {}))
                ni_mined = _plausible_series(mined.get("net_income", {}))
                if len(ta_series) < 2 and len(ta_mined) >= 2:
                    ta_series = ta_mined
                if len(ni_series) < 2 and len(ni_mined) >= 2:
                    ni_series = ni_mined
                mined_basis = "evidence_mined" if ta_mined else "report_prose"
            else:
                ta_mined, mined_basis = {}, "report_prose"
            # External scale anchor + horizon for the trajectory guards
            # (wave 2): the entity's OWN aum/total-assets scalar, falling to
            # its size tier; fiscal years cap at assessment year + 1 so
            # projection prose (vestgen FY2028) never charts as an actual.
            from app.services.entity_healing import derive_size_tier
            anchor_usd = float(row.aum_usd) if row.aum_usd else None
            if not anchor_usd:
                for cand in (fh.get("total_assets"), pf.get("total_assets")):
                    if isinstance(cand, str):
                        anchor_usd = _parse_usd_amount(cand)
                        if anchor_usd:
                            break
            if not anchor_usd and prose:
                anchor_usd = _strict_total_assets(prose)
            traj = build_trajectory(
                ta_series=ta_series, ni_series=ni_series,
                branches=pf.get("branches") if isinstance(pf.get("branches"), int) else None,
                regulator=row.primary_regulator,
                geography=(pf.get("geography") or pf.get("hq_city")),
                headcount=row.headcount,
                source=("trends_csv" if ta_csv else
                        "financial_highlights" if ni_fh else "report_prose"),
                anchor_usd=anchor_usd,
                size_tier=(pf.get("size_tier")
                           or derive_size_tier(anchor_usd, row.headcount)),
                max_fy=(row.assessment_date.year + 1
                        if row.assessment_date else None),
                primary_key=primary_key,
                stated_cagr=stated,
                events_by_fy=events_by_fy,
            )
            if traj and recon_warn:      # workbook/AR divergence audit trail
                traj["anomalies"] = [recon_warn, *traj.get("anomalies", [])]
            # Context financials_view charts a pre-structured `series` key
            # as its primary axis — persist the primary series there ONLY
            # from the GUARDED trajectory (fill-if-empty; before wave 2 the
            # raw mined series landed here and re-charted the very points
            # the guard suppressed). Values stay raw USD (the key's
            # convention for magnitude-based unit detection downstream).
            if (traj and isinstance(traj["series"].get(primary_key), list)
                    and not isinstance(fh.get("series"), dict)):
                guarded = {
                    str(fy)[2:]: round(v * 1e9, 2)
                    for fy, v in zip(traj["fy"],
                                     traj["series"][primary_key],
                                     strict=False)
                    if v is not None}
                if len(guarded) >= 2:
                    fh["series"] = guarded
                    fh["series_metric"] = primary_key
                    fh["series_basis"] = mined_basis
            if traj:
                # fy events: major timeline items inside the series window.
                yrs = {int(y[2:]) for y in traj["fy"]}
                evs = (await session.execute(text(
                    """
                    SELECT title, event_date FROM timeline_events
                    WHERE entity_id=CAST(:e AS uuid) AND event_date IS NOT NULL
                      AND kind IN ('acquisition','leadership','regulatory','product')
                      AND COALESCE(signal,'') <> 'negative'
                    ORDER BY event_date DESC LIMIT 12
                    """), {"e": row.eid})).all()
                seen_fy: set[int] = set()
                for ev in evs:
                    y = ev.event_date.year
                    if y in yrs and y not in seen_fy and len(traj["events"]) < 4:
                        traj["events"].append({"fy": f"FY{y}", "label": (ev.title or "")[:90]})
                        seen_fy.add(y)
                fh["trajectory"] = traj
                traj_n += 1
            elif "trajectory" in fh:
                fh.pop("trajectory", None)

            # Highlights-only depth (2026-07-06 parity — operator: Context
            # shows nothing for entities like Zions). When there is no >=2yr
            # chart, D1's FinancialTrajectoryCard renders fh["trajectory"]'s
            # HIGHLIGHTS variant (latest-year metrics + CAGR) — but it reads
            # fh["trajectory"] directly, so without one it shows the empty
            # state despite real financials (Zions: net income $824M +
            # Tier-1 17%). Persist the shared normalizer's highlights blob
            # (never a chart — an un-guarded >=2yr axis is deliberately
            # excluded via `not hv.get("fy")`) with the footer facts so both
            # D1 and the Context view (which passes this blob through) agree.
            if "trajectory" not in fh:
                # Discrete-highlights + ratings depth (audit bug 1): the package
                # may carry NO >=2yr chart series yet still disclose real
                # financials (Capital Farm: loans $12.99B→$13.17B, patronage
                # $189.6M, credit quality 95.6%, Fitch BBB / Moody's Aa3) in the
                # report prose + evidence findings. Mine them (source's OWN
                # numbers, honest-null when absent) so the card's highlights/
                # ratings variant renders instead of a null "trend data gap".
                if not ev_blob:
                    ev_blob = await _evidence()
                mined_hl = _mine_highlights((prose or "") + "\n" + (ev_blob or ""))
                for k, v in mined_hl.items():
                    fh.setdefault(k, v)
                from app.services.overview_cards import financial_trajectory_card
                hv = financial_trajectory_card(fh)
                if (hv and (hv.get("highlights") or hv.get("ratings"))
                        and not hv.get("fy")):
                    hv.setdefault("regulator", row.primary_regulator)
                    hv.setdefault("geography", pf.get("geography") or pf.get("hq_city"))
                    hv.setdefault("employees", row.headcount)
                    if isinstance(pf.get("branches"), int):
                        hv.setdefault("branches", pf["branches"])
                    fh["trajectory"] = hv

            # 4. CAGR ladder: explicit prose statement (healer) → fh lines →
            #    computed from the ≥2-period assets series (basis-labelled).
            if not pf.get("cagr"):
                from app.services.entity_healing import prose_cagr
                from app.services.startup_enrich import derive_cagr
                cg = derive_cagr(fh)
                if stated is not None:      # report's OWN stated CAGR wins (bug 4)
                    pf["cagr"] = f"{stated[0]:g}%"
                    pf["cagr_basis"] = f"report_prose:stated:{stated[1] or 'metric'}"
                    cagr_n += 1
                elif cg is not None:
                    pf["cagr"] = f"{cg * 100:g}%"
                    pf["cagr_basis"] = "financial_highlights"
                    cagr_n += 1
                elif (cg_p := prose_cagr(prose)) is not None:
                    pf["cagr"] = cg_p
                    pf["cagr_basis"] = "report_prose"
                    cagr_n += 1
                else:
                    cg2 = compute_cagr(ta_series) if len(ta_series or {}) >= 2 else None
                    if cg2 is None and len(ni_series or {}) >= 3:
                        cg2 = compute_cagr(ni_series)
                    if cg2 is not None:
                        pf["cagr"] = f"{cg2 * 100:.1f}%"
                        pf["cagr_basis"] = "computed:year_series"
                        cagr_n += 1
            if not pf.get("trend"):
                from app.services.startup_enrich import derive_trend
                tr = derive_trend(fh)
                if tr:
                    pf["trend"] = tr
                    pf["trend_basis"] = "derived:financial_highlights"
                    trend_n += 1
            # Provenance floor: every present trend carries a *_basis marker.
            if pf.get("trend") and not pf.get("trend_basis"):
                pf["trend_basis"] = "derived:financial_highlights"

            # AUM recovery (fill-if-empty) — STRICTLY the entity's own attributed
            # total-assets figure: a "$N.NB … total assets" adjacency in the report
            # prose, or the parser's own `total_assets` fact. A bare "$8.9B cohort"
            # or a "2.8 peer median" score number is NOT a scale figure — the loose
            # first-$-in-prose scan misattributes those, so it is deliberately not
            # used. Honest-null when the corpus discloses no attributed assets.
            new_aum = row.aum_usd
            if new_aum is None:
                pa = _strict_total_assets(prose) if prose else None
                if pa is None and isinstance(pf.get("total_assets"), str):
                    pa = _parse_usd_amount(pf["total_assets"])
                if pa and pa > 1e6:
                    new_aum = pa
                    pf.setdefault("aum_basis", "total_assets")
                    aum_n += 1

            # Operating footprint (scalar string so the overview flattens it) —
            # an explicit footprint phrase / state list in the prose, else the
            # geography value. Stamped with provenance.
            if not pf.get("footprint"):
                from app.services.entity_healing import derive_footprint
                fp = derive_footprint(pf.get("geography"),
                                      (prose or "") + "\n" + (pf.get("geography") or ""))
                if fp:
                    pf["footprint"] = fp[:120]
                    pf["footprint_basis"] = ("derived:geography"
                                             if fp == pf.get("geography") else "nlp:report_prose")
                    footprint_n += 1

            # Size tier from the assets figure (preferred) or headcount bands.
            if not pf.get("size_tier"):
                from app.services.entity_healing import derive_size_tier
                st_tier = derive_size_tier(new_aum, row.headcount)
                if st_tier:
                    pf["size_tier"] = st_tier
                    pf["size_tier_basis"] = "derived:scale_bands"
                    size_tier_n += 1

            # HQ address column backfill (audit 2026-07-09: hq_address was 47%
            # null while parsed_facts carried the location as hq/footprint/
            # geography). Lift the headquarters CITY into the column so the
            # overview firmographics panel renders it — never a multi-state
            # footprint / 'National' descriptor (those stay pf.footprint).
            from app.services.entity_healing import (
                derive_hq_address,
                hq_is_plausible,
            )
            # keep a plausible existing value; a serialized-dict / ranking-phrase
            # stub ("Texas by asset size", "{'address':…}") is discarded and
            # re-derived (honest-null if the corpus carries no real HQ). Only the
            # entity's OWN structured parsed_facts feed the derivation — free-prose
            # mining is deliberately skipped: a narrative that names a parent /
            # partner ("Transamerica, headquartered in Baltimore MD") would else
            # bind THAT company's HQ to this client.
            new_hq = row.hq_address if hq_is_plausible(row.hq_address) else None
            if not new_hq:
                cand = derive_hq_address(pf)
                if cand:
                    new_hq = cand
                    pf.setdefault("hq_basis", "derived:parsed_facts")
                    hq_n += 1

            # 5. Revenue for revenue-basis subverticals (banks/CUs stay
            #    honest-null: assets is their scale metric).
            new_rev = row.revenue_usd
            if (new_rev is None
                    and (row.subvertical or "").upper() in REVENUE_SUBVERTICALS):
                rv = None
                for k, v in fh.items():
                    if not re.search(r"revenue", str(k), re.I):
                        continue
                    if isinstance(v, int | float):
                        rv = float(v) * (1e9 if v < 1e4 else 1.0)
                        break
                    if isinstance(v, str):     # CSV latest: "2.9 (2024)" / "$2.9B"
                        m = re.search(r"\$?([\d.,]+)\s*([BMT])?", v)
                        if m:
                            try:
                                n = float(m.group(1).replace(",", ""))
                            except ValueError:
                                continue
                            unit = m.group(2) or ("B" if "($B)" in str(k).upper()
                                                  else "M" if "($M)" in str(k).upper() else None)
                            mult = {"B": 1e9, "M": 1e6, "T": 1e12}.get(unit or "", 1e9 if n < 1e4 else 1.0)
                            rv = n * mult
                            break
                if rv is None and prose:
                    rv = prose_revenue(prose)
                if rv and rv > 1e6:
                    new_rev = rv
                    pf["revenue_basis"] = "report"
                    rev_n += 1

            await session.execute(text(
                """
                INSERT INTO firmographics (entity_id, financial_highlights, parsed_facts,
                    revenue_usd, aum_usd, hq_address)
                VALUES (CAST(:e AS uuid), CAST(:fh AS jsonb), CAST(:pf AS jsonb),
                        :rev, :aum, :hq)
                ON CONFLICT (entity_id) DO UPDATE SET
                    financial_highlights = EXCLUDED.financial_highlights,
                    parsed_facts = EXCLUDED.parsed_facts,
                    revenue_usd = COALESCE(firmographics.revenue_usd, EXCLUDED.revenue_usd),
                    aum_usd = COALESCE(firmographics.aum_usd, EXCLUDED.aum_usd),
                    -- computed value already preserves a plausible existing HQ and
                    -- clears an implausible stub, so it wins outright here.
                    hq_address = EXCLUDED.hq_address,
                    updated_at = NOW()
                """), {"e": row.eid, "fh": json.dumps(fh), "pf": json.dumps(pf),
                       "rev": new_rev, "aum": new_aum, "hq": new_hq})
        await session.commit()

    print(f"# derive_financials: scanned={scanned} filled={filled} "
          f"already_had={skipped_have} no_report_figures={no_signal} "
          f"trajectory={traj_n} cagr={cagr_n} trend={trend_n} revenue={rev_n} "
          f"aum={aum_n} footprint={footprint_n} size_tier={size_tier_n} hq={hq_n} "
          f"prose_keys_sanitized={sanitized_n} (grounded; normalized series)", flush=True)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
