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

import json as _json
from pathlib import Path as _Path


def _contract_paths():
    here = _Path(__file__).resolve()
    return [here.parent / "contracts_data.json",
            here.parents[2] / "apps" / "mcp" / "dma_mcp" / "contracts_data.json"]


_CONTRACTS = None


def _load():
    global _CONTRACTS
    if _CONTRACTS is None:
        for p in _contract_paths():
            if p.exists():
                _CONTRACTS = _json.loads(p.read_text())
                return _CONTRACTS
        raise FileNotFoundError(
            "contracts_data.json is not beside this module. deploy.sh stages "
            "packages/shared into each image that reads it; a gap computation "
            "without the contract would report every field as present.")
    return _CONTRACTS


class contracts:                     # namespace shim, same call shape as mcp
    @staticmethod
    def sections(page):
        return _load().get(page) or {}


ENVELOPE = ("e_ids", "empty_state", "internal_only", "produced_at",
            "producer_version")

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
        # Mirrors CG-18: a member may be a list of aliases for one fact, any
        # of which satisfies it. Held here in step with validation.py because a
        # worklist that asks for a field the gate already accepts sends the
        # producer looking for something it has.
        aliases = want if isinstance(want, (list, tuple)) else [want]
        norms = [_norm(a) for a in aliases]
        want = aliases[0]
        if any(n in stated or n in held for n in norms):
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
    # A page's section map also carries `_notes`, which is a LIST. Nothing in
    # a payload is ever named `_notes`, so this never fired in production — but
    # the worklist is the product, and it must not be one malformed section
    # away from raising instead of returning.
    if not isinstance(spec, dict):
        return out
    # Key presence, not truthiness. `heatmap.value_chain` declares `fields: {}`
    # — the producer authors the envelope and nothing else — and `{}` is falsy,
    # so `spec.get("fields") or spec` fell through to the SECTION spec, iterated
    # its own keys, and found the literal key "fields" mapping to a dict. The
    # worklist then reported `value_chain.fields` as a gap: a field that exists
    # in no payload, whose only compliant closure is inventing a key the
    # contract does not have. The fallthrough itself is still needed for
    # sections whose spec IS the field map.
    fields = spec["fields"] if "fields" in spec else spec
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
        # ── A worklist item whose only closure is fabrication is worse than
        #    no worklist item at all ─────────────────────────────────────────
        #
        # Audited 2026-08-15 across all six pages, every claim adversarially
        # verified (14 of 23 refuted). Two classes survived, and the contract
        # already states both — they were simply not read.
        #
        # `not_producer_authored`: the producer CANNOT write it. The serve
        # layer computes it, or the connector writes it at submit. Telling a
        # producer to "send the value" for
        # `evidence_coverage.self_sourced_basis` — whose doc reads "COMPUTED AT
        # READ — do not send" — asks it to contradict the contract to satisfy
        # the worklist. These are dropped outright: no run, no client and no
        # amount of searching can ever close one.
        if fspec.get("not_producer_authored"):
            continue
        # `absence_is_correct_when`: the producer MAY write it, on a run in a
        # different state. `financial_series.trend` is null BY MANDATE below
        # three dated points; `quarantine_reason` exists only when the identity
        # gate quarantined the series. These are NOT dropped — on a run where
        # the condition does not hold they are true gaps, and dropping them
        # would hide real holes — but they are demoted below every ordinary
        # gap and they carry the condition, so a producer reads the state
        # before it reads an instruction.
        when = fspec.get("absence_is_correct_when")
        required = fspec.get("required")
        out.append({
            "page": page, "section": section, "path": f"{section}.{fname}",
            "field": fname,
            "kind": "conditional" if when else
                    ("empty_required" if required else "empty_optional"),
            "reason": (
                f"{fname!r} is empty. The contract says absence is CORRECT "
                f"when {when} — check that first; this is a gap only if it "
                f"does not hold" if when else
                f"{fname!r} is empty on the promoted run and the section "
                f"declares no empty state"),
            "doc": (fspec.get("doc") or "")[:400],
            "closes_with": (
                f"nothing, if {when}. Otherwise send the value" if when else
                ("send the value" if required else
                 "send the value, or declare the section's empty_state with "
                 "the ladder that established the absence")),
        })
    return out


def gaps_for_payload(page: str, payload: dict) -> list:
    out: list = []
    for section, body in (payload or {}).items():
        out.extend(gaps_for_section(page, section, body))
    return out


