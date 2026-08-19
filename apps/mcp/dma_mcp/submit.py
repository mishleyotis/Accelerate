"""submit_page_payload (stage 2.5) — validate, supersede, stage, verdict.

Resubmission supersedes cleanly: the prior live row is marked superseded
by the new one in the same transaction — no merge, no accumulation, no
cleanup. The verdict is stored with the submission and returned whole.

Two transports, one validation. `payload=` carries the page inline, as it
always has; `upload_id=` names a chunked upload (dma_mcp/transport.py,
MEM-0030) that the connector assembles server-side first. Beyond the point
where `payload` is in hand the two paths are the same code: both passes run
over the assembled whole, exactly as they did before the chunked path
existed. Transport refusals (CG-16 parts, CG-17 declared length) happen
BEFORE any submission row is written, so a partially transmitted payload has
no state in which it is submittable.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import transport
from .gates import ensure_gate_registry
from . import memory as memory_mod
from . import rejections
from .validation import validate_pass1
from .validation2 import validate_pass2

_CONTRACT_VERSION = None

# migrations/versions/0002_enumerated_types.py provenance_t
PROVENANCE_T = frozenset(("analyst", "derived", "producer"))


def contract_version() -> str:
    """Identity of the payload shapes this connector validates against."""
    global _CONTRACT_VERSION
    if _CONTRACT_VERSION is None:
        data = Path(__file__).with_name("contracts_data.json").read_bytes()
        _CONTRACT_VERSION = "cr-" + hashlib.sha256(data).hexdigest()[:12]
    return _CONTRACT_VERSION


def _counts(payload: dict) -> dict:
    e_ids = set()
    for body in payload.values() if isinstance(payload, dict) else []:
        if isinstance(body, dict):
            e_ids.update(x for x in (body.get("e_ids") or [])
                         if isinstance(x, str))
    return {"sections": len(payload) if isinstance(payload, dict) else 0,
            "e_ids_used": len(e_ids)}


def _fail(reasons) -> dict:
    """A refusal that writes nothing. Used for every check that runs BEFORE a
    submission row exists — transport included, which is what makes an
    incomplete transmission unsubmittable rather than merely invalid."""
    return {"submission_id": None,
            "verdict": {"status": "fail", "reasons": reasons,
                        "warnings": [], "counts": {}}}


def submit_page_payload(conn, run_id, page: str, payload: dict = None,
                        provenance: str = "producer",
                        producer_version: str | None = None,
                        submitted_by: str = "svc_mcp",
                        encoder=None, upload_id: str = "",
                        expect: dict = None) -> dict:
    ensure_gate_registry(conn)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM runs WHERE id = %s", (run_id,))
    if cur.fetchone() is None:
        return {"submission_id": None,
                "verdict": {"status": "fail",
                            "reasons": [{"gate_id": "ET-01", "section": None,
                                         "path": "run_id",
                                         "message": f"unknown run {run_id}",
                                         "severity": "block"}],
                            "warnings": [], "counts": {}}}
    if not producer_version:
        return {"submission_id": None,
                "verdict": {"status": "fail",
                            "reasons": [{"gate_id": "CG-05", "section": None,
                                         "path": "producer_version",
                                         "message": "producer_version is "
                                         "required — every promoted row "
                                         "carries it non-null",
                                         "severity": "block"}],
                            "warnings": [], "counts": {}}}
    # provenance is the envelope's provenance CLASS (Schema §06 provenance_t),
    # not free text. A structured refusal naming the three values beats the
    # raw 22P02 the INSERT would raise — the first production submission of
    # this connector lost a round trip to exactly that.
    if provenance not in PROVENANCE_T:
        return {"submission_id": None,
                "verdict": {"status": "fail",
                            "reasons": [{"gate_id": "CG-05", "section": None,
                                         "path": "provenance",
                                         "message": (
                                             f"provenance {provenance!r} is not one of "
                                             f"{' · '.join(sorted(PROVENANCE_T))} — it is the "
                                             "envelope's provenance class, not a description "
                                             "of the inputs"),
                                         "severity": "block"}],
                            "warnings": [], "counts": {}}}

    from .contracts import PAGES
    if page not in PAGES:
        # a structured refusal, never a raw enum error from the INSERT
        return {"submission_id": None,
                "verdict": {"status": "fail",
                            "reasons": [{"gate_id": "CG-01", "section": None,
                                         "path": "page",
                                         "message": f"unknown page {page!r}; "
                                                    f"pages are {list(PAGES)}",
                                         "severity": "block"}],
                            "warnings": [], "counts": {}}}

    # ── transport: inline, or assembled from a chunked upload ──────────
    #
    # Everything below this block is transport-blind. The two paths differ only
    # in where `payload` came from, and the assembled whole is what both
    # validation passes then read — MEM-0030 is a transport defect and its fix
    # changes no gate that judges content.
    transport_meta = {"transport": "inline"}
    if upload_id and payload is not None:
        return _fail([{"gate_id": "CG-05", "section": None, "path": "payload",
                       "message": "send either `payload` (inline) or "
                                  "`upload_id` (a chunked upload assembled "
                                  "server-side), never both — two sources for "
                                  "one page is two payloads, and only one of "
                                  "them would be validated",
                       "severity": "block"}])
    if upload_id:
        payload, t_reasons, meta = transport.assemble(
            conn, upload_id, run_id, page, expect=expect)
        if t_reasons:
            # NOTHING is written: an incomplete transmission never reaches
            # `submissions`, so it can never be promoted
            return _fail(t_reasons)
        transport_meta = {"transport": "chunked", "parts": meta["parts"],
                          "assembled_bytes": meta["bytes"],
                          "assembled_sha256": meta["sha256"]}
    elif payload is None:
        return _fail([{"gate_id": "CG-05", "section": None, "path": "payload",
                       "message": "no payload — send `payload` inline, or "
                                  "`upload_id` from open_payload for a page "
                                  "too large to emit in one call (see "
                                  "get_page_contract(page)['transport'])",
                       "severity": "block"}])
    else:
        m = transport.measure(payload)
        transport_meta["assembled_bytes"] = m["bytes"]
        transport_meta["assembled_sha256"] = m["sha256"]

    reasons = validate_pass1(page, payload)
    # Pass 2 always runs too — more named conflicts per verdict means
    # fewer repair round trips. Its SG results DISCLOSE (warnings), never
    # block; everything else joins the blocking reasons.
    warnings = []
    if isinstance(payload, dict):
        p2, sg = validate_pass2(conn, run_id, page, payload, encoder=encoder)
        reasons.extend(p2)
        warnings.extend(sg)
    status = "FAIL" if any(r["severity"] == "block" for r in reasons) else "PASS"
    # The transport facts ride in `counts`, not in a gate: how the bytes
    # arrived, how many there were and their digest. A producer that has just
    # sent 1.6 MB in fourteen parts should be able to read back, from the
    # stored verdict, exactly which assembly was judged.
    counts = {**_counts(payload), **transport_meta}

    # Supersede-then-insert: the live-row unique index (one live
    # submission per run+page) demands the old row steps aside first.
    cur.execute(
        """UPDATE submissions SET superseded_at = now()
            WHERE run_id = %s AND page = %s AND superseded_at IS NULL
            RETURNING id""", (run_id, page))
    prior = cur.fetchone()
    cur.execute(
        """INSERT INTO submissions
             (run_id, page, payload, status, provenance, producer_version,
              contract_version, submitted_by, submitted_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now()) RETURNING id""",
        (run_id, page, json.dumps(payload), status, provenance,
         producer_version, contract_version(), submitted_by))
    submission_id = cur.fetchone()[0]
    if prior:
        cur.execute("UPDATE submissions SET superseded_by = %s WHERE id = %s",
                    (submission_id, prior[0]))
    cur.execute(
        """INSERT INTO submission_verdicts
             (submission_id, status, reasons, warnings, counts, evaluated_at)
           VALUES (%s,%s,%s,%s,%s, now())""",
        (submission_id, status, json.dumps(reasons), json.dumps(warnings),
         json.dumps(counts)))

    # THE REFUSAL GETS A NAME AND A QUEUE, on every submit — pass or fail.
    # A pass is what CLOSES the tickets the last failure opened, so doing this
    # only on failure would leave a queue that never empties. Before this,
    # a refused payload superseded a passing row and then sat there: nothing
    # listed it across runs, so a producer session that ended left no trace
    # anything was outstanding, and all three refusals measured on this build
    # were found by a human reading a verdict.
    #
    # Never fatal. A submission is the producer's work and a bookkeeping
    # failure must not cost it — the verdict above is already committed to.
    try:
        rejection_report = rejections.record_verdict(
            conn, run_id, page, submission_id, reasons, producer_version)
    except Exception as exc:                       # noqa: BLE001 — reported
        rejection_report = {"error": str(exc)[:200]}
    # WHAT THIS STORE ALREADY KNOWS, delivered where it is actionable.
    #
    # The findings memory has held defect classes, their measurements and the
    # refinements that closed them since migration 0034, and on 2026-08-19 the
    # producer skill named none of its tools on any of its 40 pages. A memory
    # a producer must remember to consult is a memory nobody consults: every
    # run started from zero and the same classes were rediscovered by a reader
    # looking at a rendered page.
    #
    # So recall is attached to the refusal that earned it, exactly as the
    # rejection ledger is. Never fatal: a memory that can break a submit is
    # worse than one that is silent.
    try:
        memory_recall = memory_mod.recall_for_gates(
            conn, [r.get("gate_id") for r in reasons if isinstance(r, dict)])
    except Exception as exc:                       # noqa: BLE001 — reported
        memory_recall = {"error": str(exc)[:200]}
    conn.commit()
    if upload_id:
        # spent, and naming what it became. The parts stay: they are the
        # record of what the server actually assembled and validated.
        transport.close_upload(conn, upload_id, submission_id)
    return {"submission_id": str(submission_id),
            "verdict": {"status": status.lower(), "reasons": reasons,
                        "warnings": warnings, "counts": counts},
            # The identifiers the brief asks for: a refined copy is submitted
            # against the same page and clears the very rows it was opened
            # against, so "did the repair land" is answerable without diffing
            # payloads — and `attempts` past two says the repair is looping.
            "rejections": rejection_report,
            # `known` is empty when this store has nothing on these gates;
            # `checked` says which gates were asked, so "nothing known" is
            # distinguishable from "never asked".
            "memory": memory_recall}


def get_validation_verdict(conn, submission_id) -> dict:
    cur = conn.cursor()
    cur.execute(
        """SELECT s.id, s.run_id, enum_label(s.page), enum_label(s.status),
                  s.submitted_at, s.superseded_at IS NOT NULL,
                  v.reasons, v.warnings, v.counts
             FROM submissions s
             LEFT JOIN LATERAL (SELECT reasons, warnings, counts
                                  FROM submission_verdicts
                                 WHERE submission_id = s.id
                                 ORDER BY id DESC LIMIT 1) v ON TRUE
            WHERE s.id = %s""", (submission_id,))
    row = cur.fetchone()
    if row is None:
        return {"error": "unknown_submission", "submission_id": str(submission_id)}
    sid, run_id, page, status, submitted_at, superseded, reasons, warnings, counts = row
    return {"submission_id": str(sid), "run_id": str(run_id), "page": page,
            "status": (status or "").lower(),
            "submitted_at": submitted_at.isoformat() if submitted_at else None,
            "superseded": superseded,
            "verdict": {"status": (status or "").lower(),
                        "reasons": reasons or [], "warnings": warnings or [],
                        "counts": counts or {}}}
