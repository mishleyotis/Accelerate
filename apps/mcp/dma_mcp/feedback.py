"""The reviewer feedback path — the Accept/Reject pair that wrote nothing and
could be read by nobody, now read and consumed.

Measured in production on 2026-08-08, before any of this:

    POST /v1/entities/baxter-credit-union-bcu/insights/IC-1/annotation
         ?actor=dma%40zennify.com  ->  403 unknown_actor
    SELECT count(*) FROM annotations                              ->  0
    grep -rn "FROM annotations" apps/ scripts/                    ->  no reader

Three separate gaps, and this module closes the third. Migration 0033 makes the
actor known (a `users` row from the committed allowlist) and grants the
connector SELECT; this module turns the verdicts into memory.

## What a verdict becomes

Every verdict — accept and reject alike — lands in `memory_reviewer_verdicts`,
one row per annotation, carrying the CARD'S OWN TEXT and its `r_layer` as they
were at the moment of the verdict. A re-promotion rewrites the card, and a
verdict against text that no longer exists says nothing about what was rejected.

A REJECT additionally becomes a finding, because a rejected claim is a defect in
what produced it. Its component is the synthesis skill, not the application: the
app rendered the card faithfully, the reasoning is what the reviewer refused.
Findings dedup per card claim, so the same card rejected by two reviewers is one
finding with two sightings.

An ACCEPT is not a defect and is not made into one. It lands as a verdict row —
which is what makes a reject rate measurable, and a reject finding's
`measurement` is exactly that rate — and, when the card already carries a
rejection finding, as a sighting on it recording that the same card was later
accepted. That is the cheapest possible signal that a refinement held.

## Re-running is free

`memory_reviewer_verdicts.annotation_id` is UNIQUE and the sighting carries
`source_ref = 'annotation:<id>'`. Ingest as often as you like; a verdict is
turned into a finding exactly once.
"""
from __future__ import annotations

import json

from . import memory as mem

#: The synthesis skill is what wrote the claim, so it is what a reviewer's
#: rejection is about. Overridable per call for a run produced by something
#: else; never guessed from the payload.
PRODUCER_COMPONENT = "skill:dma-surface-production"

REJECT_CLASS = "REVIEWER_REJECTED_INSIGHT"

#: The card's own severity is the producer's claim about consequence, so it is
#: what a rejection of that claim inherits. `info` rejects are still MINOR, not
#: INFO: a reviewer taking the trouble to reject is itself a signal.
_SEVERITY = {"critical": "BLOCKER", "high": "MAJOR", "opportunity": "MINOR",
             "info": "MINOR"}


def _body(raw):
    """`annotations.body` is TEXT holding the JSON the API wrote. A body that
    will not parse is not silently treated as empty (that is its own defect
    class) — it is returned as an unparsed marker so ingestion can report it."""
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(raw or "")
        return out if isinstance(out, dict) else {"_unparsed": str(raw)[:400]}
    except (TypeError, ValueError):
        return {"_unparsed": str(raw)[:400]}


def _card_text(card: dict) -> str:
    """The claim as the reviewer read it, in the card's own order."""
    parts = [("What", card.get("what_text")), ("Why", card.get("why_text")),
             ("So what", card.get("so_what_text")),
             ("Alternative explanation", card.get("alternative_explanation")),
             ("Severity rationale", card.get("severity_rationale")),
             ("Validation question", card.get("validation_question"))]
    return "\n".join(f"{label}: {value}" for label, value in parts if value)


def list_reviewer_feedback(conn, display_id=None, ic_id=None, run_id=None,
                           limit: int = 50) -> dict:
    """The READ PATH. Reviewer verdicts straight from `annotations`, joined to
    the actor and the entity — the query nothing in this repository performed
    until now.

    Reading annotations does not touch invariant 2: that invariant constrains
    the API's WRITES. A SELECT adds no content and gives no component a write
    it did not have.
    """
    cur = conn.cursor()
    limit = max(1, min(int(limit or 50), 500))
    where, params = ["a.anchor_kind = 'insight_card'"], []
    if display_id:
        where.append("e.display_id = %s")
        params.append(display_id)
    if ic_id:
        where.append("a.anchor_id = %s")
        params.append(ic_id)
    if run_id:
        where.append("a.run_id = %s")
        params.append(run_id)
    cur.execute(
        f"""SELECT a.id, a.anchor_id, a.body, a.created_at, u.email,
                   e.display_id, a.run_id, a.entity_id,
                   v.id IS NOT NULL AS ingested, v.finding_id
              FROM annotations a
              LEFT JOIN users u ON u.id = a.user_id
              LEFT JOIN entities e ON e.id = a.entity_id
              LEFT JOIN memory_reviewer_verdicts v ON v.annotation_id = a.id
             WHERE {' AND '.join(where)}
             ORDER BY a.created_at DESC, a.id DESC
             LIMIT %s""", [*params, limit])
    out = []
    for (aid, anchor, body, created, email, disp, rid, eid, ingested,
         fid) in cur.fetchall():
        parsed = _body(body)
        out.append({
            "annotation_id": aid, "ic_id": anchor,
            "action": parsed.get("action"), "note": parsed.get("note"),
            "unparsed_body": parsed.get("_unparsed"),
            "actor": email, "display_id": disp,
            "run_id": str(rid) if rid else None,
            "entity_id": str(eid) if eid else None,
            "created_at": created.isoformat() if created else None,
            "ingested": bool(ingested), "finding_id": fid,
        })
    return {"count": len(out), "verdicts": out, "errors": []}


