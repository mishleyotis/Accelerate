"""Tests for the /evidence/:id/run-history endpoint.

State-transition coverage matrix (3 branches in router docstring):

  - evidence_not_found  → test_unknown_e_id_returns_404
  - first_seen_only     → test_first_seen_only_returns_is_first_seen_true
  - seen_in_n_runs      → test_seen_in_two_runs_returns_two_items
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.evidence import evidence_run_history


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows: list[_Row] | None = None):
        self._rows = rows or []

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    """Records execute() calls and returns canned results in order."""

    def __init__(self, responses: list[list[_Row]]):
        # Each entry is the rows for one execute() call.
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, sql, params=None):
        self.calls.append((str(sql), dict(params or {})))
        if self.responses:
            return _Result(rows=self.responses.pop(0))
        return _Result(rows=[])


class _User:
    user_id = "user-1"
    email = "a@b"


# ---------------------------------------------------------------------
# Branch 1 — evidence_not_found
# ---------------------------------------------------------------------


class TestUnknownEvidence:
    def test_unknown_e_id_returns_404(self) -> None:
        session = FakeSession([[]])  # row lookup returns nothing
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                evidence_run_history(
                    e_id="E-999", user=_User(), session=session,
                )
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------
# Branch 2 — first_seen_only
# ---------------------------------------------------------------------


class TestFirstSeenOnly:
    def test_first_seen_only_returns_is_first_seen_true(self) -> None:
        ev_id = str(uuid4())
        ev_row = _Row(
            id=ev_id, e_id="E-001",
            entity_id="ent-A", tier=3,
            freshness_band="current",
        )
        link_row = _Row(
            run_id="run-1", first_seen_in_run=True,
            surfaces_in_run=["P1C1.1.1"],
            request_id="REQ-AAA",
            completed_at=datetime(2026, 5, 1),
            status="ACTIVE",
        )
        session = FakeSession([[ev_row], [link_row]])
        out = asyncio.run(
            evidence_run_history(
                e_id="E-001", user=_User(), session=session,
            )
        )
        assert out["is_first_seen"] is True
        assert out["n_runs"] == 1
        assert out["runs"][0]["first_seen_in_run"] is True
        assert out["runs"][0]["surfaces_in_run"] == ["P1C1.1.1"]


# ---------------------------------------------------------------------
# Branch 3 — seen_in_n_runs
# ---------------------------------------------------------------------


class TestSeenInMultipleRuns:
    def test_seen_in_two_runs_returns_two_items(self) -> None:
        ev_id = str(uuid4())
        ev_row = _Row(
            id=ev_id, e_id="E-002",
            entity_id="ent-A", tier=2,
            freshness_band="aging",
        )
        link_rows = [
            _Row(
                run_id="run-2", first_seen_in_run=False,
                surfaces_in_run=["P2C1.1.1"],
                request_id="REQ-BBB",
                completed_at=datetime(2026, 5, 10),
                status="ACTIVE",
            ),
            _Row(
                run_id="run-1", first_seen_in_run=True,
                surfaces_in_run=["P1C1.1.1"],
                request_id="REQ-AAA",
                completed_at=datetime(2026, 4, 1),
                status="SUPERSEDED",
            ),
        ]
        session = FakeSession([[ev_row], link_rows])
        out = asyncio.run(
            evidence_run_history(
                e_id="E-002", user=_User(), session=session,
            )
        )
        assert out["n_runs"] == 2
        assert out["is_first_seen"] is False
        assert out["runs"][0]["request_id"] == "REQ-BBB"
        assert out["runs"][1]["first_seen_in_run"] is True


# ---------------------------------------------------------------------
# UUID vs e_id resolution
# ---------------------------------------------------------------------


class TestUUIDResolution:
    def test_uuid_form_resolves_directly(self) -> None:
        """When the path token looks like a UUID we use the
        WHERE id = CAST(...) query."""
        ev_id = str(uuid4())
        session = FakeSession([
            [_Row(id=ev_id, e_id="E-001", entity_id="ent-A",
                  tier=3, freshness_band="current")],
            [],
        ])
        asyncio.run(
            evidence_run_history(
                e_id=ev_id, user=_User(), session=session,
            )
        )
        # First call should have id-form params.
        first_sql, first_params = session.calls[0]
        assert "WHERE id = CAST" in first_sql
        assert first_params["id"] == ev_id

    def test_short_e_id_uses_e_id_lookup(self) -> None:
        ev_id = str(uuid4())
        session = FakeSession([
            [_Row(id=ev_id, e_id="E-001", entity_id="ent-A",
                  tier=3, freshness_band="current")],
            [],
        ])
        asyncio.run(
            evidence_run_history(
                e_id="E-001", user=_User(), session=session,
            )
        )
        first_sql, first_params = session.calls[0]
        assert "WHERE e_id =" in first_sql
        assert first_params["e"] == "E-001"
