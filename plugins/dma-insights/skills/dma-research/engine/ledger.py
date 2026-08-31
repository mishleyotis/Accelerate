#!/usr/bin/env python3
"""Recording, and the budget check that used to crash.

WHY THIS EXISTS.

  AUD-0008 / AUD-0036  `ledger.py stats` raised NameError on every single
      invocation — `stats()` called `iterate(run, _stats)` where `_stats` was
      a local of `compact()`. R27 names that command as the token-budget
      checkpoint ('>=40 search-ops this conversation -> checkpoint and STOP'),
      so the defence the owner named by name had no working measurement.
  AUD-0037  and even had it run, nothing acted on it: orient reported 45/40,
      said 'state clean', handed over the next card and exited 0.
  AUD-0009 / AUD-0016  an unmodified skeleton was accepted as a synthesis and
      closed the subcap, because the write path validated nothing.

So: every write goes through here, every write is checked BEFORE it lands,
and `stats` both works and returns a decision rather than a number.
"""
from __future__ import annotations

# Runnable both ways. `python3 -m engine.<mod>` is the documented invocation,
# but every audit and every operator reaches for `python3 <path> --help`
# first, and a relative import dies there. Binding __package__ makes the two
# equivalent instead of making one of them a trap.
if __package__ in (None, ""):  # noqa: E402  (must precede the relative imports)
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import datetime as _dt
import json
import re

from . import contract as C
from . import quality as Q
from .workbook import RunWorkbook, FLOOR_ITEMS, _split_ids

#: R27's wall. A conversation that has fired this many searches must
#: checkpoint and stop; `stats()` returns the decision, and orient.py leads
#: `do_first` with it so it cannot be walked past (AUD-0037).
SEARCH_OP_CEILING = 40

EXCERPT_MIN, EXCERPT_MAX = 50, 500


class LedgerRefusal(ValueError):
    """A write refused before it landed, with the reason in the message."""


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── evidence ─────────────────────────────────────────────────────────────

