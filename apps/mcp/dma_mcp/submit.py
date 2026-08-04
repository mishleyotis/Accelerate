"""submit_page_payload (stage 2.5) — validate, supersede, stage, verdict.

Resubmission supersedes cleanly: the prior live row is marked superseded
by the new one in the same transaction — no merge, no accumulation, no
cleanup. The verdict is stored with the submission and returned whole.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .gates import ensure_gate_registry
from .validation import validate_pass1
from .validation2 import validate_pass2

_CONTRACT_VERSION = None


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


def submit_page_payload(conn, run_id, page: str, payload: dict,
                        provenance: str = "producer",
                        producer_version: str | None = None,
                        submitted_by: str = "svc_mcp",
                        encoder=None) -> dict:
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
    counts = _counts(payload)

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
    conn.commit()
    return {"submission_id": str(submission_id),
            "verdict": {"status": status.lower(), "reasons": reasons,
                        "warnings": warnings, "counts": counts}}


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
