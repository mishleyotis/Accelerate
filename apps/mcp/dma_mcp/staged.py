"""Reading back what was staged — the missing half of submit.

WHY THIS EXISTS. The synthesis skill documents a repair flow, and invariant 3
is built to support it: promoted staging rows are RETAINED so that fixing one
card means resubmitting one page, not re-synthesising six. The skill's own
words: "Resubmit only the affected page — it supersedes that page's staged row.
Five pages come from the retained rows, one from your new submission."

That works exactly as long as the producer still holds the payload it sent. It
does not survive a session. Nothing in this connector could return a staged
submission, so a producer resuming on a promoted run could read the CONTRACT
for a page and the SERVED projection of it, and never the thing it would be
superseding.

Measured 2026-08-15 on the second client. A producer was asked to repair the
heatmap so that ten newly-evidenced cells would stop reading as alerts. It
declined, correctly, and said why: the only copy it could reach was a served
projection that had already lost `internal_only` on all nine sections, and
rebuilding 708 cells from a lossy dump risked turning a PASS into a FAIL for no
promotion benefit. The repair the architecture is designed to make cheap was
the one thing it could not do.

So: WRITE_PATH_WITH_NO_READ_PATH, at the connector, on the flow the whole
retention design exists to serve.

WHAT THIS RETURNS, and what it deliberately does not.

Staged rows, verbatim. No redaction, no `internal_only` stripping, no computed
fields. This is the producer tier talking to the producer — the serve layer's
audience rules are about what reaches a CLIENT, and applying them here would
hand back a payload that cannot be resubmitted, which is the bug it exists to
fix.

Section-scoped, because a contract-complete heatmap is 1.1-1.6 MB and no tool
result carries that. Called without a section it returns the INDEX: every
section's name, byte size and top-level keys, so a producer can see the shape
and ask for the one it is repairing. `cell_evidence` alone runs to 862 KB and
will not come back inline — the index says so per section rather than making
the caller discover it by failing.
"""
from __future__ import annotations

import json

from .transport import INLINE_SAFE_BYTES

#: A section larger than this is described rather than returned. The same
#: budget the write side uses, for the same reason: it is what one message can
#: carry and still have room for the call around it.
SECTION_INLINE_BYTES = INLINE_SAFE_BYTES


_COLS = """s.id, enum_label(s.status), s.payload, s.submitted_at,
           s.producer_version, s.contract_version, s.promoted_at"""


def _live_submission(cur, run_id, page):
    cur.execute(
        f"""SELECT {_COLS}
             FROM submissions s
            WHERE s.run_id = %s AND s.page = %s AND s.superseded_at IS NULL""",
        (run_id, page))
    return cur.fetchone()


def _by_id(cur, run_id, page, submission_id):
    """A named submission, superseded or not.

    THE HAZARD THIS CLOSES, hit on 2026-08-19 and worth stating plainly
    because the trap is invisible until you are in it.

    A resubmit SUPERSEDES the previous submission for that page. If the new
    payload is missing a section the old one carried — because the section
    was over the inline budget, so the read that built the new payload
    DESCRIBED it rather than returning it — then the resubmit fails on CG-01
    for the missing section, and the content is now unreachable: the tool
    returns only the live row, and the live row is the failure.

    Measured: a heatmap resubmit dropped `cell_evidence`, 1.36 MB across 697
    cells, which no producer is going to re-author. Nothing was lost from the
    DATABASE — the superseded row is still there with its payload intact — so
    the tool refusing to hand it back was the whole of the problem.

    Named explicitly rather than "give me the last PASS", because a producer
    recovering from this knows the id from `get_run_progress` and a rule that
    guesses which old row was meant is a rule that will guess wrong.
    """
    cur.execute(
        f"""SELECT {_COLS}
             FROM submissions s
            WHERE s.run_id = %s AND s.page = %s AND s.id = %s""",
        (run_id, page, submission_id))
    return cur.fetchone()