def append_evidence(wb: RunWorkbook, *, source_name: str, source_url: str | None,
                    tier: str, excerpt: str, subcaps, published: str | None = None,
                    claim_type: str = "FACT", origin: str = "public",
                    ers: float | None = None, anchor_quote: str | None = None,
                    run=None,
                    access_status: str = "OK", conflict: str | None = None,
                    fact_id: str = "F1") -> str:
    """Register one fact and return its server-shaped id.

    Fail-closed evidence (invariant 4): a cited id must resolve, belong to
    this run, and carry a verbatim excerpt of 50-500 characters. Enforced at
    the WRITE, so an unresolvable citation cannot exist to be found later.

    `published` may be None. It is not defaulted to today — undated evidence
    is UNVERIFIED, never current (invariant 9), and AUD-0020 measured
    aspiration laundering staleness the other way round."""
    if tier not in C.TIERS:
        raise LedgerRefusal(f"tier {tier!r} is not in {C.TIERS}")
    if claim_type not in C.CLAIM_LABELS:
        raise LedgerRefusal(f"claim_type {claim_type!r} is not in {C.CLAIM_LABELS}")
    text = (excerpt or "").strip()
    if not (EXCERPT_MIN <= len(text) <= EXCERPT_MAX):
        raise LedgerRefusal(
            f"excerpt is {len(text)} chars; invariant 4 requires "
            f"{EXCERPT_MIN}-{EXCERPT_MAX} verbatim characters")
    if not source_url and origin == "public":
        raise LedgerRefusal(
            "a public source with no URL cannot be cited; register it with "
            "origin='internal' and it will be labelled, not laundered")
    cells = [s.strip() for s in (subcaps if isinstance(subcaps, (list, tuple))
                                 else _split_ids(subcaps))]
    tax = C.taxonomy()
    unknown = [c for c in cells if c not in tax.tier]
    if unknown:
        raise LedgerRefusal(f"evidence names cells not in the catalogue: {unknown}")
    in_run = set(wb.selected_subcaps())
    foreign = [c for c in cells if c not in in_run]
    if foreign:
        # `foreign` halts production (invariant 4). Refusing the write is
        # the halt: there is no route around it.
        raise LedgerRefusal(
            f"evidence names cells outside this run's engagement set: {foreign}")
    # ONE TRANSACTION FOR THE ID AND THE ROWS IT NAMES.
    #
    # `next_evidence_id` reads the highest E-id in the register and adds
    # one. Outside a lock that is a read-modify-write across processes: two
    # writers both see E-006 and both mint E-007, and the second append
    # overwrites the first's row in every surface that later resolves that
    # id. Measured 2026-08-31 alongside the PRELIM section a concurrent
    # scanner erased. Minting and appending inside ONE `transaction()`
    # closes both: the lock is held from the read of the maximum through the
    # save of the rows that use it.
    with wb.transaction("append_evidence"):
        eid = wb.next_evidence_id()
        # ERS is COMPUTED, never supplied (AUD-0152: the column existed, a full
        # calculator existed, and nothing joined them — twenty rows, twenty
        # empty cells, in every run ever produced). Scored INLINE here so the
        # append pays no second save; the cross-register pass that updates
        # everyone else's corroboration runs at synthesis, where a second
        # source actually changes a judgement.
        from . import ers as _ers
        _existing = [r for r in wb.rows("Evidence_Detail") if r.get("E_ID")]
        _new = {"E_ID": eid, "Source_Name": source_name, "Source_URL": source_url,
                "Tier": tier, "Recency": recency_band(published, wb),
                "SubCap_IDs": ", ".join(cells), "Excerpt": text}
        _score = _ers.score_row(_new, _existing + [_new])["ers"]
        if ers is not None:
            wb.append("Provenance", {
                "SubCap_ID": "", "Step": "ers_supplied_ignored",
                "Actor": "ledger", "At": _utcnow(),
                "Detail": f"{eid}: caller passed ERS={ers}; the score is computed "
                          f"server-side from tier, recency, specificity and "
                          f"corroboration"}, save=False)
        wb.append("Evidence_Detail", {
            "E_ID": eid, "Fact_ID": fact_id, "Source_Name": source_name,
            "Source_URL": source_url, "Tier": tier, "ERS": _score,
            "Date_Published": published, "Recency": recency_band(published, wb),
            "Claim_Type": claim_type, "Fact_Count": 1,
            "SubCap_IDs": ", ".join(cells), "Excerpt": text,
            "Anchor_Quote": anchor_quote or text, "Retrieved_At": _utcnow(),
            "Origin": origin, "Access_Status": access_status, "Conflict": conflict,
        })
        for cell in cells:
            row = wb.scoring_row(cell) or {}
            have = [i for i in _split_ids(row.get("Evidence_IDs"))
                    if i and i != C.NO_EVIDENCE]
            urls = [u for u in _split_ids(row.get("Source_URLs")) if u]
            have.append(f"{eid}:{fact_id}")
            if source_url and source_url not in urls:
                urls.append(source_url)
            wb.set_scoring(cell, {"Evidence_IDs": ", ".join(have),
                                  "Source_URLs": ", ".join(urls) or None},
                           save=False)
        # INSIDE the transaction. Both of these WRITE, and a write that
        # lands after the lock is released is a write another process can
        # interleave with — the whole defect, moved four lines down.
        wb.save()
        wb.recompute_coverage()
    return eid


