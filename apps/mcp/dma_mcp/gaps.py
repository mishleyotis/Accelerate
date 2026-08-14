"""The empty fields on a promoted run, computed — never stored, never clicked.

Build owner, 2026-08-14: "Never place an em dash. There should always be a way
to send a signal to the MCP to give us an enrichment of the empty field with the
em dash."

An em dash is a dead end in two directions. It reads the same whether the
producer searched and found nothing, held a figure that failed the identity
gate, or was never asked — and a reader who meets one has no route to getting it
filled. This module is the second half: the route.

WHY IT IS COMPUTED RATHER THAN QUEUED. The obvious design is a table a reader
writes to. It was rejected, by the build owner, for the reason invariant 8
already gives about counts: where a source of truth exists, the value is
recomputed and never stored. The set of empty fields IS derivable at any moment
from the promoted payload against the contract, so a stored queue could only
disagree with reality — it would go stale the instant a page was re-promoted,
and a request nobody dequeued would keep asking for a field that had since been
filled. Computed, the worklist cannot drift, cannot be forgotten, and needs no
new write path anywhere (invariant 2 stands untouched: the API still writes only
annotations and alert actions).

So the signal is not a click. It is that this list exists and the producer reads
it. Every gap a reader sees on a surface is already in it.

WHAT COUNTS AS A GAP, and the distinction the whole module turns on:

    stated            a value is present                    -> not a gap
    held              null, quarantined, WITH a reason       -> not a gap; it is
                                                                a finding, and
                                                                the reason is
                                                                the content
    silent            null, or absent from the payload       -> A GAP
    empty-declared    the section declares an empty_state
                      with a ladder                          -> not a gap; the
                                                                search happened
                                                                and is recorded

A held field and a silent one look identical on a page rendering em dashes.
That is precisely the damage: one is the assessment's most defensible output and
the other is a hole, and the reader could not tell them apart.
"""
from __future__ import annotations

from . import contracts
from .contracts import ENVELOPE

# The submission's own machinery — provenance, thread, reasoning layer — not
# client-facing content. A null one is not a gap a producer closes by
# searching, so they are never reported as such. Imported from the contract
# rather than restated, plus the section-level keys that are structure: a list
# held in two places is the drift this build keeps paying for.
ENVELOPE_KEYS = frozenset(ENVELOPE) | frozenset((
    "r_layer", "narrative_thread", "provenance", "submission_id",
    "claim_label", "grounded_on", "section", "page", "run_id",
))

# A boolean's ABSENCE is its value. `sub_vertical_undefined`, `identity_mismatch`
# and `verified_sparse` are declarations a run makes when they are true and
# omits when they are not, so reporting them as empty would put nine permanent
# non-gaps at the top of every worklist and teach the producer to skim it.
NON_GAP_TYPES = frozenset(("boolean",))


def _is_empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == []


def _held(item) -> tuple[bool, str]:
    """A quarantined field WITH a stated reason is held, not silent."""
    if not isinstance(item, dict):
        return False, ""
    reason = str(item.get("quarantine_reason") or "").strip()
    if item.get("quarantined") and reason:
        return True, reason
    return False, ""


def _empty_declared(body) -> bool:
    es = body.get("empty_state") if isinstance(body, dict) else None
    return (isinstance(es, dict) and bool(es.get("reason"))
            and isinstance(es.get("sources_searched"), list)
            and len(es["sources_searched"]) > 0)


