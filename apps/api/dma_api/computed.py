"""The fields the contract declares COMPUTED and nobody was computing.

`build_page` read columns and returned. Eleven required contract fields have
no column on purpose — they are census counts, rollups and reconciliation
assertions, and invariant 8 says a count with a source of truth is computed,
never stored. The read path then computed none of them, so every one of them
served as absent, and absent on a client surface reads as "the producer left
it empty" rather than "the app did not do its half".

Measured 2026-08-09 on both promoted clients: none of O11's five fields
present on either. **The whole evidence-mix panel has never rendered, for any
client, ever.** `safeguard_gates.gates` was never joined from `gate_results`,
so a failing SG disclosed nothing — and invariant 12's whole point is that a
failing safeguard gate discloses and still promotes.

Two rules hold everywhere in this module:

  * **A count is computed or it is null.** Never a zero standing in for
    "not computed" — invariant 9. A reader cannot tell a real zero from a
    missing one, so this module returns None when it has no basis and a
    number only when it counted something.
  * **Never overwrite what the producer sent.** Where a producer wrote a
    figure the contract says is computed, the computed value wins and the
    producer's is kept beside it as `<field>_stated`. If they disagree,
    that disagreement is a finding, and deleting one of the two numbers is
    how it stops being one.
"""
from __future__ import annotations

import json
from pathlib import Path

# Tier -> the highest evidence level that tier can carry, RENDERED beside the
# count because it is what the mix means (O11 contract). T5 is vendor
# collateral: corroboration required, ceiling L2.
TIER_CEILING = {"T1": "L5", "T2": "L5", "T3": "L4", "T4": "L2.5", "T5": "L2"}

# The four layer cards, in render order, with the pillar each absorbs
# (charter: OPS · CUST · DATA · INFRA, deliberately not L2–L5).
LAYERS = (("OPS", "P3"), ("CUST", "P2"), ("DATA", "P4"), ("INFRA", "P4"))

# The four landscape tiles. GAPS is not a status in the register — it is the
# ABSENT rows, which is why the tile prints named items rather than a bare
# count.
TILE_FOR_STATUS = {"CONFIRMED": "CONFIRMED", "INFERRED": "INFERRED",
                   "CLAIMED": "CLAIMED", "ABSENT": "GAPS"}


def _product_label(vendor: str | None, name: str | None) -> str:
    """`vendor + " " + product`, unless the product already carries it.

    The register stores them separately and a producer may put the vendor
    in either field or both. Blind concatenation produced "Salesforce
    Salesforce Data Cloud" and "MuleSoft MuleSoft Anypoint Platform" on a
    customer-facing D2 tile — mine, found by an adversarial read of the
    live page.
    """
    name = (name or "").strip()
    vendor = (vendor or "").strip()
    if not vendor:
        return name
    if not name:
        return vendor
    if name.lower().startswith(vendor.lower()):
        return name
    return f"{vendor} {name}"


def _pct(part: int, whole: int) -> float | None:
    """A share, or None. Never 0.0 for an empty denominator: 0% of nothing
    is a claim about nothing, and it renders as a fact."""
    return round(100.0 * part / whole, 1) if whole else None


def _set(data: dict, key: str, value) -> None:
    """Write a computed field, preserving a producer-sent one beside it."""
    if value is None:
        return
    stated = data.get(key)
    if stated is not None and stated != value:
        data[f"{key}_stated"] = stated
    data[key] = value


# ── overview ───────────────────────────────────────────────────────────────
def firmographics(data: dict) -> None:
    rows = data.get("fields")
    if not isinstance(rows, list):
        return
    dated = sum(1 for r in rows if isinstance(r, dict) and r.get("as_of"))
    _set(data, "undated_pct", _pct(len(rows) - dated, len(rows)))


