"""The package-evidence id namespace: how a workbook-local `E-0NN` becomes a
row this entity — and only this entity — can cite.

## The defect this module exists to end

`evidence_index.e_id` is a global primary key, but package Evidence_Master
ids are workbook-LOCAL: every General-DMA template starts at E-001, so two
clients both ship an `E-007`. The ingest qualified them with a token folded
out of the institution's NAME (`E-{ENT}-nnn`), and a name is not an identity:

  · `_entity_token` keeps 8 alphanumerics, so "Texas Capital Bancshares" and
    "Tri Counties Bank" are both TCB, "First National Bank of Omaha" and
    "First National Financial LP" are both FIRSTNAT;
  · when the package ships no manifest there is no name at all and the token
    falls back to the literal string `UNK`.

Measured in production 2026-08-08 over 281 ingested runs: 166 entities, 113
distinct tokens, 13 tokens owned by more than one entity — `UNK` by 14 of
them across 1,053 rows. The landing code never aliased across entities; it
simply ran out of escapes (`E-UNK-007`, then `E-UNK-007-R{run_seq}`, both
taken by earlier manifest-less packages) and recorded the item as
unpersistable: 5,019 such observations across 61 runs, 50 runs left with no
citable evidence at all. `get_evidence`, recomputing the same token, found
the first client's row and reported `foreign` — which halts production.

The token was never the safeguard. It only looked like one.

## What replaces it

`evidence_package_ids` (migration 0036) maps (entity_id, package_local_id) →
the stored row, with the entity IN the primary key. Resolution is therefore
entity-scoped by construction: a citation in Northern Trust's workbook can
resolve to a Northern Trust row or to nothing, and there is no query shape
over that table that returns another institution's. A separate table rather
than a column because the relation is many-to-one — when the dedup keeps one
row for two local numbers, both numbers must still resolve.

`foreign` goes back to meaning what invariant 4 means by it: a globally
scoped id (`E-CC-nnn`, or another entity's qualified id) that belongs to
someone else — the reasoning has drifted onto the wrong entity.

The e_id string keeps its readable `E-{TOKEN}-nnn` shape where that is free,
because a stored id that says NORTHERN is worth having, and its `-R{run_seq}`
re-mint. When the token is already spoken for by ANOTHER entity the mint
falls to a suffix taken from this entity's own uuid. Correctness rests on
the mapping table either way, never on the string.
"""
from __future__ import annotations

import re

# A workbook-local package id, optionally cited at fact grain (E-047:F1).
BARE_PACKAGE = re.compile(r"^E-\d+$")
# A stored package id: E-{TOKEN}-nnn, optionally -R{run_seq} (a re-mint after
# a content change) and/or -{ENT6} (the cross-entity escape below).
STORED_PACKAGE = re.compile(r"^E-[A-Z0-9]+-(?P<n>\d+)(?:-(?:R\d+|[0-9A-F]{6}))*$")


def local_id(cited: str) -> str | None:
    """The package-local id a citation names, or None if it is not one.

    `E-047:F1` cites fact 1 OF item E-047; the item is the row.
    """
    item = str(cited or "").split(":")[0].strip().upper()
    return item if BARE_PACKAGE.match(item) else None


def local_id_of_stored(e_id: str) -> str | None:
    """The package-local id a STORED package id was minted from.

    `E-BCU-006`, `E-BCU-006-R2` and `E-UNK-007-1FCA91` all came from the same
    workbook cell. Returns None outside the package namespace — notably the
    server's own `E-CC-nnn` mints, which are not workbook-local and must
    never acquire a mapping (a bare `E-104` must not reach `E-CC-104`).
    """
    s = str(e_id or "").strip().upper()
    if s.startswith("E-CC-"):
        return None
    m = STORED_PACKAGE.match(s)
    return f"E-{m.group('n')}" if m else None


def entity_suffix(entity_id) -> str:
    """A deterministic, entity-unique tail for a minted id.

    Deterministic so re-scanning the same package resolves to the row it
    already created instead of minting a second one; taken from the entity's
    own uuid so it cannot be shared by two institutions the way a folded name
    can. Uniqueness does not rest on these six hex digits — the mapping
    table's primary key does — they only keep the id readable.
    """
    return re.sub(r"[^0-9a-f]", "", str(entity_id).lower())[:6].upper()


