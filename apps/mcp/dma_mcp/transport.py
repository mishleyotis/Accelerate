"""Chunked payload transport (MEM-0030) — a whole payload, in more than one breath.

## The defect

`submit_page_payload` took `payload` as an inline JSON object, so a producing
agent had to emit the entire page as literal tokens inside ONE tool call. A
contract-complete heatmap does not fit. Measured 2026-08-08 by two independent
producers: Frost Bank 1,128,742 bytes compact (~282k tokens), `cell_evidence`
alone 862,351 across 697 served cells; Fisher Investments heatmap 1,598,147
chars, `cell_evidence` 1,208,289 across 708 cells — and the barest still-
compliant reduction of that section is still 347,509 chars.

Rule 17 requires a drawer row for every served cell, so this is the contract's
size, not an authoring choice. The reference client `baxter-credit-union-bcu`
serves 69 cell_evidence rows out of 765 cells — 9% — which was never a synthesis
decision. It is what fit.

## Why chunked-and-assembled, and not by-reference

The rejected alternative was a by-reference submit: the producer writes the
payload to a GCS object and the connector reads it. It loses on four counts.

1. It does not actually reduce what the producer must emit. The bytes are
   written either way; by-reference only moves them from tool arguments to a
   file write, which has its own per-call ceiling. You end up chunking anyway —
   with a weaker story about what was validated.
2. It needs the producer to hold a bucket credential. The producing agent's
   only server-side capability today is this connector. A bucket it can write
   and the connector reads on trust makes the BUCKET the door, which is
   invariant 2 read backwards; and proving the object came from the claimed
   producer is an authentication problem the connector does not have.
3. The credential is either a service-account key we would have to issue and
   store, or a signed upload URL — a secret in a URL, which lands in the Cowork
   transcript and in Cloud Run request logs. That is explicitly out of bounds.
4. `dmai-mcp` holds only `objectViewer` on the artefact bucket and `dmai-worker`
   is provisioned as its only writer. Turning it into a producer inbox
   contradicts the provisioning model on purpose.

The cost of the shape actually chosen is honest and small: the server holds
partial state between calls, and there are more round trips. Both are contained.
A part is INERT — no gate reads it, no writer can see it, `promote_run` does not
know it exists — and only the assembled whole ever becomes a submission.

## The shape

    open_payload(run_id, page, producer_version)      -> upload_id (server-allocated)
    append_payload_part(upload_id, part, parts_total, path, items= | fields=)
    ...
    submit_page_payload(run_id, page, upload_id=..., expect={path: length})

Two operations, both applied in ascending part index so the same set of parts
always assembles to the same bytes:

  * `fields={...}` shallow-MERGES an object at a dotted path
  * `items=[...]`  APPENDS to the list at a dotted path

Path `""` is the payload root, so a small section arrives whole
(`path="", fields={"linking_stats": {...}}`) and a large one arrives as an
envelope merge plus N appends to `cell_evidence.cells`.

## Atomicity

`parts_total` is declared on every part and must agree across all of them.
Submit refuses unless the received set is exactly {1..parts_total}: a gap is
named by index under CG-16 and NO submission row is written. `expect` adds the
second half — the producer declares the assembled length of each appended list
and CG-17 checks it against what was actually assembled, which catches the one
truncation a JSON parse cannot see: a list cut short at a valid element
boundary.

Neither gate touches content. `validate_pass1` and `validate_pass2` run over the
assembled payload byte-for-byte as they always have.
"""
from __future__ import annotations

import hashlib
import hmac
import json

# What a producing model can reliably emit in one tool call. Derived from the
# measurement, not guessed: 1,128,742 bytes came to ~282k tokens, so ~4 bytes a
# token; a producer with ~32k tokens of output budget for one message can carry
# roughly 128 KiB of compact JSON and still have room for the call scaffolding.
INLINE_SAFE_BYTES = 131_072
RECOMMENDED_PART_BYTES = 131_072
# Server-side ceiling on a single part. Generous — it exists so one runaway part
# cannot make the connector hold an unbounded string, not to police the producer.
MAX_PART_BYTES = 1_048_576
# Abandoned uploads are swept opportunistically at open time.
UPLOAD_TTL_HOURS = 48


