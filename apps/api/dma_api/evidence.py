"""The evidence drawer's read path — fail-closed (invariant 4).

Every surface in this app cites evidence by id, and every one of those ids is
meant to open a drawer showing the verbatim excerpt behind the claim. That is
the product's whole argument-from-evidence posture, so RESOLUTION of a cited id
is strict rather than convenient, and it is entity-scoped because that is the
scope invariant 4 defines:

  found      the id exists AND belongs to this entity
  not_found  no such id anywhere
  foreign    the id exists but belongs to a DIFFERENT entity

`foreign` is never rendered as a row and never silently dropped: a citation
pointing at another institution's evidence is a contamination signal, and the
drawer says so. The connector halts production on it at submit time; here, on
the read side, the reader is told.

LISTING is a different question from resolution, and it used to be answered
with the same query. Asked for "this run's evidence" the module returned every
row the ENTITY owns, while the `linked_subcap_ids` beside each row were read
per RUN — so a second ingest's rows were listed under the first run's evidence
tab with no cells behind any of them (36 of 178 for one client). A row that
cannot be resolved to this run must not be listed as if it belonged to it, so
the unfiltered listing is run-scoped by the two facts that actually tie a row
to a run:

  · the run LINKS it (`evidence_subcap_links.run_id` — the same resolution
    revision 0021 uses to decide which run an entity-grained evidence row
    belongs to), or
  · the run CITES it (its id appears in the `e_ids` of a row this run
    promoted). A producer-registered source with no cell links is still this
    run's evidence if this run's pages cite it.

Nothing is inferred. The tier, claim class, recency band and age in months are
GENERATED or stored columns on `evidence_index` — this module selects them, it
does not compute them (invariants 8 and 9). The only computed values are counts
over the rows themselves, which is exactly where invariant 8 says counts belong.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path as _Path


def _put_shared_on_path() -> None:
    """REPO FIRST, image second — the same order computed.py argues for.

    A build artefact shadowing its own source is how verification runs against
    the wrong copy: `apps/api/shared/` is gitignored and written by deploy.sh,
    so in a checkout it can be an old copy of a file a human has since fixed.
    In the image the repo path does not exist and the staged one is the only
    one. In the image this module is /app/dma_api/evidence.py — three parents,
    so the repo path is built CONDITIONALLY or it raises IndexError on the
    line before the path that would have worked.
    """
    here = _Path(__file__).resolve()
    cands = []
    if len(here.parents) > 3:
        cands.append(here.parents[3] / "packages" / "shared")
    cands.append(here.parent.parent / "shared")
    wanted = [str(c) for c in cands if c.exists()]
    # ALREADY PRESENT IS NOT THE SAME AS PRESENT IN THE RIGHT ORDER, and the
    # first version of this treated them as the same: it skipped a candidate
    # found anywhere on the path and inserted the other at position 0, so the
    # gitignored staged copy won whenever a caller had put the repo path on
    # first. A stale `apps/api/shared/abbreviations.py` from an earlier deploy
    # then answered a rule the tracked file had and it did not — the exact
    # shadowing computed.py's loader comments warn about, reproduced by the
    # code that quotes them. So: drop every occurrence, then lay them down in
    # priority order.
    for path in wanted:
        while path in sys.path:
            sys.path.remove(path)
    for path in reversed(wanted):
        sys.path.insert(0, path)


_put_shared_on_path()
# Imported hard, never in a try. A missing shared file must fail the deploy
# loudly: enrichment_register.json was swallowed into an empty dict once and
# five surfaces served without their status while every test passed.
from abbreviations import expand as _expand_abbrev  # noqa: E402
from evidence_merge import merge_same_source  # noqa: E402

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


def _row_to_item(row: tuple, columns=_COLUMNS) -> dict:
    item = dict(zip(columns, row))
    # THE ABBREVIATION IN THE LABEL, spelled out here because there is nowhere
    # else it can be. `source_name` on a package-ingested row is typed by
    # whoever assembled the assessment; the ingested tier is read-only once
    # scanned (charter), and no payload gate ever sees it because it never
    # travels through a payload. Four rounds of sweeps cleared the prose and a
    # reader still opened a drawer onto "Logix FCU call report aggregation".
    #
    # `excerpt` is NOT touched, here or anywhere: it is a byte-for-byte span of
    # the artefact and the verifier compares it against those bytes.
    if item.get("source_name"):
        item["source_name"] = _expand_abbrev(item["source_name"], "label")
    for k in ("published_date", "reference_date"):
        v = item.get(k)
        item[k] = v.isoformat() if hasattr(v, "isoformat") else v
    for k in ("ers",):
        v = item.get(k)
        item[k] = float(v) if v is not None else None
    item.setdefault("linked_subcap_ids", [])
    item["linked_subcap_ids"] = item.get("linked_subcap_ids") or []
    return item


@lru_cache(maxsize=1)
def _citing_tables() -> tuple[str, ...]:
    """Serving tables that carry an `e_ids` column, read off the writer spec.

    Derived rather than listed, for the same reason the reader is: a section
    that gains or loses its citations column changes one description of the
    mapping, and both directions follow. The column is always named `e_ids`
    even where the writer binds it to a differently-named item key
    (`supporting_e_ids`, `evidence_ids`) — it is the COLUMN this needs.
    """
    from .serving_spec import readers
    tables = set()
    for r in readers().values():
        if r["grain"] == "none":
            continue                     # not a per-run table (evidence store)
        if "e_ids" in r["env_cols"] or "e_ids" in r["item_cols"]:
            tables.add(r["table"])
    return tuple(sorted(tables))


def cited_by_run(cur, run_id) -> list[str]:
    """Every evidence id this run's promoted rows cite, deduplicated.

    A citation is a claim of belonging that no link table records: the
    producer registers a source, cites it on a card, and links it to no cell.
    Reading it here keeps such a row in its own run's evidence tab without
    letting another run's rows in.
    """
    tables = _citing_tables()
    if not tables:
        return []
    sql = " UNION ".join(
        f"SELECT unnest(e_ids) AS e_id FROM {t} WHERE run_id = %s" for t in tables)
    cur.execute(sql, [run_id] * len(tables))
    return sorted({r[0] for r in cur.fetchall() if r[0]})


def fetch(cur, entity_id, e_ids: list[str] | None = None,
          run_id=None) -> dict:
    """Evidence for one run of one entity, optionally filtered to specific ids.

    Returns `{items, found, not_found, foreign, distribution}`. The three id
    lists are the drawer's resolution verdict per requested id; they are empty
    when no filter was asked for, because "every id this run holds" cannot have
    a missing one.

    Two scopes, deliberately different:

      · asked for SPECIFIC ids (the drawer resolving a card's citations), the
        row set is the ENTITY's — that is the scope invariant 4 defines, and
        narrowing it would turn a legitimate citation into `not_found` and
        blank a drawer the reader opened on purpose.
      · asked for the LISTING, the row set is this RUN's: rows this run links
        or cites. Another run's rows are not this run's evidence, and listing
        them here is what put 36 link-less rows in one run's evidence tab.

    Each item carries `linked_subcap_ids` — the cells this item was linked to
    in `evidence_subcap_links`, for THIS run. Those links are what make the
    drawer traceable in both directions: a card cites an id, the drawer names
    the id's source and excerpt, and these ids walk back to the cells the item
    actually supports. Read from the link table, never inferred from prose, and
    scoped to the run so a prior run's linkage cannot answer for this one.
    """
    columns = _COLUMNS + ("linked_subcap_ids",)
    # LEFT JOIN LATERAL, not a plain join: an item with no linkage yet is still
    # an evidence row and must resolve, so `found` stays honest.
    sql = (f"SELECT {', '.join('e.' + c for c in _COLUMNS)}, "
           "COALESCE(l.ids, ARRAY[]::TEXT[]) "
           "FROM evidence_index e "
           "LEFT JOIN LATERAL ("
           "  SELECT array_agg(DISTINCT k.subcap_id ORDER BY k.subcap_id) AS ids"
           "  FROM evidence_subcap_links k"
           "  WHERE k.e_id = e.e_id"
           + ("    AND k.run_id = %s" if run_id else "")
           + ") l ON TRUE WHERE e.entity_id = %s")
    params: list = ([run_id] if run_id else []) + [entity_id]
    if e_ids:
        sql += " AND e.e_id = ANY(%s)"
        params.append(list(e_ids))
    elif run_id:
        # `l.ids IS NOT NULL` is exactly "this run links it" — array_agg over
        # no rows is NULL, and the lateral is already run-scoped. The second
        # arm keeps a row this run CITES but linked to no cell: dropping it
        # would hide a source the pages argue from.
        sql += " AND (l.ids IS NOT NULL OR e.e_id = ANY(%s))"
        params.append(cited_by_run(cur, run_id))
    sql += " ORDER BY e.tier, e.e_id"
    cur.execute(sql, params)
    items = [_row_to_item(r, columns) for r in cur.fetchall()]

    # THE LISTING ONLY, and the asymmetry is the point. A row with no verbatim
    # span that references an artefact a sibling row already quotes adds
    # nothing to a reader except its cell links — and on this corpus 10 such
    # rows held the links while the spans sat on a different row, so a cell
    # opened onto a citation with no quote while a quote from the same document
    # was one row away. Merging joins the two.
    #
    # RESOLUTION is never merged: `get_evidence` asks for specific ids and each
    # one must answer for itself (invariant 4). This rewrites what is LISTED,
    # and every absorbed id is named on the survivor as `also_filed_as` and
    # still resolves on its own.
    merge_report = {"absorbed": 0, "groups": 0, "excerpts_recovered": 0}
    if not e_ids:
        items, merge_report = merge_same_source(items)

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
            "foreign": foreign, "distribution": distribution(items),
            # Counted, never silent: a listing that shrank without saying so is
            # indistinguishable from a query that lost rows.
            "merged": merge_report}


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
