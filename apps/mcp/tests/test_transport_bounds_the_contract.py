"""MEM-0030 · TRANSPORT_BOUNDS_THE_CONTRACT — the payload the interface could not carry.

The defect, measured 2026-08-08 by two independent producers:

  * Frost Bank        heatmap 1,128,742 bytes compact (~282k tokens);
                      `cell_evidence` alone 862,351 across 697 served cells
  * Fisher Investments heatmap 1,598,147 chars; `cell_evidence` 1,208,289
                      across 708 cells; the barest still-compliant reduction
                      of that section still 347,509

`submit_page_payload` took the payload as an inline JSON object, so all of that
had to be emitted as literal tokens inside one tool call. It could not be, and
the failure mode was not an error — it was a smaller payload that validated
perfectly. `baxter-credit-union-bcu` serves 69 `cell_evidence` rows out of 765
cells (9%) on a clean verdict, which was never a synthesis decision.

These tests build cell_evidence at the MEASURED scale and assert the four
properties the fix has to have:

  1. the section really is far past what one inline call can carry, so the
     chunked path is not optional for it;
  2. the parts assemble, in any arrival order, to exactly the payload the
     producer built — byte for byte;
  3. validation sees no difference: pass 1 over the assembled payload returns
     the same reasons as pass 1 over the inline one. This is a transport
     change, not a validation change, and this test is what says so;
  4. an incomplete transmission is refused, by index, and produces no payload
     at all — the assembled whole or nothing.
"""
import json
import os
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_mcp import transport
from dma_mcp.contracts import get_page_contract
from dma_mcp.submit import submit_page_payload
from dma_mcp.validation import validate_pass1

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"

# The two measurements this module exists because of.
FROST_CELLS = 697
FROST_CELL_EVIDENCE_BYTES = 862_351
FISHER_CELLS = 708

ENVELOPE = {"produced_at": "2026-08-08T12:00:00Z",
            "producer_version": "transport-proof@2026-08-08",
            "e_ids": [], "internal_only": []}


def _cell(i: int) -> dict:
    """One drawer row of the shape the H2 contract states, at the length the
    contract's own prompts ask for (synthesis 40-90 words, excerpt 50-500
    chars per cited item). Nothing here is padding: a shorter item would make
    the test pass by measuring something the contract does not permit."""
    subcap = f"P{1 + i % 4}C{1 + i % 4}.{i}"
    e_ids = [f"E-{i:04d}-{k}" for k in range(3)]
    return {
        "subcap_id": subcap,
        "e_ids": e_ids,
        "grounded_on": len(e_ids),
        "thin": False,
        "provenance": "producer",
        "reach_note": ("Three research-workbook rows map to this "
                       "subcapability by sheet subject and were each checked "
                       "against the capability before linking."),
        "synthesis": (
            "The evidence establishes a working capability at this cell: the "
            "institution operates the function in production, describes it in "
            "its own material, and the two independent sources agree on "
            "scope. Against the peer median the position sits marginally "
            "ahead, which is worth protecting rather than extending, because "
            "the downstream cells that depend on it are the ones carrying the "
            "gap. " + f"Cell {subcap} carries three linked items."),
        "items": [
            {"e_id": e, "tier": "T2", "claim_label": "operational",
             "recency": "CURRENT", "source_title": f"Annual disclosure {i}",
             "publisher": "Institution",
             "excerpt": ("The platform processes originations end to end and "
                         "has done so since the migration completed, with "
                         "servicing handled on the same system of record. "
                         f"Reference {e}.")}
            for e in e_ids
        ],
    }


def _cell_evidence(n: int) -> dict:
    return {"cell_evidence": {
        **ENVELOPE,
        "cells": [_cell(i) for i in range(n)],
        "linking_stats": {"cells_scored": n, "cells_linked": n,
                          "rows_unlinkable": 0},
    }}


def _chunk(payload: dict, part_bytes: int) -> list:
    """The producer's side: envelope and scalars as a merge, `cells` in
    batches. Returns [(part, op, path, body)] the way the parts table holds
    them."""
    section = payload["cell_evidence"]
    head = {k: v for k, v in section.items() if k != "cells"}
    rows = [(1, "merge", "cell_evidence", head)]
    batch, size, part = [], 0, 1
    for cell in section["cells"]:
        raw = len(json.dumps(cell, separators=(",", ":")))
        if batch and size + raw > part_bytes:
            part += 1
            rows.append((part, "append", "cell_evidence.cells", batch))
            batch, size = [], 0
        batch.append(cell)
        size += raw
    if batch:
        part += 1
        rows.append((part, "append", "cell_evidence.cells", batch))
    return rows


