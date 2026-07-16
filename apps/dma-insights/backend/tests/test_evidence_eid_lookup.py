"""GET /entities/{id}/evidence ?e_id= exact-match lookup (2026-07-06).

The evidence drawer previously had no way to resolve a cited E-ID that
fell outside the current subcap scope or belonged to a different run of
the entity — a citation click could land on an empty drawer. The new
``e_id`` query param widens the scope run → entity for an exact-match
lookup (resolved-run rows sort first) while the default path keeps its
run-scoped behaviour byte-for-byte.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from app.routers.insights import evidence


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows):
        self._rows = rows or []

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    """Records execute() calls and returns canned results in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, sql, params=None):
        self.calls.append((str(sql), dict(params or {})))
        if self.responses:
            return _Result(self.responses.pop(0))
        return _Result([])


class _User:
    user_id = "user-1"
    email = "a@b"


class _View:
    audience = "internal"


_ENTITY_ID = str(uuid4())
_RUN_ID = str(uuid4())


def _base_responses(evidence_rows):
    """resolve_entity_run does (1) entity select, (2) fallback run select;
    the third response feeds the evidence query itself."""
    return [
        [_Row(id=_ENTITY_ID)],
        [_Row(id=_RUN_ID, request_id="REQ-AAAAAAA1", status="ACTIVE",
              ccg_catalog_version="v7.0")],
        evidence_rows,
    ]


def _ev_row(e_id="E-047"):
    return _Row(
        id=uuid4(), e_id=e_id, source_name="10-K", source_url=None,
        excerpt="The firm has no CDP; profiles are stitched manually.",
        claim_type="FACT", tier=2, recency_months=7, published_date=None,
        linked_subcap_ids=["P4C1.1.1"],
    )


def test_e_id_lookup_widens_scope_to_entity_and_echoes_filter() -> None:
    fake = FakeSession(_base_responses([_ev_row()]))
    resp = asyncio.run(evidence(
        display_id="acme-bank-0001", _user=_User(), session=fake,
        view=_View(), subcap_id=None, min_tier=8, limit=100, e_id="E-047",
    ))
    sql, params = fake.calls[-1]
    # entity-wide exact match — NOT run-scoped — so a citation from any
    # run of this entity resolves.
    assert "entity_id = :ent_id" in sql
    assert "e_id = :e_id" in sql
    assert "run_id = :rid" not in sql.split("ORDER BY")[0]
    # resolved-run rows sort first (freshest copy on top).
    assert "(run_id = :rid) DESC" in sql
    assert params["ent_id"] == _ENTITY_ID
    assert params["e_id"] == "E-047"
    assert resp.filter_e_id == "E-047"
    assert [i.e_id for i in resp.items] == ["E-047"]


def test_default_path_stays_run_scoped_and_filter_echo_is_none() -> None:
    fake = FakeSession(_base_responses([_ev_row("E-001")]))
    resp = asyncio.run(evidence(
        display_id="acme-bank-0001", _user=_User(), session=fake,
        view=_View(), subcap_id=None, min_tier=8, limit=100, e_id=None,
    ))
    sql, params = fake.calls[-1]
    assert "run_id = :rid" in sql
    assert "e_id = :e_id" not in sql
    assert params["rid"] == _RUN_ID
    assert resp.filter_e_id is None


def test_e_id_lookup_composes_with_subcap_filter() -> None:
    fake = FakeSession(_base_responses([]))
    resp = asyncio.run(evidence(
        display_id="acme-bank-0001", _user=_User(), session=fake,
        view=_View(), subcap_id="P4C1.1.1", min_tier=8, limit=100, e_id="E-047",
    ))
    sql, params = fake.calls[-1]
    assert "e_id = :e_id" in sql
    # Hierarchical predicate: exact tag, child tags (:sid_kids), or a
    # coarser parent tag — the merged drawer's grain-aware subcap scope.
    assert "unnest(linked_subcap_ids)" in sql and ":sid_kids" in sql
    assert params["sid"] == "P4C1.1.1"
    assert resp.items == []  # honest empty when nothing matches
