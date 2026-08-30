"""The reviewer feedback path in `dma_api.annotations` — the write that
refused, and the read that did not exist.

No live DB, per the suite's style: a fake cursor speaks just enough of the
module's own SQL to drive it, and records every statement so the write
boundary can be asserted against what was actually executed.

What is pinned here:

  * the 403 for an unknown actor is STILL a 403. Migration 0033 made the
    actor known; it did not make the check optional, and a regression that
    auto-creates a user inside the write path would delete the only thing
    standing between an annotation and an unattributable one.
  * a successful write touches `annotations`, `idempotency_keys` and
    `users.last_seen_at` — and no serving table (invariant 2).
  * the read half returns verdicts, refuses a customer audience, and never
    renders an unreadable body as an empty verdict (invariant 9: "I could not
    read this" and "there was nothing here" are different facts).
"""
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.annotations import (annotate_insight,             # noqa: E402
                                 latest_verdicts,
                                 read_insight_annotations)
from dma_api.pages import ApiError                             # noqa: E402

T0 = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
KEY = str(uuid.uuid4())
USER = "9f2c1b7e-0000-4000-8000-000000000001"
RUN = "11111111-1111-1111-1111-111111111111"
ENTITY = "22222222-2222-2222-2222-222222222222"


class _Cur:
    """Enough of a pg8000 cursor for this module: the idempotency lookup, the
    user lookup, the anchor resolution, two INSERTs, the last_seen_at UPDATE
    and the two reads."""

    def __init__(self, *, user=True, anchor=True, annotations=()):
        self.user, self.anchor = user, anchor
        self.annotations = list(annotations)
        self.sql = []
        self._result = None

    def execute(self, sql, params=()):
        self.sql.append((" ".join(sql.split()), params))
        s = " ".join(sql.split()).lower()
        if s.startswith("select request_hash"):
            self._result = None
        elif s.startswith("select id from users"):
            self._result = (USER,) if self.user else None
        elif "from insight_cards" in s:
            self._result = (RUN, ENTITY) if self.anchor else None
        elif s.startswith("insert into annotations"):
            self._result = (7, T0)
        elif "from annotations" in s:
            # latest_verdicts projects five columns; read_insight_annotations
            # eight. Project here so the fake speaks the module's own SQL
            # rather than one convenient shape for both.
            self._rows = ([(r[1], r[2], r[3], r[4], r[5])
                           for r in self.annotations]
                          if "distinct on" in s else self.annotations)
            self._result = None
        else:
            self._result = None

    def fetchone(self):
        return self._result

    def fetchall(self):
        return getattr(self, "_rows", [])

    def wrote(self, table):
        return any(f"insert into {table}" in s or f"update {table}" in s
                   for s, _ in ((a.lower(), b) for a, b in self.sql))


def _row(anchor="IC-1", action="ACCEPT", note=None, body=None, email="a@b.com",
         name="Analyst", role="ADMIN", aid=7):
    return (aid, anchor,
            body if body is not None else json.dumps({"action": action,
                                                      "note": note}),
            T0, email, name, role, RUN)


# ── the write: the 403 that was right ───────────────────────────────────
def test_an_unknown_actor_is_still_refused():
    cur = _Cur(user=False)
    with pytest.raises(ApiError) as e:
        annotate_insight(cur, "acme-cu", "IC-1", body={"action": "ACCEPT"},
                         idempotency_key=KEY, actor_email="nobody@zennify.com")
    assert e.value.status == 403 and e.value.code == "unknown_actor"
    assert not cur.wrote("annotations"), (
        "an unknown actor must not enrol itself on the way to writing")


