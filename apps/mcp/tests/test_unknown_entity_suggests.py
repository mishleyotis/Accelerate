"""A dead-end lookup must not read as "this client is new".

WHAT IT COST, measured 2026-08-30. A session needed GoEasy's state, called
`get_client_state("goeasy")`, and got:

    {"error": "unknown_entity", "display_id": "goeasy"}

It read that as a client with no package and fired the ASSESSMENT INTAKE
routine — whose whole job is preparing a preflight for a client that has no
package yet. GoEasy's real display_id is `goeasy-ltd`, and it already had
four ingested runs and a completed research package. The firing had to be
interrupted before it pushed a preflight recommending research that was
already done.

The lookup knew. `goeasy` and `goeasy-ltd` share every character of the
first, and `pg_trgm` — installed since migration 0001 and already used by
`memory.py` at this same 0.20 threshold — would have said so for the cost of
one query against a table of a few hundred rows.

WHAT THIS DELIBERATELY DOES NOT DO: resolve the near miss into a match.
`unknown_entity` is still the answer. Guessing which client somebody meant
is the silent inference this system refuses everywhere else, and a wrong
guess here routes an assessment onto the wrong company. The refusal simply
stops being silent about what it saw.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp import bundle                                    # noqa: E402


@pytest.fixture()
def db():
    try:
        import pg8000.dbapi
        conn = pg8000.dbapi.connect(host="localhost", port=5432,
                                    user="postgres", password="local",
                                    database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    tag = uuid.uuid4().hex[:8]
    yield conn, tag
    cur = conn.cursor()
    cur.execute("DELETE FROM entities WHERE display_id LIKE %s", (f"%{tag}%",))
    conn.commit()
    conn.close()


def _entity(conn, display_id, legal_name):
    cur = conn.cursor()
    cur.execute("INSERT INTO entities (display_id, legal_name) "
                "VALUES (%s, %s) RETURNING id", (display_id, legal_name))
    conn.commit()
    return cur.fetchone()[0]


def test_the_goeasy_shape_itself(db):
    """The exact miss: a bare name against a suffixed slug."""
    conn, tag = db
    _entity(conn, f"goeasy-ltd-{tag}", "goeasy Ltd.")
    out = bundle.get_client_state(conn, f"goeasy-{tag}")
    assert out["error"] == "unknown_entity", (
        "a near miss must not be resolved into a match — guessing which "
        "client was meant routes an assessment onto the wrong company")
    ids = [m["display_id"] for m in out["did_you_mean"]]
    assert f"goeasy-ltd-{tag}" in ids, (
        f"the lookup still said nothing about the client one suffix away: "
        f"{out}")


def test_the_hint_names_the_routing_consequence(db):
    """The reader of this error is deciding a ROUTE. The hint has to say
    what a near match means for that decision, or it is decoration."""
    conn, tag = db
    _entity(conn, f"goeasy-ltd-{tag}", "goeasy Ltd.")
    out = bundle.get_client_state(conn, f"goeasy-{tag}")
    assert "synthesis" in out["hint"].lower()
    assert "intake" in out["hint"].lower()


def test_a_genuine_stranger_is_told_it_is_one(db):
    """The other direction, and the one that keeps the suggestion honest: a
    client that really is new must come back with an EMPTY list and a hint
    that says so. A caller who cannot tell "no matches" from "we did not
    look" learns nothing from either."""
    conn, tag = db
    _entity(conn, f"goeasy-ltd-{tag}", "goeasy Ltd.")
    out = bundle.get_client_state(conn, f"zzq-{tag}-unrelated-institution")
    assert out["error"] == "unknown_entity"
    assert out["did_you_mean"] == []
    assert "genuinely has no package" in out["hint"]


def test_the_legal_name_is_matched_too(db):
    """A caller holding the client's real name rather than its slug is the
    same person making the same mistake."""
    conn, tag = db
    _entity(conn, f"acme-fcu-{tag}", f"Acme Federal Credit Union {tag}")
    out = bundle.get_client_state(conn, f"Acme Federal Credit Union {tag}")
    assert [m["display_id"] for m in out["did_you_mean"]] == [f"acme-fcu-{tag}"]


def test_the_matches_are_ordered_by_closeness(db):
    """An unordered list of five makes the caller do the comparison the
    query already did."""
    conn, tag = db
    _entity(conn, f"goeasy-ltd-{tag}", "goeasy Ltd.")
    _entity(conn, f"goodenergy-plc-{tag}", "Good Energy plc")
    out = bundle.get_client_state(conn, f"goeasy-{tag}")
    sims = [m["similarity"] for m in out["did_you_mean"]]
    assert sims == sorted(sims, reverse=True), sims
    assert out["did_you_mean"][0]["display_id"] == f"goeasy-ltd-{tag}"


def test_a_found_entity_is_unchanged(db):
    """The suggestion path must not touch the answer for a client that
    exists — this is an error-path repair, not a shape change."""
    conn, tag = db
    _entity(conn, f"acme-{tag}", f"Acme {tag}")
    out = bundle.get_client_state(conn, f"acme-{tag}")
    assert "error" not in out
    assert "did_you_mean" not in out
