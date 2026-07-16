"""Project firmographics blobs into the D1 "Evidence & benchmarks" card
shapes (FinancialTrajectoryCard + SentimentCard).

Why this exists
---------------
`derive_financials` / `derive_sentiment` populate ``firmographics.
financial_highlights`` and ``firmographics.sentiment`` in the DB, and the
schema declares top-level ``financial_trajectory`` / ``sentiment`` fields
on ``EntityOverviewResponse`` — but the overview endpoint never mapped
the firmographics blobs into those card fields, so both cards rendered
their empty state on every client (audit 2026-07-02). These two pure
functions bridge the gap: no new derivation, just a reshape at serve
time so the packed overview carries the card payloads.

Both are total (never raise) and return ``None`` when there is nothing
renderable, so the card keeps its honest empty state.
"""
from __future__ import annotations

import re

# "$34.2B" / "$592M" / "$27.4 B" → (value, unit-letter)
_MONEY = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)\s*([BbMmKk])\b")
# a metric line: "Total assets: 2023 $34.2B → 2024 $38.3B → 2025 $40.8B"
_METRIC_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z /&%-]{2,40}?)\s*[:\-]\s*(.+)$")
# canonical card series keys the FinancialTrajectoryCard reads. Order matters —
# `_key_for` returns the FIRST substring hit, so multi-word keys precede the
# generic single words they contain ("credit quality" before "quality").
_SERIES_KEYS = {
    "total assets": "total_assets",
    "assets": "total_assets",
    "net income": "net_income_m",
    "deposits": "deposits",
    "nim": "nim_pct",
    "net interest margin": "nim_pct",
    "revenue": "revenue",
    "premium": "premium",
    "aum": "aum",
    "members": "members",
    "loans": "loans",
    # discrete-highlights metrics for partial-trend clients (audit bug 1)
    "patronage": "patronage",
    "credit quality": "credit_quality_pct",
    "asset quality": "credit_quality_pct",
    "debt to equity": "debt_to_equity",
    "roa": "roa_pct",
    "roe": "roe_pct",
    "efficiency": "efficiency_ratio_pct",
}
# Display labels for the highlights variant (single-year / CAGR-only clients).
_LABELS = {
    "total_assets": "Total assets", "net_income_m": "Net income",
    "deposits": "Deposits", "nim_pct": "NIM", "revenue": "Revenue",
    "premium": "Premium", "aum": "AUM", "members": "Members", "loans": "Loans",
    "patronage": "Patronage", "credit_quality_pct": "Credit quality",
    "debt_to_equity": "Debt/equity", "roa_pct": "ROA", "roe_pct": "ROE",
    "efficiency_ratio_pct": "Efficiency ratio",
}


def _money(tok: str) -> tuple[float | None, str | None]:
    m = _MONEY.search(tok)
    if not m:
        return None, None
    val = float(m.group(1).replace(",", ""))
    unit = m.group(2).upper()
    return val, unit


def _scalar_highlight(key: str, val: float) -> tuple[float, str | None]:
    """A bare scalar metric → a compact (value, unit) so the card renders
    "$824M" / "17%" instead of the raw "824,000,000" (2026-07-06 parity fix:
    Zions' net_income 824000000 charted as a naked integer on both D1 and D5).
    A percent metric carries a "%" unit (the card omits the $ prefix for it)."""
    if key.endswith("_pct"):
        return round(val, 1), "%"
    a = abs(val)
    if a >= 1e9:
        return round(val / 1e9, 1), "B"
    if a >= 1e6:
        return round(val / 1e6, 0), "M"
    if a >= 1e3:
        return round(val / 1e3, 0), "K"
    return val, None