def _part_count(n: int) -> int:
    return max(1, -(-n // SECTION_INLINE_BYTES))


def get_staged_payload(conn, run_id, page: str, section: str = "",
                       submission_id: str = "", part: int = 0) -> dict:
    """The live staged submission for one page, or one section of it.

    Returns `{page, submission_id, status, submitted_at, producer_version,
    contract_version, promoted_at, sections: {...}}` where `sections` is the
    index when no section is named, and `{section: <verbatim>}` when one is.
    """
    cur = conn.cursor()
    if submission_id:
        row = _by_id(cur, run_id, page, submission_id)
        if row is None:
            return {"error": "unknown_submission", "page": page,
                    "submission_id": submission_id,
                    "hint": ("no submission with that id on this run and page. "
                             "`get_run_progress` names the live one; a "
                             "superseded id comes from your own record of what "
                             "you submitted.")}
    else:
        row = _live_submission(cur, run_id, page)
    if row is None:
        return {"error": "no_staged_submission",
                "page": page,
                "hint": (f"this run has no live submission for {page!r}. Pass "
                         "`submission_id` to read a SUPERSEDED one — that is "
                         "the recovery route when a resubmit dropped a section "
                         "the previous payload carried. Otherwise produce the "
                         "page.")}
    sub_id, status, payload, submitted_at, pver, cver, promoted_at = row
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    payload = payload if isinstance(payload, dict) else {}

    head = {
        "page": page,
        "submission_id": str(sub_id),
        "status": status,
        "submitted_at": submitted_at.isoformat() if submitted_at else None,
        "producer_version": pver,
        "contract_version": cver,
        "promoted_at": promoted_at.isoformat() if promoted_at else None,
        # Said plainly, because the whole point of handing this back is that it
        # goes out again: what you receive is what you would be superseding.
        "note": ("staged rows verbatim — not redacted, not the served "
                 "projection. Edit and resubmit; nothing here has been "
                 "stripped, so nothing has to be reconstructed."),
    }

    def _size(v):
        return len(json.dumps(v, separators=(",", ":"), default=str))

    if not section:
        index = {}
        for name, body in payload.items():
            n = _size(body)
            index[name] = {
                "bytes": n,
                "keys": sorted(body) if isinstance(body, dict) else None,
                "inline": n <= SECTION_INLINE_BYTES,
            }
        head["sections"] = index
        head["total_bytes"] = _size(payload)
        head["hint"] = (
            "call again with `section` for the one you are repairing. A "
            f"section over {SECTION_INLINE_BYTES} bytes has inline=false and "
            "will come back described rather than whole — repair those by "
            "producing them, not by round-tripping them.")
        return head

    if section not in payload:
        head["error"] = "unknown_section"
        head["hint"] = (f"{section!r} is not in this staged payload. It "
                        f"carries: {sorted(payload)}")
        return head

    body = payload[section]
    n = _size(body)
    if n > SECTION_INLINE_BYTES and not part:
        # DESCRIBED, NOT TRUNCATED. A truncated payload that looks whole is
        # worse than a refusal: a producer would resubmit it and silently
        # empty a section that was complete. Say the size, say how to get it
        # whole, and stop.
        head["section"] = section
        head["error"] = "section_too_large"
        head["bytes"] = n
        head["parts"] = _part_count(n)
        head["keys"] = sorted(body) if isinstance(body, dict) else None
        head["item_count"] = len(body) if isinstance(body, (list, dict)) else None
        head["hint"] = (
            f"{section!r} is {n} bytes, over the {SECTION_INLINE_BYTES}-byte "
            f"inline budget. Call again with part=1..{_part_count(n)} and "
            "concatenate the `chunk` strings in order, then json.loads the "
            "result — the same shape as the chunked WRITE, and for the same "
            "reason: a section you can submit in parts you must be able to "
            "read in parts. A truncated copy resubmitted would empty a "
            "complete section, which is why nothing partial is returned "
            "unless you ask for a numbered part.")
        return head

    if part:
        # THE READ HALF OF CHUNKED TRANSPORT. Added 2026-08-19 after a resubmit
        # dropped a 1.36 MB section and made it unrecoverable: the tool could
        # describe it and could not return it, so the only route left was
        # re-authoring 697 cells that were sitting intact in the database.
        #
        # Bytes, not items: the caller reassembles one JSON string, so the
        # split cannot depend on the section's shape. Splitting a list by
        # items would have to know it is a list.
        blob = json.dumps(body, separators=(",", ":"), default=str)
        total = _part_count(len(blob))
        if part < 1 or part > total:
            head["section"] = section
            head["error"] = "no_such_part"
            head["parts"] = total
            head["hint"] = f"parts are numbered 1..{total} for this section."
            return head
        lo = (part - 1) * SECTION_INLINE_BYTES
        head["section"] = section
        head["part"] = part
        head["parts"] = total
        head["bytes"] = len(blob)
        head["chunk"] = blob[lo:lo + SECTION_INLINE_BYTES]
        head["hint"] = (
            f"part {part} of {total}. Concatenate every part's `chunk` in "
            "order and json.loads the result; each chunk alone is not valid "
            "JSON and is not meant to be.")
        return head

    head["section"] = section
    head["data"] = body
    head["bytes"] = n
    return head
