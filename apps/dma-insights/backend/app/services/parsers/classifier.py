"""File classifier — first stage of the Drive parse pipeline.

Drive folders for each DMA are unstructured: analysts drop a mix of scoring
workbooks, research workbooks, evidence-handoff JSON, DOCX reports, client
profile docs, issue registers, screenshots, supplementary PDFs. The
classifier maps each file to a `file_kind` so the right downstream parser
runs.

Strategy:
  1. **Cheap filename + extension match.** Most files follow the naming
     convention `{Kind}_{Client}_{REQ}.{ext}` (e.g.
     `Scoring_Workbook_FCE_REQ-A6654887.xlsx`). When the filename pattern
     matches a known kind, we return immediately — no Gemini call needed.
  2. **Few-shot Gemini Flash classification** as a fallback. The fallback
     is wrapped behind a callable so unit tests don't need network.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

FileKind = Literal[
    "assessment_report",
    "scoring_workbook",
    "research_workbook",
    "evidence_handoff_json",
    "client_profile",
    "issue_register",
    "supplementary",
    "unknown",
]

# (regex, kind) — first match wins. Patterns are case-insensitive.
FILENAME_PATTERNS: list[tuple[re.Pattern[str], FileKind]] = [
    (re.compile(r"^assessment[_\- ]report", re.I), "assessment_report"),
    (re.compile(r"^scoring[_\- ]workbook", re.I), "scoring_workbook"),
    (re.compile(r"^research[_\- ]workbook", re.I), "research_workbook"),
    (re.compile(r"^app[_\- ]payload[_\- ]v?\d", re.I), "evidence_handoff_json"),
    (re.compile(r"^evidence[_\- ]handoff", re.I), "evidence_handoff_json"),
    (re.compile(r"^client[_\- ]profile", re.I), "client_profile"),
    (re.compile(r"^issue[_\- ]register", re.I), "issue_register"),
]

EXTENSION_KINDS: dict[str, FileKind] = {
    ".pdf": "supplementary",
    ".png": "supplementary",
    ".jpg": "supplementary",
    ".jpeg": "supplementary",
}


@dataclass
class Classification:
    kind: FileKind
    confidence: float  # 0.0 - 1.0
    rationale: str


def classify_by_filename(filename: str) -> Classification | None:
    name = filename.strip()
    for pattern, kind in FILENAME_PATTERNS:
        if pattern.search(name):
            return Classification(
                kind=kind, confidence=0.95,
                rationale=f"filename matched /{pattern.pattern}/",
            )
    # Pure JSON without an obvious prefix → likely evidence handoff
    if name.lower().endswith(".json"):
        return Classification(
            kind="evidence_handoff_json", confidence=0.6,
            rationale="json extension, unrecognized prefix",
        )
    return None


def classify_by_extension(filename: str) -> Classification | None:
    lower = filename.lower()
    for ext, kind in EXTENSION_KINDS.items():
        if lower.endswith(ext):
            return Classification(
                kind=kind, confidence=0.5,
                rationale=f"extension {ext}",
            )
    return None


def classify(
    filename: str,
    first_chars: str = "",
    *,
    gemini_classify: Callable[[str, str], Classification] | None = None,
) -> Classification:
    """Run the cascade. `gemini_classify` is optional (injected for tests)."""
    fn = classify_by_filename(filename)
    if fn is not None and fn.confidence >= 0.9:
        return fn

    # Try the extension fallback before LLM
    ext = classify_by_extension(filename)

    if gemini_classify is not None:
        try:
            llm = gemini_classify(filename, first_chars)
            if llm.confidence >= 0.7:
                return llm
        except Exception:
            pass

    if fn is not None:
        return fn
    if ext is not None:
        return ext
    return Classification(
        kind="unknown", confidence=0.0,
        rationale="no rule matched",
    )
