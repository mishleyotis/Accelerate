"""Catalogue-grounded platform↔subcap affinity from the v7 L3/L4 layers.

The fit engine's addressability signal had two rungs: catalogue keyword
tags (measured ~11% precise on the 94-client corpus) and the miniLM +
cross-encoder semantic tier (precise but recall-limited to what a subcap
NAME expresses). The v7.0 workbooks ship a third, strictly better rung
the loader now promotes: ``ccg_l4_features`` — curated subcap → L3
platform feature links (12k rows, 840 subcaps) joined to
``ccg_l3_platforms`` for vendor identity. A subcap linked to an L3
platform of a scored family is addressable BY CATALOGUE DESIGN, with the
named features as the receipts.

This module is framework-free: :func:`build_catalogue_affinity` is pure
(rows in → affinity out) so the engine tests build inputs by hand;
:func:`load_catalogue_affinity` is the one async DB touch, memoized per
catalogue version (the L4 layer is version-stable, not run-varying).

Affinity is graded by feature depth, not binary: ``sqrt(n_features/8)``
capped at 1.0 — one linked feature ≈ 0.35, four ≈ 0.7, eight+ = full
weight — so a platform with one tangential feature ranks below one the
catalogue maps a whole feature set onto.
"""
from __future__ import annotations

import re
from typing import Any

# L3 vendor/platform → scored platform family. Kept in lockstep with
# PLATFORM_FAMILY_PATTERNS (platform_fit_data) / SCORED_PLATFORM_FAMILIES
# (TechStackPage.tsx), but matched against the L3 reference's vendor AND
# platform_name fields ("Salesforce / MuleSoft", "Salesforce / Tableau"
# rows belong to both parents; first match on the ORDER below wins for
# the slash-joined vendor, so put the more specific family first).
_FAMILY_RES: list[tuple[str, re.Pattern[str]]] = [
    ("tableau", re.compile(r"\btableau\b(?!\s*crm)", re.I)),
    ("databricks", re.compile(r"databricks", re.I)),
    ("twilio", re.compile(r"twilio|\bsegment\b", re.I)),
    ("ncino", re.compile(r"ncino", re.I)),
    ("salesforce", re.compile(
        r"salesforce|mulesoft|tableau\s*crm|marketing cloud|data cloud", re.I)),
]

# Full catalogue weight at this many linked L4 features.
_DEPTH_FULL = 8.0

_CACHE: dict[str, dict[str, dict[str, dict]]] = {}
# Companion cache: per-family per-L3 aggregates (the sub-product grain the
# family-grain _CACHE discards). Keyed by the same catalogue version.
_L3_CACHE: dict[str, dict[str, dict[str, dict]]] = {}

# A genuine INTEGRATION/CONNECTIVITY vehicle — the product a customer stands
# up to wire a new platform into an installed incumbent (2026-07-14
# solutioning audit). Matched against the L3 category AND platform_name.
# Deliberately NARROW: it must name a connectivity product (MuleSoft
# Anypoint/Composer/DataGraph, Data Cloud/CDP, Twilio Segment, a *Connect*
# ingestion layer), NOT a platform's generic headline — the first cut of
# this regex matched "data platform" and mislabelled "Databricks Data
# Intelligence Platform" as the vehicle to bridge Databricks to itself
# (stress test, american-airlines-federa). Bare "platform"/"lakehouse"/
# "data platform" no longer qualify.
_INTEGRATION_CATEGORY_RE = re.compile(
    r"ipaas|\bintegration\b|\bcdp\b|data\s*cloud|\bsegment\b|anypoint|"
    r"composer|datagraph|\bconnect\b|integration\s*gateway", re.I)


def families_for_l3(vendor: str | None, platform_name: str | None) -> list[str]:
    """Every scored family an L3 row belongs to (slash-joined vendors like
    "Salesforce / Tableau" map to both). The two fields are matched
    SEPARATELY — concatenating them fabricates adjacencies (vendor
    "… / Tableau" + product "CRM Analytics" would read as "Tableau CRM",
    tripping the negative lookahead that keeps the Salesforce-embedded
    Tableau CRM product out of the tableau family)."""
    return [fam for fam, rx in _FAMILY_RES
            if rx.search(vendor or "") or rx.search(platform_name or "")]


def build_catalogue_affinity(
    rows: list[tuple[str, str | None, str | None, str | None]],
) -> dict[str, dict[str, dict]]:
    """Pure fold: ``(subcap_id, vendor, platform_name, feature_name)`` rows →
    ``{platform_id: {subcap_id: {"affinity": float, "features": [names]}}}``.

    Affinity grades on linked-feature depth (sqrt(n/8), capped 1.0);
    feature names keep sheet order (curated), deduped, capped at 6.
    """
    counts: dict[str, dict[str, int]] = {}
    feats: dict[str, dict[str, list[str]]] = {}
    for sid, vendor, pname, fname in rows:
        if not sid:
            continue
        for fam in families_for_l3(vendor, pname):
            counts.setdefault(fam, {})[sid] = counts.get(fam, {}).get(sid, 0) + 1
            bucket = feats.setdefault(fam, {}).setdefault(sid, [])
            f = (fname or "").strip()
            if f and f not in bucket and len(bucket) < 6:
                bucket.append(f)
    out: dict[str, dict[str, dict]] = {}
    for fam, by_sid in counts.items():
        out[fam] = {
            sid: {
                "affinity": round(min(1.0, (n / _DEPTH_FULL) ** 0.5), 4),
                "features": feats.get(fam, {}).get(sid, []),
            }
            for sid, n in by_sid.items()
        }
    return out


