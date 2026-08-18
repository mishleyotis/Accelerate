"""Stage 2.5 QA bullets — the promote transaction:

- A promote with one page missing writes nothing and names the page.
- An injected writer failure rolls back all writes.
- Re-promoting a promoted run is not an error (idempotent).
- Every promoted row carries a non-null producer version.
- The writer registry order is stable (the order IS the deadlock
  discipline).
- Fixing one page re-promotes six pages from five retained staged rows.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_mcp.contracts import PAGES, SERVING_TABLES, sections
from dma_mcp.promote import _SPEC_PATH, promote_run, writer_registry
from dma_mcp.submit import submit_page_payload

pytestmark = pytest.mark.skipif(
    not _SPEC_PATH.exists(),
    reason="writer_spec.json not yet extracted")

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"

ENV = {"produced_at": "2026-08-04T12:00:00Z", "producer_version": "test@1",
       "e_ids": [], "internal_only": []}
STAMPS = {"run_id": "11111111-1111-1111-1111-111111111111",
          "entity_id": "22222222-2222-2222-2222-222222222222",
          "promoted_at": "2026-08-08T00:00:00+00:00",
          "producer_version": "test@1", "provenance": "producer"}
EMPTY = {"reason": "Walking-skeleton empty state",
         "sources_searched": ["package", "research", "enrichment"]}


def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


#: CG-23 refuses a section whose writer stores a page thread and got none.
#: The fixture adds one only where the CONTRACT binds it, because adding it
#: everywhere would trip CG-04 on the sections that have nowhere to put one —
#: which is the same asymmetry the gate itself reads.
THREAD = "Thread " + " ".join(["thread"] * 49)


def _thread_if_bound(page: str, name: str) -> dict:
    return ({"narrative_thread": THREAD}
            if "narrative_thread" in sections(page)[name]["fields"] else {})


def _empty_page(page: str) -> dict:
    return {name: {**ENV, "empty_state": EMPTY, **_thread_if_bound(page, name)}
            for name in sections(page)}


def _hero_page() -> dict:
    """overview with one real section (the hero) and empty states elsewhere
    — the walking skeleton's own shape."""
    page = _empty_page("overview")
    page["scores"] = {
        **ENV, "e_ids": [],
        "composite": 2.1,
        "pillars": [{"pillar_id": "P1", "score": 2.1, "peer_median": 3.1,
                     "delta": -1.0, "peer_n": 5, "peer_basis": "table",
                     "proxy_disclosure": None}],
        "posture": "LAGGING", "posture_basis": "EVIDENCE",
        "framing": ("Early digital maturity, with strategy work under way "
                    "and clear peer gaps across the group."),
        "claim_label": "FACT", "confidence": "HIGH",
        "narrative_thread": THREAD,
    }
    return page


