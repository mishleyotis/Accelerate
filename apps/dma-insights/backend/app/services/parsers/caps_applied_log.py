"""Parse `07_governance/caps_applied_log.csv` into structured cap events.

Per the v2-QA under-leveraged matrix §C10 finding (2026-06-07), every
DMA package except WSFS ships an explicit cap-event log surfacing why
particular subcap scores were ceiling-capped (evidence ceiling, severity
ceiling, regulatory ceiling, etc.). Currently lost — D6 Health Gates
tab shows the capped score but no defensible rationale.

The CSV schema observed across the 4 real fixtures:

    Log_ID, SubCap_ID, Cap_Type, Trigger_Condition, Cap_Ceiling,
    Trigger_Evidence, Affected_Categories, Severity, Date_Applied,
    Recalc_Verified

Values:
  - `Log_ID` example: `IR-001` (issue-register-cross-reference id).
  - `SubCap_ID` example: `P3C3` (category-level cap) or `P3C1.8.CL1`
    (subcap-level).
  - `Cap_Type` example: `REGULATORY`, `EVIDENCE_QUALITY`, `SEVERITY`.
  - `Cap_Ceiling` example: `3.0` (the score this cap puts on the
    subcap).
  - `Trigger_Evidence` is a comma-separated list of E-IDs.
  - `Affected_Categories` is a comma-separated list of pillar/category
    IDs the cap propagates to.

End-user impact when surfaced:
  - AE can explain on a sales call: "this subcap scored M2.5 because
    IR-003 severity capped it at M2.5, not because of low maturity".
  - Reviewer can audit which caps fired and whether they're justified.
  - HealthPage Gates tab gains a sortable cap-events table.

Tolerant of two real-fixture column-name variants:
  - SubCap_ID / SubCapID / Subcap_ID
  - Cap_Type / CapType
  - Trigger_Condition / TriggerCondition
  - Cap_Ceiling / CapCeiling / Ceiling
  - Trigger_Evidence / TriggerEvidence
"""
from __future__ import annotations

import contextlib
import csv
import re
from io import StringIO
from pathlib import Path

from app.schemas.package import CapsAppliedRow

# Header-name aliases. Each canonical field name maps to the set of
# tolerated input header names (case-insensitive comparison).
# Three real-fixture shapes covered:
#   Alma:       Log_ID, SubCap_ID, Cap_Type, Trigger_Condition, …
#   Calprivate: cap_id, cap_type, trigger_reason, trigger_evidence,
#               affected_subcap, raw_score_ceiling, cap_ceiling, …
#   Nicola:     cap_id, cap_type, trigger_reason, trigger_evidence,
#               affected_id, raw_score, cap_ceiling, …
#   Odlum:      cap_id, cap_type, trigger_reason, trigger_evidence,
#               affected_id, raw_score, cap_ceiling, …
_SUBCAP_IN_ROW_RE = re.compile(r"P\d+C\d+(?:\.\d+)*")

_HEADER_ALIASES = {
    "log_id": {
        "log_id", "logid", "log id", "id", "cap_id", "capid",
    },
    "subcap_id": {
        "subcap_id", "subcapid", "sub_cap_id", "subcap id",
        "affected_subcap", "affected_subcap_id", "affected_id", "affectedid",
        "affected", "category", "category_affected", "capability_id",
        "capabilities",
    },
    "cap_type": {"cap_type", "captype", "type"},
    "trigger_condition": {
        "trigger_condition", "triggercondition", "trigger",
        "condition", "trigger_reason", "triggerreason", "reason",
    },
    "cap_ceiling": {
        "cap_ceiling", "capceiling", "ceiling", "cap", "applied_ceiling",
        "final_score", "finalscore",
    },
    "trigger_evidence": {
        "trigger_evidence", "triggerevidence", "evidence",
        "evidence_ids", "evidenceids",
    },
    "affected_categories": {
        "affected_categories", "affectedcategories", "categories",
        "cascade",
    },
    "severity": {"severity", "sev", "level"},
    "date_applied": {
        "date_applied", "dateapplied", "applied_date", "date",
        "applied_on", "appliedon",
    },
    "recalc_verified": {
        "recalc_verified", "recalcverified", "verified", "recalc",
    },
}


