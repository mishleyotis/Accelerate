"""Catalogue diff — emits the payload admin reviews on /admin/catalogue.

Compares the staged version's rows against the prior frozen version, grouped
by table. Output shape is the JSON written to `ccg_loader_runs.diff_vs_prior_version`.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass


@dataclass
class TableDiff:
    table: str
    added: list[str]
    removed: list[str]
    renamed: list[tuple[str, str]]
    unchanged_count: int


def diff_id_lists(
    *,
    table: str,
    prior_ids: Iterable[str],
    current_ids: Iterable[str],
    rename_pairs: Iterable[tuple[str, str]] = (),
) -> TableDiff:
    """Set-diff with rename pairs lifted out so the UI shows them separately."""
    prior = set(prior_ids)
    current = set(current_ids)
    renames = list(rename_pairs)
    renamed_from = {a for a, _ in renames}
    renamed_to = {b for _, b in renames}
    added = sorted(current - prior - renamed_to)
    removed = sorted(prior - current - renamed_from)
    unchanged = len(prior & current)
    return TableDiff(
        table=table,
        added=added,
        removed=removed,
        renamed=renames,
        unchanged_count=unchanged,
    )


def diff_to_payload(diffs: list[TableDiff]) -> dict[str, object]:
    return {
        "tables": [asdict(d) for d in diffs],
        "summary": {
            "total_added": sum(len(d.added) for d in diffs),
            "total_removed": sum(len(d.removed) for d in diffs),
            "total_renamed": sum(len(d.renamed) for d in diffs),
        },
    }