def build_l3_affinity(
    rows: list[tuple[str, str | None, str | None, str | None, str | None, str | None]],
) -> dict[str, dict[str, dict]]:
    """Per-family per-L3 aggregates — the sub-product grain the family-grain
    :func:`build_catalogue_affinity` sums away (2026-07-14 solutioning audit:
    for a bank's data-governance gaps v7 maps Data Cloud 12 features >
    Databricks Unity Catalog 7 > MuleSoft 2, but the family rollup credited
    "databricks" for its 949 corpus-wide features and buried that Data Cloud
    is the deeper answer). Lets the card resolve WHICH L3 platform/vehicle
    best covers the ENTITY'S actual gapped subcaps.

    Rows are ``(subcap_id, vendor, platform_name, feature_name, l3_id,
    category)``. Returns
    ``{family: {l3_id: {"platform_name", "vendor", "category",
    "subcaps": {sid: n_features}, "features_by_sid": {sid: [names≤4]},
    "n_features": int, "is_integration": bool}}}``.
    """
    agg: dict[str, dict[str, dict]] = {}
    for sid, vendor, pname, fname, l3_id, category in rows:
        if not sid or not l3_id:
            continue
        for fam in families_for_l3(vendor, pname):
            fam_map = agg.setdefault(fam, {})
            node = fam_map.get(l3_id)
            if node is None:
                node = fam_map[l3_id] = {
                    "platform_name": pname or l3_id,
                    "vendor": vendor,
                    "category": category,
                    "subcaps": {},
                    "features_by_sid": {},
                    "n_features": 0,
                    "is_integration": bool(
                        _INTEGRATION_CATEGORY_RE.search(category or "")
                        or _INTEGRATION_CATEGORY_RE.search(pname or "")),
                }
            node["subcaps"][sid] = node["subcaps"].get(sid, 0) + 1
            node["n_features"] += 1
            f = (fname or "").strip()
            fb = node["features_by_sid"].setdefault(sid, [])
            if f and f not in fb and len(fb) < 4:
                fb.append(f)
    return agg


def top_l3_for_gaps(
    fam_l3: dict[str, dict],
    gap_subcap_ids: list[str] | str,
    *,
    limit: int = 3,
) -> list[dict]:
    """Rank a family's L3 platforms by how many of the ENTITY'S gapped
    subcaps each covers (then by feature depth on those gaps). Pure. Returns
    ``[{l3_id, platform_name, category, is_integration, gaps_covered,
    features}]`` — the receipts a card/play uses to name the right vehicle
    instead of a bare family label."""
    gaps = {gap_subcap_ids} if isinstance(gap_subcap_ids, str) else set(gap_subcap_ids or [])
    scored: list[tuple[int, int, str, dict]] = []
    for l3_id, node in (fam_l3 or {}).items():
        covered = [s for s in node.get("subcaps", {}) if s in gaps]
        if not covered:
            continue
        depth = sum(node["subcaps"][s] for s in covered)
        feats: list[str] = []
        for s in covered:
            for f in node.get("features_by_sid", {}).get(s, []):
                if f not in feats:
                    feats.append(f)
        scored.append((len(covered), depth, l3_id, {
            "l3_id": l3_id,
            "platform_name": node.get("platform_name") or l3_id,
            "category": node.get("category"),
            "is_integration": bool(node.get("is_integration")),
            "gaps_covered": len(covered),
            "features": feats[:4],
        }))
    # most gaps covered, then deepest, then stable by l3_id
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return [d for _c, _d, _i, d in scored[:limit]]


