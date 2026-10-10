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
#:
#: 40 → 60 on 2026-09-03, with the five-volley rule: forty was set when a
#: subcap took one or two searches. Under `volleys_incomplete` every cell
#: costs at least five, and forty stopped a conversation at its eighth cell
#: in the middle of a volley. Sixty is twelve fully volleyed cells between
#: checkpoints — still a wall, still per conversation, still resumed from
#: the position the checkpoint recorded.
SEARCH_OP_CEILING = 60

EXCERPT_MIN, EXCERPT_MAX = 50, 500


class LedgerRefusal(ValueError):
    """A write refused before it landed, with the reason in the message."""


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── evidence ─────────────────────────────────────────────────────────────

def _refuse_on_drift(wb: RunWorkbook) -> None:
    """No row is written into a run whose lock no longer matches the engine.

    Measured 28-09-2026 (QA audit F-F06-009): with the catalogue tier of one
    cell mutated, `resume` reported the drift and `search` still wrote a row.
    A write is the one place a refusal is cheap and final."""
    drift = wb.verify_handoff_lock()
    if drift:
        raise LedgerRefusal(
            "the run's lock no longer matches the engine: " + "; ".join(drift)
            + ". Nothing is written into a run the engine cannot vouch for; "
              "pin the catalogue (DMA_CATALOGUE) or the engine version first.")


def own_hosts(wb: RunWorkbook) -> set[str]:
    """The entity's own web identities: the Firmographics website, bare."""
    out = set()
    for r in wb.rows("Firmographics"):
        if str(r.get("Field") or "").strip().lower() == "website" \
                and str(r.get("Value") or "").strip():
            out.add(str(r.get("Value")).strip().lower().removeprefix("www."))
    return out


def host_of(url: str | None) -> str:
    return str(url or "").split("//")[-1].split("/")[0].lower().removeprefix("www.")


def is_own_host(wb: RunWorkbook, url: str | None) -> bool:
    h = host_of(url)
    return bool(h) and any(h == o or h.endswith("." + o) for o in own_hosts(wb))


def retier_evidence(wb: RunWorkbook, e_id: str, tier: str, *, reason: str,
                    run=None, actor: str | None = None) -> dict:
    """Move one registered row to another tier, with the cascade the tier
    carries: the claim label is re-derived (a FACT cannot rest on T3 or
    weaker), ERS is recomputed for the whole register (corroboration is a
    property of the register), and the change is logged where a reader of
    the run looks — a Provenance row and a non-blocking Gate_Log row. The
    cells' ceilings are recomputed by the next `assessment` pass, which
    reads the register rather than a stored tier."""
    from . import ers as _ers
    _refuse_on_drift(wb)
    eid = str(e_id or "").strip().upper()
    if tier not in C.TIERS:
        raise LedgerRefusal(f"tier {tier!r} is not in {C.TIERS}")
    if len(str(reason or "").strip()) < 20:
        raise LedgerRefusal("say why the tier changes (--reason, >=20 chars): "
                            "a re-tier with no reason is the silent downgrade "
                            "the refusal at registration exists to prevent")
    row = next((r for r in wb.rows("Evidence_Detail")
                if str(r.get("E_ID") or "").strip().upper() == eid), None)
    if row is None:
        raise LedgerRefusal(f"{eid} is not in this run's register")
    was = str(row.get("Tier") or "")
    if was == tier:
        raise LedgerRefusal(f"{eid} is already {tier}")
    if tier == "T1" and str(row.get("Origin") or "public") == "public" \
            and is_own_host(wb, row.get("Source_URL")):
        raise LedgerRefusal(f"{eid} is on the entity's own domain, which is never T1")
    label = str(row.get("Claim_Type") or "")
    new_label = label
    if label == "FACT" and tier not in C.FACT_TIERS:
        new_label = C.claim_label_for(tier)
    with wb.transaction("retier_evidence"):
        wb.update_row("Evidence_Detail", "E_ID", row["E_ID"],
                      {"Tier": tier, "Claim_Type": new_label}, save=False)
        wb.append("Provenance", {
            "SubCap_ID": "", "Step": "retier", "Actor": actor or "ledger",
            "At": _utcnow(),
            "Detail": (f"{eid}: {was} -> {tier}"
                       + (f"; claim label {label} -> {new_label}" if new_label != label else "")
                       + f". {str(reason).strip()}")[:900]}, save=False)
        wb.append("Gate_Log", {
            "Timestamp": _utcnow(), "Gate": "RETIER", "Scope": eid,
            "Verdict": "PASS", "Blocking": False,
            "Detail": f"{was} -> {tier}: {str(reason).strip()}"[:900]})
    _ers.recompute(wb, run)
    wb.reload() if hasattr(wb, "reload") else None
    now = next((r for r in wb.rows("Evidence_Detail")
                if str(r.get("E_ID") or "").strip().upper() == eid), {})
    return {"e_id": eid, "was": was, "tier": tier, "claim_type": new_label,
            "claim_type_was": label, "ers": now.get("ERS")}


#: THE REGISTER FREEZES WHILE THE REPORTS ARE WRITTEN (B1 Bank, 2026-10-08):
#: evidence kept landing during REPORTS (998 -> 1005 rows), so every passed
#: section failed the next whole-report pass on a figure that had moved under
#: it — §8 was relaunched twice in twelve minutes, and the session's own fix
#: was "I've stopped registering evidence until both reports pass". That is
#: now a rule the ledger holds: `engine.narrative freeze` (the driver sets it
#: when REPORTS starts) refuses a new register row until `thaw`. A writer
#: that needs new evidence returns BLOCKED_UPSTREAM with kind `evidence`;
#: the conducting session thaws, registers, re-freezes, and the sections
#: that cited the moved facts are the ONLY ones reopened.
FREEZE_KEY = "evidence_freeze"


def is_frozen(wb: RunWorkbook) -> str:
    """The freeze reason, or '' when the register is open."""
    v = str(wb.metadata().get(FREEZE_KEY) or "").strip()
    return "" if not v or v.upper() in ("NO", "OFF", "FALSE", "0") else v


def refuse_if_frozen(wb: RunWorkbook, what: str) -> None:
    why = is_frozen(wb)
    if why:
        raise LedgerRefusal(
            f"the evidence register is FROZEN ({why}) — cannot {what}. The report "
            f"sections are being written against the register as it stands; a row "
            f"added now reopens every section whose figures it moves. If the fact "
            f"is needed, return BLOCKED_UPSTREAM (kind evidence) so the conducting "
            f"session thaws (`engine.narrative thaw`), registers it, re-freezes and "
            f"reopens only the sections that cite it.")


def freeze(wb: RunWorkbook, why: str) -> dict:
    why = " ".join(str(why or "").split())
    if len(why) < 10:
        raise LedgerRefusal("freeze needs a reason of >= 10 chars (which stage, why)")
    wb.set_metadata(FREEZE_KEY, f"{why} @ {_utcnow()}")
    return {"frozen": True, "why": why, "rows": len(wb.evidence_index())}


def thaw(wb: RunWorkbook, why: str) -> dict:
    why = " ".join(str(why or "").split())
    if len(why) < 10:
        raise LedgerRefusal("thaw needs a reason of >= 10 chars (what is being registered)")
    was = is_frozen(wb)
    wb.set_metadata(FREEZE_KEY, "")
    append_gate(wb, gate="EVIDENCE_THAW", scope="run", verdict="PASS", blocking=False,
                detail=f"register thawed: {why[:300]} (was: {was[:200] or 'open'})")
    return {"frozen": False, "why": why}


def append_evidence(wb: RunWorkbook, *, source_name: str, source_url: str | None,
                    tier: str, excerpt: str, subcaps, published: str | None = None,
                    claim_type: str | None = None, origin: str = "public",
                    ers: float | None = None, anchor_quote: str | None = None,
                    run=None, actor: str | None = None,
                    access_status: str = "OK", conflict: str | None = None,
                    fact_id: str = "F1", verify_excerpts: bool = False,
                    unverified_reason: str | None = None) -> str:
    """Register one fact and return its server-shaped id.

    Fail-closed evidence (invariant 4): a cited id must resolve, belong to
    this run, and carry a verbatim excerpt of 50-500 characters. Enforced at
    the WRITE, so an unresolvable citation cannot exist to be found later.

    VERBATIM USED TO BE A WORD IN AN ERROR MESSAGE. Until 2026-09-14 this
    checked the excerpt's LENGTH and nothing else; "verbatim" appeared only
    in the refusal text for a span of the wrong size. The only real check in
    the system was the app connector's `register_evidence`, a tool every
    research agent's manifest denies. Now `engine.cli fetch` leaves the
    page's extracted text under the run, and three outcomes follow:

      cached, span present   registers.
      cached, span absent    `excerpt_not_verbatim` — WHATEVER
                             `verify_excerpts` says. The page is in hand;
                             not looking at it because a flag is off would
                             make the check an opinion.
      not cached             `excerpt_unverified` when `verify_excerpts`,
                             unless `unverified_reason` says what stopped
                             the fetch — then the row carries
                             `Access_Status = "UNVERIFIED: <reason>"`.
                             Recorded, never silent.

    `verify_excerpts` DEFAULTS OFF because every in-process caller — the
    fixtures, the stub, the handoff — registers against URLs nothing
    fetched; flipping the default would rewrite what those mean rather than
    add a check. `engine.cli evidence` and `memory.consolidate` pass True,
    which is where a lane's writes actually go.

    `published` may be None. It is not defaulted to today — undated evidence
    is UNVERIFIED, never current (invariant 9), and AUD-0020 measured
    aspiration laundering staleness the other way round."""
    _refuse_on_drift(wb)
    refuse_if_frozen(wb, "register evidence")
    if tier not in C.TIERS:
        raise LedgerRefusal(f"tier {tier!r} is not in {C.TIERS}")
    # THE LABEL IS DERIVED FROM PROVENANCE, NOT TYPED. Until 28-09-2026 this
    # parameter defaulted to "FACT" and nothing compared it with the tier,
    # so 77 of 285 FACT rows on one staged heatmap rested on T3/T4
    # reportage (QA audit F-J04-004, regression seed 2). A writer that
    # states no label gets the one its tier licenses; a writer that states
    # FACT on a tier that cannot carry it is refused, not corrected —
    # silently downgrading a stated claim would hide the mistake the
    # refusal exists to surface.
    if claim_type is None:
        claim_type = C.claim_label_for(tier)
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
    # THE ENTITY'S OWN SITE IS NEVER T1. The methodology's ladder puts
    # regulatory and audited filings at T1, the entity's official
    # disclosures at T2 and its marketing at T5; a page on the entity's own
    # domain is at best the second rung. Measured 2026-10-06 (Arbor Bank):
    # six own-site pages filed T1 (E-004, E-074, E-224, E-225, E-233, E-234)
    # carried FACT labels and lifted ceilings a marketing page cannot carry,
    # and nothing could re-tier them (`engine.cli retier` now can). Refused
    # at the write, the way every other provenance rule is.
    if origin == "public" and tier == "T1" and is_own_host(wb, source_url):
        raise LedgerRefusal(
            f"{source_url} is on the entity's own domain, which is never T1: "
            f"a regulator's or auditor's copy of a filing is T1; the entity's "
            f"own annual report, investor page or press release is T2 "
            f"(official disclosure); its product and about pages are T5 "
            f"(marketing). File it at the tier the ladder gives it "
            f"(references/evidence_methodology.md).")
    # A machine technographic scan is T1 (contract.SCAN_TIER). Measured
    # 28-09-2026 (QA audit F-J04-015): 5 technographic rows on one staged
    # heatmap sat at T3, capping the ceilings their cells could reach.
    # Refused, not corrected, for the reason the label rule gives: a
    # silent re-tier would hide the mistake. Before the FACT rule so the
    # writer is told the tier to fix rather than the label that follows it.
    scan = C.scan_source(source_name, source_url)
    if scan and tier != C.SCAN_TIER:
        raise LedgerRefusal(
            f"source names the technographic scan provider {scan!r} and is "
            f"filed at {tier}; a machine technographic scan is "
            f"{C.SCAN_TIER} (contract.SCAN_TIER). Re-register it at "
            f"{C.SCAN_TIER}, or under the source that actually states the "
            f"claim if this is reportage about a scan rather than the scan")
    # After the excerpt and URL checks on purpose: a thin note is refused
    # on its length first (the message the notebook tests read back), and
    # only a citable span is then judged on what its tier can carry.
    if claim_type == "FACT" and tier not in C.FACT_TIERS:
        raise LedgerRefusal(
            f"claim_type 'FACT' requires tier in {C.FACT_TIERS}; got {tier!r}. "
            f"A {tier} source supports an INFERENCE (label it so, with the "
            f"question that would confirm it) or a corroborated FACT from a "
            f"T1/T2 source — never a FACT on its own")
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
    assert_actor_scope(actor, "evidence", cells)
    if not str(published or "").strip() and source_url and run is not None:
        # THE DATE THE PAGE STATES, FILLED AT THE WRITE (2026-10-09,
        # R-IMA-20261009 P2C1: 19 of 20 rows undated, a news URL reading
        # /20230406/ among them). `engine.cli fetch` records the page's own
        # publication metadata or URL-path date beside the cached text; a
        # writer who omitted --published gets it here, so dating does not
        # depend on a lane copying a line. Never the retrieval date: a page
        # stating today passes the refusal below on its URL, and one that
        # does not is left undated rather than refused.
        try:
            from . import fetch as _fetch
            got = _fetch.cached_published(run, source_url).get("published")
        except Exception:                                    # noqa: BLE001
            got = None
        if got and got != _dt.date.today().isoformat():
            published = got
    _refuse_retrieval_date_as_published(wb, published, text, source_url)
    access_status = _verified_access_status(
        wb, run, source_url, text, verify_excerpts, unverified_reason,
        access_status)
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
    # THE SAME SPAN IS THE SAME ROW. Measured 2026-09-30 (SWBC relay): a
    # registration whose output was lost was re-run and minted E-224..E-226
    # for one TechFabric span — three identities for one document, which
    # `single_source_fact` and corroboration both miscount. An identical
    # URL + excerpt now reuses the existing row and cites it from any new
    # cell through `attach_evidence`, the reuse loop's own write.
    _norm = " ".join(text.split())
    _url = str(source_url or "").strip()
    dup = next((str(r["E_ID"]) for r in wb.rows("Evidence_Detail")
                if r.get("E_ID") and str(r.get("Source_URL") or "").strip() == _url
                and " ".join(str(r.get("Excerpt") or "").split()) == _norm), None)
    if dup:
        new_cells = [c for c in cells if dup not in
                     _split_ids((wb.scoring_row(c) or {}).get("Evidence_IDs"))
                     and f"{dup}:" not in str((wb.scoring_row(c) or {}).get("Evidence_IDs") or "")]
        if new_cells:
            attach_evidence(wb, dup, new_cells, actor=actor)
        return dup
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
        if wb.autosave:           # a batch (autosave off) saves once at its end
            wb.save()
        wb.recompute_coverage()
    return eid


