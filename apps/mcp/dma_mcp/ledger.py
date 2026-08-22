"""The enrichment ledger: what was enriched, and whether a reader can see it.

The pattern this closes, reported three rounds running: "the work was done
but it is not showing". An enrichment ran — in a producer session, in a
scheduled scan, under a different account — and the surface a reader opens
did not have it. Nothing in the system held both halves of that sentence, so
nothing could notice the gap.

Two writes and one question:

    record_enrichment(...)   a facet was enriched. Allocates the next version.
    record_promotion(...)    a facet reached the serving tier at that version.
    drift(...)               per facet: current · enriched_not_promoted ·
                             never_enriched.

The version is allocated server-side by `next_enrichment_version`, so a
caller cannot mint one that collides or one that goes backwards, and two
producers enriching the same facet concurrently order rather than collide.

WHERE THE REFUSAL LIVES. Not at promote: a promote carrying five of seven
facets forward is better than no promote, and refusing it strands the five.
`blocking(...)` answers the question "is this client done?", which is the
claim the owner's rule is actually about.
"""
from __future__ import annotations

#: The facets a client is "done" on. Mirrors the CHECK constraint in
#: migration 0051 — the constraint is the enforcement, this is the
#: vocabulary, and `test_ledger.py` asserts they have not drifted apart.
FACETS = ("leadership", "firmographics", "techstack", "sentiment",
          "why_now", "platform_readiness", "peer_scores")

#: Which promoted (page, section) carries each facet to the reader. A facet
#: is promoted when its section is, so `record_promotion` can be driven off
#: what a promote actually wrote rather than off a producer remembering to
#: declare it.
FACET_SECTIONS = {
    "leadership":         ("overview", "leadership"),
    "firmographics":      ("overview", "firmographics"),
    "techstack":          ("techstack", "techstack"),
    "sentiment":          ("overview", "sentiment"),
    "why_now":            ("overview", "why_now"),
    "platform_readiness": ("platform", "platform_story"),
    "peer_scores":        ("heatmap", "workbook_scores"),
}

STATES = ("current", "enriched_not_promoted", "never_enriched")
#: The two states that mean a client is not finished. `never_enriched` is a
#: different job from `enriched_not_promoted` — run it, versus promote it —
#: which is why they are two states and not one boolean.
BLOCKING_STATES = ("enriched_not_promoted", "never_enriched")


class LedgerError(ValueError):
    """A ledger write that cannot be made sense of."""


def _facet(facet: str) -> str:
    f = str(facet or "").strip().lower()
    if f not in FACETS:
        raise LedgerError(
            f"unknown facet {facet!r}. The ledger's facets are "
            f"{', '.join(FACETS)} — a new one is a schema change (the CHECK "
            "constraint in 0051), not a string a caller may invent, because a "
            "typo'd facet silently creates an eighth one nobody watches.")
    return f


