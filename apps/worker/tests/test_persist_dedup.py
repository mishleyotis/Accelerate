"""Stage 1.3 verification bullets against a real database — the persist
step's evidence dedup semantics (synthetic package; no client data):

- Two package rows with identical content land as ONE evidence row; the
  duplicate's e_id is aliased to the kept row so its citations resolve.
- The dedup is recorded twice over: an evidence_dedup_audit row (the same
  ledger register_evidence uses) and a parser observation with the id
  mapping — never silently reconciled.
- Re-persisting the same e_id is the idempotent re-scan path: no audit
  row, no duplicate evidence.
- linked_evidence_count is a computed zero once the linker has run —
  NULL means the linker never saw the run.

Runs as the dmai-worker parity user when a migrated database is present;
skips otherwise.
"""
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_worker.persist import persist_package
from dma_worker.workbook_parser import ParsedScore, WorkbookParse

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"


def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def conns():
    try:
        worker = _connect("dmai-worker@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")

    def clean():
        cur = admin.cursor()
        cur.execute("SELECT id FROM entities WHERE display_id = 'synthetic-dedup-bank'")
        for (eid,) in cur.fetchall():
            cur.execute("""DELETE FROM evidence_dedup_audit WHERE matched_e_id IN
                             (SELECT e_id FROM evidence_index WHERE entity_id = %s)""", (eid,))
            cur.execute("""DELETE FROM evidence_subcap_links WHERE run_id IN
                             (SELECT id FROM runs WHERE entity_id = %s)""", (eid,))
            cur.execute("""DELETE FROM parser_observations WHERE run_id IN
                             (SELECT id FROM runs WHERE entity_id = %s)""", (eid,))
            cur.execute("""DELETE FROM subcap_scores WHERE run_id IN
                             (SELECT id FROM runs WHERE entity_id = %s)""", (eid,))
            cur.execute("""DELETE FROM peer_scores WHERE run_id IN
                             (SELECT id FROM runs WHERE entity_id = %s)""", (eid,))
            cur.execute("""DELETE FROM recommendations_raw WHERE run_id IN
                             (SELECT id FROM runs WHERE entity_id = %s)""", (eid,))
            cur.execute("""DELETE FROM run_manifest WHERE run_id IN
                             (SELECT id FROM runs WHERE entity_id = %s)""", (eid,))
            cur.execute("DELETE FROM runs WHERE entity_id = %s", (eid,))
            cur.execute("DELETE FROM evidence_index WHERE entity_id = %s", (eid,))
            cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
        admin.commit()

    clean()
    yield worker, admin
    worker.rollback()
    clean()
    worker.close()
    admin.close()


MANIFEST = {
    "run_id": "DMA-ASM-SDB-20260801-01",
    "institution": {"name": "Synthetic Dedup Bank"},
    "versions": {"taxonomy": "v7.0"},
    "assessment": {"date": "2026-08-01"},
    "scores": {"overall": 2.5},
}

EXCERPT = ("The bank's 2025 annual report confirms a fully deployed core "
           "modernisation programme across all retail lines of business.")

# E-002 duplicates E-001's content under a different id; E-003 is distinct.
EVIDENCE = [
    {"e_id": "E-001", "source_name": "Annual Report", "source_url": "https://sdb.example/ar",
     "excerpt": EXCERPT, "tier": None, "ers": None, "published_date": "2025-12-31",
     "subcaps": ["P1C1.1.1"]},
    {"e_id": "E-002", "source_name": "Annual Report (re-filed)", "source_url": "https://sdb.example/ar",
     "excerpt": EXCERPT, "tier": None, "ers": None, "published_date": "2025-12-31",
     "subcaps": ["P1C1.1.2"]},
    {"e_id": "E-003", "source_name": "Press release", "source_url": "https://sdb.example/pr",
     "excerpt": "A genuinely different excerpt about the data platform rollout, long enough to hash.",
     "tier": None, "ers": None, "published_date": None,
     "subcaps": []},
]


def _score(subcap, score, cell, refs, confidence):
    return ParsedScore(subcap_id=subcap, pillar_id="P1", category_id="P1C1",
                       capability_id="P1C1.1", name=None, tier=None,
                       score=Decimal(score), source_cell=cell,
                       evidence_quality=None, confidence=confidence,
                       evidence_refs=refs)


