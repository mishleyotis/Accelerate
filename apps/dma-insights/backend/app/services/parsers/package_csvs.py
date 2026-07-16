"""CSV leaf parsers for the canonical DMA package layout.

Every parser is pure (str → list[Row]); the orchestrator
(`dma_package.parse_package`) walks the directory tree, hands each CSV
text blob to the right parser, and stitches the rows into the
`IngestedPackage` envelope.

State-branch contract:
  - All parsers tolerate an optional leading `# run_id: …` comment row
    (the exports add provenance) — _skip_provenance_header_ strips it.
  - All parsers tolerate trailing blank rows.
  - Score columns are parsed as float; "" / "N/A" / "-" → None.
  - Subcap mappings in evidence CSVs are split on `,`; rows with the
    sentinel value `ENTITY_PROFILE` (no subcap) keep it for downstream
    routing as a non-subcap evidence reference.
"""
from __future__ import annotations

import csv
import io
import re

from app.schemas.package import (
    CategoryScoreRow,
    EvidenceRow,
    IssueRow,
    PillarScoreRow,
    SubcapScoreRow,
)

_PROV_RE = re.compile(r"^#\s*run_id\s*:", re.I)


def _strip_provenance(text: str) -> str:
    lines = text.splitlines()
    if lines and _PROV_RE.match(lines[0]):
        return "\n".join(lines[1:])
    return text


# ── Alias inventories (the parsers below read these) ──────────────────
# Pulled OUT of the parsers as module-level dicts so the observation
# sidecar (`observe_csv_unknown_columns`) can compare incoming headers
# against the exact same canonical→{aliases} mapping the parser uses,
# without duplicating knowledge. Each canonical key MUST be a real
# field on the corresponding Row schema; aliases are lowercase and the
# header check is also lowercased.
SCORING_DETAIL_ALIASES: dict[str, list[str]] = {
    "subcap_id":          ["subcap_id"],
    "subcap_name":        ["subcap_name"],
    "category":           ["category"],
    "score":              ["score"],
    "confidence":         ["confidence"],
    "evidence_ids":       ["evidence_ids"],
    "source_urls":        ["source_urls"],
    "evidence_ceiling":   ["evidence_ceiling"],
    "caps_applied":       ["caps_applied"],
    "rationale":          ["rationale"],
    "proxy_searched":     ["proxy_searched"],
}

ISSUE_REGISTER_ALIASES: dict[str, list[str]] = {
    "issue_id":            ["issue_id", "id", "cap_id", "iss_id"],
    "type":                ["type", "cap_source", "cap_type", "category"],
    "severity":            ["severity", "cap_severity", "priority"],
    "status":              ["status"],
    # 2026-07-06 corpus census: client registers title their rows via
    # `description_summary` (Nicola A7), `issue` (Security Finance A5),
    # `title` (Bank of Utah A6), `gap_description`; QA registers via
    # `name`/`detail`/`finding` (BOK governance). All aliased so no row
    # can persist with an empty title again.
    "description":         ["description", "title", "finding",
                            "description_summary", "issue",
                            "gap_description", "name", "detail"],
    "evidence_ids":        ["evidence_ids", "evidence", "eids", "e_ids",
                            "evidence_id", "source"],
    "cap_formula":         ["cap_formula", "cap_logic"],
    "cap_ceiling":         ["cap_ceiling", "cap_value", "ceiling_impact",
                            "maximum_score", "max_score"],
    # Capability/subcap attribution vocabulary measured across the 41
    # client-style registers (capability_impact 17, cap_impact 6,
    # subcaps/affected_capabilities/affected_subcaps a few each).
    "affected_categories": ["affected_categories", "capabilities_affected",
                            "capability_impact", "cap_impact", "subcaps",
                            "caps", "affected_capabilities",
                            "affected_subcaps", "capability", "affected"],
    "regulator":           ["regulator"],
    "opened_on":           ["date", "date_identified", "date_opened",
                            "opened", "identified", "date_detected"],
    "resolved_on":         ["date_resolved", "resolved", "date_closed",
                            "closed"],
    # Operator-side cap metadata variants that don't have a Row field
    # yet but are common enough to be worth NOT flagging as unknown.
    # Adding them here keeps the observation queue clean; promoting any
    # of them into IssueRow can happen later without touching this dict.
    "zennify_solution":    ["zennify_solution", "salesforce_implication",
                            "milestones", "detected_batch", "validated_by",
                            "penalty_amount"],
}

