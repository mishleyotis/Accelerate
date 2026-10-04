"""Connector-origin evidence and split discovery spans at register_evidence
(owner decision 3 and RC-08 / D-10, 2026-10-04; migration 0063).

MEASURED on SWBC (gold audit, S-01/S-03): the sentiment card shipped one
company-reported bar while two auditors called the Indeed connector and got
an employer rating of 3.1/5 (recommend 46 of 97), and a CFPB complaint API
call returned 213 complaints at 96.2% timely response. Neither could be
registered: register_evidence verified excerpts by FETCHING a URL, and a
connector reading is a tool result. A URL-less registration demoted it to
INFERENCE — a measured reading laundered into a weak claim.

The owner admitted it as origin 'connector', recording tool, query and
retrieval date, with the tier COMPUTED from the tool (Indeed T3, CFPB T1)
and the excerpt verified against the STORED response.

The same day's default for discovery evidence: a partly sensitive internal
row is SPLIT into a shareable span (customer_attribution) and an internal
span; each span is a verbatim piece of its parent.

The pure rules are tested here without a database. The minting paths run
against the migrated local database and skip honestly without one, like
every DB-backed fixture in this suite.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import register as R                                 # noqa: E402
from dma_mcp.register import (attribution_problem, connector_family,  # noqa: E402
                              connector_provenance, register_evidence,
                              split_problem)

NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
INDEED = json.dumps({"company": "Example Group", "rating": 3.1,
                     "reviews": 97, "recommend_to_friend": "46 of 97 reviewers "
                     "would recommend working at Example Group to a friend"})
EXCERPT = ("46 of 97 reviewers would recommend working at Example Group "
           "to a friend")


def _indeed(**kw):
    c = {"tool": "mcp__Indeed__get_company_data",
         "query": {"company": "Example Group"},
         "retrieved_at": "2026-10-01T14:03:00Z", "response": INDEED}
    c.update(kw)
    return {"origin": "connector", "excerpt": EXCERPT, "claim_type": "FACT",
            "source_name": "Indeed employer reviews for Example Group",
            "connector": c}


# ── tier is computed from the tool ─────────────────────────────────────────
def test_indeed_is_t3_and_cfpb_is_t1():
    assert connector_family("mcp__Indeed__get_company_data") == ("indeed", "T3")
    assert connector_family("Indeed.get_company_data") == ("indeed", "T3")
    assert connector_family("cfpb.complaints_api") == ("cfpb", "T1")
    assert connector_family("consumerfinance.gov complaint search API") == \
        ("cfpb", "T1")
    assert connector_family("mcp__Clay__search-companies") is None


def test_a_producer_tier_is_ignored_and_said_so():
    p = connector_provenance({**_indeed(), "tier": "T1"}, now=NOW)
    assert p["errors"] == [] and p["tier"] == "T3"
    assert any("tier T1 ignored" in a for a in p["adjustments"])


def test_an_unregistered_tool_is_refused():
    p = connector_provenance(_indeed(tool="mcp__Clay__search-companies"),
                             now=NOW)
    assert any(e.startswith("connector_tool_unregistered") for e in p["errors"])


@pytest.mark.parametrize("field,value,needle", [
    ("tool", "", "connector.tool"),
    ("query", "", "connector.query"),
    ("retrieved_at", None, "connector.retrieved_at"),
    ("retrieved_at", "last week", "connector.retrieved_at"),
    ("retrieved_at", (NOW + timedelta(days=3)).isoformat(), "in the future"),
    ("response", None, "excerpt_unverifiable"),
])
def test_provenance_is_required(field, value, needle):
    p = connector_provenance(_indeed(**{field: value}), now=NOW)
    assert any(needle in e for e in p["errors"]), p["errors"]


def test_the_response_hash_is_computed_server_side():
    p = connector_provenance(_indeed(), now=NOW)
    assert p["sha256"] == hashlib.sha256(INDEED.encode()).hexdigest()
    bad = connector_provenance(_indeed(response_sha256="0" * 64), now=NOW)
    assert any("does not match" in e for e in bad["errors"])


def test_a_stored_response_may_be_referenced_by_hash():
    p = connector_provenance(_indeed(response=None,
                                     response_sha256="ab" * 32), now=NOW)
    assert p["errors"] == [] and p["body"] is None


# ── register_evidence, up to the first database write ─────────────────────
class _Cur:
    """Answers the run lookup only. Every refusal below happens before the
    first write, which is what makes these runnable with no database."""

    def __init__(self):
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append(sql)

    def fetchone(self):
        if "FROM runs" in self.sql[-1]:
            return ("ent-1", datetime(2026, 10, 1).date())
        return None


class _Conn:
    def __init__(self):
        self.cur = _Cur()

    def cursor(self):
        return self.cur

    def commit(self):  # pragma: no cover — no write reaches here
        raise AssertionError("nothing may be written")


def test_a_paraphrase_of_the_response_is_refused_without_a_fetch():
    called = []
    item = _indeed()
    item["excerpt"] = ("About half of the reviewers say they would recommend "
                       "the employer to a friend.")
    r = register_evidence(_Conn(), "run-1", item,
                          fetch=lambda u: called.append(u))
    assert r["e_id"] is None and "excerpt_not_verbatim" in r["errors"][0]
    assert called == [], "a connector reading is never verified by a fetch"


def test_connector_provenance_on_another_origin_is_refused():
    item = {**_indeed(), "origin": "producer", "tier": "T3"}
    r = register_evidence(_Conn(), "run-1", item, fetch=lambda u: None)
    assert any("origin='connector'" in e for e in r["errors"])


# ── split spans: pure rules ────────────────────────────────────────────────
PARENT_EXCERPT = ("The sponsor said there is no single customer profile "
                  "across the lines of business, and asked for a proposal "
                  "covering about five hundred users.")
PARENT = ("E-CC-1", "ent-1", "internal", PARENT_EXCERPT)
SPAN = "there is no single customer profile across the lines of business"


def test_a_span_must_be_a_verbatim_piece_of_an_internal_parent():
    assert split_problem(PARENT, "ent-1", SPAN) is None
    assert "not_verbatim" in split_problem(
        PARENT, "ent-1", "the client has no golden customer record anywhere")
    assert "foreign" in split_problem(PARENT, "ent-2", SPAN)
    assert "only an internal" in split_problem(
        ("E-CC-1", "ent-1", "producer", PARENT_EXCERPT), "ent-1", SPAN)
    assert "does not exist" in split_problem(None, "ent-1", SPAN)


@pytest.mark.parametrize("label,ok", [
    ("Client statement, discovery conversations, September 2026", True),
    ("Zennify discovery notes, September 2026", False),
    ("Internal discovery write-up prepared for the sponsor", False),
    ("Client", False),
])
def test_the_attribution_is_the_clients_voice(label, ok):
    assert (attribution_problem(label) is None) is ok


def test_an_attribution_needs_a_split():
    item = {"origin": "internal", "excerpt": SPAN + " today.",
            "claim_type": "FACT", "tier": "T2",
            "customer_attribution": "Client statement, discovery "
                                    "conversations, September 2026"}
    r = register_evidence(_Conn(), "run-1", item, fetch=None)
    assert any("split_of" in e for e in r["errors"])


# ── the minting paths, against the migrated local database ────────────────
DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"


@pytest.fixture()
def seeded():
    import pg8000.dbapi
    try:
        mcp = pg8000.dbapi.connect(user="dmai-mcp@digital-maturity-assessor.iam",
                                   password="local", host=HOST, port=5432,
                                   database="dma_insights")
        admin = pg8000.dbapi.connect(
            user="dmai-migrate@digital-maturity-assessor.iam",
            password="local", host=HOST, port=5432, database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()

    def clean():
        cur.execute("SELECT id FROM entities WHERE display_id = "
                    "'synthetic-connector-bank'")
        for (eid,) in cur.fetchall():
            for sql in (
                """DELETE FROM evidence_dedup_audit WHERE matched_e_id IN
                     (SELECT e_id FROM evidence_index WHERE entity_id = %s)""",
                """DELETE FROM evidence_subcap_links WHERE e_id IN
                     (SELECT e_id FROM evidence_index WHERE entity_id = %s)""",
                "DELETE FROM runs WHERE entity_id = %s",
                # Parent and spans in ONE statement: the self-reference is NO
                # ACTION (checked at the statement's end), and `split_of` is
                # fixed at mint, so it cannot be nulled first (0063 trigger).
                "DELETE FROM evidence_index WHERE entity_id = %s",
                "DELETE FROM connector_responses WHERE entity_id = %s",
                "DELETE FROM entities WHERE id = %s",
            ):
                cur.execute(sql, (eid,))
        admin.commit()

    clean()
    cur.execute("""INSERT INTO entities (display_id, status, created_at)
                   VALUES ('synthetic-connector-bank','ACTIVE', now())
                   RETURNING id""")
    eid = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status,
                                     completed_at)
                   VALUES (%s,'DMA-ASM-SCB-20261001-01',1,'INGESTED',
                           '2026-10-01') RETURNING id""", (eid,))
    rid = cur.fetchone()[0]
    admin.commit()
    yield mcp, str(rid)
    mcp.rollback()
    clean()
    mcp.close()
    admin.close()