def evidence_coverage(cur, data: dict, run_id, entity_id,
                      entity_domain: str | None = None) -> None:
    """O11's census, over the run's own evidence store.

    An item is a DOCUMENT; a fact is a claim carried by one. One annual
    report is one item carrying many facts (E-xxx:Fy), so both are reported
    and neither substitutes for the other. Here the fact grain is the
    cell links: a document evidencing eleven cells is eleven facts about
    this run, which is the only fact count this schema can honestly derive.
    """
    # "This run's evidence" is defined ONCE, in `evidence.py`, and this reads
    # the same definition: rows belonging to the entity that this run links to
    # a cell. `evidence_run_links` looks like the right table and is EMPTY —
    # 0 rows for a run whose evidence_subcap_links carries 6,323 — so a census
    # over it reported a store of zero for a client with 182 rows, which is
    # how a second definition of the same thing fails.
    cur.execute(
        """SELECT ei.tier::text, ei.claim_type::text, ei.source_domain,
                  count(l.subcap_id)
             FROM evidence_index ei
             JOIN evidence_subcap_links l
               ON l.e_id = ei.e_id AND l.run_id = %s
            WHERE ei.entity_id = %s
            GROUP BY ei.e_id, ei.tier, ei.claim_type, ei.source_domain""",
        (run_id, entity_id))
    rows = cur.fetchall()
    if not rows:
        # No evidence linked to this run is a FINDING, not a zero. Say so in
        # the field's own words rather than printing 0 items and 0%.
        _set(data, "item_count", 0)
        _set(data, "fact_count", 0)
        data.setdefault("empty_reason",
                        "no evidence rows are linked to this run, so the mix "
                        "cannot be described")
        return

    tiers, claims, self_sourced, facts = {}, {}, 0, 0
    own = _entity_domains(cur, entity_id, entity_domain, run_id)
    for tier, claim, domain, n_links in rows:
        tiers[tier or "unknown"] = tiers.get(tier or "unknown", 0) + 1
        claims[claim or "unlabelled"] = claims.get(claim or "unlabelled", 0) + 1
        facts += int(n_links or 0)
        if domain and any(domain.endswith(d) for d in own):
            self_sourced += 1

    total = len(rows)
    _set(data, "item_count", total)
    _set(data, "fact_count", facts)
    _set(data, "tiers", [
        {"tier": t, "count": c, "pct": _pct(c, total),
         "max_evidence_level": TIER_CEILING.get(t)}
        for t, c in sorted(tiers.items())])
    _set(data, "claim_classes", [
        {"claim_label": k, "count": c, "pct": _pct(c, total)}
        for k, c in sorted(claims.items())])
    # Only meaningful when the entity's own domains are known. Guessing them
    # from the evidence would make the numerator define its own denominator.
    _set(data, "self_sourced_pct", _pct(self_sourced, total) if own else None)
    if own:
        _set(data, "self_sourced_basis",
             "share of items published on " + ", ".join(sorted(own)))
    else:
        # A field that is simply ABSENT reads as "the producer left it
        # empty" — the exact misreading this module exists to end, and the
        # one its own docstring names. Measured 2026-08-09: `entities.domain`
        # is NULL on all 166 rows, no row in the corpus carries
        # `origin = 'internal'`, and nothing in the ingest path writes
        # either — so this figure cannot be computed for ANY client today
        # and says so, naming what would close it.
        data.setdefault("self_sourced_basis",
                        "not computed: this run records no publication "
                        "domain for the entity itself, and inferring one "
                        "from the evidence would let the numerator define "
                        "its own denominator. Closed by the run stating "
                        "firmographics.website, which the contract has "
                        "required on every sub-vertical since 2026-08-14")


def _bare_domain(value) -> str:
    """`https://WWW.BCU.org/about` -> `client.example`. "" when there is nothing.

    `entities.domain` is TEXT and nothing enforces its shape, so a value
    written as a URL would match no `source_domain` and score a confident
    0% — a wrong number, which is worse than the null it replaced. This is
    the same defensive normalisation `source_domain` gets at ingest.
    """
    if not isinstance(value, str):
        return ""
    v = value.strip().lower()
    v = v.split("://", 1)[-1]              # scheme
    v = v.split("/", 1)[0]                 # path
    v = v.split("?", 1)[0].split("#", 1)[0]
    v = v.rsplit("@", 1)[-1]               # userinfo
    v = v.split(":", 1)[0]                 # port
    return v.removeprefix("www.").strip(".")