def limits() -> dict:
    """The transport envelope, as `get_page_contract` reports it."""
    return {
        "inline_max_bytes": INLINE_SAFE_BYTES,
        "recommended_part_bytes": RECOMMENDED_PART_BYTES,
        "max_part_bytes": MAX_PART_BYTES,
        "upload_ttl_hours": UPLOAD_TTL_HOURS,
    }


def _canonical(payload) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=False).encode("utf-8")


def measure(payload) -> dict:
    """Bytes and digest of a payload as the connector sees it. The digest is
    returned in the verdict so a producer can prove WHICH assembly was
    validated — the question "did all of it arrive" needs an answer that is not
    the producer's own arithmetic."""
    raw = _canonical(payload)
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


# ── path walking ────────────────────────────────────────────────────────
def _segments(path: str) -> list:
    return [s for s in str(path or "").split(".") if s != ""]


def _descend(root: dict, segs: list, create: bool):
    """Walk to the container named by `segs`; returns None where a segment
    cannot be walked (a missing key with create=False, or a scalar in the way)."""
    node = root
    for seg in segs:
        if isinstance(node, list):
            if not seg.isdigit() or int(seg) >= len(node):
                return None
            node = node[int(seg)]
            continue
        if not isinstance(node, dict):
            return None
        if seg not in node or node[seg] is None:
            if not create:
                return None
            node[seg] = {}
        node = node[seg]
    return node


def read_path(payload: dict, path: str):
    """The value at a dotted path, or None. Used by the `expect` check."""
    segs = _segments(path)
    if not segs:
        return payload
    node = _descend(payload, segs[:-1], create=False)
    leaf = segs[-1]
    if isinstance(node, dict):
        return node.get(leaf)
    if isinstance(node, list) and leaf.isdigit() and int(leaf) < len(node):
        return node[int(leaf)]
    return None


def apply_part(payload: dict, op: str, path: str, body) -> str | None:
    """Apply one part to the assembly in place. Returns an error string, or
    None on success — assembly errors are transport errors, never gate
    reasons, and they name the part that could not be placed."""
    segs = _segments(path)
    if op == "merge":
        if not isinstance(body, dict):
            return "merge body must be an object"
        target = _descend(payload, segs, create=True)
        if not isinstance(target, dict):
            return f"path {path!r} does not name an object"
        for k, v in body.items():
            target[k] = v
        return None
    if op == "append":
        if not isinstance(body, list):
            return "append body must be a list"
        if not segs:
            return "cannot append at the payload root — the root is an object"
        parent = _descend(payload, segs[:-1], create=True)
        leaf = segs[-1]
        if not isinstance(parent, dict):
            return f"path {path!r} has no object to hold its list"
        existing = parent.get(leaf)
        if existing is None:
            parent[leaf] = list(body)
        elif isinstance(existing, list):
            existing.extend(body)
        else:
            return (f"path {path!r} already holds a "
                    f"{type(existing).__name__}, not a list")
        return None
    return f"unknown op {op!r}"


