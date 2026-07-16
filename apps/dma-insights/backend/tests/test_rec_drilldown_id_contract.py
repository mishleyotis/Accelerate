"""GET /recommendations/{id} — dual-ID contract (2026-07-06 drilldown fix).

Live bug: opening a recommendation from the platform page (stairstep
curve / roadmap chevrons) failed to load. Those openers only hold the
human-readable ``REC-NN`` display code, but the detail endpoint ran
``WHERE r.id = CAST(:rid AS uuid)`` — a display code fails the uuid
cast (Postgres 22P02), the first ``except Exception`` swallowed it, the
identical fallback query re-raised uncaught → HTTP 500 → the modal's
"Couldn't load recommendation" empty state.

Contract now:
  - UUID pk           → passes through, zero extra queries.
  - REC-NN + display_id → resolves within the entity's ACTIVE run.
  - REC-NN, no scope  → resolves when unambiguous; 404 (never 500)
                        when ambiguous across entities or unknown.
  - runs.ccg_catalog_version NULL → response still builds
    (catalogue_version = "unversioned"), not a Pydantic 500.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.recommendations import (
    is_uuid_literal,
    recommendation_detail,
    resolve_recommendation_uuid,
)


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
    email = "ae@zennify.com"


class _View:
    audience = "internal"


_REC_UUID = str(uuid4())


def _rec_row(ver="v7.0"):
    return _Row(
        id=_REC_UUID,
        rec_id="REC-08",
        title="Deploy Data Cloud identity resolution",
        description="Unify profiles across core and digital channels.",
        platform_id="salesforce",
        target_subcap_ids=["P4C1.1.1"],
        addressable_offerings=[],
        cited_l4_features=[],
        cited_constructs=[],
        cited_agents=[],
        uplift_per_pillar={"P4": 0.6},
        effort_band="MEDIUM",
        prerequisite_rec_ids=["REC-03"],
        feature="Data Cloud",
        phase=2,
        root_cause_e_ids=["E-047"],
        outcomes={"time": "6 months", "effort": "M"},
        entity_display_id="alma-bank",
        ccg_catalog_version=ver,
    )


# ── is_uuid_literal ────────────────────────────────────────────────────

def test_uuid_literal_detection():
    assert is_uuid_literal(_REC_UUID)
    assert not is_uuid_literal("REC-08")
    assert not is_uuid_literal("")
    assert not is_uuid_literal("REC-08; DROP TABLE runs")


# ── resolve_recommendation_uuid ────────────────────────────────────────

def test_uuid_passthrough_makes_no_queries():
    session = FakeSession([])
    out = asyncio.run(resolve_recommendation_uuid(session, _REC_UUID, None))
    assert out == _REC_UUID
    assert session.calls == []


def test_rec_code_resolves_scoped_by_display_id():
    session = FakeSession([[_Row(id=_REC_UUID)]])
    out = asyncio.run(
        resolve_recommendation_uuid(session, "REC-08", "alma-bank"),
    )
    assert out == _REC_UUID
    sql, params = session.calls[0]
    assert "r.rec_id = :code" in sql
    assert "e.display_id = :did" in sql
    # code_uc/code_alt: pack-drift normalization ("r-08"/"R-08" → "REC-08")
    # folded into the resolver — the WHERE matches raw, upper, or alt form.
    assert params == {
        "code": "REC-08", "did": "alma-bank",
        "code_uc": "REC-08", "code_alt": "REC-08",
    }


def test_rec_code_unknown_is_404_not_500():
    session = FakeSession([[]])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(resolve_recommendation_uuid(session, "REC-99", "alma-bank"))
    assert exc.value.status_code == 404


def test_rec_code_ambiguous_without_scope_is_404_with_hint():
    session = FakeSession([[_Row(id=_REC_UUID), _Row(id=str(uuid4()))]])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(resolve_recommendation_uuid(session, "REC-01", None))
    assert exc.value.status_code == 404
    assert "display_id" in exc.value.detail


def test_rec_code_unambiguous_without_scope_resolves():
    session = FakeSession([[_Row(id=_REC_UUID)]])
    out = asyncio.run(resolve_recommendation_uuid(session, "REC-08", None))
    assert out == _REC_UUID


# ── recommendation_detail end-to-end (fake session) ───────────────────

def _detail_responses(rec_row):
    """(1) code→uuid resolve, (2) main SELECT, (3) unlocks SELECT.
    Cited lists are empty so no catalogue-resolution queries fire."""
    return [
        [_Row(id=_REC_UUID)],
        [rec_row],
        [_Row(rec_id="REC-11")],
    ]


def test_detail_loads_via_display_code_and_scope():
    session = FakeSession(_detail_responses(_rec_row()))
    out = asyncio.run(
        recommendation_detail(
            "REC-08", _User(), session, _View(), display_id="alma-bank",
        )
    )
    assert out.id == _REC_UUID
    assert out.rec_id == "REC-08"
    # The main SELECT must run on the RESOLVED uuid, not the code.
    main_sql, main_params = session.calls[1]
    assert "CAST(:rid AS uuid)" in main_sql
    assert main_params["rid"] == _REC_UUID
    assert out.dependencies.prerequisites == ["REC-03"]
    assert out.dependencies.unlocks == ["REC-11"]


def test_detail_null_catalogue_version_is_labelled_not_500():
    session = FakeSession(_detail_responses(_rec_row(ver=None)))
    out = asyncio.run(
        recommendation_detail(
            "REC-08", _User(), session, _View(), display_id="alma-bank",
        )
    )
    assert out.catalogue_version == "unversioned"


def test_detail_uuid_path_unchanged():
    session = FakeSession([[_rec_row()], [_Row(rec_id="REC-11")]])
    out = asyncio.run(
        recommendation_detail(_REC_UUID, _User(), session, _View()),
    )
    assert out.rec_id == "REC-08"
    # No resolve query when a UUID is passed: first call IS the main SELECT.
    assert "FROM recommendations r" in session.calls[0][0]