# ── citing a row the run already holds ───────────────────────────────────

#: The Provenance steps this module writes for the reuse loop. Deliberately
#: NOT in `contract.PROVENANCE_STEPS`: that tuple is the set of steps whose
#: AUTHORSHIP is load-bearing for the independence checks, and an attach is a
#: citation, not a judgement. It is written straight to the sheet the same
#: way `append_evidence` writes `ers_supplied_ignored`.
ATTACH_STEP = "attach"
DECLINE_STEP = "reuse_declined"


def smear_of_cell(wb: RunWorkbook, cell: str) -> dict | None:
    """The gate's `evidence_smear` finding this cell is part of NOW, or None.

    Asked at SYNTHESIS, not at registration: collection is complete when the
    judgement is written, so the measurement is the one the gate will make —
    asked at the register it was order-dependent (a capability-level source
    registered first reads as 100% of every sibling before the cell-specific
    rows arrive), and refused the engine's own one-source-many-cells notes."""
    cap = cell.rsplit(".", 1)[0]
    rows = [{"SubCap_ID": str(r.get("SubCap_ID") or ""), "Evidence_IDs": r.get("Evidence_IDs")}
            for r in wb.scoring_rows()
            if str(r.get("SubCap_ID") or "").rsplit(".", 1)[0] == cap]
    return next((x for x in Q.evidence_smear(rows) if cell in x["subcaps"]), None)


#: who may undo a citation beyond a category producer on its own cells: the
#: conducting tier. Never a collector or another category's lane — one that
#: could detach could launder evidence out of a judgement it does not own.
DETACH_ACTORS = frozenset({"research-conductor"})
DETACH_STEP = "detach"


def detach_evidence(wb: RunWorkbook, eid: str, cell: str, *, reason: str,
                    actor: str | None = None) -> dict:
    """Undo ONE citation (evidence row ↔ cell), audited.

    The remedy the smear rule needs and nothing else had: an attachment made
    upstream (a connector pass, a pilot lane) that does not answer the cell's
    own question. Refuses: an actor that is neither the category's producer
    on its own cells nor in DETACH_ACTORS; a reason under 20
    characters; a pair that does not exist; a cell whose current synthesis
    still names the id (re-synthesise without it first — a synthesis must
    never cite a row its cell no longer carries). The row itself stays in the
    register; the cell's challenge verdict is cleared, because the evidence
    it judged changed. Every detach is a Provenance row with the reason."""
    eid = str(eid or "").strip()
    who = str(actor or "").strip()
    own = re.match(r"^research-(p\d+c\d+)-producer$", who, re.I)
    if own and str(cell).upper().startswith(own.group(1).upper()):
        pass                     # a category's judge, on its own category's cells
    elif who not in DETACH_ACTORS:
        raise LedgerRefusal(
            f"detach is the conducting tier's ({', '.join(sorted(DETACH_ACTORS))}) or "
            f"the category producer's on its own cells, not "
            f"{who or 'an unattributed writer'}'s: a collector or another category "
            f"could otherwise remove evidence from a judgement it does not own")
    if len(str(reason or "").strip()) < 20:
        raise LedgerRefusal("detach needs a reason (>= 20 chars): why the row "
                            "does not answer this cell's own question")
    sr = wb.scoring_row(cell)
    if sr is None:
        raise LedgerRefusal(f"{cell} is not in this run's engagement set")
    have = [i for i in _split_ids(sr.get("Evidence_IDs")) if i and i != C.NO_EVIDENCE]
    keep = [i for i in have if i.split(":")[0] != eid]
    if len(keep) == len(have):
        raise LedgerRefusal(f"{cell} does not cite {eid}; nothing to detach")
    prose = " ".join(str(sr.get(k) or "") for k in C.PILLAR_COLUMNS
                     if k not in ("Evidence_IDs", "Source_URLs"))
    if re.search(rf"\b{re.escape(eid)}\b", prose):
        raise LedgerRefusal(
            f"{cell}'s synthesis still names {eid}; re-synthesise the cell without "
            f"it first, then detach — a synthesis must not cite a row its cell "
            f"no longer carries")
    register = wb.evidence_index()
    with wb.transaction("detach_evidence"):
        row = register.get(eid) or {}
        named = [x.split(":")[0].strip() for x in _split_ids(row.get("SubCap_IDs"))
                 if str(x).strip() and x.split(":")[0].strip() != cell]
        wb.update_row("Evidence_Detail", "E_ID", eid,
                      {"SubCap_IDs": ", ".join(named)}, save=False)
        urls_kept = {str((register.get(i.split(":")[0]) or {}).get("Source_URL") or "")
                     for i in keep}
        urls = [u for u in _split_ids(sr.get("Source_URLs")) if u and u in urls_kept]
        # empty is written as the sentinel / "" — set_scoring skips a None
        wb.set_scoring(cell, {"Evidence_IDs": ", ".join(keep) or C.NO_EVIDENCE,
                              "Source_URLs": ", ".join(urls),
                              "Challenge_Verdict": ""}, save=False)
        wb.append("Provenance", {"SubCap_ID": cell, "Step": DETACH_STEP, "Actor": who,
                                 "At": _utcnow(),
                                 "Detail": f"detached {eid}: {str(reason).strip()}"},
                  save=False)
    return {"detached": eid, "cell": cell, "evidence_ids": keep}


def attach_evidence(wb: RunWorkbook, eid: str, subcaps, *,
                    actor: str | None = None) -> dict:
    """Cite an EXISTING register row from another cell, without minting a
    duplicate.

    THE WRITE THE REUSE LOOP WAS MISSING. `brief.leads_in` and
    `brief.reusable.proposed_from_other_categories` show a lane rows another
    lane opened; until this existed the only way to act on one was
    `append_evidence`, which mints a SECOND row for the same source — a new
    E-id, a re-scored ERS, and a register where one document is two
    identities and `single_source_fact` cannot tell.

    It is the ONE cross-category write a category lane may make, and only to
    its OWN category's cells: `scope.violation(actor, "attach", cells)` is
    the same table every other writer asks, so `research-p1c1-producer`
    attaching to a P3 cell is refused in the same words as every other
    out-of-scope write.

    The link is written BOTH WAYS — the cell cites the id and the row names
    the cell back — because the floors gate counts a citation only when both
    are true (`_named_by`, AUD-0115), and a one-way attach would look like
    consolidation and count as nothing.

    Refuses, each saying what and why: an e_id the register does not hold; a
    cell the catalogue does not know; a cell outside this run's engagement
    set; a pair the cell already cites.
    """
    eid = str(eid or "").strip()
    cells = [s.strip() for s in (subcaps if isinstance(subcaps, (list, tuple))
                                 else _split_ids(subcaps)) if str(s).strip()]
    if not cells:
        raise LedgerRefusal(
            "attach names no cell. Pass the cell(s) of YOUR category this "
            "registered row bears on; an attach that reaches no cell "
            "consolidates nothing.")
    register = wb.evidence_index()
    if eid not in register:
        raise LedgerRefusal(
            f"no evidence row {eid!r} in this run's register "
            f"({len(register)} row(s)). `attach` CITES a row the run already "
            f"holds — it does not create one. Register a new source with "
            f"`engine.cli evidence`.")
    tax = C.taxonomy()
    unknown = [c for c in cells if c not in tax.tier]
    if unknown:
        raise LedgerRefusal(f"attach names cells not in the catalogue: {unknown}")
    in_run = set(wb.selected_subcaps())
    foreign = [c for c in cells if c not in in_run]
    if foreign:
        raise LedgerRefusal(
            f"attach names cells outside this run's engagement set: {foreign}")
    assert_actor_scope(actor, "attach", cells)

    row = register[eid]
    fact_id = str(row.get("Fact_ID") or "F1").strip() or "F1"
    source_url = str(row.get("Source_URL") or "").strip() or None
    already = []
    for cell in cells:
        sr = wb.scoring_row(cell) or {}
        if eid in [i.split(":")[0] for i in _split_ids(sr.get("Evidence_IDs"))
                   if i and i != C.NO_EVIDENCE]:
            already.append(cell)
    if already:
        raise LedgerRefusal(
            f"{eid} is already cited by {', '.join(already)}. An attach that "
            f"repeats a citation inflates `grounded_on` and the per-cell "
            f"evidence floor with one source counted twice; the pair "
            f"(evidence, cell) is the identity, and it exists.")

    with wb.transaction("attach_evidence"):
        named = [s.split(":")[0].strip()
                 for s in _split_ids(row.get("SubCap_IDs")) if str(s).strip()]
        for cell in cells:
            if cell not in named:
                named.append(cell)
        wb.update_row("Evidence_Detail", "E_ID", eid,
                      {"SubCap_IDs": ", ".join(named)}, save=False)
        for cell in cells:
            sr = wb.scoring_row(cell) or {}
            have = [i for i in _split_ids(sr.get("Evidence_IDs"))
                    if i and i != C.NO_EVIDENCE]
            urls = [u for u in _split_ids(sr.get("Source_URLs")) if u]
            have.append(f"{eid}:{fact_id}")
            if source_url and source_url not in urls:
                urls.append(source_url)
            wb.set_scoring(cell, {"Evidence_IDs": ", ".join(have),
                                  "Source_URLs": ", ".join(urls) or None},
                           save=False)
            wb.append("Provenance", {
                "SubCap_ID": cell, "Step": ATTACH_STEP,
                "Actor": str(actor or "unattributed").strip(),
                "At": _utcnow(),
                "Detail": f"cited {eid} ({str(row.get('Source_Name') or '')[:80]}) "
                          f"registered against {', '.join(named)}",
                "Session": _agent_session()}, save=False)
        if wb.autosave:
            wb.save()
        wb.recompute_coverage()
    return {"e_id": eid, "subcaps": cells, "fact_id": fact_id,
            "now_names": named, "minted": False}