def test_an_indeed_reading_mints_as_t3_fact_with_its_provenance(seeded):
    mcp, rid = seeded
    r = register_evidence(mcp, rid, {**_indeed(), "tier": "T1",
                                     "linked_subcap_ids": ["P1C4.1.1"]},
                          fetch=lambda u: pytest.fail("no fetch"))
    assert r["errors"] == [] and r["e_id"].startswith("E-CC-"), r
    cur = mcp.cursor()
    cur.execute("""SELECT enum_label(origin), enum_label(tier),
                          enum_label(claim_type), connector_tool,
                          connector_query, connector_retrieved_at,
                          connector_response_sha256, published_date
                     FROM evidence_index WHERE e_id = %s""", (r["e_id"],))
    (origin, tier, claim, tool, query, retrieved, sha,
     published) = cur.fetchone()
    assert (origin, tier, claim) == ("connector", "T3", "FACT")
    assert tool == "mcp__Indeed__get_company_data"
    assert json.loads(query) == {"company": "Example Group"}
    assert retrieved.isoformat().startswith("2026-10-01T14:03")
    assert published.isoformat() == "2026-10-01"
    cur.execute("SELECT body FROM connector_responses WHERE sha256 = %s",
                (sha,))
    assert cur.fetchone()[0] == INDEED

    # get_evidence returns the provenance with the row.
    from dma_mcp.evidence_tools import get_evidence
    got = get_evidence(mcp, rid, [r["e_id"]])["found"][0]
    assert got["origin"] == "connector" and got["tier"] == "T3"
    assert got["connector"]["tool"] == "mcp__Indeed__get_company_data"
    assert got["connector"]["retrieved_at"].startswith("2026-10-01")

    # A second span of the SAME stored response, referenced by hash.
    second = _indeed(response=None, response_sha256=sha)
    second_item = {**second, "excerpt": INDEED[:80]}
    r2 = register_evidence(mcp, rid, second_item, fetch=None)
    assert r2["errors"] == [], r2