def financial_trajectory_card(fh: object) -> dict | None:
    """Build ``{currency, unit, fy[], series{...}, headline, events[]}`` from
    ``firmographics.financial_highlights``.

    Parses the structured "Metric: YYYY $NB → YYYY $NB" lines (bank-ozk
    style) into aligned year→value series; falls back to mining bare
    year→$value pairs out of prose lines (frost/fisher style) for the
    dominant metric. Returns None when no ≥2-point series can be formed.
    """
    if not isinstance(fh, dict):
        return None
    # FIRST: derive_financials already normalized + GUARDED this trajectory
    # (unit-rescued / outlier-dropped, anomalies audited) and persisted it
    # under `trajectory`. D5 Context charts exactly this via
    # context_extras.financials_view, so trusting it here makes the Overview
    # card and the Context chart agree by construction (Compeer, 2026-07-06
    # deploy review: context charted a 5-year series while the Overview card
    # fell to the highlights variant because fh["series"] happened to be
    # metric-keyed, not year-keyed). Trust the one persisted, guarded axis.
    tj = fh.get("trajectory")
    if (isinstance(tj, dict) and len(tj.get("fy") or []) >= 2
            and isinstance(tj.get("series"), dict)
            and any(v for v in tj["series"].values() if v)):
        return dict(tj)
    # Pre-structured year-keyed series (derive_financials' evidence miner
    # and the Gemini financial_series_extraction enrichment both persist
    # `series`/`series_metric`) — the same primary axis the D5 context
    # view charts, so both surfaces agree by construction.
    pre = fh.get("series")
    if isinstance(pre, dict):
        pairs = sorted(
            (int(str(y)), float(v)) for y, v in pre.items()
            if re.fullmatch(r"(?:19|20)\d{2}", str(y).strip())
            and isinstance(v, int | float)
        )
        if len(pairs) >= 2:
            metric = str(fh.get("series_metric") or "total_assets")
            vals = [v for _, v in pairs]
            unit = "B" if max(vals) >= 1e9 else ("M" if max(vals) >= 1e6 else "K")
            div = {"B": 1e9, "M": 1e6, "K": 1e3}[unit]
            key = _SERIES_KEYS.get(metric.replace("_", " "), None) or (
                "total_assets" if metric == "total_assets" else metric)
            cagr_v = None
            y0, v0 = pairs[0]
            y1, v1 = pairs[-1]
            if v0 > 0 and v1 > 0 and y1 > y0:
                cagr_v = f"{((v1 / v0) ** (1 / (y1 - y0)) - 1) * 100:.1f}%"
            return {
                "currency": "USD", "unit": unit,
                "fy": [y for y, _ in pairs],
                "series": {key: [round(v / div, 2) for _, v in pairs]},
                "cagr": fh.get("cagr") or cagr_v,
                "trend": next((t for t in ("ACCELERATING", "DECLINING",
                                           "STABLE", "DECELERATING")
                               if t in str(fh.get("trend") or "").upper()), None),
                "headline": None, "events": [],
            }
    lines = fh.get("lines") or []
    if isinstance(lines, str):
        lines = [lines]
    series: dict[str, dict[int, float]] = {}
    bare_metrics: dict[str, tuple[float, str]] = {}  # metric → (value, unit), no year
    unit_seen: str | None = None

    def _pairs(text: str) -> list[tuple[int, float, str]]:
        """All (year, value, unit) pairs in a segment, both orderings:
        "2023 $34.2B", "$592M in 2023", and "$153.7M (2022)"."""
        out: list[tuple[int, float, str]] = []
        for ym in re.finditer(r"\b(19|20)(\d{2})\b[^\d$]{0,14}?(\$\s*[\d,]+(?:\.\d+)?\s*[BbMmKk])", text):
            v, u = _money(ym.group(3))
            y = int(ym.group(1) + ym.group(2))
            if v is not None and 1990 <= y <= 2035:
                out.append((y, v, u))
        # value→year: a connecting word ("$592M in 2023") OR a parenthesized
        # year ("$153.7M (2022)") disambiguates it from arrow-separated
        # structured data ("$34.2B → 2024") where the year belongs to the NEXT.
        for vm in re.finditer(
            r"(\$\s*[\d,]+(?:\.\d+)?\s*[BbMmKk])\s*"
            r"(?:(?:in|of|as of|by|during|for|through)\s+(?:\w+\s+)?(19|20)(\d{2})"
            r"|\(\s*(?:FY\s*)?(19|20)(\d{2})[^)]*\))",
            text,
        ):
            v, u = _money(vm.group(1))
            y = int((vm.group(2) or vm.group(4)) + (vm.group(3) or vm.group(5)))
            if v is not None and 1990 <= y <= 2035:
                out.append((y, v, u))
        return out

    def _key_for(text: str, label: str | None = None) -> str | None:
        src = re.sub(r"[_/]", " ", (label or text).lower())
        return next((v for k, v in _SERIES_KEYS.items() if k in src), None)

    for ln in lines:
        if not isinstance(ln, str):
            continue
        m = _METRIC_LINE.match(ln)
        key = _key_for(ln, m.group(1) if m else None)
        if key is None:
            continue
        for year, val, unit in _pairs(ln):
            unit_seen = unit_seen or unit
            series.setdefault(key, {})[year] = val
    # Mine EVERY string field's value too (not just `lines`): the healed data
    # carries per-metric keys like "Revenue ($B)": "5.1 (2024)" and
    # "Total assets": "2023 $34.2B → 2024 $38.3B" whose metric name is the KEY.
    for rawk, rawv in fh.items():
        if rawk == "lines" or not isinstance(rawk, str):
            continue
        blob = f"{rawk}: {rawv}" if isinstance(rawv, str | int | float) else ""
        km = re.match(r"([a-z_]+?)_((?:19|20)\d{2})$", rawk.lower())
        if km:  # keyed year-value ("deposits_2024": "$31.0B")
            key = _key_for(km.group(1).replace("_", " "))
            val, unit = _money(str(rawv))
            if key and val is not None:
                unit_seen = unit_seen or unit
                series.setdefault(key, {}).setdefault(int(km.group(2)), val)
            continue
        key = _key_for(blob, rawk)
        if not key:
            continue
        # unit lives in the KEY ("Revenue ($B)": "5.1 (2024)") — the value is a
        # bare number ± a parenthesized year; the $ regex in _pairs can't see it.
        uk = re.search(r"\(\s*\$?\s*([BbMmKk])\b", rawk)
        nm = re.match(r"\s*\$?\s*([\d,]+(?:\.\d+)?)", str(rawv))
        if uk and nm and isinstance(rawv, str) and "$" not in str(rawv):
            val = float(nm.group(1).replace(",", ""))
            unit_seen = unit_seen or uk.group(1).upper()
            ym = re.search(r"\(\s*(?:FY\s*)?((?:19|20)\d{2})", str(rawv))
            if ym:
                series.setdefault(key, {}).setdefault(int(ym.group(1)), val)
            else:
                bare_metrics.setdefault(key, (val, uk.group(1).upper()))
        elif isinstance(rawv, str):
            pairs = _pairs(blob)
            for year, val, unit in pairs:
                unit_seen = unit_seen or unit
                series.setdefault(key, {}).setdefault(year, val)
            if not pairs:  # bare money string, no year ("total_assets": "$3.7B")
                mv, mu = _money(rawv)
                if mv is not None:
                    unit_seen = unit_seen or mu
                    bare_metrics.setdefault(key, (mv, mu or "B"))

    # CAGR + trend classification + a headline line, always surfaced.
    cagr = fh.get("cagr_3yr") or fh.get("year_cagr") or fh.get("cagr")
    text_all = " ".join(str(x) for x in [*lines, *fh.values()] if isinstance(x, str))
    if not cagr:
        # "9.4% CAGR" (value-first) OR "CAGR (2022-2025): 9.4%" (label-first,
        # with a year range / basis between the word and the value).
        cm = re.search(r"([\d.]+\s*%)[^%]{0,20}?(?:CAGR|compound annual)", text_all, re.I) \
            or re.search(r"(?:CAGR|compound annual)[^%]{0,40}?([\d.]+\s*%)", text_all, re.I)
        if cm:
            cagr = cm.group(1).strip()
    trend = next((t for t in ("ACCELERATING", "DECLINING", "STABLE", "DECELERATING")
                  if t in text_all.upper()), None)
    headline = next((ln.strip()[:180] for ln in lines
                     if isinstance(ln, str) and re.search(r"CAGR|Trend|Growth|trajectory", ln, re.I)),
                    None)

    multi = {k: v for k, v in series.items() if len(v) >= 2}
    if multi:
        fys = sorted({y for v in multi.values() for y in v})
        return {
            "currency": "USD", "unit": unit_seen or "B",
            "fy": fys, "series": {k: [v.get(y) for y in fys] for k, v in multi.items()},
            "cagr": cagr, "trend": trend, "headline": headline, "events": [],
        }
    # No ≥2-period series — surface the financial DEPTH that still exists
    # (latest-year headline metrics + CAGR + trend) as a highlights card so the
    # AE never sees an empty state when real financials are present.
    highlights: list[dict] = []
    for key, yv in series.items():           # single-year series values
        yr = max(yv)
        highlights.append({"label": _LABELS.get(key, key), "value": yv[yr],
                           "unit": unit_seen or "B", "year": yr})
    for key, (val, unit) in bare_metrics.items():   # unit-in-key, no year
        if key not in series:
            highlights.append({"label": _LABELS.get(key, key), "value": val,
                               "unit": unit, "year": None})
    for rawk, rawv in fh.items():            # standalone scalar metrics
        if not isinstance(rawk, str) or rawk in ("lines", "cagr", "cagr_3yr"):
            continue
        key = _key_for(rawk)
        if key and key not in series and key not in bare_metrics \
                and isinstance(rawv, int | float):
            hv, hu = _scalar_highlight(key, float(rawv))
            highlights.append({"label": _LABELS.get(key, key),
                               "value": hv, "unit": hu, "year": None})
    highlights = highlights[:4]
    ratings = fh.get("ratings") if isinstance(fh.get("ratings"), dict) else None
    if not (highlights or cagr or ratings):
        return None
    out: dict = {
        "currency": "USD", "unit": unit_seen or "B",
        "fy": [], "series": {}, "cagr": cagr, "trend": trend,
        "headline": headline, "highlights": highlights, "events": [],
    }
    if ratings:      # agency credit ratings (audit bug 1 — Capital Farm)
        out["ratings"] = {str(k): str(v) for k, v in ratings.items()}
    return out