def qualify(e_id: str, token: str) -> str:
    """The package-facing id in its stored form: E-047 -> E-{ENT}-047.

    Bare ids stay the package-facing form; this is the one choke point.
    An id that is not `E-nnn` shaped is stored as it arrived — it is already
    outside the template's numbering and qualifying it would invent a shape.
    """
    return f"E-{token}-{e_id[2:]}" if BARE_PACKAGE.match(str(e_id).upper()) else e_id


# The contract floor for a citable span. The schema states it on the column
# (`excerpt TEXT, -- verbatim, 50-500 chars, verified at registration`),
# `register_evidence` refuses outside it, and ET-04 blocks a citation that
# resolves to a row outside it. The worker used to be the one writer of this
# column that did not know the number.
EXCERPT_MIN, EXCERPT_MAX = 50, 500


def citable_span(value):
    """`(excerpt, reason_it_is_not_citable)` — exactly one of the two is set.

    Three different values were being stored in this column and only one of
    them was a span:

      · a real 50-500 character quotation;
      · a fragment under the floor — the rationale miner accepts 20 chars —
        which lands, links to cells, and is then refused by ET-04 the moment
        a producer tries to cite it;
      · the empty string, produced by a whitespace-only workbook cell,
        because `"   "` is truthy and `"   ".strip()` is `""`.

    The empty string is the expensive one, and it is why this function
    returns None rather than tidying in place. `repair_evidence_namespace`
    keys its third arm on `excerpt IS NULL`; `embed` filters on
    `IS NOT NULL`; and `CONTENT_HASH_EXPR` concatenates the excerpt without
    a COALESCE, so a NULL excerpt yields a NULL `content_hash` and the
    dedup index never fires. A row holding `''` is therefore invisible to
    the repair, absent from the embedding corpus and outside the dedup
    index, while reading as populated to every check written against None.
    Measured on Logix run d7ed1d90: 36 of 62 rows uncitable, and the whole
    evidence index had to be re-registered by hand from the fetched sources.

    A short fragment is dropped rather than stored for the same reason a
    guessed field is refused everywhere else in this build: it is not the
    thing it claims to be, and storing it converts a visible absence into an
    invisible defect that surfaces as a blocked submission much later.
    """
    if value is None:
        return None, "the package states no excerpt for this row"
    span = str(value).strip()
    if not span:
        return None, "the package's excerpt cell is empty or whitespace"
    if len(span) < EXCERPT_MIN:
        return None, (f"the package states a {len(span)}-character fragment, "
                      f"under the {EXCERPT_MIN}-character floor a citation "
                      "needs; stored as absent rather than as a span that "
                      "would be refused at ET-04")
    return span[:EXCERPT_MAX], None


def stored_url(value):
    """A source URL, or None. Same reason as above: `''` and NULL were two
    spellings of 'no url' and only one of them was ever queried for."""
    if value is None:
        return None
    url = str(value).strip()
    return url or None


