"""The evidence drawer's read path — fail-closed, entity-scoped (invariant 4).

Every surface in this app cites evidence by id, and every one of those ids is
meant to open a drawer showing the verbatim excerpt behind the claim. That is
the product's whole argument-from-evidence posture, so the resolution rule is
strict rather than convenient:

  found      the id exists AND belongs to this entity
  not_found  no such id anywhere
  foreign    the id exists but belongs to a DIFFERENT entity

`foreign` is never rendered as a row and never silently dropped: a citation
pointing at another institution's evidence is a contamination signal, and the
drawer says so. The connector halts production on it at submit time; here, on
the read side, the reader is told.

Nothing is inferred. The tier, claim class, recency band and age in months are
GENERATED or stored columns on `evidence_index` — this module selects them, it
does not compute them (invariants 8 and 9). The only computed values are counts
over the rows themselves, which is exactly where invariant 8 says counts belong.
"""
from __future__ import annotations

# Ordered so a distribution renders in ladder order rather than hash order.
TIERS = ("T1", "T2", "T3", "T4", "T5")

# Internal-only per the TRD's rung table: ERS is the app's own scoring of an
# evidence item, and specificity/corroboration are its inputs. A customer sees
# the excerpt and its source, never the grading.
INTERNAL_FIELDS = ("ers", "specificity", "corroboration", "identity_note")

_COLUMNS = ("e_id", "origin", "source_name", "source_url", "source_domain",
            "excerpt", "claim_type", "tier", "published_date", "reference_date",
            "age_months", "recency_band", "ers", "specificity", "corroboration",
            "identity_ok", "identity_note")


def _row_to_item(row: tuple) -> dict:
    item = dict(zip(_COLUMNS, row))
    for k in ("published_date", "reference_date"):
        v = item.get(k)
        item[k] = v.isoformat() if hasattr(v, "isoformat") else v
    for k in ("ers",):
        v = item.get(k)
        item[k] = float(v) if v is not None else None
    return item


def fetch(cur, entity_id, e_ids: list[str] | None = None) -> dict:
    """Evidence for one entity, optionally filtered to specific ids.

    Returns `{items, found, not_found, foreign, distribution}`. The three id
    lists are the drawer's resolution verdict per requested id; they are empty
    when no filter was asked for, because "every id for this entity" cannot
    have a missing one.
    """
    sql = f"SELECT {', '.join(_COLUMNS)} FROM evidence_index WHERE entity_id = %s"
    params: list = [entity_id]
    if e_ids:
        sql += " AND e_id = ANY(%s)"
        params.append(list(e_ids))
    sql += " ORDER BY tier, e_id"
    cur.execute(sql, params)
    items = [_row_to_item(r) for r in cur.fetchall()]

    found = [i["e_id"] for i in items]
    not_found: list[str] = []
    foreign: list[str] = []
    if e_ids:
        missing = [x for x in e_ids if x not in set(found)]
        if missing:
            # An id absent from THIS entity is either unknown or another
            # entity's. The distinction is the whole point of the gate, so it
            # costs one more query rather than being collapsed into "missing".
            cur.execute("SELECT e_id FROM evidence_index WHERE e_id = ANY(%s)",
                        (missing,))
            elsewhere = {r[0] for r in cur.fetchall()}
            foreign = sorted(x for x in missing if x in elsewhere)
            not_found = sorted(x for x in missing if x not in elsewhere)

    return {"items": items, "found": found, "not_found": not_found,
            "foreign": foreign, "distribution": distribution(items)}


def distribution(items: list[dict]) -> dict:
    """Tier and claim-class counts over the rows just read.

    Computed here, never stored (invariant 8), and computed over rows that
    passed the identity gate: `identity_ok = FALSE` excludes an item from
    coverage and from the tier distribution by the schema's own comment, so a
    contaminated citation cannot inflate the picture of how well evidenced a
    run is.
    """
    ok = [i for i in items if i.get("identity_ok") is not False]
    tiers = {t: 0 for t in TIERS}
    claims: dict = {}
    for i in ok:
        t = i.get("tier")
        if t in tiers:
            tiers[t] += 1
        elif t:
            tiers[t] = tiers.get(t, 0) + 1
        c = i.get("claim_type")
        if c:
            claims[c] = claims.get(c, 0) + 1
    return {"tiers": tiers, "claims": claims, "total_items": len(ok),
            "excluded_identity": len(items) - len(ok)}


def redact_items(items: list[dict], audience: str) -> list[dict]:
    """Strip the internal grading for the customer audience. Server-side and
    default-deny, like every other redaction in this app: the customer's
    document never contains the fields, rather than hiding them in the client."""
    if audience != "customer":
        return items
    out = []
    for i in items:
        c = dict(i)
        for k in INTERNAL_FIELDS:
            c.pop(k, None)
        out.append(c)
    return out