def _member_gaps(page, section, fname, spec, val, out) -> None:
    """A must-present member that is silent. The strongest gap class there is:
    the contract names it on every sub-vertical, so its absence is never a
    property of this client."""
    members = list(spec.get("must_present") or [])
    if not members:
        return
    key = spec.get("must_present_key", "field")
    stated, held = {}, {}
    for item in val or []:
        if not isinstance(item, dict):
            continue
        name = _norm(item.get(key))
        if not name:
            continue
        is_held, reason = _held(item)
        if not _is_empty(item.get("value")):
            stated[name] = True
        elif is_held:
            held[name] = reason
    for want in members:
        n = _norm(want)
        if n in stated or n in held:
            continue
        out.append({
            "page": page, "section": section,
            "path": f"{section}.{fname}[{want}]",
            "field": want, "kind": "must_present_member",
            "reason": (f"{want!r} is named in the contract's must-present set "
                       f"for every sub-vertical and this run neither states it "
                       f"nor holds it with a reason"),
            "doc": (spec.get("doc") or "")[:400],
            "closes_with": "state the value with its provenance, or run the "
                           "absence ladder and mark it quarantined with a "
                           "quarantine_reason",
        })


def _norm(s) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")


def gaps_for_section(page: str, section: str, body: dict) -> list:
    """Every silent field in one promoted section body."""
    out: list = []
    if not isinstance(body, dict):
        return out
    spec_all = contracts.sections(page) or {}
    spec = (spec_all.get(section) or {})
    fields = spec.get("fields") or spec
    declared = _empty_declared(body)

    for fname, fspec in (fields or {}).items():
        if fname in ENVELOPE_KEYS or not isinstance(fspec, dict):
            continue
        val = body.get(fname)
        if isinstance(fspec.get("must_present"), list):
            _member_gaps(page, section, fname, fspec, val, out)
        if fspec.get("type") in NON_GAP_TYPES or not _is_empty(val):
            continue
        # A section that declared its empty state with a ladder has already
        # answered for the whole section; re-reporting each field would drown
        # the real gaps in a run that did its work honestly.
        if declared or fspec.get("may_be_empty"):
            continue
        out.append({
            "page": page, "section": section, "path": f"{section}.{fname}",
            "field": fname,
            "kind": "empty_required" if fspec.get("required") else "empty_optional",
            "reason": (f"{fname!r} is empty on the promoted run and the section "
                       f"declares no empty state"),
            "doc": (fspec.get("doc") or "")[:400],
            "closes_with": ("send the value" if fspec.get("required") else
                            "send the value, or declare the section's "
                            "empty_state with the ladder that established the "
                            "absence"),
        })
    return out


def gaps_for_payload(page: str, payload: dict) -> list:
    out: list = []
    for section, body in (payload or {}).items():
        out.extend(gaps_for_section(page, section, body))
    return out


def list_enrichment_gaps(conn, run_id, page: str | None = None) -> dict:
    """Every empty field on a run's live submissions — the producer's worklist.

    Reads the STAGED submissions, not the served projection. That distinction
    has cost this build twice: the serve layer strips `internal_only` paths and
    redacts `entity_ids` from cohort patterns for every audience, so a gap list
    built from what the API returns would report the redaction machinery working
    correctly as content the producer failed to write.

    Ordered so the list is workable rather than merely complete: must-present
    members first (the contract names them on every sub-vertical, so their
    absence is never a property of this client), then required fields, then
    optional ones.
    """
    cur = conn.cursor()
    cur.execute(
        """SELECT enum_label(page), payload
             FROM submissions
            WHERE run_id = %s AND superseded_at IS NULL""", (run_id,))
    rows = cur.fetchall()
    if not rows:
        return {"run_id": str(run_id), "gaps": [], "pages_read": [],
                "note": "no live submissions on this run — nothing staged to "
                        "read. Gaps are computed from what was submitted; a "
                        "run with no submissions has no fields to be empty"}

    order = {"must_present_member": 0, "empty_required": 1, "empty_optional": 2}
    out, pages_read = [], []
    for pg, payload in rows:
        if page and pg != page:
            continue
        pages_read.append(pg)
        out.extend(gaps_for_payload(pg, payload or {}))
    out.sort(key=lambda g: (order.get(g["kind"], 3), g["page"], g["path"]))
    counts: dict = {}
    for g in out:
        counts[g["kind"]] = counts.get(g["kind"], 0) + 1
    return {"run_id": str(run_id), "pages_read": sorted(pages_read),
            "gaps": out, "count": len(out), "by_kind": counts}