class EvidenceLander:
    """Lands package evidence rows for one entity, and records what each
    workbook-local id resolves to.

    Shared by the ingest (`persist_package`) and by the repair pass that
    re-lands the rows the collision left unpersistable, so both write the
    same rows through the same rules — a repair that landed evidence by a
    second set of rules would be a second thing to get wrong.
    """

    #: Mirrors CONTENT_HASH_EXPR in 0005. Three parameters, IN THIS ORDER:
    #: source_url, claim_type, excerpt.
    #:
    #: IT USED TO HARDCODE THE CLAIM-TYPE SEGMENT AS `''`, on the stated
    #: premise that "the package path never asserts a claim type". The INSERT
    #: eleven lines below passes `ev.get("claim_type")` — so the premise was
    #: false in the same file that stated it, and every package evidence item
    #: carrying a claim type hashed one way into the generated column and
    #: another way in every lookup that tried to find it again.
    #:
    #: Measured against the live generated column on 2026-08-30, same url and
    #: excerpt:
    #:     claim_type NULL    generated af4458b1…  mirror af4458b1…   agree
    #:     claim_type FACT    generated 74b8e86d…  mirror af4458b1…   DIVERGE
    #:
    #: The two consequences, both of which the ingest then recorded as though
    #: they were facts about the package rather than about this expression:
    #:   * `content_hash IS NOT DISTINCT FROM` (line ~299) reads false, so a
    #:     row the entity already holds looks like "same id, different
    #:     content" — a mint under a suffix, logged `evidence_id_collision`.
    #:   * the dedup lookup below cannot find the row the unique index just
    #:     rejected against, so the item is UNATTRIBUTABLE AND DROPPED,
    #:     logged `evidence_conflict_unresolved`.
    #: goeasy-ltd, one package: 316 collisions and 430 dropped items.
    #:
    #: `enum_label` rather than a bare cast because that is what the
    #: generated column uses, and this has to stay byte-identical to it —
    #: being nearly identical is what cost the corpus its evidence.
    HASH_SQL = r"""encode(digest(coalesce(%s,'') || '|' ||
                    coalesce(enum_label(%s::claim_t),'') || '|' ||
                    lower(left(regexp_replace(%s,'\s+',' ','g'),500)),
             'sha256'),'hex')"""

    MAX_MINT_ATTEMPTS = 4

    def __init__(self, cur, *, entity_id, run_id, run_seq: int, token: str,
                 reference_date, observe):
        self.cur = cur
        self.entity_id = entity_id
        self.run_id = run_id
        self.run_seq = run_seq
        self.token = token
        self.reference_date = reference_date
        self._observe = observe
        self.landed: set[str] = set()        # stored ids this pass owns a row for
        self.claimed: set[str] = set()       # local ids this pass has resolved
        self.superseded: dict[str, str] = {}  # minted -> the id it supersedes

    # ------------------------------------------------------------------
    def _lookup(self, local, url, claim_type, excerpt):
        """(stored e_id, content matches) for this entity's row under
        `local`, or (None, False). The entity is in the WHERE clause and in
        the mapping's primary key: this cannot see another institution.

        `claim_type` is part of the content hash and therefore part of the
        question. Omitting it made "content matches" read false for every
        item that carried one — see HASH_SQL."""
        self.cur.execute(
            f"""SELECT m.e_id, e.content_hash IS NOT DISTINCT FROM {self.HASH_SQL}
                  FROM evidence_package_ids m
                  JOIN evidence_index e ON e.e_id = m.e_id
                 WHERE m.entity_id = %s AND m.package_local_id = %s""",
            (url, claim_type, excerpt, self.entity_id, local))
        row = self.cur.fetchone()
        return (row[0], bool(row[1])) if row else (None, False)

    def _map(self, local, e_id):
        """Point this entity's local id at a stored row. Last mint wins: a
        re-mint is the same source read again with fuller content, and 0028
        carries the superseded row's links onto it."""
        self.cur.execute(
            """INSERT INTO evidence_package_ids (entity_id, package_local_id, e_id, run_id)
               VALUES (%s,%s,%s,%s)
               ON CONFLICT (entity_id, package_local_id)
               DO UPDATE SET e_id = EXCLUDED.e_id""",
            (self.entity_id, local, e_id, self.run_id))

    # ------------------------------------------------------------------
    def land(self, ev: dict) -> str | None:
        """Insert one package item; return the stored id its local id
        resolves to, or None (recorded) when nothing can hold it."""
        from decimal import Decimal
        ers = ev.get("ers")
        if ers is not None and not (Decimal("1") <= ers <= Decimal("5")):
            # A stated ERS outside the 1–5 rubric (some packages score on
            # 0–10): landed as NULL and recorded — never rescaled, a made-up
            # conversion would be data that was never stated.
            self._observe("ers_out_of_range",
                          {"package_local_id": ev["e_id"], "stated": str(ers)})
            ev = {**ev, "ers": None}

        local = local_id(ev["e_id"])
        url = stored_url(ev.get("source_url"))
        excerpt, uncitable = citable_span(ev.get("excerpt"))
        # Bound ONCE, here, and passed to the INSERT and to every hash
        # lookup alike. The defect this repairs was exactly a value that the
        # insert wrote and the lookups did not know about.
        claim_type = ev.get("claim_type")
        if uncitable:
            # Recorded per row, so "this package landed evidence nobody can
            # cite" is a number on the scan rather than something a producer
            # discovers by writing prose about it three days later.
            self._observe("evidence_excerpt_uncitable",
                          {"package_local_id": ev["e_id"],
                           "source_url": url, "reason": uncitable})

        prior, prior_same = (None, False)
        if local:
            if local in self.claimed:
                # The same local number twice in one package. Reading order
                # wins, as it does for a repeated subcap row; the repeat is
                # recorded rather than silently overwriting the mapping.
                prior, _ = self._lookup(local, url, claim_type, excerpt)
                self._observe("duplicate_package_local_id",
                              {"package_local_id": local, "resolved_to": prior,
                               "reason": "the package states this local id more "
                                         "than once; the first row keeps it"})
                return prior
            prior, prior_same = self._lookup(local, url, claim_type, excerpt)
            if prior and prior_same and local_id_of_stored(prior) == local:
                # Idempotent re-scan: this entity already holds this item
                # under its OWN number. A mapping that points at some other
                # item's row is an ALIAS the dedup created; that is not this
                # branch, and it still earns its audit row below — a
                # duplicate recognised on a later scan is a duplicate.
                self.landed.add(prior)
                self.claimed.add(local)
                return prior

        candidate = qualify(ev["e_id"], self.token)
        tried: list[str] = []
        while candidate and candidate not in tried and len(tried) < self.MAX_MINT_ATTEMPTS:
            tried.append(candidate)
            self.cur.execute(
                """INSERT INTO evidence_index
                     (e_id, entity_id, origin, source_name, source_url, excerpt,
                      tier, claim_type, ers, published_date, reference_date)
                   VALUES (%s,%s,'package',%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING RETURNING e_id""",
                (candidate, self.entity_id, ev.get("source_name"), url, excerpt,
                 ev.get("tier"), claim_type, ev.get("ers"),
                 ev.get("published_date"), self.reference_date))
            if self.cur.fetchone():
                self.landed.add(candidate)
                if local:
                    self._map(local, candidate)
                    self.claimed.add(local)
                if prior:
                    # A mint exists only because this entity already holds
                    # this local id under different content: the same source,
                    # read again. Record the pair; the links the superseded
                    # row carries are carried over once this scan has written
                    # its own, so a link this package states keeps its basis.
                    self.superseded[candidate] = prior
                return candidate

            # The bare ON CONFLICT covers both uniques; work out which fired.
            self.cur.execute(
                f"""SELECT entity_id = %s,
                           content_hash IS NOT DISTINCT FROM {self.HASH_SQL}
                      FROM evidence_index WHERE e_id = %s""",
                (self.entity_id, url, claim_type, excerpt, candidate))
            row = self.cur.fetchone()
            if row is None:
                return self._dedup_branch(ev, candidate, local, url,
                                          claim_type, excerpt)
            same_entity, same_content = row
            if same_entity and same_content:
                # Idempotent re-scan of a package this entity already holds
                # under an id the mapping had not recorded (a row landed
                # before 0036, or by a pass that predates the mapping).
                self.landed.add(candidate)
                if local:
                    self._map(local, candidate)
                    self.claimed.add(local)
                return candidate

            # Same stored id, different content. Within this entity that is a
            # re-assessment reusing the local number — run-qualify it. Across
            # entities it is the collision this module exists to end: leave
            # the other institution's row untouched and mint under a suffix
            # drawn from THIS entity's uuid. NEVER alias to it.
            nxt = (f"{candidate}-R{self.run_seq}" if same_entity else
                   f"{qualify(ev['e_id'], self.token)}-{entity_suffix(self.entity_id)}")
            self._observe("evidence_id_collision",
                          {"package_local_id": ev["e_id"], "stored_id": candidate,
                           "same_entity": bool(same_entity), "retry": nxt})
            candidate = nxt

        self._observe("evidence_unpersistable",
                      {"package_local_id": ev["e_id"], "tried": tried})
        return None

    # ------------------------------------------------------------------
    def _dedup_branch(self, ev, candidate, local, url, claim_type,
                      excerpt):
        """No PK hit -> the (entity_id, content_hash) dedup index fired: this
        content already lives under another of this entity's ids. Map to it
        and record — never silently."""
        self.cur.execute(
            f"""SELECT e_id FROM evidence_index
                 WHERE entity_id = %s AND content_hash = {self.HASH_SQL}""",
            (self.entity_id, url, claim_type, excerpt))
        hit = self.cur.fetchone()
        if hit is None:
            # Neither lookup resolved: the insert conflicted on a constraint
            # this branch cannot attribute. Record it and drop THIS item —
            # one unattributable row must not sink a whole package, and a
            # silent alias to the wrong row would be worse than an absent
            # citation.
            self._observe("evidence_conflict_unresolved", {
                "package_local_id": ev["e_id"], "candidate": candidate,
                "has_url": bool(url), "has_excerpt": bool(excerpt),
                "reason": "ON CONFLICT fired but neither the e_id nor the "
                          "(entity_id, content_hash) lookup matched"})
            return None
        kept = hit[0]
        branch = "duplicate_within_run" if kept in self.landed else "dedup_same_entity"
        self.cur.execute(
            f"""INSERT INTO evidence_dedup_audit
                  (e_id, content_hash, branch, matched_e_id, occurred_at)
                VALUES (NULL, {self.HASH_SQL}, %s, %s, now())""",
            (url, claim_type, excerpt, branch, kept))
        self._observe("evidence_dedup", {"package_local_id": ev["e_id"],
                                         "incoming_e_id": candidate,
                                         "kept_e_id": kept, "branch": branch})
        if local:
            # Both local numbers must resolve to the row that was kept —
            # this is the many-to-one the mapping table exists to hold.
            self._map(local, kept)
            self.claimed.add(local)
        return kept


