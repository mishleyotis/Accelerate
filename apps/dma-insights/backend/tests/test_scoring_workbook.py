"""Tests for the scoring workbook parser."""
from __future__ import annotations

import pytest
from openpyxl import Workbook

from app.services.parsers.scoring_workbook import (
    ScoringWorkbookMap,
    col_letter,
    col_to_index,
    collect_sheet_metadata,
    header_to_col,
    parse,
    parse_with_map,
    score_to_band,
    shape_fingerprint,
)


class TestColumnHelpers:
    @pytest.mark.parametrize(
        ("idx", "letter"),
        [(0, "A"), (1, "B"), (25, "Z"), (26, "AA"), (27, "AB"), (51, "AZ"), (52, "BA")],
    )
    def test_col_letter(self, idx: int, letter: str) -> None:
        assert col_letter(idx) == letter

    @pytest.mark.parametrize(
        ("letter", "idx"),
        [("A", 0), ("B", 1), ("Z", 25), ("AA", 26), ("AZ", 51), ("BA", 52)],
    )
    def test_col_to_index(self, letter: str, idx: int) -> None:
        assert col_to_index(letter) == idx

    def test_col_letter_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            col_letter(-1)

    def test_col_letter_round_trip(self) -> None:
        for i in (0, 1, 25, 26, 52, 100, 701, 702):
            assert col_to_index(col_letter(i)) == i


class TestScoreToBand:
    @pytest.mark.parametrize(
        ("score", "band"),
        [
            (1.0, "M1"),
            (1.49, "M1"),
            (1.5, "M2"),
            (2.49, "M2"),
            (2.5, "M3"),
            (3.49, "M3"),
            (3.5, "M4"),
            (4.49, "M4"),
            (4.5, "M5"),
            (5.0, "M5"),
        ],
    )
    def test_bands(self, score: float, band: str) -> None:
        assert score_to_band(score) == band

    @pytest.mark.parametrize("bad", [0.99, 5.01, -1.0])
    def test_out_of_range_raises(self, bad: float) -> None:
        with pytest.raises(ValueError):
            score_to_band(bad)


def _build_workbook(headers: list[str], rows: list[list]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Detailed Scores"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    return wb


class TestCollectMetadataAndFingerprint:
    def test_collect_metadata(self) -> None:
        wb = _build_workbook(
            ["SubCap ID", "Score", "Evidence"],
            [["P1C1.1.1", 3.2, "from annual report"]],
        )
        md = collect_sheet_metadata(wb)
        assert len(md) == 1
        assert md[0].sheet_name == "Detailed Scores"
        assert md[0].headers == ["SubCap ID", "Score", "Evidence"]
        assert md[0].sample_rows == [["P1C1.1.1", 3.2, "from annual report"]]

    def test_fingerprint_stable(self) -> None:
        wb1 = _build_workbook(["SubCap ID", "Score"], [["P1C1.1.1", 3.2]])
        wb2 = _build_workbook(["SubCap ID", "Score"], [["P9C9.9.9", 1.0]])
        md1 = collect_sheet_metadata(wb1)
        md2 = collect_sheet_metadata(wb2)
        # Different rows, same shape → same fingerprint.
        assert shape_fingerprint(md1) == shape_fingerprint(md2)

    def test_fingerprint_changes_when_headers_change(self) -> None:
        wb1 = _build_workbook(["SubCap ID", "Score"], [])
        wb2 = _build_workbook(["SubCap ID", "Maturity"], [])
        assert shape_fingerprint(collect_sheet_metadata(wb1)) != shape_fingerprint(collect_sheet_metadata(wb2))


class TestHeaderToCol:
    def test_present(self) -> None:
        assert header_to_col(["A", "B", "C"], "B") == "B"

    def test_missing(self) -> None:
        assert header_to_col(["A", "B"], "Z") is None

    def test_case_insensitive(self) -> None:
        assert header_to_col(["SubCap ID", "Score"], "subcap id") == "A"


class TestParseWithMap:
    def test_happy_path(self) -> None:
        wb = _build_workbook(
            ["SubCap ID", "Score", "Confidence", "Evidence", "Peer Median"],
            [
                ["P1C1.1.1", 3.2, 0.85, "from annual report", 2.8],
                ["P1C1.1.2", 2.5, 0.6, None, 3.0],
            ],
        )
        m = ScoringWorkbookMap(
            subcap_score_sheet="Detailed Scores",
            subcap_id_col="A", score_col="B", confidence_col="C",
            evidence_col="D", peer_median_col="E",
        )
        res = parse_with_map(wb, m)
        assert len(res.rows) == 2
        first = res.rows[0]
        assert first.subcap_id == "P1C1.1.1"
        assert first.score == 3.2
        assert first.confidence == 0.85
        assert first.evidence_excerpt == "from annual report"
        assert first.peer_median == 2.8

    def test_skips_missing_id_and_score(self) -> None:
        wb = _build_workbook(
            ["SubCap ID", "Score"],
            [
                ["P1C1.1.1", 3.2],
                [None, 2.5],            # missing id
                ["P1C1.1.3", None],     # missing score
                ["P1C1.1.4", 4.5],
            ],
        )
        m = ScoringWorkbookMap(subcap_score_sheet="Detailed Scores",
                               subcap_id_col="A", score_col="B")
        res = parse_with_map(wb, m)
        assert [r.subcap_id for r in res.rows] == ["P1C1.1.1", "P1C1.1.4"]

    def test_warns_on_bad_score(self) -> None:
        wb = _build_workbook(
            ["SubCap ID", "Score"],
            [
                ["P1C1.1.1", "garbage"],
                ["P1C1.1.2", 6.5],   # out of range
                ["P1C1.1.3", 3.0],
            ],
        )
        m = ScoringWorkbookMap(subcap_score_sheet="Detailed Scores",
                               subcap_id_col="A", score_col="B")
        res = parse_with_map(wb, m)
        assert [r.subcap_id for r in res.rows] == ["P1C1.1.3"]
        kinds = sorted(w["kind"] for w in res.warnings)
        assert kinds == ["bad_score_cell", "score_out_of_range"]


class TestParseCacheFlow:
    def test_cache_hit_skips_infer(self) -> None:
        wb = _build_workbook(
            ["SubCap ID", "Score"],
            [["P1C1.1.1", 3.2]],
        )
        cached = {
            shape_fingerprint(collect_sheet_metadata(wb)):
                ScoringWorkbookMap(subcap_score_sheet="Detailed Scores",
                                   subcap_id_col="A", score_col="B")
        }
        infer_calls: list[int] = []

        def infer(_md):
            infer_calls.append(1)
            raise AssertionError("should not be called when cached")

        res = parse(
            wb,
            map_cache_lookup=lambda fp: cached.get(fp),
            map_cache_store=lambda _fp, _m: None,
            infer_map=infer,
        )
        assert infer_calls == []
        assert len(res.rows) == 1

    def test_cache_miss_calls_infer_and_stores(self) -> None:
        wb = _build_workbook(
            ["SubCap ID", "Score"],
            [["P1C1.1.1", 3.2]],
        )
        stored: dict[str, ScoringWorkbookMap] = {}

        def infer(_md):
            return ScoringWorkbookMap(subcap_score_sheet="Detailed Scores",
                                       subcap_id_col="A", score_col="B")

        res = parse(
            wb,
            map_cache_lookup=lambda _fp: None,
            map_cache_store=lambda fp, m: stored.update({fp: m}),
            infer_map=infer,
        )
        assert len(res.rows) == 1
        assert len(stored) == 1
