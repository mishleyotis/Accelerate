"""Pure selection of which `Firmographics` fields persist into the
`firmographics.parsed_facts` JSONB bag.

Kept dependency-free (no DB / network imports) so it is unit-testable in
isolation and reusable by both the persistence layer and any future
read-side normaliser.

Background (2026-06-09): persistence previously packed parsed_facts via a
hardcoded 3-key allowlist (`total_assets` / `employees_approx` /
`branches`). Every NEW extra the parsers learned to emit — the flat
`financial_baseline.json` fields (`total_deposits`, `roe`,
`efficiency_ratio`, `net_income`, `financials_as_of`) and the flat
`entity_profile.json` classification fields (`ticker`, `sub_vertical`,
`size_tier`, `entity_type`) — was silently dropped before reaching the
DB. This inverts the rule: persist everything that lacks a dedicated
column, so future extras survive ingest automatically.
"""
from __future__ import annotations

from typing import Any

# Firmographics fields that own a dedicated `firmographics` table column
# (or get special handling) and so must NOT be duplicated into parsed_facts.
FIRMOGRAPHICS_COLUMN_FIELDS: frozenset[str] = frozenset(
    {"hq", "primary_regulator", "leadership", "narrative_md",
     "financial_highlights", "sentiment"}
)


def firmographics_parsed_facts(firm_dict: dict[str, Any]) -> dict[str, Any]:
    """Select the firmographics fields to persist into `parsed_facts`.

    Keeps every non-empty field that lacks a dedicated column. Empty
    values (None / "" / [] / {}) are dropped so the JSONB stays compact
    and `COALESCE(EXCLUDED.parsed_facts, …)` re-ingest semantics hold.
    """
    out: dict[str, Any] = {}
    for key, value in firm_dict.items():
        if key in FIRMOGRAPHICS_COLUMN_FIELDS:
            continue
        if value in (None, "", [], {}):
            continue
        out[key] = value
    return out
