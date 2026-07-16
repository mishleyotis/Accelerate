"""section_analysis_#.json → D2 insight_cards.

Pins the finding→card mapping (WHAT/WHY/SO-WHAT, subcap anchor, E-ID
extraction, M-band severity), the NOT-NULL/skip guards, ic_id dedup, and
the end-to-end derivation against the real ProPartners package.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.parsers.section_analysis import (
    _severity_from_maturity,
    insights_from_recommendations,
    parse_section_analyses,
)

_PROPARTNERS = (
    Path(__file__).resolve().parents[1]
    / "tests/fixtures/dma_packages_batches/batch_08/ProPartners - DMA"
)


def test_severity_from_maturity() -> None:
    assert _severity_from_maturity("P2C4 ceiling capped at M1-M2") == "high"
    assert _severity_from_maturity("P1C1 Strategy transitioning M2") == "medium"
    assert _severity_from_maturity("P3C3 Compliance strong at M4") == "low"
    assert _severity_from_maturity("no band here") == "medium"


def test_parse_real_propartners() -> None:
    if not _PROPARTNERS.exists():
        import pytest
        pytest.skip("fixture moved")
    cards = parse_section_analyses(_PROPARTNERS)
    assert len(cards) >= 3
    # all NOT-NULL invariants hold
    for c in cards:
        assert c.ic_id and c.title and c.what_text
        assert c.linked_subcap_id.startswith("P")
        assert c.severity in ("critical", "high", "medium", "low")
    # ic_ids unique
    assert len({c.ic_id for c in cards}) == len(cards)
    # the "Zero CRM" finding maps cleanly: WHAT/WHY/SO-WHAT + subcap + E-IDs
    crm = next((c for c in cards if "CRM" in c.title), None)
    assert crm is not None
    assert crm.linked_subcap_id == "P2C4"
    assert crm.severity == "high"
    assert "E-001" in crm.linked_e_ids
    assert crm.so_what_text  # zennify action present


def test_dedup_and_skip(tmp_path: Path) -> None:
    d = tmp_path / "04_reports"
    d.mkdir()
    (d / "section_analysis_1.json").write_text(json.dumps({
        "top_findings": [
            {"id": "F-001", "title": "Has subcap", "observation": "x [E-1]",
             "maturity": "P1C1 at M1", "zennify": "do thing"},
            {"id": "F-002", "title": "No subcap anchor",
             "observation": "generic text", "maturity": "no ids"},  # skip
            {"id": "F-003", "title": "", "observation": "y",
             "maturity": "P2C2 M2"},  # skip (no title)
        ]
    }))
    (d / "section_analysis_2.json").write_text(json.dumps({
        "top_findings": [
            {"id": "F-001", "title": "Dup id diff section",
             "observation": "z", "maturity": "P3C3 M3"},  # ic_id deduped
        ]
    }))
    cards = parse_section_analyses(tmp_path)
    assert len(cards) == 2  # F-002 (no subcap) + F-003 (no title) skipped
    assert len({c.ic_id for c in cards}) == 2  # second F-001 re-id'd


def test_e2e_insight_cards_populated() -> None:
    from app.services.parsers.dma_package import parse_package

    if not _PROPARTNERS.exists():
        import pytest
        pytest.skip("fixture moved")
    pkg = parse_package(_PROPARTNERS)
    assert len(pkg.insight_cards) >= 3
    assert all(c.linked_subcap_id for c in pkg.insight_cards)


def test_insights_from_category_gaps() -> None:
    from app.schemas.package import CategoryScoreRow
    from app.services.parsers.section_analysis import insights_from_category_gaps
    cats = [
        CategoryScoreRow(category_id="P2C1", pillar_id="P2", score=1.5, peer_median=2.8),
        CategoryScoreRow(category_id="P1C1", pillar_id="P1", score=3.2, peer_median=2.5),  # above → skip
        CategoryScoreRow(category_id="P4C2", pillar_id="P4", score=1.6),  # low, no peer
        CategoryScoreRow(category_id="P3C3", pillar_id="P3", score=3.5, peer_median=3.4),  # parity → skip
    ]
    cards = insights_from_category_gaps(cats)
    ids = {c.linked_subcap_id for c in cards}
    assert ids == {"P2C1", "P4C2"}  # only the gaps/low ones
    p2 = next(c for c in cards if c.linked_subcap_id == "P2C1")
    assert p2.severity == "high" and "2.8" in p2.what_text
    # Honest prefixes: below-peer → GAP, low-absolute-no-peer → MAT.
    assert p2.ic_id.startswith("GAP-")
    p4 = next(c for c in cards if c.linked_subcap_id == "P4C2")
    assert p4.ic_id.startswith("MAT-")
    # Every derived card now carries an actionable so-what (was hardcoded "").
    assert all(c.so_what_text.strip() for c in cards)


def test_category_gap_strengths_are_low_severity_strengths_to_extend() -> None:
    """A high-maturity entity at/above the peer median on every category must
    surface its relative priorities as strengths-to-extend — distinct copy +
    STR- prefix and the LOWEST urgency severity, never a 'medium'/'high' that
    reads like a deficit (the 2026-06-23 corpus audit found these mislabeled).

    The severity MUST be persistable: the DB CHECK `insight_cards_severity_chk`
    and `_persist_insight_cards` accept only critical/high/medium/low, so an
    out-of-set label (the old 'opportunity') is silently dropped at persist and
    empties the entity's Insights surface — the qa-gates `insights` GAP that
    failed for the all-strength entities (Elliott, LPL, Farm Credit MA)."""
    from app.schemas.package import CategoryScoreRow
    from app.services.parsers.package_persist import _VALID_INSIGHT_SEVERITY
    from app.services.parsers.section_analysis import insights_from_category_gaps
    cats = [
        CategoryScoreRow(category_id="P1C1", pillar_id="P1", score=4.2, peer_median=3.5),
        CategoryScoreRow(category_id="P2C1", pillar_id="P2", score=3.9, peer_median=3.6),
        CategoryScoreRow(category_id="P3C1", pillar_id="P3", score=4.5, peer_median=4.0),
    ]
    cards = insights_from_category_gaps(cats)
    assert cards, "relative-priority fallback must still populate D2"
    assert all(c.ic_id.startswith("STR-") for c in cards)
    assert all("strength" in c.title.lower() for c in cards)
    assert all(c.so_what_text.strip() for c in cards)
    # Lowest urgency, and — critically — a value the DB/persist accept.
    assert all(c.severity == "low" for c in cards)
    assert all(c.severity in _VALID_INSIGHT_SEVERITY for c in cards)


def test_all_category_gap_severities_are_persistable() -> None:
    """Every severity the gap deriver can emit — deficit GAPs, early-stage MAT,
    and relative-mode STRength cards — must be in the persist allowlist (== the
    DB CHECK set). The deriver↔persist contract that, had it been pinned, would
    have caught the 'opportunity' regression before it reached qa-gates."""
    from app.schemas.package import CategoryScoreRow
    from app.services.parsers.package_persist import _VALID_INSIGHT_SEVERITY
    from app.services.parsers.section_analysis import insights_from_category_gaps
    mixed = [
        CategoryScoreRow(category_id="P1C1", pillar_id="P1", score=1.4, peer_median=3.0),  # gap → high
        CategoryScoreRow(category_id="P2C1", pillar_id="P2", score=2.6, peer_median=3.2),  # gap → medium
        CategoryScoreRow(category_id="P3C1", pillar_id="P3", score=1.6),                   # low/no-peer → MAT
    ]
    strengths = [
        CategoryScoreRow(category_id="P4C1", pillar_id="P4", score=4.2, peer_median=3.5),  # strength → STR
    ]
    for cats in (mixed, strengths):
        cards = insights_from_category_gaps(cats)
        assert cards
        for c in cards:
            assert c.severity in _VALID_INSIGHT_SEVERITY, (
                f"{c.ic_id} severity {c.severity!r} is not persistable"
            )


def _rec(**over):
    from app.schemas.package import RecommendationRow
    base = {
        "id": "REC-1", "title": "Adopt Marketing Cloud", "priority": "high",
        "root_cause": {"finding": "P2C1.1 personalization gap"},
        "solution": {"description": "Roll out Marketing Cloud."},
    }
    base.update(over)
    return RecommendationRow(**base)


def test_recs_derived_card_never_has_blank_why() -> None:
    """A rec with a subcap anchor but no peer benchmark / scoring impact must
    still get a grounded (non-empty) WHY anchored to its subcap."""
    cards = insights_from_recommendations([_rec()])
    assert len(cards) == 1
    card = cards[0]
    assert card.linked_subcap_id == "P2C1.1"
    assert card.why_text.strip()                       # never blank
    assert "P2C1.1" in card.why_text                   # grounded in the anchor


def test_recs_derived_card_prefers_real_peer_benchmark() -> None:
    """When the rec carries a peer benchmark, that wins over the fallback."""
    cards = insights_from_recommendations([
        _rec(peer_benchmark={"summary": "Trails the peer median by 1.2."}),
    ])
    assert len(cards) == 1
    assert "peer median" in cards[0].why_text.lower()
    assert "see the heatmap" not in cards[0].why_text.lower()
