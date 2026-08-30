"""The findings memory against a real database (skips without one).

The round trip the whole store exists for:

    record -> the same defect again is ONE finding with two sightings
           -> search finds it both lexically and by trigram
           -> it cannot be closed without naming a refinement
           -> it is closed, and then it comes back
           -> the refinement that did not hold is named, and `held` is false

Everything a caller could be tempted to store — sighting counts, recurrence
counts, whether a fix held — is computed by a view here, and these tests read
it back rather than trusting the writer (invariant 8).

Run with a migrated local database:
    LOCAL_DATABASE_URL=postgresql://postgres:local@localhost:5432/dma_insights
"""
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi                                            # noqa: E402

from dma_mcp import memory as mem                              # noqa: E402

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"
MARK = "pytest-memory-store"


def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def store():
    try:
        conn = _connect("dmai-mcp@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()
    cur.execute("SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'memory_findings'")
    if cur.fetchone() is None:
        pytest.skip("migrations 0034/0035 not applied to this database")

    def clean():
        cur.execute("""DELETE FROM memory_finding_sightings
                        WHERE finding_id IN (SELECT finding_id FROM
                              memory_findings WHERE raised_by = %s)""", (MARK,))
        cur.execute("""DELETE FROM memory_refinement_findings
                        WHERE finding_id IN (SELECT finding_id FROM
                              memory_findings WHERE raised_by = %s)""", (MARK,))
        cur.execute("UPDATE memory_findings SET status = 'OPEN', "
                    "resolved_by = NULL, resolved_at = NULL WHERE raised_by = %s",
                    (MARK,))
        cur.execute("DELETE FROM memory_findings WHERE raised_by = %s", (MARK,))
        cur.execute("DELETE FROM memory_refinements WHERE applied_by = %s",
                    (MARK,))
        admin.commit()

    clean()
    yield conn
    conn.rollback()
    clean()
    conn.close()
    admin.close()


def _finding(**kw):
    base = {
        "title": f"Synthetic store probe {uuid.uuid4().hex[:8]}",
        "observed": "A synthetic defect recorded by the test suite.",
        "measurement": "python3 -m pytest apps/mcp/tests/test_memory_store.py "
                       "-k round_trip, one run, one row expected",
        "component": "mcp",
        "file_path": "apps/mcp/dma_mcp/memory.py",
        "defect_class": "WRITE_PATH_WITH_NO_READ_PATH",
        "severity": "MINOR",
        "raised_by_kind": "TEST",
        "raised_by": MARK,
    }
    base.update(kw)
    return base


# ── the refusals are the contract ───────────────────────────────────────
def test_a_finding_that_cannot_say_how_it_was_measured_is_refused(store):
    out = mem.record_finding(store, _finding(measurement="it broke"))
    assert out["finding_id"] is None
    assert any("measurement" in e for e in out["errors"])
    assert any("opinion" in e for e in out["errors"])


def test_an_unknown_class_is_refused_with_the_known_ones(store):
    out = mem.record_finding(store, _finding(defect_class="VIBES"))
    assert out["finding_id"] is None
    joined = " ".join(out["errors"])
    assert "not a known class" in joined and "new_class" in joined


def test_a_class_may_be_invented_only_by_defining_it(store):
    cls = f"SYNTHETIC_{uuid.uuid4().hex[:6].upper()}"
    bad = mem.record_finding(store, _finding(defect_class=cls,
                                             new_class={"title": "t"}))
    assert bad["finding_id"] is None
    good = mem.record_finding(store, _finding(
        defect_class=cls,
        new_class={"title": "t", "description": "d", "tell": "how it shows",
                   "probe": "how to check"}))
    assert good["finding_id"] and not good["errors"]
    cur = store.cursor()
    cur.execute("SELECT tell, probe FROM memory_defect_classes WHERE class_id = %s",
                (cls,))
    assert list(cur.fetchone()) == ["how it shows", "how to check"]
    cur.execute("DELETE FROM memory_findings WHERE finding_id = %s",
                (good["finding_id"],))
    cur.execute("DELETE FROM memory_defect_classes WHERE class_id = %s", (cls,))
    store.commit()


# ── one defect, many reports ────────────────────────────────────────────
def test_the_same_defect_three_times_is_one_finding_with_three_sightings(store):
    f = _finding()
    first = mem.record_finding(store, f)
    assert first["deduped"] is False and first["finding_id"].startswith("MEM-")
    ids = set()
    for who in ("agent:a", "agent:b"):
        again = mem.record_finding(store, dict(f, raised_by=MARK,
                                               note=f"seen by {who}"))
        assert again["deduped"] is True
        ids.add(again["finding_id"])
    assert ids == {first["finding_id"]}
    detail = mem.get_finding(store, first["finding_id"])
    assert detail["sighting_count"] == 3
    assert detail["recurrence_count"] == 0


def test_a_sighting_with_the_same_source_ref_does_not_duplicate(store):
    f = _finding(source_ref="annotation:4242")
    a = mem.record_finding(store, f)
    b = mem.record_finding(store, f)
    assert a["finding_id"] == b["finding_id"]
    assert mem.get_finding(store, a["finding_id"])["sighting_count"] == 1


# ── search answers both ways, and says which ran ────────────────────────
def test_search_names_every_path_it_ran_and_every_path_it_skipped(store):
    f = _finding(title=f"Trigram probe zzqq {uuid.uuid4().hex[:6]}")
    out = mem.record_finding(store, f)
    hit = mem.search_findings(store, "trigram probe zzqq", mode="lexical")
    assert "lexical" in hit["paths_run"]
    assert any(r["finding_id"] == out["finding_id"] for r in hit["results"])
    # no encoder in the test process: semantic must be SKIPPED WITH A REASON,
    # never silently absent
    auto = mem.search_findings(store, "trigram probe zzqq")
    assert "semantic" in auto["paths_skipped"]
    assert "encoder" in auto["paths_skipped"]["semantic"]


def test_fuzzy_finds_what_shares_no_lexeme(store):
    mem.record_finding(store, _finding(title="Promotion discarded the anchor"))
    out = mem.search_findings(store, "promotoin discarded", mode="fuzzy")
    assert out["paths_run"] == ["trigram"]


# ── closing requires the change that closed it ──────────────────────────
def test_a_finding_cannot_be_closed_without_a_refinement(store):
    f = mem.record_finding(store, _finding())
    out = mem.resolve_finding(store, f["finding_id"], "")
    assert out["errors"] and "refinement_id" in out["errors"][0]
    out = mem.resolve_finding(store, f["finding_id"], "REF-999999")
    assert out["errors"] and "unknown_refinement" in out["errors"][0]


def test_a_refinement_nobody_can_locate_is_refused(store):
    f = mem.record_finding(store, _finding())
    out = mem.record_refinement(store, {
        "target_kind": "SKILL", "target": "skill:x", "change": "c",
        "applied_by": MARK, "finding_ids": [f["finding_id"]]})
    assert out["refinement_id"] is None
    assert any("commit_sha" in e for e in out["errors"])


def test_a_refinement_against_a_finding_that_does_not_exist_is_refused(store):
    out = mem.record_refinement(store, {
        "target_kind": "SKILL", "target": "skill:x", "change": "c",
        "commit_sha": "deadbee", "applied_by": MARK,
        "finding_ids": ["MEM-999999"]})
    assert out["refinement_id"] is None
    assert "do not exist" in " ".join(out["errors"])


# ── the whole loop ──────────────────────────────────────────────────────
def test_round_trip_record_refine_resolve_recur(store):
    f = mem.record_finding(store, _finding())
    fid = f["finding_id"]

    ref = mem.record_refinement(store, {
        "target_kind": "GATE", "target": "CG-13",
        "change": "the census now resolves the item grain",
        "commit_sha": "af4cd4b", "gate_added": "CG-13",
        "applied_by": MARK, "finding_ids": [fid]})
    rid = ref["refinement_id"]
    assert rid.startswith("REF-")

    closed = mem.resolve_finding(store, fid, rid, verification="pytest")
    assert closed["status"] == "RESOLVED" and closed["resolved_by"] == rid

    cur = store.cursor()
    cur.execute("SELECT held, findings_recurred FROM memory_refinement_outcome "
                "WHERE refinement_id = %s", (rid,))
    held, recurred = cur.fetchone()
    assert held is True and recurred == 0, "a fresh refinement holds"

    # ...and then it comes back.
    back = mem.report_recurrence(
        store, fid,
        measurement="re-ran the census after the fix; the item grain is swept "
                    "but two writers still bind nothing, 2 of 18 keys unbound",
        reported_by=MARK, reported_by_kind="TEST")
    assert back["status"] == "RECURRED"
    assert back["refinement_that_did_not_hold"] == rid
    assert back["refinement_still_holds"] is False
    assert back["recurrences"] == 1

    cur.execute("SELECT held FROM memory_refinement_outcome "
                "WHERE refinement_id = %s", (rid,))
    assert cur.fetchone()[0] is False, (
        "`held` is computed from the sightings, not asserted by the writer")

    # RECURRED counts as open again.
    open_now = mem.list_open_findings(store, component="mcp", limit=500)
    assert fid in [r["finding_id"] for r in open_now["findings"]]


def test_a_recurrence_needs_something_that_could_have_failed(store):
    f = mem.record_finding(store, _finding())
    out = mem.report_recurrence(
        store, f["finding_id"],
        measurement="a measurement long enough to pass the floor, taken twice",
        reported_by=MARK)
    assert out["errors"] and "never resolved" in out["errors"][0]


def test_reporting_a_resolved_defect_again_warns_rather_than_reopening(store):
    f = _finding()
    first = mem.record_finding(store, f)
    ref = mem.record_refinement(store, {
        "target_kind": "TEST", "target": "t", "change": "c",
        "change_ref": "skill@v2", "applied_by": MARK,
        "finding_ids": [first["finding_id"]]})
    mem.resolve_finding(store, first["finding_id"], ref["refinement_id"])
    again = mem.record_finding(store, dict(f, source_ref="second-look"))
    assert again["deduped"] is True and again["status"] == "RESOLVED"
    assert "report_recurrence" in again["warning"]


# ── the digest is the loop's own read ───────────────────────────────────
def test_the_digest_reports_what_came_back(store):
    f = mem.record_finding(store, _finding())
    ref = mem.record_refinement(store, {
        "target_kind": "SKILL", "target": "skill:dma-surface-production",
        "change": "sharpened the prompt", "change_ref": "skill@v3",
        "applied_by": MARK, "finding_ids": [f["finding_id"]]})
    mem.resolve_finding(store, f["finding_id"], ref["refinement_id"])
    mem.report_recurrence(
        store, f["finding_id"],
        measurement="the same shape appeared on the next run; measured on the "
                    "served payload, 1 of 1 sections affected",
        reported_by=MARK, reported_by_kind="TEST")
    digest = mem.memory_digest(store, days=7)
    assert any(r["finding_id"] == f["finding_id"]
               for r in digest["recurrences_in_window"])
    assert any(r["refinement_id"] == ref["refinement_id"] and r["held"] is False
               for r in digest["refinements_in_window"])
    assert digest["totals"]["all"] >= 1