def sentiment_card(sent: object) -> dict | None:
    """Normalize ``firmographics.sentiment`` into the SentimentCard shape
    ``{employee[], customer[], industry_avg, b2b_b2c_gap}``.

    The derive_sentiment output is already card-shaped; this guards the
    types (lists, floats) and drops the blob when neither cohort carries
    a rating so the card keeps its honest empty state.
    """
    if not isinstance(sent, dict):
        return None
    # Serve-time normalization: a raw ingest/Clay blob ({"sources":[…]}) carries
    # none of the scorecard arrays the card renders, so it would blank the card
    # even though the ratings sit in `sources`. normalize_sentiment (the same
    # pure transform derive_sentiment + entity_healing use) lifts sources into
    # employee[]/customer[]/nps[]/qualitative[]. Lazy + guarded so serve never
    # breaks on it (2026-07-09 QA: most sentiment cards rendered empty because
    # normalization ran only in an out-of-band script, not at serve time).
    if (not any(isinstance(sent.get(k), list) and sent.get(k)
                for k in ("employee", "customer", "nps", "qualitative"))
            and sent.get("sources")):
        try:
            from app.scripts.derive_sentiment import normalize_sentiment
            sent = normalize_sentiment(sent) or sent
        except Exception:
            pass
    emp = sent.get("employee") if isinstance(sent.get("employee"), list) else []
    cust = sent.get("customer") if isinstance(sent.get("customer"), list) else []
    nps = sent.get("nps") if isinstance(sent.get("nps"), list) else []
    qual = sent.get("qualitative") if isinstance(sent.get("qualitative"), list) else []
    if not emp and not cust and not nps and not qual:
        return None

    # sentiment signals ingest from research notes that carry markdown
    # emphasis ("**ANB BBB Rating**", "Servicing: **MIXED**") — never render
    # raw "**" in the chip text (2026-07-13 corpus scan)
    def _destar(rows: object) -> object:
        if isinstance(rows, list):
            for _r in rows:
                if isinstance(_r, dict) and isinstance(_r.get("signal"), str):
                    _r["signal"] = _r["signal"].replace("**", "").strip()
        return rows

    emp, cust, nps, qual = _destar(emp), _destar(cust), _destar(nps), _destar(qual)
    out = {
        "employee": emp,
        "customer": cust,
        "b2b_b2c_gap": sent.get("b2b_b2c_gap"),
        "derived_from": sent.get("derived_from"),
    }
    # NPS rows are their own metric kind (a -100..+100 index — "NPS +22"),
    # never a score/scale bar; score-less sources ship as qualitative rows
    # (signal + trend, no bar) instead of vanishing (2026-07-06 review).
    if nps:
        out["nps"] = nps
    if qual:
        out["qualitative"] = qual
    ia = sent.get("industry_avg")
    if isinstance(ia, int | float):
        out["industry_avg"] = float(ia)
    return out


__all__ = ["financial_trajectory_card", "sentiment_card"]
