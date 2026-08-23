"""promote_run (stage 2.5) — all six pages, one transaction, all or nothing.

The run row is taken FOR UPDATE (one promote per run at a time); the 34
section writers then run in REGISTRY ORDER — the ordering is load-
bearing, unordered acquisition deadlocks under concurrent promotes of
different runs. Each writer deletes its section's rows for this run and
rewrites them from the live PASSING submission, so re-promotion is
idempotent and fixing one page re-promotes six pages from five retained
staged rows plus one new one. Any writer failure rolls back everything.

Writers are data, not code: writer_spec.json (extracted from the 0008
DDL against the contract registry, adversarially verified) maps every
table column to its payload source. A column the spec cannot source is
NULL; a column the DDL generates is never written.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import ledger
from .contracts import PAGES, SERVING_TABLES
from .validation import validate_pass1

_SPEC_PATH = Path(__file__).with_name("writer_spec.json")
_SPEC = None

# THE ALERT CEILING WAS REMOVED by the build owner on 2026-08-16, and the
# COUNT deliberately was not.
#
# It was set at 15 on 2026-08-14 after a run promoted carrying 98 open alerts
# that nothing had read. Two clients later the number looks like a property of
# the CORPUS rather than of any run: measured 2026-08-16, a second client owed
# 621 alerts against the same ceiling — 621 of 705 scored cells flagged thin,
# 472 with no linked evidence — because that assessment ran in PUBLIC evidence
# mode, whose own methodology says that is why two thirds of subcapabilities
# come back Unknown. An alert per unknown cell counts the evidence mode, not
# the work. A ceiling of 15 against a floor of 621 is not a queue-length rule;
# it is a rule that refuses the corpus, and its only reachable escape is a
# producer deleting alerts to clear it — the one repair the refusal text
# explicitly forbade.
#
# What stays is the measurement. The original defect was never the size of the
# queue; it was that NOBODY ANYWHERE READ THE COUNT — not at submit, not at
# promote — so 98 reached a dashboard unremarked. Deleting the counter along
# with the ceiling would restore exactly that. `promote_run` now reports
# `open_alerts` on success: nothing is blocked, and nothing is unremarked.


def _open_alert_count(live: dict) -> int:
    """How many alerts this promote is about to put in the queue.

    Counted from the payload that is about to be written rather than from a
    stored total (invariant 8): every alert row promotion writes starts open,
    so the length of the array IS the queue the AE will meet. A payload with
    no alerts section counts zero, which is the honest reading — a run that
    raised none is not a run that hid them.
    """
    hm = (live.get("heatmap") or {}).get("payload") or {}
    alerts = ((hm.get("alerts") or {}).get("alerts")
              if isinstance(hm.get("alerts"), dict) else None)
    return len(alerts) if isinstance(alerts, list) else 0


def writer_registry() -> list:
    """The ordered writer list. Order = contracts.SERVING_TABLES order,
    which is the registry's canonical page/section order — stable, and
    tested to stay so."""
    global _SPEC
    if _SPEC is None:
        by_key = {}
        for page_spec in json.loads(_SPEC_PATH.read_text())["specs"]:
            for w in page_spec["writers"]:
                # the writer carries its own page so a single writer is
                # self-describing wherever it is handed on
                w["page"] = page_spec["page"]
                by_key[(page_spec["page"], w["section"])] = w
        _SPEC = [((page, section), by_key[(page, section)])
                 for (page, section) in SERVING_TABLES
                 if (page, section) in by_key]
        missing = [k for k in SERVING_TABLES if k not in by_key]
        if missing:
            raise RuntimeError(f"writer_spec.json lacks writers for {missing}")
    return _SPEC


def _walk_path(node, path: str):
    """Dotted-path get: 'platforms.0.gaps' walks dicts and lists; any miss
    is None (computed or null, never a KeyError at promote time)."""
    for seg in path.split("."):
        if isinstance(node, dict):
            node = node.get(seg)
        elif isinstance(node, list) and seg.isdigit() and int(seg) < len(node):
            node = node[int(seg)]
        else:
            return None
    return node


from .dates import resolve as resolve_date

_DATE_FIELDS = None


def _date_paths() -> dict:
    """{(page, section): {field_leaf, …}} for DATE-promoted fields."""
    global _DATE_FIELDS
    if _DATE_FIELDS is None:
        _DATE_FIELDS = {}
        try:
            raw = json.loads(_SPEC_PATH.with_name("enum_fields.json").read_text())
            for key, paths in raw.get("date_fields", {}).items():
                page, _, section = key.partition(".")
                _DATE_FIELDS[(page, section)] = {p.split(".")[-1] for p in paths}
        except Exception:
            pass
    return _DATE_FIELDS


def _value(source, ctx, section, item):
    kind, _, field = source.partition(":")
    if kind == "skip":
        return ...                     # sentinel: column never written
    if kind == "sys":
        return ctx[field]
    if kind == "env" or kind == "section":
        return _walk_path(section, field) if isinstance(section, dict) else None
    if kind == "item":
        return _walk_path(item, field) if isinstance(item, dict) else None
    if kind == "const":
        return field                   # a lifecycle initial, not payload data
    raise ValueError(f"unknown source {source!r}")


def _expand_h4_maps(section_payload: dict) -> list:
    """heatmap.workbook_scores: the contract's two required fields are
    OBJECT MAPS (pillars {P1..: {...}}, categories {PxCy: {...}}), not a
    list — fan both into rows. Order is meaning: pillars first, then
    categories, each in key order."""
    rows = []
    for pid, entry in (section_payload.get("pillars") or {}).items():
        if isinstance(entry, dict):
            rows.append({"pillar_id": pid, "category_id": None, **entry})
    for cid, entry in (section_payload.get("categories") or {}).items():
        if isinstance(entry, dict):
            rows.append({"pillar_id": cid.split("C")[0], "category_id": cid,
                         **entry})
    return rows


def _promoted_sections(live):
    """(page, section) for every section a promoted payload carries.

    Read from the submissions this promote is writing, so it names what
    happened rather than what a producer said would happen.
    """
    for page, sub in live.items():
        payload = sub.get("payload") or {}
        if isinstance(payload, dict):
            for name in payload:
                if not str(name).startswith("_"):
                    yield (page, name)


def promote_run(conn, run_id) -> dict:
    registry = writer_registry()
    cur = conn.cursor()
    try:
        cur.execute("""SELECT entity_id FROM runs WHERE id = %s FOR UPDATE""",
                    (run_id,))
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return {"promoted": False, "error": "unknown_run"}
        entity_id = row[0]

        cur.execute(
            """SELECT enum_label(page), enum_label(status), id, payload,
                      producer_version, enum_label(provenance)
                 FROM submissions
                WHERE run_id = %s AND superseded_at IS NULL""", (run_id,))
        live = {r[0]: {"status": r[1], "id": r[2], "payload": r[3],
                       "producer_version": r[4], "provenance": r[5]}
                for r in cur.fetchall()}
        missing = [p for p in PAGES if p not in live]
        unpassed = [p for p, s in live.items() if s["status"] != "PASS"]
        if missing or unpassed:
            conn.rollback()
            return {"promoted": False, "error": "incomplete_run",
                    "missing_pages": sorted(missing),
                    "unpassed_pages": sorted(unpassed),
                    "hint": "promote requires a PASS row for every page"}

        # ── the alert queue: counted, never a refusal ──────────────────
        #
        # Measured, not gated. The ceiling this replaced is explained at the
        # top of the module; the short version is that the count turned out to
        # measure the assessment's EVIDENCE MODE rather than the run's quality,
        # so refusing on it refused the corpus. Nothing below rolls back.
        alerts = _open_alert_count(live)

        # A retained PASS is a DATED OBSERVATION, not a current state.
        #
        # Validation runs at submit. Retention is correct and load-bearing —
        # invariant 3 exists so that fixing one page does not cost five
        # re-syntheses — but it means a page keeps a verdict issued by the
        # gate set of the day it was submitted, and every later promote
        # carries it forward unexamined. So a gate added today protects only
        # pages submitted after today.
        #
        # Measured on the reference client: its context page holds a PASS
        # from before CG-09 learned `arc_shape` and CG-10 learned the
        # issue register's dates, and against today's gates the same stored
        # payload returns seven blocking reasons. It is live, and its row
        # says PASS.
        #
        # Re-validated here, over the payload promote is about to write —
        # no extra I/O, it is already in hand.
        #
        # THIS USED TO DISCLOSE AND PROMOTE ANYWAY, and the argument for that
        # was written here: a gate that tightened after a page was authored is
        # a reason to look, not a reason to strand five other pages that are
        # fine, and refusing makes every gate change retroactively
        # un-promotable, which is how a build stops adding gates.
        #
        # Measured 2026-08-16, which is what retired it. A run was re-promoted
        # from retained rows after an unrelated gate was removed. Promotion
        # carried forward payloads dated a week earlier, none of the owner's
        # reported issues having been re-synthesised, and disclosed EIGHT
        # CG-15 reasons at severity "block" — then promoted. The content
        # reached the client surface. The disclosure went into a promote
        # result that is read once, by whoever typed the call, and it was
        # under-weighted exactly as a passing-looking result invites.
        #
        # "Disclosed" is only a control if something downstream refuses on it.
        # Nothing did. So a blocking reason now blocks, and the "strand five
        # pages" objection is answered by retention itself — the repair is to
        # resubmit the ONE page named and promote again, which is the workflow
        # invariant 3 exists for. It costs one re-synthesis, not six.
        #
        # SG is the documented exception and keeps its old behaviour: the
        # charter says a failing safeguard discloses and still promotes. A
        # failing CG, AG or ET is a correctness reason and does not.
        stale_verdicts = {}
        refusing = {}
        families: dict = {}          # page -> {gate_id: count}, complete
        totals: dict = {}            # page -> how many blocking reasons
        for page, sub in sorted(live.items()):
            try:
                now = validate_pass1(page, sub["payload"] or {})
            except Exception as exc:      # noqa: BLE001
                # A re-validation that CRASHED established nothing. It must
                # not read as a clean page — that is the
                # CHECK_NEVER_RAN_READS_AS_UNKNOWN shape — so it refuses.
                reasons = [{"gate_id": "revalidation", "severity": "block",
                            "message": f"re-validation raised "
                                       f"{type(exc).__name__}; this page's "
                                       "current state is unknown, which is "
                                       "not the same as clean"}]
                stale_verdicts[page] = reasons
                refusing[page] = reasons
                continue
            if now:
                stale_verdicts[page] = now[:8]
                blocking = [r for r in now
                            if r.get("severity") == "block"
                            and not str(r.get("gate_id", "")).startswith("SG")]
                if blocking:
                    # TRUNCATED FOR READING, COUNTED IN FULL. `blocking[:8]`
                    # alone made the repair non-convergent: measured
                    # 2026-08-23 (MEM-0181/MEM-0188), one run carried 54
                    # blocking reasons across 8 gate families and the repair
                    # was scoped against the 3 families the first 8 happened
                    # to name. The producer fixed those, resubmitted, and met
                    # the rest. The count and the family spread travel with
                    # the sample so one pass can cover the page.
                    refusing[page] = blocking[:8]
                    families[page] = dict(
                        Counter(str(r.get("gate_id", "?")) for r in blocking)
                        .most_common())
                    totals[page] = len(blocking)
        if refusing:
            conn.rollback()
            return {
                "promoted": False, "error": "retained_pages_fail_current_gates",
                "pages": sorted(refusing),
                "reasons": refusing,
                # THE THREE FIELDS THAT MAKE THIS DIAGNOSABLE. `reasons` is a
                # sample; these say how big the job really is and which gates
                # to dispatch against, so nobody has to infer scope from a
                # truncated list.
                "blocking_total": totals,
                "blocking_by_gate": families,
                "truncated": {p: totals[p] > len(refusing[p]) for p in refusing},
                "hint": (
                    "These pages hold a PASS issued by an earlier gate set and "
                    "do not pass today's. A retained verdict is a DATED "
                    "observation, not a current state, and promoting on one "
                    "puts content on a client surface that this connector "
                    "would refuse if it were submitted now. Resubmit each page "
                    "named — only those; the others' retained rows are still "
                    "good and cost nothing — then promote again. Safeguard "
                    "(SG) reasons are excluded from this refusal and still "
                    "disclose-and-promote, per the charter."),
            }

        stats = {p: {"sections": 0, "rows_written": 0} for p in PAGES}
        for (page, section), writer in registry:
            sub = live[page]
            ctx = {"run_id": run_id, "entity_id": entity_id,
                   "producer_version": sub["producer_version"],
                   "provenance": sub["provenance"]}
            payload = sub["payload"] or {}
            section_payload = payload.get(section)
            n = _write_section(cur, writer, ctx, section_payload)
            stats[page]["sections"] += 1
            stats[page]["rows_written"] += n

        # one active promoted run per entity: demote the previous one
        cur.execute("""UPDATE runs SET is_active = FALSE, status = 'SUPERSEDED'
                        WHERE entity_id = %s AND is_active AND id <> %s""",
                    (entity_id, run_id))
        # A successful promote is the ONLY way back from withdrawal (0042).
        # Clearing the three columns here rather than in a restore tool is
        # deliberate: a run was withdrawn because what it served was wrong,
        # so the way onto a client's screen is passing the gates again, not
        # a lever that un-withdraws without fixing anything.
        cur.execute("""UPDATE runs SET status = 'PROMOTED', is_active = TRUE,
                                       promoted_at = now(),
                                       withdrawn_at = NULL,
                                       withdrawn_reason = NULL,
                                       withdrawn_by = NULL
                        WHERE id = %s""", (run_id,))
        # stamp by the EXACT ids read at the top of the transaction — a
        # resubmission racing this promote must never get stamped for
        # content that was not written
        cur.execute("""UPDATE submissions SET promoted_at = now()
                        WHERE id = ANY(%s)""",
                    ([s["id"] for s in live.values()],))
        # ── the enrichment ledger's other half ─────────────────────────
        #
        # A promote is the only moment the system knows a facet reached a
        # reader, so it is the only honest place to record it. Driven off the
        # sections this promote ACTUALLY wrote rather than off a producer
        # declaring anything, because the declaration is the thing that goes
        # missing — three rounds of "the work was done but it is not showing"
        # were all a promotion nobody recorded against an enrichment nobody
        # versioned.
        #
        # Inside the transaction: a promote that rolls back must not leave
        # the ledger claiming its facets are live.
        promoted_facets, ledger_error = [], None
        try:
            promoted_facets = ledger.record_promotion_for_sections(
                cur, entity_id,
                list(_promoted_sections(live)),
                run_id=run_id)
        except Exception as e:            # noqa: BLE001 — reported, not silent
            # The ledger is a safeguard, not the product. A promote that
            # succeeded must not be reported as failed because its bookkeeping
            # did — but it must not be reported as clean either.
            ledger_error = str(e)[:200]
        conn.commit()
        # after commit: the directory's materialised view sees the new
        # promotion. A refresh failure never un-promotes — it is reported.
        refresh_error = None
        try:
            cur.execute("SELECT refresh_serving_directory()")
            conn.commit()
        except Exception as e:            # noqa: BLE001 — reported, not silent
            conn.rollback()
            refresh_error = str(e)[:200]
        cur.execute("SELECT promoted_at FROM runs WHERE id = %s", (run_id,))
        out = {"promoted": True,
               "promoted_at": cur.fetchone()[0].isoformat(),
               # The queue this promote just put in front of an AE. Reported
               # on SUCCESS because that is the only path left: with the
               # ceiling gone, a number nobody returns is a number nobody
               # reads, which is the exact state that let 98 alerts reach a
               # dashboard unremarked in the first place.
               "open_alerts": alerts,
               "stats": stats}
        # The drift flag, DISCLOSED and never blocking. A promote carrying
        # five of seven facets forward is better than no promote; refusing it
        # would strand the five. The refusal lives on "is this client done?",
        # which is a claim about the whole client rather than one transaction.
        try:
            out["enrichment"] = ledger.summary(ledger.drift(cur, entity_id))
            out["enrichment"]["promoted_now"] = promoted_facets
        except Exception as e:            # noqa: BLE001 — reported, not silent
            out["enrichment_error"] = str(e)[:200]
        if ledger_error:
            out["enrichment_ledger_error"] = ledger_error
        if refresh_error:
            out["directory_refresh_error"] = refresh_error
        if stale_verdicts:
            out["stale_verdicts"] = stale_verdicts
            out["stale_verdicts_note"] = (
                "These pages promoted from a RETAINED submission whose PASS "
                "predates gates that now refuse it. Their content is live and "
                "nothing here blocked it — validation runs at submit and a "
                "retained verdict is a dated observation, not a current "
                "state. Resubmit each page named to clear them; a page not "
                "listed is clean against today's gates.")
        return out
    except Exception:
        conn.rollback()
        raise


# table -> {column: initial value}. Lowercase to match alert_action_t
# (acknowledged · assigned · waived · resolved · reopened), which is the
# vocabulary the actions that move this column are enumerated in.
LIFECYCLE_INITIAL = {"heatmap_alerts": {"status": "open"}}


def _write_section(cur, writer, ctx, section_payload) -> int:
    """Delete-then-rewrite one section's rows from the live submission.
    promoted_at columns take SQL now() so every row of the promotion
    carries one transaction instant."""
    table = writer["table"]
    if writer["grain"] == "none":
        return 0
    cur.execute(f"DELETE FROM {table} WHERE run_id = %s", (ctx["run_id"],))
    if section_payload is None:
        return 0
    if writer.get("expand") == "h4_maps":
        rows = _expand_h4_maps(section_payload)
    elif writer["grain"] == "item":
        items = _walk_path(section_payload, writer["item_field"]) or []
        rows = [i for i in items if isinstance(i, dict)]
    else:
        rows = [None]

    # A section that PROMOTED WITH AN EMPTY COLLECTION must still leave a row.
    #
    # `assemble` returns None when a section has no serving rows, and pages.py
    # then serves {"kind": "section_not_promoted", "reason": "no serving row
    # for this run"}. So a producer who worked a section, found nothing it
    # could publish, and wrote the reason WHY — the cohort floor of five runs
    # for heatmap.cohort_patterns, the pillar grain the workbook does not
    # resolve for heatmap.workbook_scores, each with its sources searched and
    # its closure condition — had that reason discarded right here, and the
    # reader was handed the plumbing sentence in its place. Promoted with
    # nothing in it and never promoted are DIFFERENT FACTS and must not serve
    # the same document (TRD §08).
    #
    # The envelope-only row carries the envelope columns and nulls every item
    # column, which is what H9's value-chain section has always done by
    # design. `assemble` skips a row with no item content, so the collection
    # still serves empty; the envelope, and with it `empty_state`, survives.
    #
    # It carries NO LIFECYCLE STATE either. `serving_directory.open_alerts`
    # counts `heatmap_alerts` rows whose status is 'open', and heatmap.alerts
    # is item-grain: an envelope-only alert row stamped with the lifecycle
    # initial would put one open alert on the directory of every run whose
    # queue promoted empty — an alert naming no cell, on a run that raised
    # none. Exactly the kind of asserted count this change exists to remove.
    envelope_only = not rows and isinstance(section_payload, dict)
    if envelope_only:
        rows = [None]

    cols, exprs, per_row_sources = [], [], []
    # A queue-lifecycle column the contract does not name, but the queue is
    # useless without: heatmap_alerts.status has no DDL default, so an alert
    # promoted with a NULL status is invisible to the alert dashboard and to
    # serving_directory.open_alerts. The lifecycle itself belongs to
    # alert_actions; promote only sets the first state.
    for col, initial in LIFECYCLE_INITIAL.get(table, {}).items():
        cols.append(col)
        exprs.append("%s")
        per_row_sources.append({"column": col, "source": f"const:{initial}",
                                "lifecycle": True})
    for c in writer["columns"]:
        if c["source"].startswith("skip:"):
            continue
        cols.append(c["column"])
        if c["source"] == "sys:promoted_at":
            exprs.append("now()")
        else:
            exprs.append("%s")
            per_row_sources.append(c)
    date_leaves = _date_paths().get((writer["page"], writer["section"]), set())
    written = 0
    for item in rows:
        values = []
        for c in per_row_sources:
            v = _value(c["source"], ctx, section_payload, item)
            if v is ...:
                v = None
            # An envelope-only row is a carrier for the section's declared
            # absence, not a queue entry: it takes no lifecycle state, so it
            # cannot be counted as an open alert on a run that raised none.
            if envelope_only and c.get("lifecycle"):
                v = None
            if v is not None and c["source"].split(":")[-1].split(".")[-1] in date_leaves:
                # Month and quarter precision are legitimate in the payload
                # (the prompts ask for them) and the column is a DATE; the
                # same resolver the submit gate used converts them, so a
                # value that reaches here cannot abort the transaction.
                resolved = resolve_date(v)
                v = None if resolved is False else resolved
            if v is not None and (c.get("jsonb") or isinstance(v, dict)):
                # dicts serialise for JSONB — and defensively for TEXT
                # columns whose contract value is an object (lossless,
                # never a pg8000 type error at promote time)
                v = json.dumps(v)
            values.append(v)
        cur.execute(
            f'INSERT INTO {table} ({",".join(cols)}) VALUES ({",".join(exprs)})',
            values)
        written += 1
    return written
