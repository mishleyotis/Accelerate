"""Strict ingest gate (operator mandate 2026-06-10, supersedes the
2026-06-08 drop policy AND the short-lived narrative-first refinement).

ONLY fully-scored deliverables are ingested. A package that parses to
ZERO subcap scores is SKIPPED at every ingest entry point (local
backfill, Drive backfill, live /ingest/package) — *whatever narrative
it carries* — and recorded in backfill_quarantine so it is re-picked
from Drive automatically once the scored deliverable lands. The
narrative-first refinement persisted unscored packages with report
sections; on the live app those rendered as hollow/partial entities
(empty ScoreRing, blank heatmap) which the operator rejected.

`_is_pre_subcap_framework` is the shared predicate. It must key on the
PARSED package's subcap_scores ONLY — never penalise a selective
re-ingest that *skips* an unchanged (but populated) scoring table.
"""

from types import SimpleNamespace

from app.scripts.historical_backfill import _is_pre_subcap_framework


def _pkg(subcaps, *, sections=None, recs=None, evidence=None):
    return SimpleNamespace(
        subcap_scores=subcaps,
        report_sections=sections or [],
        recommendations=recs or [],
        evidence=evidence or [],
    )


def test_zero_subcaps_is_dropped() -> None:
    assert _is_pre_subcap_framework(_pkg([])) is True
    assert _is_pre_subcap_framework(_pkg(None)) is True


def test_any_subcaps_is_kept() -> None:
    assert _is_pre_subcap_framework(_pkg([object()])) is False
    assert _is_pre_subcap_framework(_pkg([1, 2, 3])) is False


def test_zero_subcaps_with_narrative_sections_is_still_dropped() -> None:
    """The narrative-first escape hatch is GONE: 253 classified report
    sections (the AAA Club Alliance shape) without a single subcap
    score still skip — partial reports stay out of the app until the
    scored deliverable lands in Drive."""
    assert _is_pre_subcap_framework(
        _pkg([], sections=[object()] * 253)
    ) is True


def test_zero_subcaps_with_recommendations_is_still_dropped() -> None:
    assert _is_pre_subcap_framework(
        _pkg([], recs=[object()] * 5)
    ) is True


def test_zero_subcaps_with_evidence_subcap_mappings_is_still_dropped() -> None:
    ev = SimpleNamespace(subcap_mappings=["P1C1.1.1"])
    assert _is_pre_subcap_framework(_pkg([], evidence=[ev])) is True