def ingest_reviewer_feedback(conn, limit: int = 200, encoder=None,
                             producer_component: str = PRODUCER_COMPONENT
                             ) -> dict:
    """Turn every un-ingested verdict into memory. Idempotent; safe to run on
    a schedule and again by hand five minutes later."""
    cur = conn.cursor()
    limit = max(1, min(int(limit or 200), 1000))

    cur.execute(
        """SELECT a.id, a.anchor_id, a.body, a.created_at, a.run_id,
                  a.entity_id, u.email, e.display_id
             FROM annotations a
             LEFT JOIN users u ON u.id = a.user_id
             LEFT JOIN entities e ON e.id = a.entity_id
             LEFT JOIN memory_reviewer_verdicts v ON v.annotation_id = a.id
            WHERE a.anchor_kind = 'insight_card' AND v.id IS NULL
            ORDER BY a.created_at, a.id
            LIMIT %s""", (limit,))
    pending = cur.fetchall()

    ingested = skipped = 0
    findings, problems = [], []

    for (aid, ic_id, body, created, run_id, entity_id, email,
         display_id) in pending:
        parsed = _body(body)
        action = str(parsed.get("action") or "").upper()
        if action not in ("ACCEPT", "REJECT"):
            skipped += 1
            problems.append({
                "annotation_id": aid, "reason": "unreadable_action",
                "detail": f"body carried {parsed.get('_unparsed') or parsed!r}; "
                          "no ACCEPT/REJECT to consume. Left un-ingested so it "
                          "is not silently counted as nothing."})
            continue
        note = parsed.get("note")

        # The card as the reviewer read it. A missing card is not fatal: the
        # verdict still lands, with the text columns NULL and the absence
        # stated, because an anchor that no longer resolves is itself worth
        # keeping.
        cur.execute(
            """SELECT title, what_text, why_text, so_what_text,
                      alternative_explanation, severity, severity_rationale,
                      validation_question, claim_label::text, linked_subcap_id,
                      r_layer
                 FROM insight_cards
                WHERE run_id = %s AND ic_id = %s
                LIMIT 1""", (run_id, ic_id))
        crow = cur.fetchone()
        if crow is None:
            card = {}
            problems.append({
                "annotation_id": aid, "reason": "card_not_found",
                "detail": f"{ic_id} is not on run {run_id}; the verdict is "
                          "recorded with no card text"})
        else:
            keys = ("title", "what_text", "why_text", "so_what_text",
                    "alternative_explanation", "severity",
                    "severity_rationale", "validation_question",
                    "claim_label", "linked_subcap_id", "r_layer")
            card = dict(zip(keys, crow))

        finding_id = None
        if action == "REJECT":
            finding_id = _reject_finding(
                conn, cur, aid=aid, ic_id=ic_id, card=card, note=note,
                email=email, display_id=display_id, run_id=run_id,
                entity_id=entity_id, encoder=encoder,
                component=producer_component)
            if finding_id is None:
                skipped += 1
                problems.append({
                    "annotation_id": aid, "reason": "finding_refused",
                    "detail": "record_finding refused this rejection; the "
                              "verdict is left un-ingested rather than stored "
                              "without the finding it is supposed to raise"})
                continue
            findings.append({"annotation_id": aid, "ic_id": ic_id,
                             "finding_id": finding_id})
        else:
            finding_id = _accept_sighting(
                cur, ic_id=ic_id, display_id=display_id, aid=aid,
                email=email, note=note, run_id=run_id, entity_id=entity_id)

        r_layer = card.get("r_layer")
        cur.execute(
            """INSERT INTO memory_reviewer_verdicts
                 (annotation_id, action, note, actor_email, entity_display_id,
                  entity_id, run_id, ic_id, card_title, card_text,
                  card_severity, card_claim_label, card_subcap_id, r_layer,
                  finding_id, verdict_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (annotation_id) DO NOTHING""",
            (aid, action, note, email or "(unknown)", display_id, entity_id,
             run_id, ic_id, card.get("title"), _card_text(card) or None,
             card.get("severity"), card.get("claim_label"),
             card.get("linked_subcap_id"),
             json.dumps(r_layer) if isinstance(r_layer, (dict, list))
             else r_layer,
             finding_id, created))
        ingested += 1

    conn.commit()

    cur.execute("""SELECT action, count(*) FROM memory_reviewer_verdicts
                    GROUP BY action ORDER BY action""")
    tally = {a: n for a, n in cur.fetchall()}
    total = sum(tally.values()) or 0
    return {
        "ingested": ingested, "skipped": skipped,
        "pending_seen": len(pending),
        "findings_raised": findings,
        "problems": problems,
        "verdict_tally": tally,
        "reject_rate": (round(tally.get("REJECT", 0) / total, 4)
                        if total else None),
        "errors": [],
    }