# --------------------------------------------------------------------------
# Measurement — read-only, and the reason the fix is shaped the way it is.
# --------------------------------------------------------------------------

_REPORT_SQL = {
    # Which entities share a stored-id namespace: the token sitting between
    # the E- and the number of each stored package id.
    "namespace_owners": """
        SELECT split_part(e_id, '-', 2) AS token,
               count(DISTINCT entity_id) AS entities,
               count(*) AS rows
          FROM evidence_index
         WHERE origin = 'package'
         GROUP BY 1 HAVING count(DISTINCT entity_id) > 1
         ORDER BY 2 DESC, 1
    """,
    # Runs whose entity holds no citable package evidence at all.
    "runs_without_package_evidence": """
        SELECT count(*) FROM runs r
         WHERE NOT EXISTS (SELECT 1 FROM evidence_index e
                            WHERE e.entity_id = r.entity_id
                              AND e.origin = 'package')
    """,
    "entities_without_package_evidence": """
        SELECT count(*) FROM entities en
         WHERE EXISTS (SELECT 1 FROM runs r WHERE r.entity_id = en.id)
           AND NOT EXISTS (SELECT 1 FROM evidence_index e
                            WHERE e.entity_id = en.id AND e.origin = 'package')
    """,
    # The ingest's own record of the collisions, per kind.
    "collision_observations": """
        SELECT kind, count(*) AS rows, count(DISTINCT run_id) AS runs
          FROM parser_observations
         WHERE kind IN ('evidence_id_collision', 'evidence_unpersistable',
                        'evidence_conflict_unresolved', 'manifest_absent',
                        'evidence_dedup', 'duplicate_package_local_id')
         GROUP BY 1 ORDER BY 2 DESC
    """,
    "null_fields": """
        SELECT count(*) FILTER (WHERE r.request_id IS NULL)      AS runs_no_request_id,
               count(*) FILTER (WHERE r.completed_at IS NULL)    AS runs_no_completed_at,
               count(*) FILTER (WHERE en.legal_name IS NULL)     AS runs_no_legal_name,
               count(*) FILTER (WHERE en.sub_vertical IS NULL)   AS runs_no_sub_vertical,
               count(*)                                          AS runs
          FROM runs r JOIN entities en ON en.id = r.entity_id
    """,
    "substrate": """
        SELECT (SELECT count(*) FROM document_sections)   AS document_sections,
               (SELECT count(*) FROM techstack_raw)       AS techstack_raw,
               (SELECT count(*) FROM platform_fits_raw)   AS platform_fits_raw,
               (SELECT count(*) FROM firmographics_raw)   AS firmographics_raw,
               (SELECT count(*) FROM recommendations_raw) AS recommendations_raw,
               (SELECT count(*) FROM peer_scores)         AS peer_scores,
               (SELECT count(*) FROM evidence_index WHERE origin='package')
                                                          AS package_evidence,
               (SELECT count(*) FROM evidence_subcap_links) AS evidence_links
    """,
    "runs_without_sections": """
        SELECT count(*) FROM runs r
         WHERE NOT EXISTS (SELECT 1 FROM document_sections d WHERE d.run_id = r.id)
    """,
    "unlinked_scores": """
        SELECT count(*) FILTER (WHERE linked_evidence_count = 0) AS zero,
               count(*) FILTER (WHERE linked_evidence_count IS NULL) AS null_count,
               count(*) AS scores
          FROM subcap_scores
    """,
}


