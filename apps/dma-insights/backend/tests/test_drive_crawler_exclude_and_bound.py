"""Drive-crawler exclude-existing + bounding contract.

2026-06-18 incident: the crawler ran a SEQUENTIAL cold-start re-ingest of every
`{Client} - DMA` folder with NO exclusion of the already-seeded 94 clients.
Because the seeded entities carry `drive_folder_id='local:…'` keys that the
crawler's real Drive folder ids can never match, every deploy-time crawl
re-created the 94 as fresh ACTIVE rows — the live dashboard's "100 entities" /
junk-named duplicates. It also had no upper bound, so a cold start hung the
deploy window.

This pins the fix: the crawler must (a) recognise an already-known client from
just its folder name (so it can skip it BEFORE downloading), and (b) expose
finite, env-overridable bounds so a run is always fast + finite.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Workers package is one level up from the backend root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.drive_crawler.main import (  # noqa: E402
    CRAWLER_CONCURRENCY,
    CRAWLER_DEADLINE_SEC,
    CRAWLER_MAX_FOLDERS,
    _folder_is_known,
    _norm_client_key,
)


class TestNormClientKey:
    """The three shapes that denote ONE client must collapse to one key."""

    def test_local_seed_id_folder_name_and_display_id_collapse(self) -> None:
        # All three of these are how the SAME client appears in the system:
        #   seeded entity drive_folder_id, real Drive folder name, display_id.
        for seed_id, folder_name, display_id, expected in [
            ("local:Haventree Bank DMA - DMA", "Haventree Bank - DMA",
             "haventree-bank-0001", "haventreebank"),
            ("local:Zions Bancorporation - DMA", "Zions Bancorporation - DMA",
             "zions-bancorporation-0001", "zionsbancorporation"),
            ("local:Exchange Bank - DMA", "Exchange Bank - DMA",
             "exchange-bank-0001", "exchangebank"),
        ]:
            assert _norm_client_key(seed_id) == expected
            assert _norm_client_key(folder_name) == expected
            assert _norm_client_key(display_id) == expected

    def test_strips_dma_marker_ordinal_and_punctuation(self) -> None:
        assert _norm_client_key("Bank of Utah - DMA") == "bankofutah"
        assert _norm_client_key("bank-of-utah-0001") == "bankofutah"
        assert _norm_client_key("  ") == ""
        assert _norm_client_key(None) == ""

    def test_distinct_clients_do_not_collide(self) -> None:
        assert _norm_client_key("Bank of Utah - DMA") != _norm_client_key("Bank OZK - DMA")


class TestFolderIsKnown:
    def test_seeded_client_is_known_from_folder_name_alone(self) -> None:
        known = {"haventreebank", "zionsbancorporation", "bankofutah"}
        # Real Drive folder names for already-seeded clients → excluded.
        assert _folder_is_known("Haventree Bank - DMA", known) is True
        assert _folder_is_known("Zions Bancorporation - DMA", known) is True

    def test_net_new_client_is_not_known(self) -> None:
        known = {"haventreebank", "zionsbancorporation"}
        assert _folder_is_known("Brand New Bank - DMA", known) is False
        assert _folder_is_known("Acme Capital Partners - DMA", known) is False

    def test_empty_or_unmatchable_never_known(self) -> None:
        assert _folder_is_known("", {"x"}) is False
        assert _folder_is_known(None, {"x"}) is False
        assert _folder_is_known("Anything - DMA", set()) is False


class TestBoundsAreFiniteAndConfigurable:
    """A crawl must always be finite so it can never hang the deploy window."""

    def test_bounds_have_safe_finite_defaults(self) -> None:
        assert isinstance(CRAWLER_MAX_FOLDERS, int) and 0 < CRAWLER_MAX_FOLDERS <= 200
        assert isinstance(CRAWLER_CONCURRENCY, int) and 1 <= CRAWLER_CONCURRENCY <= 16
        assert isinstance(CRAWLER_DEADLINE_SEC, int) and 0 < CRAWLER_DEADLINE_SEC <= 3600
