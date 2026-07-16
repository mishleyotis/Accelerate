"""B (2026-07-14 audit): the pack composers now consult the accumulated
learning memory (compose-time prior) — learned preferred evidence + recurring
themes + archetype — and boost evidence selection toward what past helpful
answers relied on. Best-effort + None-safe: empty until the tables accumulate
feedback, so it's a no-op today and an additive, cohort-fenced boost once
populated."""
from __future__ import annotations

import pytest

from app.services.compose_memory import (
    EMPTY_PRIOR,
    ComposePrior,
    boost_scores,
    load_compose_prior,
)
from app.services.nlp.knowledge import build_entity_knowledge


def test_prior_is_empty():
    assert EMPTY_PRIOR.is_empty is True
    assert ComposePrior(preferred_eids=frozenset({"E-1"})).is_empty is False
    assert ComposePrior(recurring_themes=("x",)).is_empty is False
    assert ComposePrior(archetype="compliance-first").is_empty is False


def test_boost_scores_additive_and_resorts():
    hits = [("E-1", 0.40), ("E-2", 0.30), ("E-3", 0.20)]
    prior = ComposePrior(preferred_eids=frozenset({"E-2"}))
    out = boost_scores(hits, prior, boost=0.15)
    assert out[0][0] == "E-2"                 # 0.30 + 0.15 = 0.45 → tops 0.40
    assert dict(out)["E-1"] == 0.40           # non-preferred untouched
    # empty prior → identity
    assert boost_scores(hits, EMPTY_PRIOR) == hits


@pytest.mark.asyncio
async def test_load_prior_none_safe():
    assert await load_compose_prior(None, entity_id="e") is EMPTY_PRIOR
    assert await load_compose_prior(object(), entity_id=None) is EMPTY_PRIOR


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, by_sql):
        self.by_sql = by_sql

    async def execute(self, sql, params=None):
        s = str(sql)
        for key, rows in self.by_sql.items():
            if key in s:
                return _Result(rows)
        return _Result([])


class _BoomSession:
    async def execute(self, *a, **k):
        raise RuntimeError("db down")


@pytest.mark.asyncio
async def test_load_prior_populates_from_tables():
    sess = _FakeSession({
        "chat_learning_signals": [(["E-1", "E-2"],)],
        # archetype lives in archetype_history (one entry per run); the loader
        # extracts the most recent.
        "customer_intelligence_profiles": [(
            ["fragmented data", "manual ops"],
            [{"archetype": "experience-first"}, {"archetype": "compliance-first"}],
        )],
    })
    prior = await load_compose_prior(sess, entity_id="ent-1", surface="rag_answer")
    assert prior.preferred_eids == frozenset({"E-1", "E-2"})
    assert prior.recurring_themes == ("fragmented data", "manual ops")
    assert prior.archetype == "compliance-first"      # latest history entry


@pytest.mark.asyncio
async def test_load_prior_fails_closed_to_empty():
    prior = await load_compose_prior(_BoomSession(), entity_id="ent-1")
    assert prior.is_empty is True             # DB error → empty, never raises


def test_build_entity_knowledge_cohort_fences_preferred(monkeypatch):
    monkeypatch.setenv("DMA_DISABLE_SEMANTIC", "1")
    ek = build_entity_knowledge(
        {"E-1": "commercial lending is manual", "E-2": "marketing shared inbox"},
        preferred_eids=frozenset({"E-1", "E-9"}),   # E-9 is not in the corpus
    )
    assert ek is not None
    assert ek.preferred_eids == frozenset({"E-1"})  # E-9 fenced out