def _workbook():
    scores = [
        _score("P1C1.1.1", "2.4", "P1_Subcap_Scoring!D2", ["E-001"], "HIGH"),
        # cites the DUPLICATE id — must resolve to the kept row
        _score("P1C1.1.2", "1.9", "P1_Subcap_Scoring!D3", ["E-002"], "HIGH"),
        # no citations at all — computed zero, thin
        _score("P1C1.1.4", "3.1", "P1_Subcap_Scoring!D4", [], "MEDIUM"),
    ]
    return WorkbookParse(scores=scores, observations=[], toggled_out=[],
                         scored_cells=len(scores), composite=None)


def test_duplicate_content_lands_once_and_citations_resolve(conns):
    worker, admin = conns
    res = persist_package(worker, manifest=MANIFEST, workbook=_workbook(),
                          source_folder_id="synthetic", evidence=EVIDENCE)
    cur = worker.cursor()

    # stored ids are entity-qualified (E-047 -> E-{ENT}-047: workbook-local
    # numbering is global-PK-safe only once qualified); E-002 deduped away
    cur.execute("SELECT e_id FROM evidence_index WHERE entity_id = %s ORDER BY e_id",
                (res.entity_id,))
    assert [r[0] for r in cur.fetchall()] == ["E-SDB-001", "E-SDB-003"]

    # the duplicate's links resolve to the kept row, on both bases
    cur.execute("""SELECT e_id, subcap_id, link_basis FROM evidence_subcap_links
                    WHERE run_id = %s ORDER BY subcap_id, link_basis""", (res.run_id,))
    links = [list(r) for r in cur.fetchall()]
    assert ["E-SDB-001", "P1C1.1.1", "package"] in links
    assert ["E-SDB-001", "P1C1.1.2", "package"] in links   # E-002's link, aliased
    assert all(e.startswith("E-SDB-") for e, _, _ in links)

    # audit ledger + observation, never silent
    acur = admin.cursor()
    acur.execute("""SELECT branch, matched_e_id FROM evidence_dedup_audit
                     WHERE matched_e_id = 'E-SDB-001'""")
    assert [list(r) for r in acur.fetchall()] == [["duplicate_within_run", "E-SDB-001"]]
    cur.execute("""SELECT detail FROM parser_observations
                    WHERE run_id = %s AND kind = 'evidence_dedup'""", (res.run_id,))
    (detail,) = cur.fetchone()
    assert detail["package_local_id"] == "E-002"
    assert detail["kept_e_id"] == "E-SDB-001"

    # linker ran: uncited cell carries a computed zero, and it reads as thin
    cur.execute("""SELECT subcap_id, linked_evidence_count, is_thin_evidence
                    FROM subcap_scores WHERE run_id = %s ORDER BY subcap_id""",
                (res.run_id,))
    by_id = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    assert by_id["P1C1.1.4"] == (0, True)
    assert by_id["P1C1.1.1"][0] >= 1 and by_id["P1C1.1.2"][0] >= 1

    # undated evidence is UNVERIFIED, never current
    cur.execute("SELECT recency_band FROM evidence_index WHERE e_id = 'E-SDB-003'")
    assert cur.fetchone()[0] == "UNVERIFIED"


def test_rescan_of_same_ids_is_idempotent_and_unaudited(conns):
    worker, admin = conns
    persist_package(worker, manifest=MANIFEST, workbook=_workbook(),
                    source_folder_id="synthetic", evidence=EVIDENCE)
    res2 = persist_package(worker, manifest=MANIFEST, workbook=_workbook(),
                           source_folder_id="synthetic", evidence=EVIDENCE)
    cur = worker.cursor()
    cur.execute("SELECT count(*) FROM evidence_index WHERE entity_id = %s", (res2.entity_id,))
    assert cur.fetchone()[0] == 2                # still just E-SDB-001, E-SDB-003
    acur = admin.cursor()
    acur.execute("SELECT count(*) FROM evidence_dedup_audit WHERE matched_e_id = 'E-SDB-001'")
    assert acur.fetchone()[0] == 2   # one per persist call — E-002 deduped each time
    # second run is a new run row (run-level idempotency lives in scan_diff)
    assert res2.run_seq == 2