def test_a_cfpb_aggregation_is_t1(seeded):
    mcp, rid = seeded
    body = json.dumps({"hits": {"total": {"value": 213}},
                       "aggregations": {"timely": {"yes": 205, "no": 8}}})
    item = {"origin": "connector", "claim_type": "FACT",
            "source_name": "CFPB Consumer Complaint Database",
            "excerpt": body[:90],
            "connector": {"tool": "cfpb.complaints_api",
                          "query": "company=Example Group&size=0",
                          "retrieved_at": "2026-10-01", "response": body}}
    r = register_evidence(mcp, rid, item, fetch=None)
    assert r["errors"] == [], r
    cur = mcp.cursor()
    cur.execute("SELECT enum_label(tier) FROM evidence_index WHERE e_id = %s",
                (r["e_id"],))
    assert cur.fetchone()[0] == "T1"


def test_a_discovery_row_splits_into_a_shareable_and_an_internal_span(seeded):
    mcp, rid = seeded
    parent = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": PARENT_EXCERPT, "claim_type": "FACT",
        "tier": "T2", "source_name": "Internal discovery notes",
        "published_date": "2026-09-01"}, fetch=None)
    assert parent["errors"] == [], parent
    shared = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": SPAN, "split_of": parent["e_id"],
        "customer_attribution": "Client statement, discovery conversations, "
                                "September 2026",
        "linked_subcap_ids": ["P4C1.1.1"]}, fetch=None)
    assert shared["errors"] == [], shared
    internal = register_evidence(mcp, rid, {
        "origin": "internal", "split_of": parent["e_id"],
        "excerpt": "asked for a proposal covering about five hundred users"},
        fetch=None)
    assert internal["errors"] == [], internal
    cur = mcp.cursor()
    cur.execute("""SELECT e_id, customer_attribution, split_of,
                          enum_label(tier), published_date
                     FROM evidence_index WHERE e_id = ANY(%s) ORDER BY e_id""",
                ([shared["e_id"], internal["e_id"]],))
    rows = {r[0]: r[1:] for r in cur.fetchall()}
    assert rows[shared["e_id"]][0].startswith("Client statement")
    assert rows[internal["e_id"]][0] is None          # never served
    assert rows[shared["e_id"]][1] == parent["e_id"]
    # inherited from the parent: tier and date
    assert rows[shared["e_id"]][2] == "T2"
    assert rows[shared["e_id"]][3].isoformat() == "2026-09-01"
    from dma_mcp.evidence_tools import get_evidence
    got = {f["e_id"]: f for f in get_evidence(
        mcp, rid, [shared["e_id"], internal["e_id"]])["found"]}
    assert got[shared["e_id"]]["customer_attribution"].startswith("Client")
    assert got[internal["e_id"]]["customer_attribution"] is None
    assert got[internal["e_id"]]["split_of"] == parent["e_id"]

    # The whole parent as the "shareable span" is REFUSED, and the parent
    # never gains an attribution (RC-08 review 2026-10-04: it carries the
    # seller remark registered above as the internal span).
    whole = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": PARENT_EXCERPT,
        "split_of": parent["e_id"],
        "customer_attribution": "Client statement, discovery conversations, "
                                "September 2026"}, fetch=None)
    assert whole["e_id"] is None and any(
        "whole_row" in e for e in whole["errors"]), whole
    cur.execute("SELECT customer_attribution FROM evidence_index "
                "WHERE e_id = %s", (parent["e_id"],))
    assert cur.fetchone()[0] is None
