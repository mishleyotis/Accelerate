"""Pattern registry — artifact-shape fingerprints instead of exact filenames.

Why: report-agnosticism. The ingestion audit showed loaders keyed on
exact filenames/tab names (10/25 catalogue tabs loaded; value chains 0
rows ever), so any drift in the bot's output silently dropped data.
Parsers register STRUCTURAL fingerprints here — filename regexes, CSV
header sets, JSON key sets, workbook sheet names — and
:func:`match_artifact` returns the best parser with a confidence score.
An artifact that matches nothing flows to the generic section-miner AND
gets a structured ``PATTERN_GAP`` warning via
:func:`record_pattern_gap`, so `qa_language_audit`'s pattern-gap
zero-day report can list every shape the registry has not learned yet.

Deliberately minimal: page agents wire the per-parser fingerprints in;
this module only owns registration, matching, and gap recording.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

_FINGERPRINT_FIELDS = ("filename_regex", "headers", "keys", "sheet_names")

_REGISTRY: list[dict] = []


def register(fingerprint: dict, parser_key: str) -> None:
    """Register a structural fingerprint for ``parser_key``.

    ``fingerprint`` supports: ``filename_regex`` (str, searched against
    the basename, case-insensitive) and/or ``headers`` / ``keys`` /
    ``sheet_names`` (iterables of expected tokens, matched
    case-insensitively). At least one component is required — an empty
    fingerprint would match everything.
    """
    if not parser_key:
        raise ValueError("parser_key is required")
    normalized: dict = {}
    for field in _FINGERPRINT_FIELDS:
        value = fingerprint.get(field)
        if not value:
            continue
        if field == "filename_regex":
            normalized[field] = str(value)
        else:
            normalized[field] = {str(v).strip().lower() for v in value if str(v).strip()}
    if not normalized:
        raise ValueError("fingerprint must define at least one component")
    _REGISTRY.append({"fingerprint": normalized, "parser_key": parser_key})


def _component_scores(
    fingerprint: dict,
    basename: str,
    observed: dict[str, set[str]],
) -> list[float]:
    scores: list[float] = []
    for field, expected in fingerprint.items():
        if field == "filename_regex":
            scores.append(1.0 if re.search(expected, basename, re.IGNORECASE) else 0.0)
        else:
            got = observed.get(field) or set()
            scores.append(len(expected & got) / len(expected) if expected else 0.0)
    return scores


def match_artifact(
    path: str | Path,
    headers: list[str] | None = None,
    keys: list[str] | None = None,
    sheet_names: list[str] | None = None,
) -> tuple[str | None, float]:
    """Best-matching parser for an artifact → ``(parser_key | None, confidence)``.

    Confidence is the mean of the fingerprint's component scores
    (filename regex hit, header/key/sheet overlap fractions). Below the
    0.5 floor no parser is returned — the caller falls to the generic
    miner and records a pattern gap; the raw confidence still comes back
    so the gap row can say how close the nearest pattern was.
    """
    basename = Path(path).name if path else ""
    observed = {
        "headers": {str(h).strip().lower() for h in headers or []},
        "keys": {str(k).strip().lower() for k in keys or []},
        "sheet_names": {str(s).strip().lower() for s in sheet_names or []},
    }
    best_key: str | None = None
    best_conf = 0.0
    for entry in _REGISTRY:
        scores = _component_scores(entry["fingerprint"], basename, observed)
        confidence = sum(scores) / len(scores) if scores else 0.0
        if confidence > best_conf:
            best_key, best_conf = entry["parser_key"], confidence
    if best_conf >= 0.5:
        return best_key, round(best_conf, 4)
    return None, round(best_conf, 4)


def record_pattern_gap(run_warnings: list, path: str | Path, reason: str) -> dict:
    """Append a structured PATTERN_GAP entry to ``run_warnings`` and return it.

    The entry shape is stable (``code`` = "PATTERN_GAP") so the
    qa_language_audit zero-day report can aggregate gaps across runs and
    the registry learns each new artifact shape exactly once.
    """
    entry = {
        "code": "PATTERN_GAP",
        "path": str(path),
        "reason": reason,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    run_warnings.append(entry)
    return entry


def registered() -> list[dict]:
    """Snapshot of the registry (for audits/tests)."""
    return [dict(entry) for entry in _REGISTRY]


def reset() -> None:
    """Clear the registry — test isolation only."""
    _REGISTRY.clear()