@pytest.fixture()
def seeded():
    try:
        mcp = _connect("dmai-mcp@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()

    def clean():
        cur.execute("SELECT id FROM entities WHERE display_id = 'synthetic-promote-bank'")
        for (eid,) in cur.fetchall():
            cur.execute("SELECT id FROM runs WHERE entity_id = %s", (eid,))
            rids = [r[0] for r in cur.fetchall()]
            for rid in rids:
                cur.execute("DELETE FROM run_manifest WHERE run_id = %s", (rid,))
                for table in set(SERVING_TABLES.values()) - {"evidence_index"}:
                    cur.execute(f"DELETE FROM {table} WHERE run_id = %s", (rid,))
                cur.execute("DELETE FROM gate_results WHERE run_id = %s", (rid,))
                cur.execute("""DELETE FROM submission_verdicts WHERE submission_id IN
                                 (SELECT id FROM submissions WHERE run_id = %s)""", (rid,))
                cur.execute("DELETE FROM submissions WHERE run_id = %s", (rid,))
            cur.execute("DELETE FROM runs WHERE entity_id = %s", (eid,))
            cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
        admin.commit()

    clean()
    cur.execute("""INSERT INTO entities (display_id, status, created_at)
                   VALUES ('synthetic-promote-bank','ACTIVE', now()) RETURNING id""")
    eid = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status)
                   VALUES (%s,'DMA-ASM-SPB-20260801-01',1,'INGESTED') RETURNING id""",
                (eid,))
    rid = str(cur.fetchone()[0])
    # the hero quotes P1 = 2.1; the run must SERVE that figure (stated grain)
    cur.execute("INSERT INTO run_manifest (run_id, payload) VALUES (%s, %s)",
                (rid, '{"manifest": {}, "workbook_grains": {"pillars": '
                      '[{"pillar_id": "P1", "score": 2.1, "peer_median": 3.1}], '
                      '"categories": []}}'))
    admin.commit()
    yield mcp, admin, rid
    mcp.rollback()
    clean()
    mcp.close()
    admin.close()


def _submit_all(mcp, rid, overview=None):
    for page in PAGES:
        payload = (overview if page == "overview" and overview is not None
                   else _hero_page() if page == "overview"
                   else _empty_page(page))
        r = submit_page_payload(mcp, rid, page, payload, producer_version="test@1")
        assert r["verdict"]["status"] == "pass", (page, r["verdict"]["reasons"][:3])


def test_registry_order_is_stable_and_covers_all_34():
    reg = writer_registry()
    assert [k for k, _ in reg] == list(SERVING_TABLES)
    assert len(reg) == 34
    # the order is the deadlock discipline: assert the exact table sequence
    tables = [w["table"] for _, w in reg]
    assert tables == [SERVING_TABLES[k] for k, _ in reg]


def test_incomplete_run_writes_nothing_and_names_pages(seeded):
    mcp, admin, rid = seeded
    for page in ("overview", "insights"):
        submit_page_payload(mcp, rid, page,
                            _hero_page() if page == "overview" else _empty_page(page),
                            producer_version="test@1")
    out = promote_run(mcp, rid)
    assert out["promoted"] is False and out["error"] == "incomplete_run"
    assert out["missing_pages"] == ["context", "heatmap", "platform", "techstack"]
    cur = admin.cursor()
    cur.execute("SELECT count(*) FROM overview_scores WHERE run_id = %s", (rid,))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT status FROM runs WHERE id = %s", (rid,))
    assert cur.fetchone()[0] == "INGESTED"


def test_promote_all_or_nothing_then_idempotent(seeded):
    mcp, admin, rid = seeded
    _submit_all(mcp, rid)
    out = promote_run(mcp, rid)
    assert out["promoted"] is True
    assert out["stats"]["overview"]["sections"] == 12
    cur = admin.cursor()
    cur.execute("""SELECT composite, producer_version, promoted_at
                     FROM overview_scores WHERE run_id = %s""", (rid,))
    composite, pv, promoted_at = cur.fetchone()
    assert float(composite) == 2.1 and pv == "test@1" and promoted_at is not None
    cur.execute("SELECT enum_label(status), is_active FROM runs WHERE id = %s", (rid,))
    assert list(cur.fetchone()) == ["PROMOTED", True]

    # every promoted row carries a non-null producer version
    for table in sorted(set(SERVING_TABLES.values()) - {"evidence_index"}):
        cur.execute(f"""SELECT count(*) FROM {table}
                         WHERE run_id = %s AND producer_version IS NULL""", (rid,))
        assert cur.fetchone()[0] == 0, table

    # re-promotion is not an error and rewrites the same rows
    again = promote_run(mcp, rid)
    assert again["promoted"] is True
    cur.execute("SELECT count(*) FROM overview_scores WHERE run_id = %s", (rid,))
    assert cur.fetchone()[0] == 1


def test_a_promote_clears_a_withdrawal_and_nothing_else_does(seeded):
    """0042: withdrawal is reversed by passing the gates again, not by a
    lever. There is deliberately no restore tool — a restore would be a way
    to put a run back on a client's screen without fixing what it served —
    so this promote is the ONLY path back, and the test that proves it is
    the one that would notice if somebody added the lever."""
    from dma_mcp.withdraw import withdraw_run
    mcp, admin, rid = seeded
    _submit_all(mcp, rid)
    assert promote_run(mcp, rid)["promoted"] is True

    out = withdraw_run(mcp, rid,
                       "Top-band cells rest on a filing for a far smaller "
                       "subsidiary; withheld pending a rescore.",
                       "agent:test")
    assert out["withdrawn"] is True
    cur = admin.cursor()
    cur.execute("SELECT count(*) FROM serving_directory WHERE run_id = %s", (rid,))
    gone = cur.fetchone()[0]
    # Commit before the next promote: a read leaves this connection idle IN
    # TRANSACTION holding AccessShare on the matview, and the promote's
    # REFRESH wants Exclusive. Not a product defect — a test that would hang
    # rather than fail, which is worse than either.
    admin.commit()
    assert gone == 0

    assert promote_run(mcp, rid)["promoted"] is True
    cur.execute("""SELECT withdrawn_at, withdrawn_reason, withdrawn_by,
                          enum_label(status), is_active
                     FROM runs WHERE id = %s""", (rid,))
    at, reason, by, status, active = cur.fetchone()
    assert (at, reason, by) == (None, None, None)
    assert (status, active) == ("PROMOTED", True)
    cur.execute("SELECT count(*) FROM serving_directory WHERE run_id = %s", (rid,))
    assert cur.fetchone()[0] == 1


def test_fix_one_page_repromotes_from_retained_staging(seeded):
    mcp, admin, rid = seeded
    _submit_all(mcp, rid)
    assert promote_run(mcp, rid)["promoted"] is True
    # resubmit ONLY overview with a corrected composite
    fixed = _hero_page()
    fixed["scores"]["composite"] = 2.2
    r = submit_page_payload(mcp, rid, "overview", fixed, producer_version="test@2")
    assert r["verdict"]["status"] == "pass"
    out = promote_run(mcp, rid)
    assert out["promoted"] is True
    cur = admin.cursor()
    cur.execute("SELECT composite, producer_version FROM overview_scores WHERE run_id = %s", (rid,))
    composite, pv = cur.fetchone()
    assert float(composite) == 2.2 and pv == "test@2"
    # the five other pages promoted from their RETAINED staged rows
    cur.execute("""SELECT count(DISTINCT enum_label(page)) FROM submissions
                    WHERE run_id = %s AND superseded_at IS NULL
                      AND promoted_at IS NOT NULL""", (rid,))
    assert cur.fetchone()[0] == 6


def test_injected_writer_failure_rolls_back_everything(seeded, monkeypatch):
    mcp, admin, rid = seeded
    _submit_all(mcp, rid)
    import dma_mcp.promote as promote_mod
    real = promote_mod._write_section
    calls = {"n": 0}

    def sabotage(cur, writer, ctx, section_payload):
        calls["n"] += 1
        if calls["n"] == 30:               # deep into the write sequence
            raise RuntimeError("injected writer failure")
        return real(cur, writer, ctx, section_payload)

    monkeypatch.setattr(promote_mod, "_write_section", sabotage)
    with pytest.raises(RuntimeError):
        promote_run(mcp, rid)
    cur = admin.cursor()
    for table in sorted(set(SERVING_TABLES.values()) - {"evidence_index"}):
        cur.execute(f"SELECT count(*) FROM {table} WHERE run_id = %s", (rid,))
        assert cur.fetchone()[0] == 0, table
    cur.execute("SELECT enum_label(status) FROM runs WHERE id = %s", (rid,))
    assert cur.fetchone()[0] == "INGESTED"


def test_partial_dates_resolve_at_the_writer_boundary():
    """The prompts accept month and quarter precision; the serving column is
    a DATE. The writer resolves with the same rule the ingest tier uses, so
    a legitimate payload cannot abort the promote transaction."""
    from dma_mcp.dates import resolve
    from datetime import date
    assert resolve("2026-07") == date(2026, 7, 1)      # month -> first day
    assert resolve("2025-Q4") == date(2025, 12, 31)    # quarter -> END (H7 rule)
    assert resolve("2019") == date(2019, 1, 1)
    assert resolve("2026-01-15T09:00:00+00:00") == date(2026, 1, 15)
    assert resolve(None) is None
    assert resolve("last summer") is False             # rejected, never coerced


def test_every_writer_knows_its_own_page():
    """_write_section resolves date columns by (page, section), so a writer
    handed on alone must still say which page it belongs to."""
    from dma_mcp.promote import writer_registry
    for (page, section), w in writer_registry():
        assert w["page"] == page and w["section"] == section


def test_five_tiles_survive_promotion():
    """P1 submits FIVE platform tiles and production served ONE.

    `platform_story.gap_rows` was sourced from `section:platforms.0.gaps` —
    the first tile's gap rows, out of five tiles each carrying its own
    fit_score, gaps[] and story_md. Everything from rank 2 down was dropped
    inside the promote transaction, every gate passed, and a reader clicking
    the other four platforms found them empty ("when I click on each
    platform, not all surfaces are enriched for each platform").

    Asserted as the round trip that matters: what promote WRITES, read back
    by the serving projection, must still be five tiles with their own
    stories and their own gaps.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "api"))
    from dma_api.serving_spec import assemble, readers
    from dma_mcp.promote import _value

    tiles = [{"platform": f"Platform {n}", "rank": n,
              "fit_score": 80 - n, "story_md": f"story for platform {n}",
              "gaps": [{"subcap_id": f"P1C1.{n}.{g}", "current_score": 2.0}
                       for g in range(1, n + 1)]}
             for n in range(1, 6)]
    payload = {"platforms": tiles,
               "discarded": [{"platform": "Discarded", "reason": "r",
                              "relevance": 0.1}],
               "e_ids": ["E-X-001"], "internal_only": [],
               "produced_at": "2026-08-08T00:00:00Z"}

    spec = readers()[("platform", "platform_story")]
    assert spec["grain"] == "run"
    row = {}
    for w in json.loads(_SPEC_PATH.read_text())["specs"]:
        if w["page"] != "platform":
            continue
        writer = next(x for x in w["writers"] if x["section"] == "platform_story")
        for c in writer["columns"]:
            v = _value(c["source"], STAMPS, payload, None)
            if v is ...:
                continue
            row[c["column"]] = (json.dumps(v) if c.get("jsonb")
                                or isinstance(v, (dict, list)) else v)

    served = assemble("platform", "platform_story", [row])["data"]
    assert len(served["platforms"]) == 5, "promotion must not eat four tiles"
    for n, tile in enumerate(served["platforms"], start=1):
        assert tile["story_md"] == f"story for platform {n}"
        assert len(tile["gaps"]) == n
        assert tile["fit_score"] == 80 - n
    # and the rank-1 story is still in its own column, for readers that
    # predate the change — the same string, not a second version of it
    assert row["story"] == "story for platform 1"


