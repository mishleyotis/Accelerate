"""Schema-tolerant tech-stack reader → D7.

Today only the Explorium `*_Tech_Stack*.xlsx` is read, so only 3/36 of the
corpus populates D7 even though ~20 ship a tech artifact under several
shapes:

  A. `A4_Tech_Stack_Map.csv` (15): Technology, Category, Evidence_Level,
     Utilization, Evidence_IDs, Zennify_Priority.
  B. `tech_inventory.json` (3) / `tech_stack_inventory.json` (4):
     `{platforms: {slug: {name, evidence_level, utilization}}}` OR the flat
     category→vendor-string shape (C).
  C. `tech_stack.json` (4): flat `{core_banking:"Temenos…", crm:"Salesforce…",
     integration:"MuleSoft, TIBCO", …, zennify_priority_flags:{…}}`.

Plus (per the operator) tech is also named in the Client-Profile / Assessment
report prose — `extract_tech_from_text` scans for a curated KNOWN-vendor
dictionary (precision over recall) as a last-resort supplement.

All paths emit `TechStackRow{vendor, product, category, confidence, source}`;
`package_persist` derives tech_id/layer/status. Pure / no DB.

Parse-time sanitation (Part 9.1) — :func:`sanitize_tech_rows` is the single
taxonomy gate every path (CSV / JSON / prose, and dma_package's Explorium
xlsx path) runs through before rows reach persistence. Each candidate cell
is split via ``nlp.taxonomy.split_cell`` then classified:

    platform            → persisted canonical (taxonomy vendor + canonical
                          product name + layer_hint + l3 link)
    engineering_signal  → persisted with status='ENGINEERING_SIGNAL' —
                          proof the entity builds software, but EXCLUDED
                          from the platform surface by the router.
    noise               → DROPPED + one aggregated DEGRADED parser warning.
    unknown_vendor      → persisted with status='UNKNOWN_VENDOR' (review
                          queue; not AE-rendered).

Mechanism note: ``tech_stack_entries`` has no ``category`` column and
migrations are additive-frozen for this workstream, so the classification
marker rides the free-form ``status`` varchar (no CHECK constraint on it —
verified against migration 006/044). The router filters both markers out of
the AE-facing ``items``.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from app.schemas.package import TechStackRow
from app.services.nlp.taxonomy import classify, split_cell
from app.services.parsers.tech_linker import l3_for_tech

# Status markers for taxonomy-flagged rows (see module docstring).
STATUS_ENGINEERING_SIGNAL = "ENGINEERING_SIGNAL"
STATUS_UNKNOWN_VENDOR = "UNKNOWN_VENDOR"

# Deployment-state signals → the prototype's status enum
# (DETECTED | CONFIRMED | CONFIRMED_REMOVED). Confirmed = the source asserts
# the tech is actually deployed/in-use; removed = it was decommissioned;
# everything else is an inferred detection.
_STATUS_REMOVED_RE = re.compile(
    r"remov|decommiss|sunset|retired|replaced|migrat\w*\s*off|former|legacy[\s_]*\(", re.I
)
_STATUS_CONFIRMED_RE = re.compile(
    r"confirm|deploy|in[\s_]*use|\bactive\b|production|\blive\b|implemented|current|yes|true",
    re.I,
)
_STATUS_INFERRED_RE = re.compile(r"infer|likely|possible|suspected|unconfirm|hypoth|\bno\b", re.I)


def tech_status_from_signals(raw_status: object, confidence: float | None = None) -> str:
    """Map a source status/presence cell (+ confidence) onto the status enum."""
    s = str(raw_status or "").strip()
    if _STATUS_REMOVED_RE.search(s):
        return "CONFIRMED_REMOVED"
    if _STATUS_CONFIRMED_RE.search(s):
        return "CONFIRMED"
    if _STATUS_INFERRED_RE.search(s):
        return "DETECTED"
    if confidence is not None and confidence >= 0.8:
        return "CONFIRMED"
    return "DETECTED"


# Flat-JSON keys that are metadata, not a technology category.
_META_KEYS = frozenset({
    "run_id", "source", "entity", "last_updated", "total_technologies",
    "total_tech_items", "zennify_priority", "zennify_priority_flags",
    "replaced_systems", "on_prem_data_warehouse",
})
_E_ID_RE = re.compile(r"\bE-\d{1,4}\b")

# Curated vendor dictionary for the report-prose scan. Precise (exact,
# word-boundary, case-insensitive) so a passing mention is a real signal,
# not a false positive. canonical name → regex alternatives.
_KNOWN_VENDORS: tuple[tuple[str, str], ...] = (
    ("Salesforce", r"salesforce"),
    ("MuleSoft", r"mulesoft"),
    ("Tableau", r"tableau"),
    ("Temenos", r"temenos"),
    ("Fiserv", r"fiserv"),
    ("FIS", r"\bFIS\b"),
    ("Jack Henry", r"jack henry|symitar|silverlake"),
    ("nCino", r"ncino"),
    ("Q2", r"\bQ2\b"),
    ("Backbase", r"backbase"),
    ("Snowflake", r"snowflake"),
    ("Databricks", r"databricks"),
    ("AWS", r"\bAWS\b|amazon web services"),
    ("Microsoft Azure", r"\bazure\b"),
    ("Google Cloud", r"google cloud|\bGCP\b"),
    ("Power BI", r"power bi"),
    ("Workday", r"workday"),
    ("ServiceNow", r"servicenow"),
    ("Adobe", r"adobe"),
    ("HubSpot", r"hubspot"),
    ("Marketo", r"marketo"),
    ("Pega", r"pega(systems)?"),
    ("Encompass", r"encompass"),
    ("Blend", r"\bBlend\b"),
)
_COMPILED_VENDORS = tuple(
    (name, re.compile(pat, re.IGNORECASE)) for name, pat in _KNOWN_VENDORS
)


def _evidence_level_to_conf(raw: object) -> float | None:
    """`1-Confirmed`/`1`/1 → 1.0; 2 → 0.66; 3 → 0.33; else None."""
    if raw is None:
        return None
    m = re.match(r"\s*(\d)", str(raw))
    if not m:
        return None
    lvl = int(m.group(1))
    return {1: 1.0, 2: 0.66, 3: 0.33}.get(lvl, max(0.1, 1.0 - 0.2 * lvl))


def _clean_vendor(value: str) -> list[str]:
    """Split a category value like 'MuleSoft, TIBCO, RabbitMQ' or
    'AWS (CloudFront, S3)' into individual vendor tokens. Parenthetical
    detail is dropped FIRST so its inner commas don't over-split."""
    no_parens = re.sub(r"\([^)]*\)", "", value)
    no_parens = re.sub(r"(?i)\b(presence|utilization)\b.*$", "", no_parens)
    parts = [p.strip(" ;.-") for p in no_parens.split(",")]
    return [p for p in parts if p and 1 < len(p) <= 120]