async def load_catalogue_affinity(
    session: Any, catalogue_version: str,
) -> dict[str, dict[str, dict]]:
    """Load + memoize the affinity map for a catalogue version. Runs pinned
    to a pre-v7 catalogue (whose L4 layer was never authored) fall back to
    v7.0 — subcap ids are P#C#-stable enough that the curated links still
    beat the 11%-precise keyword tags; renamed subcaps simply miss and the
    semantic tier covers them. Never raises: a cold/absent table returns {}
    and the engine behaves exactly as before (zero regression)."""
    from sqlalchemy import text
    key = catalogue_version or "v7.0"
    if key in _CACHE:
        return _CACHE[key]
    try:
        rows = (await session.execute(text(
            """
            SELECT f.subcap_id, p.vendor, p.platform_name, f.feature_name
            FROM ccg_l4_features f
            JOIN ccg_l3_platforms p
              ON p.version = f.version AND p.l3_id = f.l3_id
            WHERE f.version = :v
            """), {"v": key})).all()
        if not rows and key != "v7.0":
            if "v7.0" not in _CACHE:
                rows = (await session.execute(text(
                    """
                    SELECT f.subcap_id, p.vendor, p.platform_name, f.feature_name
                    FROM ccg_l4_features f
                    JOIN ccg_l3_platforms p
                      ON p.version = f.version AND p.l3_id = f.l3_id
                    WHERE f.version = 'v7.0'
                    """))).all()
                _CACHE["v7.0"] = build_catalogue_affinity(
                    [(r.subcap_id, r.vendor, r.platform_name, r.feature_name)
                     for r in rows])
            _CACHE[key] = _CACHE["v7.0"]
            return _CACHE[key]
        _CACHE[key] = build_catalogue_affinity(
            [(r.subcap_id, r.vendor, r.platform_name, r.feature_name)
             for r in rows])
        return _CACHE[key]
    except Exception:
        return {}


_INCUMBENT_COV_CACHE: dict[str, dict[str, set]] = {}


async def load_incumbent_subcap_coverage(
    session: Any, catalogue_version: str,
) -> dict[str, set]:
    """{lowercased L4 vendor string → set(subcap_ids it covers)} for the
    WHOLE L4 layer (2026-07-14 incumbent-coverage signal). The v7 L4 layer
    is a broad market reference — third-party incumbents (Snowflake Inc. 61
    features, Collibra 162, Power BI…) carry curated links too. Lets the fit
    engine ask "does the customer's INSTALLED incumbent already deliver this
    gapped capability?" and discount the Zennify challenger's marginal
    opportunity where it does (empirically: Snowflake covers P4C1.3.x data-
    platform subcaps, NONE of the P1C2.5.x governance gaps — so the discount
    correctly abstains for a governance pitch). Memoized; never raises."""
    from sqlalchemy import text
    key = catalogue_version or "v7.0"
    if key in _INCUMBENT_COV_CACHE:
        return _INCUMBENT_COV_CACHE[key]
    sql = text(
        """
        SELECT DISTINCT p.vendor, f.subcap_id
        FROM ccg_l4_features f
        JOIN ccg_l3_platforms p
          ON p.version = f.version AND p.l3_id = f.l3_id
        WHERE f.version = :v AND p.vendor IS NOT NULL AND f.subcap_id IS NOT NULL
        """)
    try:
        rows = (await session.execute(sql, {"v": key})).all()
        if not rows and key != "v7.0":
            rows = (await session.execute(sql, {"v": "v7.0"})).all()
        cov: dict[str, set] = {}
        for vendor, sid in rows:
            cov.setdefault(str(vendor).lower(), set()).add(sid)
        _INCUMBENT_COV_CACHE[key] = cov
        return cov
    except Exception:
        return {}


def incumbent_covered_subcaps(
    incumbent_display_names: list[str],
    coverage: dict[str, set],
) -> set:
    """Union of subcaps the named incumbents cover, matching each incumbent
    display name (``Snowflake``, ``Power BI``, ``dbt``) as a substring of the
    L4 vendor strings (``Snowflake Inc.``, ``Microsoft Power BI``, ``dbt
    Labs``). Pure."""
    out: set = set()
    for name in incumbent_display_names or []:
        needle = str(name).lower().strip()
        if not needle:
            continue
        for vendor, subs in coverage.items():
            if needle in vendor:
                out |= subs
    return out


async def load_l3_affinity(
    session: Any, catalogue_version: str,
) -> dict[str, dict[str, dict]]:
    """Per-family per-L3 aggregates (:func:`build_l3_affinity`), memoized per
    catalogue version. Self-contained query + cache so the family-grain
    :func:`load_catalogue_affinity` zero-regression contract is untouched.
    Never raises: cold/absent table → {} and the vehicle resolver simply
    finds nothing (card behaves exactly as before)."""
    from sqlalchemy import text
    key = catalogue_version or "v7.0"
    if key in _L3_CACHE:
        return _L3_CACHE[key]
    sql = text(
        """
        SELECT f.subcap_id, p.vendor, p.platform_name, f.feature_name,
               f.l3_id, p.category
        FROM ccg_l4_features f
        JOIN ccg_l3_platforms p
          ON p.version = f.version AND p.l3_id = f.l3_id
        WHERE f.version = :v
        """)
    try:
        rows = (await session.execute(sql, {"v": key})).all()
        if not rows and key != "v7.0":
            rows = (await session.execute(sql, {"v": "v7.0"})).all()
        _L3_CACHE[key] = build_l3_affinity(
            [(r.subcap_id, r.vendor, r.platform_name, r.feature_name,
              r.l3_id, r.category) for r in rows])
        return _L3_CACHE[key]
    except Exception:
        return {}
