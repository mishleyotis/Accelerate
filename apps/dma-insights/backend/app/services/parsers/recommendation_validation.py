"""Parse `recommendation_validation.json` -> per-rec prerequisite rec_ids.

The DMA bot's recommendation-validation step records, per recommendation,
whether it validated AND (occasionally) a free-text `prerequisite` clause
naming sibling recommendations that must ship first -- e.g. Greenstone R8
(Agentforce): "R2 + R5 must precede R8". That intelligence was
parsed-not-persisted (abandoned at ingest). This extracts the prerequisite
rec_ids so the D4 RecommendationModal can render a Prerequisites / Unlocks
dependency map.

Two observed schemas (the file's dir varies -- `02_research_workbook/` or
`01_evidence/`):
  Greenstone: `validations[].id` = "R1".."R9"; the rec that has prerequisites
              carries a `prerequisite` string field.
  Frost:      `validations[].rec` = "REC-01 MuleSoft" (REC-prefixed token +
              solution name); `finding` + `status` only, NO prerequisite -> {}.

The id mapping is kept in lock-step with the recommendations parser by
reusing its `_rec_id` normaliser, and every extracted id is intersected with
the package's known rec_id set so only confident, real links survive.
Self-references are dropped. Pure / no DB. Returns {} on malformed input.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services.parsers.package_recommendations import _rec_id

# A prerequisite clause names siblings as "R2" / "R5" or "REC-02"; capture the
# digits after an R / REC / REC- prefix. Intersection with known_rec_ids (in
# parse_rec_prerequisites) drops any incidental match that isn't a real rec.
_REC_TOKEN_RE = re.compile(r"\b(?:REC-?|R)(\d{1,3})\b", re.IGNORECASE)


def _row_rec_id(row: dict[str, Any]) -> str | None:
    """Derive the row's own rec_id. Greenstone uses `id` ("R8"); Frost uses
    `rec` ("REC-01 MuleSoft" -- take the leading token)."""
    raw = row.get("id")
    if raw is None:
        rec_field = row.get("rec")
        if isinstance(rec_field, str) and rec_field.strip():
            raw = rec_field.strip().split()[0]  # "REC-01 MuleSoft" -> "REC-01"
    if raw is None or not str(raw).strip():
        return None
    return _rec_id(raw) or None


def _prereq_prose(row: dict[str, Any]) -> str:
    """The dedicated prerequisite field only -- `prerequisite` (str) or
    `prerequisites` (list/str). We deliberately do NOT scan the free-text
    `result` / `check` / `exclusion_check` fields, which mention sibling
    R-ids incidentally and would yield false positives."""
    p = row.get("prerequisite")
    if isinstance(p, str):
        return p
    pl = row.get("prerequisites")
    if isinstance(pl, list):
        return " ".join(str(x) for x in pl)
    if isinstance(pl, str):
        return pl
    return ""


def parse_rec_prerequisites(
    blob: str, known_rec_ids: set[str]
) -> dict[str, list[str]]:
    """Map rec_id -> [prerequisite rec_id, ...] for the rows that declare one.

    `known_rec_ids` are the package's persisted rec_ids (already `REC-NN`);
    every extracted prerequisite is intersected against them so only
    confident matches survive, and the dict only carries rows with >=1 match.
    """
    try:
        data = json.loads(blob)
    except (ValueError, TypeError):
        return {}
    rows: Any = data.get("validations") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        rows = data.get("items") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {}

    out: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        rec_id = _row_rec_id(row)
        if rec_id is None:
            continue
        prose = _prereq_prose(row)
        if not prose:
            continue
        prereqs: list[str] = []
        for m in _REC_TOKEN_RE.finditer(prose):
            cand = f"REC-{int(m.group(1)):02d}"
            if cand == rec_id:          # drop self-reference
                continue
            if cand not in known_rec_ids:  # keep only confident, real links
                continue
            if cand not in prereqs:
                prereqs.append(cand)
        if prereqs:
            out[rec_id] = prereqs
    return out
