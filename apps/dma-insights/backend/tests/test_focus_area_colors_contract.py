"""Contract: focus-area `colors` are wireframe token pairs, in order.

The HeatmapPage's `.fa-card` (frontend/src/pages/HeatmapPage.tsx) reads
`fa.colors` as a 2-tuple gradient. QA audit 2026-06-11 (pixel-sampling
the rendered focus cards against tokens.css) found the prior hash
palette emitting raw web gradients — pink #FF8FB1, violet #A86CFF,
neon mint #38EF7D — none of which exist in the Zennify brand system.

The contract now pins the wireframe's own palette
(docs/wireframe-2026-06/src/01_data.js FOCUS_AREAS[].colors): six
ordered pairs of tokens.css var() references, walked by the card's
position in the entity's rendered list — FA #1 teal, #2 purple, #3
mid-teal, #4 blue, #5 orange, #6 below-brown, then wrapping.
"""
from __future__ import annotations

import re

from app.routers.write_surfaces import (
    _FA_GRADIENT_PALETTE,
    _focus_area_colors,
)

# Every stop must be a tokens.css reference — no raw hex may reach a
# rendered surface (UI/UX brief acceptance criterion #1).
_TOKEN_RE = re.compile(r"^var\(--[a-z0-9-]+\)$")

# The token vocabulary of frontend/styles/tokens.css (subset used here).
_ALLOWED_TOKENS = {
    "var(--z-teal)", "var(--m-bld)", "var(--z-dpur)", "var(--ph0)",
    "var(--z-mid)", "var(--z-blue)", "var(--ph1)", "var(--z-org)",
    "var(--m-act)", "var(--z-below)", "var(--m-act-t)",
}


def test_palette_is_the_wireframe_token_palette() -> None:
    assert _FA_GRADIENT_PALETTE == (
        ("var(--z-teal)", "var(--m-bld)"),
        ("var(--z-dpur)", "var(--ph0)"),
        ("var(--z-mid)", "var(--z-teal)"),
        ("var(--z-blue)", "var(--ph1)"),
        ("var(--z-org)", "var(--m-act)"),
        ("var(--z-below)", "var(--m-act-t)"),
    )


def test_every_stop_is_a_token_reference() -> None:
    for pair in _FA_GRADIENT_PALETTE:
        for stop in pair:
            assert _TOKEN_RE.match(stop), f"non-token color stop: {stop}"
            assert stop in _ALLOWED_TOKENS, f"unknown token: {stop}"


def test_colors_walk_palette_in_wireframe_order_and_wrap() -> None:
    """Position 0 → teal pair (FA-01), 1 → purple (FA-02), …, 6 wraps
    back to teal — the prototype's exact visual rhythm."""
    for pos in range(12):
        got = _focus_area_colors(pos)
        expected = list(_FA_GRADIENT_PALETTE[pos % 6])
        assert got == expected


def test_colors_is_two_item_list_of_strings() -> None:
    colors = _focus_area_colors(0)
    assert isinstance(colors, list)
    assert len(colors) == 2
    assert all(isinstance(c, str) for c in colors)
