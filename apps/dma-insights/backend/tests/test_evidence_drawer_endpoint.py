"""Evidence-drawer endpoint contract (2026-07-06 remediation).

The drawer endpoint (`GET /entities/{d}/evidence`) had two resolution
defects that made 72% of insight-card opens render a zero-row drawer
(10-client stratified measurement, corpus fixtures as ground truth):

  1. The subcap filter was EXACT-match (`:sid = ANY(linked_subcap_ids)`)
     while cards were evidence-linked at derive time via PREFIX/category
     roll-up (attach_evidence_ladder) — a card anchored at P2C1 cites rows
     tagged P2C1.x.y and vice versa. → hierarchical predicate.
  2. There was no way to pass a card's cited E-ID list, so cited rows
     outside the subcap/tier filters were unreachable. → `?e_ids=` whose
     rows are UNIONED into the result regardless of filters.

Coverage matrix:
  - parse_e_ids           pure parsing (empty / dedupe / whitespace / cap)
  - subcap_matches        Python twin of the SQL predicate (exact, both
                          prefix directions, sibling non-match)
  - handler SQL shape     hierarchical predicate + params; e_ids union
                          branch + cited-first ordering; plain query when
                          neither filter is set
  - response mapping      recency_months served; filter_e_ids echoed
"""
from __future__ import annotations

import asyncio
from datetime import date
from uuid import uuid4

import pytest

