"""Compose-time learning prior — B (2026-07-14 resilience audit).

The pack composers (exec summary, why-now, platform, insight cards) previously
got ZERO benefit from the accumulated learning memory that the live RAG path
uses (``chat_learning_signals``, ``customer_intelligence_profiles``,
``peer_archetypes``). This module lets a composer load a per-entity prior and
BOOST evidence selection toward what past HELPFUL answers relied on — the same
signal ``rag_answer.apply_learning_signal`` applies on the chat path — plus the
entity's recurring themes + peer archetype for narrative framing.

Contract (matches the "learning boost is purely additive" rule): the prior is
best-effort and None-safe by construction. A missing table, an empty signal
(the fresh/low-traffic case — the tables need accumulated feedback), or any DB
error yields an EMPTY prior, so composition is byte-identical to today until the
memory is populated. Never raises.

Cohort safety: a learned ``preferred_evidence_id`` only ever boosts an evidence
row the entity ACTUALLY has (the boost intersects the composer's own corpus),
so a cluster-level signal can never pull another entity's evidence into this
entity's narrative.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any


def _savepoint(session: Any):
    """A SAVEPOINT context so a failing best-effort query rolls back ONLY
    itself, never poisoning the caller's (deepen's) outer transaction — the
    2026-07-14 crash: a bad column reference here aborted the whole derive
    step. Falls back to a null context for sessions without begin_nested
    (test fakes)."""
    bn = getattr(session, "begin_nested", None)
    return bn() if callable(bn) else contextlib.nullcontext()


@dataclass(frozen=True)
class ComposePrior:
    """What the accumulated learning memory knows for one entity/surface."""

    preferred_eids: frozenset[str] = frozenset()
    recurring_themes: tuple[str, ...] = ()
    archetype: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.preferred_eids or self.recurring_themes or self.archetype)


EMPTY_PRIOR = ComposePrior()


def boost_scores(
    hits: list[tuple[str, float]],
    prior: ComposePrior,
    *,
    boost: float = 0.15,
) -> list[tuple[str, float]]:
    """Re-rank ``(eid, score)`` by adding ``boost`` to any eid the learning
    memory marks preferred, then sort desc. Additive-only (never demotes), and
    a no-op when the prior carries no preferred eids. Pure; never raises."""
    if not hits or not prior.preferred_eids:
        return hits
    out = [
        (eid, score + boost if eid in prior.preferred_eids else score)
        for eid, score in hits
    ]
    out.sort(key=lambda t: t[1], reverse=True)
    return out


async def load_compose_prior(
    session: Any,
    *,
    entity_id: str | None,
    surface: str = "rag_answer",
    min_effectiveness: float = 0.5,
    min_samples: int = 5,
) -> ComposePrior:
    """Best-effort per-entity prior from the learning memory. Returns
    ``EMPTY_PRIOR`` on any failure / empty tables / missing entity_id. The two
    reads are independent and each fails closed to empty. Never raises."""
    if session is None or not entity_id:
        return EMPTY_PRIOR
    preferred: set[str] = set()
    themes: tuple[str, ...] = ()
    archetype: str | None = None

    from sqlalchemy import text

    # 1) learned preferred evidence for this surface (gated the same way the
    #    RAG re-ranker gates: effective + enough samples). Cluster-level, so the
    #    caller intersects with the entity's own corpus (cohort fence). Isolated
    #    in a SAVEPOINT so a failure never poisons the caller's transaction.
    try:
        async with _savepoint(session):
            rows = (await session.execute(
                text(
                    """
                    SELECT preferred_evidence_ids
                    FROM chat_learning_signals
                    WHERE surface = :s
                      AND effectiveness >= :eff
                      AND sample_count >= :n
                      AND preferred_evidence_ids IS NOT NULL
                    """
                ),
                {"s": surface, "eff": min_effectiveness, "n": min_samples},
            )).all()
        for r in rows:
            for e in (r[0] or []):
                if e:
                    preferred.add(str(e))
    except Exception:
        preferred = set()

    # 2) the entity's recurring themes + latest peer archetype (narrative
    #    framing). archetype lives in archetype_history (one entry per run);
    #    take the most recent. SAVEPOINT-isolated.
    try:
        async with _savepoint(session):
            row = (await session.execute(
                text(
                    """
                    SELECT recurring_themes, archetype_history
                    FROM customer_intelligence_profiles
                    WHERE entity_id = CAST(:e AS uuid)
                    """
                ),
                {"e": entity_id},
            )).first()
        if row is not None:
            themes = tuple(str(t) for t in (row[0] or []) if t)
            hist = row[1]
            if isinstance(hist, str):
                import json as _json
                with contextlib.suppress(Exception):
                    hist = _json.loads(hist)
            if isinstance(hist, list) and hist and isinstance(hist[-1], dict):
                archetype = (str(hist[-1].get("archetype"))
                             if hist[-1].get("archetype") else None)
    except Exception:
        themes, archetype = (), None

    return ComposePrior(
        preferred_eids=frozenset(preferred),
        recurring_themes=themes,
        archetype=archetype,
    )