def _entity_domains(cur, entity_id, entity_domain: str | None = None,
                    run_id=None) -> set:
    """The entity's own publication domains.

    Three sources, in authority order, and none of them is the evidence mix
    this figure is a share OF:

    1. `entities.domain` — the column the schema declares for exactly this,
       carried on `serving_directory` (0045) because `svc_api` holds no
       grant on `entities`.
    2. The run's own `firmographics.website` — required on every sub-vertical
       as of 2026-08-14 (build owner). This is the source that actually
       fires: `entities.domain` is populated by nothing (0 of 166 rows, and
       the write half of that is still upstream), whereas the website is
       stated by the producer with provenance like any other firmographic,
       and it arrives with the run rather than ahead of it.
    3. evidence rows this run marked `origin = 'internal'` — the entity's
       own publications, as classified at registration.

    Empty when none states one, which makes self_sourced_pct null rather
    than 0. Reading beyond source 3 is the half that was missing: the
    original version named only that one, and `evidence_origin_t` has an
    `internal` label that no row in the corpus has ever carried — so the
    condition was unsatisfiable and the field could never render for any
    client. A mechanism that cannot fire is worse than none, because the
    code reads as though the path exists.

    Every source goes through `_bare_domain`, because a producer writing
    `https://www.client.example/` would otherwise match no `source_domain`
    and render a confident 0% — worse than the null it replaced.
    """
    own = {_bare_domain(entity_domain)} if _bare_domain(entity_domain) else set()
    if run_id is not None:
        # `field` is free text by contract, so match the shapes a producer
        # actually writes rather than one spelling. Quarantined rows are
        # excluded: a field the identity gate refused is not a fact.
        cur.execute(
            """SELECT value FROM overview_firmographics
                WHERE run_id = %s AND value IS NOT NULL
                  AND coalesce(quarantined, false) = false
                  AND lower(field) IN ('website', 'web site', 'domain',
                                       'primary domain', 'web domain',
                                       'entity website', 'url')""",
            (run_id,))
        own |= {d for d in (_bare_domain(r[0]) for r in cur.fetchall()) if d}
    cur.execute(
        """SELECT DISTINCT ei.source_domain
             FROM evidence_index ei
            WHERE ei.entity_id = %s AND ei.origin = 'internal'
              AND ei.source_domain IS NOT NULL""", (entity_id,))
    return own | {r[0] for r in cur.fetchall() if r[0]}


# ── insights ───────────────────────────────────────────────────────────────
def landscape(cur, data: dict, run_id) -> None:
    """Invariant 8, verbatim: the T2 landscape recomputes from the T1
    register. Two code paths producing two numbers is exactly what the
    `reconciles_to_register` boolean exists to make visible."""
    cur.execute(
        # ORDER BY id: rule 10, order is meaning. Without it the GAPS tile's
        # named_items came back in heap order and two of three platforms
        # swapped between reads of one promoted run.
        """SELECT status::text, name, vendor, evidence_level::text
             FROM techstack_items WHERE run_id = %s ORDER BY id""",
        (run_id,))
    rows = cur.fetchall()
    if not rows:
        return
    buckets: dict = {k: [] for k in ("CONFIRMED", "INFERRED", "CLAIMED", "GAPS")}
    for status, name, vendor, level in rows:
        tile = TILE_FOR_STATUS.get((status or "").upper())
        if tile:
            buckets[tile].append((_product_label(vendor, name), level))

    tiles = []
    for kind in ("CONFIRMED", "INFERRED", "CLAIMED", "GAPS"):
        members = buckets[kind]
        levels = sorted({l for _, l in members if l})
        tiles.append({
            "kind": kind, "count": len(members),
            # The basis is PRINTED: a bare count invites certainty, and
            # "5 · L1–L3 evidence" tells a reader what kind of five.
            "basis": (f"{len(members)} · {levels[0]}–{levels[-1]} evidence"
                      if len(levels) > 1 else
                      f"{len(members)} · {levels[0]} evidence" if levels else
                      f"{len(members)} · evidence level not recorded"),
            "detail": None,
            # Only the GAPS tile names its members: a list of what is absent
            # is the finding; a list of what is present is the register.
            "named_items": ([n for n, _ in members] if kind == "GAPS" else []),
        })
    _set(data, "tiles", tiles)
    _set(data, "reconciles_to_register",
         sum(t["count"] for t in tiles) == len(rows))


