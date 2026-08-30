"""The Northern Trust / Kitsap defect, as a test.

Measured in production on 2026-08-08: Northern Trust's run cited twelve of
its own ingested ids and `get_evidence` returned twelve of twelve as
`foreign`, belonging to entity 6fd2defa-…; Kitsap's 62 research-ledger ids
returned `foreign` to several different institutions. Both runs held ZERO
package evidence rows of their own. Neither package ships a manifest, so the
ingest's name-derived id token fell back to the literal string `UNK` — and 14
entities were writing into that one `E-UNK-nnn` namespace.

Reproduced below with two manifest-less packages, which is the whole
mechanism in miniature: same token, same local numbers, different clients.

The two properties that matter:

  · both clients' `E-007` LANDS — the second one is not left unpersistable
    because the first took the id;
  · a bare id resolves to the citing run's own entity or to nothing, and
    can never be reported as another institution's row.

A globally scoped id that really does belong to someone else — the server's
`E-CC-nnn` mint, another entity's stored id — is still `foreign`, because
that one means the reasoning has drifted (invariant 4). That half is
asserted by apps/mcp/tests/test_get_evidence.py and left there.
"""
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "mcp"))

from dma_worker.evidence_ids import (BARE_PACKAGE, entity_suffix, local_id,
                                     local_id_of_stored, qualify)

# --------------------------------------------------------------------------
# The id vocabulary — no database needed, and the part that must never drift
# from the connector's copy of the same regexes.
# --------------------------------------------------------------------------


def test_only_workbook_local_numbers_are_treated_as_package_ids():
    assert local_id("E-047") == "E-047"
    assert local_id("E-047:F1") == "E-047"      # fact grain cites the item
    assert local_id("e-047") == "E-047"
    # the server's own mint is global, not workbook-local: a bare E-104 must
    # not reach E-CC-104, and E-CC-104 must not be entity-scoped away from
    # the foreign check
    assert local_id("E-CC-104") is None
    # another entity's stored id is global too — that is what `foreign` is for
    assert local_id("E-GEB-047") is None
    assert local_id("REC-01") is None


def test_a_stored_id_remembers_which_workbook_number_it_came_from():
    assert local_id_of_stored("E-BCU-006") == "E-006"
    assert local_id_of_stored("E-BCU-006-R2") == "E-006"
    assert local_id_of_stored("E-UNK-007-1FCA91") == "E-007"
    assert local_id_of_stored("E-CC-104") is None


def test_the_collision_escape_is_this_entitys_own_identity():
    """A folded name is shared; a uuid is not. Northern Trust and Kitsap both
    tokenised to UNK — the suffix is what keeps their mints apart."""
    nt = entity_suffix("1fca9101-fce5-4240-b728-93ef5fcfcad2")
    kcu = entity_suffix("582772f6-6940-47c1-8615-1d518c923f1c")
    assert nt == "1FCA91" and kcu == "582772"
    assert nt != kcu
    assert entity_suffix("1fca9101-fce5-4240-b728-93ef5fcfcad2") == nt   # deterministic


def test_qualification_leaves_ids_outside_the_template_numbering_alone():
    assert qualify("E-047", "UNK") == "E-UNK-047"
    assert qualify("REC-01", "UNK") == "REC-01"
    assert BARE_PACKAGE.match("E-047") and not BARE_PACKAGE.match("E-CC-104")


# --------------------------------------------------------------------------
# End to end, against a real database. Skips when none is up, like every
# other DB-backed suite here.
# --------------------------------------------------------------------------

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
_M = re.match(r"^[^:]+(?:\+\w+)?://(?:[^@/]*@)?([^:/]+)(?::(\d+))?/(\w+)", DSN)
HOST, PORT, DB = (_M.group(1), int(_M.group(2) or 5432), _M.group(3)) if _M \
    else ("localhost", 5432, "dma_insights")


def _connect(user):
    import pg8000.dbapi
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=PORT, database=DB)


# Neither package ships a manifest — exactly the production shape. Identity
# comes from the folder name (cascade signal 4, PENDING_REVIEW), so there is
# no legal name, no request id, and the id token is UNK for both.
_NO_MANIFEST: dict = {}

NT_EXCERPT = ("Northern Trust uses a variety of machine-learning and AI "
              "solutions across its asset servicing platform, the 10-K states.")
KCU_EXCERPT = ("Kitsap Credit Union completed a digital banking platform "
               "migration for its retail membership during the year.")


def _wb():
    from dma_worker.workbook_parser import ParsedScore, WorkbookParse
    return WorkbookParse(
        scores=[ParsedScore(subcap_id="P1C1.1.1", pillar_id="P1",
                            category_id="P1C1", capability_id="P1C1.1",
                            name=None, tier=None, score=Decimal("2.1"),
                            source_cell="P1_Subcap_Scoring!D2",
                            evidence_quality=None, confidence="HIGH",
                            evidence_refs=["E-007"])],
        observations=[], toggled_out=[], scored_cells=1)