# ── Parse-time taxonomy sanitation (Part 9.1) ──────────────────────────────
#
# Cell-level guards that catch what the per-part classifier can't see once
# split_cell() has shredded the cell: person+title fragments whose title sits
# inside parens ("Archana Deskus (ex-PayPal CTO) on Board Risk Overs…" — the
# audit's PERSON row), and running prose (≥6 words with ≥2 function words).
_CELL_PERSON_RE = re.compile(
    r"\b(?:ex[-\s])?[A-Z][A-Za-z&.]*\s+"
    r"(?:CEO|CTO|CIO|CFO|COO|CISO|CRO|CDO|Chief|SVP|EVP|VP|President|Director)\b"
)
_CELL_PROSE_HINT_RE = re.compile(
    r"\b(?:the|and|with|for|from|that|our|their|via|both|into|are|is|was|has|have)\b",
    re.IGNORECASE,
)


def _is_noise_cell(cell: str) -> bool:
    """True when the WHOLE cell is prose/person/date noise. Checked before
    splitting so sentence fragments don't get shredded into pseudo-vendors
    ('Three key digital partners: Salesforce, FIS, and W' must die whole —
    prose mentions of real tech are the report-prose miner's job)."""
    if classify(cell)["kind"] == "noise":
        return True
    if _CELL_PERSON_RE.search(cell):
        return True
    words = cell.split()
    return len(words) >= 6 and len(_CELL_PROSE_HINT_RE.findall(cell)) >= 2


