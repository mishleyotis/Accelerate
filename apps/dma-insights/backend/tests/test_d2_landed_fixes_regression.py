"""D2 regression guard: lock in the already-landed B3 narrative fixes so a
future change can't silently regress them — the SCQA 0.0-placeholder drop
(`report_synthesis.build_derived_scqa`) and the serve-time scrub
(`text_hygiene.scrub_md`: jargon subs + internal provenance footer).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.parsers.report_synthesis import build_derived_scqa
from app.services.text_hygiene import scrub_md


def _cat(cid: str, score: float, peer: float | None = None,
         name: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(category_id=cid, score=score, peer_median=peer,
                           category_name=name)


def test_scqa_drops_zero_placeholders_no_000_overall() -> None:
    # 0.0 is a placeholder sentinel, not real maturity — must be excluded
    # so the overall is the mean of the real scores (2.0, 3.0 → 2.50).
    cats = [_cat("P1C1", 0.0), _cat("P2C1", 2.0), _cat("P3C1", 3.0)]
    out = build_derived_scqa("AAFCU", cats, [])
    assert out is not None
    assert "0.00" not in out
    assert "2.50" in out


def test_scqa_all_zero_returns_none() -> None:
    cats = [_cat("P1C1", 0.0), _cat("P2C1", 0.0)]
    assert build_derived_scqa("X", cats, []) is None


def test_scrub_md_strips_footer_and_jargon() -> None:
    body = (
        "Level: M3 / Pillar Score: 2.71 per the Severity-to-Maturity Cap "
        "Matrix, driven by the subcap.\n\n"
        "*Derived from extracted scores + recommendations (no analyst "
        "synthesis shipped).*"
    )
    out = scrub_md(body)
    assert out is not None
    low = out.lower()
    assert "derived from extracted scores" not in low
    assert "severity-to-maturity cap matrix" not in low
    assert "subcap" not in low
    assert "level: m3" not in low
    assert "pillar score" not in low
