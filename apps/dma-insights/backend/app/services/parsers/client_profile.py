"""Client Profile DOCX parser.

Walks ``04_reports/*_Client_Profile_Research_Report.docx`` — a separate
DOCX from the Assessment_Report — and extracts the firmographic
narrative, focus areas (with verbatim source quotes), leadership
overview, and financial highlights.

State-branch contract:

  - ``no_docx_found``       — no Client_Profile DOCX in the package;
    parser returns empty ClientProfileParseResult.
  - ``partial_coverage``    — DOCX parsed but ≥1 of {focus_areas,
    leadership, financial_highlights} came back empty.
  - ``full_coverage``       — all four buckets populated.

The output feeds three persistence sinks:

  - ``focus_areas`` table (added in migration 018) — verbatim quote +
    source_path + page_number per row.
  - ``firmographics.narrative_md`` column.
  - ``firmographics.leadership`` JSONB + ``financial_highlights`` JSONB.

The classifier maps the AlmaBank/WSFS section taxonomy ("2.1 Corporate
Identity", "4.3 Leadership Overview", "1.2 Top Findings", etc.) to
canonical buckets. Header drift across template variants is tolerated
by liberal regex matching.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger(__name__)

CoverageState = Literal["no_docx_found", "partial_coverage", "full_coverage"]


@dataclass(slots=True)
class FocusArea:
    title: str
    verbatim_quote: str
    source_path: str | None = None
    page_number: int | None = None
    involved_subcap_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LeadershipEntry:
    name: str
    role: str | None = None
    raw_text: str = ""


@dataclass(slots=True)
class ClientProfileParseResult:
    focus_areas: list[FocusArea] = field(default_factory=list)
    leadership: list[LeadershipEntry] = field(default_factory=list)
    financial_highlights: dict[str, Any] = field(default_factory=dict)
    firmographics_narrative_md: str = ""
    state_kind: CoverageState = "no_docx_found"
    warnings: list[dict[str, Any]] = field(default_factory=list)
    # D5 Context timeline mined from the report's "Digital Evolution Timeline"
    # table (Date | Initiative | Evidence | Zennify Relevance). Each item is a
    # `TimelineEventCandidate` (kept as Any here to avoid a schema import at
    # dataclass-definition time). Used as a DERIVED fallback when no dated
    # evidence facts produced events.
    timeline_events: list[Any] = field(default_factory=list)
    # D5 sentiment mined from the report's "Sentiment Overview" table —
    # {sources:[{source, rating}]}. Fallback for `firmographics.sentiment`
    # when no A#_sentiment_data.csv / entity_profile sentiment shipped. Empty
    # unless the table is genuinely rating-shaped (no fabrication).
    sentiment: dict[str, Any] = field(default_factory=dict)
    # D5 acquisition-history events mined from the report's "Acquisition
    # History" table → TimelineEventCandidate[] (kind='acquisition'). Merged
    # into timeline_events by the orchestrator (the D5 acquisitions list reads
    # kind='acquisition'). Empty unless a dated acquisition table is present.
    acquisition_events: list[Any] = field(default_factory=list)
    # D2 Part 5.1 PRIMARY-rung material: normalized findings mined from the
    # report's "Key Findings / Strategic Priorities / Digital Evolution /
    # Technology Landscape" sections (audit: this report ships in 82/113
    # packages but fed ZERO insight cards). Items are
    # `section_analysis.ProfileFinding` (kept as Any to avoid an import at
    # dataclass-definition time); the orchestrator feeds them into
    # `insights_from_profile_findings`.
    profile_findings: list[Any] = field(default_factory=list)
    # 2026-07-06 issue-register mining: the report's "5. Risk & Issues /
    # 5.1 Issue Register" table (ID/Type/Severity/Status/Description/
    # Cap Impact/Cap Value — 69/80 corpus reports carry the section) as
    # normalized dicts, plus a prose fallback mining issue STATEMENTS
    # (sentence-level, nlp.segment) from Risk/Issues sections when no
    # table ships. Lower-priority than the appendix CSV registers — the
    # orchestrator dedups by issue_id / text similarity.
    issue_rows: list[dict[str, Any]] = field(default_factory=list)
    # Subcap-level cap attribution from the "Trigger → Capabilities
    # Affected → Maximum Score" table ({trigger, subcap_ids, max_score})
    # — merged into matching issue rows so the DMA impact reaches
    # subcap grain (the CSV registers mostly stop at category grain).
    issue_cap_triggers: list[dict[str, Any]] = field(default_factory=list)


# ── Header regexes (liberal — match header drift across templates) ──

RE_TOP_FINDINGS = re.compile(r"top\s+findings|focus\s+areas?|key\s+findings", re.I)
RE_CRITICAL_GAPS = re.compile(r"critical\s+gaps?|priority\s+gaps?", re.I)
RE_LEADERSHIP = re.compile(r"leadership\s+(overview|profile|team)|key\s+leaders", re.I)
RE_FINANCIALS = re.compile(
    r"financial\s+(highlights?|trajectory)|scale\s+metrics?", re.I,
)
RE_CORP_IDENTITY = re.compile(
    r"corporate\s+identity|entity\s+(profile|snapshot)|firmographics?", re.I,
)
# Strategic objectives: the bank's own forward-looking strategy
# (Five-Year Plan / Three-Year Vision / Strategic Imperatives /
# Transformation Roadmap / Strategic Bets / Strategic Pillars).
# These differ from "Top Findings" — they are the client's stated
# priorities, not Zennify's gap assessment — but share the focus_areas
# table; `source_path='docx:strategic_section'` distinguishes them so
# the focus-area synthesizer + downstream queries can route correctly.
RE_STRATEGIC_OBJECTIVES = re.compile(
    r"strategic\s+(priorit(?:ies|y)|imperatives?|objectives?|"
    r"pillars?|bets?|initiatives?|roadmap|plan|vision|themes?|"
    r"focus(?:\s+areas?)?)"
    r"|(?:five|three|3|5)[\s\-]year\s+(strategic\s+)?(plan|vision|roadmap|strategy)"
    r"|transformation\s+roadmap|strategic\s+transformation"
    r"|(?:most\s+recent|recent)\s+strategic\s+objectives?",
    re.I,
)
# Scaffolding inside a strategic-objectives section that is NOT itself a
# priority: the section preamble ("The following objectives are drawn
# directly from …") and the Zennify SO-WHAT line threaded under each
# priority ("Zennify Relevance: …"). These are analyst framing, never the
# client's stated priority (2026-07 TowneBank screenshot: both leaked as
# focus cards). Skipped at extraction so only the priorities themselves
# become focus areas.
RE_STRATEGIC_META = re.compile(
    r"^\s*(the\s+following\b"
    r"|these\s+\w+\s+(objectives?|priorities|findings?)\b"
    r"|this\s+section\b"
    r"|zennify\s+relevance\b"
    r"|implications?\s+for\s+zennify\b"
    r"|each\s+(insight|finding)\b)",
    re.I,
)
# A numbered strategic priority the report enumerates ("1. Organic growth
# + selective M&A in insurance"). The label after the number is a clean
# priority HEADLINE (the title); any prose that follows — the supporting
# quote — is folded into the description, never emitted as its own card.
RE_NUMBERED_PRIORITY = re.compile(r"^\s*(\d{1,2})[.)]\s+(\S.*)$")
# D2 Part 5.1: the two remaining first-class Client Profile sections the
# insight ladder mines (beyond Key Findings + Strategic Priorities).
RE_DIGITAL_EVOLUTION = re.compile(
    r"digital\s+(?:evolution|transformation|journey|maturity|initiatives?)",
    re.I,
)
RE_TECH_LANDSCAPE = re.compile(
    r"technology\s+(?:landscape|stack|environment|footprint|profile)|"
    r"current\s+technology|tech\s+stack|systems?\s+landscape",
    re.I,
)
# Subcap ID extractor — matches P{1-4}C{1-9}.{1-9}.{1-9} (with optional Tn)
RE_SUBCAP_ID = re.compile(r"\bP[1-4]C\d+(?:\.\d+){1,3}(?:[Tt]\d)?\b")
# Page-number extractor — "p. 5", "page 12", "(p. 23)"
RE_PAGE_NUM = re.compile(r"\bp(?:age|\.)?\s*(\d{1,4})\b", re.I)
# Source-path extractor — anything like "Source: foo" or quoted URLs
RE_SOURCE_PATH = re.compile(
    r"source\s*[:\-]\s*(.+?)(?:$|;|\||\.)", re.I,
)
# Leadership name detector — "Name, Role" or "Name — Role"
RE_NAME_ROLE = re.compile(
    r"^([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){1,3})\s*[,\-–—]\s*(.+)$",  # noqa: RUF001
)
# Evidence-ID inside a timeline cell ("E-008", "E028", "E-008; E-012").
RE_EVIDENCE_ID = re.compile(r"\bE-?\d{2,}\b", re.I)
_MONTH_NUM = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"], 1,
    )
}


def _normalize_timeline_date(raw: str) -> str:
    """Map a timeline-cell date to a string `parse_event_date` accepts.

    Handles the textual-month forms the Client Profile uses (``Jan 2021``,
    ``March 1, 2025``, ``Q1 2021``) on top of the bare-year / range / ISO
    forms `parse_event_date` already understands (``2016``, ``2019-2022``).
    Never invents a date — returns "" when nothing date-shaped is present.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    low = s.lower()
    # "Jan 2021" / "January 1, 2025" / "Mar 1 2025"
    mm = re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*"
        r"(\d{1,2})?\s*,?\s*(\d{4})\b",
        low,
    )
    if mm:
        mon = _MONTH_NUM[mm.group(1)]
        year = mm.group(3)
        if mm.group(2):
            return f"{year}-{mon:02d}-{int(mm.group(2)):02d}"
        return f"{year}-{mon:02d}"
    # "Q1 2021" or "2021 Q1" → YYYY-Qn (parse_event_date handles it).
    qm = re.search(r"\bq([1-4])\b[^0-9]*?(\d{4})\b", low) or re.search(
        r"\b(\d{4})\b[^0-9]*?\bq([1-4])\b", low,
    )
    if qm:
        year = re.search(r"\d{4}", qm.group(0)).group(0)
        quarter = re.search(r"q([1-4])", qm.group(0)).group(1)
        return f"{year}-Q{quarter}"
    return s  # bare year / range / ISO → parse_event_date handles it


