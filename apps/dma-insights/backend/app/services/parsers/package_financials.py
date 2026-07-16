"""Parse the D5 financial-trajectory + sentiment artifacts.

Both surfaces are dead corpus-wide today: the Context endpoint reads
`firmographics.financial_highlights` (→ `financials_view`) and
`firmographics.sentiment`, but persistence never wrote either column, and
the structured sources were unread:

  - `A#_Financial_Trends.csv` (14): Metric, 2020, 2021, …, Source, Tier —
    a real multi-year series. (The client-research-report DOCX also carries
    flat financial highlights via client_profile; the CSV is preferred when
    present because it is multi-year.)
  - `A#_sentiment_data.csv` (20): Source, Rating, Volume, Key_Themes, Trend,
    Capability_Signal.

`parse_financial_trends_csv` emits a dict shaped for `financials_view`
(`series` keyed by year for the headline metric + the latest value of every
metric); `parse_sentiment_csv` emits `{sources:[…]}`. Pure / no DB.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

# A header cell is a year column if it CONTAINS a 4-digit year — matches a
# bare "2024", an "FY2024", and a "2024_Q3" alike (quarters of the same year
# collapse to that year; last write wins).
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_TOTAL_ASSETS_RE = re.compile(r"total[_ ]?assets|\baum\b", re.IGNORECASE)
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _num(raw: str) -> float | None:
    """Coerce '$6.41B' / '18.6%' / '5,840' → float (B/M/K scaled)."""
    if raw is None:
        return None
    s = str(raw).strip()
    m = _NUM_RE.search(s.replace(",", ""))
    if not m:
        return None
    try:
        val = float(m.group(0))
    except ValueError:
        return None
    tail = s[m.end():].lstrip()
    if s.upper().endswith("B") or "B" in tail[:2].upper():
        pass  # keep $B unit as-is (series is self-consistent per metric)
    return val


def _read_csv_lines(path: Path) -> list[str]:
    try:
        return [
            ln for ln in path.read_text().splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
    except OSError:
        return []


def parse_financial_trends_csv(path: Path) -> dict[str, Any]:
    """Multi-year financial series → financials_view-shaped dict.

    Headline metric (prefers Total Assets) drives the `series` year axis;
    every metric's latest value is surfaced as a scalar `metric: value`.
    """
    if not path.exists():
        return {}
    lines = _read_csv_lines(path)
    if not lines:
        return {}
    reader = csv.reader(lines)
    rows = list(reader)
    if len(rows) < 2:
        return {}
    header = rows[0]
    year_cols: list[tuple[int, int]] = []
    for i, h in enumerate(header):
        m = _YEAR_RE.search(h or "")
        if m:
            year_cols.append((i, int(m.group(0))))
    metric_col = 0

    out: dict[str, Any] = {}
    metrics: list[tuple[str, dict[int, float], str]] = []
    for r in rows[1:]:
        if not r or len(r) <= metric_col:
            continue
        name = (r[metric_col] or "").strip()
        if not name:
            continue
        by_year: dict[int, float] = {}
        latest_str = ""
        for ci, yr in year_cols:
            if ci < len(r):
                cell = (r[ci] or "").strip()
                v = _num(cell)
                if v is not None:
                    by_year[yr] = v
                    latest_str = cell
        if by_year:
            metrics.append((name, by_year, latest_str))
            out[name] = f"{latest_str} ({max(by_year)})"

    if not metrics:
        # Single-period variant: `Metric, Value, …` (no year columns) — no
        # trajectory, but the figures are real. Surface them as scalar
        # `metrics` so the D5 financials card still renders.
        val_col = next(
            (i for i, h in enumerate(header)
             if str(h or "").strip().lower() in ("value", "latest", "current")),
            None,
        )
        if val_col is not None:
            for r in rows[1:]:
                if not r or metric_col >= len(r) or val_col >= len(r):
                    continue
                name = (r[metric_col] or "").strip()
                val = (r[val_col] or "").strip()
                if name and val:
                    out[name] = val
        return out
    # Headline series: prefer a Total-Assets-like metric, else the one with
    # the most year points.
    headline = next(
        (m for m in metrics if _TOTAL_ASSETS_RE.search(m[0])),
        max(metrics, key=lambda m: len(m[1])),
    )
    out["series"] = {str(y): headline[1][y] for y in sorted(headline[1])}
    return out


def parse_sentiment_csv(path: Path) -> dict[str, Any]:
    """`A#_sentiment_data.csv` → {sources:[{source, rating, volume, themes,
    trend, signal}]}. Returns {} when empty."""
    if not path.exists():
        return {}
    lines = _read_csv_lines(path)
    if not lines:
        return {}
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        return {}
    norm = {re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_"): h for h in reader.fieldnames}

    def col(*names: str) -> str | None:
        for n in names:
            if n in norm:
                return norm[n]
        return None

    c_src = col("source") or reader.fieldnames[0]
    c_rate, c_vol = col("rating", "score"), col("volume")
    c_theme = col("key_themes", "themes")
    c_trend, c_sig = col("trend"), col("capability_signal", "signal")

    sources: list[dict[str, Any]] = []
    for row in reader:
        src = (row.get(c_src) or "").strip()
        if not src:
            continue
        entry = {"source": src}
        for key, c in (("rating", c_rate), ("volume", c_vol), ("themes", c_theme),
                       ("trend", c_trend), ("signal", c_sig)):
            if c and (val := (row.get(c) or "").strip()):
                entry[key] = val
        sources.append(entry)
    return {"sources": sources} if sources else {}


def _first_match(root: Path, patterns: tuple[str, ...]) -> Path | None:
    for pat in patterns:
        for p in sorted(root.glob(pat)):
            if p.is_file():
                return p
    return None


def load_financial_trends(root: Path) -> dict[str, Any]:
    p = _first_match(root, (
        "**/A[0-9]*[Ff]inancial*[Tt]rends*.csv",
        "**/*[Ff]inancial_[Tt]rends*.csv",
    ))
    return parse_financial_trends_csv(p) if p else {}


def load_sentiment(root: Path) -> dict[str, Any]:
    p = _first_match(root, (
        "**/A[0-9]*[Ss]entiment*.csv",
        "**/*[Ss]entiment_data*.csv",
        "**/*[Ss]entiment*.csv",
    ))
    return parse_sentiment_csv(p) if p else {}


# A "metric key" must be a metric NAME, not a slugged prose sentence. The
# 2026-07 audit found prose-keys shipping to the D1/D5 financial cards
# ("this_revenue_mix_shift_toward_recurring_fee_income_is_the_execution_…",
# "mce_evidence_shows_that_…", subcap/E-ID slugs like "e-p1c1", junk "vg").
# They die HERE, at the parse source (plan 4.6/8.4).
_PROSE_KEY_RE = re.compile(
    r"_(?:is|are|was|were|shows?|show_that|has|have|but|toward|lifted|reduced)_"
    r"|^(?:this|the|these|those|mce|note)_"
    r"|^e-[a-z0-9]{2,6}$"          # E-ID / subcap slugs (e-b1, e-p1c1)
    r"|^[a-z]{1,3}$",              # 1-3 letter junk keys ("vg")
    re.IGNORECASE,
)


def is_sane_metric_key(key: object) -> bool:
    """True only for a plausible metric name (bounded length/word-count, not
    a slugged prose sentence, not an E-ID/subcap slug)."""
    k = str(key or "").strip()
    if not k or len(k) > 40:
        return False
    if _PROSE_KEY_RE.search(k):
        return False
    return len(re.split(r"[_\s]+", k)) <= 5


def sanitize_metric_keys(d: dict[str, Any]) -> dict[str, Any]:
    """Drop prose-keys / junk-slug metrics; values that are themselves prose
    (>120 chars) are dropped too. `lines`/`series` payloads pass through."""
    out: dict[str, Any] = {}
    for k, v in (d or {}).items():
        if k in ("lines", "series", "metrics", "trajectory"):
            out[k] = v
            continue
        if not is_sane_metric_key(k):
            continue
        if isinstance(v, str) and len(v) > 120:
            continue
        out[k] = v
    return out


def load_financial_baseline(root: Path) -> dict[str, Any]:
    """Fallback financials from `financial_baseline.json` (flat assets /
    deposits / net_income / roe / efficiency / branches) → financials_view
    `metrics` when no multi-year trends CSV ships. The figures are real
    (FDIC/UBPR-sourced); financials_view surfaces them as scalar metrics.
    Prose-keys die at this source (`sanitize_metric_keys`)."""
    import json as _json

    from app.services.parsers.entity_profile import parse_financial_baseline_json
    for p in sorted(root.glob("**/financial_baseline.json")):
        try:
            fields = parse_financial_baseline_json(p)
        except Exception:
            fields = {}
        if fields:
            return sanitize_metric_keys(fields)
        # Nested filing variant (Amarillo): mine top-level scalar metrics.
        try:
            d = _json.loads(p.read_text())
        except (OSError, _json.JSONDecodeError):
            continue
        if isinstance(d, dict):
            out = sanitize_metric_keys({
                k: v for k, v in d.items()
                if isinstance(v, str | int | float)
                and k not in ("run_id", "entity", "as_of", "source",
                              "data_source_primary", "filing_currency", "notes")
            })
            if out:
                return out
    return {}


_SENT_SKIP = frozenset({"claim_label", "evidence_ids", "source", "as_of"})


def sentiment_from_entity_profile(root: Path) -> dict[str, Any]:
    """Mine the `sentiment` block some entity_profile.json files carry
    (Glassdoor / Indeed / app ratings / press themes) into the
    {sources:[…]} grid shape. Heterogeneous across the corpus, so each
    top-level key becomes one source row with a readable value."""
    import json as _json
    for p in sorted(root.glob("**/entity_profile.json")):
        try:
            d = _json.loads(p.read_text())
        except (OSError, _json.JSONDecodeError):
            continue
        raw = d.get("sentiment") if isinstance(d, dict) else None
        if not isinstance(raw, dict) or not raw:
            continue
        sources: list[dict[str, Any]] = []
        for k, v in raw.items():
            if k in _SENT_SKIP or v in (None, "", [], {}):
                continue
            label = k.replace("_", " ").title()
            if isinstance(v, dict):
                rating = next(
                    (str(v[x]) for x in v
                     if any(t in x.lower() for t in ("rating", "score", "approval"))),
                    None,
                )
                note = next(
                    (str(v[x]) for x in v
                     if x.lower() in ("notes", "summary", "perception",
                                      "public_perception", "sentiment")),
                    None,
                )
                entry: dict[str, Any] = {"source": label}
                if rating:
                    entry["rating"] = rating
                entry["signal"] = (note or ", ".join(
                    f"{x}: {v[x]}" for x in list(v)[:3]))[:220]
                sources.append(entry)
            elif isinstance(v, list):
                sources.append({"source": label,
                                "themes": "; ".join(str(x) for x in v[:4])[:220]})
            else:
                sources.append({"source": label, "signal": str(v)[:220]})
        if sources:
            return {"sources": sources}
    return {}