def test_caps_and_item_provenance_survive_promotion():
    """"How come there are no caps from issues?" — because there was nowhere
    to put them.

    `capped_subcap_ids` is the reason an issue is on this register at all ("an
    issue is only interesting here because it CAPS something"): it validated at
    submit and had no column, so a client read a regulatory matter beside a
    score it appeared not to touch. Per-item `provenance` went the same way for
    a different reason — one envelope column was answering two questions.

    Both asserted through the same round trip as the platform tiles: what
    promote writes, read back by the serving projection.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "api"))
    from dma_api.serving_spec import assemble
    from dma_mcp.promote import _value

    payload = {"issues": [{
        "issue_id": "ISS-001", "title": "t", "severity": "S2", "status": "OPEN",
        "capped_subcap_ids": [{"subcap_id": "P4C4.2.1", "cap_level": 3.0}],
        "provenance": "analyst", "e_ids": ["E-1"],
        "linked_subcap_ids": ["P4C4.2.1"]}],
        "e_ids": ["E-1"], "internal_only": [],
        "produced_at": "2026-08-08T00:00:00Z"}
    writer = next(w for p in json.loads(_SPEC_PATH.read_text())["specs"]
                  if p["page"] == "context"
                  for w in p["writers"] if w["section"] == "issue_register")
    row = {}
    for c in writer["columns"]:
        v = _value(c["source"], STAMPS, payload, payload["issues"][0])
        if v is ...:
            continue
        row[c["column"]] = (json.dumps(v) if c.get("jsonb")
                            or isinstance(v, (dict, list)) else v)

    built = assemble("context", "issue_register", [row])
    issue = built["data"]["issues"][0]
    assert issue["capped_subcap_ids"] == [{"subcap_id": "P4C4.2.1",
                                           "cap_level": 3.0}]
    # Two facts, two columns: how THIS issue was arrived at, and who produced
    # the section. Neither may answer for the other.
    assert issue["provenance"] == "analyst"
    assert built["stamps"]["provenance"] == "producer"


def test_alert_status_is_initialised_at_promote():
    """heatmap_alerts.status has no DDL default and no contract field, so
    promote must set it — an alert promoted NULL is invisible to the alert
    dashboard and counts zero in serving_directory.open_alerts. Lowercase, to
    match alert_action_t, the enum of the actions that move it."""
    from dma_mcp.promote import LIFECYCLE_INITIAL, _value
    assert LIFECYCLE_INITIAL["heatmap_alerts"]["status"] == "open"
    assert _value("const:open", {}, {}, {}) == "open"


def test_a_retained_pass_is_revalidated_and_disclosed(seeded):
    """A retained PASS is a DATED OBSERVATION, not a current state.

    Validation runs at submit. Retention is correct and load-bearing —
    invariant 3 exists so fixing one page does not cost five re-syntheses
    — but a page keeps the verdict of the gate set it was submitted under,
    and every later promote carried it forward unexamined. Measured on the
    reference client: its context page holds a PASS from before CG-09
    learned `arc_shape`, and against today's gates the same stored payload
    returns seven blocking reasons. It is live, and its row says PASS.

    Disclosed, never refused: a gate that tightened after a page was
    authored is a reason to look, not a reason to strand five pages that
    are fine — and refusing would make every gate change retroactively
    un-promotable, which is how a build stops adding gates."""
    mcp, admin, rid = seeded
    _submit_all(mcp, rid)
    clean = promote_run(mcp, rid)
    assert clean["promoted"] is True
    assert "stale_verdicts" not in clean, \
        "pages that pass today's gates must not be named"

    # Reach past submit and corrupt a RETAINED payload the way a later gate
    # would see it — an off-vocabulary value CG-09 now refuses.
    cur = admin.cursor()
    cur.execute("""SELECT id, payload FROM submissions
                    WHERE run_id = %s AND page = 'context'
                      AND superseded_at IS NULL""", (rid,))
    sid, payload = cur.fetchone()
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload.setdefault("timeline", {})["arc_shape"] = "strategy-first, substrate-later"
    cur.execute("UPDATE submissions SET payload = %s WHERE id = %s",
                (json.dumps(payload), sid))
    admin.commit()

    out = promote_run(mcp, rid)
    assert out["promoted"] is True, "disclosure must not block the promote"
    assert "context" in out.get("stale_verdicts", {}), \
        "a retained PASS that today's gates refuse must be named"
    assert any(r["gate_id"] == "CG-09"
               for r in out["stale_verdicts"]["context"])
    assert "resubmit" in out["stale_verdicts_note"].lower()
