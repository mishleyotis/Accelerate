"""Assessment-report DOCX section parser.

Walks a `04_reports/Assessment_Report*.docx` file, extracts paragraphs +
heading styles, and classifies each section into one of the 12 canonical
section kinds from PRD §02. The result feeds two tables on the way to
the wireframe-narrative surfaces:

  - `document_sections` (run_id, section_kind, ordinal, heading, body, …)
  - `document_lineage`  (section_id, target_type, target_ref)
  - `document_evidence_items` (E-IDs mentioned per section)

State-branch contract (single canonical matrix referenced by tests):

  - full_coverage      → all 12 canonical kinds are present (or all the
                         ones a given DMA template emits — typically 10+).
                         Coverage ratio ≥ 0.80 of EXPECTED_KINDS.
  - partial_coverage   → 0 < coverage < 0.80 — parser emits warnings on
                         missing kinds but still persists what it found.
  - llm_fallback_used  → headings are ambiguous; classify_heading drops
                         a section into the `other` bucket and a warning
                         like `unknown_heading` is emitted. (The actual
                         Gemini-Pro structured-output fallback is a
                         design point — in this batch we ship a strict
                         heuristic plus a hook function the LLM call
                         will replace.)
  - no_docx_found      → no `04_reports/*.docx` in the package. Parser
                         returns an empty `ReportParseResult`, all
                         downstream narrative fields are `null`, surfaces
                         keep their skeleton.

The classifier supports header drift across the WSFS / AlmaBank / Regions
DMA templates (e.g. "Strategic Posture & Governance" → P1 deep-dive,
"Engagement Pillar" → P2 deep-dive, "Operations Pillar" → P3 deep-dive).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)


SectionKind = Literal[
    "executive_summary_scqa",
    "trend_analysis",
    "issue_register",
    "pillar_deep_dive_p1",
    "pillar_deep_dive_p2",
    "pillar_deep_dive_p3",
    "pillar_deep_dive_p4",
    "benchmark_comparison",
    "gap_prioritization",
    "recommendations",
    "roadmap",
    "data_gaps",
    "evidence_registry",
    "unknown",
    "other",
]

# The 12 canonical sections per PRD §02 (used for coverage assertions).
EXPECTED_KINDS: tuple[SectionKind, ...] = (
    "executive_summary_scqa",
    "trend_analysis",
    "issue_register",
    "pillar_deep_dive_p1",
    "pillar_deep_dive_p2",
    "pillar_deep_dive_p3",
    "pillar_deep_dive_p4",
    "benchmark_comparison",
    "gap_prioritization",
    "recommendations",
    "roadmap",
    "data_gaps",
)


# Heading regex → SectionKind. First match wins. Case-insensitive.
#
# We deliberately keep these patterns liberal — DMA templates drift
# across vendors and analysts. "Strategic Posture & Governance" maps to
# P1 (Strategy Pillar) because that's the canonical AlmaBank substitute;
# "Engagement Pillar" maps to P2 because that's how Regions phrases it.
HEADING_PATTERNS: list[tuple[re.Pattern[str], SectionKind]] = [
    # Specific (high-priority) patterns first
    (re.compile(r"^\s*(?:\d+[\.\)]\s*)?(?:executive\s+summary|scqa)\b", re.I), "executive_summary_scqa"),
    (re.compile(r"^\s*(?:trend\s+analysis|trends?(?:\s+&\s+forces)?)\b", re.I), "trend_analysis"),
    (re.compile(r"^\s*issue\s+register\b", re.I), "issue_register"),

    # Pillar deep-dives — match P[1234] explicitly OR the canonical
    # pillar names. Order matters here: a "pillar 1" heading hits the
    # explicit pattern; "strategic posture" only hits via name match.
    (re.compile(r"^\s*pillar\s+1\b|^\s*p1\b|^\s*strategy[, ]+governance|^\s*strategic\s+(posture|governance|positioning)\b", re.I), "pillar_deep_dive_p1"),
    (re.compile(r"^\s*pillar\s+2\b|^\s*p2\b|^\s*customer\s+experience|^\s*engagement\s+pillar|^\s*(?:cx|customer)\s+&\s+engagement", re.I), "pillar_deep_dive_p2"),
    (re.compile(r"^\s*pillar\s+3\b|^\s*p3\b|^\s*process\s+automation|^\s*operations\s+pillar|^\s*operations\s+&\s+automation", re.I), "pillar_deep_dive_p3"),
    (re.compile(r"^\s*pillar\s+4\b|^\s*p4\b|^\s*data\s+&\s+ai\b|^\s*data\s+and\s+ai\b|^\s*ai\s+enablement", re.I), "pillar_deep_dive_p4"),

    (re.compile(r"^\s*benchmark\s+comparison\b|^\s*peer\s+(comparison|benchmark)", re.I), "benchmark_comparison"),
    (re.compile(r"^\s*gap\s+prioriti[sz]ation\b|^\s*prioriti[sz]ed\s+gaps?", re.I), "gap_prioritization"),
    (re.compile(r"^\s*recommendation", re.I), "recommendations"),
    (re.compile(r"^\s*roadmap\b|^\s*transformation\s+roadmap", re.I), "roadmap"),
    (re.compile(r"^\s*data\s+gaps?\b|^\s*thin\s+evidence", re.I), "data_gaps"),
    (re.compile(r"^\s*evidence\s+registry\b|^\s*evidence\s+(index|appendix)", re.I), "evidence_registry"),
]

# Pillar deep-dive → pillar_id mapping for lineage rows.
PILLAR_FOR_KIND: dict[SectionKind, str] = {
    "pillar_deep_dive_p1": "P1",
    "pillar_deep_dive_p2": "P2",
    "pillar_deep_dive_p3": "P3",
    "pillar_deep_dive_p4": "P4",
}

# Match P{n}C{c}.{cluster}.{ord} subcap IDs and E-{NNNN} evidence IDs.
_SUBCAP_RX = re.compile(r"\bP[1-4]C\d+\.\d+\.\d+\b")
_E_ID_RX = re.compile(r"\bE-\d{1,6}\b")


@dataclass
class ReportSection:
    kind: SectionKind
    heading: str
    body: str
    ordinal: int
    page_number: int | None = None
    subcap_ids_mentioned: list[str] = field(default_factory=list)
    e_ids_mentioned: list[str] = field(default_factory=list)


@dataclass
class ReportParseResult:
    sections: list[ReportSection] = field(default_factory=list)
    warnings: list[dict[str, object]] = field(default_factory=list)
    source_path: str | None = None

    @property
    def coverage_ratio(self) -> float:
        """Fraction of EXPECTED_KINDS present in this parse."""
        kinds = {s.kind for s in self.sections}
        hits = sum(1 for k in EXPECTED_KINDS if k in kinds)
        return hits / len(EXPECTED_KINDS) if EXPECTED_KINDS else 0.0

    @property
    def state_kind(self) -> str:
        """Returns the canonical state-transition label for logging/tests."""
        if not self.sections:
            return "no_docx_found"
        if any(w.get("kind") == "unknown_heading" for w in self.warnings):
            ratio = self.coverage_ratio
            if ratio >= 0.80:
                return "full_coverage"
            return "llm_fallback_used"
        return "full_coverage" if self.coverage_ratio >= 0.80 else "partial_coverage"


# Strip leading section numbering ("1.", "1.2", "Section 3:", "A.")
# before classification.
_NUMBERING_RX = re.compile(
    r"^\s*(?:section\s+)?(?:[a-z]\.|\d+(?:\.\d+)*[\.\):]?)\s+",
    re.I,
)


def _strip_numbering(heading: str) -> str:
    if not heading:
        return ""
    return _NUMBERING_RX.sub("", heading).strip()


def classify_heading(heading: str) -> SectionKind:
    candidates = [heading or "", _strip_numbering(heading or "")]
    for candidate in candidates:
        for pattern, kind in HEADING_PATTERNS:
            if pattern.search(candidate):
                return kind
    # ML fallback — ONLY when the regex dictionary returned nothing (the "other"
    # bucket), and only above a conservative confidence floor so a genuinely
    # novel/ambiguous heading stays "other" rather than being mislabelled.
    # Dependency-optional: no-op when sklearn/joblib or the artifact is absent.
    text = (heading or "").strip()
    if text:
        try:
            from app.ml.text_classifier import get_classifier
            label, _conf = get_classifier("report_section", min_confidence=0.70).predict(text)
            if label in EXPECTED_KINDS:
                return label  # type: ignore[return-value]
        except Exception:
            pass
    return "other"


def parse_report_paragraphs(
    paragraphs: Iterable[tuple[str, str]],
) -> ReportParseResult:
    """Walk `(style, text)` pairs from python-docx and split into sections.

    Style strings starting with 'Heading' (case-insensitive) open a new
    section. All non-heading paragraphs accumulate into the current section.
    """
    out = ReportParseResult()
    current_kind: SectionKind = "unknown"
    current_heading = ""
    current_body: list[str] = []
    ordinal = 0
    has_seen_heading = False

    def flush() -> None:
        nonlocal current_body
        text = "\n".join(p for p in current_body if p.strip())
        if not text and not has_seen_heading:
            current_body = []
            return
        subcap_ids = sorted(set(_SUBCAP_RX.findall(text)))
        e_ids = sorted(set(_E_ID_RX.findall(text)))
        out.sections.append(ReportSection(
            kind=current_kind, heading=current_heading,
            body=text, ordinal=ordinal,
            subcap_ids_mentioned=subcap_ids,
            e_ids_mentioned=e_ids,
        ))
        current_body = []

    for style, text in paragraphs:
        if style and style.lower().startswith("heading"):
            # Close the previous section first
            flush()
            ordinal += 1
            current_heading = (text or "").strip()
            current_kind = classify_heading(current_heading)
            if current_kind == "other":
                out.warnings.append({
                    "kind": "unknown_heading",
                    "heading": current_heading,
                    "ordinal": ordinal,
                })
            has_seen_heading = True
        else:
            current_body.append(text or "")

    flush()
    # If no headings ever opened, emit a single unknown section
    if not has_seen_heading and current_body:
        out.sections.append(ReportSection(
            kind="unknown", heading="",
            body="\n".join(current_body), ordinal=0,
        ))
    return out


def extract_paragraphs_from_docx(path: Path) -> list[tuple[str, str]]:
    """Read a DOCX file and emit (style_name, text) pairs IN DOCUMENT ORDER.

    Uses python-docx, walking `document.element.body` so paragraphs and
    tables stay interleaved exactly as authored. Tables are flattened to
    text rows (cells joined by tabs) and tagged "Normal" so they accrue
    to the CURRENT section rather than opening a new one.

    Document order matters: the IBKR-shape reports put each §9
    recommendation's title banner ("R1 [CRITICAL] Financial Services
    Cloud — …") and its Capability/Current/Target score grid in 1x1 /
    multi-column DOCX tables between the section's paragraphs. The prior
    implementation appended ALL tables after ALL paragraphs, which
    detached those banners from §9 and dumped them at the tail of the
    last section — report_recommendations then fabricated recs out of
    the leftover prose fragments (2026-07-06 defect family).
    """
    try:
        import docx  # type: ignore[import-not-found]
        from docx.oxml.ns import qn  # type: ignore[import-not-found]
        from docx.table import Table  # type: ignore[import-not-found]
        from docx.text.paragraph import Paragraph  # type: ignore[import-not-found]
    except ImportError:
        log.warning("python-docx not installed; skipping %s", path)
        return []
    doc = docx.Document(str(path))
    out: list[tuple[str, str]] = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            para = Paragraph(child, doc)
            style = (para.style.name if para.style else "") or ""
            text = (para.text or "").strip()
            if text:
                out.append((style, text))
        elif child.tag == qn("w:tbl"):
            table = Table(child, doc)
            for row in table.rows:
                cells = [(c.text or "").strip() for c in row.cells]
                line = "\t".join(c for c in cells if c)
                if line:
                    out.append(("Normal", line))
    return out


def parse_assessment_report(path: Path | str) -> ReportParseResult:
    """Parse a single Assessment_Report DOCX file.

    Returns an empty result (state=no_docx_found) when the file doesn't
    exist or python-docx isn't available. Callers should always inspect
    `result.state_kind` for the canonical branch label.
    """
    p = Path(path)
    if not p.exists():
        out = ReportParseResult(source_path=str(p))
        out.warnings.append({"kind": "no_docx_found", "path": str(p)})
        return out
    paragraphs = extract_paragraphs_from_docx(p)
    result = parse_report_paragraphs(paragraphs)
    result.source_path = str(p)
    return result


def find_assessment_reports(root: Path | str) -> list[Path]:
    """Locate Assessment_Report*.docx files under a DMA package root.

    Discovery strategy (in priority order, so canonical paths win):
      1. `04_reports/*.docx` (canonical package layout)
      2. `*Assessment_Report*.docx` at package root
      3. Recursive search for any *.docx whose filename matches DMA
         assessment-report tokens, scoped to depth ≤ 3 to avoid
         pathological folder trees.

    The recursive branch (added 2026-05-28 — H7) is what lets the
    historical backfill find report DOCXs in DOCX-only Drive folders
    (no canonical 04_reports/ layout) and folders that nest reports
    under "Reports/" or "Final/" etc. Without it, only the first DOCX
    in the canonical paths was discovered, and 21+ Drive folders in
    the 2026-05-28 backfill were misclassified as "no DMA package
    detected".

    Skips `*Client_Profile*` and `*Research_Report*` — those are
    handled by separate parsers (`client_profile.py` /
    `research_workbook.py`). Returns deduped, sorted list.
    """
    root_p = Path(root)
    out: list[Path] = []
    candidates: list[Path] = []

    # 1. Canonical `04_reports/` layout — at root and one level down
    #    (wrapper folders are common when operators upload zips).
    for base in (root_p, *[c for c in root_p.iterdir() if c.is_dir()]):
        reports_dir = base / "04_reports"
        if reports_dir.is_dir():
            candidates.extend(reports_dir.glob("*.docx"))

    # 2. Root-level DOCX with assessment-report naming.
    candidates.extend(root_p.glob("*Assessment_Report*.docx"))
    candidates.extend(root_p.glob("*[Aa]ssessment*[Rr]eport*.docx"))

    # 3. Recursive fallback — any *.docx within depth 3 whose name
    #    matches DMA report tokens. Capped depth avoids blowing up on
    #    deep mixed-content Drive folders.
    def _walk(p: Path, depth: int) -> None:
        if depth > 3:
            return
        try:
            entries = list(p.iterdir())
        except (PermissionError, OSError):
            return
        for entry in entries:
            if entry.is_file() and entry.suffix.lower() == ".docx":
                candidates.append(entry)
            elif entry.is_dir():
                _walk(entry, depth + 1)

    _walk(root_p, 0)

    # Filter to assessment reports only — drop client_profile,
    # research_report (those have dedicated parsers).
    for c in candidates:
        n = c.name.lower()
        if "client_profile" in n or "research_report" in n:
            continue
        if "assessment" not in n and "report" not in n and "dma" not in n:
            continue
        if c not in out:
            out.append(c)
    return sorted(out)