# ── 1 · the section really does not fit ────────────────────────────────
def test_frost_bank_cell_evidence_does_not_fit_in_one_inline_call():
    payload = _cell_evidence(FROST_CELLS)
    measured = transport.measure(payload)["bytes"]
    # the shape built here is the same order of magnitude as the real one —
    # if this ever drops under the measured 862,351 the fixture has been
    # trimmed below what the contract asks for
    assert measured > 700_000, (
        f"{measured} bytes for {FROST_CELLS} cells is below the shape the H2 "
        "contract states; the fixture has been trimmed, not the payload")
    assert measured > 5 * transport.INLINE_SAFE_BYTES, (
        f"{measured} bytes against an inline ceiling of "
        f"{transport.INLINE_SAFE_BYTES} — this is the defect, and it is not "
        "close")


def test_the_contract_states_the_transport_so_the_next_producer_reads_it():
    """The second-order fix: a producer should learn the limit from the
    contract, not by building 1.6 MB and failing."""
    contract = get_page_contract("heatmap")
    t = contract["transport"]
    assert t["inline_max_bytes"] == transport.INLINE_SAFE_BYTES
    assert "cells" in t["chunked"]["chunkable_fields"]["cell_evidence"]
    assert any(m["bytes"] == FROST_CELL_EVIDENCE_BYTES
               for m in t["measured"]["sections"]["cell_evidence"]["measured_bytes"])
    assert any(m["items"] == FISHER_CELLS
               for m in t["measured"]["sections"]["cell_evidence"]["measured_bytes"])
    assert t["measured"]["finding"].startswith("MEM-0030")
    # and it says what NOT to do, because both producers were right to refuse
    assert "cutting served rows" in t["rule"] or "reduce the payload" in t["rule"]
    # every page answers, not only the one that was measured
    for page in ("overview", "insights", "platform", "context", "techstack"):
        assert get_page_contract(page)["transport"]["inline_max_bytes"] > 0


# ── 2 · the parts assemble to exactly what was built ───────────────────
def test_parts_assemble_byte_for_byte_in_any_arrival_order():
    payload = _cell_evidence(FROST_CELLS)
    rows = _chunk(payload, transport.RECOMMENDED_PART_BYTES)
    assert len(rows) > 6, "the fixture should need real chunking"
    for _part, _op, _path, body in rows:
        assert len(json.dumps(body, separators=(",", ":"))) <= transport.MAX_PART_BYTES

    shuffled = list(rows)
    random.Random(30).shuffle(shuffled)
    assembled, reasons, meta = transport.assemble_parts(
        shuffled, len(rows), expect={"cell_evidence.cells": FROST_CELLS})
    assert reasons == []
    assert transport.measure(assembled) == transport.measure(payload)
    assert meta["bytes"] == transport.measure(payload)["bytes"]
    assert meta["parts"] == len(rows)
    assert len(assembled["cell_evidence"]["cells"]) == FROST_CELLS
    # order within the list is the producer's order, not arrival order
    assert [c["subcap_id"] for c in assembled["cell_evidence"]["cells"]] == \
           [c["subcap_id"] for c in payload["cell_evidence"]["cells"]]


# ── 3 · validation is unchanged ────────────────────────────────────────
def test_validation_sees_no_difference_between_inline_and_assembled():
    """The claim the whole change rests on: every gate runs over the assembled
    payload exactly as it runs over an inline one."""
    payload = _cell_evidence(120)
    rows = _chunk(payload, transport.RECOMMENDED_PART_BYTES)
    assembled, reasons, _meta = transport.assemble_parts(rows, len(rows))
    assert reasons == []
    assert validate_pass1("heatmap", assembled) == validate_pass1("heatmap", payload)

    # and a payload that is WRONG is wrong identically through both transports
    payload["cell_evidence"]["invented_field"] = 1
    del payload["cell_evidence"]["linking_stats"]
    rows = _chunk(payload, transport.RECOMMENDED_PART_BYTES)
    assembled, _r, _m = transport.assemble_parts(rows, len(rows))
    inline_gates = sorted(r["gate_id"] for r in validate_pass1("heatmap", payload))
    chunked_gates = sorted(r["gate_id"] for r in validate_pass1("heatmap", assembled))
    assert inline_gates == chunked_gates
    assert "CG-04" in chunked_gates and "CG-02" in chunked_gates


