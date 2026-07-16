"""Metric extraction from prose + guarded year-series alignment.

Why: the financial surfaces were polluted by two bug classes the audits
quantified — (1) ad-hoc number scraping that lost the metric/unit/period
context ("$2.35B" with no idea it was revenue, +23.8% with no
direction), and (2) the spurious year-series harvest where years were
pulled OUT OF VALUE PROSE, producing series like [2022, 2025] →
[2023, 87.5]. :func:`extract_metrics` returns fully-labelled
``{metric, value, unit, period, direction, raw}`` records;
:func:`extract_year_series` aligns year→value ONLY when the year token
is a standalone key/label — a year appearing inside a value string (or
a value that itself parses to a bare year) is never treated as a series
point.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from app.services.nlp.entities import parse_money, parse_percent

Metric = dict

_MONEY_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:MM|K|M|B|T|bn|k|m|mm|tn|billion|million|thousand|trillion)?\b"
)
_PCT_RE = re.compile(r"([+\-~≈]?)\s?(\d+(?:\.\d+)?)\s?%")
_ARROW_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(days?|months?)\s*(?:→|->|to)\s*(\d[\d,]*(?:\.\d+)?)\s*(days?|months?)",
    re.IGNORECASE,
)
_STARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*stars?\b", re.IGNORECASE)
_COUNT_RE = re.compile(
    r"\b(\d{1,3}(?:,\d{3})+|\d+)\s+"
    r"(branches?|users?|employees?|members?|customers?|locations?|clients?|accounts?|"
    r"stores?|offices?|FTEs?|ATMs?|advisors?|agents?|seats?|licen[cs]es?)\b",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(days?|months?)\b", re.IGNORECASE)
_RATIO_RE = re.compile(r"\b(\d+(?:\.\d+)?)x\b|\bratio\s+(?:of\s+)?(\d+(?:\.\d+)?)\b(?!\s*%)")

_COMPANION_PCT_RE = re.compile(r"[^()]{0,25}\(\s*([+\-])\s?(\d+(?:\.\d+)?)\s?%\s*\)")
_PAREN_PERIOD_RE = re.compile(r"\s*\(([^()]*(?:19|20)\d{2}[^()]*)\)")
# Period-awareness (audit bug 5b): a period may be a QUARTER / HALF ("Q2 2025",
# "H1 2026") — captured so a period-aware consumer can reject a quarterly figure
# when an ANNUAL field is wanted (a $1.9B Q2 print is not the annual revenue).
# The date-range dash is matched via unicode escapes so no ambiguous literal
# en/em dash sits in the source (ruff RUF001/003).
_INLINE_PERIOD_RE = re.compile(
    r"\b(?:in|for|during|as of)\s+"
    r"((?:Q[1-4]\s*|H[12]\s*)?(?:FY\s?)?(?:19|20)\d{2}"
    r"(?:\s*[\u2013\u2014-]\s*(?:FY\s?)?(?:19|20)\d{2})?)",
    re.IGNORECASE,
)
# A quarter/half period sitting immediately after the value, no connective word
# ("$1.9B Q2 2025", "$48.9B (H1 2026)").
_TRAILING_QUARTER_RE = re.compile(
    r"\s*\(?\s*((?:Q[1-4]|H[12])\s*(?:FY\s?)?(?:19|20)\d{2})", re.IGNORECASE)
# Any quarter / half / "quarterly" token — the sub-annual-period detector.
_QUARTER_RE = re.compile(r"\bQ[1-4]\b|\bH[12]\b|\bquarterl?y?\b|\binterim\b", re.IGNORECASE)
_COMPARATOR_RE = re.compile(r"\s*(below|above)\s+([\w][\w\s]*?)(?=[.,;:!?)]|$)", re.IGNORECASE)

# Size-tier band (audit bug 5c): a two-edge money RANGE that describes a tier
# BAND ("Large ($10B-$50B)", "$100B-$200B size tier"), NOT a point estimate.
# Neither edge may be read as a precise figure — the balance-sheet actual wins.
_TIER_BAND_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:MM|K|M|B|T|bn|billion|million|trillion)?\s*"
    r"(?:[\u2013\u2014-]|to)\s*"
    r"\$?\s?\d[\d,]*(?:\.\d+)?\s?(?:MM|K|M|B|T|bn|billion|million|trillion)?",
    re.IGNORECASE,
)
# A band is only a tier band when a size/tier/band cue sits just before it — so a
# real growth range ("revenue grew from $2.0B to $5.1B") keeps BOTH endpoints.
_TIER_CUE_RE = re.compile(
    r"(?:size[-\s]?tier|\btier\b|\bband\b|\brange\b|\bbetween\b|\bSV\d|"
    r"small|community|mid[-\s]?size|midsize|large|mega|enterprise|regional)\W{0,3}$",
    re.IGNORECASE,
)

# Trailing verbs/fillers that sit between a metric label and its number.
_LABEL_SKIP = frozenset({
    "the", "a", "an", "of", "to", "was", "were", "is", "are", "at", "in", "and",
    "with", "approximately", "about", "around", "roughly", "its", "their", "total",
    "grew", "rose", "declined", "fell", "increased", "decreased", "improved",
    "dropped", "reached", "hit", "totaled", "totalled", "stands", "stood", "posted",
    "reported", "now", "currently", "from", "by", "up", "down", "or", "per",
})
_MONEY_NOUNS = frozenset({
    "revenue", "revenues", "assets", "income", "deposits", "loans", "aum", "budget",
    "capital", "funding", "valuation", "sales", "ebitda", "equity", "fees",
})
_DIR_UP_RE = re.compile(r"\b(up|increase[ds]?|grew|rose|improved|gain(?:ed)?|expand(?:ed)?)\b", re.IGNORECASE)
_DIR_DOWN_RE = re.compile(
    r"\b(down|decline[ds]?|fell|dropped|decrease[ds]?|contract(?:ed)?|below|shrank)\b",
    re.IGNORECASE,
)


def _overlaps(start: int, end: int, taken: list[tuple[int, int]]) -> bool:
    return any(s < end and start < e for s, e in taken)


def _label_before(text: str, start: int, max_words: int = 3) -> str | None:
    """The metric label preceding a number ("efficiency ratio 58.2%")."""
    prefix = text[:start]
    # Stay inside the current sentence/clause.
    cut = max(prefix.rfind(ch) for ch in ".;:!?\n") if prefix else -1
    prefix = prefix[cut + 1 :]
    words = re.findall(r"[A-Za-z][\w&/'-]*", prefix)
    picked: list[str] = []
    for word in reversed(words):
        if word.lower() in _LABEL_SKIP:
            if picked:
                break
            continue
        picked.append(word)
        if len(picked) >= max_words:
            break
    if not picked:
        return None
    return " ".join(reversed(picked))


def _period_after(text: str, end: int) -> str | None:
    m = _PAREN_PERIOD_RE.match(text, end)
    if m:
        inner = m.group(1).strip()
        # A parenthetical that is ONLY a % change is direction, not period.
        if re.search(r"(?:19|20)\d{2}", inner):
            return inner
    m = _TRAILING_QUARTER_RE.match(text, end)
    if m:
        return m.group(1).strip()
    m = _INLINE_PERIOD_RE.search(text[end : end + 40])
    if m:
        return m.group(1).strip()
    return None


def is_quarterly(period: object) -> bool:
    """True when a period label names a sub-annual span (Q#/H#/quarterly).

    Lets a revenue picker reject a quarterly print when the ANNUAL figure is
    wanted — a "$1.9B (Q2 2025)" must never be labelled the annual revenue.
    """
    return bool(period) and bool(_QUARTER_RE.search(str(period)))


def is_size_tier_band(text: object) -> bool:
    """True when a string is a size-tier BAND ("Large ($10B-$50B)",
    "$100B-$200B tier") rather than a point estimate. A band edge is not a
    precise figure — callers prefer the balance-sheet actual instead."""
    s = str(text or "")
    for m in _TIER_BAND_RE.finditer(s):
        if _TIER_CUE_RE.search(s[max(0, m.start() - 28): m.start()]):
            return True
    return False


def _direction_near(text: str, start: int, end: int) -> str | None:
    window = text[max(0, start - 40) : min(len(text), end + 20)]
    if _DIR_DOWN_RE.search(window):
        return "down"
    if _DIR_UP_RE.search(window):
        return "up"
    return None


def extract_metrics(text: str) -> list[Metric]:
    """Extract labelled metrics → ``[{metric, value, unit, period, direction, raw}]``.

    ``unit`` ∈ ``{usd, pct, count, days, months, ratio, stars}``.
    Extractors run most-specific-first over non-overlapping spans, so
    "$2.35B revenue (+23.8%)" yields one usd metric plus one pct change
    metric — never a bare 2.35 cardinal.
    """
    out: list[Metric] = []
    if not text or not text.strip():
        return out
    taken: list[tuple[int, int]] = []

    # 0. Reserve size-tier band spans FIRST (audit bug 5c) so neither edge of a
    #    "Large ($10B-$50B)" band is later emitted as a point estimate. Only
    #    cue-preceded bands are consumed; a bare growth range keeps both edges.
    for m in _TIER_BAND_RE.finditer(text):
        if _TIER_CUE_RE.search(text[max(0, m.start() - 28): m.start()]):
            taken.append((m.start(), m.end()))

    def emit(metric: str | None, value: float, unit: str, *, period: str | None = None,
             direction: str | None = None, raw: str, span: tuple[int, int]) -> None:
        out.append({"metric": metric, "value": value, "unit": unit,
                    "period": period, "direction": direction, "raw": raw})
        taken.append(span)

    # 1. Before→after transitions ("12 days → 4 days"): improvement class.
    for m in _ARROW_RE.finditer(text):
        before = float(m.group(1).replace(",", ""))
        after = float(m.group(3).replace(",", ""))
        unit = "days" if m.group(4).lower().startswith("day") else "months"
        direction = "improvement" if after < before else "degradation"
        emit(_label_before(text, m.start()), after, unit, direction=direction,
             raw=m.group(0), span=(m.start(), m.end()))

    # 2. Money (+ optional companion % change in a following parenthetical).
    for m in _MONEY_RE.finditer(text):
        if _overlaps(m.start(), m.end(), taken):
            continue
        value = parse_money(m.group(0))
        if value is None:
            continue
        metric = None
        after = re.match(r"\s+([A-Za-z][\w-]*)", text[m.end() :])
        if after and after.group(1).lower() in _MONEY_NOUNS:
            metric = after.group(1)
        if metric is None:
            metric = _label_before(text, m.start())
        emit(metric, value, "usd", period=_period_after(text, m.end()),
             raw=m.group(0), span=(m.start(), m.end()))
        companion = _COMPANION_PCT_RE.match(text, m.end())
        if companion:
            pct = float(companion.group(2))
            direction = "down" if companion.group(1) == "-" else "up"
            emit(metric, pct, "pct", direction=direction,
                 raw=f"{companion.group(1)}{companion.group(2)}%",
                 span=(companion.start(), companion.end()))

    # 3. Percents.
    for m in _PCT_RE.finditer(text):
        if _overlaps(m.start(), m.end(), taken):
            continue
        value = parse_percent(m.group(0)) or float(m.group(2))
        direction = None
        if m.group(1) == "+":
            direction = "up"
        elif m.group(1) == "-":
            direction = "down"
        else:
            direction = _direction_near(text, m.start(), m.end())
        emit(_label_before(text, m.start()), value, "pct",
             period=_period_after(text, m.end()), direction=direction,
             raw=m.group(0).strip(), span=(m.start(), m.end()))

    # 4. Star ratings ("0.8 stars below peer median").
    for m in _STARS_RE.finditer(text):
        if _overlaps(m.start(), m.end(), taken):
            continue
        metric = _label_before(text, m.start())
        direction = None
        comparator = _COMPARATOR_RE.match(text, m.end())
        if comparator:
            direction = "down" if comparator.group(1).lower() == "below" else "up"
            metric = metric or comparator.group(2).strip()
        emit(metric, float(m.group(1)), "stars", direction=direction,
             raw=m.group(0), span=(m.start(), m.end()))

    # 5. Entity counts ("905 branches", "1,800 users").
    for m in _COUNT_RE.finditer(text):
        if _overlaps(m.start(), m.end(), taken):
            continue
        emit(m.group(2).lower(), float(m.group(1).replace(",", "")), "count",
             raw=m.group(0), span=(m.start(), m.end()))

    # 6. Standalone durations not already consumed by a transition.
    for m in _DURATION_RE.finditer(text):
        if _overlaps(m.start(), m.end(), taken):
            continue
        unit = "days" if m.group(2).lower().startswith("day") else "months"
        emit(_label_before(text, m.start()), float(m.group(1)), unit,
             raw=m.group(0), span=(m.start(), m.end()))

    # 7. Ratios ("1.4x", "Texas ratio of 0.85").
    for m in _RATIO_RE.finditer(text):
        if _overlaps(m.start(), m.end(), taken):
            continue
        value = float(m.group(1) or m.group(2))
        emit(_label_before(text, m.start()), value, "ratio",
             raw=m.group(0), span=(m.start(), m.end()))

    out.sort(key=lambda item: text.find(item["raw"]))
    return out


def pick_annual_revenue_usd(text: str) -> float | None:
    """The entity's ANNUAL revenue in USD, period-aware (audit bug 5b).

    Runs :func:`extract_metrics`, keeps usd metrics whose label mentions
    revenue, and REJECTS any whose period is a quarter/half ("$1.9B in Q2
    2025" is not the annual figure). Returns the largest surviving annual
    figure, else ``None`` — never coerces a quarterly print into an annual
    field. A size-tier band edge can't leak in: bands are consumed upstream.
    """
    best: float | None = None
    for m in extract_metrics(text or ""):
        if m.get("unit") != "usd":
            continue
        if "revenue" not in str(m.get("metric") or "").lower():
            continue
        if is_quarterly(m.get("period")):
            continue
        v = m.get("value")
        if isinstance(v, int | float) and v > 1e6 and (best is None or v > best):
            best = float(v)
    return best


# --- year series ----------------------------------------------------------

_YEAR_KEY_RE = re.compile(r"(?:FY\s?)?((?:19|20)\d{2})")
_BARE_YEAR_VALUE_RE = re.compile(r"(?:FY\s?)?(?:19|20)\d{2}")
_SEGMENT_ROW_RE = re.compile(
    r"^\s*(?:FY\s?)?((?:19|20)\d{2})\s*(?:[:=\t]|[—–-]|\s)\s*(\S.*)$"  # noqa: RUF001
)


def _parse_series_value(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    if _BARE_YEAR_VALUE_RE.fullmatch(raw):
        return None  # "2021-2024"-style ranges / bare years are labels, not values
    sign = -1.0 if re.match(r"^\s*[-(]", raw) else 1.0
    value = parse_money(raw)
    if value is None:
        return None
    return sign * value


def extract_year_series(text_or_pairs: str | dict | Iterable[tuple]) -> dict[int, float]:
    """Align year→value ONLY when the year token is a standalone key/label.

    Accepts a prose/table string OR key-value pairs (dict / iterable of
    2-tuples). The guard that fixes the [2022, 2025] → [2023, 87.5] bug
    class: years are NEVER harvested out of value prose — a pair whose
    key is not a year contributes nothing (its value is not scanned),
    and a value that itself parses to a bare year (range endpoints like
    "2021-2024") is rejected.
    """
    series: dict[int, float] = {}
    if isinstance(text_or_pairs, str):
        segments = re.split(r"[\n|;]", text_or_pairs)
        for segment in segments:
            m = _SEGMENT_ROW_RE.match(segment)
            if not m:
                continue
            value = _parse_series_value(m.group(2))
            if value is not None:
                series[int(m.group(1))] = value
        return series

    pairs = text_or_pairs.items() if isinstance(text_or_pairs, dict) else text_or_pairs
    for key, raw_value in pairs:
        key_text = str(key).strip()
        km = _YEAR_KEY_RE.fullmatch(key_text)
        if not km:
            continue  # non-year key: value prose is NOT scanned for years
        if isinstance(raw_value, int | float):
            value = float(raw_value)
            # An integral value in the year range is almost certainly a
            # mis-keyed year, not a measurement — same bug class.
            if value.is_integer() and 1900 <= value <= 2099:
                continue
        else:
            parsed = _parse_series_value(str(raw_value))
            if parsed is None:
                continue
            value = parsed
        series[int(km.group(1))] = value
    return series


# ── Evidence-prose metric-year mining (2026-07-04 deep search) ─────────────
# The all-94 deep search found 67 clients whose multi-year financials live
# ONLY in evidence excerpts, in shapes the section-table parser can't see:
#   "Total assets $9,066,879K (Dec 31, 2024)"          raw-thousands + date
#   "Net income $34.9M (2024) vs $50.3M (2023)"        vs-comparison
#   "Sep 30, 2025 NCUA data: ... ~$9.24B total assets" date-first line
#   "grew from $2.286B in 2021 to $3.209B in 2025"     from/to prose
#   "total assets of $15.6 billion in 2023"            of-in prose
# extract_metric_year_pairs assembles {metric: {year: usd}} from them with
# a peer-institution guard (a line naming a DIFFERENT org is peer context,
# not this entity's series) and per-metric magnitude-consistency checks.

_EM_METRICS: tuple[tuple[str, str], ...] = (
    ("total_assets", r"total assets|assets under management"
                     r"|owned (?:and |& )?managed assets|earning assets?"
                     r"|\bEAOM\b|\bAUM\b"),
    ("net_income", r"net income"),
    ("deposits", r"total deposits|member(?:s'?)? shares|deposits"),
    ("revenue", r"total revenue|revenue"),
    ("loans", r"net loans|total loans|loan portfolio"),
)
_EM_MONEY = (
    r"[~≈]?\$\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(K|M|B|T|thousand|million|billion|trillion)?\b"
)
_EM_MONEY_RE = re.compile(_EM_MONEY)
_EM_MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12,
            "THOUSAND": 1e3, "MILLION": 1e6, "BILLION": 1e9, "TRILLION": 1e12}
_EM_YEAR = r"(?:19|20)\d{2}"
# "$V (Dec 31, 2024)" / "$V (2024)" / "$V in 2021" / "$V as of FY2023"
_EM_VAL_YEAR = re.compile(
    _EM_MONEY + r"[^.;\n]{0,30}?"
    r"(?:\(\s*(?:[A-Z][a-z]{2,8}\.?\s+\d{1,2},\s*)?(" + _EM_YEAR + r")\s*\)"
    r"|(?:\bin\b|\bas of\b|\bat\b|\bfor\b|\bFY)\s*(" + _EM_YEAR + r"))")
# "Sep 30, 2025 …: … $V" — year appears BEFORE the value on the same line.
_EM_YEAR_VAL = re.compile(
    r"\b(" + _EM_YEAR + r")\b[^.;\n$]{0,80}?" + _EM_MONEY)
# A capitalised org name ending in an FSI suffix — peer-line detector.
_EM_ORG = re.compile(
    r"\b((?:[A-Z][A-Za-z&'.-]+\s+){1,4}"
    r"(?:Credit Union|Bank(?:corp|shares)?|Financial|Insurance|Trust|"
    r"Bancorp(?:oration)?|Investments?))\b")
# NCUA / call-report raw-thousands convention (2026-07-06 deploy review):
# credit-union filings state "$518,000" MEANING $518M ("dollars in
# thousands"). A unitless $-figure on a line carrying one of these cues is
# in that convention — mined literally it produced net_income_m points of
# 518000/939000/66000 "M" (chemung/empower/global class).
_EM_THOUSANDS_CUE = re.compile(
    r"\bNCUA\b|call[- ]report|form\s*5300|\(?\s*in\s+thousands\s*\)?"
    r"|\(\$?000s?\)|\$000s?\b", re.I)
# unitless raw-thousands live in this band; outside it the literal reading
# is kept (a true $2,500 fee or a $12,000,000 figure is not the convention).
_EM_THOUSANDS_LO, _EM_THOUSANDS_HI = 1e4, 1e7


def _em_usd(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    return v * _EM_MULT.get((unit or "").upper(), 1.0)


def _em_is_peer_line(line: str, entity_tokens: set[str]) -> bool:
    """True when the line names an institution sharing NO token with the
    entity — its numbers are peer/benchmark context, not this series."""
    for m in _EM_ORG.finditer(line):
        org_tokens = {t.lower() for t in m.group(1).split()
                      if len(t) > 2 and t.lower() not in
                      {"credit", "union", "bank", "financial", "insurance",
                       "trust", "the", "and", "bancorp", "bancorporation",
                       "bankcorp", "bankshares", "investments", "investment"}}
        if org_tokens and not (org_tokens & entity_tokens):
            return True
    return False


def extract_metric_year_pairs(
    text: str, *, entity_name: str = "",
) -> dict[str, dict[int, float]]:
    """{metric: {year: usd_value}} mined from prose/evidence lines.

    Only pairs where the metric keyword sits within the same clause as the
    value; only years 2015-2035; a metric's series is dropped entirely when
    its values span >8x (mixed magnitudes = mixed sources). Lines naming a
    different institution are skipped (peer guard). Unitless figures on
    NCUA/call-report cue lines are read in the filings' raw-thousands
    convention ("$518,000" = $518M) — and a unitless value sitting ~1000x
    below a metric's unit-carrying cluster is harmonized the same way, so
    one series never mixes conventions."""
    ent_tokens = {t.lower() for t in re.findall(r"[A-Za-z]{3,}", entity_name)
                  if t.lower() not in {"credit", "union", "bank", "the",
                                       "financial", "insurance", "trust"}}
    out: dict[str, dict[int, float]] = {}
    unitless: dict[tuple[str, int], bool] = {}   # (metric, year) → no K/M/B/T
    for line in re.split(r"[\n]+", text or ""):
        if not line.strip() or (ent_tokens and _em_is_peer_line(line, ent_tokens)):
            continue
        thousands_line = bool(_EM_THOUSANDS_CUE.search(line))
        # keyword positions first; every value-year match then binds to its
        # NEAREST keyword within 90 chars — a fixed window per keyword
        # swallowed the previous clause's value ("…assets $9.1B (2024);
        # Net income $34.9M (2024)" credited $9.1B to net income).
        kw_hits: list[tuple[str, int, int]] = []      # (metric, start, end)
        for metric, kw in _EM_METRICS:
            for km in re.finditer(kw, line, re.IGNORECASE):
                kw_hits.append((metric, km.start(), km.end()))
        if not kw_hits:
            continue
        # (vstart, vend, year, usd, had_unit)
        matches: list[tuple[int, int, int, float, bool]] = []
        for m in _EM_VAL_YEAR.finditer(line):
            year = int(m.group(3) or m.group(4))
            if 2015 <= year <= 2035:
                matches.append((m.start(), m.end(), year,
                                _em_usd(m.group(1), m.group(2)),
                                bool(m.group(2))))
        if not matches:
            for m in _EM_YEAR_VAL.finditer(line):
                year = int(m.group(1))
                if 2015 <= year <= 2035:
                    # bind on the VALUE's own span, not the whole match:
                    # with the year-through-value span, a keyword sitting
                    # BETWEEN them ("Dec 31, 2024 … net income $518,000")
                    # was neither preceding nor following, so the value
                    # bound to the NEXT clause's keyword (NCUA class,
                    # 2026-07-06 deploy review).
                    matches.append((m.start(2) - 1, m.end(), year,
                                    _em_usd(m.group(2), m.group(3)),
                                    bool(m.group(3))))
        # Single-year line sweep: "…2024 …: net income $A; total assets $B."
        # carries ONE year for several ';'-separated values — the year-gap
        # regex can't cross the ';', so trailing values were dropped. Any
        # unconsumed $-value on a one-year line joins with that year; the
        # keyword binding below still decides (or rejects) its metric.
        if matches and len({y for _, _, y, _, _ in matches}) == 1:
            year1 = matches[0][2]
            spans = [(s, e) for s, e, *_ in matches]
            for vm in _EM_MONEY_RE.finditer(line):
                if any(s <= vm.start() < e for s, e in spans):
                    continue
                matches.append((vm.start(), vm.end(), year1,
                                _em_usd(vm.group(1), vm.group(2)),
                                bool(vm.group(2))))
        for vstart, vend, year, usd, had_unit in matches:
            if (not had_unit and thousands_line
                    and _EM_THOUSANDS_LO <= usd < _EM_THOUSANDS_HI):
                usd *= 1e3    # the filing's own "in thousands" convention
                had_unit = True
            # A metric label directly PRECEDES its value in financial prose
            # ("Total assets $9.1B"); the following-keyword form is the
            # date-first rollup ("… ~$9.24B total assets"). Preceding wins.
            preceding = [(mt, vstart - kend) for mt, kstart, kend in kw_hits
                         if kend <= vstart and vstart - kend <= 60]
            following = [(mt, kstart - vend) for mt, kstart, kend in kw_hits
                         if kstart >= vend and kstart - vend <= 60]
            pick = (min(preceding, key=lambda t: t[1]) if preceding
                    else min(following, key=lambda t: t[1]) if following
                    else None)
            if pick is not None and year not in out.get(pick[0], {}):
                out.setdefault(pick[0], {})[year] = usd
                unitless[(pick[0], year)] = not had_unit
    # convention harmonization: a UNITLESS point sitting ~1000x below a
    # metric's unit-carrying cluster is the raw-thousands convention read
    # literally — lift it into the cluster's convention (never the reverse:
    # unit-carrying figures are trusted as written).
    for metric, series in out.items():
        anchored = [v for y, v in series.items() if not unitless.get((metric, y))]
        if not anchored:
            continue
        med = sorted(anchored)[len(anchored) // 2]
        for y, v in list(series.items()):
            if unitless.get((metric, y)) and v > 0 and 200 <= med / v <= 5000:
                series[y] = v * 1e3
    # magnitude-consistency: a series mixing $34.9M and $9.1B under one
    # metric came from different statements — drop the outliers, keep the
    # dominant magnitude cluster (or drop the metric if no cluster of ≥2).
    cleaned: dict[str, dict[int, float]] = {}
    for metric, series in out.items():
        if len(series) < 2:
            cleaned[metric] = series
            continue
        vals = sorted(series.values())
        med = vals[len(vals) // 2]
        keep = {y: v for y, v in series.items()
                if med / 8 <= v <= med * 8}
        cleaned[metric] = keep if len(keep) >= 2 else {}
    return {m: s for m, s in cleaned.items() if s}