def attempts_for_run(conn, run_id) -> dict:
    """What the enrichment routine already tried, keyed by the gap's path.

    Migration 0047 granted svc_mcp SELECT on these tables for exactly this —
    "the producer session reads what the routine already resolved so it does
    not re-run a search that has an answer" — and then nothing read them. The
    hourly job resolved BCU's website to a value, recorded it, and
    `list_enrichment_gaps` went on reporting the field as untouched: the
    producer would have run the same search again and had no way to know.

    That is the write-path-with-no-read-path shape inside the machinery built
    to close it, which is why this is here rather than in a later stage.

    Both halves matter and for different reasons. A RESOLVED attempt saves the
    search and, more importantly, carries the value's PROVENANCE — the producer
    still has to register it as evidence and submit it through the connector,
    because a resolved attempt is a lead and not a promotion (invariant 2). An
    UNRESOLVED attempt is the more valuable of the two on a second pass: it says
    which route was tried and why it failed, so the producer neither repeats a
    dead search nor mistakes an unattempted field for an exhausted one.

    Returns {} when the tables are absent or unreadable. The worklist is the
    product here; degrading it to a bare list is correct, and failing to
    produce one because a history table is missing is not.
    """
    out: dict = {}
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT a.field_path, a.status, a.value, a.unit, a.as_of,
                      a.reason, a.resolver, a.source_url, a.excerpt,
                      a.confidence, a.attempted_at
                 FROM enrichment_attempts a
                WHERE a.run_id = %s
                ORDER BY a.attempted_at DESC, a.id DESC""",
            (run_id,))
        rows = cur.fetchall()
    except Exception:
        # A missing grant or a table that does not exist yet must not take the
        # worklist down with it.
        try:
            conn.rollback()
        except Exception:
            pass
        return {}

    for (path, status, value, unit, as_of, reason, resolver, source_url,
         excerpt, confidence, attempted_at) in rows:
        # Newest first, so the first row per path is the current answer and
        # every earlier attempt on that path is superseded history.
        if path in out:
            continue
        rec = {
            "status": status,
            "resolver": resolver,
            "attempted_at": attempted_at.isoformat() if attempted_at else None,
        }
        if status == "RESOLVED":
            rec.update({
                "value": value, "unit": unit,
                "as_of": as_of.isoformat() if as_of else None,
                "source_url": source_url, "excerpt": excerpt,
                "confidence": confidence,
                # Said plainly, because a resolved attempt looks like a done
                # job and is not one. The value is a LEAD: it still has to be
                # registered as evidence and submitted through the connector,
                # which is the only path content may take (invariant 2).
                "still_to_do": ("register_evidence with this source, then "
                                "submit the field citing the id you are "
                                "given — a resolved attempt is a lead, not a "
                                "promotion"),
            })
        else:
            rec["reason"] = reason
        out[path] = rec
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

    # `conditional` sits last on purpose: it is the only kind whose correct
    # resolution is often "do nothing", so it must never sit above a gap that
    # genuinely needs work.
    order = {"must_present_member": 0, "empty_required": 1, "empty_optional": 2,
             "conditional": 3}
    out, pages_read = [], []
    for pg, payload in rows:
        if page and pg != page:
            continue
        pages_read.append(pg)
        out.extend(gaps_for_payload(pg, payload or {}))
    # What the routine already tried, joined onto the gap it was trying to
    # close. Ordering puts a gap with an answer waiting at the top of its own
    # kind: it is the cheapest one to close and leaving it buried is how the
    # answer goes unused for another hour.
    tried = attempts_for_run(conn, run_id)
    for g in out:
        a = tried.get(g["path"])
        if a:
            g["enrichment_attempt"] = a
    out.sort(key=lambda g: (
        order.get(g["kind"], 3),
        0 if (g.get("enrichment_attempt") or {}).get("status") == "RESOLVED" else 1,
        g["page"], g["path"]))
    counts: dict = {}
    for g in out:
        counts[g["kind"]] = counts.get(g["kind"], 0) + 1
    resolved = sum(1 for g in out
                   if (g.get("enrichment_attempt") or {}).get("status") == "RESOLVED")
    attempted = sum(1 for g in out if g.get("enrichment_attempt"))
    return {"run_id": str(run_id), "pages_read": sorted(pages_read),
            "gaps": out, "count": len(out), "by_kind": counts,
            # Stated at the top level because a producer scanning the list
            # needs to know an answer is waiting before it starts searching.
            "with_resolved_value": resolved,
            "attempted_by_routine": attempted,
            "never_attempted": len(out) - attempted}