# ── the tools ───────────────────────────────────────────────────────────
def open_payload(conn, run_id, page: str, producer_version: str = "",
                 opened_by: str = "svc_mcp") -> dict:
    from .contracts import PAGES
    cur = conn.cursor()
    if page not in PAGES:
        return {"ok": False, "error": "unknown_page",
                "message": f"unknown page {page!r}; pages are {list(PAGES)}"}
    cur.execute("SELECT 1 FROM runs WHERE id = %s", (run_id,))
    if cur.fetchone() is None:
        return {"ok": False, "error": "unknown_run",
                "message": f"unknown run {run_id}"}
    # opportunistic sweep: an abandoned transmission is garbage, and garbage
    # with a foreign key to a run is still garbage
    cur.execute(
        "DELETE FROM payload_uploads WHERE state = 'OPEN' "
        f"AND opened_at < now() - interval '{UPLOAD_TTL_HOURS} hours'")
    cur.execute(
        """INSERT INTO payload_uploads (run_id, page, producer_version,
                                        opened_by)
           VALUES (%s,%s,%s,%s) RETURNING id, opened_at""",
        (run_id, page, producer_version or None, opened_by))
    upload_id, opened_at = cur.fetchone()
    conn.commit()
    return {
        "ok": True,
        "upload_id": str(upload_id),
        "run_id": str(run_id),
        "page": page,
        "opened_at": opened_at.isoformat(),
        "limits": limits(),
        "how": ("Send every part with the SAME parts_total. `fields` "
                "shallow-merges an object at `path`; `items` appends to the "
                "list at `path`; path '' is the payload root. Then call "
                "submit_page_payload(run_id, page, upload_id=...) — the "
                "assembled whole is what is validated and staged. A gap in "
                "the part sequence refuses the submission and names the "
                "missing indexes; nothing partial can be staged."),
    }


def append_payload_part(conn, upload_id, part: int, parts_total: int,
                        path: str = "", items=None, fields=None,
                        item_count: int = 0) -> dict:
    cur = conn.cursor()
    cur.execute("""SELECT run_id, enum_label(page), parts_total, state
                     FROM payload_uploads WHERE id = %s""", (upload_id,))
    row = cur.fetchone()
    if row is None:
        return {"ok": False, "error": "unknown_upload",
                "message": f"no open payload upload {upload_id} — call "
                           "open_payload(run_id, page) first; the connector "
                           "allocates the id"}
    run_id, page, declared, state = row
    if state != "OPEN":
        return {"ok": False, "error": "upload_closed",
                "message": "this upload has already been assembled and "
                           "submitted; open a new one rather than appending "
                           "to the record of what was validated"}
    if not isinstance(part, int) or part < 1:
        return {"ok": False, "error": "bad_part_index",
                "message": "part is a 1-based integer index"}
    if not isinstance(parts_total, int) or parts_total < 1:
        return {"ok": False, "error": "bad_parts_total",
                "message": "parts_total is the number of parts this payload "
                           "will arrive in — declare it on every part; it is "
                           "what makes an incomplete transmission detectable"}
    if part > parts_total:
        return {"ok": False, "error": "part_out_of_range",
                "message": f"part {part} is above the declared parts_total "
                           f"{parts_total}"}
    if declared is not None and declared != parts_total:
        return {"ok": False, "error": "parts_total_disagreement",
                "message": f"this upload was opened declaring "
                           f"{declared} parts and part {part} declares "
                           f"{parts_total} — one transmission, one declared "
                           "length. Open a new upload if the plan changed"}

    if (items is None) == (fields is None):
        return {"ok": False, "error": "one_body",
                "message": "send exactly one of `items` (append to the list "
                           "at `path`) or `fields` (shallow-merge an object "
                           "at `path`)"}
    if items is not None:
        if not isinstance(items, list):
            return {"ok": False, "error": "bad_items",
                    "message": "`items` must be a list"}
        op, body = "append", items
        n_items = len(items)
    else:
        if not isinstance(fields, dict):
            return {"ok": False, "error": "bad_fields",
                    "message": "`fields` must be an object"}
        op, body = "merge", fields
        n_items = len(fields)
    if item_count and item_count != n_items:
        return {"ok": False, "error": "item_count_mismatch",
                "message": f"part {part} declares item_count={item_count} and "
                           f"carries {n_items} — a part that arrived short is "
                           "a part that was truncated in transit; resend it"}

    raw = _canonical(body)
    if len(raw) > MAX_PART_BYTES:
        return {"ok": False, "error": "part_too_large",
                "message": f"part {part} is {len(raw)} bytes, above the "
                           f"{MAX_PART_BYTES}-byte ceiling — split it "
                           f"(recommended {RECOMMENDED_PART_BYTES} bytes a "
                           "part) and raise parts_total on every part of the "
                           "new plan"}

    # a retry after a dropped connection REPLACES its part; it never doubles it
    cur.execute("""INSERT INTO payload_upload_parts
                     (upload_id, part, op, path, body, bytes, item_count)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (upload_id, part) DO UPDATE
                     SET op = EXCLUDED.op, path = EXCLUDED.path,
                         body = EXCLUDED.body, bytes = EXCLUDED.bytes,
                         item_count = EXCLUDED.item_count,
                         received_at = now()
                   RETURNING (xmax <> 0)""",
                (upload_id, part, op, path or "", json.dumps(body),
                 len(raw), n_items))
    replaced = bool(cur.fetchone()[0])
    if declared is None:
        cur.execute("UPDATE payload_uploads SET parts_total = %s WHERE id = %s",
                    (parts_total, upload_id))
    conn.commit()

    cur.execute("""SELECT count(*), coalesce(sum(bytes), 0),
                          coalesce(sum(item_count), 0)
                     FROM payload_upload_parts WHERE upload_id = %s""",
                (upload_id,))
    received, total_bytes, total_items = cur.fetchone()
    missing = _missing_parts(cur, upload_id, parts_total)
    return {"ok": True, "upload_id": str(upload_id), "run_id": str(run_id),
            "page": page, "part": part, "op": op, "path": path or "",
            "replaced": replaced, "part_bytes": len(raw),
            "parts_received": received, "parts_total": parts_total,
            "missing_parts": missing, "bytes_received": int(total_bytes),
            "items_received": int(total_items),
            "complete": not missing}


