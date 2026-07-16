"""F3a tests — folder-name matcher recognises every real Drive folder
shape we've seen, including the 5 operator-uploaded packages
(RegionsBank, Amalgamated Bank, ANB, WSFS, AmeriCU) whose names
DON'T match the legacy strict ' - DMA' suffix filter.

Bug fixed: the previous `endswith(' - DMA')` filter dropped every
operator-uploaded package silently — `_list_dma_folders` returned 0
and `historical_backfill` reported "found 0 folders" with no
actionable diagnostic. The new `_name_is_dma_candidate` uses a
permissive regex matching any folder containing the token "DMA"
surrounded by word boundaries, with an override env var
`DRIVE_FOLDER_NAME_INCLUDE` for operators who need a tighter pattern.
"""
from __future__ import annotations

import re

import pytest

from app.scripts.historical_backfill import _name_is_dma_candidate


@pytest.mark.parametrize("name", [
    "RegionsBank_DMA_20260518",
    "Amalgamated_Bank_DMA_2026",
    "ANB_DMA_Complete_Bundle",
    "WSFS_DMA_Engagement_Package",
    "AmeriCU_DMA_Deliverable_2026-04-29",
    "First Citizens Bank - DMA",         # legacy strict suffix still works
    "FirstCitizens DMA 2026",            # space-delimited
    "fce-dma-20260601",                  # lowercase + hyphens
    "DMA Engagement WSFS",               # leading token
    "DMA",                               # bare token
])
def test_recognises_real_folder_names(name):
    assert _name_is_dma_candidate(name)


@pytest.mark.parametrize("name", [
    "My Random Folder",
    "HelloWorld",
    "DMA_Recipes_Cookbook",   # ambiguous — token DMA followed by _;
                              # accepted on purpose, see notes below
    "dmagine",                # `dma` is not surrounded by word/path
                              # boundaries — must NOT match
    "",
    "   ",
])
def test_rejects_non_dma_names_or_accepts_with_word_boundary(name):
    if name in ("DMA_Recipes_Cookbook",):
        # Permissive on purpose: ops occasionally use this shape; we
        # still accept it and let the per-folder ingest path skip if
        # the contents don't parse. False-positives are cheap (one
        # extra walk_drive_tree); false-negatives are silent drops.
        assert _name_is_dma_candidate(name)
    else:
        assert not _name_is_dma_candidate(name)


def test_operator_override_via_include_pattern():
    """When ops have a non-standard naming convention, the
    DRIVE_FOLDER_NAME_INCLUDE env var (passed in as `include_pattern`
    to `_name_is_dma_candidate`) overrides the default matcher.
    """
    pat = re.compile(r"^FCE-[A-Z0-9]+$")
    assert _name_is_dma_candidate("FCE-2026Q2", include_pattern=pat)
    # Matches the override → returns True even though the default
    # matcher would reject (no "DMA" token).
    assert _name_is_dma_candidate("FCE-XYZ123", include_pattern=pat)
    # Doesn't match the override → returns False even though the
    # default matcher would accept.
    assert not _name_is_dma_candidate("WSFS_DMA_Engagement_Package", include_pattern=pat)
