"""Shallow catalogue alias bridge for category-level SubCap_IDs.

Per the 2026-06-07 v2-QA Batch 3 finding: 14 of 104 active entities
ship their scoring workbook with ``SubCap_ID`` at CATEGORY depth
(``P1C1``, ``P2C3``, ...) rather than canonical subcap depth
(``P1C1.1.1``, ``P2C3.2.4``). The catalogue v7.0 has 1236 subcap-
level rows; none match a category id, so
:class:`CatalogueResolver.resolve_subcap` returns ``SubcapNotFound``
for every row and the run persists with 0 ``subcap_scores``. The
overview + heatmap endpoints have nothing to render -- 28 FAIL cells
in ``qa_render_matrix.tsv``.

The fix is a SHALLOW BROADCAST: when a category-shaped id reaches
the unresolved branch, fetch the category's catalogue v7.0 children
and persist one ``subcap_scores`` row per child, all carrying the
parent's score / band / confidence / rationale. Each broadcast row
is marked ``data_source='shallow_broadcast'`` with
``parent_category_id=<category>`` so the UI can display the
disclosure ("this score is broadcast from the category-level
finding; the bot pipeline should re-emit at subcap depth for full
fidelity").

State-branch contract:

  is_direct_subcap       -- ``^P[1-4]C\\d+\\.\\d+\\.\\d+$`` (or
                            ``-tier-RB`` suffix variants). Resolver
                            handles directly; no bridge.
  is_category_level      -- ``^P[1-4]C\\d+$``. Bridge kicks in,
                            broadcasts to v7.0 children.
  is_subcat_level        -- ``^P[1-4]C\\d+\\.\\d+$``. Mid-depth; we
                            broadcast to grandchildren under the
                            subcat (typically 5-10 children per
                            subcat in v7.0).
  is_pillar_level        -- ``^P[1-4]$``. Too coarse to broadcast
                            usefully (would create ~700 broadcast
                            rows per pillar). We refuse and emit a
                            ``e_pillar_level_score_dropped`` warning
                            instead.
  malformed              -- anything else. Counted as unresolved as
                            before.

The bridge is PURE-FUNCTION: takes parsed-shape inputs + a child
lookup, returns broadcast rows. The persistence layer wires the SQL
side. This keeps the unit tests fast (no DB) and lets the bridge be
re-used by future surfaces (eg. backfilling broadcast rows post-fact
when a prior run was unresolved).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Shape predicates -- exhaustive of the patterns seen in the
# 113-package corpus + the AlmaBank / WSFS real samples.
_RX_PILLAR = re.compile(r"^P[1-4]$")
_RX_CATEGORY = re.compile(r"^P[1-4]C\d+$")
_RX_SUBCAT = re.compile(r"^P[1-4]C\d+\.\d+$")
_RX_SUBCAP = re.compile(r"^P[1-4]C\d+\.\d+\.\d+(?:[-_].*)?$")


def is_pillar_level(subcap_id: str) -> bool:
    return bool(_RX_PILLAR.fullmatch((subcap_id or "").strip()))


def is_category_level(subcap_id: str) -> bool:
    return bool(_RX_CATEGORY.fullmatch((subcap_id or "").strip()))


def is_subcat_level(subcap_id: str) -> bool:
    return bool(_RX_SUBCAT.fullmatch((subcap_id or "").strip()))


def is_subcap_level(subcap_id: str) -> bool:
    return bool(_RX_SUBCAP.fullmatch((subcap_id or "").strip()))


def extract_category(subcap_id: str) -> str | None:
    """Return the category prefix (``P1C1``) of any subcap-shaped id.

    Used by the broadcast logic to look up children when only a
    sub-category-level ID is parsed.
    """
    s = (subcap_id or "").strip()
    m = re.match(r"^(P[1-4]C\d+)(?:\.|$)", s)
    return m.group(1) if m else None


@dataclass(frozen=True)
class BroadcastRow:
    """One broadcast subcap_scores row.

    The persistence layer turns each instance into an UPSERT against
    ``(run_id, subcap_id)``. Score / band / confidence / rationale
    inherit from the parent; ``data_source`` + ``parent_category_id``
    flag the broadcast for the UI; ``is_thin_evidence`` is forced True
    because the source has only category-level evidence (no subcap-
    specific support).
    """
    subcap_id: str
    parent_category_id: str
    score: float
    band: str
    confidence: float | None
    rationale: str | None
    caps_applied: str | None
    data_source: str = "shallow_broadcast"
    is_thin_evidence: bool = True


async def get_category_children(
    session: AsyncSession,
    *,
    version: str,
    category_id: str,
) -> list[str]:
    """Fetch the catalogue v<version> child subcap_ids for a category.

    Returns the canonical child ids, sorted. Empty list when the
    category isn't in the catalogue (defensive: caller should NOT
    broadcast in that case).
    """
    rows = (await session.execute(
        text(
            "SELECT subcap_id FROM ccg_subcaps "
            "WHERE version = :v "
            "  AND subcap_id LIKE :prefix "
            "  AND subcap_id ~ :rx "
            "ORDER BY subcap_id"
        ),
        {
            "v": version,
            "prefix": f"{category_id}.%",
            # ``P1C1.1.1`` (subcap-level) only -- skip
            # ``P1C1.1.1.A`` v8-bump alias rows, capability-level
            # ``P1C1::role`` ids, etc. The regex pins exactly three
            # dot-separated number groups under the category.
            "rx": rf"^{re.escape(category_id)}\.\d+\.\d+$",
        },
    )).all()
    return [r[0] for r in rows]


def build_broadcast_rows(
    *,
    parent_score: float,
    parent_band: str,
    parent_confidence: float | None,
    parent_rationale: str | None,
    parent_caps_applied: str | None,
    parent_category_id: str,
    children_ids: list[str],
) -> list[BroadcastRow]:
    """Pure-function: produce one BroadcastRow per child.

    Empty ``children_ids`` -> empty list (caller must NOT broadcast
    in that case; emit a ``e_category_unresolved`` warning instead).
    """
    if not children_ids:
        return []
    # Append a disclosure suffix to the rationale so anyone reading
    # the raw DB row sees the broadcast origin at a glance. Active-voice
    # phrasing per the UI/UX brief R6 (the language audit caught the
    # prior passive draft).
    if parent_rationale and parent_rationale.strip():
        rationale = (
            f"{parent_rationale.strip()} "
            f"[Catalogue mapping inherits this score from "
            f"{parent_category_id}; the bot pipeline emits subcap-depth "
            f"detail for full fidelity.]"
        )
    else:
        rationale = (
            f"Catalogue mapping inherits this score from the "
            f"{parent_category_id} category finding."
        )
    return [
        BroadcastRow(
            subcap_id=child_id,
            parent_category_id=parent_category_id,
            score=parent_score,
            band=parent_band,
            confidence=parent_confidence,
            rationale=rationale,
            caps_applied=parent_caps_applied,
        )
        for child_id in children_ids
    ]


def derive_broadcast_category(parsed_subcap_id: str) -> str | None:
    """Map a parsed-but-unresolved subcap_id to a category-id we can
    broadcast from.

    Decision matrix:
      - pillar-level (``P1``) -> None (too coarse).
      - category-level (``P1C1``) -> the ID itself.
      - subcat-level (``P1C1.1``) -> the parent category (``P1C1``).
        These are still aggregate; broadcasting to grandchildren is
        a reasonable degradation when the bot omits the leaf depth.
      - subcap-level (``P1C1.1.1``) -> None (resolver should have
        handled this; broadcasting would be wrong).
      - malformed -> None.
    """
    s = (parsed_subcap_id or "").strip()
    if is_pillar_level(s):
        return None
    if is_category_level(s):
        return s
    if is_subcat_level(s):
        return extract_category(s)
    return None