def decline_evidence(wb: RunWorkbook, eid: str, subcap: str, *,
                     why: str, actor: str | None = None) -> dict:
    """Record that a lane READ a proposal and it does not bear on the cell.

    The other half of PROPOSE-never-attach. Without it, "offered and not
    taken" and "offered and never looked at" are the same state, so
    `floors_gate.reuse_ignored` could not tell a lane that judged from a lane
    that ignored — and an advisory term that cannot tell those apart teaches
    nobody anything. Writes Provenance only: a decline changes no citation.
    """
    eid = str(eid or "").strip()
    subcap = str(subcap or "").strip()
    if not str(why or "").strip():
        raise LedgerRefusal(
            "a decline with no reason is indistinguishable from ignoring the "
            "proposal. Say what the row is about and why it does not answer "
            "this cell's question.")
    if eid not in wb.evidence_index():
        raise LedgerRefusal(f"no evidence row {eid!r} in this run's register")
    if subcap not in set(wb.selected_subcaps()):
        raise LedgerRefusal(
            f"{subcap} is not selected in this run; there is no proposal to "
            f"decline")
    assert_actor_scope(actor, "attach", [subcap])
    wb.append("Provenance", {
        "SubCap_ID": subcap, "Step": DECLINE_STEP,
        "Actor": str(actor or "unattributed").strip(), "At": _utcnow(),
        "Detail": f"declined {eid}: {str(why).strip()[:400]}",
        "Session": _agent_session()})
    return {"e_id": eid, "subcap": subcap, "declined": True}


def reuse_decisions(wb: RunWorkbook, category: str | None = None) -> dict:
    """What lanes DID with the proposals they were offered, from Provenance.

    `attached` and `declined` are lists of (e_id, cell) pairs. Computed from
    the sheet rather than from a lane's report, like everything else the
    conductor reads.
    """
    cat = str(category or "").strip().upper()
    out = {"attached": [], "declined": []}
    for r in wb.rows("Provenance"):
        step = str(r.get("Step") or "").strip()
        if step not in (ATTACH_STEP, DECLINE_STEP):
            continue
        cell = str(r.get("SubCap_ID") or "").strip()
        if cat and not cell.startswith(cat):
            continue
        detail = str(r.get("Detail") or "")
        eid = ""
        for word in detail.replace(":", " ").split():
            if word.upper().startswith("E-"):
                eid = word.strip(",()")
                break
        key = "attached" if step == ATTACH_STEP else "declined"
        out[key].append({"e_id": eid, "subcap": cell,
                         "actor": str(r.get("Actor") or ""),
                         "at": r.get("At")})
    return out


def _run_of(wb: RunWorkbook, run=None):
    """The run this workbook belongs to, for the fetch cache.

    Derived from the workbook's own path (`runstate.locate` globs the run
    root for the .xlsx) rather than required from the caller, so a caller
    that forgets to thread `run=` cannot silently turn the verification off.
    An explicit `run` wins."""
    if run is not None:
        return run
    from . import runstate as _runstate
    return _runstate.Run(run_id=wb.path.stem, root=wb.path.parent,
                         workbook_path=wb.path)


def _verified_access_status(wb, run, source_url, text, verify_excerpts,
                            unverified_reason, access_status) -> str:
    """The row's Access_Status after the excerpt has been checked, or a
    LedgerRefusal. See `append_evidence` for the three outcomes."""
    if not source_url:
        # Verification is about a URL. An internal document has none, is
        # labelled origin='internal', and is refused or not on its own terms.
        return access_status
    from . import fetch as _fetch
    _run = _run_of(wb, run)
    # The refusals below print a command the reader can paste; `fetch` is
    # per-run (its cache is), so the run id has to be in it.
    _where = f"--run {getattr(_run, 'run_id', '<R>')}"
    page = _fetch.cached_text(_run, source_url)
    if page is not None:
        if _fetch.normalise(text) not in _fetch.normalise(page):
            raise LedgerRefusal(
                f"excerpt_not_verbatim: this span is not in the text "
                f"`engine.cli fetch` read from {source_url} (whitespace and "
                f"case are normalised; nothing else is). Re-extract it from "
                f"the source — `engine.cli fetch {_where} --url {source_url} "
                f"--query '<what you are quoting>'` prints the spans that are "
                f"there. "
                f"Never repair a quote by hand.")
        return access_status
    if not verify_excerpts:
        return access_status
    reason = str(unverified_reason or "").strip()
    if not reason:
        raise LedgerRefusal(
            f"excerpt_unverified: nothing in this run has read {source_url}, "
            f"so there is nothing to check this span against. Run "
            f"`engine.cli fetch {_where} --url {source_url} --query "
            f"'<the DQ text>'` "
            f"and register from a window it prints — it costs three windows "
            f"of context, not the page. If the page genuinely cannot be "
            f"fetched (a 403 WAF, a paywall, a connector's own extract), say "
            f"so with `--unverified '<what stopped it>'` and the row is "
            f"recorded UNVERIFIED rather than passed off as checked. "
            f"(`engine.cli fetch --via-text -` caches a connector's extract "
            f"under the URL, which verifies it properly.)")
    return f"UNVERIFIED: {reason}"


def _refuse_retrieval_date_as_published(wb, published, excerpt: str, url: str | None):
    """A `published` equal to TODAY is the retrieval date wearing the
    publication date's clothes, unless the page itself states today's date.

    Measured 2026-10-09 (IMA Financial Group, E-001): a sonnet PRELIM lane
    registered a trade-press revenue profile with `--published 2026-10-09` —
    the day it was read — so an undated page banded CURRENT and earned the
    recency score a dated one earns. The prompt already said "never today's
    date"; a rule the ledger refuses is the one that holds for every tier.
    A press release genuinely issued today carries its date in the span or
    the URL, and passes."""
    from . import dates as _dates
    d = _dates.resolve(published)
    if not d:
        return
    today = _dt.date.today()
    if d != today:
        return
    hay = f"{excerpt or ''} {url or ''}".lower()
    forms = {today.isoformat(), today.strftime("%B %d, %Y").lower(),
             today.strftime("%B %-d, %Y").lower(), today.strftime("%b %-d, %Y").lower(),
             today.strftime("%d %B %Y").lower(), today.strftime("%-d %B %Y").lower(),
             today.strftime("%Y/%m/%d"), today.strftime("%m/%d/%Y")}
    if any(f in hay for f in forms):
        return
    raise LedgerRefusal(
        f"published {published!r} is today's date, which is when the page was "
        f"READ, not when it was published, and nothing in the excerpt or URL "
        f"states it. Omit --published for an undated page (the row bands "
        f"{C.RECENCY_UNVERIFIED}, never current), or quote the dated line the "
        f"page carries.")


def recency_band(published: str | None, wb: RunWorkbook | None = None) -> str:
    """The recency band a date earns against the run's pinned reference date.

    AUD-0020: a future-dated 'planned' fact made 2019 evidence CURRENT,
    because the ladder was fed the best date in the record rather than the
    date the source was published. A date in the future is not a publication
    date; it is a plan, and it bands UNVERIFIED.

    A month, a quarter or a bare year IS a date (QA audit F-L11-031,
    29-09-2026): `engine/dates.py` resolves them the way the app does — a
    quarter to its end — so `2025-Q4` bands like the app bands it, not as
    undated."""
    from . import dates as _dates
    d = _dates.resolve(published)
    if not d:
        return C.RECENCY_UNVERIFIED
    ref = _dt.date.today()
    if wb is not None:
        r = _dates.resolve(wb.metadata().get("reference_date"))
        if r:
            ref = r
    if d > ref:
        return C.RECENCY_UNVERIFIED
    months = (ref.year - d.year) * 12 + (ref.month - d.month)
    for word, hi in C.RECENCY_LADDER:
        if months < hi:
            return word
    return C.RECENCY_ARCHIVAL


def assert_actor_scope(actor, op: str, cells=None) -> None:
    """Refuse a write the actor's tier may not make (`engine/scope.py`).

    Called at the END of each writer's validation, so a more specific
    refusal — an unresolvable cell, a failed independence check — keeps its
    own wording. An actor of None is unconstrained: every caller that does
    not name one is asking the library, not acting as an agent.
    """
    from . import scope as _scope
    why = _scope.violation(actor, op, cells or [])
    if why:
        raise LedgerRefusal(why)


# ── search ───────────────────────────────────────────────────────────────

#: The tools a category LANE holds. Every other SEARCH_TOOLS entry is a
#: connector the lane cannot call: its rows come from the conducting
#: session's relay subagents — a different conversation, bounded by its own
#: batch file. Measured 2026-09-30 (SWBC): relay rows were charged to the
#: category window, so a lane was walled at "61/60" after firing five
#: searches of its own.
LANE_SEARCH_TOOLS = ("web_search", "web_fetch")


def _search_scope(row: dict) -> str:
    """The conversation a Search_Log row belongs to: its cell's category, or
    PRELIM for institution-profile retrieval that names no cell, or RELAY for
    a connector search the in-session relay fired."""
    cell = str(row.get("SubCap_ID") or "").strip()
    # A row with no cell is PRELIM retrieval whatever tool ran it. The relay
    # always services a lane's request FOR a cell, so a cell-less connector
    # search was never the relay's — and counting it as RELAY walled the
    # PRELIM connector pass (Susser Bank, 2026-10-05: an Issue_Register
    # registry sweep refused at "RELAY: 870 since its last checkpoint").
    if not cell:
        return "PRELIM"
    if (str(row.get("Tool") or "").strip() not in LANE_SEARCH_TOOLS
            and not _is_category_producer(row.get("Actor"), cell)):
        return "RELAY"
    return cell.split(".")[0]


def _is_category_producer(actor, cell: str) -> bool:
    """A connector search a category researcher fired ITSELF (an in-session
    workflow agent holds the connectors) is that category's retrieval and
    counts against its window; only the relay's searches are RELAY's."""
    a = str(actor or "").strip().lower()
    cat = (cell.split(".")[0] if cell else "").lower()
    return bool(cat) and a == f"research-{cat}-producer"


def _collector_scope(actor, cells) -> str | None:
    """The window of a lean collector lane: its CAPABILITY, not its category.

    Measured 2026-10-09, R-IMA-20261009 P2C1: eight collector lanes ran side
    by side as one actor (`research-p2c1-collector`), each its OWN headless
    conversation, and the category window — one conversation's ceiling —
    counted all eight together. It reached 60 while lanes 4, 5 and 7 were
    still logging, refused every search they had already fired (19 ops), and
    14 cells closed nothing for want of a logged primary. The ceiling guards a
    conversation's context; a collector's conversation is its batch, and a
    batch is whole capabilities (one primary per cell plus five volleys, ~n+5
    distinct ops, far below 60). So each capability carries its own window:
    a lane that fires sixty genuinely different searches on one capability
    still hits the wall."""
    a = str(actor or "").strip().lower()
    if not (a.startswith("research-") and a.endswith("-collector")) or not cells:
        return None
    caps = {".".join(str(c).split(".")[:2]) for c in cells}
    return caps.pop() if len(caps) == 1 else None