def _reject_finding(conn, cur, *, aid, ic_id, card, note, email, display_id,
                    run_id, entity_id, encoder, component) -> str | None:
    """A rejection is a defect in what produced the claim. The finding carries
    the card's text and its r_layer, so a reader can see WHICH reasoning was
    refused rather than only that something was."""
    # The measurement is the rate, not the anecdote: one reject out of one
    # verdict and one out of forty are different facts about the producer.
    cur.execute(
        """SELECT count(*) FILTER (WHERE action = 'REJECT'), count(*)
             FROM memory_reviewer_verdicts WHERE run_id = %s""", (run_id,))
    prior_rejects, prior_total = cur.fetchone()
    rejects, total = prior_rejects + 1, prior_total + 1

    r_layer = card.get("r_layer")
    if isinstance(r_layer, str):
        try:
            r_layer = json.loads(r_layer)
        except ValueError:
            pass
    reasoning = ""
    if isinstance(r_layer, dict):
        reasoning = "\n".join(
            f"{k}: {v}" for k, v in r_layer.items()
            if isinstance(v, str) and v.strip())

    title = card.get("title") or ic_id
    observed = "\n\n".join(filter(None, [
        f"Insight card {ic_id} on {display_id or '(unknown entity)'}: {title}",
        _card_text(card),
        f"Recorded reasoning (r_layer):\n{reasoning}" if reasoning else None,
        f"Reviewer note: {note}" if note else
        "Reviewer left no note — the verdict says only that this reasoning "
        "was refused.",
    ]))
    measurement = (
        f"Reviewer {email or '(unknown)'} pressed Reject on insight card "
        f"{ic_id} of {display_id or '(unknown entity)'} (run {run_id}), "
        f"annotation id {aid}, via "
        f"POST /v1/entities/{display_id}/insights/{ic_id}/annotation. "
        f"This run now stands at {rejects} rejected of {total} annotated "
        f"cards.")
    out = mem.record_finding(conn, {
        "title": f"Reviewer rejected: {title}",
        "observed": observed,
        "measurement": measurement,
        "measured_value": f"{rejects}/{total} rejected on this run",
        "expected": "an insight card whose recorded reasoning an analyst will "
                    "put in front of a client",
        "component": component,
        "surface": "D1 insights",
        "defect_class": REJECT_CLASS,
        "severity": _SEVERITY.get(str(card.get("severity") or "").lower(),
                                  "MINOR"),
        "raised_by_kind": "REVIEWER",
        "raised_by": email or "(unknown reviewer)",
        "run_id": run_id, "entity_id": entity_id, "annotation_id": aid,
        "source_ref": f"annotation:{aid}",
        "session_ref": f"web:{display_id}",
        "note": note,
        "fix_hint": "Read the r_layer above, not just the headline: the "
                    "reviewer refused a chain of reasoning. Refine the "
                    "producing skill's prompt for that claim shape, then "
                    "record the refinement against this finding.",
        # The card's identity is the defect's identity: the same card rejected
        # twice is one finding with two sightings, and a different card with
        # the same title on another entity is a different finding.
        "dedup_key": f"reviewer-reject|{display_id}|{ic_id}|{title}",
    }, encoder=encoder)
    if out.get("errors"):
        return None
    return out["finding_id"]


def _accept_sighting(cur, *, ic_id, display_id, aid, email, note, run_id,
                     entity_id):
    """An accept on a card that was previously rejected is the cheapest signal
    available that something was fixed. It is recorded against that finding —
    as a sighting with a note, never as a resolution: only a refinement may
    close a finding (0034's CHECK), and an accept names no change."""
    cur.execute(
        """SELECT finding_id FROM memory_reviewer_verdicts
            WHERE entity_display_id IS NOT DISTINCT FROM %s AND ic_id = %s
              AND action = 'REJECT' AND finding_id IS NOT NULL
            ORDER BY verdict_at DESC LIMIT 1""", (display_id, ic_id))
    row = cur.fetchone()
    if row is None:
        return None
    finding_id = row[0]
    mem.add_sighting(
        cur, finding_id, reported_by_kind="REVIEWER",
        reported_by=email or "(unknown reviewer)",
        measurement=(f"Reviewer {email or '(unknown)'} later ACCEPTED insight "
                     f"card {ic_id} of {display_id} (annotation {aid}), which "
                     "was previously rejected."),
        measured_value="ACCEPT", note=note,
        session_ref=f"web:{display_id}", source_ref=f"annotation:{aid}",
        run_id=run_id, entity_id=entity_id, annotation_id=aid)
    return finding_id
