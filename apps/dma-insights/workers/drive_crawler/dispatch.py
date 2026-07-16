"""Pure file → parser dispatch for the drive_crawler worker.

Each entry maps a `file_kind` (output of the classifier) to a small
descriptor: which parser to call, which target tables to UPSERT into,
and whether the kind blocks the run from going ACTIVE (handoff JSON is
the only required artifact; the others enrich it).

State-branch contract:
  - file_kind unknown to the dispatch table → returned as `noop` so the
    crawler still records the file in import_files but doesn't try to
    parse it.
  - file_kind=`evidence_handoff_json` is `is_authoritative=True` — its
    payload overrides the workbook-derived rows on E-ID conflict per
    plan §①.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FileKind = Literal[
    "assessment_report", "scoring_workbook", "research_workbook",
    "evidence_handoff_json", "client_profile", "issue_register",
    "supplementary", "unknown",
]


@dataclass(frozen=True)
class DispatchEntry:
    file_kind: FileKind
    parser_module: str   # dotted path; loaded lazily by main.py
    parser_callable: str
    target_tables: tuple[str, ...]
    is_authoritative: bool = False
    blocks_active: bool = False


DISPATCH_TABLE: dict[FileKind, DispatchEntry] = {
    "evidence_handoff_json": DispatchEntry(
        file_kind="evidence_handoff_json",
        parser_module="app.services.parsers.evidence_handoff",
        parser_callable="parse_handoff_text",
        target_tables=(
            "subcap_scores", "evidence_index", "insight_cards",
            "recommendations", "focus_areas", "issue_register",
            "timeline_events", "tech_stack_entries",
        ),
        is_authoritative=True,
        blocks_active=True,
    ),
    "scoring_workbook": DispatchEntry(
        file_kind="scoring_workbook",
        parser_module="app.services.parsers.scoring_workbook",
        parser_callable="parse",
        target_tables=("subcap_scores",),
    ),
    "research_workbook": DispatchEntry(
        file_kind="research_workbook",
        parser_module="app.services.parsers.research_workbook",
        parser_callable="parse_research_workbook",
        target_tables=("evidence_index",),
    ),
    "assessment_report": DispatchEntry(
        file_kind="assessment_report",
        parser_module="app.services.parsers.assessment_report",
        parser_callable="parse_report_paragraphs",
        target_tables=("document_sections", "document_lineage"),
    ),
    "client_profile": DispatchEntry(
        file_kind="client_profile",
        parser_module="app.services.parsers.assessment_report",
        parser_callable="parse_report_paragraphs",
        target_tables=("focus_areas",),
    ),
    "issue_register": DispatchEntry(
        file_kind="issue_register",
        parser_module="app.services.parsers.research_workbook",
        parser_callable="parse_research_workbook",
        target_tables=("issue_register",),
    ),
    "supplementary": DispatchEntry(
        file_kind="supplementary",
        parser_module="",
        parser_callable="",
        target_tables=(),
    ),
}


def lookup(file_kind: str) -> DispatchEntry | None:
    """Returns None for kinds outside the dispatch table (e.g. 'unknown')."""
    return DISPATCH_TABLE.get(file_kind)  # type: ignore[arg-type]


def is_authoritative(file_kind: str) -> bool:
    entry = lookup(file_kind)
    return bool(entry and entry.is_authoritative)


def blocks_run_activation(file_kinds: list[str]) -> bool:
    """A run only flips to ACTIVE when at least one blocks_active=True
    artifact has been parsed (today: evidence_handoff_json).
    """
    return any(blocks_active_for_kind(k) for k in file_kinds)


def blocks_active_for_kind(file_kind: str) -> bool:
    entry = lookup(file_kind)
    return bool(entry and entry.blocks_active)