def _ops_since_checkpoint(wb: RunWorkbook, scope: str | None = None) -> int:
    """Searches FIRED since the last recorded checkpoint.

    Read from the workbook's own metadata rather than by importing runstate,
    which imports this module — the mark is a plain integer and does not
    justify a cycle. A run that has never checkpointed measures from zero,
    which is correct: its whole history is one conversation.

    Fired, not rows written. One search that bears on a capability's cells
    lands one row per cell — `volley_status` matches `SubCap_ID` exactly, so
    a sibling with no row of its own reads as never searched — and counting
    those rows would charge a lane five ops for one tool call. Measured on
    the real catalogue at capability grain: a 57-cell category fires 195
    searches and writes 627 rows; the raw count would wall it at a ceiling
    of 60 three times more often than the retrieval it actually did.

    This ceiling is a CONTEXT-preservation device — "a conversation that has
    fired this many searches must checkpoint and stop" — and context is
    spent by the tool call, not by the ledger write. So the unit is the
    distinct (query, tool, facet) a conversation put to the world. A lane
    firing sixty genuinely different searches still hits the wall, which is
    the half that must not soften (MEM-0338 / R27).
    """
    rows = wb.rows("Search_Log")
    try:
        cp = json.loads(wb.metadata().get("checkpoint") or "{}")
    except (ValueError, TypeError):
        cp = {}
    # PER CONVERSATION MEANS PER LANE. Measured 2026-09-30 (SWBC): the window
    # was run-wide — Search_Log carries no actor, and one global mark — so
    # sixteen parallel category lanes shared ONE window of 60. PRELIM had
    # already spent part of it; two lanes were walled at 60 in round 0, and
    # no lane could checkpoint (there is no CLI for it). A 760-cell run got
    # 60 searches. The window is now scoped to the conversation's category
    # (PRELIM on its own), each with its own mark.
    marks = cp.get("marks") if isinstance(cp.get("marks"), dict) else {}
    if scope is not None and scope in marks:
        mark = int(marks.get(scope) or 0)
    else:
        try:
            mark = int(cp.get("search_ops") or 0)
        except (ValueError, TypeError):
            mark = 0
    since = [(i, r) for i, r in enumerate(rows) if i >= max(0, mark)]
    if scope is not None and "." not in scope:
        since = [(i, r) for i, r in since if _search_scope(r) == scope]
    since = [r for _i, r in since]
    if scope is not None and "." in scope:
        # a collector lane's window is its CAPABILITY (see `_collector_scope`)
        since = [r for r in since
                 if str(r.get("SubCap_ID") or "").strip().startswith(scope + ".")]
    return len({(str(r.get("Query") or "").strip(),
                 str(r.get("Tool") or "").strip(),
                 str(r.get("Facet") or "").strip()) for r in since})


def windows(wb: RunWorkbook) -> dict:
    """Every conversation's search window: {scope: distinct searches since
    that scope's last checkpoint} for PRELIM, RELAY and each category that
    has a Search_Log row."""
    scopes = {_search_scope(r) for r in wb.rows("Search_Log")}
    return {s: _ops_since_checkpoint(wb, s) for s in sorted(scopes)}


def worst_window(wb: RunWorkbook) -> tuple:
    """(scope, since) for the conversation closest to its ceiling — the
    run-level reading of a per-conversation rule. A run with no search has
    no window: ("", 0)."""
    w = windows(wb)
    if not w:
        return "", 0
    scope = max(w, key=lambda k: (w[k], k))
    return scope, w[scope]


def append_search(wb: RunWorkbook, *, subcap, facet: str | None,
                  query: str, tool: str, hits: int, kept: int,
                  outcome: str = "", prelim: bool = False,
                  actor: str | None = None) -> int:
    """Log one search op and return the running count.

    Every search is logged before its results are used, so the budget check
    reads a real number rather than an agent's recollection of one.

    A search names its CELL and its FACET, or it is a PRELIM search
    (`prelim=True`: institution-profile retrieval that belongs to no cell).
    Measured 2026-09-03: `append_search(subcap=None, facet=None,
    tool="my-made-up-tool")` was accepted — a row that spent the search
    budget and counted toward no volley, with a tool nobody could census.
    The tool vocabulary is closed (contract.SEARCH_TOOLS) so the gate can
    see WHICH connectors were asked before a cell is declared empty.

    `subcap` takes a cell or a SEQUENCE of cells, and a sequence writes one
    row per cell. That is not bookkeeping: `volley_status` matches
    `SubCap_ID` exactly, so a capability sibling with no row of its own
    reads as never searched and `absence_unsearched` blocks it — one query
    that genuinely bears on five cells has to say so five times or four of
    them are unworked by the only measure the gate can take.

    The ceiling is charged ONCE for the group, because one tool call was
    made (see `_ops_since_checkpoint`). The facet, tool, query, timestamp
    and hit counts are the same on every row by construction — they were one
    search, and `hits`/`kept` describe THAT SEARCH, not a per-cell triage
    nobody performed. So a fanned-out group repeats them rather than
    splitting them: `kept_ratio` is a ratio and survives, but the absolute
    hit census over a fanned run counts the search once per cell it bore on.
    Which cell each kept source actually grounds is settled where it is
    settled — `append_evidence(subcaps=[...])` — not here.
    """
    _refuse_on_drift(wb)
    if facet is not None and facet not in C.DQ_FACETS and not (
            prelim and facet in C.PRELIM_SHEET_FACETS):
        raise LedgerRefusal(
            f"facet {facet!r} is not in {C.DQ_FACETS}"
            + (f" (with --prelim also {C.PRELIM_SHEET_FACETS})" if prelim else ""))
    tool = str(tool or "").strip().lower()
    if tool not in C.SEARCH_TOOLS:
        raise LedgerRefusal(
            f"tool {tool!r} is not one of {C.SEARCH_TOOLS}. The Search_Log "
            f"records WHICH connector ran so the gate can count the "
            f"enrichment effort behind an empty cell; a free-text tool name "
            f"is a tool nobody can count.")
    cells = ([] if subcap is None else
             [subcap] if isinstance(subcap, str) else list(subcap))
    cells = [str(c).strip() for c in cells if str(c).strip()]
    if not prelim and (not cells or not str(facet or "").strip()):
        raise LedgerRefusal(
            "a search that names no --subcap and no --facet counts toward "
            "nothing the gate measures. Pass --subcap <cell> --facet "
            "<primary|works|fails|value|contradicts|corroborates|ai_*>, or "
            "--prelim for institution-profile retrieval that belongs to no "
            "cell.")
    if prelim:
        facet = facet or None
    assert_actor_scope(actor, "search", cells)
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
    # Every search is bounded (the wall test): lane tools and a category
    # researcher's own connector volleys against the category's window, the
    # relay's connector volleys against RELAY's. Uncounted relay rows were a
    # hole once researchers began firing connectors themselves (2026-09-30).
    scope = _collector_scope(actor, cells) or _search_scope(
        {"Tool": tool, "Actor": actor,
         "SubCap_ID": "" if prelim or not cells else cells[0]})
    since = _ops_since_checkpoint(wb, scope)
    if since >= SEARCH_OP_CEILING:
        raise LedgerRefusal(
            f"search-op ceiling reached for {scope}: {since} since its last "
            f"checkpoint, cap {SEARCH_OP_CEILING}. Checkpoint and stop — "
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
    # THE SAME QUESTION IS NOT ASKED TWICE. Measured 28-09-2026 (QA audit
    # F-D05-033): `engine.cli search` accepted the same query twice into the
    # Search_Log (rows 1 and 2 identical), and the only dedupe in the system
    # was the relay's, over relay requests. A repeat asks the world the same
    # question and pays for the same answer; the log is the record, and a
    # query it already holds — same identity, same tool, same facet — is
    # refused unless it is being extended to a cell the search was not logged
    # against (one call, one row per cell it bears on, exactly as the fan-out
    # rule says). The facet is part of the question: the same text asked of
    # `works` and of `fails` is two questions, and the ceiling counts
    # questions (test_search_fanout pins that; a facet-blind identity
    # refused the second and contradicted it).
    prior = prior_searches(wb, query, tool, facet=facet)
    if prior:
        logged_cells = {str(r.get("SubCap_ID") or "").strip() for r in prior}
        new_cells = [c for c in cells if c not in logged_cells]
        if not new_cells:
            first = prior[0]
            raise LedgerRefusal(
                f"query already logged for this run at seq {first.get('Seq')} "
                f"through {tool} (hits {first.get('Hits')}, kept "
                f"{first.get('Kept')}, outcome {str(first.get('Outcome') or '')[:60]!r}): "
                f"{query!r}. A repeated search pays for the answer the log "
                f"already holds. Work from that row, rephrase from a different "
                f"angle (another facet's operators, a proxy class, a named "
                f"artefact), or fire a different tool — `prior_queries` on the "
                f"card and the relay brief list what has been asked "
                f"(QA audit F-D05-033, 28-09-2026).")
        cells = new_cells
    # Seq is allocated past the HIGHEST recorded value, not from the row
    # count: a row the strip or a repair removed left `len(rows)` below the
    # last Seq, and the next searches reused 6250-6253 on Arbor Bank
    # (2026-10-06) — four rows nobody can cite unambiguously.
    seq = max((int(float(r.get("Seq") or 0)) for r in wb.rows("Search_Log")
               if str(r.get("Seq") or "").strip()), default=0)
    stamp = _utcnow()
    for cell in (cells or [None]):
        seq += 1
        wb.append("Search_Log", {
            "Seq": seq, "Timestamp": stamp, "SubCap_ID": cell,
            "Facet": facet, "Query": query, "Tool": tool, "Hits": hits,
            "Kept": kept, "Outcome": outcome,
        })
    return seq


def prior_searches(wb: RunWorkbook, query: str, tool: str,
                   facet: str | None = None) -> list[dict]:
    """Search_Log rows carrying this query's identity through this tool —
    at this facet when one is given, at any facet when `facet` is None (the
    "was this ever fired" reading the stub, the relay and the fixtures
    take)."""
    key = Q.norm_query(query)
    tool = str(tool or "").strip().lower()
    want = str(facet or "").strip().lower()
    if not key:
        return []
    return [r for r in wb.rows("Search_Log")
            if Q.norm_query(r.get("Query")) == key
            and str(r.get("Tool") or "").strip().lower() == tool
            and (not want or str(r.get("Facet") or "").strip().lower() == want)]


def prior_queries(wb: RunWorkbook, cells=None, *, prelim: bool = False) -> list[dict]:
    """The exclusion list: every distinct (query, tool) already fired for
    these cells (or run-level rows when `prelim`), with what it returned.
    This is what a relay brief states to the specialist and what a card can
    print, so a rephrased repeat is a choice rather than an accident
    (QA audit D-16, 28-09-2026)."""
    want = {str(c).strip() for c in (cells or []) if str(c).strip()}
    out: dict[tuple, dict] = {}
    for r in wb.rows("Search_Log"):
        q = str(r.get("Query") or "").strip()
        if not q:
            continue
        cell = str(r.get("SubCap_ID") or "").strip()
        if want and cell not in want:
            continue
        if not want and not prelim and cell:
            continue
        if prelim and cell:
            continue
        key = (Q.norm_query(q), str(r.get("Tool") or "").strip().lower())
        row = out.get(key)
        if row is None:
            row = {"seq": r.get("Seq"), "query": q, "tool": key[1],
                   "facet": str(r.get("Facet") or "").strip(),
                   "facets": [],
                   "cells": [], "hits": r.get("Hits"), "kept": r.get("Kept"),
                   "outcome": str(r.get("Outcome") or "").strip()}
            out[key] = row
        fc = str(r.get("Facet") or "").strip()
        if fc and fc not in row["facets"]:
            row["facets"].append(fc)
        if cell and cell not in row["cells"]:
            row["cells"].append(cell)
    return sorted(out.values(), key=lambda r: (int(r["seq"] or 0), r["tool"]))


# ── synthesis ────────────────────────────────────────────────────────────

#: The working-area fields a synthesis must carry, and the minimum each has
#: to reach. Length is a floor, never the test — `quality` decides substance.
SYNTHESIS_REQUIRED = {
    "Dominant_Claim": 20, "What_We_Found": 120, "Triangulation": 40,
    "Ceiling_Reasoning": 20, "Why_It_Matters": 30, "DMA_Impact": 30,
}
DQ_FIELDS = ("DQ_Works", "DQ_Fails", "DQ_Value", "DQ_Corroborates",
             "DQ_Contradicts")


def _agent_session() -> str:
    """A token stable across ONE agent run and distinct between runs, so
    independence can be checked by SESSION rather than by a free-text label a
    single agent can relabel. The harness sets it per dispatched agent; a
    subprocess the agent spawns inherits it. Empty when unset (older records)."""
    import os
    for k in ("DMA_AGENT_SESSION", "CLAUDE_AGENT_ID", "CLAUDE_SESSION_ID"):
        v = os.environ.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return ""


#: Role/function suffix tokens that name what an actor DID, not WHO it is.
#: Stripping them leaves the base identity, so `x-producer` and `x-challenger`
#: collapse to the same `x` — a relabel of one agent, not two agents.
_ROLE_TOKENS = frozenset({
    "producer", "challenger", "reviewer", "review", "challenge", "synthesis",
    "synthesist", "synthesiser", "synthesizer", "synth", "author", "verifier",
    "grader", "critic", "adjudicator", "independent", "self", "actor", "agent"})


def _base_identity(name: str) -> str:
    toks = [t for t in re.split(r"[^a-z0-9]+", str(name or "").lower()) if t]
    core = [t for t in toks if t not in _ROLE_TOKENS]
    return " ".join(core)


def challenge_independence(author: str, author_session: str,
                           challenger: str, challenger_session: str
                           ) -> tuple[bool, str]:
    """Is a challenge INDEPENDENT of the synthesis it reviews? (AUD-0113/0117)

    ONE rule, used by BOTH the write path (`record_challenge`, which refuses a
    dependent challenge) and the READ path (the floors gate, which flags one
    already on the workbook — a challenge written before this rule existed, or
    by a tool that bypassed the ledger). Two answers to one question must not
    drift: the gate used to catch only an EXACT actor match, so a relabel
    (`x-producer` synthesises, `x-challenger` challenges, no session tokens)
    passed the gate though the write path would now refuse it.

    Session proof wins: two present, distinct sessions are two runs, and the
    labels may then legitimately share a base. Absent that proof, a shared base
    identity is a relabel of one run. Returns (independent, reason) where reason
    is '' when independent, else 'same_actor' / 'same_session' / 'relabel'."""
    a = str(author or "").strip()
    c = str(challenger or "").strip()
    asess = str(author_session or "").strip()
    csess = str(challenger_session or "").strip()
    if a and c and a == c:
        return (False, "same_actor")
    if asess and csess and asess == csess:
        return (False, "same_session")
    if asess and csess and asess != csess:
        return (True, "")            # distinct sessions prove two runs
    if _base_identity(c) and _base_identity(c) == _base_identity(a):
        return (False, "relabel")    # shared base, no session proof
    return (True, "")


def record_provenance(wb: RunWorkbook, subcap: str, step: str, actor: str,
                      detail: str = "", session: str = "") -> None:
    """Who did this step. Authorship is what makes independence checkable."""
    if step not in C.PROVENANCE_STEPS:
        raise LedgerRefusal(f"step {step!r} not in {C.PROVENANCE_STEPS}")
    if not str(actor or "").strip():
        raise LedgerRefusal(
            "an unattributed write cannot be checked for independence; name "
            "the actor (an agent name, a session id, a person)")
    wb.append("Provenance", {"SubCap_ID": subcap, "Step": step,
                             "Actor": str(actor).strip(), "At": _utcnow(),
                             "Detail": detail,
                             "Session": str(session or _agent_session()).strip()})


def actor_for(wb: RunWorkbook, subcap: str, step: str) -> str | None:
    """The most recent actor for one step of one subcap."""
    hits = [r for r in wb.rows("Provenance")
            if str(r.get("SubCap_ID") or "") == subcap
            and str(r.get("Step") or "") == step]
    return str(hits[-1]["Actor"]) if hits else None


def session_for(wb: RunWorkbook, subcap: str, step: str) -> str:
    """The most recent session token for one step of one subcap ('' if none)."""
    hits = [r for r in wb.rows("Provenance")
            if str(r.get("SubCap_ID") or "") == subcap
            and str(r.get("Step") or "") == step]
    return str(hits[-1].get("Session") or "").strip() if hits else ""


def record_challenge(wb: RunWorkbook, subcap: str, *, verdict: str, actor: str,
                     dimensions: dict, rationale: str,
                     ceiling_band_delta: str = "", session: str = "") -> dict:
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
    # ONE independence rule, shared with the floors gate (challenge_independence).
    # A distinct SESSION token (set by the harness per agent, inherited by the
    # subprocesses it spawns) proves a different run; absent it, a shared base
    # identity is a relabel of one run (AUD-0113) and refused.
    ch_session = str(session or _agent_session()).strip()
    syn_session = session_for(wb, subcap, "synthesis")
    independent, why = challenge_independence(
        author, syn_session, str(actor).strip(), ch_session)
    if not independent:
        if why == "same_actor":
            raise LedgerRefusal(
                f"{actor!r} wrote this synthesis and cannot also be its "
                f"challenger. A verdict on your own work is a feeling; the "
                f"learning loop's grader is independent BY CONSTRUCTION and the "
                f"research challenge has to be independent by record.")
        if why == "same_session":
            raise LedgerRefusal(
                f"the challenge was recorded in the SAME session "
                f"({ch_session!r}) as the synthesis it reviews. One agent run "
                f"cannot be its own independent challenger, whatever actor "
                f"label it uses. Record the challenge from a genuinely separate "
                f"agent run.")
        raise LedgerRefusal(
            f"{actor!r} and the synthesis author {author!r} are the same "
            f"identity under a different role label ('{_base_identity(actor)}') "
            f"— a relabel is not independence. Record the challenge from a "
            f"genuinely separate agent run, or carry a distinct session token "
            f"(both this challenge and the synthesis must record one) to prove "
            f"the runs differ.")
    # Scope AFTER independence, so those refusals keep their own
    # wording: "you wrote this" is the more useful sentence when both
    # are true. This one catches the rest — a tier that does not judge.
    assert_actor_scope(actor, "challenge", [subcap])
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
        "Ceiling_Band_Delta": ceiling_band_delta, "At": _utcnow(),
        "Session": ch_session})
    record_provenance(wb, subcap, "challenge", actor,
                      f"{verdict}; {len(dimensions)} dimensions",
                      session=ch_session)
    wb.set_scoring(subcap, {"Challenge_Verdict": verdict})
    return {"subcap": subcap, "verdict": verdict, "challenger": actor,
            "author": author, "failed_dimensions": failed}