def sanitize_tech_rows(
    rows: list[TechStackRow], *, warnings: list[str] | None = None,
) -> list[TechStackRow]:
    """The single taxonomy gate for every tech-stack parse path.

    Every candidate cell runs through ``split_cell`` → ``classify``:
    platform hits are re-emitted canonical (taxonomy vendor + product +
    layer_hint + l3 link); engineering signals and unknown vendors are kept
    but status-flagged (router excludes them from the AE surface); noise is
    dropped with one aggregated DEGRADED warning. Idempotent — canonical /
    flagged rows re-classify to themselves.
    """
    out: list[TechStackRow] = []
    seen: set[tuple[str, str]] = set()
    dropped: list[str] = []

    def _emit(row: TechStackRow, key: tuple[str, str]) -> None:
        if key not in seen:
            seen.add(key)
            out.append(row)

    for row in rows:
        cell = re.sub(r"\s+", " ", row.vendor or "").strip()
        if not cell or _is_noise_cell(cell):
            dropped.append(cell[:80] or "<empty>")
            continue
        vendor_parts = split_cell(cell)
        prod = (row.product or "").strip()
        product_parts: list[str] = []
        if prod and prod.lower() != cell.lower() and not _is_noise_cell(prod):
            product_parts = [p for p in split_cell(prod) if p not in vendor_parts]
        parts = vendor_parts + product_parts
        if not parts:
            dropped.append(cell[:80])
            continue

        results = [(p, classify(p)) for p in parts]
        platform_hits = {r["canonical"]: r for _p, r in results
                         if r["kind"] == "platform"}
        # Vendor/product column pairs describe ONE deployment: when the
        # vendor cell resolves to a generic vendor-level entry
        # ("Salesforce") and the product cell resolves to a specific
        # product of that SAME taxonomy vendor ("Marketing Cloud"), keep
        # only the specific row. Multi-platform cells ("Salesforce,
        # Tableau") are untouched — both parts came from the vendor cell.
        if product_parts and len(platform_hits) > 1:
            product_canonicals = {
                r["canonical"] for p, r in results
                if p in product_parts and r["kind"] == "platform"
            }
            for canonical in list(platform_hits):
                r = platform_hits[canonical]
                if (
                    canonical == r["vendor"]
                    and canonical not in product_canonicals
                    and any(
                        c in product_canonicals and o["vendor"] == r["vendor"]
                        for c, o in platform_hits.items() if c != canonical
                    )
                ):
                    del platform_hits[canonical]
        for canonical, r in platform_hits.items():
            vendor = r["vendor"] or canonical
            _emit(TechStackRow(
                vendor=vendor[:128], product=canonical[:255],
                category=row.category, layer=r["layer_hint"],
                confidence=row.confidence, source=row.source,
                status=row.status or "DETECTED",
                l3_id=l3_for_tech(canonical, canonical, row.category)
                or l3_for_tech(vendor, canonical, row.category),
            ), (vendor.lower(), canonical.lower()))
        # Engineering-signal / unknown-vendor flags come from the VENDOR
        # cell only. Product-cell fragments of a non-platform row are
        # qualifiers of the same candidate, not separate review rows —
        # expanding them would mint one pseudo-vendor per fragment on
        # every pass (non-idempotent heal).
        for p, r in results:
            if p not in vendor_parts:
                continue
            if r["kind"] == "engineering_signal":
                _emit(TechStackRow(
                    vendor=p[:128], product=p[:255], category=row.category,
                    confidence=row.confidence, source=row.source,
                    status=STATUS_ENGINEERING_SIGNAL,
                ), ("engineering_signal", p.lower()))
            elif r["kind"] == "unknown_vendor" and not platform_hits:
                # Unknowns riding a cell that also named a catalogue platform
                # are qualifiers ("Salesforce, custom extensions"), not
                # separate review candidates.
                _emit(TechStackRow(
                    vendor=p[:128], product=(prod or p)[:255],
                    category=row.category, confidence=row.confidence,
                    source=row.source, status=STATUS_UNKNOWN_VENDOR,
                ), ("unknown_vendor", p.lower()))
            elif r["kind"] == "noise" and not platform_hits:
                dropped.append(p[:80])

    if dropped and warnings is not None:
        sample = "; ".join(dropped[:3])
        warnings.append(
            f"DEGRADED:techstack_noise_dropped: {len(dropped)} candidate(s) "
            f"rejected by taxonomy (e.g. {sample!r})"
        )
    return out


