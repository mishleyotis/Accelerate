"""Zip-extraction safety guards shared by the ingest ROUTER and the
WORKER backfill path.

WHY THIS MODULE EXISTS (2026-06-10 live incident): these guards used to
live in `app.routers.ingest_package`. The Drive-crawler worker imports
them at extraction time, but `app.routers.*` imports `fastapi` — and the
workers image deliberately does NOT install fastapi (lean image, no HTTP
surface). Every Drive folder ingest crashed with
`ModuleNotFoundError: No module named 'fastapi'` and the deploy-time
backfill stalled at 45/124 with zero packages ingested. Shared
ingest logic therefore lives HERE (framework-free); the router imports
from this module, never the other way around. The lean-worker contract
is pinned by tests/test_worker_import_safety.py.

The guards themselves:

  - `_MAX_PER_ENTRY_UNCOMPRESSED_BYTES` / `_MAX_UNCOMPRESSED_TOTAL_BYTES`
    bound decompressed sizes (zip-bomb defense) for entries we parse.
  - `_zip_entry_should_skip` excludes presentation/deck artifacts the
    parsers never read (05_narrative_deck pptx is 55-65 MB on its own),
    so a real package isn't rejected for transport bulk it doesn't use.
"""
from __future__ import annotations

# Per-entry decompressed cap for entries we ACTUALLY parse (deck
# entries are skipped before this gate fires).
_MAX_PER_ENTRY_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
# Cumulative decompressed-bytes ceiling across the whole archive's
# parsed material. Defends against zip-bomb (100 entries x 50 MB each
# -> 5 GB decompressed). 200 MB is generous for a real parsed DMA
# package (largest fixture: 12 MB uncompressed parsed material).
_MAX_UNCOMPRESSED_TOTAL_BYTES = 200 * 1024 * 1024

# Subpaths that the parsers never read. These are skipped DURING zip
# extraction (before per-entry size limits fire) so a real DMA package
# whose deck PPTX is 59 MB isn't rejected. The skip is a *contract*,
# not a heuristic — adding a new parsed artifact requires updating
# this list AND the relevant parser entrypoint.
_SKIPPED_PACKAGE_PREFIXES = (
    "05_narrative_deck/",
    "narrative_deck/",
    "deck/",
    "slides/",
)
# Extensions inside the above prefixes that we explicitly drop on the
# floor even if filenames are non-canonical. Operators that hand-roll
# a package + accidentally drop a 60 MB pptx in 04_reports/ still get
# a clean ingest with a parser_warning, not a 413.
_SKIPPED_EXTENSIONS = (".pptx", ".key", ".odp")


def _zip_entry_should_skip(name: str) -> bool:
    """True iff this zip entry is a presentation/deck artifact the
    parsers never read. Matches by prefix OR by extension so an
    operator dropping a stray .pptx in the wrong folder still gets
    a clean parse, not a 413.

    Self-healing contract: the skip surfaces as a parser_warning
    (`skipped_non_ingested_artifact:<filename>`) so the operator
    sees what was excluded.
    """
    n = name.replace("\\", "/")
    # Allow leading folder like "WSFS_DMA_Complete_Package/05_narrative_deck/x.pptx"
    parts = n.split("/")
    for i in range(len(parts)):
        suffix = "/".join(parts[i:])
        for prefix in _SKIPPED_PACKAGE_PREFIXES:
            if suffix.startswith(prefix):
                return True
    lower = n.lower()
    return any(lower.endswith(ext) for ext in _SKIPPED_EXTENSIONS)
