"""Parse `08_appendices/entity_profile.json` into firmographics fields.

Per the v2-QA under-leveraged matrix §C9 finding (2026-06-07), some
packages (Calprivate among the 5 real fixtures; likely future variants)
ship a richly-structured `entity_profile.json` alongside the Client
Profile DOCX. The JSON carries:

  - corporate_identity: entity_legal_name, doing_business_as,
    holding_company, ticker, founded (ISO date), headquarters,
    branch_count, geographic_focus, employee_count, …
  - regulatory_standing: primary_regulator, secondary_regulator,
    fdic_certificate_number, charter_type, fed_member,
    enforcement_actions_found, …
  - financial_baseline: per-quarter financials (revenue, ROA, NIM,
    total_assets_usd_b, …)
  - subvertical_classification: selected sv code, size_tier,
    confidence breakdown, …
  - leadership_snapshot: CEO/CFO/CIO/CTO with name, title, tenure,
    background.

The DOCX regex extractor in `client_profile.py` covers only a fragile
subset (legal_name, hq, primary_regulator, employees_approx). When the
structured JSON is present, prefer it as authoritative; the DOCX path
remains as the fallback when this file is absent (Alma / WSFS / Nicola
/ Odlum among the 5 fixtures).

End-user impact when applied:
  - D5 Context "About" panel populates with richer firmographics
    (ticker, founded date, branch count) on packages that ship the
    JSON.
  - ClientOverview FirmographicsRows show ticker + branches + employee
    count instead of the regex-extracted subset.
  - Migration to richer firmographics is additive — packages without
    the JSON keep the current behavior.
"""
from __future__ import annotations

import contextlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _safe_str(v: Any, max_len: int = 200) -> str | None:
    """Coerce a value to a non-empty string, truncating defensively."""
    if v is None:
        return None
    s = str(v).strip()
    return s[:max_len] if s else None


def _founded_year_from_iso(value: str | None) -> int | None:
    """Extract YYYY from an ISO date like '2006-12-18' or '2006'."""
    if not value:
        return None
    m = re.match(r"(\d{4})", str(value))
    if not m:
        return None
    year = int(m.group(1))
    # Sanity bound: reject years before banking era + after current.
    if 1700 <= year <= datetime.now().year + 1:
        return year
    return None


def _format_total_assets(financial_baseline: dict[str, Any]) -> str | None:
    """Derive a human-readable `total_assets` string from the latest
    quarterly financials. The canonical Firmographics.total_assets is
    a string (e.g. `$2.58B`) so React renders verbatim.
    """
    # Try most-recent quarter first; older quarters are fallbacks.
    for q in (
        "q4_2025_total_assets_usd_b",
        "q3_2025_total_assets_usd_b",
        "q2_2025_total_assets_usd_b",
        "q1_2025_total_assets_usd_b",
        "fy2024_total_assets_usd_b",
    ):
        v = financial_baseline.get(q)
        if v is None:
            continue
        try:
            return f"${float(v):.2f}B"
        except (TypeError, ValueError):
            continue
    # `financials` wrapper variant (FNBO): raw-dollar integers under
    # year-stamped keys ({"total_assets_2024": 30780000000}). Newest
    # year first; format $30.8B / $450M.
    for key in (
        "total_assets", "total_assets_latest", "total_assets_2025",
        "total_assets_2024", "total_assets_2023",
    ):
        v = financial_baseline.get(key)
        if v is None:
            continue
        if isinstance(v, str) and v.strip():
            return v.strip()[:40]
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if n >= 1e9:
            return f"${n / 1e9:.1f}B"
        if n >= 1e6:
            return f"${n / 1e6:.0f}M"
    return None


def _format_employees_approx(corporate_identity: dict[str, Any]) -> str | None:
    """`employees_approx` is a STRING field on Firmographics (the
    DOCX regex extractor returns strings like '1,450'). Match that
    contract by stringifying the integer with thousands separators.
    """
    raw = (
        corporate_identity.get("employee_count")
        or corporate_identity.get("employees")
    )
    if raw is None:
        return None
    try:
        n = int(raw)
        if n <= 0:
            return None
        return f"{n:,}"
    except (TypeError, ValueError):
        return _safe_str(raw)