def _rows(cur, sql, args=()):
    cur.execute(sql, args)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def namespace_report(conn, probe_runs: list | None = None) -> dict:
    """Everything the defect needs measured, in one read-only pass."""
    cur = conn.cursor()
    out: dict = {}
    for name, sql in _REPORT_SQL.items():
        rows = _rows(cur, sql)
        out[name] = rows if len(rows) != 1 or len(rows[0]) > 1 else \
            list(rows[0].values())[0]

    # Does the mapping exist yet? The report runs on both sides of 0036.
    cur.execute("""SELECT count(*) FROM information_schema.tables
                    WHERE table_name = 'evidence_package_ids'""")
    out["mapping_table"] = bool(cur.fetchone()[0])
    if out["mapping_table"]:
        cur.execute("""SELECT count(*) AS mapped,
                              count(DISTINCT entity_id) AS entities
                         FROM evidence_package_ids""")
        mapped, entities = cur.fetchone()
        out["package_ids_mapped"] = mapped
        out["entities_with_mapped_ids"] = entities

    for run_id in (probe_runs or []):
        out.setdefault("probes", {})[str(run_id)] = probe_run(cur, run_id)
    return out


def probe_run(cur, run_id) -> dict:
    """One run, end to end: identity, substrate and what its own citations
    resolve to."""
    cur.execute(
        """SELECT r.entity_id, r.request_id, r.run_seq, r.completed_at,
                  r.source_folder_id, en.display_id, en.legal_name,
                  en.sub_vertical, en.status
             FROM runs r JOIN entities en ON en.id = r.entity_id
            WHERE r.id = %s""", (run_id,))
    row = cur.fetchone()
    if row is None:
        return {"error": "unknown_run"}
    entity_id = row[0]
    cur.execute("""SELECT count(*) FROM evidence_index
                    WHERE entity_id = %s AND origin = 'package'""", (entity_id,))
    own = cur.fetchone()[0]
    cur.execute("""SELECT count(*) FROM evidence_package_ids WHERE entity_id = %s""",
                (entity_id,))
    mapped = cur.fetchone()[0]
    cur.execute("""SELECT kind, count(*) FROM parser_observations
                    WHERE run_id = %s GROUP BY 1 ORDER BY 2 DESC""", (run_id,))
    obs = {k: n for k, n in cur.fetchall()}
    cur.execute("SELECT count(*) FROM document_sections WHERE run_id = %s", (run_id,))
    sections = cur.fetchone()[0]
    cur.execute("""SELECT count(*) FILTER (WHERE linked_evidence_count > 0),
                          count(*) FROM subcap_scores WHERE run_id = %s""", (run_id,))
    linked, scores = cur.fetchone()
    return {
        "entity_id": str(entity_id), "display_id": row[5], "legal_name": row[6],
        "sub_vertical": row[7], "status": row[8], "request_id": row[1],
        "run_seq": row[2], "completed_at": str(row[3]) if row[3] else None,
        "source_folder_id": row[4],
        "package_evidence_rows_for_entity": own,
        "package_local_ids_mapped": mapped,
        "document_sections": sections,
        "scores": scores, "scores_with_linked_evidence": linked,
        "parser_observations": obs,
    }
