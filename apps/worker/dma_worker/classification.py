"""Artefact classification and test-case exclusion (stage 1.1 / TRD §07).

Classification ranks every file against the artefact registry by source
priority (1 = scoring workbook … 5 = ops sheet). Test-case detection runs
BEFORE entity resolution so a rehearsal folder never becomes an entity,
and every exclusion records the rule that fired — a silently skipped
folder is indistinguishable from a traversal bug (PRD).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Classification:
    kind: str
    priority: int   # TRD §07 artefact priority; lower ranks higher


# The artefact registry (TRD §07 "Artefact priority"). Order within a
# priority class is first-match.
ARTEFACT_REGISTRY: list[tuple[str, int, re.Pattern]] = [
    ("scoring_workbook", 1, re.compile(r"(scoring|workbook|capability[_ ]mapping).*\.xlsx$|\.xlsm$", re.I)),
    ("assessment_report", 2, re.compile(r"assessment[_ ]report.*\.docx$", re.I)),
    ("client_profile", 3, re.compile(r"client[_ ]profile.*(research)?.*\.docx$", re.I)),
    # The fourth final output of a package (engine/assemble.py's contract).
    # The .docx is the human document; the .json sidecar is what the ingest
    # actually parses — both classify, so neither is silently dropped (the
    # AUD-0091 lesson: 'classified and then dropped' is worse than
    # unclassified, because the record says it was seen).
    ("technographic_scan", 3, re.compile(
        r"technographic[_ ]scan.*\.(docx|json)$", re.I)),
    ("package_manifest", 4, re.compile(r"(^|/)(manifest|run_manifest)\.json$", re.I)),
    ("package_structured", 4, re.compile(
        r"(evidence_index|issue_register|peer_(comparison|scores)|recommendations?_detail|"
        r"research_handoff|qa_verdict|export_\w+)\.(csv|json)$", re.I)),
    ("package_archive", 4, re.compile(r"dma[_ ]?complete[_ ]?package.*\.zip$", re.I)),
    ("ops_sheet", 5, re.compile(r"ops[_ ]sheet|ae[_ ]assignment", re.I)),
]


def classify(name: str) -> Classification | None:
    """None means unrecognised — recorded in import_files with no kind,
    never silently dropped."""
    for kind, priority, pattern in ARTEFACT_REGISTRY:
        if pattern.search(name):
            return Classification(kind, priority)
    return None


# Named exclusion rules — the id is what import_files.exclusion_rule
# records. Predicates receive lower-cased path segments (folder names on
# the path plus the file name).
EXCLUSION_RULES: list[tuple[str, re.Pattern]] = [
    ("test_marker", re.compile(r"\btest(s|ing|case)?\b", re.I)),
    ("demo_marker", re.compile(r"\bdemo\b", re.I)),
    ("sample_marker", re.compile(r"\bsample\b", re.I)),
    ("rehearsal_marker", re.compile(r"\brehearsal\b", re.I)),
    ("template_marker", re.compile(r"\btemplate\b", re.I)),
    ("sandbox_marker", re.compile(r"\bsandbox\b", re.I)),
    ("draft_marker", re.compile(r"\bdraft\b", re.I)),
    ("archive_marker", re.compile(r"\barchived?\b", re.I)),
]


def detect_test_case(path_segments: list[str]) -> str | None:
    """Return the id of the first rule that fires, or None. Runs on every
    segment of the path so a marker anywhere up the tree excludes the
    whole subtree — recorded per file, with this rule id."""
    for segment in path_segments:
        for rule_id, pattern in EXCLUSION_RULES:
            if pattern.search(segment):
                return rule_id
    return None