def challenge_for(wb: RunWorkbook, subcap: str) -> dict | None:
    hits = [r for r in wb.rows("Challenge_Log")
            if str(r.get("SubCap_ID") or "") == subcap]
    return hits[-1] if hits else None


#: Words that NAME an inference. An INFERENCE whose text carries none of
#: them states a conclusion and hides the step (the challenger's own test:
#: "INFERENCE needs 2+ evidence ids plus named logic").
_INFERENCE_MARKERS = re.compile(
    r"\b(infer|inferred|inference|implies|imply|suggests?|indicat(?:es|ing)|"
    r"likely|probabl[ye]|consistent with|therefore|so (?:the|it|they)|because|"
    r"points? to|which means)\b", re.I)

#: The highest legal score inside each band word — the same table as
#: `assessment.BAND_TOP` (pinned equal by test; assessment imports this module).
BAND_TOP = {"ACTIVATING": 1.75, "BUILDING": 2.75, "COMPETING": 3.75,
            "DIFFERENTIATING": 5.0}
#: A claim that says WHEN it was true. Years are allowed only when an excerpt
#: on the cell carries them (the ungrounded-figure rule), so the words carry it.
_TEMPORAL_QUALIFIER = re.compile(
    r"\bas of\b|\bas at\b|\bat the time\b|\bhistoric(al(ly)?)?\b|\bpreviously\b|"
    r"\bformerly\b|\bundated\b|\b(in|since|from|by|until) (19|20)\d\d\b|"
    r"\b(stated|reported|published|announced|disclosed|described) (in|on|as of)\b|"
    r"\blast (stated|reported|published|evidenced)\b|\bmost recent (public|published)\b|"
    r"\bno (current|recent) (source|evidence)\b", re.I)


def label_fit_problems(wb: RunWorkbook, subcap: str, merged: dict,
                       row_eids: list[str]) -> list[str]:
    """The claim-label rules the independent challenger applied by hand,
    enforced where the synthesis is written.

    Measured 2026-10-05..08 (Arbor, Susser, Cross): 205 / 135 / 26 challenge
    FAILs, and the FAIL text was the SAME four sentences — "INFERENCE needs
    2+ evidence ids and a named inference", "FACT needs two source
    identities", "evidence[] is empty: the claim asserts specific content
    but cites no registered row", "cell is in open_contradictions and the
    disposition is empty". Each one cost a Sonnet challenge lane, a repair
    batch and a re-challenge — the research rounds the owner measured. A
    rule a challenger can state in one sentence is a rule the ledger can
    refuse in one line, and the challenge lane then spends its judgement on
    the dimensions a rule cannot read (synthesis quality, ceiling reasoning).

    The SKILL's own table is the authority: FACT = T1/T2 ids, two source
    identities; INFERENCE = 2+ evidence ids + the logic; HYPOTHESIS = ids +
    the proxy attempts; CEILING_ESTIMATE = ids + the uncertainty."""
    out: list[str] = []
    label = str(merged.get("Claim_Label") or "").strip().upper()
    register = wb.evidence_index()
    # the row carries `E-004:F1` (fact-qualified); the register is keyed by E-id
    row_eids = [str(e).split(":")[0] for e in row_eids if str(e).strip()]
    rows = [register[e] for e in row_eids if e in register]
    idents = set()
    for r in rows:
        url = str(r.get("Source_URL") or "")
        idents.add(host_of(url) or str(r.get("Source_Name") or "").strip().lower())
    idents.discard("")
    claim = str(merged.get("Dominant_Claim") or "")
    absence = Q.claims_absence(claim) or str(
        merged.get("Absence_Claimed") or "").strip().upper() in ("YES", "TRUE", "1")
    if label == "FACT" and rows and len(idents) < 2:
        out.append(
            f"FACT rests on one source identity ({', '.join(sorted(idents)) or 'unnamed'}); "
            f"the challenger refuses it as claim_label_fit and the gate as "
            f"single_source_fact — register a second independent source, or label "
            f"the claim INFERENCE and name the step")
    if label == "INFERENCE":
        if len(row_eids) < 2 and not absence:
            out.append(
                f"INFERENCE cites {len(row_eids)} evidence id(s); the label needs 2+ "
                f"ids plus the logic (SKILL claim-label table). One row supports a "
                f"direct reading (FACT on T1/T2) or a HYPOTHESIS with its proxy attempts")
        logic = " ".join(str(merged.get(k) or "") for k in
                         ("Dominant_Claim", "Triangulation", "What_We_Found"))
        if not _INFERENCE_MARKERS.search(logic):
            out.append(
                "INFERENCE names no inference: say what is inferred FROM what "
                "(implies / suggests / likely / consistent with …) in Dominant_Claim "
                "or Triangulation — a conclusion with the step hidden is what the "
                "challenger fails as claim_label_fit")
    if label in ("FACT", "INFERENCE", "CEILING_ESTIMATE") and not row_eids and not absence:
        out.append(
            f"{label} with no evidence id on the row: the claim asserts specific "
            f"content and cites nothing a challenger can open (evidence_total=0). "
            f"Register the source, or close the cell through `engine.cli absence`")
    # THE BAND MUST NOT CLAIM MORE THAN THE EVIDENCE'S OWN CAP (R-INTERAC-
    # 20261010, P3C1 round 1: four cells citing only interac.ca held at
    # Building and failed ceiling_reasoning; every repair round re-paid a
    # sonnet lane). `assessment.mechanical_caps` already refuses the SCORE
    # above 2.0 on own-site-only evidence and above 3.0 on one source
    # identity; the band a synthesis states is that ceiling's conclusion, so
    # the same caps bind it here, at the write, and the challenger never
    # meets the mismatch.
    band = str(merged.get("Ceiling_Band") or "").strip().upper()
    if rows and band in BAND_TOP:
        hosts = {host_of(str(r.get("Source_URL") or "")) for r in rows}
        hosts.discard("")
        own = own_hosts(wb)
        own_only = bool(hosts) and bool(own) and all(
            any(h == o or h.endswith("." + o) for o in own) for h in hosts) \
            and len(hosts) == len(idents)
        cap, why = (2.0, "every source sits on the entity's own site") if own_only else \
                   (3.0, "the evidence has one source identity") if len(idents) < 2 else \
                   (5.0, "")
        if BAND_TOP[band] > cap:
            allowed = [b.title() for b, top in BAND_TOP.items() if top <= cap]
            out.append(
                f"Ceiling_Band {band.title()} tops at {BAND_TOP[band]} but {why} "
                f"(cap {cap}): state the band the cap allows ({' or '.join(allowed)}) "
                f"and say so in Ceiling_Reasoning — the challenger fails the "
                f"mismatch as ceiling_reasoning")
    # TENSE FOLLOWS RECENCY (R-INTERAC-20261010, P3C1 round 1: five cells whose
    # every row was DATED/STALE/ARCHIVAL written in unqualified present tense,
    # failed as recency). When no cited row is CURRENT or RECENT, the claim
    # must say when it was true.
    # Only a row that STATES an old date triggers it: an undated (UNVERIFIED)
    # row renders with its own band and the challenger passed present tense on
    # it (2 of 2 measured) — refusing those would cost a write turn for nothing.
    fresh = {"CURRENT", "RECENT"}
    aged = {"DATED", "STALE", C.RECENCY_ARCHIVAL}
    recencies = {str(r.get("Recency") or "").strip().upper() for r in rows}
    if rows and not (recencies & fresh) and (recencies & aged) and not absence:
        text = " ".join(str(merged.get(k) or "") for k in ("Dominant_Claim", "What_We_Found"))
        if not _TEMPORAL_QUALIFIER.search(text):
            out.append(
                f"every row on this cell is {'/'.join(sorted(recencies)) or 'undated'} "
                f"— none CURRENT or RECENT — and the claim is in unqualified present "
                f"tense: say when it was true (as of <the row's date>, historically, "
                f"at the time, undated) — the challenger fails present tense on "
                f"stale rows as recency")
    contra = str(merged.get("DQ_Contradicts") or "").strip()
    disp = str(merged.get("Contradiction_Disposition") or "").strip()
    if contra and not contra.upper().startswith(("NOT_RUN", "NO_FINDING", "NONE")) \
            and len(disp) < 20:
        out.append(
            "DQ_Contradicts names a finding and Contradiction_Disposition does not "
            "say what the synthesis did with it (>= 20 chars: outweighed by …, "
            "superseded by …, reconciled as …) — an open contradiction fails "
            "contradiction_handling at challenge")
    return out