# ── techstack ──────────────────────────────────────────────────────────────
def techstack_layers(cur, data: dict, run_id, catalog_version) -> None:
    """`layers` is required by the contract and had no writer anywhere: the
    string appears in no promote path, so it could not be persisted or served
    for any client, ever. The frontend compensated by computing the rollup
    from `items` with `expected` set to the rows the producer wrote — which is
    circular, and on one client rendered "11 of 12, 92% covered" on a register
    whose own empty_state said it was narrower than the estate.

    Here `expected` is the catalogue's platform coverage for the layer's
    pillar — an outside number the register cannot move — and it is null,
    not a substitute, when the catalogue does not state one.
    """
    cur.execute("""SELECT layer::text, status::text, is_primary_gap
                     FROM techstack_items WHERE run_id = %s""", (run_id,))
    rows = cur.fetchall()
    if not rows:
        return
    expected = _expected_per_layer(cur, catalog_version)
    # DATA and INFRA both absorb P4. Handing each of them the whole pillar
    # would let two layers claim the same denominator, so "6 of 187" and
    # "11 of 187" would both be printed over one 187 — a bigger lie than no
    # denominator at all. Where a pillar carries more than one layer the
    # count is not separable and `expected` is null, with the reason stated
    # rather than left for a reader to infer from a blank.
    shared = {p for p in {pl for _, pl in LAYERS}
              if sum(1 for _, q in LAYERS if q == p) > 1}
    out = []
    for layer, pillar in LAYERS:
        members = [r for r in rows if (r[0] or "").upper() == layer]
        detected = sum(1 for r in members
                       if (r[1] or "").upper() in ("CONFIRMED", "INFERRED"))
        n = None if pillar in shared else expected.get(pillar)
        out.append({
            "layer": layer, "pillar_id": pillar, "detected": detected,
            "expected": n,
            "expected_basis": (
                f"cells in {pillar} carrying a platform vocabulary "
                f"({catalog_version})" if n is not None else
                f"{pillar} is shared by more than one layer, so a per-layer "
                f"expected count is not separable from the catalogue"
                if pillar in shared else
                f"{catalog_version} maps no platform vocabulary onto {pillar}"),
            "is_primary_gap": any(bool(r[2]) for r in members),
        })
    _set(data, "layers", out)


def _expected_per_layer(cur, catalog_version) -> dict:
    """Cells carrying a platform vocabulary, per pillar, in the run's PINNED
    catalogue version.

    The version comes from `serving_directory` — svc_api holds no SELECT on
    `runs` by design (invariant 8: the directory view is the one window), so
    joining the run here would 42501 rather than answer.

    Returns {} rather than zeros when the catalogue does not carry the
    mapping: an expected count of 0 renders every layer as fully covered,
    which is the circular rollup this function replaces.
    """
    if not catalog_version:
        return {}
    # `l3_platform_areas`, not `l3_platform`. The first version of this query
    # named a column that does not exist and the section served
    # `computed_error: DatabaseError` — caught, named, and still wrong,
    # because the unit test drove a fake cursor that answered whatever it was
    # asked. A fake cannot refuse a column name. That is why
    # test_computed_against_the_real_schema.py exists.
    cur.execute(
        """SELECT pillar_id, count(*) FROM ccg_subcaps
            WHERE version = %s AND coalesce(cardinality(l3_platform_areas), 0) > 0
            GROUP BY pillar_id""", (catalog_version,))
    return {p: n for p, n in cur.fetchall()}