def _looks_like_timeline_table(table: dict[str, Any]) -> bool:
    """A `Date | Initiative/Event | … | Relevance` table shape."""
    head = [h.lower().strip() for h in table.get("header", [])]
    if len(head) < 2 or len(table.get("rows", [])) < 1:
        return False
    has_date = any(("date" in h or "year" in h or "when" in h) for h in head)
    has_event = any(
        ("initiative" in h or "event" in h or "milestone" in h
         or "development" in h or "activity" in h) for h in head
    )
    return has_date and has_event


def _date_cell_precision(normalized: str) -> str:
    """Precision label for a normalised date cell (Part 8.2 honesty flag).

    The Digital Evolution Timeline's date cell is authoritative (the
    analyst dated the row), so precision reflects the cell's own grain —
    never ``publish_fallback``.
    """
    s = (normalized or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return "day"
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return "month"
    if re.fullmatch(r"\d{4}-[Qq][1-4]", s):
        return "quarter"
    return "year"


def _cell_evidence_ids(cell: str) -> list[str]:
    """All E-IDs in a table cell, normalised to ``E-###`` (order kept)."""
    out: list[str] = []
    for m in RE_EVIDENCE_ID.finditer(cell or ""):
        token = m.group(0).upper()
        eid = token if "-" in token else "E-" + token[1:]
        if eid not in out:
            out.append(eid)
    return out


def _extract_digital_timeline(tables: list[dict[str, Any]]) -> list[Any]:
    """Mine the "Digital Evolution Timeline" table → TimelineEventCandidate[].

    Reuses `facts_extractor` for date normalisation + kind classification so
    DOCX-sourced events are shaped identically to evidence-derived ones, and
    the shared NLP platform for the Part 8.2 fields: titlecraft display
    titles (verbatim initiative+relevance preserved in ``body``), native
    polarity ``signal``, ``date_precision`` from the date cell's own grain,
    ``subcap_ids``/``evidence_e_ids`` mined from the row's cells. Negated
    absences ("No M&A activity") are suppressed — they are not events.
    Rows with an unparseable date or empty initiative are skipped (never
    fabricated).
    """
    from app.schemas.package import TimelineEventCandidate
    from app.services.nlp import polarity as nlp_polarity
    from app.services.parsers.facts_extractor import (
        classify_fact_kind,
        event_title,
        extract_refs,
        parse_event_date,
    )

    cand = [t for t in tables if _looks_like_timeline_table(t)]
    if not cand:
        return []
    table = cand[0]
    head = [h.lower().strip() for h in table["header"]]

    def _col(*keys: str) -> int | None:
        for i, h in enumerate(head):
            if any(k in h for k in keys):
                return i
        return None

    i_date = _col("date", "year", "when")
    i_date = 0 if i_date is None else i_date
    i_title = _col("initiative", "event", "milestone", "development", "activity")
    i_ev = _col("evidence", "e-id", "eid", "citation")
    i_body = _col(
        "relevance", "zennify", "implication", "significance", "detail",
        "description", "note",
    )

    out: list[Any] = []
    seen: set[tuple[str, Any, str]] = set()
    for row in table["rows"]:
        if not row or all(not (c or "").strip() for c in row):
            continue
        date_raw = row[i_date] if i_date < len(row) else ""
        normalized = _normalize_timeline_date(date_raw)
        dt = parse_event_date(normalized)
        if dt is None:
            continue
        title = ""
        if i_title is not None and i_title < len(row):
            title = (row[i_title] or "").strip()
        if not title and len(row) > 1:
            title = (row[1] or "").strip()
        if not title:
            continue
        body = None
        if i_body is not None and i_body < len(row):
            body = (row[i_body] or "").strip() or None
        evidence_e_ids: list[str] = []
        if i_ev is not None and i_ev < len(row):
            evidence_e_ids = _cell_evidence_ids(row[i_ev] or "")
        e_id = evidence_e_ids[0] if evidence_e_ids else None
        # Collapse in-cell newlines/runs of whitespace for clean rendering
        # (a multi-line "Initiative" cell renders as one event title).
        title = re.sub(r"\s+", " ", title).strip()
        if body:
            body = re.sub(r"\s+", " ", body).strip() or None
        combined = f"{title}. {body}" if body else title
        if nlp_polarity.is_negated_absence(combined):
            continue  # "No M&A activity" rows are absences, not events
        kind = classify_fact_kind(combined) or "milestone"
        display_title = event_title(title)
        # Nothing is lost: the verbatim initiative rides in body when the
        # display title compressed it.
        body_verbatim = combined if display_title != title else (body or None)
        key = (kind, dt, display_title[:60].lower())
        if key in seen:
            continue
        seen.add(key)
        subcap_ids, cited = extract_refs(combined)
        for eid in cited:
            if eid not in evidence_e_ids:
                evidence_e_ids.append(eid)
        out.append(
            TimelineEventCandidate(
                event_date=dt,
                kind=kind,
                title=display_title[:300],
                body=(body_verbatim[:1000] if body_verbatim else None),
                e_id=e_id,
                signal=nlp_polarity.signal_for_kind(combined, kind),
                date_precision=_date_cell_precision(normalized),
                evidence_e_ids=evidence_e_ids[:6],
                subcap_ids=subcap_ids,
            )
        )
    return out


def _iter_paragraphs(doc: Any) -> list[dict[str, Any]]:
    """Yield {text, style} dicts per non-empty paragraph."""
    out: list[dict[str, Any]] = []
    for p in doc.paragraphs:
        text = (p.text or "").strip()
        if not text:
            continue
        style = ""
        try:
            style = p.style.name if p.style else ""
        except AttributeError:
            style = ""
        out.append({"text": text, "style": style})
    return out


def _iter_tables(doc: Any) -> list[dict[str, Any]]:
    """Snapshot every table as {header_row, rows: list[list[str]]}.

    Only used as a *fallback* for buckets the paragraph walker missed —
    AlmaBank's Leadership Overview lives in a table, WSFS may render
    findings via tables too.
    """
    out: list[dict[str, Any]] = []
    for t in getattr(doc, "tables", []) or []:
        if not t.rows:
            continue
        rows: list[list[str]] = []
        for row in t.rows:
            rows.append([(c.text or "").strip() for c in row.cells])
        if not rows or not any(any(c for c in r) for r in rows):
            continue
        header = rows[0]
        out.append({"header": header, "rows": rows[1:], "all_rows": rows})
    return out


def _table_looks_like_leadership(table: dict[str, Any]) -> bool:
    """Heuristic: header row identifies a person-row table.

    Two accepted shapes:
      1. Canonical (Alma): explicit `Name` + `Title|Role|Position` cols.
      2. Combined-cell (WSFS/Calprivate): first column header is exactly
         `Executive` and the cell carries `name <sep> title` combined
         (see `_split_name_title_combined`).
    Entity-metadata tables like `Entity Name | WSFS Financial Corporation`
    or `Legal Name | …` are explicitly rejected — they pass a naive
    "header contains name" check but represent entity key/value pairs,
    not executives.
    """
    head = [h.lower().strip() for h in table["header"]]
    if not head or len(table["rows"]) < 1:
        return False
    # Branch 1: explicit name + title/role/position columns.
    has_name = any("name" in h or "executive" in h for h in head)
    has_role = any(
        ("title" in h or "role" in h or "position" in h) for h in head
    )
    if has_name and has_role:
        return True
    # Branch 2: first column is exactly "Executive" (combined name+title).
    return head[0] == "executive"


def _split_name_title_combined(cell: str) -> tuple[str, str | None]:
    """Split a combined 'Name + Title' cell.

    Real-world shapes:
      • WSFS:  'Jim Wechsler\\nEVP Chief Commercial Banking'  (newline)
      • Calprivate: 'Rick Sowers — President & CEO'           (em-dash)
      • AmeriCU:    'Ron Belle | Chief Lending Officer'       (pipe)
    Returns (name, title|None). When no separator is found the entire
    cell is treated as the name and title is None.
    """
    text = cell.strip()
    for sep in ("\n", " — ", " - ", " | "):
        if sep in text:
            name, _, title = text.partition(sep)
            return name.strip(), (title.strip() or None)
    return text, None


def _extract_leadership_from_tables(
    tables: list[dict[str, Any]],
) -> list[LeadershipEntry]:
    """Walk all tables; aggregate rows from EVERY matching leadership
    table.

    Real-world packages sometimes split executives across multiple
    tables (WSFS: 4 separate `Executive | Hire/Tenure | …` tables, one
    per role family). The original `break` after the first match
    skipped tables 2-4 → only ~3 of 16 executives surfaced.
    """
    out: list[LeadershipEntry] = []
    seen_names: set[str] = set()
    for tbl in tables:
        if not _table_looks_like_leadership(tbl):
            continue
        head = [h.lower().strip() for h in tbl["header"]]
        name_idx = next(
            (i for i, h in enumerate(head) if "name" in h or "executive" in h),
            0,
        )
        role_idx = next(
            (i for i, h in enumerate(head)
             if "title" in h or "role" in h or "position" in h),
            None,
        )
        # Edge case: a single header cell like "Name / Title" matches
        # BOTH name and role keywords. Detect and force combined-cell
        # split (Nicola's shape).
        combined_name_title = (
            role_idx is not None
            and role_idx == name_idx
        )
        for r in tbl["rows"]:
            if name_idx >= len(r):
                continue
            name_cell = r[name_idx].strip()
            if (role_idx is not None and role_idx < len(r)
                    and not combined_name_title):
                name = name_cell
                role = r[role_idx].strip() or None
                # Even when the name column is supposedly separate, it
                # may carry the role appended on a newline (Odlum
                # `Name & Credentials` cells). Split it.
                if "\n" in name:
                    name = name.split("\n", 1)[0].strip()
            else:
                # Combined-cell shape — split on the first known sep.
                name, role = _split_name_title_combined(name_cell)
            if not name or len(name) < 3:
                continue
            # Dedup across tables: same person sometimes appears in
            # multiple sub-tables (WSFS reuses executives across role
            # families).
            key = name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            out.append(LeadershipEntry(
                name=name, role=role, raw_text=" | ".join(r),
            ))
    return out


def _section_bodies(paragraphs: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Group paragraphs by their immediately-preceding heading."""
    sections: dict[str, list[str]] = {}
    current_head = ""
    for p in paragraphs:
        if "Heading" in p["style"]:
            current_head = p["text"]
            sections.setdefault(current_head, [])
            continue
        if current_head:
            sections[current_head].append(p["text"])
    return sections


# Bot run-log lines the DOCX writer sometimes embeds ("SECTION 1
# COMPLETE — Assessment ID DMA-… | Evidence Mode: PUBLIC | …"). These
# are pipeline metadata, never client content — served verbatim they
# read as broken data (2026-06-10 operator finding). One guard, used by
# every paragraph emitter.
RE_PIPELINE_META = re.compile(
    r"SECTION\s+\d+\s+COMPLETE|Assessment\s+ID\s+DMA-|"
    r"Evidence\s+Mode:\s*(PUBLIC|HYBRID)|^Batch\s+\d+\s*/",
    re.I,
)

# Leading "TOKEN | " label/id prefixes ("F-002 | …", "Maturity
# implication | …") concatenated into prose by the section writers.
RE_LABEL_PREFIX = re.compile(r"^(#?\d{1,3}|[A-Za-z][\w .#&-]{0,30})\s*\|\s+(?=.{8,})")


def _clean_quote(para: str) -> str | None:
    """None when the paragraph is pipeline metadata; else the paragraph
    with any leading label prefix stripped. When a whole findings ROW
    leaked into prose ("F-005 | statement | rationale | …"), the leading
    id prefix strip leaves a residual multi-cell seam — keep the first
    substantive cell (the finding statement) rather than shipping the raw
    pipe dump as a verbatim quote."""
    if RE_PIPELINE_META.search(para):
        return None
    cleaned = RE_LABEL_PREFIX.sub("", para).strip()
    if " | " in cleaned:
        segments = [s.strip() for s in cleaned.split(" | ") if s.strip()]
        first_substantive = next((s for s in segments if len(s) >= 16), "")
        cleaned = (first_substantive
                   or (max(segments, key=len) if segments else cleaned))
    return cleaned


def _extract_focus_areas(sections: dict[str, list[str]]) -> list[FocusArea]:
    """Walk every section whose head matches Top Findings / Focus
    Areas / Critical Gaps and emit one FocusArea per body paragraph.

    Each paragraph is treated as a focus area; the verbatim_quote is
    the paragraph text. Source path and page number are extracted via
    regex when present.
    """
    out: list[FocusArea] = []
    for head, body in sections.items():
        if not (RE_TOP_FINDINGS.search(head) or RE_CRITICAL_GAPS.search(head)):
            continue
        for para in body:
            if len(para) < 32:
                continue
            cleaned = _clean_quote(para)
            if cleaned is None or len(cleaned) < 32:
                continue
            page_m = RE_PAGE_NUM.search(para)
            page = int(page_m.group(1)) if page_m else None
            src_m = RE_SOURCE_PATH.search(para)
            src = src_m.group(1).strip() if src_m else None
            subcaps = RE_SUBCAP_ID.findall(para)
            title = head.split(".", 1)[-1].strip()[:120] or "Focus area"
            out.append(FocusArea(
                title=title,
                verbatim_quote=cleaned,
                source_path=src,
                page_number=page,
                involved_subcap_ids=list(dict.fromkeys(subcaps)),
            ))
    return out


def _extract_strategic_objectives(
    sections: dict[str, list[str]],
) -> list[FocusArea]:
    """Walk every section whose head matches the strategic-objectives
    pattern and emit one FocusArea per body paragraph.

    These rows carry ``source_path = 'docx:strategic_section'`` so that
    downstream consumers (the focus-area synthesizer in particular)
    can distinguish them from assessment-derived "Top Findings". The
    operator's mandate: strategic objectives in the research report
    should be used as-is; Gemini synthesis only fills in when they're
    absent.

    Title contract (operator 2026-07): the TITLE is always a concise
    strategic-priority headline — the verbatim label when the report
    numbers the priorities ("1. Organic growth + selective M&A in
    insurance"), with the supporting prose quote that follows folded into
    the description (never emitted as its own fragment-titled card). For a
    section that lists priorities as standalone prose (no numbering) each
    paragraph is one priority; the display layer humanizes any sentence-
    fragment title. Section preamble + "Zennify Relevance:" analyst lines
    are dropped.
    """
    out: list[FocusArea] = []
    seen_quotes: set[str] = set()
    for head, body in sections.items():
        if not RE_STRATEGIC_OBJECTIVES.search(head):
            continue
        # Don't double-classify a "Strategic Top Findings" section as
        # both strategic + top findings — the Top Findings extractor
        # gets priority.
        if RE_TOP_FINDINGS.search(head) or RE_CRITICAL_GAPS.search(head):
            continue
        pending: FocusArea | None = None   # open numbered priority
        pending_quotes: list[str] = []     # its supporting prose
        for para in body:
            para = para.strip()
            if len(para) < 12:
                continue
            # Section preamble / Zennify SO-WHAT lines are analyst framing,
            # not priorities.
            if RE_STRATEGIC_META.search(para):
                continue
            m = RE_NUMBERED_PRIORITY.match(para)
            if m:
                # A new numbered priority closes the previous one, folding
                # its collected prose into the description.
                if pending is not None:
                    if pending_quotes:
                        pending.verbatim_quote = " ".join(pending_quotes)[:1000]
                    out.append(pending)
                    pending, pending_quotes = None, []
                label = re.sub(r"\s+", " ", m.group(2)).strip(" .—–-").strip()  # noqa: RUF001
                if not label:
                    continue
                key = label.lower()[:160]
                if key in seen_quotes:
                    continue  # duplicate priority (summary + detail lists)
                seen_quotes.add(key)
                page_m = RE_PAGE_NUM.search(para)
                pending = FocusArea(
                    # The numbered label IS the headline; the prose quote
                    # (folded in below) is the description.
                    title=label[:120],
                    verbatim_quote=label,
                    source_path="docx:strategic_section",
                    page_number=int(page_m.group(1)) if page_m else None,
                    involved_subcap_ids=list(dict.fromkeys(RE_SUBCAP_ID.findall(para))),
                )
                continue
            if pending is not None:
                # Prose supporting the open numbered priority — its quote.
                pending_quotes.append(para)
                for sid in RE_SUBCAP_ID.findall(para):
                    if sid not in pending.involved_subcap_ids:
                        pending.involved_subcap_ids.append(sid)
                continue
            # Standalone-prose priority (section isn't numbered) — each
            # paragraph is one priority. Dedup on the normalized quote.
            if len(para) < 24:
                continue
            key = re.sub(r"\s+", " ", para.lower())[:160]
            if key in seen_quotes:
                continue
            seen_quotes.add(key)
            page_m = RE_PAGE_NUM.search(para)
            page = int(page_m.group(1)) if page_m else None
            subcaps = RE_SUBCAP_ID.findall(para)
            # Trim leading bullet glyphs + list numbering for a clean
            # title; fall back to the section heading when the body is
            # all narrative. Sentence-fragment titles are humanized by
            # focus_area_sanity at render time.
            title_src = re.sub(r"^[•\-\*\d\.\)\s]+", "", para).strip()
            title = (title_src[:120] or head[:120] or "Strategic objective")
            out.append(FocusArea(
                title=title,
                verbatim_quote=para,
                source_path="docx:strategic_section",
                page_number=page,
                involved_subcap_ids=list(dict.fromkeys(subcaps)),
            ))
        # Flush a trailing open priority.
        if pending is not None:
            if pending_quotes:
                pending.verbatim_quote = " ".join(pending_quotes)[:1000]
            out.append(pending)
    return out


# The DMA findings/gaps tables carry a "(→OBJ-2, HIGH)" objective+priority
# tail on the finding statement — split it off the thesis title.
_FA_OBJ_PRI_RE = re.compile(
    r"\s*\(\s*(?:→|->)?\s*(?:OBJ-\d+)?\s*[,;]?\s*"
    r"(?:CRITICAL|HIGH|MEDIUM|MED|LOW)?\s*\)\s*$", re.I)
# A cell that is nothing but a finding id ("F-001", "CG-2", "IC-003") — never
# a usable title.
_FA_ROW_ID_RE = re.compile(r"^(?:F|CG|IC|OBS|GAP|RISK)-?\d+$", re.I)
# Inline "[E-###]" / bare "E-###" citation markup stripped from a verbatim
# quote (the ids live in the evidence layer, not the prose).
_FA_EID_MARKUP_RE = re.compile(r"\s*\[?\bE-(?:[A-Z]+-)?\d+\b\]?")


def _col_role(
    header: list[str], *keywords: str, exclude: tuple[str, ...] = (),
) -> int | None:
    """Index of the first column whose (lowercased) header contains any
    ``keywords`` and none of ``exclude``; None when no column matches."""
    for i, h in enumerate(header):
        hl = h.lower()
        if any(k in hl for k in keywords) and not any(x in hl for x in exclude):
            return i
    return None


def _cell_at(cells: list[str], i: int | None) -> str:
    """Cell value at index ``i`` (empty string when the column is absent)."""
    return cells[i] if (i is not None and 0 <= i < len(cells)) else ""


def _clean_table_quote(text: str) -> str:
    """A citable verbatim quote from an observation/evidence cell: strip
    inline E-id markup, collapse whitespace, and if a residual ' | ' seam
    remains keep the most substantive segment — never a raw row dump."""
    cleaned = _FA_EID_MARKUP_RE.sub("", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" |;:—–-")  # noqa: RUF001
    if " | " in cleaned:
        cleaned = max((s.strip() for s in cleaned.split(" | ")), key=len)
    return cleaned


def _extract_focus_areas_from_tables(
    tables: list[dict[str, Any]],
) -> list[FocusArea]:
    """Map a Client-Profile findings/gaps/observations table to structured
    focus areas.

    These tables are the richest strategic source in the pack — DMA "Top
    Findings" (``ID | Finding | Observation (Evidence) | Implication |
    Zennify Solution``), "Critical Gaps" (``ID | Critical Gap | Evidence |
    Solution``), "Insight Cards" (``ID | Factual Observation (Evidence) |
    Analytical Judgment | … | Subcaps | Priority``). The prior fallback
    joined every cell with " | " into ``verbatim_quote`` and mis-assigned a
    data cell to ``source_path``; the gold quote is the OBSERVATION/EVIDENCE
    cell and the title is the FINDING statement, so map columns by header
    role and ship a citable quote + a thesis title, never the raw row.
    """
    for tbl in tables:
        header = [str(h).strip() for h in tbl["header"]]
        head_l = [h.lower() for h in header]
        if not any(
            "finding" in h or "observation" in h or "gap" in h or "issue" in h
            for h in head_l
        ):
            continue
        id_idx = _col_role(header, "id")
        stmt_idx = _col_role(
            header, "finding", "critical gap", "priority gap", "gap", "issue",
            exclude=("evidence",),
        )
        if stmt_idx is None:
            stmt_idx = _col_role(header, "observation", "judgment")
        ev_idx = _col_role(header, "evidence", "observation")
        subcap_idx = _col_role(header, "subcap")
        out: list[FocusArea] = []
        for r in tbl["rows"]:
            cells = [str(c).strip() for c in r]
            if not any(cells):
                continue
            row_id = _cell_at(cells, id_idx)
            statement = _FA_OBJ_PRI_RE.sub(
                "", _cell_at(cells, stmt_idx)).strip(" .—–-")  # noqa: RUF001
            # The verbatim quote is the evidence/observation cell (the
            # grounding); fall back to the statement when there is no
            # distinct evidence column (or it is just an E-id list).
            quote = (_clean_table_quote(_cell_at(cells, ev_idx))
                     or _clean_table_quote(statement))
            if not quote or len(quote) < 16:
                continue
            if subcap_idx is not None:
                subcaps = RE_SUBCAP_ID.findall(_cell_at(cells, subcap_idx))
            else:
                subcaps = RE_SUBCAP_ID.findall(" ".join(cells))
            title = statement
            if not title or _FA_ROW_ID_RE.match(title):
                title = quote
            out.append(FocusArea(
                title=title[:120].strip(),
                verbatim_quote=quote[:800],
                source_path=(f"docx:client_profile#findings/{row_id}"
                             if row_id else "docx:client_profile#findings"),
                page_number=None,
                involved_subcap_ids=list(dict.fromkeys(subcaps)),
            ))
        if out:
            return out
    return []


def _extract_leadership(sections: dict[str, list[str]]) -> list[LeadershipEntry]:
    """Walk the Leadership section and emit Name/Role pairs."""
    out: list[LeadershipEntry] = []
    for head, body in sections.items():
        if not RE_LEADERSHIP.search(head):
            continue
        for para in body:
            # Try "Name — Role" / "Name, Role"
            m = RE_NAME_ROLE.match(para)
            if m:
                out.append(LeadershipEntry(
                    name=m.group(1).strip(),
                    role=m.group(2).strip()[:160],
                    raw_text=para,
                ))
                continue
            # Fall back: any paragraph beginning with a capitalised name —
            # we keep raw_text so a downstream consumer can disambiguate.
            tokens = para.split()
            if (
                len(tokens) >= 2
                and tokens[0][:1].isupper()
                and tokens[1][:1].isupper()
                and len(para) < 280
            ):
                out.append(LeadershipEntry(
                    name=" ".join(tokens[:2]),
                    role=None,
                    raw_text=para,
                ))
    # De-dup by name (case-insensitive) preserving order.
    seen: set[str] = set()
    deduped: list[LeadershipEntry] = []
    for e in out:
        key = e.name.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


def _extract_financials(sections: dict[str, list[str]]) -> dict[str, Any]:
    """Grab everything from Financial Highlights / Scale Metrics into a
    structured-ish dict. The free-form lines are kept under 'lines'
    plus any obvious key=value pairs detected."""
    aggregated: list[str] = []
    for head, body in sections.items():
        if RE_FINANCIALS.search(head):
            aggregated.extend(body)
    if not aggregated:
        return {}
    parsed: dict[str, Any] = {"lines": aggregated[:24]}
    # Look for "AUM: $1.5B" / "Assets — $1.5B" patterns.
    for line in aggregated:
        for m in re.finditer(
            r"([A-Z][A-Za-z0-9 \-/]+?)\s*[:\-–—]\s*\$?([\d.]+[BMK]?\b[^\n]{0,40})",  # noqa: RUF001
            line,
        ):
            k = m.group(1).strip().lower().replace(" ", "_")
            if k and k not in parsed:
                parsed[k] = m.group(2).strip()
    return parsed


def _extract_firmographics_narrative(sections: dict[str, list[str]]) -> str:
    """Concatenate the Corporate Identity / Entity Profile section."""
    chunks: list[str] = []
    for head, body in sections.items():
        if RE_CORP_IDENTITY.search(head):
            chunks.extend(body)
    return "\n\n".join(chunks)[:8000]


# Structured firmographics extraction (2026-06-06 Batch 4.2).
# The Overview FirmographicsRows React component reads `firm.total_assets`,
# `firm.employees_approx`, `firm.primary_regulator`, `firm.branches`, and
# `firm.hq`. Until this batch, the parser only emitted the freeform
# narrative; the React rows rendered "—" for every field, defeating the
# Batch 2 layout port. These regexes pull the canonical patterns out of
# the Client Profile DOCX (verified end-to-end against the Alma_Bank
# fixture in test_client_profile_firmographics_extraction.py).

# `$1.5B in assets`, `$1.492B assets`, `$25.4M total assets`. The two
# directional variants cover both word orders the DOCX templates use:
#   1. amount-first ("$1.5B in assets")
#   2. label-first  ("Total assets: $25.4M")
# The first match wins; both regexes scan the same narrative blob.
_RE_TOTAL_ASSETS_AMOUNT_FIRST = re.compile(
    r"\$\s*([\d.]+)\s*([BM])\b\s*(?:in\s+)?(?:total\s+)?assets",
    re.IGNORECASE,
)
_RE_TOTAL_ASSETS_LABEL_FIRST = re.compile(
    r"(?:total\s+)?assets[:\s]+\$\s*([\d.]+)\s*([BM])\b",
    re.IGNORECASE,
)

# `1,200 employees`, `approx. 350 staff`, `~85 FTEs`
_RE_EMPLOYEES = re.compile(
    r"(?:approximately|approx\.?|~)?\s*([\d,]+)\s+(?:employees|staff|FTEs?)",
    re.IGNORECASE,
)

# `14 branches`, `1 branch`, `200+ branches`, `1,253 branches`. NOTE
# `branches?` would only match "branche"/"branches" -- we use
# `branch(?:es)?` so the singular "branch" matches too. The digit group
# admits thousands separators so a large network ("1,253 branches") is
# not silently truncated to its last group ("253"); commas are stripped
# by the caller before the value is stored.
_RE_BRANCHES = re.compile(r"(\d[\d,]{0,7})\+?\s+branch(?:es)?\b", re.IGNORECASE)

# `headquartered in <city>`, `HQ in <city>`, `based in <city>`. Bounded
# so we don't run past sentence end. IGNORECASE is essential -- "Based"
# at sentence start would NEVER match without it.
_RE_HQ = re.compile(
    r"(?:headquartered|HQ|based)\s+in\s+([A-Z][A-Za-z .\-]+(?:,\s*[A-Z]{2,3})?)",
    re.IGNORECASE,
)

# Primary regulator: list of major US/CA/UK financial regulators. Match
# the FIRST one that appears in the narrative; subsequent ones are
# usually mentioned in a different context (an examiner naming, a
# benchmark, etc.).
_RE_REGULATOR = re.compile(
    r"\b(FDIC|OCC|Federal\s+Reserve|FRB|NCUA|SEC|FINRA|CFPB|OSFI|FCA)\b",
)


def _extract_firmographics_facts(
    narrative: str, *, strict: bool = False,
) -> dict[str, str]:
    """Mine the firmographics narrative for the structured fields the
    Overview React page renders. Returns a dict with keys subset of
    {total_assets, employees_approx, branches, hq, primary_regulator};
    absent fields are omitted (Pydantic's `extra='allow'` schema
    tolerates the partial dict).

    All values are STRINGS (the schema models employees_approx as
    `str | None` to support ranges like "200-250"). Numeric callers
    in the React tree do their own `Number(...)`."""
    facts: dict[str, str] = {}
    if not narrative:
        return facts

    # Try amount-first ("$1.5B in assets") then fall back to label-first
    # ("Total assets: $25.4M") so the two common DOCX templates are both
    # covered. The amount-first variant is preferred because it tends to
    # appear more often in the canonical Client Profile preamble.
    def _unambiguous(values: list[str]) -> str | None:
        """strict mode: accept a mined numeric ONLY when every match in
        the text agrees. A Client Profile narrative can cite an ACQUIRED
        bank's "$2.2B assets" alongside the entity's own "$35B assets"
        (FNBO, 2026-06-10) — when amounts disagree, the field stays
        empty and the Gemini firmographics enrichment (grounded) fills
        it on the live deployment instead of a wrong number."""
        uniq = sorted(set(values))
        if not uniq:
            return None
        if strict and len(uniq) > 1:
            return None
        return values[0]

    asset_vals = [
        f"${m.group(1)}{m.group(2)}"
        for m in _RE_TOTAL_ASSETS_AMOUNT_FIRST.finditer(narrative)
    ] + [
        f"${m.group(1)}{m.group(2)}"
        for m in _RE_TOTAL_ASSETS_LABEL_FIRST.finditer(narrative)
    ]
    v = _unambiguous(asset_vals)
    if v:
        facts["total_assets"] = v

    emp_vals = [
        m.group(1).replace(",", "")
        for m in _RE_EMPLOYEES.finditer(narrative)
        if m.group(1).replace(",", "").isdigit()
        and int(m.group(1).replace(",", "")) > 0
    ]
    v = _unambiguous(emp_vals)
    if v:
        facts["employees_approx"] = v

    branch_vals = [
        m.group(1).replace(",", "") for m in _RE_BRANCHES.finditer(narrative)
        if m.group(1).replace(",", "").isdigit()
    ]
    v = _unambiguous(branch_vals)
    if v:
        facts["branches"] = v

    m = _RE_HQ.search(narrative)
    if m:
        facts["hq"] = m.group(1).strip()

    m = _RE_REGULATOR.search(narrative)
    if m:
        # Normalise "Federal Reserve" / "FRB" → "Federal Reserve" for
        # consistent UI display.
        raw = m.group(1)
        facts["primary_regulator"] = "Federal Reserve" if raw == "FRB" else raw

    return facts


# ── Heading-anchored table extraction (sentiment + acquisitions) ──
#
# Some report tables (sentiment, acquisition history) have no distinctive
# header row, so we cannot identify them by `_iter_tables` header matching.
# Instead we walk the document body in order and grab the first table that
# appears UNDER a matching HEADING (style "Heading *") and BEFORE the next
# heading. Each candidate is then SHAPE-VALIDATED, so a wrong table under a
# drifted heading yields nothing rather than mismapped data.

RE_SENTIMENT_HEADING = re.compile(
    r"sentiment\s+(overview|analysis|summary|snapshot)|"
    r"public\s+sentiment|employee\s+sentiment|brand\s+sentiment",
    re.I,
)
RE_ACQUISITION_HEADING = re.compile(
    r"acquisition\s+history|m&a\s+(history|activity|timeline)|"
    r"acquisitions?\s*&|mergers?\s+(?:and|&)\s+acquisitions?",
    re.I,
)
# A value cell that looks like a sentiment rating (3.6/5.0, 72%, "positive",
# star glyphs) — guards against grabbing entity key/value tables.
_RATING_CELL = re.compile(
    r"\d(?:\.\d+)?\s*/\s*5|\d+(?:\.\d+)?\s*%|"
    r"\b(positive|negative|mixed|neutral|favou?rable|unfavou?rable|strong|weak)\b|"
    r"[★☆]",
    re.I,
)


def _is_heading(paragraph: Any) -> bool:
    sty = (paragraph.style.name if getattr(paragraph, "style", None) else "") or ""
    return sty.lower().startswith("heading")


def _iter_doc_blocks(doc: Any) -> list[tuple[str, Any]]:
    """Body blocks in document order: ('p', Paragraph) | ('tbl', Table)."""
    try:
        from docx.table import Table  # type: ignore[import-untyped]
        from docx.text.paragraph import Paragraph  # type: ignore[import-untyped]
    except ImportError:
        return []
    body = getattr(getattr(doc, "element", None), "body", None)
    if body is None:
        return []
    out: list[tuple[str, Any]] = []
    for child in body.iterchildren():
        tag = child.tag
        if tag.endswith("}p"):
            out.append(("p", Paragraph(child, doc)))
        elif tag.endswith("}tbl"):
            out.append(("tbl", Table(child, doc)))
    return out


def _table_rows_under_heading(
    blocks: list[tuple[str, Any]], rx: re.Pattern[str],
) -> list[list[str]] | None:
    """First table's rows appearing under a HEADING matching ``rx``."""
    armed = False
    for kind, obj in blocks:
        if kind == "p":
            if _is_heading(obj):
                armed = bool(rx.search((obj.text or "").strip()))
        elif armed:
            rows = [[(c.text or "").strip() for c in r.cells] for r in obj.rows]
            if rows:
                return rows
    return None


def _extract_sentiment(blocks: list[tuple[str, Any]]) -> dict[str, Any]:
    """Mine the "Sentiment Overview" 2-col metric|value table.

    → {sources:[{source, rating}]}. Returns {} unless the table is genuinely
    rating-shaped (≥2 rating-like value cells) — never fabricated.
    """
    rows = _table_rows_under_heading(blocks, RE_SENTIMENT_HEADING)
    if not rows or len(rows[0]) != 2:
        return {}
    rating_rows = sum(1 for r in rows if len(r) > 1 and _RATING_CELL.search(r[1]))
    if rating_rows < 2:
        return {}
    sources: list[dict[str, Any]] = []
    for r in rows:
        label = (r[0] or "").strip()
        value = (r[1] or "").strip() if len(r) > 1 else ""
        if not label or not value:
            continue
        # Skip a "Metric | Value" header row if present.
        if label.lower() in {"metric", "dimension", "field", "source"} and not _RATING_CELL.search(value):
            continue
        sources.append({"source": label[:120], "rating": value[:200]})
        if len(sources) >= 30:
            break
    return {"sources": sources} if sources else {}


def _norm_target_name(name: str) -> str:
    """Normalize an acquired-party name for dedup keying: lowercase, collapse
    every run of non-alphanumerics to a single space, trim. Two rows for the
    same deal ("EnerBank USA" / "EnerBank  USA.") collapse to one key while
    distinct targets stay distinct. Capped so a compressed multi-fact cell
    can't dodge the key."""
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()[:60]


def _extract_acquisitions(blocks: list[tuple[str, Any]]) -> list[Any]:
    """Mine the "Acquisition History" table → TimelineEventCandidate[].

    Requires a header with a date/period column AND a target/event column
    (so strategic-M&A narrative tables without dates are rejected), and a
    parseable date per row. Part 8.2/8.3: negated-absence and hypothetical
    ("actively seeking…") rows are suppressed — the table must record deals
    that happened, not strategy intent; each row carries ``signal``,
    ``date_precision`` (from the date cell's grain) and any cited E-IDs.
    Verbatim title/body; never fabricated.
    """
    from app.schemas.package import TimelineEventCandidate
    from app.services.nlp import polarity as nlp_polarity
    from app.services.parsers.facts_extractor import parse_event_date

    rows = _table_rows_under_heading(blocks, RE_ACQUISITION_HEADING)
    if not rows or len(rows) < 2:
        return []
    head = [h.lower().strip() for h in rows[0]]

    def _col(*keys: str) -> int | None:
        for i, h in enumerate(head):
            if any(k in h for k in keys):
                return i
        return None

    i_date = _col("date", "period", "year", "when")
    # Acquired-party column. Regions §4.4 labels it "Entity" (WSFS uses
    # "Target / Event"), so the synonym list covers the entity/name/firm
    # family too — otherwise an "Entity"-headed table is dropped whole and
    # real deals surface as `acquisitions: 0`.
    i_target = _col(
        "target", "event", "acqui", "transaction", "deal", "company",
        "entity", "name", "firm", "institution", "business", "subsidiary",
    )
    if i_date is None or i_target is None:
        return []
    i_rationale = _col("rationale", "strategic", "reason", "purpose")
    i_impl = _col("implication", "impact", "digital", "relevance", "note")

    hypothetical = re.compile(
        r"\b(?:actively\s+seeking|seeking\s+to|exploring|considering|"
        r"plans?\s+to|intends?\s+to|would|could|potential|pipeline)\b",
        re.IGNORECASE,
    )

    out: list[Any] = []
    seen: set[tuple[str, int]] = set()
    for row in rows[1:]:
        if not row or all(not (c or "").strip() for c in row):
            continue
        date_raw = row[i_date] if i_date < len(row) else ""
        normalized = _normalize_timeline_date(date_raw)
        dt = parse_event_date(normalized)
        if dt is None:
            continue
        title = (row[i_target] or "").strip() if i_target < len(row) else ""
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue
        body_parts = []
        for ci in (i_rationale, i_impl):
            if ci is not None and ci < len(row) and (row[ci] or "").strip():
                body_parts.append(re.sub(r"\s+", " ", row[ci]).strip())
        body = " — ".join(body_parts)[:1000] or None
        combined = f"{title}. {body}" if body else title
        if nlp_polarity.is_negated_absence(combined) or hypothetical.search(title):
            continue  # absence notes / strategy intent are not acquisitions
        # Dedup on (normalized target name, year) — NOT exact datetime. The
        # same deal often recurs with differing date grains ("2021" vs
        # "Jan 2021"); keying on the datetime lets the coarser/finer grain
        # slip through as a duplicate row (the Wintrust symptom). Year +
        # normalized name collapses those to one deal.
        key = (_norm_target_name(title), dt.year)
        if key in seen:
            continue
        seen.add(key)
        evidence_e_ids = _cell_evidence_ids(combined)
        # Long multi-fact target cells compress to a display title; the
        # verbatim cell is preserved in body (titles-clean contract).
        from app.services.parsers.facts_extractor import event_title
        display_title = title if len(title) <= 90 else event_title(title)
        body_verbatim = combined if display_title != title else body
        out.append(
            TimelineEventCandidate(
                event_date=dt,
                kind="acquisition",
                title=display_title[:300],
                body=(body_verbatim[:1000] if body_verbatim else None),
                e_id=evidence_e_ids[0] if evidence_e_ids else None,
                signal=nlp_polarity.signal_for_kind(combined, "acquisition"),
                date_precision=_date_cell_precision(normalized),
                evidence_e_ids=evidence_e_ids[:6],
            )
        )
    return out


# ── Risk & Issues mining (2026-07-06 Context issue-register fix) ─────
# 69/80 corpus Client Profile Research Reports carry a "5. Risk &
# Issues / 5.1 Issue Register" section. Wescom's TABLE 9 is the
# canonical shape (ID/Type/Severity/Status/Description/Cap Impact/Cap
# Value); TABLE 15 maps triggers to SUBCAP-level caps ("Barracuda
# breach" → P4C4.7, P4C4.8, P3C4.5 @ 3.0). Bank of Utah's report has
# no table — its "H) Risk & Compliance Profile" prose states the same
# issues in sentences ("Active FDIC consent order … capping P3C3
# Compliance at 2.5"). Both faces are mined here.

RE_RISK_ISSUES_HEAD = re.compile(r"\brisks?\b|\bissues?\b", re.I)
RE_ISSUE_CUE = re.compile(
    r"consent\s+order|enforcement|cease[\s-]and[\s-]desist|breach|"
    r"penalt|\bfine[sd]?\b|lawsuit|class\s+action|violation|deficien|"
    r"attrition|outage|downgrade|complaint|\bconstrain|"
    r"\bcap(?:s|ped|ping)\b|no\s+(?:soc\s*-?\s*2|iso\s*-?\s*27001|"
    r"named|formal|public|identified)\b",
    re.I,
)
RE_REGULATOR_TOKEN = re.compile(
    r"\b(FDIC|OCC|NCUA|FINRA|SEC|CFPB|FTC|DFS|OSFI|FCA|FRB|"
    r"Federal\s+Reserve)\b",
)
RE_ISSUE_STATUS_TOKEN = re.compile(
    r"\b(active|open|ongoing|resolved|settled|terminated|closed|"
    r"monitoring)\b",
    re.I,
)


def _extract_issue_register_tables(
    tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Issue rows from register-shaped tables (header fingerprint: a
    description/issue column + a cap/capability column + a status or
    severity column). Gap-priority tables without status/severity and
    findings tables without a cap column are rejected — this mines the
    ISSUE register only."""
    out: list[dict[str, Any]] = []
    for tbl in tables:
        head = [h.lower().strip() for h in tbl["header"]]
        if not head or len(tbl["rows"]) < 1:
            continue
        has_desc = any("description" in h or h == "issue" for h in head)
        has_cap = any("cap" in h or "capabilit" in h for h in head)
        has_sev = any("severity" in h for h in head)
        has_status = any("status" in h for h in head)
        if not (has_desc and has_cap and (has_sev or has_status)):
            continue

        def _col(*keys: str, _head: list[str] = head) -> int | None:
            for i, h in enumerate(_head):
                if any(k in h for k in keys):
                    return i
            return None

        i_id = _col("id")
        i_type = _col("type")
        i_sev = _col("severity")
        i_status = _col("status")
        i_desc = _col("description", "issue")
        i_cap_imp = _col("cap impact", "capabilit", "cap_impact", "subcap")
        i_cap_val = _col("cap value", "cap_value", "max", "ceiling")
        i_evidence = _col("evidence")
        i_regulator = _col("regulator")
        i_date = _col("date")

        def _cell(row: list[str], i: int | None) -> str:
            return (row[i] or "").strip() if i is not None and i < len(row) else ""

        for n, row in enumerate(tbl["rows"], start=1):
            desc = re.sub(r"\s+", " ", _cell(row, i_desc)).strip()
            if not desc or RE_PIPELINE_META.search(desc):
                continue
            out.append({
                "issue_id": _cell(row, i_id) or f"RPT-{n:03d}",
                "type": _cell(row, i_type) or None,
                "severity": _cell(row, i_sev) or None,
                "status": _cell(row, i_status) or None,
                "description": desc,
                "capability_impact": _cell(row, i_cap_imp) or None,
                "cap_value": _cell(row, i_cap_val) or None,
                "evidence": _cell(row, i_evidence) or None,
                "regulator": _cell(row, i_regulator) or None,
                "date": _cell(row, i_date) or None,
                "source": "docx:issue_table",
            })
    return out


def _extract_issue_cap_triggers(
    tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The "Trigger → Capabilities Affected → Maximum Score" table:
    subcap-level cap attribution ({trigger, subcap_ids, max_score})."""
    from app.services.parsers.package_csvs import mine_p_codes

    out: list[dict[str, Any]] = []
    for tbl in tables:
        head = [h.lower().strip() for h in tbl["header"]]
        if not head:
            continue
        if not (any("trigger" in h for h in head)
                and any("capabilit" in h or "subcap" in h for h in head)
                and any("score" in h or "max" in h or h == "cap" for h in head)):
            continue
        i_trigger = next(i for i, h in enumerate(head) if "trigger" in h)
        i_caps = next(i for i, h in enumerate(head)
                      if "capabilit" in h or "subcap" in h)
        i_score = next((i for i, h in enumerate(head)
                        if "score" in h or "max" in h), None)
        for row in tbl["rows"]:
            trigger = (row[i_trigger] or "").strip() if i_trigger < len(row) else ""
            caps_cell = (row[i_caps] or "") if i_caps < len(row) else ""
            subcap_ids = mine_p_codes(caps_cell)
            if not trigger or not subcap_ids:
                continue
            max_score: float | None = None
            if i_score is not None and i_score < len(row):
                m = re.search(r"\d(?:\.\d+)?", row[i_score] or "")
                if m:
                    v = float(m.group(0))
                    max_score = v if 1.0 <= v <= 5.0 else None
            out.append({
                "trigger": re.sub(r"\s+", " ", trigger),
                "subcap_ids": subcap_ids,
                "max_score": max_score,
            })
    return out


def _extract_issue_prose(
    sections: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Sentence-level issue statements from Risk/Issues section prose —
    the fallback when the report ships no register table. Each kept
    sentence carries a concrete issue cue (consent order / breach /
    penalty / missing-certification / cap language); regulator, status,
    date and subcap-level caps are captured where the text states them.
    Never fabricated: every emitted description is a verbatim sentence.
    """
    from app.services.nlp import polarity as nlp_polarity
    from app.services.nlp.segment import sentences as nlp_sentences
    from app.services.parsers.package_csvs import (
        mine_cap_levels,
        mine_p_codes,
    )

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for heading, paras in sections.items():
        if not RE_RISK_ISSUES_HEAD.search(heading):
            continue
        for para in paras:
            cleaned = _clean_quote(para)
            if not cleaned:
                continue
            for sent in nlp_sentences(cleaned):
                evidence_ids = RE_EVIDENCE_ID.findall(sent)
                # Leading citation debris ("[E-094]; ") + label prefixes
                # ("PRIMARY RISK: ") stripped so the statement stands alone.
                s = re.sub(r"^\s*(?:\[E-?\d{2,4}\][;,]?\s*)+", "", sent).strip()
                s = re.sub(r"^(?:PRIMARY|SECONDARY|TERTIARY)\s+RISK:\s*",
                           "", s, flags=re.I).strip()
                if not 30 <= len(s) <= 420 or not RE_ISSUE_CUE.search(s):
                    continue
                # Positive/clean-standing statements ("Zero data breaches
                # 2023-2026", "Verafin provides fraud detection with zero
                # breach outcomes") are NOT issues.
                if nlp_polarity.is_negated_absence(s) \
                        or re.search(r"\bzero\b", s, re.I):
                    continue
                key = re.sub(r"\s+", " ", s.lower())[:160]
                if key in seen:
                    continue
                seen.add(key)
                reg_m = RE_REGULATOR_TOKEN.search(s)
                status_m = RE_ISSUE_STATUS_TOKEN.search(s)
                date_m = re.search(
                    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
                    r"[a-z]*\.?\s+(?:19|20)\d{2}\b|\b(?:19|20)\d{2}\b",
                    s, re.I,
                )
                caps = mine_cap_levels(s)
                out.append({
                    "issue_id": f"RPT-{len(out) + 1:03d}",
                    "type": None,
                    "severity": None,
                    "status": status_m.group(1).upper() if status_m else None,
                    "description": s,
                    "capability_impact": ",".join(mine_p_codes(s)) or None,
                    "cap_value": None,
                    "evidence": ",".join(evidence_ids) or None,
                    "regulator": reg_m.group(1) if reg_m else None,
                    "date": date_m.group(0) if date_m else None,
                    "caps": caps or None,
                    "source": "docx:risk_prose",
                })
                if len(out) >= 8:
                    return out
    return out


# A "substantive" Digital-Evolution / Technology-Landscape paragraph must
# carry at least one hard fact hook: an E-ID, a subcap ref, a year, a
# number, or a named platform/vendor. Everything else is section filler.
RE_SUBSTANTIVE_HOOK = re.compile(
    r"\bE-?\d{2,4}\b|\bP[1-4]C\d|\b(?:19|20)\d{2}\b|\d+(?:\.\d+)?\s*%|\$\s*\d|"
    r"\b\d{2,}\b|salesforce|fiserv|jack\s+henry|fis\b|temenos|finastra|q2\b|"
    r"alkami|ncino|mulesoft|tableau|databricks|snowflake|twilio|marketo|"
    r"hubspot|servicenow|workday|okta|aws\b|azure|google\s+cloud|core\s+banking",
    re.I,
)


def mine_profile_findings(
    sections: dict[str, list[str]],
    tables: list[dict[str, Any]],
) -> list[Any]:
    """D2 Part 5.1 PRIMARY rung: mine the report's "Key Findings /
    Strategic Priorities / Digital Evolution / Technology Landscape"
    sections into normalized :class:`section_analysis.ProfileFinding`
    rows.

    Sources, in order:
      1. Findings TABLES (the canonical 5-col ``F-ID | Title |
         Observation [E-###] | Maturity implication | Zennify relevance``
         shape) — richest, fully cited.
      2. Key Findings / Top Findings / Critical Gaps paragraph sections.
      3. Strategic Priorities sections (``source_kind='strategic_priority'``).
      4. Digital Evolution / Technology Landscape narrative paragraphs —
         kept only when substantive (an E-ID, subcap ref, year, number,
         or named platform), so section filler never becomes a card.

    Pure; dedups on normalized observation; capped at 24 per report.
    """
    from app.services.parsers.section_analysis import profile_finding_from_quote

    out: list[Any] = []
    seen: set[str] = set()

    def _push(finding: Any) -> None:
        if finding is None:
            return
        key = re.sub(r"\s+", " ", finding.observation.lower())[:160]
        if key in seen:
            return
        seen.add(key)
        out.append(finding)

    # 1. Findings tables → structured rows (same walk the focus-area
    # fallback uses, but keeping every column separate).
    for tbl in tables:
        head = [h.lower() for h in tbl.get("header", [])]
        if not any("finding" in h or "observation" in h or "gap" in h
                   for h in head):
            continue
        for r in tbl.get("rows", []):
            if not r or not any(c for c in r):
                continue
            quote = " | ".join(c for c in r if c)
            if len(quote) < 24:
                continue
            page_m = RE_PAGE_NUM.search(quote)
            _push(profile_finding_from_quote(
                r[0][:120] if r and r[0] else None, quote,
                page=int(page_m.group(1)) if page_m else None,
                source_kind="key_findings",
            ))

    # 2-4. Heading-classified paragraph sections.
    for head, body in sections.items():
        if RE_TOP_FINDINGS.search(head) or RE_CRITICAL_GAPS.search(head):
            kind = "key_findings"
        elif RE_STRATEGIC_OBJECTIVES.search(head):
            kind = "strategic_priority"
        elif RE_DIGITAL_EVOLUTION.search(head):
            kind = "digital_evolution"
        elif RE_TECH_LANDSCAPE.search(head):
            kind = "tech_landscape"
        else:
            continue
        for para in body:
            cleaned = _clean_quote(para)
            if cleaned is None or len(cleaned) < 32:
                continue
            if kind in ("digital_evolution", "tech_landscape") and (
                len(cleaned) < 60 or not RE_SUBSTANTIVE_HOOK.search(cleaned)
            ):
                continue
            page_m = RE_PAGE_NUM.search(para)
            title = head.split(".", 1)[-1].strip()[:120] or None
            _push(profile_finding_from_quote(
                title, cleaned,
                page=int(page_m.group(1)) if page_m else None,
                source_kind=kind,
            ))
        if len(out) >= 24:
            break
    return out[:24]


def parse_client_profile_doc(doc: Any) -> ClientProfileParseResult:
    """Pure-Python entrypoint for an already-loaded ``python-docx`` Document."""
    paragraphs = _iter_paragraphs(doc)
    sections = _section_bodies(paragraphs)
    tables = _iter_tables(doc)

    leadership = _extract_leadership(sections)
    # Fallback: many DMA Client Profile templates render leadership as
    # a table rather than free-form paragraphs (Alma's "4.3 Leadership
    # Overview" is a 5-col table).
    if not leadership:
        leadership = _extract_leadership_from_tables(tables)
    # Focus areas are the entity's STATED STRATEGIC PRIORITIES first
    # (operator mandate 2026-07: the heatmap must show the client's
    # priorities, not Zennify's derived maturity findings). When the
    # research report ships a strategic-objectives section it is
    # authoritative and used as-is (`source_path='docx:strategic_section'`).
    # Focus areas are the CLIENT'S OWN strategic objectives — the profile
    # report's strategic/priorities sections only. Findings tables are
    # NOT objectives (2026-07-12 vetting: FCMA rendered 'FCMA is nCino
    # customer' and finding F-007 as focus areas); a report with no
    # strategic section yields NO focus areas here, and the research
    # tier fills the gap (deepen files a G2 'most recent strategic
    # objectives' clarification; the crawler answers it; every focus
    # area is re-validated on a 6-month cadence regardless of source).
    focus_areas = _extract_strategic_objectives(sections)
    if not focus_areas:
        focus_areas = _extract_focus_areas(sections)
    financials = _extract_financials(sections)
    firmographics = _extract_firmographics_narrative(sections)
    timeline_events = _extract_digital_timeline(tables)
    doc_blocks = _iter_doc_blocks(doc)
    sentiment = _extract_sentiment(doc_blocks)
    acquisition_events = _extract_acquisitions(doc_blocks)
    # D2 Part 5.1: normalized profile findings for the insight ladder's
    # PRIMARY rung. Best-effort — a mining failure never fails the parse.
    try:
        profile_findings = mine_profile_findings(sections, tables)
    except Exception:
        log.warning("client_profile.profile_findings_mining_failed",
                    exc_info=True)
        profile_findings = []
    # 2026-07-06: Risk & Issues mining — register table first, prose
    # sentences only when no table shipped. Best-effort like the rest.
    try:
        issue_rows = _extract_issue_register_tables(tables)
        if not issue_rows:
            issue_rows = _extract_issue_prose(sections)
        issue_cap_triggers = _extract_issue_cap_triggers(tables)
    except Exception:
        log.warning("client_profile.issue_mining_failed", exc_info=True)
        issue_rows, issue_cap_triggers = [], []

    filled = sum(bool(x) for x in [focus_areas, leadership, financials, firmographics])
    if filled == 0:
        state: CoverageState = "no_docx_found"
    elif filled < 4:
        state = "partial_coverage"
    else:
        state = "full_coverage"

    result = ClientProfileParseResult(
        focus_areas=focus_areas,
        leadership=leadership,
        financial_highlights=financials,
        firmographics_narrative_md=firmographics,
        state_kind=state,
        timeline_events=timeline_events,
        sentiment=sentiment,
        acquisition_events=acquisition_events,
        profile_findings=profile_findings,
        issue_rows=issue_rows,
        issue_cap_triggers=issue_cap_triggers,
    )
    if not focus_areas:
        result.warnings.append({"kind": "no_focus_areas_found"})
    if not leadership:
        result.warnings.append({"kind": "no_leadership_found"})
    return result


def parse_client_profile_path(path: Path | str) -> ClientProfileParseResult:
    """Convenience entrypoint that imports ``python-docx`` lazily.

    Returns ``no_docx_found`` when the path doesn't exist (so the
    orchestrator can call this unconditionally).
    """
    p = Path(path)
    if not p.exists():
        return ClientProfileParseResult(state_kind="no_docx_found")
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError as exc:
        log.warning("python-docx unavailable: %s", exc)
        return ClientProfileParseResult(state_kind="no_docx_found")
    return parse_client_profile_doc(Document(str(p)))