# ── 4 · an incomplete transmission is refused, by index ────────────────
def test_a_missing_part_is_refused_and_names_what_is_missing():
    payload = _cell_evidence(FROST_CELLS)
    rows = _chunk(payload, transport.RECOMMENDED_PART_BYTES)
    dropped = [r for r in rows if r[0] not in (3, 5)]
    assembled, reasons, meta = transport.assemble_parts(dropped, len(rows))
    assert assembled is None, "an incomplete payload must not assemble at all"
    assert meta == {}
    assert len(reasons) == 1 and reasons[0]["gate_id"] == "CG-16"
    assert reasons[0]["severity"] == "block"
    assert "[3, 5]" in reasons[0]["message"]
    assert f"of {len(rows)} declared parts" in reasons[0]["message"]


def test_zero_parts_is_a_transmission_that_never_started():
    assembled, reasons, _ = transport.assemble_parts([], 0)
    assert assembled is None
    assert reasons[0]["gate_id"] == "CG-16"


def test_a_list_truncated_at_an_element_boundary_is_caught_by_the_declared_length():
    """The one truncation a JSON parse cannot see: the last part arrives with
    fewer items than it should and everything still parses."""
    payload = _cell_evidence(200)
    rows = _chunk(payload, transport.RECOMMENDED_PART_BYTES)
    short = [(p, o, path, body[:-4] if o == "append" and p == rows[-1][0] else body)
             for p, o, path, body in rows]
    assembled, reasons, _ = transport.assemble_parts(
        short, len(rows), expect={"cell_evidence.cells": 200})
    assert assembled is None
    assert reasons[0]["gate_id"] == "CG-17"
    assert "196" in reasons[0]["message"] and "200" in reasons[0]["message"]

    # without the declaration it assembles quietly short — which is precisely
    # why the declaration exists, and why a producer should always send it
    quiet, no_reasons, _ = transport.assemble_parts(short, len(rows))
    assert no_reasons == [] and len(quiet["cell_evidence"]["cells"]) == 196


# ── the placement rules the two ops promise ────────────────────────────
def test_merge_and_append_compose_in_either_order():
    for order in ([("merge", "cell_evidence", {**ENVELOPE}),
                   ("append", "cell_evidence.cells", [_cell(0)])],
                  [("append", "cell_evidence.cells", [_cell(0)]),
                   ("merge", "cell_evidence", {**ENVELOPE})]):
        payload = {}
        for op, path, body in order:
            assert transport.apply_part(payload, op, path, body) is None
        assert payload["cell_evidence"]["producer_version"] == ENVELOPE["producer_version"]
        assert len(payload["cell_evidence"]["cells"]) == 1


def test_a_part_that_cannot_be_placed_refuses_rather_than_being_dropped():
    payload = {"cell_evidence": {"cells": "not-a-list"}}
    err = transport.apply_part(payload, "append", "cell_evidence.cells", [{}])
    assert err and "not a list" in err

    rows = [(1, "merge", "cell_evidence", {"cells": "not-a-list"}),
            (2, "append", "cell_evidence.cells", [_cell(0)])]
    assembled, reasons, _ = transport.assemble_parts(rows, 2)
    assert assembled is None
    assert reasons[0]["gate_id"] == "CG-16" and "part[2]" in reasons[0]["path"]


def test_root_path_carries_a_whole_small_section():
    payload = {}
    assert transport.apply_part(
        payload, "merge", "", {"linking_stats": {"cells_scored": 3}}) is None
    assert payload["linking_stats"]["cells_scored"] == 3
    assert transport.read_path(payload, "linking_stats.cells_scored") == 3


def test_the_transport_gates_are_in_the_registry():
    from dma_mcp.gates import GATES
    for gate in ("CG-16", "CG-17"):
        assert gate in GATES
        assert GATES[gate][4] == "block"


