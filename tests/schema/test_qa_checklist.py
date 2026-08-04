"""Backend Schema §10 QA checklist, implemented as tests (stage 0.3 DoD).

Runs against a migrated database (alembic upgrade head) reachable via
LOCAL_DATABASE_URL, with the docker-compose / pg-init parity users present
so role-boundary assertions behave exactly as they will on Cloud SQL.
"""
import os
import threading
import uuid

import pg8000.dbapi
import pytest

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql+pg8000://postgres:local@localhost:5432/dma_insights")


def _connect(user="postgres", password="local"):
    host = DSN.split("@")[1].split(":")[0]
    return pg8000.dbapi.connect(
        user=user, password=password, host=host, port=5432, database="dma_insights"
    )


@pytest.fixture(scope="module")
def db():
    conn = _connect()
    yield conn
    conn.rollback()
    conn.close()


def q(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall() if cur.description else None


# The §06 complete map — 33 dedicated serving tables (heatmap.evidence
# reuses evidence_index and is deliberately absent here).
SERVING_TABLES = [
    "overview_scores", "overview_firmographics", "overview_why_now",
    "overview_exec_summary", "overview_opportunity", "overview_findings",
    "overview_leadership", "overview_financial_series", "overview_sentiment",
    "overview_ceilings", "overview_evidence_coverage", "overview_thought_leadership",
    "insight_cards", "insights_landscape",
    "heatmap_workbook_scores", "heatmap_focus_areas", "heatmap_cell_evidence",
    "heatmap_value_chain", "heatmap_alerts", "heatmap_safeguard_gates",
    "heatmap_evidence_age", "heatmap_cohort_patterns",
    "platform_story", "platform_recommendations", "platform_starters",
    "platform_roadmap", "platform_stairstep",
    "context_timeline", "context_issue_register", "context_regulatory_standing",
    "context_sentiment", "context_acquisitions",
    "techstack_items",
]
ENVELOPE = ["run_id", "entity_id", "promoted_at", "producer_version", "provenance",
            "e_ids", "internal_only", "empty_state", "r_layer", "narrative_thread",
            "produced_at"]


def test_table_count_is_89(db):
    (n,) = q(db, "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")[0]
    assert n == 89


def test_serving_map_reconciles(db):
    rows = q(db, """SELECT tablename FROM pg_tables WHERE schemaname='public'""")
    present = {r[0] for r in rows}
    missing = [t for t in SERVING_TABLES if t not in present]
    assert not missing, f"serving tables absent: {missing}"
    assert len(SERVING_TABLES) == 33


def test_every_serving_table_carries_the_envelope(db):
    for t in SERVING_TABLES:
        cols = {r[0] for r in q(db, "SELECT column_name FROM information_schema.columns WHERE table_name=%s", (t,))}
        missing = [c for c in ENVELOPE if c not in cols]
        assert not missing, f"{t} missing envelope columns: {missing}"


def test_producer_version_and_promoted_at_not_null(db):
    for t in SERVING_TABLES:
        rows = dict(q(db, """SELECT column_name, is_nullable FROM information_schema.columns
                             WHERE table_name=%s AND column_name IN ('producer_version','promoted_at')""", (t,)))
        assert rows.get("producer_version") == "NO", t
        assert rows.get("promoted_at") == "NO", t


def test_every_generated_column_is_stored_not_virtual(db):
    rows = q(db, """SELECT c.relname, a.attname, a.attgenerated
                    FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public' AND a.attgenerated <> ''""")
    assert rows, "expected generated columns"
    not_stored = [(r[0], r[1]) for r in rows if r[2] != "s"]
    assert not_stored == []
    assert len(rows) >= 16


def test_api_role_denied_on_staging(db):
    api = _connect(user="dmai-api@digital-maturity-assessor.iam")
    try:
        with pytest.raises(pg8000.dbapi.DatabaseError) as e:
            q(api, "SELECT * FROM submissions LIMIT 1")
        assert "42501" in str(e.value)  # insufficient_privilege
    finally:
        api.close()


def test_out_of_range_ers_rejected(db):
    db.rollback()
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s) RETURNING id", (eid,))
    with pytest.raises(pg8000.dbapi.DatabaseError) as e:
        q(db, """INSERT INTO evidence_index (e_id, entity_id, source_url, excerpt, claim_type, reference_date, ers)
                 SELECT 'E-QA1', id, 'https://x.test/a', repeat('x',60), 'FACT', '2026-05-01', 0.78
                 FROM entities WHERE display_id=%s""", (eid,))
    assert "ers_bounded" in str(e.value)
    db.rollback()


