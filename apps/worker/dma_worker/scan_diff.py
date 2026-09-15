"""Scan diffing (stage 1.1 / TRD §07 step 1).

The scan is idempotent: re-running on an unchanged tree creates nothing.
This module is the pure half — given the current tree listing and the
prior scan state (import_files checksums), split the tree into
new / changed / unchanged / missing. The tree source (Drive, or a local
fixture tree in tests) and the import_scans/import_files writes live in
scan_runner.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FileStat:
    file_id: str              # stable source id (Drive file id / fixture path)
    path_segments: tuple      # folders on the path, then the file name
    name: str
    checksum: str             # drives the unchanged-tree diff
    size_bytes: int
    mime_type: str = ""
    # Source ids of the folders on the path, root-first. A folder NAME is not
    # an identity: the production intake tree carries two distinct folders
    # both called "Corporate America Credit Union - DMA", each with its own
    # scoring workbook, and grouping by name silently discarded one of them.
    parent_ids: tuple = ()
    #: Drive's own `modifiedTime` (RFC-3339), when the source provides one.
    #:
    #: The walk has always FETCHED this and thrown it away — it was read only
    #: as a checksum fallback. Nothing could therefore ask "which of these
    #: copies did the agent write last", and `_package_groups` broke ties on
    #: the FILENAME instead, which is stable and arbitrary and has no
    #: relationship to which file is current. Measured 2026-09-03 on Bank of
    #: Travelers Rest: one client folder holding four workbooks at three
    #: depths, three of them byte-identical, and the scan reading neither the
    #: newest nor the one with scores.
    modified_time: str = ""


@dataclass
class ScanDiff:
    new: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    unchanged: list = field(default_factory=list)
    missing: list = field(default_factory=list)   # ids seen before, absent now — reported, never silently dropped


def diff_tree(current: list[FileStat], prior: dict[str, str]) -> ScanDiff:
    """prior maps file_id -> checksum from the last scan's import_files."""
    d = ScanDiff()
    seen = set()
    for f in current:
        seen.add(f.file_id)
        if f.file_id not in prior:
            d.new.append(f)
        elif prior[f.file_id] != f.checksum:
            d.changed.append(f)
        else:
            d.unchanged.append(f)
    d.missing = [fid for fid in prior if fid not in seen]
    return d
