"""Stage 2.3b/2.5 QA bullets — register_evidence:

- The server allocates the id and computes the bounded rank score;
  registering the same source six times returns one id six times.
- An excerpt not present in the fetched artefact is rejected AT
  registration; an unreachable URL rejects rather than trusting.
- A value with no source URL cannot be registered as FACT.
- identity_ok is asserted only when a check ran (never a silent pass).
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_mcp.register import register_evidence

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"

PAGE = ("Annual report 2025. The group processed 4 billion in premium and "
        "completed its core migration in Q3, with 92 percent of policies "
        "on the new platform by December.")


def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def seeded():
    try:
        mcp = _connect("dmai-mcp@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()

    def clean():
        cur.execute("SELECT id FROM entities WHERE display_id = 'synthetic-register-bank'")
        for (eid,) in cur.fetchall():
            for sql in (
                """DELETE FROM evidence_dedup_audit WHERE matched_e_id IN
                     (SELECT e_id FROM evidence_index WHERE entity_id = %s)""",
                """DELETE FROM evidence_subcap_links WHERE e_id IN
                     (SELECT e_id FROM evidence_index WHERE entity_id = %s)""",
                "DELETE FROM runs WHERE entity_id = %s",
                "DELETE FROM evidence_index WHERE entity_id = %s",
                "DELETE FROM entities WHERE id = %s",
            ):
                cur.execute(sql, (eid,))
        admin.commit()

    clean()
    cur.execute("""INSERT INTO entities (display_id, status, created_at)
                   VALUES ('synthetic-register-bank','ACTIVE', now()) RETURNING id""")
    eid = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status, completed_at)
                   VALUES (%s,'DMA-ASM-SRB-20260801-01',1,'INGESTED','2026-08-01')
                   RETURNING id""", (eid,))
    rid = cur.fetchone()[0]
    admin.commit()
    yield mcp, str(rid)
    mcp.rollback()
    clean()
    mcp.close()
    admin.close()


def _item(**kw):
    base = {
        "source_name": "Annual Report 2025",
        "source_url": "https://srb.example/annual-report",
        "excerpt": ("The group processed 4 billion in premium and completed "
                    "its core migration in Q3, with 92 percent of policies "
                    "on the new platform by December."),
        "claim_type": "FACT", "tier": "T2",
        "published_date": "2025-12-31",
        "linked_subcap_ids": ["P4C3.1.1"],
        "facts": [{"label": "premium", "value": "4bn"}],
    }
    base.update(kw)
    return base


def test_mint_dedup_and_bounded_ers(seeded):
    mcp, rid = seeded
    fetch = lambda url: PAGE
    r1 = register_evidence(mcp, rid, _item(), fetch=fetch)
    assert r1["errors"] == [] and r1["deduped"] is False
    assert r1["e_id"].startswith("E-CC-")
    # T2(4)*.35 + CURRENT(5)*.25 + spec5*.20 + corr T2-single(3)*.20 = 4.25
    assert r1["ers"] == 4.25

    # same content five more times -> same id, deduped, ers not recomputed
    ids = set()
    for _ in range(5):
        r = register_evidence(mcp, rid, _item(), fetch=fetch)
        assert r["deduped"] is True and r["ers"] is None
        ids.add(r["e_id"])
    assert ids == {r1["e_id"]}

    cur = mcp.cursor()
    cur.execute("SELECT ers, specificity, corroboration FROM evidence_index WHERE e_id = %s",
                (r1["e_id"],))
    ers, spec, corr = cur.fetchone()
    assert float(ers) == 4.25 and spec == 5 and corr == 3
    # the six surfaces' links collapsed onto one row
    cur.execute("SELECT count(*) FROM evidence_subcap_links WHERE e_id = %s", (r1["e_id"],))
    assert cur.fetchone()[0] == 1


def test_excerpt_must_be_verbatim_and_url_reachable(seeded):
    mcp, rid = seeded
    bad = register_evidence(mcp, rid,
                            _item(excerpt="A paraphrase of the report that says the "
                                          "migration finished and most policies moved over."),
                            fetch=lambda u: PAGE)
    assert bad["e_id"] is None and "excerpt_not_verbatim" in bad["errors"][0]

    down = register_evidence(mcp, rid, _item(), fetch=lambda u: None)
    assert down["e_id"] is None and "url_unreachable" in down["errors"][0]

    nofetcher = register_evidence(mcp, rid, _item(), fetch=None)
    assert nofetcher["e_id"] is None and "excerpt_unverifiable" in nofetcher["errors"][0]


def test_no_url_cannot_be_fact_and_identity_never_defaults(seeded):
    mcp, rid = seeded
    r = register_evidence(mcp, rid, _item(source_url=None), fetch=None)
    assert r["errors"] == [] and r["e_id"]
    assert any("downgraded to INFERENCE" in a for a in r["adjustments"])
    cur = mcp.cursor()
    cur.execute("""SELECT enum_label(claim_type), identity_ok
                     FROM evidence_index WHERE e_id = %s""", (r["e_id"],))
    claim, identity_ok = cur.fetchone()
    assert claim == "INFERENCE"
    assert identity_ok is None            # no check ran -> no assertion

    own = register_evidence(mcp, rid, _item(excerpt=PAGE[:120]),
                            fetch=lambda u: PAGE,
                            known_entity_domains=["srb.example"])
    cur.execute("SELECT identity_ok, identity_note FROM evidence_index WHERE e_id = %s",
                (own["e_id"],))
    ok, note = cur.fetchone()
    assert ok is True and note == "entity's own domain"


def test_malformed_items_reject_with_named_reasons(seeded):
    mcp, rid = seeded
    r = register_evidence(mcp, rid, _item(excerpt="too short", claim_type="OPINION",
                                          tier="T9"), fetch=lambda u: PAGE)
    assert r["e_id"] is None
    joined = " ".join(r["errors"])
    assert "excerpt_length" in joined and "claim_type" in joined and "tier" in joined