def test_null_published_date_yields_unverified_never_current(db):
    db.rollback()
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
    q(db, """INSERT INTO evidence_index (e_id, entity_id, source_url, excerpt, claim_type, reference_date)
             SELECT 'E-QA2', id, 'https://x.test/b', repeat('y',60), 'FACT', '2026-05-01'
             FROM entities WHERE display_id=%s""", (eid,))
    (age, band) = q(db, "SELECT age_months, recency_band FROM evidence_index WHERE e_id='E-QA2'")[0]
    assert age is None and band == "UNVERIFIED"
    db.rollback()


def test_undated_age_row_bands_undated_and_status_follows(db):
    db.rollback()
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
    q(db, """INSERT INTO runs (entity_id, run_seq, status) SELECT id, 1, 'PROMOTED' FROM entities WHERE display_id=%s""", (eid,))
    q(db, """INSERT INTO heatmap_evidence_age (run_id, reference_date, title, promoted_at, producer_version)
             SELECT r.id, '2026-05-01', 't', now(), 'qa' FROM runs r
             JOIN entities e ON e.id=r.entity_id WHERE e.display_id=%s""", (eid,))
    (age, band, status) = q(db, """SELECT age_months, band, status FROM heatmap_evidence_age
                                   WHERE producer_version='qa'""")[0]
    assert age is None and band == "undated" and status == "UNDATED"
    db.rollback()


def test_band_boundaries_strict_less_than_on_raw_score(db):
    db.rollback()
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
    q(db, "INSERT INTO runs (entity_id, run_seq, status) SELECT id, 1, 'PROMOTED' FROM entities WHERE display_id=%s", (eid,))
    q(db, """INSERT INTO heatmap_workbook_scores (run_id, subcap_id, score, promoted_at, producer_version)
             SELECT r.id, 'S'||s.i, s.v, now(), 'qa'
             FROM runs r JOIN entities e ON e.id=r.entity_id,
                  (VALUES (1,1.99),(2,2.00),(3,2.97),(4,3.00),(5,3.99),(6,4.00),(7,NULL::numeric)) s(i,v)
             WHERE e.display_id=%s""", (eid,))
    got = dict(q(db, "SELECT score, band FROM heatmap_workbook_scores WHERE producer_version='qa'"))
    from decimal import Decimal as D
    assert got[D("1.99")] == "Activating" and got[D("2.00")] == "Building"
    assert got[D("2.97")] == "Building" and got[D("3.00")] == "Competing"
    assert got[D("3.99")] == "Competing" and got[D("4.00")] == "Differentiating"
    assert got[None] is None
    db.rollback()


def test_active_run_partial_unique_holds_under_concurrent_insert(db):
    db.rollback()
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
    db.commit()
    (entity_id,) = q(db, "SELECT id FROM entities WHERE display_id=%s", (eid,))[0]
    results = {}

    def insert_active(tag):
        c = _connect()
        try:
            q(c, "INSERT INTO runs (entity_id, run_seq, is_active, status) VALUES (%s, 1, TRUE, 'PROMOTED')", (str(entity_id),))
            c.commit()
            results[tag] = "ok"
        except pg8000.dbapi.DatabaseError as e:
            results[tag] = "unique" if "runs_active_uq" in str(e) else f"other: {e}"
        finally:
            c.close()

    t1 = threading.Thread(target=insert_active, args=("a",))
    t2 = threading.Thread(target=insert_active, args=("b",))
    t1.start(); t2.start(); t1.join(15); t2.join(15)
    assert sorted(results.values()) == ["ok", "unique"], results
    q(db, "DELETE FROM runs WHERE entity_id=%s", (str(entity_id),))
    q(db, "DELETE FROM entities WHERE id=%s", (str(entity_id),))
    db.commit()


def test_live_submission_partial_unique(db):
    db.rollback()
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
    q(db, "INSERT INTO runs (entity_id, run_seq, status) SELECT id, 1, 'INGESTED' FROM entities WHERE display_id=%s", (eid,))
    q(db, """INSERT INTO submissions (run_id, page, status)
             SELECT r.id, 'overview', 'PASS' FROM runs r JOIN entities e ON e.id=r.entity_id WHERE e.display_id=%s""", (eid,))
    with pytest.raises(pg8000.dbapi.DatabaseError) as e:
        q(db, """INSERT INTO submissions (run_id, page, status)
                 SELECT r.id, 'overview', 'FAIL' FROM runs r JOIN entities e ON e.id=r.entity_id WHERE e.display_id=%s""", (eid,))
    assert "submissions_live_uq" in str(e.value)
    db.rollback()


def test_band_enum_has_no_fifth_value(db):
    rows = q(db, """SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid
                    WHERE t.typname='band_t' ORDER BY enumsortorder""")
    assert [r[0] for r in rows] == ["Activating", "Building", "Competing", "Differentiating"]
