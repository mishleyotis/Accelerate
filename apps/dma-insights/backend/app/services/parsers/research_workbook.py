"""Research workbook parser.

Per plan §① — research workbooks are paired with the scoring workbook in
each DMA's Drive folder. They contain the analyst's evidence rows. Shape
varies per DMA (analysts add columns).

Two shapes confirmed in the wild:

  1. **Flat evidence sheet** (synthetic / future). One row per E-ID; the
     ResearchWorkbookMap targets one sheet with e_id/source/tier columns.

  2. **Per-pillar-category sheets** (AlmaBank, WSFS, Regions). One row per
     SubCap, with Evidence_IDs + Source_URLs as semicolon- or pipe-
     delimited multi-value columns and a Key_Evidence_Excerpt OR
     Evidence_Notes column carrying the verbatim quotes. The
     ``parse_per_pillar_sheets`` entrypoint walks these and emits one
     ``ParsedEvidence`` per E-ID, fanning the linked subcaps from the
     row.

Strategy:
  1. Read sheet metadata via openpyxl.
  2. Optionally infer the column map via injected ``infer_map`` (Gemini Pro
     in production; deterministic in tests).
  3. Cached by SHA-256 of normalized headers — same workbook shape →
     cache hit → skip LLM.
  4. Deterministic ingest with the column map.

Anti-corruption: every row drops if it can't produce an e_id + excerpt.
Tiers are normalized to the canonical research-workbook source-tier
taxonomy (T1..T7 — ``app.schemas.package.normalize_tier``); a row whose
tier cell is missing or out-of-taxonomy is KEPT with ``tier=None`` (the
evidence content is real even when its tier label is junk) and a warning
is emitted — a tier is never fabricated. The caller cross-references the
resulting rows against the ``research_handoff.json`` (if present) — JSON
wins on E-ID conflict.

State-branch contract (single canonical matrix consumed by tests):

  - ``full_extract``                         — ≥1 row extracted; no
    warnings; column map cached.
  - ``partial_with_warnings``                — ≥1 row extracted but
    ≥1 warning emitted (bad_tier, missing_required, etc.).
  - ``llm_column_mapper_used``               — fingerprint cache miss
    triggered the injected infer_map; the new map was stored.
  - ``headers_too_drifted_requires_admin_review``
                                              — 100% of headers unknown
    to the heuristic mapper; ``parse_per_pillar_sheets`` returns no
    rows and marks the file PENDING_REVIEW.
  - ``file_missing``                          — caller's responsibility;
    the orchestrator emits this branch when no
    ``02_research_workbook/*.xlsx`` is present.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResearchWorkbookMap:
    """Where each scalar lives in this particular workbook shape."""
    sheet_name: str
    e_id_col: str
    source_name_col: str
    source_url_col: str | None
    excerpt_col: str
    claim_type_col: str | None
    tier_col: str
    published_date_col: str | None = None
    linked_subcap_ids_col: str | None = None


@dataclass
class ParsedEvidence:
    e_id: str
    source_name: str
    source_url: str | None
    excerpt: str
    claim_type: str
    # Canonical source tier (T1..T7) or None when the workbook states no
    # parseable tier — never a fabricated default.
    tier: int | None
    published_date: str | None = None
    linked_subcap_ids: list[str] = field(default_factory=list)


@dataclass
class ResearchParseResult:
    rows: list[ParsedEvidence] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    used_map: ResearchWorkbookMap | None = None


# ---------- helpers (kept here so the service is self-contained) ----------

def _col_to_index(letter: str) -> int:
    idx = 0
    for ch in letter.upper():
        if not ("A" <= ch <= "Z"):
            raise ValueError(f"bad column letter: {letter!r}")
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _split_subcap_ids(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [s.strip() for s in str(v).split(",") if s.strip()]


def collect_research_metadata(workbook: Any, *, sample_size: int = 20) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ws in workbook.worksheets:
        headers: list[str] = []
        for cell in next(ws.iter_rows(min_row=1, max_row=1, values_only=True), []):
            headers.append(str(cell).strip() if cell is not None else "")
        samples: list[list[Any]] = []
        for row in ws.iter_rows(min_row=2, max_row=1 + sample_size, values_only=True):
            if all(c is None for c in row):
                continue
            samples.append(list(row))
        out.append({"sheet_name": ws.title, "headers": headers, "sample_rows": samples})
    return out


def research_shape_fingerprint(metadata: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for m in metadata:
        parts.append(str(m["sheet_name"]))
        parts.extend(str(h) for h in m["headers"])
        parts.append("|")
    blob = "␟".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def parse_research_with_map(
    workbook: Any, workbook_map: ResearchWorkbookMap,
) -> ResearchParseResult:
    """Deterministic ingest given a column map."""
    result = ResearchParseResult(used_map=workbook_map)
    try:
        ws = workbook[workbook_map.sheet_name]
    except KeyError:
        result.warnings.append({
            "kind": "missing_sheet", "sheet": workbook_map.sheet_name,
        })
        return result

    cols = {
        "e_id": _col_to_index(workbook_map.e_id_col),
        "source_name": _col_to_index(workbook_map.source_name_col),
        "source_url": _col_to_index(workbook_map.source_url_col) if workbook_map.source_url_col else None,
        "excerpt": _col_to_index(workbook_map.excerpt_col),
        "claim_type": _col_to_index(workbook_map.claim_type_col) if workbook_map.claim_type_col else None,
        "tier": _col_to_index(workbook_map.tier_col),
        "published_date": _col_to_index(workbook_map.published_date_col) if workbook_map.published_date_col else None,
        "linked_subcap_ids": _col_to_index(workbook_map.linked_subcap_ids_col) if workbook_map.linked_subcap_ids_col else None,
    }

    def at(row: tuple[Any, ...], idx: int | None) -> Any:
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(c is None for c in row):
            continue
        e_id = _str_or_none(at(row, cols["e_id"]))
        excerpt = _str_or_none(at(row, cols["excerpt"]))
        tier_raw = at(row, cols["tier"])
        if not e_id or not excerpt:
            result.warnings.append({
                "kind": "missing_required",
                "e_id": e_id, "has_excerpt": excerpt is not None,
            })
            continue
        # Tier: canonical taxonomy or honest None. The row is KEPT either
        # way — the evidence content is real even when the tier cell is
        # junk; only the tier label is withheld (never fabricated).
        tier = _coerce_tier(tier_raw)
        if tier is None:
            result.warnings.append({
                "kind": "missing_tier" if tier_raw is None else "bad_tier",
                "e_id": e_id, "value": None if tier_raw is None else str(tier_raw),
            })
        result.rows.append(
            ParsedEvidence(
                e_id=e_id,
                source_name=str(at(row, cols["source_name"]) or "").strip() or "(unknown)",
                source_url=_str_or_none(at(row, cols["source_url"])),
                excerpt=excerpt,
                claim_type=str(at(row, cols["claim_type"]) or "strategic_signal").strip(),
                tier=tier,
                published_date=_str_or_none(at(row, cols["published_date"])),
                linked_subcap_ids=_split_subcap_ids(at(row, cols["linked_subcap_ids"])),
            )
        )
    return result


def parse_research_workbook(
    workbook: Any,
    *,
    cache_lookup: Callable[[str], ResearchWorkbookMap | None],
    cache_store: Callable[[str, ResearchWorkbookMap], None],
    infer_map: Callable[[list[dict[str, Any]]], ResearchWorkbookMap],
) -> ResearchParseResult:
    metadata = collect_research_metadata(workbook)
    fp = research_shape_fingerprint(metadata)
    m = cache_lookup(fp)
    if m is None:
        m = infer_map(metadata)
        cache_store(fp, m)
    return parse_research_with_map(workbook, m)


# ── Per-pillar-category sheet parsers (AlmaBank / WSFS shape) ────────

# Canonical header aliases for the per-pillar shape. Order matters —
# the first column to match wins.
PERPILLAR_HEADER_ALIASES: dict[str, list[str]] = {
    "subcap_id": [
        "subcap_id", "sub_cap_id",
        # 2026-06 pattern-mining promotion: `subcapability` appeared 9
        # times across the 5 sanitized + 5 real fixture packages on
        # per-pillar sheets that otherwise matched the standard shape.
        # Promoted from the parser_observations queue (migration 026).
        "subcapability",
    ],
    "evidence_ids": ["evidence_ids", "evidence id", "evidence_id"],
    "source_urls": [
        "source_urls", "source url", "source_url", "url",
        # 2026-06: `proof_links` showed 8 occurrences across fixtures
        # as a URL-bearing column on evidence sheets — same semantics
        # as source_urls.
        "proof_links",
    ],
    "tier": [
        # Evidence-specific tier columns FIRST (2026-07-06 deploy review:
        # OZK-class workbooks carry the per-evidence tier in
        # `Evidence_Tier_ERS` on underscore-named per-pillar sheets —
        # unmatched, the whole workbook's evidence trail was skipped and
        # the tier card fell back to a 43-item index vs 115 workbook rows).
        "evidence_tier_ers",
        "evidence_tier",
        "tier",
        # 2026-06: `tier_sv` (subvertical-flagged tier) shows up as 7
        # occurrences. Same int-tier semantics; the `_sv` suffix is
        # operator-side metadata that doesn't change parsing.
        "tier_sv",
    ],
    "excerpt": [
        "key_evidence_excerpt", "evidence_excerpt", "excerpt",
        "evidence_notes", "evidence notes", "notes",
        # 2026-06: `proof_claims` (8 occurrences) is the analyst's
        # narrative claim text — same semantics as excerpt.
        "proof_claims",
    ],
}

# Header regex to spot per-pillar sheets. The Alma fixture names sheets
# "P1C1".."P4C4"; WSFS uses "P1 Strategy Gov Culture"; the OZK/CalPrivate/
# Compeer class uses underscores ("P1_Strategy_Governance", "P4C1_Data_Mgmt",
# "P1_Scoring_Detail") — unmatched before 2026-07-06, which silently dropped
# those workbooks' evidence→subcap trail (2026-07-06 QA / deploy review).
PERPILLAR_SHEET_RE = re.compile(r"^P[1-4](?:C[1-9]|[\s_])", re.IGNORECASE)

# Scoring-detail sheets (Compeer/FNBO/Utah class: "P1_Scoring_Detail",
# "Pillar_P1") carry a `Tier` column that is the SUBCAP taxonomy tier
# (T1-T3 catalogue importance) and comma-joined multi-evidence cells whose
# per-evidence tiers live in the flat Evidence_Linkage_Matrix — emitting
# them would corrupt the evidence index. `Score_1_to_5` is their signature.
_SCORING_DETAIL_HEADER = "score_1_to_5"
# Placeholder cells in the Evidence_IDs column (OZK writes NO_EVIDENCE per
# unevidenced subcap) — an absent-evidence row, never a bad-tier warning.
_PLACEHOLDER_EID_RE = re.compile(
    r"^(?:no[_ ]?evidence|none|n/?a|tbd|pending|-)$", re.I)
# OZK-class tier cells annotate per-evidence: "E-065:T2 ERS:3.65".
_EID_TIER_RE = re.compile(r"(E-?[A-Z0-9-]*\d)\s*:\s*T?([1-8])\b", re.I)
_TIER_TOKEN_RE = re.compile(r"\bT?([1-8])\b")


def _find_col(headers: list[str], aliases: list[str]) -> int | None:
    """Case-insensitive header match — first alias wins."""
    norm = [str(h).strip().lower() for h in headers]
    for a in aliases:
        if a in norm:
            return norm.index(a)
    return None


def _split_multi_value(s: Any) -> list[str]:
    """Split on the analyst-vernacular separators: ; | newline."""
    if s is None:
        return []
    parts = re.split(r"[;|\n]+", str(s))
    return [p.strip() for p in parts if p.strip()]


def _coerce_tier(raw: Any) -> int | None:
    """Accept '3', 3, 'T3', 'tier 3', 'T1, T2, T3' (strongest wins) — all
    normalized to the canonical research-workbook source-tier taxonomy
    (T1..T7). Out-of-taxonomy ('T10-CONTRADICTORY', 'T9') / non-tier
    words → None. Delegates to the shared ``normalize_tier`` so every
    parser path applies one taxonomy."""
    from app.schemas.package import normalize_tier

    return normalize_tier(raw)


@dataclass
class PerPillarParseResult:
    """Result for the per-pillar-sheets walker.

    `observations` is the self-improvement signal added 2026-06: per-
    workbook list of structural things the parser SAW but didn't know
    how to canonically map (typically a column header outside
    `PERPILLAR_HEADER_ALIASES`). Each dict has shape:
        {"kind": "unknown_column",
         "value": "<raw column header>",
         "canonical_guess": "<best guess or None>",
         "sample_context": {"sheet": "P1C1", "neighbor_headers":[...]}}
    Downstream `dma_package.parse_package` merges these into
    `IngestedPackage.parser_observations`, which `package_persist`
    flushes to the `parser_observations` table via
    `record_parser_observation`. The table is the queue the operator
    (or a future nightly job) drains to promote variants into the
    static ALIASES dict.
    """
    rows: list[ParsedEvidence] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    state_kind: str = "file_missing"
    sheets_scanned: int = 0


def parse_per_pillar_sheets(workbook: Any) -> PerPillarParseResult:
    """Walk AlmaBank/WSFS-shaped workbooks.

    For each per-pillar sheet:
      1. Resolve the column indices from heuristic header aliases.
      2. For each row, split multi-value Evidence_IDs / Source_URLs.
      3. Emit ONE ParsedEvidence per E-ID; subcap_id from the row goes
         into linked_subcap_ids. Tier from the row's Tier cell.
      4. De-dup at E-ID level WITHIN this workbook (later runs aggregate
         linked_subcap_ids across sheets).
    """
    result = PerPillarParseResult()
    accum: dict[str, ParsedEvidence] = {}
    headers_known = 0
    headers_total = 0
    _warned_tiers: set[tuple[str, str]] = set()

    for ws in workbook.worksheets:
        title = str(ws.title)
        if not PERPILLAR_SHEET_RE.match(title):
            continue
        result.sheets_scanned += 1
        rows_iter = ws.iter_rows(values_only=True)

        # The WSFS shape has the header row at row 2 (row 1 is a
        # banner). The Alma shape has it at row 1. We auto-detect.
        header_row: list[Any] | None = None
        for r in rows_iter:
            if r and any(
                str(c).strip().lower() == "subcap_id" for c in r if c is not None
            ):
                header_row = list(r)
                break
        if header_row is None:
            result.warnings.append({"kind": "no_header_row", "sheet": title})
            continue
        headers_str = [str(c) if c is not None else "" for c in header_row]
        headers_total += len(headers_str)

        cols = {
            k: _find_col(headers_str, aliases)
            for k, aliases in PERPILLAR_HEADER_ALIASES.items()
        }
        norm_headers = [str(h).strip().lower() for h in headers_str]
        if _SCORING_DETAIL_HEADER in norm_headers:
            # Scoring-detail sheet: its `Tier` is subcap taxonomy, not an
            # evidence tier. The headers are RECOGNIZED (counted below so
            # the workbook never false-flags as drifted) but no evidence
            # rows are emitted — the flat Evidence_Linkage_Matrix /
            # Evidence_Index sheet carries this class's per-evidence tiers.
            headers_known += sum(1 for v in cols.values() if v is not None)
            result.observations.append({
                "kind": "scoring_detail_sheet_skipped",
                "value": title,
                "canonical_guess": None,
                "sample_context": {
                    "sheet": title,
                    "parser": "research_workbook.parse_per_pillar_sheets",
                    "neighbor_headers": [s for s in headers_str if s][:5],
                },
            })
            continue
        if cols["evidence_ids"] is None or cols["tier"] is None:
            result.warnings.append({
                "kind": "missing_required_columns",
                "sheet": title,
                "missing": [k for k, v in cols.items() if v is None],
            })
            continue
        headers_known += sum(1 for v in cols.values() if v is not None)

        # ── Self-improvement observation pass ──────────────────────────
        # Any header in this sheet that ISN'T in any alias list is a
        # potential new variant. Record it so the operator can promote
        # the variant into PERPILLAR_HEADER_ALIASES on the next deploy.
        # Cheapest signal: lowercased exact-match check against the
        # union of all known alias strings.
        known_alias_set: set[str] = set()
        for aliases in PERPILLAR_HEADER_ALIASES.values():
            for a in aliases:
                known_alias_set.add(a.strip().lower())
        for h in headers_str:
            norm = (h or "").strip().lower()
            if not norm or norm in known_alias_set:
                continue
            # Heuristic canonical guess by keyword presence (best-effort;
            # the operator gets to confirm). The goal isn't perfect
            # classification — it's surfacing the variant at all.
            guess: str | None = None
            if "subcap" in norm or "sub_cap" in norm or "capability" in norm:
                guess = "subcap_id"
            elif "evidence" in norm and "id" in norm:
                guess = "evidence_ids"
            elif "url" in norm or "source" in norm:
                guess = "source_urls"
            elif "tier" in norm:
                guess = "tier"
            elif "excerpt" in norm or "note" in norm:
                guess = "excerpt"
            result.observations.append({
                "kind": "unknown_column",
                "value": h,
                "canonical_guess": guess,
                "sample_context": {
                    "sheet": title,
                    "parser": "research_workbook.parse_per_pillar_sheets",
                    "neighbor_headers": [
                        s for s in headers_str if s and s != h
                    ][:5],
                },
            })

        for row in rows_iter:
            if row is None or all(c is None for c in row):
                continue
            # E-ID cells split on the analyst separators PLUS comma — the
            # OZK class comma-joins multi-evidence cells ("E-061, E-065,
            # E-066") whose per-E-ID tiers are annotated in the tier cell.
            evidence_ids = [
                e2
                for e in _split_multi_value(
                    row[cols["evidence_ids"]] if cols["evidence_ids"] < len(row) else None
                )
                for e2 in (s.strip() for s in e.split(","))
                if e2 and not _PLACEHOLDER_EID_RE.match(e2)
            ]
            if not evidence_ids:
                continue    # absent-evidence row (NO_EVIDENCE) — no warning
            urls = _split_multi_value(
                row[cols["source_urls"]] if (cols["source_urls"] is not None
                                              and cols["source_urls"] < len(row)) else None
            )
            # Per-evidence tier resolution (2026-07-06 deploy review —
            # OZK writes "E-065:T2 ERS:3.65" in the tier cell): an E-ID:T#
            # annotation map wins per evidence; a token list positionally
            # aligned with the Evidence_IDs list is zipped; a single
            # scalar/token broadcasts (the Alma/WSFS shape, unchanged).
            tier_cell = row[cols["tier"]] if cols["tier"] < len(row) else None
            tier_raw = str(tier_cell) if tier_cell is not None else ""
            eid_tiers = {m.group(1).upper(): int(m.group(2))
                         for m in _EID_TIER_RE.finditer(tier_raw)}
            tokens = ([] if eid_tiers
                      else [int(t) for t in _TIER_TOKEN_RE.findall(tier_raw)])
            base_tier = (_coerce_tier(tier_cell)
                         if not eid_tiers and len(tokens) <= 1 else None)

            # loop variables bound as defaults — the closure outlives the
            # iteration and late binding would read the LAST row's values.
            def _tier_for(i: int, e_id: str, *, _et=eid_tiers, _tk=tokens,
                          _ev=evidence_ids, _bt=base_tier) -> int | None:
                if _et:
                    return _et.get(e_id.upper())
                if len(_tk) == len(_ev) and _tk:
                    return _tk[i]
                if len(_tk) == 1:
                    return _tk[0]
                return _bt

            if (not eid_tiers and not tokens and base_tier is None
                    and tier_cell is not None):
                # Junk / ambiguous-set tier cell → warn (once per distinct
                # cell value per sheet), but KEEP the row with tier=None:
                # the E-ID/excerpt/subcap linkage is real evidence content;
                # only the tier label is withheld (never fabricated).
                w_key = (title, str(tier_cell))
                if w_key not in _warned_tiers:
                    _warned_tiers.add(w_key)
                    result.warnings.append({
                        "kind": "bad_tier",
                        "sheet": title,
                        "raw": str(tier_cell),
                    })
            excerpt = ""
            if cols["excerpt"] is not None and cols["excerpt"] < len(row):
                excerpt = str(row[cols["excerpt"]] or "").strip()
            subcap_id = ""
            if cols["subcap_id"] is not None and cols["subcap_id"] < len(row):
                subcap_id = str(row[cols["subcap_id"]] or "").strip()
            for i, e_id in enumerate(evidence_ids):
                # None = this E-ID's tier is not stated in the row. The
                # row is KEPT anyway — the E-ID/excerpt/subcap linkage is
                # real evidence content; only the tier label is withheld
                # (honest tier=None, never fabricated).
                tier = _tier_for(i, e_id)
                url = urls[i] if i < len(urls) else (urls[0] if urls else None)
                existing = accum.get(e_id)
                if existing is None:
                    accum[e_id] = ParsedEvidence(
                        e_id=e_id,
                        source_name=_derive_source_name(url) or "(unknown)",
                        source_url=url,
                        excerpt=excerpt or "(no excerpt)",
                        claim_type="research_evidence",
                        tier=tier,
                        published_date=None,
                        linked_subcap_ids=[subcap_id] if subcap_id else [],
                    )
                else:
                    # Aggregate subcap across multiple rows referencing the same E-ID.
                    if subcap_id and subcap_id not in existing.linked_subcap_ids:
                        existing.linked_subcap_ids.append(subcap_id)
                    # Tier upgrade — keep the stronger (lower) tier; a
                    # known tier always beats None (unknown).
                    if tier is not None and (existing.tier is None
                                             or tier < existing.tier):
                        existing.tier = tier

    result.rows = sorted(accum.values(), key=lambda p: p.e_id)
    if result.sheets_scanned == 0:
        result.state_kind = "file_missing"
    elif not result.rows:
        if headers_total > 0 and headers_known == 0:
            result.state_kind = "headers_too_drifted_requires_admin_review"
        else:
            result.state_kind = "partial_with_warnings"
    else:
        result.state_kind = (
            "partial_with_warnings" if result.warnings else "full_extract"
        )
    return result


def _derive_source_name(url: str | None) -> str | None:
    """Friendly source name from a URL host."""
    if not url:
        return None
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else None


# ── Flat evidence-sheet tier histogram (the workbook's own tier truth) ──
# Every confirmed workbook shape ships ONE flat per-evidence sheet:
#   Evidence_Linkage_Matrix   (Compeer / FNBO / 1st Security / Odlum)
#   Evidence_Master           (OZK)
#   Evidence_Index            (Spokane / Bank of Utah / CalPrivate)
# with an Evidence_ID + Tier column pair. The D1 evidence tier card must
# show THESE counts (user mandate, 2026-07-06 deploy review: OZK's card
# showed a 43-item index histogram vs the workbook's 115 rows).
_FLAT_EVIDENCE_SHEET_RE = re.compile(
    r"evidence[_ ]?(master|index|linkage|inventory)|linkage[_ ]?matrix"
    r"|merged[_ ]?evidence", re.I)
_FLAT_EID_ALIASES = ["evidence_id", "e_id", "eid", "evidence id"]
_FLAT_TIER_ALIASES = ["tier", "evidence_tier", "evidence_tier_ers", "tier_sv"]


def evidence_tier_histogram(workbook: Any) -> dict[str, Any] | None:
    """Per-evidence tier histogram from the workbook's flat evidence sheet.

    Returns ``{"tiers": {"T1": n, …}, "total_items": N, "sheet": name}``
    over UNIQUE evidence IDs (FNBO's matrix repeats an E-ID per subcap
    row — the strongest/lowest tier wins on conflict), or ``None`` when no
    sheet carries the id+tier pair (east-west class: the caller's
    provenance ladder falls through to the handoff / index rungs)."""
    best: dict[str, Any] | None = None
    for ws in workbook.worksheets:
        title = str(ws.title)
        if not _FLAT_EVIDENCE_SHEET_RE.search(title):
            continue
        rows_iter = ws.iter_rows(values_only=True)
        header_row: list[Any] | None = None
        for scanned, r in enumerate(rows_iter, start=1):
            # banner-tolerant: header within first 3 rows
            headers = [str(c) if c is not None else "" for c in (r or ())]
            if _find_col(headers, _FLAT_EID_ALIASES) is not None:
                header_row = headers
                break
            if scanned >= 3:
                break
        if header_row is None:
            continue
        i_eid = _find_col(header_row, _FLAT_EID_ALIASES)
        i_tier = _find_col(header_row, _FLAT_TIER_ALIASES)
        if i_eid is None or i_tier is None:
            continue
        tier_by_eid: dict[str, int] = {}
        for row in rows_iter:
            if row is None or all(c is None for c in row):
                continue
            e_id = _str_or_none(row[i_eid] if i_eid < len(row) else None)
            tier = _coerce_tier(row[i_tier] if i_tier < len(row) else None)
            if not e_id or tier is None:
                continue
            prior = tier_by_eid.get(e_id)
            if prior is None or tier < prior:   # strongest tier wins
                tier_by_eid[e_id] = tier
        if not tier_by_eid:
            continue
        tiers: dict[str, int] = {}
        for t in tier_by_eid.values():
            tiers[f"T{t}"] = tiers.get(f"T{t}", 0) + 1
        cand = {"tiers": dict(sorted(tiers.items())),
                "total_items": len(tier_by_eid), "sheet": title}
        if best is None or cand["total_items"] > best["total_items"]:
            best = cand
    return best


# ── Handoff cross-reference ──────────────────────────────────────────

def cross_reference_with_handoff(
    workbook_rows: list[ParsedEvidence],
    handoff_items: list[dict[str, Any]],
) -> tuple[list[ParsedEvidence], list[dict[str, Any]]]:
    """Reconcile per-pillar rows against research_handoff.json items.

    Per plan §① the handoff JSON wins on E-ID conflict (more
    structured, includes publish_date and signal_direction). The
    workbook contributes evidence not present in the handoff.

    Returns (merged_rows, conflict_warnings).
    """
    handoff_by_id: dict[str, dict[str, Any]] = {
        (h.get("evidence_id") or ""): h for h in handoff_items
    }
    conflicts: list[dict[str, Any]] = []
    merged: dict[str, ParsedEvidence] = {p.e_id: p for p in workbook_rows}

    for e_id, h in handoff_by_id.items():
        if not e_id:
            continue
        ho_tier = _coerce_tier(h.get("tier"))
        ho_url = h.get("url")
        ho_excerpt = h.get("excerpt") or ""
        ho_source = h.get("source_name") or _derive_source_name(ho_url) or "(unknown)"
        ho_subcaps = [
            s for s in (h.get("subcap_mappings") or [])
            if isinstance(s, str) and re.match(r"^P[1-4]C\d", s)
        ]
        ho_published = _str_or_none(h.get("publish_date"))
        existing = merged.get(e_id)
        if existing is None:
            merged[e_id] = ParsedEvidence(
                e_id=e_id,
                source_name=ho_source,
                source_url=ho_url,
                excerpt=ho_excerpt or "(no excerpt)",
                claim_type=str(h.get("signal_direction") or "research_evidence").lower(),
                # Honest tier: the handoff's own (canonicalized) tier, or
                # None when it states none — never a fabricated mid-scale 5.
                tier=ho_tier,
                published_date=ho_published,
                linked_subcap_ids=ho_subcaps,
            )
        else:
            if ho_tier is not None and ho_tier != existing.tier:
                conflicts.append({
                    "kind": "tier_conflict_handoff_wins",
                    "e_id": e_id, "workbook_tier": existing.tier,
                    "handoff_tier": ho_tier,
                })
                existing.tier = ho_tier
            if ho_url:
                existing.source_url = ho_url
            if ho_source:
                existing.source_name = ho_source
            if ho_excerpt:
                existing.excerpt = ho_excerpt
            existing.published_date = ho_published or existing.published_date
            for s in ho_subcaps:
                if s not in existing.linked_subcap_ids:
                    existing.linked_subcap_ids.append(s)
    return sorted(merged.values(), key=lambda p: p.e_id), conflicts