from app.deps import ViewMode
from app.routers.insights import evidence, parse_e_ids, subcap_matches


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    """Records execute() calls and returns canned rows."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, sql, params=None):
        self.calls.append((str(sql), dict(params or {})))
        return _Result(self.rows)


class _User:
    user_id = "user-1"
    email = "a@b"


class _Resolved:
    id = str(uuid4())
    request_id = "REQ-ABCDEF01"
    # The merged drawer route reads resolved.entity_id for the
    # entity-wide exact `?e_id=` branch (mirrors ResolvedRun's field).
    entity_id = str(uuid4())


def _ev_row(e_id="E-001", tier=3, tags=("P2C1.1.6",)):
    return _Row(
        id=uuid4(), e_id=e_id, source_name="FT.com",
        source_url="https://ft.com/x", excerpt=f"excerpt {e_id}",
        claim_type="FACT", tier=tier, recency_months=7,
        published_date=date(2025, 11, 1), linked_subcap_ids=list(tags),
    )


@pytest.fixture()
def resolver(monkeypatch):
    async def _fake_resolve(session, display_id, run_request_id=None):
        return _Resolved()

    import app.services.run_resolver as rr
    monkeypatch.setattr(rr, "resolve_entity_run", _fake_resolve)
    return _Resolved()


def _call(session, **kw):
    # Direct Python composition: pass every query param explicitly so the
    # FastAPI Query() sentinels never leak into the handler body (the
    # `run` param is plain-None by contract — see
    # tests/test_query_sentinel_regression.py).
    kw.setdefault("subcap_id", None)
    kw.setdefault("min_tier", 8)
    kw.setdefault("limit", 500)
    kw.setdefault("e_id", None)
    kw.setdefault("e_ids", None)
    kw.setdefault("run", None)
    return asyncio.run(
        evidence(
            "alma-bank-0001", _User(), session, ViewMode(audience="internal"),
            **kw,
        )
    )


# ── parse_e_ids ──────────────────────────────────────────────────────────────

def test_parse_e_ids_empty_and_none():
    assert parse_e_ids(None) == []
    assert parse_e_ids("") == []
    assert parse_e_ids(" , ,") == []


def test_parse_e_ids_strips_dedupes_preserves_order():
    assert parse_e_ids(" E-037 ,E-036, E-037 ,E-042") == ["E-037", "E-036", "E-042"]


def test_parse_e_ids_caps_the_list():
    raw = ",".join(f"E-{i}" for i in range(200))
    assert len(parse_e_ids(raw)) == 100
    assert len(parse_e_ids(raw, cap=5)) == 5


# ── subcap_matches (Python twin of the SQL predicate) ────────────────────────

def test_subcap_matches_exact():
    assert subcap_matches("P2C1.1.6", ["P2C1.1.6"])


def test_subcap_matches_category_scope_hits_leaf_tag():
    # The screenshot case: drawer opened with subcap_id=P2C1, rows tagged
    # at leaf grain.
    assert subcap_matches("P2C1", ["P2C1.1.6"])


def test_subcap_matches_leaf_scope_hits_category_tag():
    # "View evidence for <leaf>" against a category/mid-grain-tagged corpus.
    assert subcap_matches("P2C1.1.6", ["P2C1"])
    assert subcap_matches("P2C1.1.6", ["P2C1.1"])


def test_subcap_matches_rejects_siblings_and_lookalikes():
    assert not subcap_matches("P2C1", ["P2C2.1.1"])
    # P2C10 is NOT under P2C1 — the dot boundary must be respected.
    assert not subcap_matches("P2C1", ["P2C10"])
    assert not subcap_matches("P2C10", ["P2C1.1.1"])
    assert not subcap_matches("P2C1", [])
    assert not subcap_matches("P2C1", None)


# ── handler SQL shape ────────────────────────────────────────────────────────

def test_subcap_filter_is_hierarchical(resolver):
    session = FakeSession()
    _call(session, subcap_id="P2C1")
    sql, params = session.calls[0]
    assert "unnest(linked_subcap_ids)" in sql
    assert "tag = :sid" in sql
    assert "tag LIKE :sid_kids" in sql
    assert ":sid LIKE tag || '.%'" in sql
    # The pre-fix exact-only predicate must be gone.
    assert ":sid = ANY(linked_subcap_ids)" not in sql
    assert params["sid"] == "P2C1"
    assert params["sid_kids"] == "P2C1.%"


def test_e_ids_are_unioned_past_all_filters(resolver):
    session = FakeSession()
    _call(session, subcap_id="P9C9", min_tier=1, e_ids="E-037, E-036")
    sql, params = session.calls[0]
    # Union branch: (subcap+tier scope) OR cited.
    assert "OR e_id = ANY(:eids)" in sql
    assert params["eids"] == ["E-037", "E-036"]
    # Cited rows sort first so LIMIT can never push them out.
    assert "(e_id = ANY(:eids)) DESC" in sql
    # Tier + subcap filters still present for the non-cited side
    # (COALESCE form: honest-NULL tiers act as weakest, migration 059).
    assert "COALESCE(tier, 8) <= :min_tier" in sql
    assert params["min_tier"] == 1


def test_no_filters_serves_full_run_list(resolver):
    session = FakeSession()
    _call(session)
    sql, params = session.calls[0]
    assert "run_id = :rid" in sql
    assert "eids" not in params
    assert "sid" not in params
    # COALESCE(tier, 8): honest-NULL tiers (migration 059) sort weakest.
    assert "ORDER BY COALESCE(tier, 8) ASC" in sql


# ── response mapping ─────────────────────────────────────────────────────────

def test_response_serves_recency_and_echoes_cited(resolver):
    session = FakeSession(rows=[_ev_row("E-037", tier=2)])
    out = _call(session, subcap_id="P2C1", e_ids="E-037")
    assert out.filter_e_ids == ["E-037"]
    assert out.filter_subcap_id == "P2C1"
    assert out.run_request_id == "REQ-ABCDEF01"
    item = out.items[0]
    assert item.e_id == "E-037"
    assert item.recency_months == 7
    assert item.published_date == "2025-11-01"
    assert item.linked_subcap_ids == ["P2C1.1.6"]


def test_response_without_e_ids_has_empty_echo(resolver):
    session = FakeSession(rows=[_ev_row()])
    out = _call(session)
    assert out.filter_e_ids == []
    assert out.filter_min_tier == 8
