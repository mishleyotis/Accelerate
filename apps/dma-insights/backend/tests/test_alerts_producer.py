"""Thin-evidence alerts producer — pure-logic tests (fake session).

QA audit 2026-06-11: the `alerts` table had no producer (0 rows
corpus-wide vs 53k thin subcap flags). These tests pin the derivation
contract from `services/alerts_producer`:

  - per-subcap alerts at/below the per-category aggregation threshold;
    one aggregated CAT:{category} alert above it
  - severity high + PROXY_ESCALATION at 0 evidence rows;
    medium + TIER_UPGRADE at 1
  - waived (closed) content_keys are never resurrected
  - every re-derive DELETEs the entity's OPEN derived rows first, so a
    re-ingest that fixed evidence clears stale alerts
"""
from __future__ import annotations

import asyncio

from app.services.alerts_producer import (
    AGG_THRESHOLD,
    derive_thin_evidence_alerts,
)


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return self._rows


class _FakeSession:
    """Returns thin rows for the first SELECT, closed keys for the
    second; records every INSERT/DELETE with params."""

    def __init__(self, thin_rows, closed_keys=()):
        self._thin = thin_rows
        self._closed = [_Row(content_key=k) for k in closed_keys]
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self.calls.append((s, dict(params or {})))
        if s.startswith("SELECT s.subcap_id"):
            return _Result(self._thin)
        if "DISTINCT content_key" in s:
            return _Result(self._closed)
        return _Result()

    def inserts(self):
        return [p for (s, p) in self.calls if s.startswith("INSERT INTO alerts")]

    def deletes(self):
        return [s for (s, _p) in self.calls if s.startswith("DELETE FROM alerts")]


def _thin(subcap_id, category_id, ec, name=None):
    return _Row(
        subcap_id=subcap_id, category_id=category_id,
        subcap_name=name or subcap_id, evidence_count=ec,
    )


RID = "11111111-1111-1111-1111-111111111111"
EID = "22222222-2222-2222-2222-222222222222"


def test_per_subcap_below_threshold_severity_and_action() -> None:
    rows = [
        _thin("P1C1.1.1", "P1C1", 0, "Vision & strategy"),
        _thin("P1C1.1.2", "P1C1", 1),
    ]
    sess = _FakeSession(rows)
    counters = asyncio.run(
        derive_thin_evidence_alerts(sess, run_id=RID, entity_id=EID)
    )
    assert counters["alerts_inserted"] == 2
    ins = sess.inserts()
    by_key = {p["key"]: p for p in ins}
    zero = by_key["P1C1.1.1"]
    assert zero["sev"] == "high"
    assert zero["action"] == "PROXY_ESCALATION"
    assert zero["ec"] == 0
    assert "Vision & strategy" in zero["title"]
    one = by_key["P1C1.1.2"]
    assert one["sev"] == "medium"
    assert one["action"] == "TIER_UPGRADE"
    assert one["proxy"] is False


def test_aggregates_above_threshold_one_alert_per_category() -> None:
    rows = [
        _thin(f"P2C1.1.{i}", "P2C1", 1) for i in range(AGG_THRESHOLD + 3)
    ]
    sess = _FakeSession(rows)
    counters = asyncio.run(
        derive_thin_evidence_alerts(sess, run_id=RID, entity_id=EID)
    )
    assert counters["alerts_inserted"] == 1
    (only,) = sess.inserts()
    assert only["key"] == "CAT:P2C1"
    assert only["sev"] == "medium"  # no zero-evidence member
    assert f"{AGG_THRESHOLD + 3} subcaps" in only["title"]
    assert len(only["subcaps"]) == AGG_THRESHOLD + 3


def test_aggregate_severity_high_when_any_member_has_zero() -> None:
    rows = [_thin(f"P3C2.1.{i}", "P3C2", 1) for i in range(AGG_THRESHOLD)]
    rows.append(_thin("P3C2.1.99", "P3C2", 0))
    sess = _FakeSession(rows)
    asyncio.run(derive_thin_evidence_alerts(sess, run_id=RID, entity_id=EID))
    (only,) = sess.inserts()
    assert only["sev"] == "high"
    assert only["action"] == "PROXY_ESCALATION"


def test_waived_content_keys_never_resurrected() -> None:
    rows = [
        _thin("P1C1.1.1", "P1C1", 0),
        _thin("P1C1.1.2", "P1C1", 1),
    ]
    sess = _FakeSession(rows, closed_keys={"P1C1.1.1"})
    counters = asyncio.run(
        derive_thin_evidence_alerts(sess, run_id=RID, entity_id=EID)
    )
    assert counters["alerts_inserted"] == 1
    assert counters["skipped_closed"] == 1
    assert [p["key"] for p in sess.inserts()] == ["P1C1.1.2"]


def test_waived_aggregate_key_skipped() -> None:
    rows = [_thin(f"P4C1.1.{i}", "P4C1", 0) for i in range(AGG_THRESHOLD + 1)]
    sess = _FakeSession(rows, closed_keys={"CAT:P4C1"})
    counters = asyncio.run(
        derive_thin_evidence_alerts(sess, run_id=RID, entity_id=EID)
    )
    assert counters["alerts_inserted"] == 0
    assert counters["skipped_closed"] == 1
    assert sess.inserts() == []


def test_rederive_always_clears_open_rows_even_with_no_thin() -> None:
    sess = _FakeSession([])
    counters = asyncio.run(
        derive_thin_evidence_alerts(sess, run_id=RID, entity_id=EID)
    )
    assert counters["alerts_inserted"] == 0
    assert len(sess.deletes()) == 1
    assert "closed_at IS NULL" in sess.deletes()[0]
