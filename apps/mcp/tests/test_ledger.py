"""The enrichment ledger, against a real schema.

The pattern it closes, reported three rounds running: "the work was done but
it is not showing". An enrichment ran and the surface a reader opens did not
have it, and nothing in the system held both halves of that sentence.

These run against a migrated local database and skip without one, like the
other DB-backed tests here. What they can assert without a database — the
vocabulary agreeing with the migration's CHECK constraint, and the summary
arithmetic — runs everywhere.
"""
import re
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
from dma_mcp import ledger  # noqa: E402

MIGRATION = (ROOT / "migrations" / "versions"
             / "0051_enrichment_ledger_and_promotion_state.py")


# ── No database needed ─────────────────────────────────────────────────

def test_the_vocabulary_matches_the_check_constraint():
    """The module's FACETS and the migration's CHECK are two copies of one
    list. A facet added to one and not the other is either a write that the
    database refuses or a state nobody watches."""
    src = MIGRATION.read_text()
    m = re.search(r'FACETS = \(([^)]*)\)', src, re.S)
    assert m, "the migration no longer declares FACETS"
    in_migration = tuple(re.findall(r'"([a-z_]+)"', m.group(1)))
    assert in_migration == ledger.FACETS, (in_migration, ledger.FACETS)


def test_every_facet_names_the_section_that_carries_it():
    """A facet with no section cannot have its promotion recorded, so it
    would sit at `never_enriched` forever and block completion for ever."""
    assert set(ledger.FACET_SECTIONS) == set(ledger.FACETS)


def test_an_unknown_facet_is_refused_with_the_vocabulary():
    with pytest.raises(ledger.LedgerError) as e:
        ledger._facet("leadershp")
    assert "leadership" in str(e.value), "the refusal must name the real ones"


@pytest.mark.parametrize("state,blocking", [
    ("current", False),
    ("enriched_not_promoted", True),
    ("never_enriched", True),
])
def test_which_states_stop_a_client_being_done(state, blocking):
    rows = [{"facet": "leadership", "state": state,
             "enrichment_version": 1, "promoted_version": 1,
             "enriched_at": None, "promoted_at": None}]
    out = ledger.summary(rows)
    assert out["done"] is (not blocking)
    assert bool(out["blocking"]) is blocking
    if blocking:
        assert out["reason"], "a blocked client must be told why"


def test_the_reason_separates_the_two_jobs():
    """Run it, versus promote it. Collapsing them into one boolean sends an
    operator after the wrong work."""
    rows = [
        {"facet": "leadership", "state": "enriched_not_promoted",
         "enrichment_version": 3, "promoted_version": 1,
         "enriched_at": None, "promoted_at": None},
        {"facet": "peer_scores", "state": "never_enriched",
         "enrichment_version": None, "promoted_version": None,
         "enriched_at": None, "promoted_at": None},
    ]
    reason = ledger.summary(rows)["reason"]
    assert "enriched and not promoted (leadership)" in reason
    assert "never enriched (peer_scores)" in reason


def test_the_worst_state_sorts_first():
    rows = ledger.summary([
        {"facet": "a", "state": "current", "enrichment_version": 1,
         "promoted_version": 1, "enriched_at": None, "promoted_at": None},
        {"facet": "b", "state": "never_enriched", "enrichment_version": None,
         "promoted_version": None, "enriched_at": None, "promoted_at": None},
    ])["facets"]
    assert [r["facet"] for r in rows] == ["b", "a"], \
        "an operator reads the top of the list; the work belongs there"


# ── Against the migrated schema ────────────────────────────────────────