# ── the round trip, against a database ─────────────────────────────────
@pytest.fixture()
def run_row():
    try:
        mcp = pg8000.dbapi.connect(user="dmai-mcp@digital-maturity-assessor.iam",
                                   password="local", host=HOST, port=5432,
                                   database="dma_insights")
        admin = pg8000.dbapi.connect(user="dmai-migrate@digital-maturity-assessor.iam",
                                     password="local", host=HOST, port=5432,
                                     database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()
    cur.execute("SELECT to_regclass('public.payload_uploads')")
    if cur.fetchone()[0] is None:
        pytest.skip("local database predates migration 0040")
    cur.execute("SELECT id FROM entities WHERE display_id = 'synthetic-transport-bank'")
    for (old,) in cur.fetchall():
        _purge(cur, old)
    admin.commit()
    cur.execute("""INSERT INTO entities (display_id, status, created_at)
                   VALUES ('synthetic-transport-bank','ACTIVE', now()) RETURNING id""")
    eid = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status)
                   VALUES (%s,'DMA-ASM-STB-20260808-01',1,'INGESTED') RETURNING id""",
                (eid,))
    rid = cur.fetchone()[0]
    admin.commit()
    yield mcp, str(rid)
    mcp.rollback()
    _purge(cur, eid)
    admin.commit()
    mcp.close()
    admin.close()


def _purge(cur, entity_id):
    cur.execute("""DELETE FROM payload_uploads WHERE run_id IN
                     (SELECT id FROM runs WHERE entity_id = %s)""", (entity_id,))
    cur.execute("""DELETE FROM gate_results WHERE run_id IN
                     (SELECT id FROM runs WHERE entity_id = %s)""", (entity_id,))
    cur.execute("""DELETE FROM submission_verdicts WHERE submission_id IN
                     (SELECT id FROM submissions WHERE run_id IN
                        (SELECT id FROM runs WHERE entity_id = %s))""", (entity_id,))
    cur.execute("""DELETE FROM submissions WHERE run_id IN
                     (SELECT id FROM runs WHERE entity_id = %s)""", (entity_id,))
    cur.execute("DELETE FROM runs WHERE entity_id = %s", (entity_id,))
    cur.execute("DELETE FROM entities WHERE id = %s", (entity_id,))


def _send(conn, run_id, payload, part_bytes=transport.RECOMMENDED_PART_BYTES):
    opened = transport.open_payload(conn, run_id, "heatmap",
                                    producer_version="transport-proof@1")
    assert opened["ok"], opened
    rows = _chunk(payload, part_bytes)
    for part, op, path, body in rows:
        kw = {"items": body} if op == "append" else {"fields": body}
        r = transport.append_payload_part(conn, opened["upload_id"], part,
                                          len(rows), path=path, **kw)
        assert r["ok"], r
    return opened["upload_id"], rows


def test_frost_bank_scale_cell_evidence_submits_whole_through_the_chunked_path(run_row):
    """The end the whole change is for: ~700 contract-complete drawer rows,
    far past anything one tool call can carry, staged as ONE payload."""
    mcp, rid = run_row
    payload = _cell_evidence(FROST_CELLS)
    inline_bytes = transport.measure(payload)["bytes"]
    upload_id, rows = _send(mcp, rid, payload)

    out = submit_page_payload(
        mcp, rid, "heatmap", upload_id=upload_id,
        producer_version="transport-proof@1",
        expect={"cell_evidence.cells": FROST_CELLS})
    counts = out["verdict"]["counts"]
    assert out["submission_id"], out["verdict"]["reasons"][:2]
    assert counts["transport"] == "chunked"
    assert counts["parts"] == len(rows)
    assert counts["assembled_bytes"] == inline_bytes
    assert counts["assembled_sha256"] == transport.measure(payload)["sha256"]

    # what was STAGED is the whole payload, not what fit
    cur = mcp.cursor()
    cur.execute("SELECT payload FROM submissions WHERE id = %s",
                (out["submission_id"],))
    stored = cur.fetchone()[0]
    if isinstance(stored, str):
        stored = json.loads(stored)
    assert len(stored["cell_evidence"]["cells"]) == FROST_CELLS
    # the verdict is a FAIL only for the OTHER heatmap sections, never for a
    # cell_evidence that did not arrive
    assert not [r for r in out["verdict"]["reasons"]
                if r["gate_id"] in ("CG-16", "CG-17")]

    # the upload is spent, and says what it became
    cur.execute("SELECT state, submission_id FROM payload_uploads WHERE id = %s",
                (upload_id,))
    state, sub = cur.fetchone()
    assert state == "CLOSED" and str(sub) == out["submission_id"]


def test_an_incomplete_transmission_writes_no_submission_row(run_row):
    """Atomicity at the submit boundary: a payload that did not all arrive is
    not merely invalid, it is unsubmittable."""
    mcp, rid = run_row
    payload = _cell_evidence(200)
    opened = transport.open_payload(mcp, rid, "heatmap",
                                    producer_version="transport-proof@1")
    rows = _chunk(payload, transport.RECOMMENDED_PART_BYTES)
    for part, op, path, body in rows[:-1]:            # last part never sent
        kw = {"items": body} if op == "append" else {"fields": body}
        transport.append_payload_part(mcp, opened["upload_id"], part, len(rows),
                                      path=path, **kw)

    out = submit_page_payload(mcp, rid, "heatmap",
                              upload_id=opened["upload_id"],
                              producer_version="transport-proof@1")
    assert out["submission_id"] is None
    assert out["verdict"]["reasons"][0]["gate_id"] == "CG-16"
    assert str(len(rows)) in out["verdict"]["reasons"][0]["message"]
    cur = mcp.cursor()
    cur.execute("SELECT count(*) FROM submissions WHERE run_id = %s", (rid,))
    assert cur.fetchone()[0] == 0, "an incomplete payload reached submissions"

    # the missing part arrives and the same upload submits
    part, op, path, body = rows[-1]
    transport.append_payload_part(mcp, opened["upload_id"], part, len(rows),
                                  path=path, items=body)
    out = submit_page_payload(mcp, rid, "heatmap",
                              upload_id=opened["upload_id"],
                              producer_version="transport-proof@1",
                              expect={"cell_evidence.cells": 200})
    assert out["submission_id"]
    assert out["verdict"]["counts"]["parts"] == len(rows)


def test_a_resent_part_replaces_and_never_duplicates(run_row):
    mcp, rid = run_row
    payload = _cell_evidence(60)
    opened = transport.open_payload(mcp, rid, "heatmap")
    rows = _chunk(payload, 20_000)
    for part, op, path, body in rows:
        kw = {"items": body} if op == "append" else {"fields": body}
        transport.append_payload_part(mcp, opened["upload_id"], part, len(rows),
                                      path=path, **kw)
    part, op, path, body = rows[-1]
    again = transport.append_payload_part(mcp, opened["upload_id"], part,
                                          len(rows), path=path, items=body,
                                          item_count=len(body))
    assert again["replaced"] is True
    assert again["parts_received"] == len(rows) and again["complete"]
    out = submit_page_payload(mcp, rid, "heatmap",
                              upload_id=opened["upload_id"],
                              producer_version="transport-proof@1",
                              expect={"cell_evidence.cells": 60})
    assert out["submission_id"]


def test_an_upload_is_bound_to_its_run_and_page_and_spent_once(run_row):
    mcp, rid = run_row
    payload = _cell_evidence(10)
    upload_id, rows = _send(mcp, rid, payload)
    wrong = submit_page_payload(mcp, rid, "overview", upload_id=upload_id,
                                producer_version="transport-proof@1")
    assert wrong["submission_id"] is None
    assert wrong["verdict"]["reasons"][0]["gate_id"] == "CG-16"

    ok = submit_page_payload(mcp, rid, "heatmap", upload_id=upload_id,
                             producer_version="transport-proof@1")
    assert ok["submission_id"]
    twice = submit_page_payload(mcp, rid, "heatmap", upload_id=upload_id,
                                producer_version="transport-proof@1")
    assert twice["submission_id"] is None
    assert "already assembled" in twice["verdict"]["reasons"][0]["message"]
    assert not transport.append_payload_part(
        mcp, upload_id, 1, len(rows), path="", fields={"x": 1})["ok"]


def test_both_transports_or_neither_is_refused(run_row):
    mcp, rid = run_row
    both = submit_page_payload(mcp, rid, "heatmap", payload={"cell_evidence": {}},
                               upload_id="00000000-0000-0000-0000-000000000000",
                               producer_version="p@1")
    assert both["submission_id"] is None
    assert both["verdict"]["reasons"][0]["path"] == "payload"
    neither = submit_page_payload(mcp, rid, "heatmap", producer_version="p@1")
    assert neither["submission_id"] is None
    assert "get_page_contract" in neither["verdict"]["reasons"][0]["message"]


def test_the_inline_path_still_works_and_records_its_own_measurement(run_row):
    mcp, rid = run_row
    payload = _cell_evidence(3)
    out = submit_page_payload(mcp, rid, "heatmap", payload=payload,
                              producer_version="transport-proof@1")
    assert out["verdict"]["counts"]["transport"] == "inline"
    assert out["verdict"]["counts"]["assembled_bytes"] == \
        transport.measure(payload)["bytes"]