# ── heatmap ────────────────────────────────────────────────────────────────
def cell_items(cur, data: dict, entity_id) -> None:
    """Resolve every cell's `items[]` from its own `e_ids`.

    `items` and `thin` are the two H2 item keys the field census exempts from
    needing a column, and the exemption states exactly what they are:

        items — "the resolved form of the row's own e_ids: one evidence_index
                 row per id, which is exactly {e_id, tier, claim_label,
                 recency, source_title, publisher, excerpt}. grounded_on is
                 GENERATED as the length of that very array, so storing the
                 objects too would be the second code path invariant 8
                 forbids"
        thin  — "grounded_on < 3, computed from a GENERATED column"

    The exemption was right and nothing performed it. So the evidence
    DRAWER — what a reader opens to see the quotation a cell rests on, the
    only place on the heatmap where a claim meets its source text — resolved
    to nothing for every client since the beginning, and read as a producer
    who had cited nothing.

    Measured before this landed, on the reference client: 698 of 706 cells
    linked, 0 with a resolvable item. It also accounts for a byte gap nobody
    could explain: one heatmap verdict records assembled_bytes 497,793
    against 372,236 served.

    One query for the whole page, not one per cell: 706 cells against a few
    hundred evidence rows is a join, not 706 round trips.
    """
    cells = data.get("cells")
    if not isinstance(cells, list) or not cells:
        return
    wanted = sorted({e for c in cells if isinstance(c, dict)
                     for e in (c.get("e_ids") or []) if isinstance(e, str)})
    if not wanted:
        return
    # Entity-scoped, always: an id that resolves to ANOTHER institution is
    # contamination, and invariant 4 says that halts production rather than
    # rendering. Scoping the lookup means a foreign id resolves to nothing
    # here and the cell shows the id it could not open, rather than opening
    # somebody else's document.
    #
    # Resolved through `resolve_evidence_id` (0046), because a citation may
    # name a row a later scan replaced: 0043 moved the cell links onto the
    # re-mint and left 4,366 bare ids in the corpus carrying none. Opening
    # the drawer on the superseded row shows the OLDER, shorter excerpt and
    # no linkage, which is the version of the source we deliberately stopped
    # using. The rule lives in the database because the connector's ET-07
    # resolves the same citations, and two copies of it is what produced the
    # inverted remediation this pointer was added to end.
    #
    # `cited` is kept beside `e_id` so the payload's id and the row actually
    # shown are both on the surface, rather than the resolution being silent.
    cur.execute(
        """SELECT w.cited, ei.e_id, ei.tier::text, ei.claim_type::text,
                  ei.recency_band::text, ei.source_name, ei.source_domain,
                  ei.excerpt
             FROM unnest(%s::text[]) AS w(cited)
             JOIN evidence_index ei
               ON ei.e_id = resolve_evidence_id(w.cited)
            WHERE ei.entity_id = %s""", (wanted, entity_id))
    by_id = {r[0]: {"e_id": r[1], "tier": r[2], "claim_label": r[3],
                    "recency": r[4], "source_title": r[5], "publisher": r[6],
                    "excerpt": r[7],
                    **({"cited_as": r[0]} if r[0] != r[1] else {})}
             for r in cur.fetchall()}

    unresolved = 0
    for c in cells:
        if not isinstance(c, dict):
            continue
        ids = [e for e in (c.get("e_ids") or []) if isinstance(e, str)]
        items = [by_id[e] for e in ids if e in by_id]
        unresolved += len(ids) - len(items)
        # Order follows e_ids, which the producer ranked. Order is meaning.
        _set(c, "items", items)
        # `thin` is the ABSENCE-ROUTE marker — it travels with
        # sources_searched and closure_condition ("A cell's evidence is
        # genuinely thin: emit thin, sources_searched, closure_condition").
        # It is NOT a citation-count flag: computing it as grounded_on < 3
        # marked 565 CITED cells thin on the reference client, because 544
        # of them cite exactly two items — the exact definition the plan's
        # stress test withdrew as "ruinous on the reference", shipped here
        # for one deploy before this measurement caught it. The maturity
        # surface's flag is `is_thin_evidence` on the workbook scores, and
        # one screen must not carry two meanings of one word. So: the
        # producer's value serves untouched, and the only computed default
        # is thin=true on a cell with NO citations and no producer value —
        # the state the absence protocol exists to mark.
        if "thin" not in c and not ids:
            c["thin"] = True
    if unresolved:
        # Named rather than absorbed: ids that do not resolve inside this
        # entity are either deleted evidence or another institution's, and
        # both are findings.
        data["unresolved_citations"] = unresolved


