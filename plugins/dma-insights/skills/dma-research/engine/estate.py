"""What the client already runs, read against the L3 catalogue — the engine's
copy of the connector's estate identity (`apps/mcp/dma_mcp/fit.py`
`_estate_same`), vendored because the engine ships without apps/mcp; a test
holds the two equal on one truth table.

AAA WCNY (2026-10-15): MuleSoft — integrated per the partner's case study —
and Tableau beside an inferred Power BI ranked as net-new tiles, because
nothing told the ranking what the client owned. Every field here is computed
from the technology register and the catalogue; nothing is judged.
"""
from __future__ import annotations

import re

ESTATE_STATUSES = ("CONFIRMED", "INFERRED", "CLAIMED")
GENERIC_TOKENS = frozenset({"crm", "cloud", "platform", "data", "analytics", "ai",
                            "service", "sales", "marketing", "bi", "server", "core"})
GENERIC_CATEGORIES = frozenset({"platform", "industry cloud", "industry tooling", ""})


def vendor_key(v) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(v or "").lower()).strip()


def name_variants(name, vendor="") -> set:
    vt = set(vendor_key(vendor).split()) | {"salesforce"}
    raw = str(name or "")
    paren = " ".join(re.findall(r"\(([^)]*)\)", raw))
    bare = re.sub(r"\([^)]*\)", " ", raw)
    out = set()
    for form in (raw, bare, paren):
        toks = set(re.sub(r"[^a-z0-9]+", " ", form.lower()).split())
        if not toks:
            continue
        out.add(frozenset(toks - vt) or frozenset(toks))
        out.add(frozenset(toks))
    return out


def estate_same(product, p_vendor, platform, c_vendor) -> bool:
    a, b = name_variants(product, p_vendor), name_variants(platform, c_vendor)
    return any(len(v) > 1 or not (v <= GENERIC_TOKENS) for v in a & b)


def annotate(rows: list, register: list, catalogue: list) -> list:
    """Add in_estate / vendor_in_estate / replaces_in_estate to fit rows that
    lack them (an older connector). `register`: Tech_Register rows;
    `catalogue`: [{l3_id, vendor, platform_name, category}]."""
    estate = [(str(r.get("Vendor") or ""), str(r.get("Product") or ""),
               str(r.get("Status") or "").upper()) for r in register
              if str(r.get("Status") or "").upper() in ESTATE_STATUSES and r.get("Product")]
    by_name = {str(c.get("platform_name")): c for c in catalogue if isinstance(c, dict)}
    order = {s: i for i, s in enumerate(ESTATE_STATUSES)}
    for p in rows:
        if "in_estate" in p:
            continue
        c = by_name.get(str(p.get("platform"))) or {}
        vendor, category = str(c.get("vendor") or ""), str(c.get("category") or "")
        own, fam, repl = None, None, []
        for ev, prod, st in estate:
            same = estate_same(prod, ev, p.get("platform"), vendor)
            if same and (own is None or order[st] < order[own]):
                own = st
            if not same and vendor_key(ev) and vendor_key(ev) == vendor_key(vendor) \
                    and (fam is None or order[st] < order[fam]):
                fam = st
            e_cat = {str(x.get("category") or "") for x in catalogue
                     if estate_same(prod, ev, x.get("platform_name"), x.get("vendor"))}
            if not same and category.strip().lower() not in GENERIC_CATEGORIES \
                    and category in e_cat and vendor_key(ev) != vendor_key(vendor):
                repl.append(prod)
        p["in_estate"], p["vendor_in_estate"] = own, fam
        p["replaces_in_estate"] = sorted(set(repl))
    return rows
