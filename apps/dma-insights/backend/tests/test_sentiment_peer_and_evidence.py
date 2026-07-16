"""Sentiment peer-attribution fence + evidence-corpus harvest (2026-07 FCMA).

Pins the two honesty fixes in ``derive_sentiment``:

  * A peer's number is never the client's — a "Peer NPS benchmark" /
    pipe-delimited peer scoreboard ("FCSA NPS 60 (LEADER among FCS peers) |
    CoBank 50 …") never becomes the client's NPS row (FCMA shipped a
    fabricated "NPS 60" grabbed from FCSA's benchmark).
  * The per-source regexes run over the EVIDENCE CORPUS (Source_Name +
    excerpt), so the platform name in Source_Name ("Glassdoor — FCMA
    Reviews") is paired with the rating in the excerpt — instead of
    collapsing to one "Public Sources / neutral / null" row.

All shapes are verbatim from the batch_15 (FCMA) / batch_12 (Capital Farm)
fixtures.
"""
from __future__ import annotations

from app.scripts.derive_sentiment import (
    _extract_from_evidence,
    _is_aggregate_only,
    _is_peer_benchmark,
    normalize_sentiment,
)

# The FCMA E-079 peer-benchmark row that minted the fabricated "NPS 60".
_PEER_ROW = {
    "source_name": "Comparably Peer NPS Benchmark (Farm Credit System)",
    "excerpt": ("Peer NPS benchmark (Comparably Brand Intelligence): FCSA NPS "
                "60 (LEADER among FCS peers) | CoBank 50 | Rabobank 25 | "
                "Wells Fargo 7 | American AgCredit"),
}
# FCMA's OWN rows (platform in Source_Name, rating in the excerpt).
_FCMA_OWN = [
    {"source_name": "Glassdoor — Farm Credit Mid-America Reviews",
     "excerpt": "Overall 4.0-4.1/5 (191 reviews), 79% recommend to friend, "
                "sub-ratings: 4.3 work-life, 4.1 culture, 3.6 career opps"},
    {"source_name": "Apple App Store — Farm Credit Mid-America app",
     "excerpt": "iOS app rated 4.8/5 from 1.1K ratings; last update Jan 2024"},
    {"source_name": "Google Play — Farm Credit Mid-America app",
     "excerpt": "Android listing exists; specific rating not captured this batch"},
]
_PEER_NAMES = {"FCSA", "CoBank", "Rabobank", "Wells Fargo", "American AgCredit",
               "Compeer Financial", "AgCountry Farm Credit", "GreenStone"}


class TestPeerFence:
    def test_peer_nps_benchmark_row_rejected(self) -> None:
        assert _is_peer_benchmark(_PEER_ROW["source_name"], _PEER_ROW["excerpt"],
                                  _PEER_NAMES) is True

    def test_client_own_rows_pass_the_fence(self) -> None:
        for r in _FCMA_OWN:
            assert _is_peer_benchmark(r["source_name"], r["excerpt"],
                                      _PEER_NAMES) is False

    def test_no_peer_nps_attributed_to_client(self) -> None:
        rows = _extract_from_evidence([*_FCMA_OWN, _PEER_ROW], _PEER_NAMES)
        labels = {r["source"] for r in rows}
        # peer NPS 60 never becomes an NPS source row for the client
        assert "Net Promoter Score" not in labels
        norm = normalize_sentiment({"sources": rows})
        nps_vals = [n.get("value") for n in (norm.get("nps") or [])]
        assert 60 not in nps_vals and 60.0 not in nps_vals


class TestEvidenceHarvest:
    def test_client_own_glassdoor_and_appstore_captured(self) -> None:
        rows = {r["source"]: r for r in
                _extract_from_evidence(_FCMA_OWN, _PEER_NAMES)}
        # platform name lives in Source_Name; rating in the excerpt
        assert rows["Glassdoor"]["rating"] == "4.1/5"
        assert rows["App Store"]["rating"] == "4.8/5"
        # a source with no numeric rating stays qualitative (not dropped)
        assert "Google Play" in rows
        assert "rating" not in rows["Google Play"]

    def test_decimal_rating_not_truncated(self) -> None:
        # "4.8/5" must NOT segment to "8/5" (decimal point is not a boundary)
        rows = {r["source"]: r for r in _extract_from_evidence(
            [{"source_name": "Apple App Store",
              "excerpt": "iOS app rated 4.8/5 from 1.1K ratings"}])}
        assert rows["App Store"]["rating"] == "4.8/5"

    def test_yelp_bbb_split_no_mislabel(self) -> None:
        # "Yelp: 3.6/5 (80 reviews). Not BBB Accredited" — the 3.6 is Yelp's,
        # never mislabelled onto the BBB row.
        rows = {r["source"]: r for r in _extract_from_evidence(
            [{"source_name": "Yelp/BBB",
              "excerpt": "Yelp: 3.6/5 (80 reviews). Not BBB Accredited"}])}
        assert rows["Yelp"]["rating"] == "3.6/5"
        assert "rating" not in rows.get("Better Business Bureau", {})

    def test_single_digit_review_sample_voids_rating_not_source(self) -> None:
        # Low-sample honesty (_LOW_SAMPLE): a rating backed by 1-9 reviews is
        # statistically hollow — the NUMBER is voided, the Yelp mention still
        # lands as a qualitative row, and BBB still never inherits it.
        rows = {r["source"]: r for r in _extract_from_evidence(
            [{"source_name": "Yelp/BBB",
              "excerpt": "Yelp: 3.6/5 (8 reviews). Not BBB Accredited"}])}
        assert "rating" not in rows.get("Yelp", {})
        assert "rating" not in rows.get("Better Business Bureau", {})


class TestAggregateOnly:
    def test_public_sources_aggregate_is_aggregate_only(self) -> None:
        assert _is_aggregate_only(
            {"sources": [{"source": "Public Sources"}]}) is True

    def test_real_per_source_blob_is_not_aggregate(self) -> None:
        assert _is_aggregate_only(
            {"sources": [{"source": "Glassdoor", "rating": "3.9/5"}]}) is False

    def test_empty_blob_is_not_aggregate(self) -> None:
        assert _is_aggregate_only({"sources": []}) is False
        assert _is_aggregate_only({}) is False