def record_enrichment(cur, entity_id, facet: str, source: str, *,
                      run_id=None, account: str | None = None,
                      rows_written: int | None = None,
                      note: str | None = None) -> int:
    """Record that `facet` was enriched. Returns the version allocated.

    `source` is required and `account` is strongly wanted: the same
    technographic scan returned empty twice under one account and sixty
    technologies under another, and with no record of which, the two runs
    were indistinguishable afterwards.
    """
    f = _facet(facet)
    src = str(source or "").strip()
    if not src:
        raise LedgerError(
            "source is required: a ledger row with no source cannot answer "
            "'run it again how?', which is the only question a stale facet "
            "raises.")
    cur.execute("SELECT next_enrichment_version(%s, %s)", (entity_id, f))
    version = int(cur.fetchone()[0])
    cur.execute(
        """INSERT INTO enrichment_ledger
             (entity_id, run_id, facet, enrichment_version, source, account,
              rows_written, note)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (entity_id, run_id, f, version, src, account, rows_written, note))
    return version


def record_promotion(cur, entity_id, facet: str, *, run_id=None,
                     version: int | None = None) -> int:
    """Record that `facet` reached the serving tier.

    With no `version`, the CURRENT newest enrichment is promoted — which is
    what a promote of that section actually does. A facet promoted before it
    was ever enriched records version 0: the surface is live and carries
    whatever the package held, and the drift view still calls it
    `never_enriched`, because it was.
    """
    f = _facet(facet)
    if version is None:
        cur.execute("""SELECT COALESCE(max(enrichment_version), 0)
                         FROM enrichment_ledger
                        WHERE entity_id = %s AND facet = %s""", (entity_id, f))
        version = int(cur.fetchone()[0])
    cur.execute(
        """INSERT INTO facet_promotion_state
             (entity_id, facet, promoted_version, promoted_at, run_id)
           VALUES (%s,%s,%s, now(), %s)
           ON CONFLICT (entity_id, facet) DO UPDATE
              SET promoted_version = EXCLUDED.promoted_version,
                  promoted_at      = EXCLUDED.promoted_at,
                  run_id           = EXCLUDED.run_id
            -- Never move BACKWARDS. Re-promoting a retained page must not
            -- report a facet as freshly promoted at an older version than
            -- one already served.
            WHERE facet_promotion_state.promoted_version
                  <= EXCLUDED.promoted_version""",
        (entity_id, f, version, run_id))
    return version


def record_promotion_for_sections(cur, entity_id, sections, *, run_id=None):
    """Record promotion for every facet whose section is in `sections`.

    `sections` is the (page, section) set a promote actually wrote, so the
    promotion state is driven off what happened rather than off a producer
    declaring it — the declaration is the thing that goes missing.
    """
    want = {tuple(s) for s in sections}
    done = []
    for facet, key in FACET_SECTIONS.items():
        if key in want:
            record_promotion(cur, entity_id, facet, run_id=run_id)
            done.append(facet)
    return sorted(done)


def drift(cur, entity_id) -> list[dict]:
    """Every facet for this entity, with its state. Ordered worst first, so
    an operator reading the top of the list reads the work."""
    cur.execute(
        """SELECT facet, enrichment_version, enriched_at, promoted_version,
                  promoted_at, state
             FROM enrichment_drift
            WHERE entity_id = %s""", (entity_id,))
    rows = [{"facet": r[0], "enrichment_version": r[1],
             "enriched_at": r[2].isoformat() if r[2] else None,
             "promoted_version": r[3],
             "promoted_at": r[4].isoformat() if r[4] else None,
             "state": r[5]} for r in cur.fetchall()]
    return order(rows)


def blocking(rows) -> list[dict]:
    """The facets that stop a client being called done."""
    return [r for r in rows if r["state"] in BLOCKING_STATES]


#: Worst first. An operator reads the top of a list, so the work belongs
#: there — and `never_enriched` outranks `enriched_not_promoted` because it
#: is the longer job.
_RANK = {"never_enriched": 0, "enriched_not_promoted": 1, "current": 2}


def order(rows) -> list[dict]:
    return sorted(rows, key=lambda r: (_RANK.get(r.get("state"), 9),
                                       r.get("facet") or ""))


def summary(rows) -> dict:
    """The shape a connector reply and the app's flag both read.

    Orders here as well as in `drift`, so the guarantee holds for any caller
    rather than only for the one that happens to read the view.
    """
    rows = order(rows)
    stuck = blocking(rows)
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in STATES}
    return {
        "facets": rows,
        "counts": counts,
        "blocking": [r["facet"] for r in stuck],
        "done": not stuck,
        "reason": _reason(stuck),
    }


def _reason(stuck) -> str | None:
    if not stuck:
        return None
    never = sorted(r["facet"] for r in stuck if r["state"] == "never_enriched")
    late = sorted(r["facet"] for r in stuck
                  if r["state"] == "enriched_not_promoted")
    parts = []
    if late:
        parts.append(
            f"{len(late)} facet{'s' if len(late) > 1 else ''} enriched and not "
            f"promoted ({', '.join(late)}) — the work exists and no reader can "
            "see it, which is the state this ledger was built to catch")
    if never:
        parts.append(
            f"{len(never)} facet{'s' if len(never) > 1 else ''} never enriched "
            f"({', '.join(never)})")
    return "; ".join(parts)