@pytest.fixture()
def db():
    try:
        import pg8000.dbapi
        conn = pg8000.dbapi.connect(host="localhost", port=5432, user="postgres",
                                    password="local", database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()
    eid = uuid.uuid4()
    cur.execute("""INSERT INTO entities (id, display_id, legal_name, status)
                   VALUES (%s,%s,%s,'ACTIVE')""",
                (eid, f"ledger-test-{eid.hex[:8]}", "Ledger Test Entity"))
    conn.commit()
    yield conn, cur, eid
    cur.execute("DELETE FROM facet_promotion_state WHERE entity_id = %s", (eid,))
    cur.execute("DELETE FROM enrichment_ledger WHERE entity_id = %s", (eid,))
    cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
    conn.commit()
    conn.close()


def _state(cur, eid, facet):
    return next(r["state"] for r in ledger.drift(cur, eid) if r["facet"] == facet)


def test_a_facet_nobody_touched_is_never_enriched(db):
    conn, cur, eid = db
    rows = ledger.drift(cur, eid)
    assert len(rows) == len(ledger.FACETS), "every facet is accounted for"
    assert {r["state"] for r in rows} == {"never_enriched"}
    assert ledger.summary(rows)["done"] is False


def test_the_shape_that_produced_three_rounds_of_defects(db):
    """Enriched, not promoted. The whole reason this table exists."""
    conn, cur, eid = db
    v = ledger.record_enrichment(cur, eid, "leadership", "clay",
                                 account="dma@zennify.com", rows_written=3)
    conn.commit()
    assert v == 1
    assert _state(cur, eid, "leadership") == "enriched_not_promoted"

    ledger.record_promotion(cur, eid, "leadership")
    conn.commit()
    assert _state(cur, eid, "leadership") == "current"

    # Enriched again, and the surface goes stale the moment it happens.
    assert ledger.record_enrichment(cur, eid, "leadership", "clay") == 2
    conn.commit()
    assert _state(cur, eid, "leadership") == "enriched_not_promoted"


def test_the_version_is_allocated_by_the_database(db):
    """A caller cannot mint one that collides or one that goes backwards."""
    conn, cur, eid = db
    versions = [ledger.record_enrichment(cur, eid, "techstack", "explorium")
                for _ in range(3)]
    conn.commit()
    assert versions == [1, 2, 3]


def test_promotion_state_never_moves_backwards(db):
    """Re-promoting a retained page must not report a facet as freshly
    promoted at an older version than one already served."""
    conn, cur, eid = db
    ledger.record_enrichment(cur, eid, "sentiment", "clay")
    ledger.record_enrichment(cur, eid, "sentiment", "clay")
    ledger.record_promotion(cur, eid, "sentiment")            # -> 2
    conn.commit()
    ledger.record_promotion(cur, eid, "sentiment", version=1)  # older
    conn.commit()
    cur.execute("""SELECT promoted_version FROM facet_promotion_state
                    WHERE entity_id = %s AND facet = 'sentiment'""", (eid,))
    assert cur.fetchone()[0] == 2


def test_a_facet_promoted_before_it_was_ever_enriched_is_still_never_enriched(db):
    """The surface is live and carries whatever the package held. That is not
    the same as having been enriched, and calling it done would hide exactly
    the work this ledger exists to surface."""
    conn, cur, eid = db
    ledger.record_promotion(cur, eid, "why_now")
    conn.commit()
    assert _state(cur, eid, "why_now") == "never_enriched"


def test_promotion_is_recorded_from_the_sections_a_promote_wrote(db):
    conn, cur, eid = db
    for facet in ("leadership", "techstack", "peer_scores"):
        ledger.record_enrichment(cur, eid, facet, "test")
    done = ledger.record_promotion_for_sections(
        cur, eid, [("overview", "leadership"), ("techstack", "techstack"),
                   ("overview", "scores")])
    conn.commit()
    assert done == ["leadership", "techstack"], \
        "only facets whose section was actually written are recorded"
    assert _state(cur, eid, "peer_scores") == "enriched_not_promoted"


def test_the_source_is_required(db):
    conn, cur, eid = db
    with pytest.raises(ledger.LedgerError) as e:
        ledger.record_enrichment(cur, eid, "leadership", "")
    conn.rollback()
    assert "run it again how" in str(e.value)


def test_the_account_is_recorded_because_it_changed_the_result_once(db):
    """The same technographic scan returned empty twice under one account and
    sixty technologies under another. With no record of which, the two runs
    were indistinguishable afterwards."""
    conn, cur, eid = db
    ledger.record_enrichment(cur, eid, "techstack", "explorium",
                             account="account-a", rows_written=0)
    ledger.record_enrichment(cur, eid, "techstack", "explorium",
                             account="account-b", rows_written=60)
    conn.commit()
    cur.execute("""SELECT account, rows_written FROM enrichment_ledger
                    WHERE entity_id = %s AND facet = 'techstack'
                    ORDER BY enrichment_version""", (eid,))
    # pg8000 hands back its own sequence types; the shape is what matters.
    assert [list(r) for r in cur.fetchall()] == [["account-a", 0],
                                                 ["account-b", 60]]
