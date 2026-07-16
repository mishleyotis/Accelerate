"""Backend institution-name sanity gate (2026-06-10 live incident).

The Drive backfill put raw folder IDs, deliverable noise and bare
fragments on the live directory as client names ("CU",
"1NYe2zU3wmBEvd8ZRFWEHpAGIUuK1O1L2", "VNO DMA Engagement FINAL", one
entity with NO name). check_institution_name is the ingest-side gate:
junk names park the entity in the migration-038 PENDING_REVIEW admin
queue instead of rendering to AEs.

The clean list below is drawn from the REAL corpus (the gate was
validated against all 108 fixture-corpus names with zero false
positives before landing).
"""
from __future__ import annotations

import pytest

from app.services.entity_name_sanity import check_institution_name

JUNK = [
    # the live-incident exhibits
    ("1NYe2zU3wmBEvd8ZRFWEHpAGIUuK1O1L2", "raw_drive_id"),
    ("VNO DMA Engagement FINAL", "folder_artifact"),
    ("CU", "degenerate_fragment"),
    # 2026-06-18 live dashboard: "Unnamed client" rendered as an ACTIVE card —
    # the leaf-parser / healName fallback name leaked through. Park it.
    ("Unnamed client", "unnamed_placeholder"),
    ("unnamed", "unnamed_placeholder"),
    ("Unknown", "unnamed_placeholder"),
    ("Untitled entity", "unnamed_placeholder"),
    ("No Name", "unnamed_placeholder"),
    ("", "empty_or_placeholder"),
    ("(unknown)", "empty_or_placeholder"),
    ("2026-04-29 0001 | 5.0", "digit_blob"),
    # frontend-sanitizer parity (lib/sanitize.ts)
    ("—", "empty_or_placeholder"),
    ("n/a", "empty_or_placeholder"),
    ("SECTION 1 COMPLETE — Assessment ID DMA-RES-X", "pipeline_metadata"),
    # folder-artifact variants
    ("Acme Bank FINAL", "folder_artifact"),
    ("Foo Credit Union DRAFT", "folder_artifact"),
    ("Bar Insurance Deliverable", "folder_artifact"),
    ("Baz Bank v2", "folder_artifact"),
    ("Quux DMA", "folder_artifact"),
]

CLEAN = [
    "FNBO",
    "IMA Financial",
    "WSFS Bank",
    "AAA Club Alliance",
    "Farm Credit Mid-America",
    "1st Security Bank of Washington",
    "Dovenmuehle Mortgage, Inc.",
    "GESA",  # 4 chars — real client, above the fragment threshold
    "SPG",   # 3 chars — real client
    "Payments Canada (The Canadian Payments Association)",
]


@pytest.mark.parametrize("name,expected_reason", JUNK)
def test_junk_names_flagged(name: str, expected_reason: str) -> None:
    is_junk, reason = check_institution_name(name)
    assert is_junk, f"{name!r} should be junk"
    assert reason == expected_reason


@pytest.mark.parametrize("name", CLEAN)
def test_clean_names_pass(name: str) -> None:
    is_junk, reason = check_institution_name(name)
    assert not is_junk, f"{name!r} false-positived as {reason}"


def test_none_is_junk() -> None:
    assert check_institution_name(None) == (True, "empty_or_placeholder")
