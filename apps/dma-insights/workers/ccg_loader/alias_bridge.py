"""Alias bridge helpers — derived from `_R1_Source_Reference` tabs across all
four pillar workbooks. The bridge enables old DMAs (scored against v5.0/v6.8)
to render against the current catalogue version at view time.
"""
from __future__ import annotations

from collections.abc import Iterable


def merge_alias_rows(per_pillar_rows: dict[str, list[dict]]) -> list[dict]:
    """Per-pillar alias rows are merged; conflicts are surfaced as warnings.

    A `conflict` is: two rows for the same (prior_version, prior_subcap_id)
    pointing at different current_subcap_ids.
    """
    seen: dict[tuple[str, str], dict] = {}
    out: list[dict] = []
    conflicts: list[dict] = []
    for _pillar, rows in per_pillar_rows.items():
        for row in rows:
            key = (row["prior_version"], row["prior_subcap_id"])
            if key in seen:
                if seen[key]["current_subcap_id"] != row["current_subcap_id"]:
                    conflicts.append(
                        {
                            "key": key,
                            "first": seen[key]["current_subcap_id"],
                            "second": row["current_subcap_id"],
                        }
                    )
                continue
            seen[key] = row
            out.append(row)
    if conflicts:
        out.append({"__warnings__": conflicts})  # caller picks up
    return out


def build_l1_id_promotion_aliases(
    *,
    version: str,
    old_to_new_l1_ids: Iterable[tuple[str, str]],
) -> list[dict]:
    """When a workbook supplies a canonical L1_ID column for the first time
    (resolved decision 7), the prior derived slug becomes an alias with action
    `l1_id_promoted`. Returns rows ready for bulk insert into ccg_subcap_aliases.
    """
    return [
        {
            "prior_version": version,
            "prior_subcap_id": old,  # NB: keyed on L1 here; loader fans out per subcap
            "current_version": version,
            "current_subcap_id": new,
            "migration_action": "l1_id_promoted",
            "migration_notes": f"L1 ID promoted from derived slug {old} → canonical {new}",
        }
        for old, new in old_to_new_l1_ids
        if old != new
    ]