def append_synthesis(wb: RunWorkbook, subcap: str, record: dict,
                     actor: str | None = None, session: str = "") -> dict:
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
    # THE ABSENCE FLAG HAS ONE WRITER. A synthesis record on an EMPTY row
    # that carries Absence_Claimed is trying to close the cell as an absence
    # without the volleys, the ladder and the register check that
    # `declare_absence` proves — refused, naming the sanctioned command. On
    # an evidenced row the flag is a label on the claim (the source itself
    # documents an absence) and `is_declared_absent` never reads it as a
    # closed cell, because the row carries evidence.
    row_eids = [i for i in _split_ids(row.get("Evidence_IDs"))
                if i and i != C.NO_EVIDENCE]
    if (not row_eids
            and str(record.get("Absence_Claimed") or "").strip().upper()
            in ("YES", "TRUE", "1")
            and subcap not in declared_absences(wb)):
        problems.append(
            "Absence_Claimed is not a synthesis field on an empty cell. A "
            "cell with no evidence closes ONLY through `engine.cli absence "
            f"--run <R> --subcap {subcap} --actor <you> --ladder '<json>' "
            "--proxy-log '…' --hunted '…'`, which proves the five volleys, "
            "the primary question, an enrichment connector and the ladder "
            "before it writes the flag")
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
    problems += label_fit_problems(wb, subcap, merged, row_eids)
    # SMEAR, AT THE JUDGEMENT (R-INTERAC-20261010, P3C1.7.1/7.2/7.4): the gate
    # blocks a category whose siblings draw >60% of their evidence from the
    # same rows, and no challenge or repair round can change evidence. The
    # writer can: detach a shared row from the cells it does not answer, or
    # register the span each sibling's own question needs — before writing.
    sm = smear_of_cell(wb, subcap) if row_eids else None
    if sm:
        problems.append(
            f"evidence_smear: {sm['detail']} ({', '.join(sm['subcaps'])}; shared "
            f"{', '.join(sm['shared_evidence'])}) — the gate blocks it and no "
            f"repair round can undo it. Before synthesising: `engine.cli detach "
            f"--e-id <E> --subcap <cell> --reason '<why it does not answer that "
            f"cell>'` from the siblings a shared row does not answer, or register "
            f"a span specific to this cell")
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
    assert_actor_scope(actor, "synthesis", [subcap])
    payload = {k: v for k, v in record.items() if k in C.PILLAR_COLUMNS}
    payload["Retrieved_At"] = _utcnow()
    # A NEW SYNTHESIS VOIDS THE OLD VERDICT (measured 2026-10-01, Cross
    # Insurance): a challenger FAILs a cell, the producer repairs it, and
    # the row kept its FAIL. challenge-batch skips any row carrying a
    # verdict and `assessment score` refuses any evidenced row that is not
    # PASS, so a repaired cell could never be re-challenged nor scored. The
    # verdict judged prose that no longer exists; clearing it puts the cell
    # back in the challenge queue, and the floors gate reports it as
    # challenge_missing until an independent actor judges the new text.
    # And an author never writes a verdict at all: Challenge_Verdict is a
    # pillar column, so a synthesis record carrying "PASS" used to land as
    # the cell's challenge verdict with no challenger involved. Only
    # `record_challenge`, which proves independence, sets it.
    payload.pop("Challenge_Verdict", None)
    if str(row.get("Challenge_Verdict") or "").strip():
        payload["Challenge_Verdict"] = ""
    wb.set_scoring(subcap, payload)
    if actor:
        record_provenance(wb, subcap, "synthesis", actor, session=session)
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

#: Every verdict a Gate_Log row may carry.
#:
#: PENDING_ORCHESTRATOR joined the three originals on 2026-09-14, for the one
#: state the vocabulary could not say: the work was prepared and handed to the
#: conductor and has not come back yet. Written as a FAIL it would have been
#: re-dispatched or disclosed as a gap; written as NOT_RUN it would have read
#: as "nobody looked". Neither is true of a relay batch sitting on disk with
#: its requests still OPEN — that is work in flight, and the gate must be able
#: to say so without spending a heal on it.
#: PASS_SCOPE: a stage's NAMED scope (--only-categories) passed while the
#: stage stays open; WARN: a non-blocking fact the owner must see (a handoff
#: worked by in-session agents instead of a workflow). Both were written by
#: the driver on 2026-10-09 before they were here, and `_record` swallowed the
#: refusal — every verdict the driver writes is now pinned by a test.
GATE_VERDICTS = ("PASS", "FAIL", "NOT_RUN", "PENDING_ORCHESTRATOR", "PASS_SCOPE", "WARN")