def parse_entity_profile_json(path: Path) -> dict[str, Any]:
    """Read `entity_profile.json` and emit a flat dict matching the
    `Firmographics` field names. Unknown / missing fields are simply
    omitted; caller merges into the existing firm dict.

    Handles BOTH schema variants found across the corpus:

      1. NESTED (Calprivate `08_appendices/entity_profile.json`):
         `{corporate_identity:{…}, regulatory_standing:{…},
           financial_baseline:{q4_2025_total_assets_usd_b:…},
           leadership_snapshot:{…}}`.
      2. FLAT (the 41 standalone `entity_profile.json` files —
         01_evidence / 02_research_workbook / 08_appendices):
         `{entity_name, ticker, entity_type, headquarters,
           total_assets_approx, size_tier, sub_vertical,
           primary_regulator, fdic_insured, affiliate_banks,
           key_context, website}`.

    Returns an EMPTY dict when the file is absent / malformed so the
    caller can treat "no JSON" identically to "no useful fields".
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}

    # Schema discriminator: the nested variant nests firmographics under
    # `corporate_identity`; the flat variant carries `entity_name` (or
    # `total_assets_approx`) at the top level. Prefer nested when its
    # signature key is present so the richer per-quarter financials win.
    if "corporate_identity" not in data and (
        "entity_name" in data or "total_assets_approx" in data
    ):
        return _parse_flat_entity_profile(data)

    # Source dicts, broadened across the corpus variants:
    #   corporate_identity (Calprivate/OneDigital), `entity` wrapper
    #   (Amarillo: {entity:{legal_name,…}}), regulatory_standing OR
    #   regulatory_standing_summary, scale_metrics.
    # Firmographics live under different wrapper keys across the corpus:
    # `entity` (Amarillo), `entity_identity` (Corporate America),
    # `corporate_identity` (Calprivate/OneDigital). Merge so the more
    # specific key wins.
    ci: dict[str, Any] = {}
    for wrapper in ("entity", "entity_identity", "corporate_identity"):
        if isinstance(data.get(wrapper), dict):
            ci = {**ci, **data[wrapper]}
    rs = (
        data.get("regulatory_standing")
        or data.get("regulatory_standing_summary")
        or data.get("regulatory")
        or {}
    )
    # `financials` is the FNBO/Wintrust nested wrapper (2026-06-10):
    # {total_assets_2024: 30780000000, employees: 5000, …} — numbers,
    # not strings.
    fb = data.get("financial_baseline") or data.get("financials") or {}
    sm = data.get("scale_metrics") or {}

    out: dict[str, Any] = {}

    # legal_name across the observed key spellings.
    legal = (
        _safe_str(ci.get("entity_legal_name"))
        or _safe_str(ci.get("legal_name"))
        or _safe_str(ci.get("doing_business_as"))
        or _safe_str(ci.get("primary_brand"))
        or _safe_str(ci.get("legal_parent_entity"))
    )
    if legal:
        out["legal_name"] = legal

    ticker = _safe_str(ci.get("ticker") or ci.get("stock_ticker"))
    if ticker:
        out["ticker"] = ticker

    hq = _safe_str(
        ci.get("headquarters") or ci.get("hq")
        or ci.get("hq_address")
        or ci.get("headquarters_location") or sm.get("headquarters")
    )
    if hq:
        out["hq"] = hq

    founded = _founded_year_from_iso(ci.get("founded") or ci.get("founded_year"))
    if founded is not None:
        out["founded"] = founded

    employees = (
        _format_employees_approx(ci)
        or _format_employees_approx(sm)
        or _format_employees_approx(fb)
    )
    if employees:
        out["employees_approx"] = employees

    regulator = _safe_str(
        rs.get("primary_regulator") or rs.get("regulator")
        or ci.get("primary_regulator") or ci.get("regulatory_body")
    )
    if regulator:
        out["primary_regulator"] = regulator

    total_assets = (
        _format_total_assets(fb)
        or _safe_str(ci.get("total_assets_approx"))
        or _safe_str(sm.get("total_assets") or sm.get("total_assets_approx"))
    )
    if total_assets:
        out["total_assets"] = total_assets

    # Branches — extra field surfaced via `extra='allow'`. The React
    # Overview FirmographicsRows reads it via `firm.branches`.
    branches = (
        ci.get("branch_count") or sm.get("branch_count") or sm.get("branches")
    )
    if branches is not None:
        with contextlib.suppress(TypeError, ValueError):
            # Tolerate thousands separators ("1,253") so a large network is
            # captured rather than silently dropped by int("1,253").
            out["branches"] = str(int(str(branches).replace(",", "").strip()))

    return out


def _parse_flat_entity_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Map the FLAT standalone `entity_profile.json` schema onto
    `Firmographics` field names. Values in this variant are already
    human-readable strings (e.g. `total_assets_approx: "$87B (as of
    Q4 2024)"`) so they pass through verbatim. Canonical fields land on
    named keys; the rest ride `Firmographics(extra='allow')`.
    """
    out: dict[str, Any] = {}

    legal = _safe_str(data.get("entity_name"))
    if legal:
        out["legal_name"] = legal

    ticker = _safe_str(data.get("ticker"))
    # Some flat profiles use "N/A" / "Private" sentinels — keep only real tickers.
    if ticker and ticker.upper() not in ("N/A", "NA", "PRIVATE", "NONE", "-"):
        out["ticker"] = ticker

    hq = _safe_str(data.get("headquarters"))
    if hq:
        out["hq"] = hq

    # Asset/scale fields — the corpus census (2026-06-10) shows 40+
    # spellings across the flat profiles; first non-empty alias wins.
    def _first(*keys: str) -> str | None:
        for k in keys:
            v = _safe_str(data.get(k))
            if v and v.upper() not in ("N/A", "NA", "NONE", "-", "TBD"):
                return v
        return None

    total_assets = _first(
        "total_assets_approx", "total_assets", "total_assets_latest",
        "total_assets_2025", "total_assets_2024", "total_assets_dec2025_B",
        "assets_approx", "assets",
        "assets_under_administration", "aum",
    )
    if total_assets:
        out["total_assets"] = total_assets

    employees = _first(
        "employees", "employee_count", "employee_count_exact",
        "employee_count_estimate", "employee_count_range",
    )
    if employees:
        out["employees_approx"] = employees

    branches = _first("branches", "branch_count")
    if branches:
        out["branches"] = branches

    deposits = _first("total_deposits", "deposits", "deposits_2025")
    if deposits:
        out["total_deposits"] = deposits

    regulator = _safe_str(data.get("primary_regulator"))
    if regulator:
        out["primary_regulator"] = regulator

    # Extra (extra='allow') context fields the Overview / Context panels read.
    for src_key, dst_key in (
        ("sub_vertical", "sub_vertical"),
        ("size_tier", "size_tier"),
        ("entity_type", "entity_type"),
        ("key_context", "key_context"),
        ("website", "website"),
    ):
        v = _safe_str(data.get(src_key), max_len=600)
        if v:
            out[dst_key] = v

    affiliates = data.get("affiliate_banks")
    if isinstance(affiliates, list) and affiliates:
        cleaned = [s for s in (_safe_str(a) for a in affiliates) if s]
        if cleaned:
            out["affiliate_banks"] = cleaned

    return out