def test_peer_scores_store_only_named_scores_and_verify_the_median(conns):
    """Only per-peer scores land; the tab's stated median is verified
    against a recompute of the scores beside it, and a lie becomes an
    observation — derivable figures are never stored."""
    worker, _ = conns
    peers = [
        {"category_id": "P1C1", "category_name": "Digital Strategy",
         "entity_score": Decimal("1.77"), "stated_median": Decimal("3.0"),
         "peers": [("Peer A", Decimal("3.0")), ("Peer B", Decimal("3.5")),
                   ("Peer C", Decimal("2.5"))]},
        # stated median 9.9 disagrees with the recomputed 2.0
        {"category_id": "P1C2", "category_name": "Governance",
         "entity_score": Decimal("1.71"), "stated_median": Decimal("9.9"),
         "peers": [("Peer A", Decimal("2.0")), ("Peer B", Decimal("2.0")),
                   ("Peer C", None)]},
    ]
    res = persist_package(worker, manifest=MANIFEST, workbook=_workbook(),
                          source_folder_id="synthetic", evidence=EVIDENCE,
                          peers=peers)
    cur = worker.cursor()
    cur.execute("""SELECT category_id, peer_name, score FROM peer_scores
                    WHERE run_id = %s ORDER BY category_id, peer_name""", (res.run_id,))
    rows = [list(r) for r in cur.fetchall()]
    assert len(rows) == 6                      # every named peer, both categories
    assert ["P1C2", "Peer C", None] in rows    # NULL retained, never imputed
    cur.execute("""SELECT detail FROM parser_observations
                    WHERE run_id = %s AND kind = 'artefact_disagreement'
                      AND detail->>'figure' LIKE 'peer_median%%'""", (res.run_id,))
    details = [r[0] for r in cur.fetchall()]
    assert len(details) == 1 and details[0]["figure"] == "peer_median[P1C2]"
    assert details[0]["recomputed"] == "2.0"


def test_recommendations_land_raw_with_package_ids(conns):
    worker, admin = conns
    # runs.source_artefact_id is an FK onto import_files (0029): a run says
    # which artefact it was read from, so the artefact has to exist. Without
    # this row the test only ever passed because the database was down.
    acur = admin.cursor()
    acur.execute("""INSERT INTO import_files (artefact_id, checksum, first_seen_at)
                    VALUES ('wb.xlsx','synthetic', now())
                    ON CONFLICT (artefact_id) DO NOTHING""")
    admin.commit()
    recs = [{"rec_id": "REC-01", "payload": {"sequencing_phase": "1 — Foundation",
                                             "zennify_solution_s": "Workshop"}}]
    res = persist_package(worker, manifest=MANIFEST, workbook=_workbook(),
                          source_folder_id="synthetic", evidence=EVIDENCE,
                          recommendations=recs, artefact_id="wb.xlsx")
    cur = worker.cursor()
    cur.execute("""SELECT rec_id, payload->>'sequencing_phase', artefact_id
                    FROM recommendations_raw WHERE run_id = %s""", (res.run_id,))
    assert [list(r) for r in cur.fetchall()] == [["REC-01", "1 — Foundation", "wb.xlsx"]]


def test_reused_local_id_with_changed_content_never_aliases(conns):
    """A re-assessment whose Evidence_Master reuses E-001 for DIFFERENT
    content must get its own run-qualified row — serving run 1's excerpt
    for run 2's citation would be a fail-closed-evidence violation."""
    worker, _ = conns
    persist_package(worker, manifest=MANIFEST, workbook=_workbook(),
                    source_folder_id="synthetic", evidence=EVIDENCE)
    changed = [dict(EVIDENCE[0],
                    excerpt="A materially revised excerpt for the re-assessment, "
                            "long enough to clear the hash floor.")]
    res2 = persist_package(worker, manifest=MANIFEST, workbook=_workbook(),
                           source_folder_id="synthetic", evidence=changed)
    cur = worker.cursor()
    cur.execute("""SELECT e_id, excerpt FROM evidence_index
                    WHERE entity_id = %s AND e_id LIKE 'E-SDB-001%%' ORDER BY e_id""",
                (res2.entity_id,))
    rows = [list(r) for r in cur.fetchall()]
    assert [r[0] for r in rows] == ["E-SDB-001", "E-SDB-001-R2"]
    assert rows[0][1] != rows[1][1]                    # both contents retained
    cur.execute("""SELECT count(*) FROM parser_observations
                    WHERE run_id = %s AND kind = 'evidence_id_collision'""",
                (res2.run_id,))
    assert cur.fetchone()[0] == 1
    # every one of run 2's links resolves to run 2's row, not run 1's
    cur.execute("""SELECT DISTINCT e_id FROM evidence_subcap_links
                    WHERE run_id = %s""", (res2.run_id,))
    assert [r[0] for r in cur.fetchall()] == ["E-SDB-001-R2"]