def append_gate(wb: RunWorkbook, *, gate: str, scope: str, verdict: str,
                detail: str = "", blocking: bool = True) -> None:
    if verdict not in GATE_VERDICTS:
        raise LedgerRefusal(f"verdict {verdict!r} must be one of {GATE_VERDICTS}")
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
    # THE WINDOW IS PER CONVERSATION (2026-09-30), SO THE DECISION IS TOO.
    # Asked about one category, the window is that category's. Asked about
    # the run (orient, the watchdog, the hooks — none of which IS a
    # conversation), the decision is the WORST conversation's window, named,
    # never the run-wide count from the global mark: that count kept
    # reporting a promoted run as AT_BUDGET_CEILING ("6332 search-ops
    # against a ceiling of 60", Arbor Bank, 2026-10-07) with every lane's
    # own window at zero, and cli.py had patched the same defect for one
    # command only.
    if category:
        scope, since = category, _ops_since_checkpoint(wb, category)
    else:
        scope, since = worst_window(wb)
    return {
        # `search_ops` is a LIFETIME count (spend worth seeing); the budget is
        # `search_ops_since_checkpoint` against the ceiling. A lane that read
        # the first as usage stopped at "55 of 60" with 1 used (2026-09-30).
        "search_ops": n,
        "search_ops_since_checkpoint": since,
        "window_scope": scope,
        "window_remaining": max(0, SEARCH_OP_CEILING - since),
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


# ── the five volleys, measured per subcap ────────────────────────────────

def askable_facets(wb: RunWorkbook, subcap: str) -> list[str]:
    """The volley facets this run's evidence mode can fire for one subcap.

    From the DQ bank when the KG was built (a facet whose DQ is deferred in
    this mode — `contradicts` in an INTERNAL run — is not owed a search);
    the five catalogue facets when it was not."""
    from . import kg as _kg
    split = _kg.dqs_for(wb, subcap)
    if split["ask"] or split["deferred"]:
        return [str(d["facet"]) for d in split["ask"]
                if str(d["facet"]) in C.FACETS]
    return list(C.FACETS)


def volley_status(wb: RunWorkbook, subcap: str,
                  searches: list[dict] | None = None) -> dict:
    """Which of the subcap's askable volleys have a LOGGED search behind them.

    Owner, 2026-09-03: "some subcaps are marked as no evidence without any
    enrichment efforts … not even looking at the 5 volley structure and
    related DQ set." The protocol has said 'every volley fires or is NOT_RUN
    with a reason' since AUD-0017, and nothing measured it for a subcap that
    never reached synthesis: one logged query cleared `absence_unsearched`
    and the other four volleys were never asked about. Measured on the
    Golden 1 reference: 307 searches for 690 subcaps, `fails` fired 3 times.
    This is the measurement, per subcap and per facet, that the gate, the
    card and the absence declaration all read."""
    rows = searches if searches is not None else wb.rows("Search_Log")
    mine = [r for r in rows if str(r.get("SubCap_ID") or "").strip() == subcap]
    want = askable_facets(wb, subcap)
    fired = {}
    tools = set()
    for r in mine:
        f = str(r.get("Facet") or "").strip()
        fired[f] = fired.get(f, 0) + 1
        t = str(r.get("Tool") or "").strip()
        if t:
            tools.add(t)
    missing = [f for f in want if not fired.get(f)]
    return {"subcap": subcap, "askable": want,
            "fired": {f: fired.get(f, 0) for f in want},
            "missing": missing, "complete": not missing,
            # The toolkit's own diagnostic question (DQ order 0) and the
            # three AI-overlay probes (orders 6-8) were on every card and in
            # no count — a cell could close with its primary question never
            # asked. Counted here; the gate blocks on the primary.
            "primary_fired": fired.get(C.PRIMARY_FACET, 0),
            "ai_fired": {f: fired.get(f, 0) for f in C.AI_FACETS},
            "searches": len(mine), "tools": sorted(tools),
            "enrichment_tools": sorted(t for t in tools
                                       if t in C.ENRICHMENT_TOOLS)}


def enrichment_status(wb: RunWorkbook, category: str,
                      searches: list | None = None) -> dict:
    """Connector usage for ONE category, read from the Search_Log's Tool
    column — the only place the run records WHICH tool ran a search.

    Owner, 2026-09-07: categories were passing their floors gate with every
    search through bare web_search, the connector work left "aspirational".
    `declare_absence` already refuses an empty cell no enrichment connector
    was asked about; nothing measured the same thing for a category that
    found evidence. This is that measurement — a count, not a verdict; the
    driver's ENRICHMENT gate decides what a zero means and says so."""
    cat = str(category or "").strip().upper()
    rows = searches if searches is not None else wb.rows("Search_Log")
    mine = [r for r in rows if str(r.get("SubCap_ID") or "").strip().upper().startswith(cat)]
    tools: dict[str, int] = {}
    cells_enriched: set[str] = set()
    for r in mine:
        t = str(r.get("Tool") or "").strip().lower()
        if not t:
            continue
        tools[t] = tools.get(t, 0) + 1
        if t in C.ENRICHMENT_TOOLS:
            cells_enriched.add(str(r.get("SubCap_ID") or "").strip().upper())
    enriched = sum(n for t, n in tools.items() if t in C.ENRICHMENT_TOOLS)
    cells = [c for c in wb.selected_subcaps() if str(c).upper().startswith(cat)]
    return {"category": cat, "searches": len(mine), "enrichment_searches": enriched,
            "tools": sorted(tools), "tool_counts": tools,
            "enrichment_tools": sorted(t for t in tools if t in C.ENRICHMENT_TOOLS),
            "cells": len(cells), "cells_with_enrichment": len(cells_enriched & set(cells)),
            "share": (round(enriched / len(mine), 3) if mine else None)}


#: The rungs an absence ladder is climbed in, and the two that are always
#: owed. `direct` is the entity itself; `proxy` is the template's own proxy
#: class for the cell (leadership_title, regulator_filing, org_talent …).
ABSENCE_RUNGS_REQUIRED = ("direct", "proxy")


def enrichment_binding(wb: RunWorkbook) -> dict:
    """What this run's OWN RECORDED BASELINE says about enrichment connectors.

    Measured, never claimed. `connector_contract.write_baseline` records the
    tool list the session actually held when its preflight passed; this reads
    that file and asks the contract whether the enrichment families are among
    them. An agent cannot assert its way past a refusal through this — the
    answer comes from what the preflight WROTE, before any cell was worked.

    Three states, and the difference between them is the whole point (owner,
    2026-08-31: "the connectors may be lost mid session even after being
    attached"):

      known=False  no baseline on disk. UNVERIFIED IS NOT A DIAGNOSIS: every
                   caller must treat this as "a connector may well be bound",
                   never as proof one is not. `watchdog._no_enrichment_connector`
                   takes the same posture.
      bound=True   the baseline holds the required families. A cell with no
                   enrichment search is a cell the lane did not enrich, and
                   the refusals stand.
      bound=False  the baseline is short. No search through a connector was
                   POSSIBLE in this container, and no agent inside it can
                   attach one — they bind once, at session start. Refusing
                   here does not produce the enrichment; it produces a run
                   that can close no cell, pass no gate, and be re-dispatched
                   until something stops it. That is the $96.65 shape.
    """
    out = {"known": False, "bound": False, "missing": [], "reason": ""}
    try:
        import sys as _sys
        from pathlib import Path as _Path
        plugin = _Path(__file__).resolve().parents[3]
        _sys.path.insert(0, str(plugin / "scripts"))
        import connector_contract as cc                       # noqa: PLC0415
        path = _Path(cc.baseline_path(str(wb.path.parent)))
        if not path.is_file():
            return out
        held = json.loads(path.read_text()).get("mcp_tools") or []
        chk = cc.check(held)
    except Exception as e:                                    # noqa: BLE001
        out["reason"] = f"the connector baseline could not be read: {str(e)[:120]}"
        return out
    out["known"] = True
    out["bound"] = bool(chk["ok"])
    out["missing"] = list(chk["missing"])
    out["reason"] = (
        "" if chk["ok"] else
        f"this run's connector baseline is short of {', '.join(chk['missing'])}; "
        f"no enrichment connector answered in the container this run was "
        f"worked in, and a session cannot attach one — they bind at start")
    return out


def _norm_hunt(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _cell_own_hunt_problems(wb: RunWorkbook, subcap: str, hunted: str) -> list:
    """An absence is THIS cell's hunt, not its capability's.

    Measured 2026-10-09 (R-IMA-20261009, P2C2, lean tiers): 52 absences in one
    round, one shared opening; every cell of a capability carried the same
    queries, the same ladder and the same --hunted text, because one primary
    query per capability had been logged against all of its cells. The gate
    counted a volley per cell, and no cell's own diagnostic question was ever
    put to the entity. Two refusals, both answered by asking the cell's own
    question:
      * primary_shared — every `primary` search logged on this cell was
        also logged as the primary of a sibling cell of the capability;
      * hunted_shared — a sibling absence of the same capability already
        carries this exact --hunted text."""
    cap = ".".join(subcap.split(".")[:2])
    sibs = [c for c in wb.selected_subcaps()
            if c != subcap and ".".join(c.split(".")[:2]) == cap]
    if not sibs:
        return []
    problems = []
    rows = wb.rows("Search_Log")
    mine = {_norm_hunt(r.get("Query")) for r in rows
            if str(r.get("SubCap_ID") or "").strip() == subcap
            and str(r.get("Facet") or "").strip() == C.PRIMARY_FACET and r.get("Query")}
    theirs = {_norm_hunt(r.get("Query")) for r in rows
              if str(r.get("SubCap_ID") or "").strip() in sibs
              and str(r.get("Facet") or "").strip() == C.PRIMARY_FACET and r.get("Query")}
    if mine and mine <= theirs:
        problems.append(
            f"primary_shared: every primary search on {subcap} is also a sibling "
            f"cell's primary ({sorted(mine)[0][:80]!r}). The primary is THIS cell's "
            f"own diagnostic question, asked in the entity's own words — fire it "
            f"for {subcap} alone, log it with --subcap {subcap}, then declare")
    want = _norm_hunt(hunted)
    if want:
        for r in wb.scoring_rows():
            sc = str(r.get("SubCap_ID") or "")
            if sc in sibs and _norm_hunt(r.get("What_We_Found")).startswith(
                    "searched and not found: " + want):
                problems.append(
                    f"hunted_shared: {sc} already carries this exact --hunted text; "
                    f"name {subcap}'s own question, the query that asked it and "
                    f"what came back for it")
                break
    return problems


def declare_absence(wb: RunWorkbook, subcap: str, *, actor: str,
                    ladder: list[dict], proxy_log: str,
                    what_was_hunted: str, session: str = "",
                    enrichment_unavailable: bool = False,
                    inferable: str | None = None,
                    validation_question: str | None = None,
                    not_determinable: str | None = None,
                    run=None) -> dict:
    """Close a subcap as a SEARCHED, DECLARED absence — or refuse.

    The only sanctioned way a cell ends a run with NO_EVIDENCE. Before this
    existed a researcher who found nothing had nothing to write, so the row
    stayed seeded (NO_EVIDENCE / NOT_RUN) and read exactly like a cell nobody
    had opened. Refused unless:

      * every askable volley has a logged search for THIS subcap (the five
        facets, in this run's mode) — a volley you did not fire is not a
        volley that found nothing;
      * the ladder names its rungs (direct, proxy, then peer / regulatory as
        reached), each with the query that was fired, and every query is in
        the Search_Log (quality.ladder_report counts the rungs it can prove);
      * the proxy log says what proxy class was hunted (the template names
        one per cell) and what came back instead;
      * the row carries no evidence — a row with evidence is synthesised,
        not declared.

    Writes Absence_Claimed=YES, Proxy_Log, Negative_Ladder, Dominant_Claim
    (the honest sentence), the five DQ_* fields as NO_FINDING lines, and a
    Provenance row naming who declared it. The floors gate then reads the
    row as CLOSED-BY-ABSENCE rather than PENDING."""
    row = wb.scoring_row(subcap)
    if row is None:
        raise LedgerRefusal(f"{subcap} is not in this run's engagement set")
    if not str(actor or "").strip():
        raise LedgerRefusal("an absence records who declared it (--actor)")
    eids = [i for i in _split_ids(row.get("Evidence_IDs")) if i and i != C.NO_EVIDENCE]
    if eids:
        raise LedgerRefusal(
            f"{subcap} carries evidence ({', '.join(eids[:4])}); a cell with "
            f"evidence is SYNTHESISED, not declared absent")
    # THE RUN'S OWN REGISTER IS EVIDENCE (2026-09-03, owner: "limited
    # evidence is consolidated in most runs making the entire assessment
    # very evidence deficient"). A row above is refused when the CELL cites
    # evidence; this refuses the case that actually happens with sixteen
    # parallel lanes — a sibling registered a source that NAMES this cell,
    # the cell never cited it, and this lane is about to declare the cell
    # empty. The run bought that source. Consolidating it is not optional,
    # and `engine.brief reuse --subcap <cell>` is the read that finds it.
    named_by_register = []
    for eid, ev in sorted(wb.evidence_index().items()):
        named = [i.strip().split(":")[0]
                 for i in _split_ids(ev.get("SubCap_IDs"))]
        if subcap in named:
            named_by_register.append(eid)
    if named_by_register:
        raise LedgerRefusal(
            f"{subcap} cannot be declared empty: this run's evidence "
            f"register already names it — {', '.join(named_by_register[:5])}"
            + (f" (+{len(named_by_register) - 5} more)"
               if len(named_by_register) > 5 else "")
            + f". Read them (`engine.brief reuse --subcap {subcap}`) and "
            f"either synthesise the cell on them or re-register the row "
            f"against the cell it is really about. A declared absence over "
            f"the run's own evidence is the under-consolidation defect, not "
            f"an absence.")
    searches = wb.rows("Search_Log")
    vs = volley_status(wb, subcap, searches)
    problems = []
    if vs["missing"]:
        problems.append(
            f"volley(s) never fired for {subcap}: {', '.join(vs['missing'])}. "
            f"Every askable facet needs a logged `engine.cli search --subcap "
            f"{subcap} --facet <f>` before the cell may be declared empty — "
            f"'we looked and found nothing' has to be true of ALL five angles")
    if not vs["primary_fired"]:
        problems.append(
            f"the primary diagnostic question was never searched for {subcap}: "
            f"`engine.cli search --run <R> --subcap {subcap} --facet primary "
            f"--query '<the toolkit's DQ, bound to the entity>'` — the five "
            f"volleys answer the primary question, and without it they answer "
            f"nothing in particular")
    degraded = ""
    if not vs["enrichment_tools"]:
        # THE ONE REFUSAL A CONTAINER CAN BE UNABLE TO SATISFY. Every other
        # check here — the volleys, the primary, both ladder rungs, the proxy
        # log — a lane can satisfy with the built-in web tools. This one
        # cannot be satisfied when no enrichment connector is bound, and no
        # agent can bind one from inside a run. Refusing anyway does not buy
        # the enrichment; it produces a run that closes no cell, passes no
        # gate, and is re-dispatched until something stops it.
        #
        # So it is skippable, and ONLY on a measurement: the caller must ask
        # for the degraded path AND the run's own recorded baseline must
        # prove the connector was never there. A claim is not enough, an
        # absent baseline is not enough, and a bound connector the lane
        # simply did not use is not enough.
        binding = enrichment_binding(wb) if enrichment_unavailable else None
        if binding and binding["known"] and not binding["bound"]:
            degraded = binding["reason"]
        else:
            why = ""
            if enrichment_unavailable:
                why = (
                    " — and --enrichment-unavailable does not apply: "
                    + (binding["reason"] or
                       ("this run's connector baseline holds every required "
                        "family, so a connector WAS available and was not asked"
                        if binding and binding["known"] else
                        "this run has no recorded connector baseline, so "
                        "nothing here can prove one was unavailable. An "
                        "unverified claim is not a degradation")))
            problems.append(
                f"every search for {subcap} ran through {vs['tools'] or ['nothing']}; "
                f"an absence is declared only after an enrichment connector has "
                f"also been asked (one of {list(C.ENRICHMENT_TOOLS)}). Fire "
                f"`engine.cli search --run <R> --subcap {subcap} --facet <f> --tool "
                f"exa --query …` (or tavily / clay / drive) and retry — 'no "
                f"enrichment effort' is the owner's 2026-09-03 finding, and this "
                f"is the check that stops it" + why)
    assert_actor_scope(actor, "absence", [subcap])
    rep = Q.ladder_report(ladder or [], searches)
    rungs = set(rep["rungs"])
    owed = [r for r in ABSENCE_RUNGS_REQUIRED if r not in rungs]
    if owed:
        problems.append(
            f"the ladder establishes rungs {sorted(rungs) or 'none'}; "
            f"{', '.join(owed)} are owed on every absence (each rung = the "
            f"rung name plus the query that was FIRED and is in the Search_Log)")
    if rep["claimed_not_fired"]:
        problems.append(
            f"ladder rung(s) claim a query the Search_Log never saw: "
            f"{rep['claimed_not_fired'][:3]}")
    if len(str(proxy_log or "").strip()) < 40:
        proxy_class = C.proxy_classes().get(subcap, "")
        problems.append(
            f"the proxy log is {len(str(proxy_log or '').strip())} chars; say "
            f"which proxy class was hunted"
            + (f" (the template names {proxy_class!r} for this cell)" if proxy_class else "")
            + " and what came back instead (>= 40 chars)")
    if len(str(what_was_hunted or "").strip()) < 40:
        problems.append("--hunted: name what was looked for, where, and what "
                        "came back instead (>= 40 chars)")
    problems += _cell_own_hunt_problems(wb, subcap, str(what_was_hunted or ""))
    # THE DOSSIER FIELDS (QA audit D-12, 28-09-2026): an absence that still
    # permits an inference carries the inference AND the question that would
    # validate it — one without the other is a guess or a homework list; a
    # cell that cannot be determined from public sources says why, so the
    # triage can route it to the client conversation instead of to another
    # proxy round.
    inferable = str(inferable or "").strip() or None
    validation_question = str(validation_question or "").strip() or None
    not_determinable = str(not_determinable or "").strip() or None
    if bool(inferable) != bool(validation_question):
        problems.append("--inferable and --validation-question come together: "
                        "an inference states what it infers AND the question "
                        "a client answer would settle it with")
    if inferable and len(inferable) < 30:
        problems.append("--inferable: state the inference in >= 30 chars")
    if validation_question and (len(validation_question) < 15
                                or "?" not in validation_question):
        problems.append("--validation-question: a question (>= 15 chars, "
                        "ending in ?) the client can answer")
    if not_determinable and len(not_determinable) < 30:
        problems.append("--not-determinable: say why no public source can "
                        "settle this cell (>= 30 chars)")
    if problems:
        raise LedgerRefusal(f"{subcap}: absence refused — " + "; ".join(problems))
    hunted = str(what_was_hunted).strip()
    n = vs["searches"]
    claim = (f"No evidence located for this capability after {n} logged "
             f"searches across {len(vs['askable'])} volleys and a "
             f"{len(rungs)}-rung ladder ({', '.join(sorted(rungs))}); "
             f"{hunted}")
    dq = {f"DQ_{f.capitalize()}": f"NO_FINDING after {vs['fired'].get(f, 0)} logged "
                                  f"search(es): {hunted[:160]}"
          for f in C.FACETS}
    payload = {
        "Absence_Claimed": "YES", "Proxy_Log": str(proxy_log).strip(),
        "Negative_Ladder": json.dumps(ladder, separators=(",", ":")),
        "Dominant_Claim": claim, "Claim_Label": "HYPOTHESIS",
        "Proxy_Searched": "Yes", "Facet_Coverage": ", ".join(vs["askable"]),
        "What_We_Found": (f"Searched and not found: {hunted}. Volleys fired: "
                          + ", ".join(f"{f} x{vs['fired'].get(f, 0)}" for f in vs["askable"])
                          + f". Ladder rungs established: {', '.join(sorted(rungs))}."),
        "Triangulation": (f"{n} searches over {len(vs['tools']) or 1} tool(s) "
                          f"({', '.join(vs['tools']) or 'web_search'}) agree that no "
                          f"public artefact names this capability at the entity."
                          + (f" REDUCED RIGOUR: {degraded}. This absence rests "
                             f"on the built-in web tools alone; a firing with "
                             f"the connector attached may still find what this "
                             f"one could not ask for." if degraded else "")),
        "Ceiling_Reasoning": ("A documented absence supports no maturity ceiling; "
                              "the assessment scores the cell at the no-evidence "
                              "cap and discloses it as an Unknown."),
        "Why_It_Matters": ("An unevidenced cell is a discovery question for the "
                           "client conversation, not a verdict on the institution."),
        "DMA_Impact": ("Scored at the no-evidence cap and disclosed in Coverage as "
                       "an evidence gap; lifts when an internal artefact is supplied."),
        "Ceiling_Band": "", "Uncertainty": 1.0,
        **dq,
    }
    wb.set_scoring(subcap, payload)
    record_provenance(wb, subcap, "absence", actor,
                      f"{n} searches, rungs {sorted(rungs)}"
                      + (f"; REDUCED RIGOUR — {degraded}" if degraded else ""),
                      session=session)
    wb.recompute_coverage()
    out = {"subcap": subcap, "searches": n, "volleys": vs["fired"],
           "rungs": sorted(rungs), "tools": vs["tools"],
           "rigour": "REDUCED" if degraded else "FULL",
           "degraded_reason": degraded}
    dossier = gap_dossier_doc(
        wb, subcap, vs=vs, rep=rep, hunted=hunted,
        proxy_log=str(proxy_log).strip(), actor=actor,
        rigour=out["rigour"], inferable=inferable,
        validation_question=validation_question,
        not_determinable=not_determinable)
    out["dossier"] = write_gap_dossier(_run_of(wb, run), dossier)
    out["facets_status"] = dossier["facets_status"]
    out["proxy_candidates"] = dossier["proxy_candidates"]
    out["est_cost_usd"] = dossier["est_cost_usd"]
    return out


# ── the gap dossier: what a declared absence knows about itself ──────────
#
# QA audit D-12..D-16 (28-09-2026): the declared absence was the nearest
# thing to a gap dossier and carried 4 of its 11 fields. The dossier is the
# record the coordinator triages from (`engine.brief triage`) and the
# projector renders from (`engine.surface_export absence`): per-facet status
# COMPUTED from the Search_Log, the searches themselves, the ladder as
# established, the proxy class the catalogue names and the rungs not yet
# climbed, the internal artefact that would settle the cell, the inference
# (with its validation question) or the reason nothing public can decide
# it, and what one more round costs. Append-only, latest record per cell
# wins; `read_gap_dossiers` is the one reader.

GAP_DOSSIERS_NAME = "gap_dossiers.jsonl"
GAP_DOSSIER_SCHEMA = "gap_dossier_v1"
GAP_TRIAGE_NAME = "gap_triage.json"
GAP_TRIAGE_SCHEMA = "gap_triage_v1"
DISPOSITIONS = ("proxy", "internal_only", "cross_card_remap", "unknown")


def _est_round_cost() -> float | None:
    """What one more proxy round on one cell costs, from the measured
    baseline — or None when no baseline can be read (never a guess)."""
    try:
        from . import cost
        return float(cost.measured_baseline()["usd_per_subcap"])
    except Exception:                                # noqa: BLE001
        return None


def gap_dossier_doc(wb: RunWorkbook, subcap: str, *, vs: dict, rep: dict,
                    hunted: str, proxy_log: str, actor: str, rigour: str,
                    inferable: str | None, validation_question: str | None,
                    not_determinable: str | None) -> dict:
    md = wb.metadata()
    proxy_class = C.proxy_classes().get(subcap) or None
    settles = C.settling_artefacts().get(subcap) or None
    climbed = set(rep.get("rungs") or [])
    searches = [{"seq": r.get("Seq"), "facet": str(r.get("Facet") or ""),
                 "tool": str(r.get("Tool") or ""), "query": str(r.get("Query") or ""),
                 "hits": r.get("Hits"), "kept": r.get("Kept"),
                 "outcome": str(r.get("Outcome") or "")}
                for r in wb.rows("Search_Log")
                if str(r.get("SubCap_ID") or "").strip() == subcap]
    return {
        "schema_version": GAP_DOSSIER_SCHEMA,
        "run_id": md.get("run_id"), "subcap": subcap,
        "name": C.subcap_names().get(subcap),
        "category": subcap.split(".")[0],
        "declared_at": _utcnow(), "actor": actor, "rigour": rigour,
        "facets_status": {f: {"fired": vs["fired"].get(f, 0),
                              "status": "SEARCHED" if vs["fired"].get(f) else "NOT_RUN"}
                          for f in vs["askable"]},
        "primary_fired": vs["primary_fired"],
        "searches": searches,
        "tools": vs["tools"], "enrichment_tools": vs["enrichment_tools"],
        "ladder": {"rungs": sorted(climbed),
                   "claimed_not_fired": rep.get("claimed_not_fired") or []},
        "hunted": hunted, "proxy_log": proxy_log,
        "proxy_class": proxy_class,
        "proxy_candidates": ([proxy_class] if proxy_class else [])
                            + [r for r in Q.LADDER_RUNGS if r not in climbed],
        "settling_artefact": settles,
        "inferable": ({"claim": inferable, "validation_question": validation_question}
                      if inferable else None),
        "not_determinable": not_determinable,
        "est_cost_usd": _est_round_cost(),
    }


def write_gap_dossier(run, doc: dict) -> str | None:
    if run is None:
        return None
    p = run.qa_dir / GAP_DOSSIERS_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, separators=(",", ":"), default=str) + "\n")
    return str(p)