def recency_band(published: str | None, wb: RunWorkbook | None = None) -> str:
    """The recency band a date earns against the run's pinned reference date.

    AUD-0020: a future-dated 'planned' fact made 2019 evidence CURRENT,
    because the ladder was fed the best date in the record rather than the
    date the source was published. A date in the future is not a publication
    date; it is a plan, and it bands UNVERIFIED."""
    if not published:
        return C.RECENCY_UNVERIFIED
    try:
        d = _dt.date.fromisoformat(str(published)[:10])
    except ValueError:
        return C.RECENCY_UNVERIFIED
    ref = _dt.date.today()
    if wb is not None:
        try:
            ref = _dt.date.fromisoformat(str(wb.metadata().get("reference_date"))[:10])
        except (ValueError, TypeError):
            pass
    if d > ref:
        return C.RECENCY_UNVERIFIED
    months = (ref.year - d.year) * 12 + (ref.month - d.month)
    for word, hi in C.RECENCY_LADDER:
        if months < hi:
            return word
    return C.RECENCY_ARCHIVAL


# ── search ───────────────────────────────────────────────────────────────

def _ops_since_checkpoint(wb: RunWorkbook) -> int:
    """Searches fired since the last recorded checkpoint.

    Read from the workbook's own metadata rather than by importing runstate,
    which imports this module — the count is a plain integer and does not
    justify a cycle. A run that has never checkpointed measures from zero,
    which is correct: its whole history is one conversation.
    """
    done = len(wb.rows("Search_Log"))
    try:
        mark = json.loads(wb.metadata().get("checkpoint") or "{}")
        return max(0, done - int(mark.get("search_ops") or 0))
    except (ValueError, TypeError):
        return done


def append_search(wb: RunWorkbook, *, subcap: str | None, facet: str | None,
                  query: str, tool: str, hits: int, kept: int,
                  outcome: str = "") -> int:
    """Log one search op and return the running count.

    Every search is logged before its results are used, so the budget check
    reads a real number rather than an agent's recollection of one."""
    if facet is not None and facet not in C.DQ_FACETS:
        raise LedgerRefusal(f"facet {facet!r} is not in {C.DQ_FACETS}")
    # THE CEILING IS A WALL, NOT A NUMBER IN A REPORT.
    #
    # SEARCH_OP_CEILING has been the rule since R27 — "a conversation that
    # has fired this many searches must checkpoint and stop" — and it was
    # enforced by `stats()` returning `checkpoint_required` and orient.py
    # printing it first. AUD-0037 already recorded that shape once: the
    # count was reported and walked past. On 2026-08-30 a live run was
    # measured at 73 ops against the cap of 40, which is the same finding
    # recurring at 183% of the limit.
    #
    # Reported and ignored is the failure mode; refusing is the fix. The
    # window is measured from the last checkpoint rather than from run
    # start, because the ceiling is per CONVERSATION — a long run must be
    # able to checkpoint and legitimately continue, which is exactly the
    # context-preserving behaviour the ceiling exists to force.
    since = _ops_since_checkpoint(wb)
    if since >= SEARCH_OP_CEILING:
        raise LedgerRefusal(
            f"search-op ceiling reached: {since} since the last checkpoint, "
            f"cap {SEARCH_OP_CEILING}. Checkpoint and stop — "
            f"`runstate.checkpoint(wb, '<where you got to>')` records the "
            f"position in the workbook and resets the window, and a fresh "
            f"conversation resumes from it. This is the wall that keeps a "
            f"run from spending its context on searches it will not "
            f"remember; walking past it is how a run loses the reasoning "
            f"the searches were for.")
    if "{entity}" in (query or "") or "{" in (query or "") and "}" in (query or ""):
        # AUD-0015: orient issued work cards containing 15 literal {entity}
        # placeholders and nothing warned, so an unattended agent fired
        # searches for the literal string. A query with an unbound token is
        # not a query.
        raise LedgerRefusal(
            f"query carries an unbound template token: {query!r}. Bind the "
            f"entity before searching; an unbound card is not a card.")
    seq = len(wb.rows("Search_Log")) + 1
    wb.append("Search_Log", {
        "Seq": seq, "Timestamp": _utcnow(), "SubCap_ID": subcap,
        "Facet": facet, "Query": query, "Tool": tool, "Hits": hits,
        "Kept": kept, "Outcome": outcome,
    })
    return seq


# ── synthesis ────────────────────────────────────────────────────────────