@pytest.fixture()
def two_manifestless_clients():
    try:
        worker = _connect("dmai-worker@digital-maturity-assessor.iam")
        mcp = _connect("dmai-mcp@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()
    try:
        cur.execute("SELECT 1 FROM evidence_package_ids LIMIT 1")
    except Exception:
        admin.rollback()
        pytest.skip("database predates migration 0036")

    folders = ("ns-probe northern trust", "ns-probe kitsap credit union")

    def clean():
        c = admin.cursor()
        c.execute("SELECT id FROM entities WHERE display_id LIKE 'ns-probe%'")
        for (eid,) in c.fetchall():
            c.execute("""DELETE FROM evidence_dedup_audit WHERE matched_e_id IN
                           (SELECT e_id FROM evidence_index WHERE entity_id = %s)""", (eid,))
            c.execute("DELETE FROM evidence_package_ids WHERE entity_id = %s", (eid,))
            for t in ("evidence_subcap_links", "parser_observations",
                      "subcap_scores", "peer_scores", "recommendations_raw",
                      "run_manifest"):
                c.execute(f"""DELETE FROM {t} WHERE run_id IN
                                (SELECT id FROM runs WHERE entity_id = %s)""", (eid,))
            c.execute("DELETE FROM runs WHERE entity_id = %s", (eid,))
            c.execute("DELETE FROM evidence_index WHERE entity_id = %s", (eid,))
            c.execute("DELETE FROM entities WHERE id = %s", (eid,))
        admin.commit()

    clean()
    yield worker, mcp, folders
    worker.rollback()
    mcp.rollback()
    clean()
    for c in (worker, mcp, admin):
        c.close()


def _persist(conn, folder, excerpt):
    from dma_worker.persist import persist_package
    return persist_package(
        conn, manifest=_NO_MANIFEST, workbook=_wb(), source_folder_id=folder,
        evidence=[{"e_id": "E-007", "source_name": "10-K",
                   "source_url": f"https://{folder.split()[1]}.example/10k",
                   "excerpt": excerpt, "tier": None, "ers": None,
                   "published_date": None, "subcaps": ["P1C1.1.1"]}])


def test_two_manifestless_clients_both_land_their_own_e_007(two_manifestless_clients):
    """The production shape: no manifest, so both tokenise to UNK. Before the
    fix the second client's E-007 hit the first's row, exhausted its one
    retry and was recorded `evidence_unpersistable` — 5,019 items across 61
    runs in production, 33 of them Northern Trust's."""
    worker, _mcp, (nt_folder, kcu_folder) = two_manifestless_clients
    nt = _persist(worker, nt_folder, NT_EXCERPT)
    kcu = _persist(worker, kcu_folder, KCU_EXCERPT)
    assert nt.entity_id != kcu.entity_id

    cur = worker.cursor()
    for res, excerpt in ((nt, NT_EXCERPT), (kcu, KCU_EXCERPT)):
        cur.execute("""SELECT e_id, excerpt FROM evidence_index
                        WHERE entity_id = %s AND origin = 'package'""",
                    (res.entity_id,))
        rows = cur.fetchall()
        assert len(rows) == 1, f"{res.entity_id} landed {len(rows)} rows"
        assert rows[0][1] == excerpt        # its OWN excerpt, not the other's
    # nothing was dropped on the floor
    cur.execute("""SELECT count(*) FROM parser_observations
                    WHERE run_id IN (%s, %s)
                      AND kind IN ('evidence_unpersistable',
                                   'evidence_conflict_unresolved')""",
                (nt.run_id, kcu.run_id))
    assert cur.fetchone()[0] == 0

    # the two mints are distinct, and the second says whose it is
    cur.execute("""SELECT entity_id, package_local_id, e_id
                     FROM evidence_package_ids
                    WHERE entity_id IN (%s, %s) ORDER BY e_id""",
                (nt.entity_id, kcu.entity_id))
    mapped = cur.fetchall()
    assert [m[1] for m in mapped] == ["E-007", "E-007"]
    assert len({m[2] for m in mapped}) == 2
    assert any(entity_suffix(m[0]) in m[2] for m in mapped)


def test_a_bare_citation_never_resolves_to_another_institution(two_manifestless_clients):
    """The defect itself: `get_evidence` for Northern Trust's own E-007
    returned `foreign`, belonging to another entity, and invariant 4 halted
    production. It must now return `found`, with this client's excerpt."""
    from dma_mcp.evidence_tools import get_evidence
    worker, mcp, (nt_folder, kcu_folder) = two_manifestless_clients
    nt = _persist(worker, nt_folder, NT_EXCERPT)
    kcu = _persist(worker, kcu_folder, KCU_EXCERPT)

    for res, excerpt in ((nt, NT_EXCERPT), (kcu, KCU_EXCERPT)):
        out = get_evidence(mcp, res.run_id, ["E-007", "E-007:F1"])
        assert out["foreign"] == [], out["foreign"]
        assert out["not_found"] == []
        assert {f["excerpt"] for f in out["found"]} == {excerpt}
        assert {f["entity_id"] for f in out["found"]} == {str(res.entity_id)}

    # and an id this client's workbook never carried is absent, not foreign
    out = get_evidence(mcp, nt.run_id, ["E-993"])
    assert out["not_found"] == ["E-993"] and out["foreign"] == []


def test_a_deduped_local_id_still_resolves_to_the_row_that_was_kept(
        two_manifestless_clients):
    """Two Evidence_Master rows with identical content land as ONE row; both
    local numbers must still resolve. 297 dedups across 14 runs in
    production — every one a citation that resolves to nothing without the
    mapping's many-to-one."""
    from dma_mcp.evidence_tools import get_evidence
    from dma_worker.persist import persist_package
    worker, mcp, (nt_folder, _) = two_manifestless_clients
    same = {"source_name": "10-K", "source_url": "https://nt.example/10k",
            "excerpt": NT_EXCERPT, "tier": None, "ers": None,
            "published_date": None, "subcaps": ["P1C1.1.1"]}
    res = persist_package(worker, manifest=_NO_MANIFEST, workbook=_wb(),
                          source_folder_id=nt_folder,
                          evidence=[dict(same, e_id="E-007"),
                                    dict(same, e_id="E-008")])
    out = get_evidence(mcp, res.run_id, ["E-007", "E-008"])
    assert out["not_found"] == [] and out["foreign"] == []
    assert len({f["stored_id"] for f in out["found"]}) == 1   # one kept row