def read_gap_dossiers(run) -> dict[str, dict]:
    """subcap -> its latest dossier. A torn line is skipped, never fatal."""
    out: dict[str, dict] = {}
    if run is None:
        return out
    if not (run.qa_dir / GAP_DOSSIERS_NAME).is_file():
        return out
    for line in (run.qa_dir / GAP_DOSSIERS_NAME).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("subcap"):
            out[str(doc["subcap"])] = doc
    return out


def write_gap_triage(run, doc: dict) -> str:
    p = run.qa_dir / GAP_TRIAGE_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)
    return str(p)


def read_gap_triage(run) -> dict | None:
    """The coordinator's latest triage, or None when none was written."""
    if run is None:
        return None
    if not (run.qa_dir / GAP_TRIAGE_NAME).is_file():
        return None
    try:
        doc = json.loads((run.qa_dir / GAP_TRIAGE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def declared_absences(wb: RunWorkbook) -> set[str]:
    """Cells with a Provenance row Step == 'absence' — the record only
    `declare_absence` writes, after its volley, ladder and register checks."""
    return {str(r.get("SubCap_ID") or "").strip()
            for r in wb.rows("Provenance")
            if str(r.get("Step") or "").strip() == "absence"}


def is_declared_absent(row: dict, wb: RunWorkbook | None = None, *,
                       declared: set[str] | None = None) -> bool:
    """True only for a cell CLOSED BY `declare_absence`.

    Measured 2026-09-03: this read two cells — the flag and an empty
    Evidence_IDs — so anything that could set `Absence_Claimed` (a notebook
    consolidation, a synthesis record, a hand edit) produced a row the
    worklist, the handoff and the scorer all treated as a searched, declared
    absence, with zero Search_Log rows behind it. Now the flag is necessary
    and not sufficient: the cell must also carry the Provenance row that
    only `declare_absence` writes. Callers that hold the workbook pass it
    (or a precomputed `declared` set inside a loop); a bare `row` call keeps
    the two-cell answer for legacy readers and is the weaker check."""
    flagged = (str(row.get("Absence_Claimed") or "").strip().upper()
               in ("YES", "TRUE", "1")
               and not [i for i in _split_ids(row.get("Evidence_IDs"))
                        if i and i != C.NO_EVIDENCE])
    if not flagged:
        return False
    if declared is None and wb is not None:
        declared = declared_absences(wb)
    if declared is None:
        return True
    return str(row.get("SubCap_ID") or "").strip() in declared


def worklist(wb: RunWorkbook, category: str) -> dict:
    """closed / volleyed / in_volley / pending for one category.

    The three states AUD-0006 turned on, plus the one 2026-09-03 added:
    `in_volley` — some but not all askable volleys fired and no evidence yet.
    Before it, a cell with one shallow query looked exactly like an untouched
    one, and orient served the next untouched card instead of finishing the
    volley. A DECLARED absence (Absence_Claimed=YES, no evidence, all volleys
    fired) is CLOSED — searched and honestly empty."""
    closed, volleyed, in_volley, pending, declared = [], [], [], [], []
    searched_empty = []
    searches = wb.rows("Search_Log")
    declared_set = declared_absences(wb)
    for r in wb.scoring_rows():
        cell = str(r.get("SubCap_ID") or "").strip()
        if not cell.startswith(category + "."):
            continue
        has_ev = bool([i for i in _split_ids(r.get("Evidence_IDs"))
                       if i and i != C.NO_EVIDENCE])
        has_syn = bool(str(r.get("Dominant_Claim") or "").strip())
        if is_declared_absent(r, declared=declared_set):
            declared.append(cell)
            closed.append(cell)
        elif has_syn:
            closed.append(cell)
        elif has_ev:
            volleyed.append(cell)
        else:
            vs = volley_status(wb, cell, searches)
            if vs["searches"] and vs["missing"]:
                in_volley.append(cell)
            elif vs["searches"] and vs["complete"]:
                # every volley fired, nothing registered, not yet declared:
                # the card mode is DECLARE (or register what was found)
                searched_empty.append(cell)
            else:
                pending.append(cell)
    return {"category": category, "closed": sorted(closed),
            "declared_absent": sorted(declared),
            "volleyed": sorted(volleyed), "in_volley": sorted(in_volley),
            "searched_empty": sorted(searched_empty),
            "pending": sorted(pending)}


if __name__ == "__main__":  # a library, but it must answer --help
    import argparse as _ap
    _ap.ArgumentParser(
        prog=__file__.rsplit("/", 1)[-1],
        description=__doc__.split("\n")[0],
        epilog="A library module: import it, or run the modules that do have "
               "a command line (cli, orient, floors_gate, validator, handoff, "
               "reports, strip_working_area, patch_validator, watchdog).",
    ).parse_args()