def cell_linking_stats(data: dict) -> None:
    """Reach counters, so a zero-reach client is visible.

    `cells_citable` is the addition the coverage-card contradiction demanded:
    a cell can be LINKED to evidence rows that carry no excerpt, and such a
    row cannot be opened, cited or read. The grid counted links and rendered
    those cells as evidenced while the coverage card, on the same run,
    reported that they could not be opened. Both numbers now serve, so the
    disclosure is on the surface rather than in the difference between two
    surfaces. Thinness itself is NOT redefined here: recomputing it from
    citable rows alone refuses 573 of 706 cells on the reference client, and
    a flag that fires on 81% of a clean run is not a flag.
    """
    cells = data.get("cells")
    if not isinstance(cells, list):
        return
    linked = citable = 0
    for c in cells:
        if not isinstance(c, dict):
            continue
        if c.get("e_ids"):
            linked += 1
        if any(isinstance(i, dict) and (i.get("excerpt") or "").strip()
               for i in (c.get("items") or [])):
            citable += 1
    _set(data, "linking_stats", {
        "cells_scored": len(cells),
        "cells_linked": linked,
        "cells_citable": citable,
        "rows_unlinkable": len(cells) - linked,
    })


def evidence_age_rollups(data: dict) -> None:
    rows = data.get("rows")
    if not isinstance(rows, list):
        return
    stale = sum(1 for r in rows if isinstance(r, dict)
                and (r.get("band") or "").lower() in ("stale", "archival"))
    undated = sum(1 for r in rows if isinstance(r, dict)
                  and not r.get("published_or_asof"))
    _set(data, "stale_pct", _pct(stale, len(rows)))
    _set(data, "undated_pct", _pct(undated, len(rows)))


def safeguard_gates(cur, data: dict, run_id) -> None:
    """Invariant 12: an SG result renders to the client with its plain_label
    and, when it did not run, the reason. The connector writes every result to
    `gate_results` as it runs; nothing joined that table, so a failing gate
    disclosed nothing and the card was empty on every client.

    The plain_label comes from `gate_registry`, not from the result row — one
    definition of what a gate means, in the place the gate is defined.
    """
    # ONE row per gate: the LATEST. `gate_results` accumulates a row per
    # evaluation, and a resubmitted page evaluates its gates again — the reference client
    # carries 61 rows for SG-V4 and 23 for SG-S8 across its submission
    # history. Serving them all would render the same gate eighty-four times
    # and put a superseded FAIL beside its own later PASS, with nothing on
    # the card to say which is current.
    cur.execute(
        """SELECT DISTINCT ON (g.gate_id)
                  g.gate_id, r.plain_label, g.result::text, g.detail,
                  g.not_run_reason
             FROM gate_results g
             LEFT JOIN gate_registry r ON r.gate_id = g.gate_id
            WHERE g.run_id = %s AND g.gate_id LIKE 'SG-%%'
            ORDER BY g.gate_id, g.evaluated_at DESC, g.id DESC""", (run_id,))
    rows = cur.fetchall()
    if not rows:
        return
    _set(data, "gates", [
        {"gate_id": gid, "plain_label": label, "result": result,
         "detail": detail,
         # A gate reporting PASS because it did not run is worse than one
         # reporting FAIL, so NOT_RUN without a reason is stated as such
         # rather than rendered as a blank.
         "not_run_reason": (reason if result != "NOT_RUN" or reason else
                            "recorded NOT_RUN with no reason given")}
        for gid, label, result, detail, reason in rows])


# ── enrichment status ──────────────────────────────────────────────────────
#
# THE SIGNAL THAT DID NOT EXIST. Nothing in this product recorded that a
# surface depended on an enrichment source, so a section built without a scan
# and a section built with one rendered identically. Measured 2026-08-14: one
# client's technology register served 12 rows against another's 51, its own
# empty_state said the technographic scan "did not run", and no surface, gate,
# checker or routine read that sentence.
#
# This computes, per section, from what was actually served:
#
#   required     this surface depends on an enrichment source
#   sources      which ones (explorium at ingest, clay in a producer session)
#   ran          whether ANY item carries a basis showing enrichment reached it
#   count        rows served / thin_below floor
#   thin         count is under the floor
#   thin_reason  why that matters, in the register's own words
#   closes_with  what would close it
#
# Counted, never stored (invariant 8), and additive — a page that renders
# without this is worse than one that renders with it, so a register that
# cannot be read leaves every section unflagged rather than failing the page.
_ENRICHMENT_REGISTER: dict | None = None


