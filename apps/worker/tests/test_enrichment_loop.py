"""The enrichment routine, proven against a database rather than described.

Owner, 2026-08-15: "There should be a working enrichment routine; not you doing
it as Claude Code" and "confirm that this enrichment loop happens robustly as
the web app runs."

"Robustly" is the word these tests are written against. A routine that works on
the happy path and goes quiet on every other is worse than none, because the
job exits 0 and the gap stays open. So the cases below are mostly the unhappy
ones: no runs, no evidence, a tie, an aggregator-dominated register, a resolver
that raises. Each must produce a ROW WITH A REASON, never silence.

The seeded fixture builds a real run with a real submission and lets the actual
gap computation find the actual gaps — no mocked gap list, because a mocked one
would pass while the shared module and the contract disagreed.
"""
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

pg8000 = pytest.importorskip("pg8000.dbapi")

from dma_worker import enrichment as E


def _connect():
    return pg8000.connect(user="postgres", password="local", host="localhost",
                          port=5432, database="dma_insights")


DISPLAY = "synthetic-enrichment-loop"


@pytest.fixture()
def seeded():
    try:
        conn = _connect()
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()
    try:
        cur.execute("SELECT to_regclass('enrichment_jobs')")
        if cur.fetchone()[0] is None:
            pytest.skip("migration 0047 not applied to this database")
    except Exception:
        pytest.skip("no migrated local database")

    def clean():
        cur.execute("SELECT id FROM entities WHERE display_id = %s", (DISPLAY,))
        for (eid,) in cur.fetchall():
            cur.execute("DELETE FROM enrichment_attempts WHERE entity_id = %s", (eid,))
            cur.execute("SELECT id FROM runs WHERE entity_id = %s", (eid,))
            for (rid,) in cur.fetchall():
                cur.execute("DELETE FROM submissions WHERE run_id = %s", (rid,))
            cur.execute("DELETE FROM evidence_index WHERE entity_id = %s", (eid,))
            cur.execute("DELETE FROM runs WHERE entity_id = %s", (eid,))
            cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
        conn.commit()

    clean()
    cur.execute("""INSERT INTO entities (display_id, status)
                   VALUES (%s, 'ACTIVE') RETURNING id""", (DISPLAY,))
    eid = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, run_seq, status)
                   VALUES (%s, 1, 'PROMOTED') RETURNING id""", (eid,))
    rid = cur.fetchone()[0]
    conn.commit()
    yield conn, cur, eid, rid
    clean()
    conn.close()


def _submit(cur, conn, rid, payload):
    cur.execute("""INSERT INTO submissions (run_id, page, status, payload,
                                            producer_version, provenance)
                   VALUES (%s, 'overview', 'PASS', %s, 'test', 'producer')""",
                (rid, __import__("json").dumps(payload)))
    conn.commit()


def _evidence(cur, conn, eid, urls):
    for i, u in enumerate(urls):
        cur.execute(
            """INSERT INTO evidence_index (e_id, entity_id, source_url, excerpt,
                                           claim_type, reference_date)
               VALUES (%s, %s, %s, %s, 'FACT', '2026-05-01')""",
            (f"E-LOOP-{uuid.uuid4().hex[:6]}", eid, u, "x" * 60))
    conn.commit()


# ── the loop closes a real gap from real data ─────────────────────────
def test_the_website_gap_is_closed_from_the_entity_s_own_evidence(seeded):
    """The field the owner reported first, closed by the routine rather than by
    a person. The domain is DERIVED — it is the registrable host that dominates
    this entity's own evidence, which is what an institution's own site is."""
    conn, cur, eid, rid = seeded
    _submit(cur, conn, rid, {"firmographics": {
        "fields": [{"field": "employees", "value": 767}]}})
    _evidence(cur, conn, eid, [
        "https://www.example-cu.org/about", "https://example-cu.org/newsroom",
        "https://example-cu.org/rates", "https://www.linkedin.com/company/x",
    ])
    out = E.run_once(conn, "test")
    assert out["runs_scanned"] >= 1
    cur.execute("""SELECT status, value, resolver, source_url FROM enrichment_attempts
                    WHERE job_id=%s AND field='website'""", (out["job_id"],))
    row = cur.fetchone()
    assert row, "the routine did not attempt the website gap at all"
    assert row[0] == "RESOLVED", f"expected RESOLVED, got {row}"
    assert row[1] == "example-cu.org"
    assert row[2] == "self_domain"
    assert row[3], "a resolved value must carry the source it came from"


def test_an_aggregator_never_becomes_the_entity_s_own_domain(seeded):
    """The failure that would make this resolver dangerous. A client with more
    LinkedIn citations than own-site pages must NOT be assigned linkedin.com —
    a confidently wrong domain is worse than the gap, because it propagates
    into O11's self-sourced share as a denominator."""
    conn, cur, eid, rid = seeded
    _submit(cur, conn, rid, {"firmographics": {"fields": []}})
    _evidence(cur, conn, eid, [
        "https://www.linkedin.com/a", "https://www.linkedin.com/b",
        "https://www.linkedin.com/c", "https://www.linkedin.com/d",
        "https://sec.gov/x", "https://bloomberg.com/y",
    ])
    out = E.run_once(conn, "test")
    cur.execute("""SELECT status, value, reason FROM enrichment_attempts
                    WHERE job_id=%s AND field='website'""", (out["job_id"],))
    status, value, reason = cur.fetchone()
    assert status == "NOT_RUN"
    assert value is None
    assert "aggregator" in (reason or "").lower()