def parse_financial_baseline_json(path: Path) -> dict[str, Any]:
    """Read a STANDALONE `financial_baseline.json` (31 across the corpus)
    and emit a `Firmographics`-shaped dict. This flat file is the only
    structured source for D1 firmographics + D5 financials on the
    packages that ship it; it was previously read by nothing.

    Flat schema (verbatim human-readable strings):
      `{entity_name, as_of, total_assets, total_deposits, net_income_fy,
        roe, efficiency_ratio, branches, employees, source}`.

    Canonical Firmographics fields (`total_assets`, `employees_approx`)
    are emitted on their named keys; the financial extras
    (`total_deposits`, `net_income`, `roe`, `efficiency_ratio`,
    `branches`, `financials_as_of`) ride `extra='allow'` and power the
    D5 Context financial-trajectory + regulatory-standing panels.

    Returns {} when absent / malformed (treated as "no fields").
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}

    out: dict[str, Any] = {}
    field_map = (
        ("total_assets", "total_assets"),
        ("total_deposits", "total_deposits"),
        ("net_income_fy", "net_income"),
        ("roe", "roe"),
        ("efficiency_ratio", "efficiency_ratio"),
        ("branches", "branches"),
        ("employees", "employees_approx"),
        ("as_of", "financials_as_of"),
    )
    for src_key, dst_key in field_map:
        v = _safe_str(data.get(src_key))
        if v:
            out[dst_key] = v

    # `financial_trend` nested schema (OZK et al., 2026-06-10 census):
    # {"financial_trend": {"total_assets": {"2023": 34240000000, ...,
    #   "cagr_3yr": "9.5%"}, "deposits": {...}, "net_income": {...}},
    #  "key_ratios": {"roaa": 1.7, ...}}. Numbers are raw dollars.
    # Emit: total_assets (latest year, $X.XB) + cagr, and a
    # financial_highlights {series, metrics-as-scalars, lines} blob that
    # services.context_extras.financials_view renders as the D5
    # multi-year trajectory.
    trend = data.get("financial_trend")
    if isinstance(trend, dict):
        def _fmt_usd(n: float) -> str:
            if n >= 1e9:
                return f"${n / 1e9:.1f}B"
            if n >= 1e6:
                return f"${n / 1e6:.0f}M"
            return f"${n:,.0f}"

        fh: dict[str, Any] = {}
        lines: list[str] = []
        ta = trend.get("total_assets")
        if isinstance(ta, dict):
            years = {
                k: float(v) for k, v in ta.items()
                if k.isdigit() and isinstance(v, int | float)
            }
            if years:
                fh["series"] = dict(sorted(years.items()))
                latest = max(years)
                out.setdefault("total_assets", _fmt_usd(years[latest]))
                lines.append(
                    "Total assets: " + " → ".join(
                        f"{y} {_fmt_usd(v)}"
                        for y, v in sorted(years.items())
                    )
                )
            cagr = _safe_str(ta.get("cagr_3yr") or ta.get("cagr"))
            if cagr:
                out.setdefault("cagr", cagr)
                fh["cagr_3yr"] = cagr
        for metric in ("deposits", "net_income", "loans"):
            md = trend.get(metric)
            if not isinstance(md, dict):
                continue
            yrs = {
                k: float(v) for k, v in md.items()
                if k.isdigit() and isinstance(v, int | float)
            }
            if yrs:
                latest = max(yrs)
                fh[f"{metric}_{latest}"] = _fmt_usd(yrs[latest])
                lines.append(
                    f"{metric.replace('_', ' ').title()}: " + " → ".join(
                        f"{y} {_fmt_usd(v)}" for y, v in sorted(yrs.items())
                    )
                )
            t = _safe_str(md.get("trend"))
            if t:
                lines.append(
                    f"{metric.replace('_', ' ').title()}: {t}"
                )
        ratios = data.get("key_ratios")
        if isinstance(ratios, dict):
            for k, v in ratios.items():
                sv = _safe_str(v)
                if sv:
                    fh.setdefault(k, sv)
        if lines:
            fh["lines"] = lines
        if fh:
            out["financial_highlights"] = fh
    return out


def parse_entity_profile_leadership(path: Path) -> list[dict[str, Any]]:
    """Extract leadership from `entity_profile.leadership_snapshot`.

    Returns a list of dicts with `name` + `title` keys, suitable for
    LeadershipPerson construction. Empty list when the snapshot is
    absent / malformed.

    The JSON shape is `{ceo: {...}, cfo: {...}, cio: {...}, ...}` with
    each role being a single executive object containing `name` +
    `title` + `tenure_started_role` + `background` + `digital_signal`.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    snapshot = data.get("leadership_snapshot") or {}
    if not isinstance(snapshot, dict):
        return []

    out: list[dict[str, Any]] = []
    for role_key, person in snapshot.items():
        if not isinstance(person, dict):
            continue
        name = _safe_str(person.get("name"))
        if not name:
            continue
        title = _safe_str(person.get("title")) or role_key.upper()
        out.append({"name": name, "title": title})
    return out
