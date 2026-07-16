"""Backend institution-name sanity check (2026-06-10 live incident).

The Drive backfill persisted entities named after raw Drive folder IDs
("1NYe2zU3wmBEvd8ZRFWEHpAGIUuK1O1L2"), folder noise ("VNO DMA
Engagement FINAL"), and bare fragments ("CU"). The ONLY sanitizer was
frontend/src/lib/sanitize.ts — defense-in-depth at render time, far
too late: the junk had already persisted and leaked into display_ids,
peer cohorts, and the directory.

This module is the INGEST-side gate. `check_institution_name` is a
pure predicate; the persist layer uses it to (a) prefer report-derived
names over folder-derived ones, and (b) park scored-but-junk-named
entities in the migration-038 PENDING_REVIEW admin queue instead of
showing them to AEs. It deliberately mirrors the frontend semantics
(PLACEHOLDERS / metadata regex / digit-blob) and adds the ingest-only
classes the frontend never sees:

  - raw Drive folder IDs (long unspaced base64ish tokens)
  - folder-name artifacts (trailing FINAL/DRAFT/COPY/Engagement/DMA)
  - degenerate length (a stripped name of <= 2 chars is a fragment —
    "CU" — while real short clients like IMA / GFS / ANB are 3+)

Framework-free on purpose: the persist path runs on the workers image
(no fastapi) — see tests/test_worker_import_safety.py.
"""
from __future__ import annotations

import re

# Mirrors frontend/src/lib/sanitize.ts (keep in lockstep).
_META_RE = re.compile(
    r"SECTION\s+\d+\s+COMPLETE|Assessment\s+ID\s+DMA-"
    r"|Evidence\s+Mode:\s*(PUBLIC|HYBRID)|^Batch\s+\d+\s*/|^run_id\s*:",
    re.IGNORECASE,
)

_PLACEHOLDERS = frozenset({
    "", "-", "—", "(unknown)", "(untitled)", "null", "undefined",
    "n/a", "none",
})

# "Unnamed client", "Unknown", "Untitled entity" — the literal fallback names
# the leaf parsers / frontend healName emit when no real institution name was
# resolved. These leaked onto the live dashboard as ACTIVE cards (2026-06-18),
# so the ingest gate + repark must treat them as junk and park them. Mirrors
# frontend/src/lib/heal.ts's "Unnamed client" fallback (keep in lockstep).
_UNNAMED_RE = re.compile(
    r"^(unnamed|unknown|untitled|no\s+name)"
    r"(\s+(client|entity|institution|company|bank|account|org(anization)?))?$",
    re.IGNORECASE,
)

# Pure digit/punctuation blobs ("2026-04-29 0001 | 5.0 | …").
_DIGIT_BLOB_RE = re.compile(r"^[\d\s.,;:|%·/-]+$")

# A raw Drive folder/file ID: one long unspaced [A-Za-z0-9_-] token.
# Real institution names contain spaces, dots or are far shorter.
_DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{25,}$")

# Folder-name artifacts that survive `_clean_institution_from_folder`:
# deliverable-stage words and DMA markers glued onto the client name
# ("VNO DMA Engagement FINAL", "Acme Bank FINAL", "Foo DMA v2").
_FOLDER_JUNK_TAIL_RE = re.compile(
    r"(\bDMA\b[\s\w()-]*$"            # "… DMA", "… DMA Engagement FINAL"
    r"|\b(FINAL|DRAFT|COPY)\b\.?$"     # "… FINAL"
    r"|\bEngagement\b\.?$"             # "… Engagement"
    r"|\bDeliverable\b\.?$"            # "… Deliverable"
    r"|\bv\d+(\.\d+)?$)",              # "… v2"
    re.IGNORECASE,
)


def check_institution_name(name: str | None) -> tuple[bool, str | None]:
    """Returns ``(is_junk, reason)``.

    ``is_junk=True`` means the resolved institution_name is NOT fit to
    present to AEs and the entity must be parked in PENDING_REVIEW
    (when scored) or the package skipped (when unscored — the strict
    gate fires first anyway).
    """
    v = (name or "").strip()
    if v.lower() in _PLACEHOLDERS:
        return True, "empty_or_placeholder"
    if _UNNAMED_RE.match(v):
        return True, "unnamed_placeholder"
    if _META_RE.search(v):
        return True, "pipeline_metadata"
    if len(v) > 3 and _DIGIT_BLOB_RE.match(v):
        return True, "digit_blob"
    if _DRIVE_ID_RE.match(v):
        return True, "raw_drive_id"
    if len(v) <= 2:
        return True, "degenerate_fragment"
    if _FOLDER_JUNK_TAIL_RE.search(v):
        return True, "folder_artifact"
    return False, None