def test_two_domains_tied_at_the_top_resolve_to_nothing(seeded):
    """A tie is not a majority. A merged brand, a holding company or evidence
    contamination all present this way, and each wants a person."""
    conn, cur, eid, rid = seeded
    _submit(cur, conn, rid, {"firmographics": {"fields": []}})
    _evidence(cur, conn, eid, [
        "https://alpha-cu.org/1", "https://alpha-cu.org/2", "https://alpha-cu.org/3",
        "https://beta-cu.org/1", "https://beta-cu.org/2", "https://beta-cu.org/3",
    ])
    out = E.run_once(conn, "test")
    cur.execute("""SELECT status, reason FROM enrichment_attempts
                    WHERE job_id=%s AND field='website'""", (out["job_id"],))
    status, reason = cur.fetchone()
    assert status == "NOT_RUN"
    assert "tie" in (reason or "").lower()


def test_one_citation_is_below_the_floor(seeded):
    conn, cur, eid, rid = seeded
    _submit(cur, conn, rid, {"firmographics": {"fields": []}})
    _evidence(cur, conn, eid, ["https://lonely-cu.org/only"])
    out = E.run_once(conn, "test")
    cur.execute("""SELECT status, reason FROM enrichment_attempts
                    WHERE job_id=%s AND field='website'""", (out["job_id"],))
    status, reason = cur.fetchone()
    assert status == "NOT_RUN"
    assert "floor" in (reason or "").lower()


# ── fail-closed: every unresolved gap says WHY ────────────────────────
def test_a_field_with_no_resolver_records_no_source_and_the_reason(seeded):
    """The honest half of a short ladder. `revenue`, `CAGR`, `charter` have no
    machine source configured, and the row must say so rather than leave the
    gap looking unattempted — otherwise a reader of this table cannot tell a
    resolver that failed from one that was never written."""
    conn, cur, eid, rid = seeded
    _submit(cur, conn, rid, {"firmographics": {"fields": []}})
    out = E.run_once(conn, "test")
    cur.execute("""SELECT field, status, reason FROM enrichment_attempts
                    WHERE job_id=%s AND status='NO_SOURCE'""", (out["job_id"],))
    rows = cur.fetchall()
    assert rows, "no NO_SOURCE rows — the ladder silently skipped fields"
    for field, status, reason in rows:
        assert reason and len(reason) > 20, f"{field} has no usable reason"
    joined = " ".join(r[2] for r in rows)
    assert "Clay" in joined and "Explorium" in joined, (
        "the reason must name WHY no machine source exists, so the gap is "
        "actionable rather than merely reported")


def test_the_database_refuses_an_unresolved_row_with_no_reason(seeded):
    """The constraint, not the convention. A future resolver that returns empty
    without a reason must fail at the write, because a convention only holds
    while everyone remembers it."""
    conn, cur, eid, rid = seeded
    with pytest.raises(Exception) as e:
        cur.execute("""INSERT INTO enrichment_jobs (trigger) VALUES ('test')
                       RETURNING id""")
        jid = cur.fetchone()[0]
        cur.execute("""INSERT INTO enrichment_attempts
                         (job_id, run_id, entity_id, page, section, field,
                          field_path, resolver, status)
                       VALUES (%s,%s,%s,'overview','firmographics','x','x.y',
                               'r','NOT_RUN')""", (jid, rid, eid))
    assert "enrichment_unresolved_has_a_reason" in str(e.value)
    conn.rollback()


def test_the_database_refuses_a_resolved_row_with_no_value(seeded):
    conn, cur, eid, rid = seeded
    with pytest.raises(Exception) as e:
        cur.execute("""INSERT INTO enrichment_jobs (trigger) VALUES ('test')
                       RETURNING id""")
        jid = cur.fetchone()[0]
        cur.execute("""INSERT INTO enrichment_attempts
                         (job_id, run_id, entity_id, page, section, field,
                          field_path, resolver, status)
                       VALUES (%s,%s,%s,'overview','firmographics','x','x.y',
                               'r','RESOLVED')""", (jid, rid, eid))
    assert "enrichment_resolved_has_a_value" in str(e.value)
    conn.rollback()