def parse_tech_csv(
    path: Path, *, warnings: list[str] | None = None,
) -> list[TechStackRow]:
    if not path.exists():
        return []
    try:
        lines = [
            ln for ln in path.read_text().splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
    except OSError:
        return []
    if not lines:
        return []
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        return []
    norm = {re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_"): h for h in reader.fieldnames}
    tech_col = norm.get("technology") or norm.get("product") or norm.get("vendor") \
        or norm.get("name") or reader.fieldnames[0]
    cat_col = norm.get("category") or norm.get("layer")
    conf_col = norm.get("evidence_level") or norm.get("confidence")
    status_col = (norm.get("status") or norm.get("deployment_confirmed")
                  or norm.get("deploy_status") or norm.get("deployment")
                  or norm.get("presence") or norm.get("validation_method"))
    out: list[TechStackRow] = []
    for row in reader:
        name = (row.get(tech_col) or "").strip()
        if not name:
            continue
        category = ((row.get(cat_col) or "").strip() or None) if cat_col else None
        confidence = _evidence_level_to_conf(row.get(conf_col)) if conf_col else None
        out.append(TechStackRow(
            vendor=name[:128],
            product=name[:255],
            category=category,
            confidence=confidence,
            source=path.name[:64],
            status=tech_status_from_signals(row.get(status_col) if status_col else None, confidence),
            l3_id=l3_for_tech(name, name, category),
        ))
    # Part 9.1: every cell through split_cell → classify before it can
    # reach persistence (the audit's root cause was this path shipping
    # cells verbatim — languages, prose, a person, a date).
    return sanitize_tech_rows(out, warnings=warnings)


def parse_tech_json(
    path: Path, *, warnings: list[str] | None = None,
) -> list[TechStackRow]:
    """Handle BOTH the platforms-dict shape and the flat category→vendor
    shape (tech_inventory.json / tech_stack_inventory.json / tech_stack.json)."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    out: list[TechStackRow] = []
    seen: set[str] = set()

    def _add(vendor: str, category: str | None, conf: float | None) -> None:
        key = f"{vendor.lower()}|{(category or '').lower()}"
        if vendor and key not in seen:
            seen.add(key)
            out.append(TechStackRow(
                vendor=vendor[:128], product=vendor[:255],
                category=category, confidence=conf, source=path.name[:64],
                status=tech_status_from_signals(None, conf),
                l3_id=l3_for_tech(vendor, vendor, category),
            ))

    # Shape B: {platforms: {slug: {name, evidence_level, utilization}}}.
    platforms = data.get("platforms")
    if isinstance(platforms, dict):
        for slug, p in platforms.items():
            if isinstance(p, dict):
                name = (p.get("name") or slug).strip()
                _add(name, slug, _evidence_level_to_conf(p.get("evidence_level")))
        if out:
            return sanitize_tech_rows(out, warnings=warnings)

    # Shape C: flat category → vendor-string.
    for key, value in data.items():
        if key in _META_KEYS or not isinstance(value, str):
            continue
        for vendor in _clean_vendor(value):
            _add(vendor, key, None)
    return sanitize_tech_rows(out, warnings=warnings)


def load_tech_stack(
    root: Path, *, warnings: list[str] | None = None,
) -> list[TechStackRow]:
    """Resolve the package's tech stack from the structured variants.

    Searches RECURSIVELY within the resolved package root because the tech
    artifact lands in many places across the corpus: 08_appendices,
    01_evidence, 02_research_workbook/exports, AND a non-canonical
    `<Entity> Background Research/` subdir. CSV (richest + most common) is
    preferred; returns the first non-empty source, else []. Every path is
    taxonomy-sanitized (see :func:`sanitize_tech_rows`)."""
    # CSV first. Patterns ordered specific→broad; A4/A5-prefixed +
    # *tech*stack* + *technology_stack* cover every observed name.
    for pat in ("**/A[0-9]*[Tt]ech*[Ss]tack*.csv",
                "**/*[Tt]ech*[Ss]tack*.csv",
                "**/*[Tt]echnology_[Ss]tack*.csv"):
        for p in sorted(root.glob(pat)):
            rows = parse_tech_csv(p, warnings=warnings)
            if rows:
                return rows
    # Then the JSON shapes.
    for name in ("tech_inventory.json", "tech_stack_inventory.json",
                 "tech_stack.json"):
        for p in sorted(root.glob(f"**/{name}")):
            rows = parse_tech_json(p, warnings=warnings)
            if rows:
                return rows
    return []


def extract_tech_from_text(text: str, *, source: str = "report_mention") -> list[TechStackRow]:
    """Last-resort supplement: scan report prose for a curated KNOWN-vendor
    dictionary. Precision-first — only exact, word-boundary matches. Output
    is taxonomy-sanitized so prose mentions carry the canonical vendor /
    layer_hint (catalogue misses stay flagged UNKNOWN_VENDOR for review)."""
    if not text:
        return []
    out: list[TechStackRow] = []
    seen: set[str] = set()
    for name, pat in _COMPILED_VENDORS:
        if name.lower() not in seen and pat.search(text):
            seen.add(name.lower())
            out.append(TechStackRow(
                vendor=name, product=name, category=None,
                confidence=0.3, source=source[:64],
            ))
    return sanitize_tech_rows(out)