#: The working-area fields a synthesis must carry, and the minimum each has
#: to reach. Length is a floor, never the test — `quality` decides substance.
SYNTHESIS_REQUIRED = {
    "Dominant_Claim": 20, "What_We_Found": 120, "Triangulation": 40,
    "Ceiling_Reasoning": 20, "Why_It_Matters": 30, "DMA_Impact": 30,
}
DQ_FIELDS = ("DQ_Works", "DQ_Fails", "DQ_Value", "DQ_Corroborates",
             "DQ_Contradicts")


def record_provenance(wb: RunWorkbook, subcap: str, step: str, actor: str,
                      detail: str = "") -> None:
    """Who did this step. Authorship is what makes independence checkable."""
    if step not in C.PROVENANCE_STEPS:
        raise LedgerRefusal(f"step {step!r} not in {C.PROVENANCE_STEPS}")
    if not str(actor or "").strip():
        raise LedgerRefusal(
            "an unattributed write cannot be checked for independence; name "
            "the actor (an agent name, a session id, a person)")
    wb.append("Provenance", {"SubCap_ID": subcap, "Step": step,
                             "Actor": str(actor).strip(), "At": _utcnow(),
                             "Detail": detail})


def actor_for(wb: RunWorkbook, subcap: str, step: str) -> str | None:
    """The most recent actor for one step of one subcap."""
    hits = [r for r in wb.rows("Provenance")
            if str(r.get("SubCap_ID") or "") == subcap
            and str(r.get("Step") or "") == step]
    return str(hits[-1]["Actor"]) if hits else None


def record_challenge(wb: RunWorkbook, subcap: str, *, verdict: str, actor: str,
                     dimensions: dict, rationale: str,
                     ceiling_band_delta: str = "") -> dict:
    """Record a challenge — and refuse one the synthesis's own author wrote.

    AUD-0018 / AUD-0024: this repository already solves reviewer independence
    BY CONSTRUCTION for the learning loop — `learning-grader` carries no
    Write/Edit and no connector write tool, so it cannot touch the change it
    scores — and then inverts it for the research challenge, where the same
    actor writes a synthesis and its own verdict on it.

    Construction is not available here (both writes go through one library),
    so the equivalent guarantee is made checkable instead: authorship is
    recorded, and a verdict by the synthesis's own author is refused.

    AUD-0102 is the other half. The protocol asserts seven dimensions and
    "any FAIL => overall FAIL", while the schema required an OPEN object with
    no required keys — so a zero-dimension verdict validated, and the card's
    own example silently omitted `synthesis_quality`, the one carrying ten
    sub-conditions. Every dimension is required by NAME, and a FAIL in any
    one makes the overall verdict FAIL."""
    if verdict not in C.CHALLENGE_VERDICTS:
        raise LedgerRefusal(
            f"verdict {verdict!r} not in {C.CHALLENGE_VERDICTS}")
    author = actor_for(wb, subcap, "synthesis")
    if author is None:
        raise LedgerRefusal(
            f"{subcap} has no recorded synthesis author, so a challenge on it "
            f"cannot be shown to be independent. Write the synthesis with an "
            f"actor first.")
    if str(actor).strip() == author:
        raise LedgerRefusal(
            f"{actor!r} wrote this synthesis and cannot also be its "
            f"challenger. A verdict on your own work is a feeling; the "
            f"learning loop's grader is independent BY CONSTRUCTION and the "
            f"research challenge has to be independent by record.")
    missing = [d for d in C.CHALLENGE_DIMENSIONS if d not in (dimensions or {})]
    if missing:
        raise LedgerRefusal(
            f"the challenge omits {missing}. Every dimension is required by "
            f"NAME because a verdict is only as good as what it looked at, "
            f"and an open object let a zero-dimension verdict validate.")
    bad = {k: v for k, v in dimensions.items()
           if str(v).upper() not in ("PASS", "FAIL", "NOT_RUN")}
    if bad:
        raise LedgerRefusal(f"dimension verdicts must be PASS, FAIL or "
                            f"NOT_RUN: {bad}")
    failed = [k for k, v in dimensions.items() if str(v).upper() == "FAIL"]
    if failed and verdict == "PASS":
        raise LedgerRefusal(
            f"dimensions {failed} FAILED and the overall verdict is PASS. "
            f"Any FAIL means FAIL — that is the protocol's own rule.")
    if len(str(rationale or "").strip()) < 40:
        raise LedgerRefusal("a challenge with no rationale is a rubber stamp")
    wb.append("Challenge_Log", {
        "SubCap_ID": subcap, "Verdict": verdict, "Actor": str(actor).strip(),
        "Dimensions": dimensions, "Rationale": rationale,
        "Ceiling_Band_Delta": ceiling_band_delta, "At": _utcnow()})
    record_provenance(wb, subcap, "challenge", actor,
                      f"{verdict}; {len(dimensions)} dimensions")
    wb.set_scoring(subcap, {"Challenge_Verdict": verdict})
    return {"subcap": subcap, "verdict": verdict, "challenger": actor,
            "author": author, "failed_dimensions": failed}