def _missing_parts(cur, upload_id, parts_total: int) -> list:
    cur.execute("SELECT part FROM payload_upload_parts WHERE upload_id = %s",
                (upload_id,))
    have = {r[0] for r in cur.fetchall()}
    return [i for i in range(1, (parts_total or 0) + 1) if i not in have]


def _reason(gate, path, message):
    return {"gate_id": gate, "section": None, "path": path,
            "message": message, "severity": "block"}


def assemble_parts(rows, parts_total: int, expect=None) -> tuple:
    """The assembly itself, with no database in it → (payload, reasons, meta).

    `rows` is [(part, op, path, body)] in any order; parts are applied in
    ascending index so the same set always assembles to the same bytes. Kept
    separate from `assemble` precisely so the atomicity guarantee — an
    incomplete set produces a payload of None and a reason naming the gap — is
    provable without a database standing in the way.
    """
    have = {int(r[0]) for r in rows}
    missing = [i for i in range(1, (parts_total or 0) + 1) if i not in have]
    if not parts_total:
        return None, [_reason(
            "CG-16", "upload_id",
            "this upload has no parts — a payload of nothing is not an empty "
            "payload, it is a transmission that never started")], {}
    if missing:
        return None, [_reason(
            "CG-16", "upload_id",
            f"{len(have)} of {parts_total} declared parts arrived; missing "
            f"{missing} — an incomplete payload is refused whole. Resend the "
            "missing parts against this same upload_id (a part index is "
            "replaced, never duplicated) and submit again")], {}

    payload: dict = {}
    for part, op, path, body in sorted(rows, key=lambda r: int(r[0])):
        if isinstance(body, (str, bytes)):    # driver-dependent jsonb decoding
            body = json.loads(body)
        err = apply_part(payload, op, path, body)
        if err:
            return None, [_reason(
                "CG-16", f"part[{part}].{path or '<root>'}",
                f"part {part} could not be placed: {err}. The assembled whole "
                "is what gets validated, so a part that cannot be placed "
                "refuses the submission rather than being dropped")], {}

    reasons = []
    for path, want in (expect or {}).items():
        got = read_path(payload, path)
        n = len(got) if isinstance(got, (list, dict)) else None
        if n != want:
            reasons.append(_reason(
                "CG-17", path,
                f"the producer declared {want} at {path!r} and the assembled "
                f"payload carries {n if n is not None else 'no list'} — a "
                "list cut short at a valid element boundary still parses, so "
                "the declared length is the only thing that catches it. "
                "Resend the short part and submit again"))
    if reasons:
        return None, reasons, {}

    meta = measure(payload)
    meta["parts"] = parts_total
    return payload, [], meta


