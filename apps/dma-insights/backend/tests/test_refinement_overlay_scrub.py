"""apply_refinement_overlay prose hygiene — the S1_jargon deploy-gate fix.

2026-07-10 redeployment QA: 4 committed refinement overlays carried raw
P#C# subcap codes in insight why/so-what prose. apply_refinement_overlay
merged them verbatim into the startup pack, and pack_quality_gate's
ENFORCED S1_jargon segment (ceiling 0) then blocked the regen stage — a
hard deploy blocker. The fix scrubs overlay prose fields through the same
text_hygiene.plain() every composed surface passes through, while leaving
structural fields (ids, subcap keys) and _verification provenance quotes
verbatim. These tests pin that contract.
"""
from __future__ import annotations

import re

from app.scripts.apply_refinement_overlay import _PROSE_KEYS, _scrub_prose

_CODE_RE = re.compile(r"(?:^|[^-A-Za-z0-9])P[1-4]C\d")


def test_prose_fields_are_scrubbed_of_subcap_codes() -> None:
    overlay = {
        "display_id": "test-client-0001",
        "insight_cards": {
            "F-003": {
                "why_text": "M&A layered 4 MDM platforms, so P4C1 Data "
                            "Governance (2.41) is the binding constraint.",
                "so_what_text": "Integration first lifts P4C3 toward 3.5+.",
                "title": "P2C1 Digital Acquisition scores 2.55 vs peers",
            },
        },
    }
    out = _scrub_prose(overlay)
    card = out["insight_cards"]["F-003"]
    for field in ("why_text", "so_what_text", "title"):
        assert not _CODE_RE.search(card[field]), (
            f"{field} still carries a raw subcap code: {card[field]!r}"
        )
    # The surrounding prose must survive the scrub.
    assert "Data" in card["why_text"] and "constraint" in card["why_text"]


def test_structural_fields_and_verification_stay_verbatim() -> None:
    overlay = {
        "display_id": "test-client-0001",
        "insight_cards": {
            "F-001": {
                "linked_subcap_id": "P4C1",
                "affects": ["P4C1", "P4C1.1.4"],
                "what_text": "so P3C1 straight-through processing lags",
            },
        },
        "_verification": {
            "F-001": {"source": "04_reports", "quote": "P4C1 scored 2.41"},
        },
    }
    out = _scrub_prose(overlay)
    card = out["insight_cards"]["F-001"]
    # Structural keys keep their codes — they're anchors, not prose.
    assert card["linked_subcap_id"] == "P4C1"
    assert card["affects"] == ["P4C1", "P4C1.1.4"]
    # Prose is scrubbed.
    assert not _CODE_RE.search(card["what_text"])
    # Provenance quotes are untouched.
    assert out["_verification"]["F-001"]["quote"] == "P4C1 scored 2.41"


def test_committed_overlays_scrub_clean() -> None:
    """Every overlay committed at startup-data/refinement must come out of
    the scrub with zero raw subcap codes in prose fields — the exact
    condition pack_quality_gate enforces at ceiling 0."""
    import json
    from pathlib import Path

    refinement = (
        Path(__file__).resolve().parents[2] / "startup-data" / "refinement"
    )
    if not refinement.is_dir():
        return  # image layouts without the committed pack
    checked = 0

    def _walk(node, fname: str):
        nonlocal checked
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "_verification":
                    continue
                if isinstance(v, str) and k in _PROSE_KEYS:
                    checked += 1
                    assert not _CODE_RE.search(v), (
                        f"{fname}: prose field {k!r} still carries a "
                        f"subcap code after scrub: {v[:90]!r}"
                    )
                else:
                    _walk(v, fname)
        elif isinstance(node, list):
            for v in node:
                _walk(v, fname)

    for fp in sorted(refinement.glob("*.json")):
        scrubbed = _scrub_prose(json.loads(fp.read_text(encoding="utf-8")))
        _walk(scrubbed, fp.name)
    assert checked > 0, "no prose fields found across committed overlays"