def challenge_for(wb: RunWorkbook, subcap: str) -> dict | None:
    hits = [r for r in wb.rows("Challenge_Log")
            if str(r.get("SubCap_ID") or "") == subcap]
    return hits[-1] if hits else None


def append_synthesis(wb: RunWorkbook, subcap: str, record: dict,
                     actor: str | None = None) -> dict:
    """Write one subcap's synthesis onto its scoring row, or refuse.

    This is the write AUD-0009 measured accepting an unmodified skeleton.
    Every refusal below corresponds to a way that skeleton got through."""
    row = wb.scoring_row(subcap)
    if row is None:
        raise LedgerRefusal(
            f"{subcap} is not in this run's engagement set, so it has no row "
            f"to synthesise onto")
    problems = []
    for field, floor in SYNTHESIS_REQUIRED.items():
        v = record.get(field)
        s = "" if v is None else str(v).strip()
        if len(s) < floor:
            problems.append(f"{field}: {len(s)} chars, floor {floor}")
            continue
        why = Q.is_boilerplate(s)
        if why:
            problems.append(f"{field}: {why}")
    claim = str(record.get("Dominant_Claim") or "")
    if not problems:
        why = Q.is_fluent_but_empty(record.get("What_We_Found"))
        if why:
            problems.append(f"What_We_Found: {why}")
    # Every DQ facet must be answered or explicitly declared not run, with a
    # reason. AUD-0017: the facet-coverage honesty check was never
    # implemented and its only proxy was disarmed by a waiver the same agent
    # wrote.
    for f in DQ_FIELDS:
        v = str(record.get(f) or "").strip()
        if not v:
            problems.append(f"{f}: empty — answer it or write NOT_RUN: <reason>")
        elif v.upper().startswith("NOT_RUN"):
            if len(v) < len("NOT_RUN:") + 12:
                problems.append(f"{f}: NOT_RUN with no reason worth reading")
        elif Q.is_boilerplate(v):
            problems.append(f"{f}: {Q.is_boilerplate(v)}")
    # A claim of absence carries obligations (AUD-0079).
    if Q.claims_absence(claim):
        if str(record.get("Absence_Claimed") or "").strip().upper() not in \
                ("YES", "TRUE", "1"):
            problems.append(
                "Dominant_Claim asserts an absence but Absence_Claimed is not "
                "set — an absence needs a proxy log and a ladder, not a verb")
        if not str(record.get("Proxy_Log") or "").strip():
            problems.append("an absence claim with no proxy log")
    merged = dict(row); merged.update(record)
    bad = Q.claim_label_supported(merged)
    if bad:
        problems.append(bad)
    # The band is the ceiling reasoning's CONCLUSION, and it must be stated
    # in the four-band vocabulary for any positively-evidenced claim: a
    # calibration run (2026-08-29) shipped six syntheses whose
    # Ceiling_Reasoning argued a ceiling at length while Ceiling_Band stayed
    # empty, so nothing downstream could read what the reasoning concluded.
    # HYPOTHESIS — a documented absence — may leave it empty on purpose:
    # null means no score, never a default that looks like data
    # (invariant 9).
    label = str(record.get("Claim_Label") or row.get("Claim_Label")
                or "").strip().upper()
    band = str(record.get("Ceiling_Band") or "").strip()
    if label in ("FACT", "INFERENCE", "CEILING_ESTIMATE") \
            and band not in C.BANDS:
        problems.append(
            f"Ceiling_Band {band!r}: a {label} synthesis states its ceiling "
            f"as one of {C.BANDS} — the reasoning's conclusion, readable, "
            f"in vocabulary. Only HYPOTHESIS (a documented absence) may "
            f"leave it empty.")
    elif band and band not in C.BANDS:
        problems.append(f"Ceiling_Band {band!r} is not in {C.BANDS} — "
                        f"a fifth band must not exist (invariant 6)")
    # The hallucination pinpointer: every figure the synthesis asserts must
    # appear in an excerpt registered to this subcap. The excerpts are
    # verbatim spans of fused, cited sources — a number none of them carries
    # entered the prose from nowhere, and the refusal names it so the repair
    # is 'cite the source that states it or remove the figure'.
    excerpts = [f"{r.get('Excerpt') or ''} {r.get('Anchor_Quote') or ''}"
                for r in wb.rows("Evidence_Detail")
                if subcap in Q._ids(r.get("SubCap_IDs"))]
    for fig in Q.ungrounded_numbers(record, excerpts):
        problems.append(
            f"ungrounded figure {fig!r}: no excerpt registered to {subcap} "
            f"carries it — cite the source that states it or remove it")
    # Functional language: verdict words nowhere, blame constructions never
    # in the fields a client reads as being about them
    # (references/functional_language.md).
    for field in C.PILLAR_COLUMNS:
        v = str(record.get(field) or "")
        if not v or v.upper().startswith("NOT_RUN"):
            continue
        why = Q.accusatory(v, impact_field=field in Q.IMPACT_FIELDS)
        if why:
            problems.append(f"{field}: {why}")
    if problems:
        raise LedgerRefusal(
            f"{subcap}: synthesis refused — " + "; ".join(problems))
    payload = {k: v for k, v in record.items() if k in C.PILLAR_COLUMNS}
    payload["Retrieved_At"] = _utcnow()
    wb.set_scoring(subcap, payload)
    if actor:
        record_provenance(wb, subcap, "synthesis", actor)
    wb.recompute_coverage()
    # The cross-register ERS pass lands HERE rather than at every append.
    # Corroboration is a property of the whole register — a row banked first
    # is under-scored until its second source arrives — but the moment that
    # matters is when a judgement is written, not when a row is added. One
    # pass per synthesis instead of one per evidence row.
    from . import ers as _ers
    _ers.recompute(wb)
    return {"subcap": subcap, "written": sorted(payload),
            "actor": actor}


