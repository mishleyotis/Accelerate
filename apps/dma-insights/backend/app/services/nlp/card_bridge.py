"""Bridge the L3 gold composer/refine loop into the insight-card derive path.

``derive_insights.py`` builds D2 cards from a deterministic ladder (profile
findings → section analysis → recommendations → category gaps). This bridge
makes the rubric-graded composer the PRIMARY author: it composes a card per
evidence-rich, in-scope anchor, refines it against the grader, and returns only
the cards that PASS as ``InsightCardRow``s — the same shape the ladder emits, so
they slot in as the highest-priority rung. ``combine_insight_rungs`` then dedups
(gold wins; sibling near-duplicates that share one excerpt collapse), and the
deterministic ladder fills any anchor gold could not ground. Gemini remains the
fallback for anchors neither can reach (wired separately).

Fail-safe: any error assembling the state or composing returns ``[]`` so the
derive chain always falls back to the existing ladder — the gold path can never
break card production.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from app.services.nlp.entity_knowledge import load_entity_state
from app.services.nlp.refine import gemini_rescue, refine_card

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.nlp.entity_knowledge import Capability, EntityState
    from app.services.nlp.grader import Grade, Item
    from app.services.parsers.section_analysis import InsightCardRow

# gold composer is on by default; DMA_GOLD_COMPOSER=0 reverts to the ladder only.
GOLD_ENABLED = os.environ.get("DMA_GOLD_COMPOSER", "1") not in ("0", "false", "")
# Gemini fallback for sub-bar anchors is OFF by default (deterministic-only floor
# for CI / creds-less runs); DMA_GOLD_GEMINI=1 enables it in a Vertex-warm regen.
GEMINI_ENABLED = os.environ.get("DMA_GOLD_GEMINI", "0") in ("1", "true", "yes")
# how many top anchors to attempt per run (evidenced_anchors is already ranked)
_MAX_ANCHORS = 16
# cap the gold cards a single run contributes, so D2 stays a briefing not a dump
_MAX_GOLD_CARDS = 8


def _severity(cap: Capability, is_top: bool) -> str:
    """Card prominence in {critical,high,medium,low} (the insight_cards CHECK).
    A gap card's urgency tracks its score; a strength (expand-from) is medium/low.
    """
    gap = cap.peer_gap if cap.peer_gap is not None else 0.0
    if gap > 0:                                   # strength — expand from it
        return "medium" if is_top else "low"
    if cap.score is not None and cap.score < 2.0:
        return "critical" if is_top else "high"
    return "high" if is_top else "medium"


def _item_to_card(cap: Capability, item: Item, idx: int) -> InsightCardRow:
    from app.services.parsers.section_analysis import InsightCardRow
    return InsightCardRow(
        ic_id=f"GLD{idx:02d}-{cap.subcap_id}"[:16],
        severity=_severity(cap, bool(item.is_top)),
        title=item.title,
        what_text=item.what,
        why_text=item.why or "",
        so_what_text=item.so_what or "",
        linked_subcap_id=cap.subcap_id[:32],
        linked_e_ids=[e[:16] for e in (item.e_ids or [])][:20],
        source_rec_id=None,
    )


def _graded_anchors(
    state: EntityState,
) -> list[tuple[Capability, Item | None, Grade | None, dict]]:
    """Compose + refine every top evidenced anchor once; return the full graded
    set (pass, sub-bar, and skipped) so both the deterministic pass-cards and the
    Gemini escalation reuse a single refine pass per anchor."""
    anchors = state.evidenced_anchors[:_MAX_ANCHORS]
    siblings = anchors[:8]
    out: list[tuple[Capability, Item | None, Grade | None, dict]] = []
    for i, cap in enumerate(anchors):
        try:
            item, grade, telem = refine_card(
                state, cap, siblings=siblings, is_top=(i == 0))
        except Exception:
            continue
        out.append((cap, item, grade, telem))
    return out


def _pass_cards(
    graded: list[tuple[Capability, Item | None, Grade | None, dict]],
) -> list[InsightCardRow]:
    """The PASS items → InsightCardRows, highest-grade first, capped."""
    passed = [(g.grade, cap, item) for cap, item, g, _t in graded
              if item is not None and g is not None and g.passed]
    passed.sort(key=lambda t: -t[0])
    return [_item_to_card(cap, item, idx)
            for idx, (_g, cap, item) in enumerate(passed[:_MAX_GOLD_CARDS])]


def compose_gold_cards(state: EntityState) -> list[InsightCardRow]:
    """Compose + refine a card per top evidenced anchor; return the PASS cards
    as InsightCardRows (ranked, capped). Pure, deterministic — no DB, no Gemini,
    safe to unit-test."""
    return _pass_cards(_graded_anchors(state))


async def gold_cards_for_run(
    session: AsyncSession, display_id: str,
) -> list[InsightCardRow]:
    """Load the entity state for a run and compose its gold cards. Deterministic
    PASS cards first; when DMA_GOLD_GEMINI=1, sub-bar anchors not already covered
    are escalated to the Gemini fallback (re-graded, rendered only on PASS) up to
    the card cap. Returns ``[]`` on any failure or when the gold path is disabled
    — the derive chain then falls back to the deterministic ladder unchanged."""
    if not GOLD_ENABLED or not display_id:
        return []
    try:
        state = await load_entity_state(session, entity_display_id=display_id)
    except Exception:
        return []
    if state is None:
        return []
    try:
        graded = _graded_anchors(state)
        cards = _pass_cards(graded)
    except Exception:
        return []
    if not GEMINI_ENABLED or len(cards) >= _MAX_GOLD_CARDS:
        return cards
    # Escalate the sub-bar anchors (deterministic loop exhausted) to Gemini,
    # newest evidence first, until the card cap is reached. Fail-safe per anchor.
    covered = {c.linked_subcap_id for c in cards}
    for cap, item, g, telem in graded:
        if len(cards) >= _MAX_GOLD_CARDS:
            break
        if (item is None or g is None or telem.get("path") != "needs_gemini"
                or cap.subcap_id in covered):
            continue
        try:
            res = await gemini_rescue(state, cap, item, g)
        except Exception:
            res = None
        if res is not None:
            g_item, _gg, _t = res
            covered.add(cap.subcap_id)
            cards.append(_item_to_card(cap, g_item, len(cards)))
    return cards