def _build_header_index(headers: list[str]) -> dict[str, int]:
    """Map our canonical field names to the input column indexes,
    using the alias table. Unknown headers are silently ignored — the
    parser is forward-compatible with bot-pipeline column additions.
    """
    out: dict[str, int] = {}
    norm = [h.lower().strip() for h in headers]
    for canonical, aliases in _HEADER_ALIASES.items():
        for idx, h in enumerate(norm):
            if h in aliases:
                out[canonical] = idx
                break
    return out


def _split_list_cell(value: str | None) -> list[str]:
    """Split a multi-value cell on `,`, `|`, or whitespace separators
    after a comma. Empty cell -> []. Tolerant of trailing whitespace
    and quoted CSV values.
    """
    if not value:
        return []
    s = value.strip()
    if not s:
        return []
    parts: list[str] = []
    # Tolerant split: comma OR pipe OR semicolon.
    for chunk in s.replace("|", ",").replace(";", ",").split(","):
        c = chunk.strip()
        if c:
            parts.append(c)
    return parts


def parse_caps_applied_log(
    path: Path,
) -> list[CapsAppliedRow]:
    """Parse the CSV into a list of `CapsAppliedRow`.

    Returns [] for: missing file, empty file, no-data-row file. The
    caller is responsible for surfacing a parser_warning when a
    package_present-but-empty situation is meaningful.
    """
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not raw.strip():
        return []
    # Skip leading `#` comment / blank lines (Haventree ships a
    # "# DMA-… Caps Applied Log" banner before the real header) so the
    # DictReader anchors on the true column row, not the comment.
    raw = "\n".join(
        ln for ln in raw.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    )
    if not raw.strip():
        return []
    reader = csv.reader(StringIO(raw))
    try:
        headers = next(reader)
    except StopIteration:
        return []
    idx_by_field = _build_header_index(headers)
    out: list[CapsAppliedRow] = []
    for i, row in enumerate(reader):
        if not row or not any(c.strip() for c in row):
            continue

        def cell(field: str, _row: list[str] = row) -> str | None:
            """Bind `row` to the closure as `_row` so the B023 ruff
            warning about loop-variable capture doesn't bite when this
            helper is called inside the next iteration.
            """
            idx = idx_by_field.get(field)
            if idx is None or idx >= len(_row):
                return None
            v = _row[idx].strip()
            return v or None

        subcap_id = cell("subcap_id")
        if not subcap_id:
            # No subcap column matched — extract a P#C# reference from
            # anywhere in the row (Loan Depot embeds it in the rule /
            # practical_effect prose). Skip only when the cap references no
            # capability at all (1st Security `affected_scope` is pure prose).
            m = _SUBCAP_IN_ROW_RE.search(" ".join(c for c in row if c))
            subcap_id = m.group(0) if m else None
        if not subcap_id:
            continue
        # log_id is display/ordering only — synthesise when the variant
        # ships no cap_id/log_id column.
        log_id = cell("log_id") or f"CAP-{i + 1:03d}"

        with contextlib.suppress(Exception):
            out.append(CapsAppliedRow(
                log_id=log_id,
                subcap_id=subcap_id,
                cap_type=cell("cap_type"),
                trigger_condition=cell("trigger_condition"),
                cap_ceiling=cell("cap_ceiling"),
                trigger_evidence=_split_list_cell(cell("trigger_evidence")),
                affected_categories=_split_list_cell(
                    cell("affected_categories")
                ),
                severity=cell("severity"),
                date_applied=cell("date_applied"),
                recalc_verified=cell("recalc_verified"),
            ))
    return out