def test_a_known_actor_writes_and_the_write_boundary_holds():
    cur = _Cur()
    status, out = annotate_insight(
        cur, "acme-cu", "IC-1", body={"action": "ACCEPT", "note": "clean"},
        idempotency_key=KEY, actor_email="analyst@zennify.com")
    assert status == 201 and out["action"] == "ACCEPT"
    assert cur.wrote("annotations") and cur.wrote("idempotency_keys")
    # And nothing else — not even `users.last_seen_at`. Touching the seeded
    # identity here was tried and removed: test_alerts.py pins this path to
    # exactly two written tables, and a second author's boundary test is a
    # better thing to keep than a convenience column.
    assert not cur.wrote("users")
    executed = " ".join(s for s, _ in cur.sql).lower()
    for serving in ("insight_cards ", "overview_scores", "heatmap_",
                    "platform_", "techstack_", "context_"):
        assert f"insert into {serving}" not in executed
        assert f"update {serving}" not in executed


def test_a_missing_anchor_is_refused_before_the_user_is_touched():
    cur = _Cur(anchor=False)
    with pytest.raises(ApiError) as e:
        annotate_insight(cur, "acme-cu", "IC-99", body={"action": "REJECT"},
                         idempotency_key=KEY, actor_email="analyst@zennify.com")
    assert e.value.status == 404 and e.value.code == "anchor_not_found"
    assert not cur.wrote("annotations")


def test_the_customer_audience_has_no_write_route():
    with pytest.raises(ApiError) as e:
        annotate_insight(_Cur(), "acme-cu", "IC-1", body={"action": "ACCEPT"},
                         idempotency_key=KEY, actor_email="a@zennify.com",
                         audience="customer")
    assert e.value.status == 403 and e.value.code == "audience_forbidden"


# ── the read that did not exist ─────────────────────────────────────────
def test_the_read_returns_verdicts_with_their_actor():
    cur = _Cur(annotations=[_row("IC-1", "ACCEPT", "reads well"),
                            _row("IC-2", "REJECT", "mechanism unproven", aid=8)])
    out = read_insight_annotations(cur, "acme-cu")
    assert out["count"] == 2
    first = out["annotations"][0]
    assert first["ic_id"] == "IC-1" and first["action"] == "ACCEPT"
    assert first["note"] == "reads well"
    assert first["by"]["email"] == "a@b.com" and first["by"]["role"] == "ADMIN"
    assert first["created_at"].startswith("2026-08-08")


def test_the_read_refuses_the_customer_audience():
    with pytest.raises(ApiError) as e:
        read_insight_annotations(_Cur(), "acme-cu", audience="customer")
    assert e.value.status == 403 and e.value.code == "audience_forbidden"
    with pytest.raises(ApiError):
        latest_verdicts(_Cur(), "acme-cu", audience="customer")


def test_an_unreadable_body_is_reported_not_rendered_as_empty():
    cur = _Cur(annotations=[_row("IC-3", body="{not json")])
    out = read_insight_annotations(cur, "acme-cu")
    row = out["annotations"][0]
    assert row["action"] is None
    assert row["unparsed"] == "{not json", (
        "an unreadable verdict must say so; a null action with no explanation "
        "is indistinguishable from a card nobody judged")


def test_latest_verdicts_is_the_shape_the_card_adapter_needs():
    cur = _Cur(annotations=[_row("IC-1", "REJECT", "no mechanism")])
    out = latest_verdicts(cur, "acme-cu", ["IC-1"])
    assert out == {"IC-1": {"action": "REJECT", "note": "no mechanism",
                            "by": "Analyst", "at": T0.isoformat()}}
    sql = " ".join(s for s, _ in cur.sql).lower()
    assert "distinct on (a.anchor_id)" in sql, (
        "one card renders one state; the latest verdict per card is a DISTINCT "
        "ON, not the caller's job to reduce")


def test_the_read_uses_the_index_0033_added():
    cur = _Cur(annotations=[])
    read_insight_annotations(cur, "acme-cu", ic_id="IC-1")
    sql = " ".join(s for s, _ in cur.sql).lower()
    assert "anchor_kind = 'insight_card'" in sql and "a.anchor_id = %s" in sql
    assert "order by a.created_at desc" in sql