# ── gate log ─────────────────────────────────────────────────────────────

def append_gate(wb: RunWorkbook, *, gate: str, scope: str, verdict: str,
                detail: str = "", blocking: bool = True) -> None:
    if verdict not in ("PASS", "FAIL", "NOT_RUN"):
        raise LedgerRefusal(f"verdict {verdict!r} must be PASS, FAIL or NOT_RUN")
    if verdict == "NOT_RUN" and not detail.strip():
        # A NOT_RUN with no reason is indistinguishable from a pass that
        # nobody looked at (the SG discipline: explicit NOT_RUN + reason).
        raise LedgerRefusal("NOT_RUN must carry the reason it did not run")
    wb.append("Gate_Log", {
        "Timestamp": _utcnow(), "Gate": gate, "Scope": scope,
        "Verdict": verdict, "Detail": detail, "Blocking": blocking,
    })


# ── the budget check, working ────────────────────────────────────────────

def stats(wb: RunWorkbook, category: str | None = None) -> dict:
    """What this run has spent, and whether it must stop.

    The function AUD-0008 measured crashing on 1 of 1 invocations. It now
    returns a DECISION as well as a count, because AUD-0037 measured the
    count being reported and then walked past."""
    searches = wb.rows("Search_Log")
    if category:
        searches = [s for s in searches
                    if str(s.get("SubCap_ID") or "").startswith(category)]
    ev = wb.rows("Evidence_Detail")
    rows = wb.scoring_rows()
    if category:
        rows = [r for r in rows
                if str(r.get("SubCap_ID") or "").startswith(category + ".")]
    synthesised = sum(1 for r in rows if str(r.get("Dominant_Claim") or "").strip())
    n = len(searches)
    # THE DECISION MUST MEASURE WHAT THE WALL MEASURES (MEM-0436).
    #
    # `append_search` refuses on `_ops_since_checkpoint` — a window that a
    # checkpoint resets, because the ceiling is per CONVERSATION and a long
    # run must be able to checkpoint and legitimately continue. This
    # function computed the same decision from the LIFETIME count, so once a
    # run passed 40 searches ever, `checkpoint_required` was true forever and
    # no checkpoint could clear it. orient prints this first, so every
    # conductor obediently stopped and re-stopped: three runs walled on
    # 2026-08-31 at 141, ~180 and 567 ops, the last of them still being told
    # to checkpoint after a revival had already reset its window.
    #
    # Two measurements of one rule is the defect; the fix is to keep one.
    # The LIFETIME count stays reported, because spend is worth seeing — it
    # just no longer decides. The gate itself is unchanged in strength: over
    # the cap since the last checkpoint still stops, which is the half a
    # loosened ceiling would have silently lost (MEM-0338 / R27).
    since = _ops_since_checkpoint(wb)
    return {
        "search_ops": n,
        "search_ops_since_checkpoint": since,
        "search_op_ceiling": SEARCH_OP_CEILING,
        "checkpoint_required": since >= SEARCH_OP_CEILING,
        "evidence_items": len(ev),
        "subcaps_selected": len(rows),
        "subcaps_synthesised": synthesised,
        "kept_ratio": (round(sum(int(s.get("Kept") or 0) for s in searches)
                             / max(1, sum(int(s.get("Hits") or 0)
                                          for s in searches)), 3)),
        "category": category,
    }