def assemble(conn, upload_id, run_id, page: str, expect=None) -> tuple:
    """→ (payload, reasons, meta). A non-empty `reasons` means NOTHING is
    submittable: the caller must return the verdict without writing a
    submission row. That is the whole atomicity guarantee — there is no state
    in which a partially transmitted payload reaches `submissions`."""
    cur = conn.cursor()
    cur.execute("""SELECT run_id, enum_label(page), parts_total, state,
                          submission_id
                     FROM payload_uploads WHERE id = %s""", (upload_id,))
    row = cur.fetchone()
    if row is None:
        return None, [_reason("CG-16", "upload_id",
                              f"no payload upload {upload_id} — open one with "
                              "open_payload(run_id, page); the connector "
                              "allocates the id")], {}
    up_run, up_page, parts_total, state, submission_id = row
    if str(up_run) != str(run_id) or up_page != page:
        return None, [_reason(
            "CG-16", "upload_id",
            f"upload {upload_id} was opened for run {up_run} page "
            f"{up_page!r} and this submit names run {run_id} page {page!r} — "
            "an upload is bound to one run and one page at open, so a part "
            "cannot be misrouted into another page's payload")], {}
    if state != "OPEN":
        return None, [_reason(
            "CG-16", "upload_id",
            f"upload {upload_id} was already assembled into submission "
            f"{submission_id} — an upload is submitted once. Open a new one "
            "to resubmit; the prior live row is superseded as usual")], {}
    cur.execute("""SELECT part, op, path, body FROM payload_upload_parts
                    WHERE upload_id = %s ORDER BY part""", (upload_id,))
    return assemble_parts(cur.fetchall(), parts_total, expect=expect)


def close_upload(conn, upload_id, submission_id) -> None:
    """Mark the upload spent, naming the submission it assembled into. The
    parts are kept: they are the record of what the server actually
    validated."""
    cur = conn.cursor()
    cur.execute("""UPDATE payload_uploads
                      SET state = 'CLOSED', closed_at = now(),
                          submission_id = %s
                    WHERE id = %s AND state = 'OPEN'""",
                (submission_id, upload_id))
    conn.commit()


class HeaderPathToken:
    """ASGI wrapper: accept the capability token as a HEADER on static /mcp.

    Why (owner, 2026-08-20): a plugin whose server URL embeds the token
    cannot connect until a human pastes it into plugin config, so every
    install sat "MCP pending" — and a token in the URL is also what an
    xtrace or an access log prints (the 2026-08-20 leak printed the
    capability URL). With the token in `X-DMA-Path-Token`, the plugin ships
    a static URL, its headers helper fetches the token itself from Secret
    Manager at connection time, and install-to-tools needs no manual step
    anywhere an identity exists. Cloud Run IAM remains the identity gate in
    front of all of this; the token stays defense in depth.

    A request to /mcp with the right header (constant-time compare) is
    rewritten to the mounted capability path. The URL-segment form keeps
    working — the rotation story is unchanged, because clients read the
    secret per connection. A wrong or missing header falls through
    untouched and meets the same 404 as any wrong path: never a
    distinguishable error, so the header is not an oracle.
    """

    def __init__(self, inner, token: str):
        self.inner = inner
        self.token = token

    async def __call__(self, scope, receive, send):
        if (scope.get("type") == "http"
                and scope.get("path", "").rstrip("/") == "/mcp"):
            supplied = ""
            for name, value in scope.get("headers") or ():
                if name == b"x-dma-path-token":
                    supplied = value.decode("latin-1").strip()
                    break
            if supplied and hmac.compare_digest(supplied, self.token):
                scope = dict(scope)
                scope["path"] = f"/mcp/{self.token}"
                scope["raw_path"] = scope["path"].encode("latin-1")
        await self.inner(scope, receive, send)
