"""Warning-severity taxonomy tests (Part 12.1).

Pins:
  - the ``{SEVERITY}/{code}: detail`` prefixed form emitted by
    ``dma_package.warn`` and parsed by ``classify_warning``
  - legacy (unprefixed) warning-family classification
  - ``structure_warnings`` + ``severity_counts`` aggregation
  - the fail-loud hollow-gate predicate in historical_backfill
  - the three formerly-silent except sites now emit DEGRADED warnings
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.parsers.dma_package import (
    SEVERITY_DATA_LOSS,
    SEVERITY_DEGRADED,
    SEVERITY_INFO,
    classify_warning,
    severity_counts,
    structure_warnings,
    warn,
)


class TestWarnHelper:
    def test_warn_appends_prefixed_string(self) -> None:
        ws: list[str] = []
        entry = warn(ws, "hollow_package", SEVERITY_DATA_LOSS, "zero evidence")
        assert ws == ["DATA_LOSS/hollow_package: zero evidence"]
        assert entry == ws[0]

    def test_prefixed_round_trip(self) -> None:
        ws: list[str] = []
        warn(ws, "run_manifest_reconciled", SEVERITY_INFO, "drift normalized")
        c = classify_warning(ws[0])
        assert c == {
            "code": "run_manifest_reconciled",
            "severity": "INFO",
            "detail": "drift normalized",
        }


class TestLegacyClassification:
    def test_data_loss_families(self) -> None:
        assert classify_warning(
            "no_recommendations_source: package ships no recommendations…"
        )["severity"] == SEVERITY_DATA_LOSS
        assert classify_warning(
            "01_evidence missing — no evidence rows ingested"
        )["severity"] == SEVERITY_DATA_LOSS
        assert classify_warning(
            "catalogue_empty_for_version: ZERO of 700 parsed subcaps…"
        )["severity"] == SEVERITY_DATA_LOSS

    def test_degraded_families(self) -> None:
        assert classify_warning(
            "run_manifest.json: json_corrupt: line 1 col 1: Expecting value"
        )["severity"] == SEVERITY_DEGRADED
        assert classify_warning(
            "scoring loaded from xlsx fallback (698 subcaps…)"
        )["severity"] == SEVERITY_DEGRADED
        assert classify_warning(
            "download_failed:04_reports/report.docx:HTTP_500"
        )["severity"] == SEVERITY_DEGRADED

    def test_unmatched_defaults_to_info(self) -> None:
        c = classify_warning("timeline_events_persisted: 12")
        assert c["severity"] == SEVERITY_INFO
        assert c["code"] == "timeline_events_persisted"

    def test_dict_entries_pass_through(self) -> None:
        c = classify_warning({
            "code": "PATTERN_GAP", "reason": "no fingerprint matched",
        })
        assert c["code"] == "PATTERN_GAP"
        assert c["severity"] == SEVERITY_INFO


class TestAggregation:
    def test_structure_and_counts(self) -> None:
        ws = [
            "DATA_LOSS/hollow_package: zero evidence",
            "DEGRADED/artifact_json_unreadable: x.json skipped",
            "used variant manifest file: 08_appendices/run_manifest.json",
        ]
        structured = structure_warnings(ws)
        assert [s["severity"] for s in structured] == [
            "DATA_LOSS", "DEGRADED", "INFO",
        ]
        counts = severity_counts(structured)
        assert counts == {"INFO": 1, "DEGRADED": 1, "DATA_LOSS": 1}


class TestHollowGate:
    def _pkg(self, *, scores: int, evidence: int, recs: int):
        return SimpleNamespace(
            subcap_scores=[object()] * scores,
            evidence=[object()] * evidence,
            recommendations=[object()] * recs,
        )

    def test_hollow_reason_branches(self) -> None:
        from app.scripts.historical_backfill import _hollow_reason
        # Unscored package is NOT hollow (the strict gate skips it earlier).
        assert _hollow_reason(self._pkg(scores=0, evidence=0, recs=0)) is None
        # Fully-populated scored package is clean.
        assert _hollow_reason(self._pkg(scores=5, evidence=3, recs=2)) is None
        # Scored + no evidence.
        assert _hollow_reason(
            self._pkg(scores=5, evidence=0, recs=2)
        ) == "zero_evidence"
        # Scored + no recommendations.
        assert _hollow_reason(
            self._pkg(scores=5, evidence=3, recs=0)
        ) == "zero_recommendations"
        # Both.
        assert _hollow_reason(
            self._pkg(scores=5, evidence=0, recs=0)
        ) == "zero_evidence+zero_recommendations"

    def test_allow_hollow_env(self, monkeypatch) -> None:
        from app.scripts.historical_backfill import _allow_hollow
        monkeypatch.delenv("DMA_ALLOW_HOLLOW", raising=False)
        assert _allow_hollow() is False
        monkeypatch.setenv("DMA_ALLOW_HOLLOW", "1")
        assert _allow_hollow() is True


class TestSilentExceptsNowWarn:
    """The three formerly-silent except sites (dma_package.py) must emit
    DEGRADED warnings with the offending path."""

    def test_institution_ladder_warns_on_corrupt_json(self, tmp_path) -> None:
        from app.services.parsers.dma_package import _institution_from_artifacts
        (tmp_path / "entity_profile.json").write_text("{not json!!!")
        ws: list[str] = []
        _institution_from_artifacts(tmp_path, ws)
        assert any(
            "DEGRADED/artifact_json_unreadable" in w
            and "entity_profile.json" in w
            for w in ws
        )

    def test_subvertical_ladder_warns_on_corrupt_json(self, tmp_path) -> None:
        from app.services.parsers.dma_package import _subvertical_from_artifacts
        (tmp_path / "research_handoff.json").write_text("][")
        ws: list[str] = []
        _subvertical_from_artifacts(tmp_path, ws)
        assert any(
            "DEGRADED/artifact_json_unreadable" in w
            and "research_handoff.json" in w
            for w in ws
        )
        # Duplicate-suppressed: the ladder scans overlapping globs — the
        # same corrupt file must be reported once.
        matching = [w for w in ws if "research_handoff.json" in w]
        assert len(matching) == 1

    def test_export_run_id_synthesis_warns_on_unreadable_csv(
        self, tmp_path, monkeypatch,
    ) -> None:
        from app.services.parsers import dma_package as dp
        scoring = tmp_path / "03_scoring_workbook"
        scoring.mkdir()
        target = scoring / "export_scoring_detail.csv"
        target.write_text("# run_id: DMA-ASM-TEST-20260101-0001\n")
        real_open = Path_open = type(target).open

        def _boom(self, *a, **k):
            if self.name == "export_scoring_detail.csv":
                raise OSError("synthetic unreadable file")
            return real_open(self, *a, **k)

        monkeypatch.setattr(type(target), "open", _boom)
        try:
            ws: list[str] = []
            result = dp._synthesize_run_manifest_from_exports(tmp_path, ws)
            assert result is None
            assert any(
                "DEGRADED/export_csv_unreadable" in w
                and "export_scoring_detail.csv" in w
                for w in ws
            )
        finally:
            monkeypatch.setattr(type(target), "open", Path_open)