def worklist(wb: RunWorkbook, category: str) -> dict:
    """closed / volleyed / pending for one category, from the workbook.

    The three states AUD-0006 turned on. `volleyed` — evidence banked, no
    synthesis — is the state the archive served past and then declared
    clean; here it is first-class and `pending` is not the only servable
    thing."""
    closed, volleyed, pending = [], [], []
    for r in wb.scoring_rows():
        cell = str(r.get("SubCap_ID") or "").strip()
        if not cell.startswith(category + "."):
            continue
        has_ev = bool([i for i in _split_ids(r.get("Evidence_IDs"))
                       if i and i != C.NO_EVIDENCE])
        has_syn = bool(str(r.get("Dominant_Claim") or "").strip())
        if has_syn:
            closed.append(cell)
        elif has_ev:
            volleyed.append(cell)
        else:
            pending.append(cell)
    return {"category": category, "closed": sorted(closed),
            "volleyed": sorted(volleyed), "pending": sorted(pending)}


if __name__ == "__main__":  # a library, but it must answer --help
    import argparse as _ap
    _ap.ArgumentParser(
        prog=__file__.rsplit("/", 1)[-1],
        description=__doc__.split("\n")[0],
        epilog="A library module: import it, or run the modules that do have "
               "a command line (cli, orient, floors_gate, validator, handoff, "
               "reports, strip_working_area, patch_validator, watchdog).",
    ).parse_args()
