"""Shared Google Sheets v4 client primitives.

Used by `workers/sheet_poller/main.py` (5-minute Ops sheet poll).

State-branch contract (`fetch_tab`):
  - incremental_sync     → previous `last_synced_utc` exists; only rows
                           with `last_updated_utc > watermark` returned.
  - full_sync_on_drift   → the local `ops_*` row count diverges by > 5%
                           from the sheet's claimed total → force-resync
                           the whole tab.
  - sheet_unavailable    → Sheets API HttpError → caller falls back to
                           the prior cycle's data and logs a structured
                           warning; no rows mutated.
  - row_conflict         → upserting hits a UNIQUE conflict and `before_json`
                           in the sheet's Audit row matches stored state →
                           sheet wins; conflict logged into audit_log.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from rapidfuzz import distance as rf_distance


@dataclass
class SheetRow:
    tab: str
    row_index: int
    columns: dict[str, Any]


def build_sheets_service() -> Any:
    """Build a Sheets v4 service. Lazy import so this module is
    test-importable without GCP creds."""
    googleapiclient = importlib.import_module("googleapiclient.discovery")
    google_auth = importlib.import_module("google.auth")
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds, _ = google_auth.default(scopes=SCOPES)
    return googleapiclient.build(
        "sheets", "v4", credentials=creds, cache_discovery=False,
    )


def read_tab(service: Any, spreadsheet_id: str, tab: str) -> list[list[Any]]:
    """Read raw values from a sheet tab. Returns rows-of-cells (the
    first row is the header). Empty cells come back as ''.
    """
    resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{tab}!A1:ZZ",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    return resp.get("values", [])


def rows_to_dicts(values: list[list[Any]]) -> list[dict[str, Any]]:
    """Header-row + body-rows → list[dict]."""
    if not values:
        return []
    headers = [str(h).strip() for h in values[0]]
    out: list[dict[str, Any]] = []
    for row in values[1:]:
        d: dict[str, Any] = {}
        for i, h in enumerate(headers):
            if i < len(row):
                d[h] = row[i]
            else:
                d[h] = ""
        out.append(d)
    return out


def fuzzy_match_assignee(
    candidate: str | None, known_names: list[str], *, max_distance: int = 2,
) -> str | None:
    """Match an assigned_to first name to one of the canonical
    ops_team.name strings via Levenshtein distance.

    Returns the matched canonical name when distance ≤ max_distance,
    otherwise None. Pure: no DB or network.

    State-branch contract:
      - exact_match       → returns the input unchanged.
      - fuzzy_match       → returns the closest known name (≤ max_distance).
      - no_match          → returns None.
    """
    if not candidate:
        return None
    cand = candidate.strip()
    if not cand:
        return None
    lower_known = {n.lower(): n for n in known_names}
    if cand.lower() in lower_known:
        return lower_known[cand.lower()]
    best: tuple[str, int] | None = None
    for name in known_names:
        d = rf_distance.Levenshtein.distance(cand.lower(), name.lower())
        if best is None or d < best[1]:
            best = (name, d)
    if best is not None and best[1] <= max_distance:
        return best[0]
    return None