def _enrichment_register() -> dict:
    global _ENRICHMENT_REGISTER
    if _ENRICHMENT_REGISTER is None:
        try:
            path = (Path(__file__).resolve().parents[3] / "packages" /
                    "shared" / "enrichment_register.json")
            _ENRICHMENT_REGISTER = json.loads(path.read_text()).get("surfaces") or {}
        except Exception:                   # noqa: BLE001
            _ENRICHMENT_REGISTER = {}
    return _ENRICHMENT_REGISTER


def enrichment_status(data: dict, page: str, section: str) -> None:
    spec = _enrichment_register().get(f"{page}.{section}")
    if not spec or not isinstance(data, dict):
        return
    rows = data.get(spec.get("counts") or "")
    rows = rows if isinstance(rows, list) else []
    count = len(rows)
    floor = spec.get("thin_below") or 0

    # "Ran" is evidenced by the rows themselves, not asserted: an item that
    # carries the register's basis key, or a contact route on a roster, is a
    # row enrichment actually reached. A producer claiming a scan ran while no
    # row shows it would be believed by any check that read a boolean.
    basis_key = spec.get("basis_key")
    contact_keys = spec.get("contact_keys") or ()
    enriched = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        if basis_key and str(r.get(basis_key) or "").strip():
            enriched += 1
        elif any(str(r.get(k) or "").strip() for k in contact_keys):
            enriched += 1

    status = {
        "required": True,
        "sources": list(spec.get("sources") or []),
        "ran": enriched > 0,
        "enriched_rows": enriched,
        "count": count,
        "thin_below": floor,
        "thin": count < floor,
    }
    if status["thin"]:
        status["thin_reason"] = spec.get("thin_reason")
        status["closes_with"] = spec.get("closes_with")
    _set(data, "enrichment_status", status)


# ── the one entry point ────────────────────────────────────────────────────
def apply(cur, page: str, section: str, data, run_meta: dict, entity_id) -> None:
    """Fill this section's computed-at-read fields, in place.

    Called after `assemble` and BEFORE redaction, so a computed field is
    subject to the same audience rules as a promoted one. A failure here must
    never take a page down: the fields are additive, and a page that renders
    without its census is worse than one that renders with it and better than
    one that 500s.
    """
    if not isinstance(data, dict):
        return
    run_id = run_meta["run_id"]
    # A SAVEPOINT, because a failed statement aborts the whole transaction in
    # PostgreSQL and every later query on this request then fails with 25P02.
    # The first version of this module shipped a query naming a column that
    # does not exist; the section reported `computed_error` correctly and
    # would have taken the rest of the page down with it on any page carrying
    # more than one computed section.
    try:
        cur.execute("SAVEPOINT computed_at_read")
    except Exception:                       # noqa: BLE001 — no savepoint, no net
        pass
    try:
        if page == "overview" and section == "firmographics":
            firmographics(data)
        elif page == "overview" and section == "evidence_coverage":
            evidence_coverage(cur, data, run_id, entity_id,
                              run_meta.get("entity_domain"))
        elif page == "insights" and section == "landscape":
            landscape(cur, data, run_id)
        elif page == "techstack" and section == "techstack":
            techstack_layers(cur, data, run_id,
                             run_meta.get("ccg_catalog_version"))
        elif page == "heatmap" and section == "cell_evidence":
            # items[] first: the counters below read what it resolved.
            cell_items(cur, data, entity_id)
            cell_linking_stats(data)
        elif page == "heatmap" and section == "evidence_age":
            evidence_age_rollups(data)
        elif page == "heatmap" and section == "safeguard_gates":
            safeguard_gates(cur, data, run_id)
        # Runs for EVERY section, after whatever else this section computes,
        # because a surface that depends on an enrichment source has to say so
        # whether or not it has other computed fields.
        enrichment_status(data, page, section)
    except Exception as exc:                # noqa: BLE001
        # Named, not swallowed. The section says which computation failed and
        # why, so an absent census reads as a broken computation rather than
        # as an empty producer.
        data["computed_error"] = f"{page}.{section}: {type(exc).__name__}"
        try:
            cur.execute("ROLLBACK TO SAVEPOINT computed_at_read")
        except Exception:                   # noqa: BLE001
            pass
    else:
        try:
            cur.execute("RELEASE SAVEPOINT computed_at_read")
        except Exception:                   # noqa: BLE001
            pass
