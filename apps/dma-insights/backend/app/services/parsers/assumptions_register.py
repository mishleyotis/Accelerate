"""Parse the assumptions register from JSON or CSV.

Per the v2-QA under-leveraged matrix §C11 finding (2026-06-07), 2 of 5
real DMA packages ship the analyst's assumptions list:

  Calprivate `08_appendices/assumptions_register.json` — 5 entries
              {id, category, assumption, confidence, basis, scoring_impact}
  Nicola     `07_governance/A9_Assumptions_Register.csv` — CSV with
              {id, assumption, basis, confidence, validation_method,
               priority, capabilities_affected}

End-user impact when surfaced: AE can answer "we assumed FIS Horizon
is the core banking system (MEDIUM-HIGH confidence) because CTO
Birkmann worked at Pacific Mercantile Bank — a documented FIS Horizon
client" on a sales call. Defensible rationale that previously was
parser-lost.

Shapes accepted:
  - Top-level JSON list   (Calprivate canonical)
  - JSON dict with `assumptions` / `register` key wrapping the list
  - CSV with a header row (Nicola shape)

Returns [] for missing file / empty file / no recognizable rows.
"""
from __future__ import annotations

import contextlib
import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

from app.schemas.package import AssumptionRow

# Header-name aliases for the CSV shape. Lower-cased keys; only
# `id` + `assumption` are required.
_CSV_HEADER_ALIASES = {
    "id": {"id", "assumption_id", "asm_id", "asm-id", "asmid"},
    "assumption": {"assumption", "statement", "claim", "hypothesis"},
    "basis": {"basis", "rationale", "evidence", "support", "justification"},
    "confidence": {"confidence", "conf", "certainty", "score"},
    "category": {"category", "domain", "area"},
    "scoring_impact": {"scoring_impact", "impact", "score_impact"},
    "validation_method": {"validation_method", "validation", "validate"},
    "priority": {"priority", "rank", "tier"},
    "capabilities_affected": {
        "capabilities_affected", "capabilities", "subcaps_affected",
        "subcaps", "affected_caps",
    },
}


def _split_csv_list(value: str | None) -> list[str]:
    """Split a multi-value cell on `,` / `|` / `;` separators."""
    if not value:
        return []
    s = value.strip()
    if not s:
        return []
    parts: list[str] = []
    for chunk in s.replace("|", ",").replace(";", ",").split(","):
        c = chunk.strip()
        if c:
            parts.append(c)
    return parts


def _coerce_assumption_dict(raw: dict[str, Any]) -> AssumptionRow | None:
    """Build an AssumptionRow from a raw dict (JSON shape).

    `id` + `assumption` are required; rows lacking either are dropped
    silently — matches the defensive pattern in
    `package_csvs.parse_issue_register_csv`.
    """
    if not isinstance(raw, dict):
        return None
    id_v = raw.get("id") or raw.get("assumption_id")
    assumption_v = raw.get("assumption") or raw.get("statement")
    if not id_v or not assumption_v:
        return None
    kwargs: dict[str, Any] = {
        "id": str(id_v).strip()[:32],
        "assumption": str(assumption_v).strip(),
    }
    for typed_field in ("basis", "confidence"):
        v = raw.get(typed_field)
        if v is not None and str(v).strip():
            kwargs[typed_field] = str(v).strip()
    # Surface any extra fields verbatim (Pydantic extra='allow').
    for k, v in raw.items():
        if k in ("id", "assumption_id", "assumption", "statement"):
            continue
        if k in kwargs:
            continue
        if v is None or v == "":
            continue
        kwargs[k] = v
    with contextlib.suppress(Exception):
        return AssumptionRow(**kwargs)
    return None


def _parse_csv(raw_text: str) -> list[AssumptionRow]:
    """Parse the CSV shape (Nicola)."""
    if not raw_text.strip():
        return []
    reader = csv.reader(StringIO(raw_text))
    try:
        headers = next(reader)
    except StopIteration:
        return []
    norm = [h.lower().strip() for h in headers]
    idx_by_field: dict[str, int] = {}
    for canonical, aliases in _CSV_HEADER_ALIASES.items():
        for i, h in enumerate(norm):
            if h in aliases:
                idx_by_field[canonical] = i
                break
    if "id" not in idx_by_field or "assumption" not in idx_by_field:
        return []
    out: list[AssumptionRow] = []
    for row in reader:
        if not row or not any(c.strip() for c in row):
            continue
        raw: dict[str, Any] = {}
        for canonical, i in idx_by_field.items():
            if i < len(row):
                v = row[i].strip()
                if v:
                    # Split list-typed cells (capabilities_affected)
                    if canonical == "capabilities_affected":
                        raw[canonical] = _split_csv_list(v)
                    else:
                        raw[canonical] = v
        row_obj = _coerce_assumption_dict(raw)
        if row_obj is not None:
            out.append(row_obj)
    return out


def _parse_json(raw_text: str) -> list[AssumptionRow]:
    """Parse the JSON shape (Calprivate). Accepts top-level list or
    a dict wrapping the list under `assumptions` / `register` / `items`.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return []
    rows: list[Any] = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("assumptions", "register", "items", "rows"):
            v = data.get(key)
            if isinstance(v, list):
                rows = v
                break
    out: list[AssumptionRow] = []
    for raw in rows:
        row_obj = _coerce_assumption_dict(raw)
        if row_obj is not None:
            out.append(row_obj)
    return out


def parse_assumptions_register(path: Path) -> list[AssumptionRow]:
    """Top-level entrypoint. Dispatches to JSON or CSV by file suffix."""
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _parse_json(raw)
    if suffix == ".csv":
        return _parse_csv(raw)
    # Unknown suffix: try both, take whichever yields rows.
    out = _parse_json(raw)
    if out:
        return out
    return _parse_csv(raw)