# ── Issue-register header classification (client vs assessment-QA) ────
# QA registers are the assessment bot's own checklists ABOUT the
# deliverable (07_governance): headers like check_id / fix /
# auto_fixable / patch_action. Client registers describe the CLIENT's
# business issues (consent orders, breaches, market gaps) and carry a
# description + capability-impact vocabulary. Measured over all 113
# corpus packages: 54 QA registers would otherwise win the pick and
# surface filenames ("Missing governance artifact: caps_applied_log.csv")
# on the AE-facing Context page.
_QA_HEADER_TOKENS = frozenset({
    "check_id", "check", "source_check", "fix", "fix_instruction",
    "auto_fixable", "patch_action", "detection_evidence", "genuine",
    "root_cause", "artifacts_affected",
})
_CLIENT_DESC_TOKENS = frozenset({
    "description", "description_summary", "issue", "title", "finding",
    "gap_description",
})
_CLIENT_SIGNAL_TOKENS = frozenset({
    "severity", "cap_severity", "status", "regulator", "date",
    "capability_impact", "cap_impact", "capabilities_affected",
    "affected_categories", "subcaps", "caps", "affected_capabilities",
    "affected_subcaps", "cap_value", "cap_ceiling", "ceiling_impact",
})


def _norm_header(h: str) -> str:
    return re.sub(r"[\s\-]+", "_", (h or "").strip().lower())


# Title-level meta classifier for LEGACY rows persisted before `kind`
# existed (migration 055 backfill + derive_issues quality gate share
# it). Matches rows about the assessment package's own files / QA
# checks — never a client-business issue. Measured over the committed
# pack: 219/662 rows match (48 literally name a .csv/.json/.xlsx file).
ASSESSMENT_QA_TITLE_RE = re.compile(
    r"governance artifact|run_manifest|caps_applied|contradiction_log|"
    r"reasoning_chain|citation (?:density|coverage)|e-?id density|"
    r"peer references|sheet(?:s)? nam(?:e|ing)|patch block|"
    r"missing required fields|rationales? missing|workbook export|"
    r"unique e-?ids|evidence mode|\.(?:csv|json|xlsx)\b",
    re.IGNORECASE,
)


def looks_like_assessment_qa_title(title: str | None) -> bool:
    return bool(title) and bool(ASSESSMENT_QA_TITLE_RE.search(title))


# PostgreSQL-flavoured port of ASSESSMENT_QA_TITLE_RE (\b → \M; no
# (?:…) needed). Used by derive_issues' quality gate; migration 055
# carries an inline copy (alembic migrations don't import app code).
# Keep the three in lock-step.
ASSESSMENT_QA_TITLE_SQL_RE = (
    r"governance artifact|run_manifest|caps_applied|contradiction_log|"
    r"reasoning_chain|citation (density|coverage)|e-?id density|"
    r"peer references|sheets? nam(e|ing)|patch block|"
    r"missing required fields|rationales? missing|workbook export|"
    r"unique e-?ids|evidence mode|\.(csv|json|xlsx)\M|"
    # scoring-methodology notes mined into client registers (2026-07-12):
    # cap/ceiling mechanics, REC echoes, coverage-flag rows — Health-page
    # material (assessment_qa), never AE-facing client issues
    r"^rec-\d+ \(|xpil-\d+|caps? p[1-4]c|cap raised m|no_evidence flag|"
    r"urf-\d|documented as n/a|score \(\d(\.\d)?\) based on"
)


def classify_issue_register_headers(headers: list[str]) -> str:
    """'assessment_qa' | 'client' for a register's header row.

    QA signature wins first (check_id/fix/auto_fixable…); otherwise a
    description-ish column marks a client register. Header-only or
    unrecognizable rows default to 'client' (legacy behavior — the row
    parser still drops untitled rows).
    """
    norm = {_norm_header(h) for h in headers if h}
    if norm & _QA_HEADER_TOKENS:
        return "assessment_qa"
    if norm & _CLIENT_DESC_TOKENS or norm & _CLIENT_SIGNAL_TOKENS:
        return "client"
    return "client"