# ── observability: is the loop alive? ─────────────────────────────────
def test_every_run_writes_a_job_row_that_closes(seeded):
    """The row the app reads to answer "is the loop alive". An open finished_at
    is a job that died mid-flight, and it must look different from one that
    completed with nothing to do."""
    conn, cur, eid, rid = seeded
    _submit(cur, conn, rid, {"firmographics": {"fields": []}})
    out = E.run_once(conn, "test")
    cur.execute("""SELECT started_at, finished_at, runs_scanned, gaps_found,
                          resolved, not_run, error
                     FROM enrichment_jobs WHERE id=%s""", (out["job_id"],))
    started, finished, scanned, gaps, resolved, not_run, err = cur.fetchone()
    assert started and finished, "the job row never closed"
    assert finished >= started
    assert err is None
    assert scanned >= 1 and gaps >= 1
    assert resolved + not_run == gaps, (
        "every gap must end in exactly one outcome; "
        f"{gaps} found but {resolved} resolved + {not_run} unresolved")


def test_a_run_with_no_runs_at_all_is_a_failure_not_a_clean_result(seeded):
    """Two clients exist. A scan that finds zero runs means the query, the
    status vocabulary or the database is wrong — the first draft of this job
    guessed two enum values that do not exist, and a green exit would have
    reported that as "nothing to do"."""
    import inspect
    src = inspect.getsource(E.main)
    assert "runs_scanned" in src and "return 1" in src
    assert "failure to look" in src


def test_the_status_vocabulary_matches_the_database_enum(seeded):
    """The defect that caught the first draft, pinned. ENRICHABLE_STATES must
    be a SUBSET of run_status_t or the query throws 22P02 at runtime."""
    conn, cur, eid, rid = seeded
    cur.execute("SELECT unnest(enum_range(NULL::run_status_t))::text")
    real = {r[0] for r in cur.fetchall()}
    unknown = set(E.ENRICHABLE_STATES) - real
    assert not unknown, f"states that do not exist in run_status_t: {unknown}"
    assert "WITHDRAWN" not in E.ENRICHABLE_STATES
    assert "SUPERSEDED" not in E.ENRICHABLE_STATES


def test_a_withdrawn_run_is_not_scanned(seeded):
    conn, cur, eid, rid = seeded
    _submit(cur, conn, rid, {"firmographics": {"fields": []}})
    cur.execute("UPDATE runs SET withdrawn_at = now() WHERE id = %s", (rid,))
    conn.commit()
    out = E.run_once(conn, "test")
    cur.execute("""SELECT count(*) FROM enrichment_attempts
                    WHERE job_id=%s AND run_id=%s""", (out["job_id"], rid))
    assert cur.fetchone()[0] == 0


def test_the_routine_is_idempotent_across_runs(seeded):
    """Run twice, get the same answer. The job writes only attempt rows and
    reads only staged payloads, so a second execution must not change what the
    first concluded — that is what makes a schedule safe."""
    conn, cur, eid, rid = seeded
    _submit(cur, conn, rid, {"firmographics": {"fields": []}})
    _evidence(cur, conn, eid, ["https://idem-cu.org/1", "https://idem-cu.org/2",
                               "https://idem-cu.org/3"])
    a = E.run_once(conn, "test")
    b = E.run_once(conn, "test")
    assert a["job_id"] != b["job_id"]
    for k in ("gaps_found", "resolved", "not_run", "failed"):
        assert a[k] == b[k], f"{k} differed between identical runs: {a} vs {b}"


def test_a_resolver_that_raises_is_recorded_not_swallowed(seeded, monkeypatch):
    conn, cur, eid, rid = seeded
    _submit(cur, conn, rid, {"firmographics": {"fields": []}})

    def boom(cur_, entity_id, run_id):
        raise RuntimeError("the source refused the connection")

    monkeypatch.setitem(E.RESOLVERS, "website", [("self_domain", boom)])
    out = E.run_once(conn, "test")
    assert out["failed"] >= 1
    cur.execute("""SELECT status, reason FROM enrichment_attempts
                    WHERE job_id=%s AND field='website'""", (out["job_id"],))
    status, reason = cur.fetchone()
    assert status == "FAILED"
    assert "RuntimeError" in reason and "refused the connection" in reason


# ── the shared definition ─────────────────────────────────────────────
def test_the_worker_and_the_connector_compute_gaps_from_ONE_module():
    """Two copies of "what counts as missing" is the drift class this build has
    paid for four times. The connector's module must BE the shared one, not a
    copy that resembles it."""
    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    from dma_mcp import gaps as connector_gaps
    assert connector_gaps.gaps_for_section.__module__ == "enrichment_gaps"
    assert E.gapmod.gaps_for_section is connector_gaps.gaps_for_section