# P-codes at category (P1C2) or subcap (P3C2.4 / P2C2.1.3) grain.
_P_CODE_RE = re.compile(r"\bP[1-4]C\d+(?:\.\d+){0,3}\b")
# Cap level following a P-code: "P1C2 @3.0", "P1C4 cap 4.0",
# "P1C2 <= 3.0", "P3C3 Compliance at 2.5", "P3C2.4 max score M3.5",
# "Limits P4C1 @2.0". The window is cut at the NEXT P-code so
# "P1C2, P3C3 @2.5" never assigns 2.5 to P1C2.
_CAP_LEVEL_RE = re.compile(
    r"(?:@|≤|<=|\bat\b|\bcap(?:ped|s)?(?:\s+at)?\b|"
    r"\bmax(?:imum)?(?:\s+score)?\b|\bceiling\b)\s*M?\s*(\d(?:\.\d+)?)\b",
    re.IGNORECASE,
)
_E_ID_TOKEN_RE = re.compile(r"\bE-?\d{2,4}\b", re.IGNORECASE)
_CAP_VALUE_NUM_RE = re.compile(r"\bM?\s*(\d(?:\.\d+)?)\b")
_RESOLVED_STATUS_RE = re.compile(
    r"\b(resolved|settled|closed|remediated|terminated|fixed|completed)\b",
    re.IGNORECASE,
)
_OPEN_STATUS_RE = re.compile(
    r"\b(active|open|ongoing|monitoring|in.progress|unknown|pending|"
    r"wind.down)\b",
    re.IGNORECASE,
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_ISO_DATE_RE = re.compile(r"\b((?:19|20)\d{2})-(\d{1,2})(?:-(\d{1,2}))?\b")
_MONTH_YEAR_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+"
    r"((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_BARE_YEAR_RE = re.compile(r"\(?\b((?:19|20)\d{2})\b\)?")


def mine_p_codes(text: str | None) -> list[str]:
    """Ordered, de-duplicated P-codes mined from free text.

    Handles every corpus shape: "P4C4,P3C4", "P2C3.6 Agent Enablement;
    P2C4.1 Customer Intelligence", "P1C2 Governance Structure",
    "['P4C1.3', 'P2C4.1']".
    """
    if not text:
        return []
    out: list[str] = []
    for m in _P_CODE_RE.finditer(text):
        code = m.group(0)
        if code not in out:
            out.append(code)
    return out


def mine_cap_levels(text: str | None) -> dict[str, float]:
    """{P-code: cap level} pairs mined from free text ("CAPS P1C2 @3.0,
    P3C3 @2.5", "P1C4 cap 4.0", "P3C2.4 max score M3.5"). A P-code with
    no cap token in its window (before the next P-code) yields nothing —
    plain lists like "P4C4.7, P4C4.8" are never misread as caps.
    """
    if not text:
        return {}
    out: dict[str, float] = {}
    matches = list(_P_CODE_RE.finditer(text))
    for i, m in enumerate(matches):
        window_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        window = text[m.end():window_end]
        lm = _CAP_LEVEL_RE.search(window)
        if not lm:
            continue
        try:
            level = float(lm.group(1))
        except ValueError:
            continue
        if 1.0 <= level <= 5.0 and m.group(0) not in out:
            out[m.group(0)] = level
    return out


def _cap_value_float(raw: str | None) -> float | None:
    """Tolerant cap-value parse: "3.0" → 3.0, "M3.0" → 3.0, "M4 cap" →
    4.0, "No cap (resolved)" → None. Values outside the maturity band
    [1, 5] are rejected (they're prose numbers, not cap levels)."""
    f = _to_float(raw)
    if f is not None:
        return f if 1.0 <= f <= 5.0 else None
    if not raw or re.search(r"\bno\s+cap\b", raw, re.IGNORECASE):
        return None
    m = _CAP_VALUE_NUM_RE.search(raw)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    return v if 1.0 <= v <= 5.0 else None


def _fuzzy_date_iso(raw: str | None) -> str | None:
    """Tolerant date parse → ISO string. "2024-02-27" → itself,
    "2025-10" → 2025-10-01, "Oct 2022" → 2022-10-01, "(2019)" →
    2019-01-01, "Ongoing" → None. Never fabricates beyond the stated
    precision's first day."""
    if not raw:
        return None
    s = raw.strip()
    if not s or s.lower() in {"ongoing", "n/a", "-", "—", "none", "tbd"}:
        return None
    m = _ISO_DATE_RE.search(s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        d = int(m.group(3)) if m.group(3) else 1
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    m = _MONTH_YEAR_RE.search(s)
    if m:
        return f"{int(m.group(2)):04d}-{_MONTHS[m.group(1).lower()[:3]]:02d}-01"
    m = _BARE_YEAR_RE.search(s)
    if m:
        return f"{int(m.group(1)):04d}-01-01"
    return None


def canonical_issue_status(raw: str | None) -> str | None:
    """Free-text status → 'RESOLVED' | 'OPEN' | None (unstated).
    "SETTLED", "RESOLVED (2019)", "Resolved Jan 2025", "TERMINATED
    2018" → RESOLVED; ACTIVE / OPEN / MONITORING / ONGOING / UNKNOWN →
    OPEN."""
    if not raw or not raw.strip():
        return None
    if _RESOLVED_STATUS_RE.search(raw):
        return "RESOLVED"
    if _OPEN_STATUS_RE.search(raw):
        return "OPEN"
    return "OPEN"


def compose_dma_impact(row: IssueRow) -> str | None:
    """One-line DMA-impact rationale composed from the row's OWN fields
    (deterministic; never fabricated): which capabilities the issue
    caps and at what maturity level, plus the type/regulator/status
    context. E.g. "Caps P1C2 at M3.0, P3C3 at M2.5 — Regulatory (FDIC),
    open"."""
    if row.caps:
        cap_bits = ", ".join(
            f"{code} at M{level:g}" for code, level in list(row.caps.items())[:4]
        )
        head = f"Caps {cap_bits}"
    elif row.cap_ceiling is not None and row.affected_categories:
        ids = ", ".join(row.affected_categories[:4])
        head = f"Caps {ids} at M{row.cap_ceiling:g}"
    elif row.affected_categories:
        head = "Impacts " + ", ".join(row.affected_categories[:4])
    else:
        return None
    reg = (row.regulator or "").strip()
    if reg.lower() in {"internal", "market", "n/a"}:
        reg = ""
    if row.type and reg:
        source_bit = f"{row.type.strip()} ({reg})"
    elif row.type:
        source_bit = row.type.strip()
    else:
        source_bit = reg
    tail_bits = [b for b in (source_bit,) if b]
    status = canonical_issue_status(row.status)
    if status:
        tail_bits.append("resolved" if status == "RESOLVED" else "open")
    if tail_bits:
        return f"{head} — {', '.join(tail_bits)}"
    return head


def enrich_issue_row(row: IssueRow) -> IssueRow:
    """Fill the DMA-impact attribution fields IN PLACE from whatever the
    raw row carried: subcap/category ids mined from the capability
    cells, per-cap levels, canonical dates from status text, and the
    composed `dma_impact` line. Idempotent — safe on already-enriched
    rows (CSV, JSON and DOCX paths all funnel through here)."""
    # Cap levels: explicit pairs beat the flat cap_value fallback.
    hay = " ".join(
        s for s in (
            " ".join(row.affected_categories), row.cap_formula or "",
            row.dma_impact or "",
        ) if s
    )
    if not row.caps:
        row.caps = mine_cap_levels(hay)
    if not row.caps and row.cap_ceiling is not None:
        row.caps = {c: row.cap_ceiling for c in row.affected_categories
                    if _P_CODE_RE.fullmatch(c)}
    # Normalize affected ids to bare P-codes (cells like "P1C2
    # Governance Structure" keep only the code).
    codes = mine_p_codes(" ".join([*row.affected_categories, *row.caps]))
    if codes:
        row.affected_categories = codes
    # Resolved date from a "Resolved Jan 2025" status when no explicit
    # Date_Resolved column shipped.
    if row.resolved_on is None and row.status \
            and _RESOLVED_STATUS_RE.search(row.status):
        row.resolved_on = _fuzzy_date_iso(row.status)
    if row.dma_impact is None:
        row.dma_impact = compose_dma_impact(row)
    return row


def observe_csv_unknown_columns(
    text: str,
    *,
    alias_lookup: dict[str, list[str]],
    parser_name: str,
    sample_label: str = "csv",
) -> list[dict[str, object]]:
    """Return observation dicts for every CSV column header outside the
    `alias_lookup` union.

    Pure (str → list); the orchestrator wires the result through
    `IngestedPackage.parser_observations` so `package_persist.persist_package`
    can flush to the `parser_observations` table.

    Heuristic `canonical_guess` matches the same keyword heuristic the
    per-pillar parser uses so operators see consistent guidance across
    surfaces:
      *subcap* / *capability*    → subcap_id
      *evidence* and *id*        → evidence_ids
      *url* / *source*           → source_urls
      *tier*                     → tier
      *excerpt* / *note*         → excerpt
      *severity* / *cap_sev*     → severity
      *cap_source* / *source_doc* → type
      *rationale* / *narrative*  → rationale
      *score*                    → score

    State branches (one return per call):
      - no_headers → empty input or all-stripped header row → returns []
      - all_known  → every header maps to a canonical → returns []
      - mixed      → returns one dict per unknown header (de-duped on
                     value; later occurrences in the same call are
                     ignored — the table's UPSERT collapses cross-call
                     duplicates)
    """
    body = _strip_provenance(text or "")
    if not body.strip():
        return []
    reader = csv.reader(io.StringIO(body))
    headers = next(reader, None) or []
    if not headers:
        return []
    # Build the union once per call.
    known: set[str] = set()
    for aliases in alias_lookup.values():
        for a in aliases:
            known.add(a.strip().lower())
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for h in headers:
        if not h:
            continue
        norm = str(h).strip().lower()
        if not norm or norm in known or norm in seen:
            continue
        seen.add(norm)
        guess = _guess_canonical(norm)
        out.append({
            "kind": "unknown_column",
            "value": str(h),
            "canonical_guess": guess,
            "sample_context": {
                "csv": sample_label,
                "parser": parser_name,
                "neighbor_headers": [
                    str(x) for x in headers if x and str(x) != str(h)
                ][:5],
            },
        })
    return out


def _guess_canonical(norm: str) -> str | None:
    """Keyword heuristic that mirrors the per-pillar parser's guess
    logic. Best-effort; the operator confirms before promoting."""
    if "subcap" in norm or "sub_cap" in norm or "capability" in norm:
        return "subcap_id"
    if "evidence" in norm and "id" in norm:
        return "evidence_ids"
    if "url" in norm or ("source" in norm and "doc" not in norm):
        return "source_urls"
    if "tier" in norm:
        return "tier"
    if "excerpt" in norm or "note" in norm:
        return "excerpt"
    if "severity" in norm or "cap_sev" in norm:
        return "severity"
    if "cap_source" in norm or "source_doc" in norm:
        return "type"
    if "rationale" in norm or "narrative" in norm:
        return "rationale"
    if "score" in norm:
        return "score"
    return None


def _to_float(v: str | None) -> float | None:
    if v is None:
        return None
    s = v.strip()
    if not s or s in {"N/A", "-", "—", "null", "None"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_score(v: str | None) -> float | None:
    """Maturity-score parse: like ``_to_float`` but clamped to the
    canonical [1.0, 5.0] band. The XLSX fallback path already clamps
    (dma_package.py); pre-fix the CSV path ingested 5.3 / 0.4 raw,
    breaking the heatmap colour scale + peer-delta arrows downstream
    (2026-06-10 synthesis audit, CRITICAL #2). NOT for non-score
    numerics (ers, recency_months) — those keep plain ``_to_float``."""
    f = _to_float(v)
    if f is None:
        return None
    return max(1.0, min(5.0, f))


def _to_int(v: str | None) -> int | None:
    f = _to_float(v)
    return int(f) if f is not None else None


def _tier_int(value: str | None) -> int | None:
    """Evidence source tier normalized to the canonical taxonomy, or None.

    Canonical inputs are ``T1`` .. ``T7`` (the union of the source-tier
    scales the research workbooks declare — see
    ``app.schemas.package.normalize_tier``). Suffixed synthetic tiers
    (``T7-PROXY``, ``T4-PROXY``, ``T2-RB``) keep their real number; a
    label outside the taxonomy (``T10-CONTRADICTORY``, ``T9``) or a
    non-tier word (``HIGH``) yields None — the previous clamp-to-[1,8] /
    default-5 behaviour fabricated tiers that polluted the evidence
    drawer's distribution (2026-07-06 QA: "Tier 8" rows).
    """
    from app.schemas.package import normalize_tier

    return normalize_tier(value)


def _split_subcaps(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def parse_scoring_detail_csv(text: str) -> list[SubcapScoreRow]:
    """Parses `03_scoring_workbook/export_scoring_detail.csv`.

    Two flavours observed:
      - ALMA: `SubCap_ID,Category,Score,Evidence_Ceiling,Caps_Applied,Confidence`
      - WSFS: `SubCap_ID,SubCap_Name,Category,Score,Confidence,Evidence_IDs,
              Source_URLs,Evidence_Ceiling,Caps_Applied,Rationale,Proxy_Searched`
    """
    body = _strip_provenance(text)
    reader = csv.DictReader(io.StringIO(body))
    rows: list[SubcapScoreRow] = []
    for raw in reader:
        sid = (raw.get("SubCap_ID") or "").strip()
        if not sid:
            continue
        rows.append(
            SubcapScoreRow(
                subcap_id=sid,
                category_id=(raw.get("Category") or "").strip(),
                score=_to_score(raw.get("Score")) or 0.0,
                confidence=(raw.get("Confidence") or "").strip() or None,
                evidence_ceiling=_to_score(raw.get("Evidence_Ceiling")),
                caps_applied=(raw.get("Caps_Applied") or "").strip() or None,
                rationale=(raw.get("Rationale") or "").strip() or None,
                # Optional — WSFS-shape CSVs carry SubCap_Name; ALMA-shape
                # doesn't. Either way the auto-bootstrap falls back to a
                # placeholder when this is None.
                name=(raw.get("SubCap_Name") or "").strip() or None,
            )
        )
    return rows


def parse_pillar_summary_csv(text: str) -> list[PillarScoreRow]:
    """Parses `03_scoring_workbook/export_pillar_summary.csv`.

    Tolerates both:
      - `Pillar_ID,Pillar_Name,Score,Weight`
      - `pillar_id,pillar_name,score,weight`
      - `Pillar,Score,Weight`  (no explicit ID column)
    """
    body = _strip_provenance(text)
    reader = csv.DictReader(io.StringIO(body))
    rows: list[PillarScoreRow] = []
    for raw in reader:
        norm = {k.lower(): v for k, v in raw.items() if k}
        pid = (norm.get("pillar_id") or norm.get("pillar") or "").strip()
        if not pid:
            continue
        # Accept "P1", "Pillar 1", "Pillar_1" → P1; "OVERALL" passes through.
        m = re.search(r"P(?:illar)?[\s_]*([1-4])", pid, re.I)
        if m:
            pid = f"P{m.group(1)}"
        rows.append(
            PillarScoreRow(
                pillar_id=pid,
                pillar_name=(norm.get("pillar_name") or "").strip() or None,
                score=_to_score(norm.get("score")) or 0.0,
                weight=_to_float(norm.get("weight")),
            )
        )
    return rows


def parse_category_summary_csv(text: str) -> list[CategoryScoreRow]:
    """Parses `03_scoring_workbook/export_category_summary.csv`.

    Header variations:
      - ALMA: `Category_ID,Category_Name,Pillar,Score,Peer_Median,Peer_P25,Peer_P75`
      - WSFS: `category_id,category_name,pillar,score,peer_p25,peer_median,peer_p75`
    """
    body = _strip_provenance(text)
    reader = csv.DictReader(io.StringIO(body))
    rows: list[CategoryScoreRow] = []
    for raw in reader:
        norm = {k.lower(): v for k, v in raw.items() if k}
        cid = (norm.get("category_id") or "").strip()
        if not cid:
            continue
        # Pillar column may be "P1" or "P1C1"-prefixed; derive from cid.
        pillar = cid[:2] if cid.startswith("P") else (norm.get("pillar") or "").strip()
        rows.append(
            CategoryScoreRow(
                category_id=cid,
                category_name=(norm.get("category_name") or "").strip() or None,
                pillar_id=pillar,
                score=_to_score(norm.get("score")) or 0.0,
                peer_median=_to_score(norm.get("peer_median")),
                peer_p25=_to_score(norm.get("peer_p25")),
                peer_p75=_to_score(norm.get("peer_p75")),
            )
        )
    return rows


def parse_evidence_csv(text: str) -> list[EvidenceRow]:
    """Parses `01_evidence/evidence_index.csv`.

    Required cols: `Evidence_ID,Source_Name,URL,Tier,ERS,Publish_Date,
    Subcap_Mappings,Excerpt`. Optional: `Signal_Direction, Internal_Source,
    Corroboration_Count`. Tolerant of header casing.
    """
    body = _strip_provenance(text)
    reader = csv.DictReader(io.StringIO(body))
    rows: list[EvidenceRow] = []
    for raw in reader:
        norm = {k.lower(): v for k, v in raw.items() if k}
        eid = (norm.get("evidence_id") or norm.get("e_id") or "").strip()
        if not eid:
            continue
        rows.append(
            EvidenceRow(
                e_id=eid,
                source_name=(norm.get("source_name") or "").strip() or "(unnamed)",
                source_url=(norm.get("url") or norm.get("source_url") or norm.get("link") or "").strip() or None,
                tier=_tier_int(norm.get("tier")),
                ers=_to_float(norm.get("ers") or norm.get("ers_score") or norm.get("avg_ers")),
                publish_date=(norm.get("publish_date") or "").strip() or None,
                subcap_mappings=_split_subcaps(
                    norm.get("subcap_mappings")
                    or norm.get("subcaps_supported")
                    or norm.get("mapped_subcaps")
                    or norm.get("capabilities")
                ),
                excerpt=(
                    norm.get("excerpt")
                    or norm.get("claim_excerpt")
                    or norm.get("fact")
                    or norm.get("finding")
                    or norm.get("summary")
                    or ""
                ).strip(),
                signal_direction=(norm.get("signal_direction") or "").strip() or None,
                internal_source=str(norm.get("internal_source") or "").strip().lower() == "true",
                corroboration_count=_to_int(norm.get("corroboration_count")),
            )
        )
    return rows


_SEV_TOKEN_MAP = {
    "MATERIAL": "HIGH",
    "S1": "CRITICAL", "S2": "HIGH", "S3": "MEDIUM", "S4": "LOW",
    "MAJOR": "HIGH", "MODERATE": "MEDIUM", "MINOR": "MINOR",
}


def normalize_issue_severity(raw: str | None) -> str:
    """Free-text severity → badge enum token (CRITICAL/HIGH/MEDIUM/LOW/
    MINOR). S1-S4 (Bank of Utah A6, Rockland) and MATERIAL (WSFS) map;
    unknown tokens pass through for the persist layer's fallback."""
    s = (raw or "MEDIUM").strip().upper()
    return _SEV_TOKEN_MAP.get(s, s)
# Description ladder shared by client + QA registers. `title` before
# `name`/`detail` so BOK's A6 (`Title` col) and its governance CSV
# (`name`,`detail`) both yield a real title; `issue` covers Security
# Finance's headerless-id layout; `description_summary` covers Nicola.
_DESC_LADDER = (
    "description", "title", "description_summary", "issue",
    "gap_description", "finding", "name", "detail", "fix",
)
_EVIDENCE_CELL_KEYS = (
    "evidence_ids", "evidence", "eids", "e_ids", "evidence_id", "source",
)
_CAPABILITY_CELL_KEYS = (
    "affected_categories", "capabilities_affected", "capability_impact",
    "cap_impact", "subcaps", "caps", "affected_capabilities",
    "affected_subcaps", "capability", "affected",
)


def parse_issue_register_csv(text: str) -> list[IssueRow]:
    """Parses ANY issue-register CSV in the corpus — the QA governance
    checklists AND the client-business registers (08_appendices
    A5/A6/A7/A8, 01_evidence, 02_research_workbook exports).

    Header classes (see `classify_issue_register_headers`):
      - assessment_qa: `Issue_ID,Check_ID,Severity,Category,Title,
              Detail,Fix` (Wescom gov) / `issue_id,check_id,severity,
              name,detail,fix` (BOK gov) — rows get kind='assessment_qa'
              and are EXCLUDED from AE-facing surfaces downstream.
      - client: `Issue_ID,Type,Severity,Status,Description,Regulator,
              Date,Capability_Impact,Cap_Value,Evidence_IDs` (Wescom A5)
              / `Issue_ID,Severity,Title,Date,Status,Source,Subcaps,
              Ceiling_Impact` (BOK A6, "CAPS P1C2 @3.0, P3C3 @2.5") /
              `evidence_id,regulator,penalty_amount,date,description,
              severity,cap_impact,status` (LPL) / `Issue,Regulator,Date,
              Severity,Status,Milestones,E_IDs` (Security Finance) and
              more — headers drift per package; every alias measured
              from the 41 client-style corpus registers.

    Guarantees: no returned row has an empty description (untitleable
    rows are dropped); severities MATERIAL/S1-S4 normalize to the badge
    enum; capability cells are mined for P-codes + per-cap levels; date
    columns parse tolerantly; `dma_impact` is composed per row.
    """
    body = _strip_provenance(text)
    reader = csv.DictReader(io.StringIO(body))
    headers = reader.fieldnames or []
    kind = classify_issue_register_headers(list(headers))
    rows: list[IssueRow] = []
    used_ids: set[str] = set()
    for n, raw in enumerate(reader, start=1):
        norm = {_norm_header(k): (v or "") for k, v in raw.items() if k}
        # Row key priority: explicit issue_id, plain id, cap_id
        # (cap-centric layout), iss_id (BOK governance), evidence_id
        # (LPL's enforcement register keys rows by E-ID). Rows with a
        # real description but NO id get a synthesized sequential id —
        # dropping them silently lost Security Finance's whole register.
        iid = (
            norm.get("issue_id") or norm.get("id") or norm.get("cap_id")
            or norm.get("iss_id") or norm.get("evidence_id") or ""
        ).strip()
        desc = ""
        for key in _DESC_LADDER:
            desc = (norm.get(key) or "").strip()
            if desc:
                break
        if not desc:
            continue  # untitleable — never persist a blank-title row
        if not iid:
            iid = f"ISS-{n:03d}"
        while iid in used_ids:
            iid = f"{iid}b"
        used_ids.add(iid)
        sev = (
            norm.get("severity") or norm.get("cap_severity")
            or norm.get("priority") or "MEDIUM"
        ).strip().upper()
        sev = _SEV_TOKEN_MAP.get(sev, sev)
        # Capability attribution: mine P-codes across every
        # capability-ish cell PLUS the evidence cell (Security Finance
        # writes "P1C2 Governance Structure, …" in E_IDs). The E-ID
        # regex never matches P-codes and vice versa, so cross-mining
        # is safe. Legacy cells with no P-codes fall back to the old
        # bracket-strip split so category-less registers keep behavior.
        cap_cells = " ; ".join(
            norm.get(k) or "" for k in _CAPABILITY_CELL_KEYS
        )
        ev_cells = " ; ".join(norm.get(k) or "" for k in _EVIDENCE_CELL_KEYS)
        ceiling_raw = (
            norm.get("cap_ceiling") or norm.get("cap_value")
            or norm.get("ceiling_impact") or norm.get("maximum_score")
            or norm.get("max_score") or ""
        )
        affected = mine_p_codes(f"{cap_cells} {ev_cells} {ceiling_raw}")
        if not affected:
            raw_aff = (
                norm.get("affected_categories")
                or norm.get("capabilities_affected") or ""
            )
            affected = [
                s.strip().strip("'").strip('"')
                for s in raw_aff.strip("[]").split(",") if s.strip()
            ]
        # `cap_source` carries the document name OR the analyst's
        # attribution. Surface it on `type` when an explicit `type`
        # column isn't provided so the FE chip has something concrete.
        type_val = (
            norm.get("type") or norm.get("cap_source") or ""
        ).strip() or None
        # Evidence: mine E-ID tokens; fall back to splitting the raw
        # cell when a register uses non-E ids (Rockland INT-HUBBL-*).
        ev_ids = [m.group(0).upper() for m in _E_ID_TOKEN_RE.finditer(ev_cells)]
        ev_ids = list(dict.fromkeys(ev_ids))
        if not ev_ids:
            primary_ev = norm.get("evidence_ids") or norm.get("evidence") or ""
            ev_ids = [
                s.strip().strip("'").strip('"')
                for s in re.split(r"[;,]", primary_ev.strip("[]"))
                if s.strip() and not _P_CODE_RE.match(s.strip())
            ]
        cap_formula = (
            norm.get("cap_formula") or norm.get("cap_logic") or ""
        ).strip() or None
        row = IssueRow(
            issue_id=iid,
            type=type_val,
            severity=sev,
            status=(norm.get("status") or "").strip() or None,
            description=desc,
            evidence_ids=ev_ids,
            cap_formula=cap_formula,
            cap_ceiling=_cap_value_float(ceiling_raw),
            affected_categories=affected,
            kind=kind,
            regulator=(norm.get("regulator") or "").strip() or None,
            opened_on=_fuzzy_date_iso(
                norm.get("date") or norm.get("date_identified")
                or norm.get("date_opened") or norm.get("opened")
                or norm.get("identified") or norm.get("date_detected")
            ),
            resolved_on=_fuzzy_date_iso(
                norm.get("date_resolved") or norm.get("resolved")
                or norm.get("date_closed") or norm.get("closed")
            ),
            caps=mine_cap_levels(f"{cap_cells} ; {ceiling_raw}"),
        )
        rows.append(enrich_issue_row(row))
    return rows
