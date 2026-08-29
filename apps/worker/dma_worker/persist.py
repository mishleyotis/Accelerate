"""Persist a parsed package into the ingested tier (stage 1.3, TRD §07
steps 4–9). Read-only from the moment the run is queued.

Rules enforced here:
- Entity identity comes from the cascade (the manifest is signal 1).
- The run pins the manifest's taxonomy version; catalogue_cells is
  denormalised from that pinned version's ccg_versions row.
- The composite is rounded ONCE, here, at 2dp (the workbook value is raw;
  presentation rounds to 1dp downstream — never twice).
- Scores land with source_cell and all four grain ids; linked evidence
  counts stay NULL until the linker runs (computed or null, never a
  default that looks like data).
- Where the manifest and the workbook disagree on a figure, the higher
  priority artefact (the workbook) wins and the disagreement is recorded
  as a parser observation — never silently reconciled.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .counts import recount_run
from .entity_resolution import DMA_ASM, resolve
from .evidence_ids import EvidenceLander
from .workbook_parser import (WorkbookParse, excerpt_clip,
                              mine_evidence_from_rationales)

# The content-hash recompute that finds the kept row after the (entity_id,
# content_hash) dedup index rejects an insert now lives with the landing rules
# it belongs to: EvidenceLander.HASH_SQL in dma_worker/evidence_ids.py.


def _institution(manifest: dict) -> dict:
    """Normalise the manifest's identity block. The shipped corpus is
    heterogeneous — every synthesis run authored its own manifest schema:
    institution as an object, as a bare string, or absent with the name
    under entity / entity_name / institution_name (entity itself object
    or string). One choke point resolves them all; nothing downstream
    guesses."""
    inst = manifest.get("institution")
    d = dict(inst) if isinstance(inst, dict) else (
        {"name": inst.strip()} if isinstance(inst, str) and inst.strip() else {})
    if not d.get("name"):
        for key in ("entity_name", "institution_name"):
            v = manifest.get(key)
            if isinstance(v, str) and v.strip():
                d["name"] = v.strip()
                break
        else:
            e = manifest.get("entity")
            if isinstance(e, str) and e.strip():
                d["name"] = e.strip()
            elif isinstance(e, dict):
                for key in ("name", "legal_name", "entity_name"):
                    v = e.get(key)
                    if isinstance(v, str) and v.strip():
                        d["name"] = v.strip()
                        break
                for key in ("sub_vertical", "subvertical", "size_tier",
                            "primary_regulator", "geography"):
                    if not d.get(key) and isinstance(e.get(key), str):
                        d[key] = e[key]
    for key, aliases in (("sub_vertical", ("sub_vertical", "subvertical",
                                           "subvertical_initial")),
                         ("size_tier", ("size_tier",))):
        if not d.get(key):
            for a in aliases:
                v = manifest.get(a)
                if isinstance(v, str) and v.strip():
                    d[key] = v.strip()
                    break
    return d


def _stated_overall(manifest: dict):
    """The manifest's STATED overall score — read, never derived. Shapes
    seen in the corpus: scores.overall (canonical) and a top-level
    overall_score."""
    sc = manifest.get("scores")
    v = sc.get("overall") if isinstance(sc, dict) else None
    if v is None:
        v = manifest.get("overall_score")
    return v if isinstance(v, (int, float)) else None


_ISOISH = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _stated_completed_at(manifest: dict):
    """The assessment's stated completion moment, tolerant of the corpus's
    key variants; anything not ISO-shaped is dropped (computed or null —
    a mangled date must not sink the package or masquerade as data).

    Last resort: the request id's OWN date token. The corpus names every run
    `DMA-ASM-<ENTITY>-<YYYYMMDD>-<seq>`, so `DMA-ASM-BCU-20260330-0001` states
    2026-03-30 as plainly as a manifest field would — it is read, not guessed.
    Reading it matters far beyond a header line: `completed_at` becomes each
    evidence row's `reference_date`, and with that null the GENERATED
    `age_months` is null and `recency_band` falls to UNVERIFIED for EVERY item.
    the reference client served 120 items, 45 of them dated, and all 120 banded UNVERIFIED —
    which is why a FACT rendered beside an "unverified" label. The ladder, the
    freshness dot and the age contribution to ERS all depend on this one field.
    """
    a = manifest.get("assessment")
    candidates = [a.get("date") if isinstance(a, dict) else None,
                  manifest.get("assessment_date"), manifest.get("completed_at"),
                  manifest.get("generated_at"), manifest.get("execution_timestamp"),
                  manifest.get("last_updated")]
    for c in candidates:
        if isinstance(c, str) and _ISOISH.match(c.strip()):
            return c.strip()
    return _request_id_date(manifest)


_REQ_ID_DATE = re.compile(r"-(\d{4})(\d{2})(\d{2})-\d+\s*$")


def _request_id_date(manifest: dict):
    """The YYYYMMDD token in a `DMA-ASM-…-YYYYMMDD-NNNN` request id, as a date.

    Validated by construction: an impossible month or day yields None rather
    than a string the DATE column would reject and abort the package on.
    """
    m = _REQ_ID_DATE.search(str(manifest.get("run_id") or "").strip().upper())
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _entity_token(manifest: dict) -> str:
    """The token that qualifies this package's local ids globally."""
    m = DMA_ASM.match(str(manifest.get("run_id", "")).strip().upper())
    if m:
        return m.group("entity")
    name = _institution(manifest).get("name") or ""
    return re.sub(r"[^A-Z0-9]", "", name.upper())[:8] or "UNK"


# The basis a carried link is written under. It is not 'package': the package
# did not state this link for this row, an earlier read of the same source did,
# and a reader who drills in is owed the difference.
CARRIED_BASIS = "carried_from_superseded"


def carry_links_across_remint(cur, superseded: str, minted: str) -> int:
    """A re-mint is the SAME SOURCE, read again — carry what the row it
    supersedes already knows. Returns the number of links carried.

    `_land_evidence` mints a run-qualified id (`E-XXX-006-R2`) when a second
    scan re-lands a package-local id whose CONTENT changed: a fuller excerpt, a
    published date, an ERS the first scan had none of. The copy is the better
    row and it is the one the surfaces cite. It used to arrive with no cell
    links at all, so a citation of it opened a drawer that could not say which
    cells the source supports, while the earlier run's linkage sat on an id
    nobody reads any more. Measured on one client: 36 such rows, 30 of them
    cited by the promoted run, every one of them linkless under it.

    Links are an assertion about the SOURCE, not about the excerpt, so they
    survive a re-read of that source — INCLUDING the links of runs other than
    this one. Carrying those is the whole point: it is what makes an earlier
    run's citation of the new id resolve to the cells it supports.

    Nothing about the content is touched. Only two things move:

      · the links, preserving their own `run_id`, under a basis that says
        where they came from, and never over one the copy already has —
        and they MOVE, they are not copied. The first version of this
        function left the superseded row's links in place, so one document
        read twice reached every one of its subcaps twice: measured on the
        reference client, E-XXX-012 and its -R2 twin each reached 191
        subcaps, and every one of those cells counted the same source as
        two items toward the `<3` thin-evidence line. The superseded row
        itself is retained — an old payload's citation of it still
        resolves — but a superseded row that still LINKS is two rows
        voting with one document's voice;
      · the grading the re-scan does not restate (specificity, corroboration,
        identity), and only into NULLs — a value the new row states is the
        measured one and always wins.
    """
    cur.execute(
        f"""INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
            SELECT %s, k.subcap_id, k.run_id, '{CARRIED_BASIS}'
              FROM evidence_subcap_links k
             WHERE k.e_id = %s
            ON CONFLICT DO NOTHING""",
        (minted, superseded))
    carried = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    # The move's second half: a carried link exists on the minted row now,
    # so the superseded row's copy comes off. Only links the mint actually
    # holds are removed — a link that failed to carry is not deleted.
    cur.execute(
        """DELETE FROM evidence_subcap_links k
            WHERE k.e_id = %s
              AND EXISTS (SELECT 1 FROM evidence_subcap_links m
                           WHERE m.e_id = %s AND m.subcap_id = k.subcap_id
                             AND m.run_id = k.run_id)""",
        (superseded, minted))
    cur.execute(
        """UPDATE evidence_index fresh
              SET specificity   = COALESCE(fresh.specificity, prior.specificity),
                  corroboration = COALESCE(fresh.corroboration, prior.corroboration),
                  identity_ok   = COALESCE(fresh.identity_ok, prior.identity_ok),
                  identity_note = COALESCE(fresh.identity_note, prior.identity_note)
             FROM evidence_index prior
            WHERE fresh.e_id = %s AND prior.e_id = %s
              AND fresh.entity_id = prior.entity_id""",
        (minted, superseded))
    # The move's third half, and the one this function shipped without (0046).
    # Retaining the superseded row so "an old payload's citation of it still
    # resolves" is only true if something says WHERE it resolves to. Without
    # this pointer the retained row is reachable and empty, and ET-07 refuses
    # every citation of it — measured corpus-wide after 0043: 4,366 bare ids
    # carrying no links, 7 of 7 blocking the first page that was resubmitted,
    # 7 of 7 with a twin holding between 6 and 141 of them.
    cur.execute(
        """UPDATE evidence_index SET superseded_by = %s
            WHERE e_id = %s AND coalesce(superseded_by, '') <> %s""",
        (minted, superseded, minted))
    return carried


@dataclass
class PersistResult:
    entity_id: str
    run_id: str
    run_seq: int
    scored_cells: int
    observations: int


def _slug(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")[:60]


def _round_once(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def persist_package(conn, *, manifest: dict, workbook: WorkbookParse,
                    source_folder_id: str, evidence: list | None = None,
                    peers: list | None = None,
                    recommendations: list | None = None,
                    artefact_id: str | None = None,
                    sections: list | None = None,
                    report_artefact_id: str | None = None,
                    grains: dict | None = None,
                    research: dict | None = None,
                    companion_observations: list | None = None,
                    artefact_checksum: str | None = None,
                    remint: bool = False) -> PersistResult:
    cur = conn.cursor()
    inst = _institution(manifest)
    # Signal 4 of the cascade: the client folder's display name (its
    # " - DMA" suffix dropped). Lowest confidence — resolves to a
    # PENDING_REVIEW entity, never an active one.
    folder_display = re.sub(r"\s*-\s*DMA\s*$", "",
                            str(source_folder_id or "")).strip() or None
    resolution = resolve(
        manifest_identity=inst.get("name"),
        request_id=manifest.get("run_id"),
        document_header=None,
        folder_name=folder_display,
    )
    if resolution is None:
        raise ValueError("package carries no resolvable identity")

    display_id = _slug(inst.get("name") or resolution.entity_token)
    cur.execute("SELECT id FROM entities WHERE display_id = %s", (display_id,))
    row = cur.fetchone()
    if row:
        entity_id = row[0]
    else:
        cur.execute(
            """INSERT INTO entities (display_id, legal_name, sub_vertical, size_tier,
                                     primary_regulator, jurisdictions, status,
                                     inference_confidence, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now()) RETURNING id""",
            (display_id, inst.get("name"), inst.get("sub_vertical"),
             inst.get("size_tier"), inst.get("primary_regulator"),
             [inst["geography"]] if inst.get("geography") else None,
             resolution.status, resolution.confidence),
        )
        entity_id = cur.fetchone()[0]

    # Pin the catalogue version the assessment was scored against. Corpus
    # variants: versions.taxonomy (canonical) or a top-level
    # framework_version; only version-shaped values are considered, and
    # the pin lands only when the version actually exists (FK) — an
    # unknown version is recorded as an observation, never a crash.
    versions = manifest.get("versions")
    taxonomy = (str(versions.get("taxonomy", "")).strip()
                if isinstance(versions, dict) else "")
    if not taxonomy:
        fv = manifest.get("framework_version")
        fv = str(fv).strip() if isinstance(fv, (str, int, float)) else ""
        taxonomy = fv if re.match(r"^v?\d+(\.\d+)?$", fv) else ""
    pinned = taxonomy if taxonomy.startswith("v") else (f"v{taxonomy}" if taxonomy else None)
    catalogue_cells = None
    unknown_version = None
    if pinned:
        cur.execute("SELECT cell_count FROM ccg_versions WHERE version = %s", (pinned,))
        r = cur.fetchone()
        if r:
            catalogue_cells = r[0]
        else:
            unknown_version, pinned = pinned, None

    # A package that states no taxonomy version still scored against ONE of
    # them, and the cells it scored say which. Left unpinned, the serving
    # view joins the catalogue on the CURRENT version and matches nothing —
    # BCU's 17-category v5-shaped run served 765 cells with 0 names, which is
    # the whole heatmap. So infer the pin from the ids themselves: the version
    # that recognises most of them wins, above a floor, and the inference is
    # recorded with its coverage rather than passing as a stated fact.
    inferred_pin = None
    if pinned is None:
        scored_ids = sorted({s.subcap_id for s in workbook.scores})
        if scored_ids:
            cur.execute(
                """SELECT version, count(*) FROM ccg_subcaps
                    WHERE subcap_id = ANY(%s)
                    GROUP BY version ORDER BY count(*) DESC, version DESC""",
                (scored_ids,))
            ranked = cur.fetchall() or []
            if ranked:
                top, hits = ranked[0][0], ranked[0][1]
                coverage = hits / len(scored_ids)
                runner = ({"version": ranked[1][0],
                           "coverage": round(ranked[1][1] / len(scored_ids), 3)}
                          if len(ranked) > 1 else None)
                if coverage >= 0.6:
                    pinned = top
                    cur.execute(
                        "SELECT cell_count FROM ccg_versions WHERE version = %s", (top,))
                    r = cur.fetchone()
                    catalogue_cells = r[0] if r else None
                inferred_pin = {"chosen": pinned, "candidate": top,
                                "coverage": round(coverage, 3),
                                "cells_recognised": hits,
                                "cells_scored": len(scored_ids),
                                "runner_up": runner,
                                "basis": "scored cell ids matched against each "
                                         "catalogue version; floor 0.60",
                                "reason": None if coverage >= 0.6 else
                                          "no version recognises enough of the "
                                          "scored cells; run left unpinned"}

    # Idempotence, and the reason it needs its own columns: `_requeue` blanks
    # the artefact's stored checksum so a failed package rescans, which makes
    # a byte-identical workbook look CHANGED on the next firing. Without a
    # record of WHICH artefact produced a run and what its bytes were, every
    # such retry minted a second run for the same package — six entities in
    # production carry duplicates that way. A deliberate re-ingest
    # (FORCE_FOLDER, after a parser fix) passes remint=True and still mints.
    # KEYED ON CONTENT, NOT ON THE FILE'S NAME IN DRIVE.
    #
    # This used to require `source_artefact_id` to match as well, and
    # `artefact_id` is the DRIVE FILE ID. Re-uploading a workbook — delete and
    # upload again, which is what people do — mints a new file id for the same
    # bytes, so the guard could not match, and a byte-identical assessment
    # ingested as a second run.
    #
    # Measured 2026-08-16 in production: 286 pending runs across 171 entities,
    # 105 of them carrying more than one. One entity holds three runs at
    # run_seq 1, 2 and 3 with the same request id, the same composite (1.63),
    # the same 120 scored cells and the same completed_at — the same
    # assessment, three times. The same scan reported "130 artefact(s) seen
    # before and absent now", which is the replaced-file signature.
    #
    # A byte-identical workbook for the same entity IS the same assessment,
    # whatever Drive calls the file today. Two genuinely different assessments
    # cannot collide here: they differ in dates and ids, so they differ in
    # bytes. `remint=True` (FORCE_FOLDER, after a parser fix) still bypasses
    # this entirely and mints deliberately.
    if artefact_id and artefact_checksum and not remint:
        cur.execute(
            """SELECT id, run_seq, scored_cells FROM runs
                WHERE entity_id = %s AND source_checksum = %s
                ORDER BY run_seq DESC LIMIT 1""",
            (entity_id, artefact_checksum))
        prior = cur.fetchone()
        if prior:
            conn.commit()
            return PersistResult(str(entity_id), str(prior[0]), prior[1],
                                 prior[2] or 0, 0)

    # AUD-0089: this was an unguarded read-modify-write. The only
    # serialisation was `pg_try_advisory_lock(815002)` in job_main.main(),
    # which exists inside the worker Job and nowhere else — so a backfill, a
    # remint, a manual repair or a second revision mid-deploy raced it, and
    # the collision was SILENT: two runs for one entity on the same run_seq,
    # after which `serving_directory (entity_id, run_seq DESC)` resolves to
    # whichever row the planner reached first.
    #
    # Two changes, and the second is the one that holds. The ENTITY row is
    # locked before the maximum is read, which serialises concurrent
    # allocators for this entity and no others — `FOR UPDATE` cannot be
    # applied to the aggregate itself, and locking the entity is both legal
    # and narrower than an advisory lock over the whole ingest. Migration
    # 0056's partial unique index on (entity_id, run_seq) is the guarantee:
    # it makes a collision FAIL rather than persist, in every writer
    # including ones not yet written.
    cur.execute("SELECT id FROM entities WHERE id = %s FOR UPDATE",
                (entity_id,))
    cur.execute("SELECT COALESCE(max(run_seq), 0) + 1 FROM runs "
                "WHERE entity_id = %s", (entity_id,))
    run_seq = cur.fetchone()[0]
    composite = _round_once(workbook.composite)   # rounded ONCE
    composite_from_manifest = False
    stated_overall = _stated_overall(manifest)
    if composite is None and stated_overall is not None:
        # The workbook generation carries no composite figure; the manifest's
        # stated overall is READ (not derived), with its provenance recorded.
        composite = _round_once(Decimal(str(stated_overall)))
        composite_from_manifest = True
    cur.execute(
        """INSERT INTO runs (entity_id, request_id, run_seq, ccg_catalog_version,
                             scored_cells, catalogue_cells, composite, status,
                             completed_at, source_folder_id,
                             source_artefact_id, source_checksum)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'INGESTED',%s,%s,%s,%s) RETURNING id""",
        (entity_id, manifest.get("run_id"), run_seq, pinned,
         len({s.subcap_id for s in workbook.scores}), catalogue_cells, composite,
         _stated_completed_at(manifest), source_folder_id,
         artefact_id, artefact_checksum),
    )
    run_id = cur.fetchone()[0]

    # The payload wraps the manifest artefact with the workbook's STATED
    # pillar/category grains (Pillar_Summary / Category_Detail): the
    # ingested tier has no stated-grain table, H4's grain lock needs the
    # stated rows server-side, and run_manifest is the run's one-to-one
    # JSONB home. Readers take payload["manifest"].
    cur.execute("INSERT INTO run_manifest (run_id, payload) VALUES (%s, %s)",
                (run_id, json.dumps({"manifest": manifest,
                                     "workbook_grains": grains or None})))
    n_obs = 0
    if composite_from_manifest:
        cur.execute(
            """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
               VALUES (%s,'composite_from_manifest',%s, now())""",
            (run_id, json.dumps({"value": str(composite),
                                 "reason": "workbook carries no composite figure"})))
        n_obs += 1
    if unknown_version:
        cur.execute(
            """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
               VALUES (%s,'unknown_catalogue_version',%s, now())""",
            (run_id, json.dumps({"stated": unknown_version,
                                 "reason": "manifest pins a version ccg_versions "
                                           "does not carry; run left unpinned"})))
        n_obs += 1
    if inferred_pin:
        cur.execute(
            """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
               VALUES (%s,'catalogue_version_inferred',%s, now())""",
            (run_id, json.dumps(inferred_pin)))
        n_obs += 1
    if not manifest:
        cur.execute(
            """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
               VALUES (%s,'manifest_absent',%s, now())""",
            (run_id, json.dumps({
                "source_folder_id": source_folder_id,
                "reason": "package ships no manifest: identity from the folder "
                          "name (cascade signal 4, PENDING_REVIEW), scores from "
                          "the workbook, no stated overall and no pinned version"})))
        n_obs += 1

    reference_date = _stated_completed_at(manifest)
    token = _entity_token(manifest)
    seen_links = set()
    alias: dict[str, str] = {}   # package-local e_id -> the row it resolves to

    def _observe(kind: str, detail: dict) -> None:
        nonlocal n_obs
        cur.execute(
            """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
               VALUES (%s,%s,%s, now())""", (run_id, kind, json.dumps(detail)))
        n_obs += 1

    # The landing rules live in one place (dma_worker.evidence_ids), shared
    # with the repair pass that re-lands what the id collision left
    # unpersistable: a repair landing evidence by a second set of rules would
    # be a second thing to get wrong.
    lander = EvidenceLander(cur, entity_id=entity_id, run_id=run_id,
                            run_seq=run_seq, token=token,
                            reference_date=reference_date, observe=_observe)

    def _carry_forward() -> None:
        # minted id -> the id it supersedes, filled while landing and drained
        # once every package link has been written, so a link this scan states
        # keeps its own basis and only the gaps are carried.
        for minted, superseded in sorted(lander.superseded.items()):
            carried = carry_links_across_remint(cur, superseded, minted)
            _observe("evidence_links_carried_forward",
                     {"superseded": superseded, "minted": minted,
                      "links_carried": carried})

    # The general_dma Evidence_Master ships a Fact_Count but no fact TEXT; the
    # verbatim excerpts live in the scoring tabs' Rationale, tagged per
    # evidence id. Mine them and fill in what the ledger left blank — an
    # evidence row with no excerpt reaches the evidence drawer empty, and a
    # citation the reader cannot read is not a citation (invariant 4). The
    # ledger still wins where it carries its own text.
    mined = mine_evidence_from_rationales(workbook.scores)
    if mined:
        _observe("evidence_excerpts_mined", {
            "source": "P*_Subcap_Scoring.Rationale tagged fragments",
            "ids_with_excerpt": sum(1 for v in mined.values() if v.get("excerpt")),
            "ids_seen": len(mined)})

    # The research workbook's Evidence_Linkage_Matrix is the ledger of record:
    # it carries ERS and a publication date for every item, which the scoring
    # workbook's Evidence_Master omits entirely (0 of 82 for BCU), and a
    # verbatim passage per fact rather than a scraped fragment. It wins on
    # those fields; the master still names the source.
    rledger: dict = {}
    for item in ((research or {}).get("ledger") or []):
        if item["e_id"] in rledger:
            # The same local id reused for a different source is a source-data
            # defect, not something to reconcile silently.
            _observe("research_ledger_duplicate_id", {"e_id": item["e_id"]})
            continue
        rledger[item["e_id"]] = item
    if rledger:
        _observe("research_workbook_ledger", {
            "rows": len(rledger),
            "with_ers": sum(1 for x in rledger.values() if x.get("ers") is not None),
            "with_published_date": sum(1 for x in rledger.values() if x.get("published_date")),
            "with_excerpt": sum(1 for x in rledger.values() if x.get("excerpt"))})

    # WHICH SOURCE'S SPANS ARE LESS DAMAGED — decided once over the whole
    # corpus, not per row, because a single string cannot reveal the width it
    # was cut at.
    #
    # Measured on T. Rowe Price's real package, 2026-08-24. The scoring
    # workbook's ledger offers excerpts clipped at 140 per clause and joined
    # with " | "; the research workbook's Evidence_Detail offers them clipped
    # at 480. By LENGTH the two are indistinguishable — 426 characters against
    # 434 — and the ingest that picked by length picked either. But the 426 is
    # THREE cuts and reads "…live in T. Row | Technog", while the 434 is one
    # span and reads as a sentence. Three fragments totalling more characters
    # carry LESS of the source, and a producer reading the fragments is the
    # exact mechanism of MEM-0129: nine products named that the citable spans
    # do not contain.
    #
    # What actually reached the client before this: 1,964 of 2,063 served
    # evidence items on the promoted heatmap cut mid-word, while the
    # 480-character source sat in the same package unread.
    led_sig = excerpt_clip.clip_signature(
        [e.get("excerpt") for e in (evidence or [])])
    res_sig = excerpt_clip.clip_signature(
        [x.get("excerpt") for x in rledger.values()])
    research_wins = excerpt_clip.prefer(led_sig, res_sig) > 0
    if led_sig["verdict"] == "CLIPPED" or res_sig["verdict"] == "CLIPPED":
        _observe("excerpt_source_chosen_by_clip_severity", {
            "ledger": {k: led_sig.get(k) for k in
                       ("verdict", "width", "clipped", "total_clauses")},
            "research": {k: res_sig.get(k) for k in
                         ("verdict", "width", "clipped", "total_clauses")},
            "chose": "research_workbook" if research_wins else "scoring_ledger",
            "reason": "an unclipped corpus beats a clipped one, and among "
                      "clipped corpora the WIDER cut keeps more of each "
                      "sentence. Length is the wrong criterion and was "
                      "measured to be: 426 characters of three 140-cuts "
                      "against 434 of one 480-cut, indistinguishable by "
                      "length and not remotely equivalent to read."})

    for ev in (evidence or []):
        r = rledger.get(ev["e_id"]) or {}
        # authoritative-where-present, never overwriting a stated value with a
        # blank one
        for field in ("ers", "published_date", "stated_recency", "tier",
                      "fact_count", "claim_type"):
            if r.get(field) is not None and ev.get(field) is None:
                ev = {**ev, field: r[field]}
        # The ingest path and the repair job disagreed about these two, and
        # only the repair job was right. `Evidence_Master` hard-caps
        # Source_Name at 40 characters and URL at 50 — measured, 119 of 127
        # names and 89 of 127 URLs sat at exactly the cap on one package —
        # while the research matrix caps at 60/80. So "longer" is never a
        # different value, it is more of the same one, and a URL cut
        # mid-path resolves for nobody while its 80-character copy is
        # complete. A run that was never hand-repaired kept the truncated
        # URL even though the research workbook was carrying the whole one.
        for field in ("source_name", "source_url"):
            if r.get(field) and len(r[field]) > len(ev.get(field) or ""):
                ev = {**ev, field: r[field]}
        # A verbatim 50-500 char passage beats a mined fragment; between two
        # verbatim ones, the corpus comparison above decides. Either source
        # still fills in for the other where it has nothing — a preference is
        # not a reason to serve an empty drawer.
        if r.get("excerpt") and (research_wins or not ev.get("excerpt")):
            ev = {**ev, "excerpt": r["excerpt"]}
        m = mined.get(ev["e_id"]) or {}
        if not ev.get("excerpt") and m.get("excerpt"):
            ev = {**ev, "excerpt": m["excerpt"]}
        if not ev.get("subcaps") and m.get("subcaps"):
            # The ledger's SubCaps column carries corpus tokens like
            # ENTITY_PROFILE rather than cell ids; the cells that actually
            # cite this item are the ones the drawer should link to.
            ev = {**ev, "subcaps": m["subcaps"]}
        resolved = lander.land(ev)
        alias[ev["e_id"]] = resolved
        if resolved is None:
            continue
        for sid in ev.get("subcaps", []):
            key = (resolved, sid)
            if key not in seen_links:
                seen_links.add(key)
                cur.execute(
                    """INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
                       VALUES (%s,%s,%s,'package') ON CONFLICT DO NOTHING""",
                    (resolved, sid, run_id))

    # The research workbook links each cell to the FACTS that support it, which
    # is finer than the scoring row's five-per-cell citation and is what makes
    # a cell's drawer specific rather than category-wide. Linked here so the
    # basis is visible: 'research_workbook' says a human mapped this fact to
    # this cell, which outranks a proximity link.
    rlinks = (research or {}).get("links") or []
    if rlinks:
        landed_links = 0
        for link in rlinks:
            for e_id in link.get("e_ids", []):
                resolved = alias.get(e_id)
                if not resolved:
                    continue
                key = (resolved, link["subcap_id"])
                if key in seen_links:
                    continue
                seen_links.add(key)
                cur.execute(
                    """INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
                       VALUES (%s,%s,%s,'research_workbook') ON CONFLICT DO NOTHING""",
                    (resolved, link["subcap_id"], run_id))
                landed_links += 1
        _observe("research_workbook_links", {
            "cells": len({l["subcap_id"] for l in rlinks}),
            "links_written": landed_links,
            "cells_with_verbatim_excerpt": sum(1 for l in rlinks if l.get("excerpts"))})
    # The assessment's own absence register: which cells were searched, how
    # hard, and the highest tier reached. A thin cell without this is an
    # absence with no recorded search.
    rabsent = (research or {}).get("absent") or []
    if rabsent:
        _observe("research_workbook_absences", {
            "rows": len(rabsent),
            "cells": [a["subcap_id"] for a in rabsent][:40],
            "reasons": sorted({a.get("reason") for a in rabsent if a.get("reason")})})

    seen_subcaps: set[str] = set()
    for s in workbook.scores:
        if s.subcap_id in seen_subcaps:
            # A workbook that states the same subcap twice: the FIRST row
            # wins (reading order), the repeat is recorded — never a
            # unique-violation crash, never a silent overwrite.
            _observe("duplicate_subcap_row",
                     {"subcap_id": s.subcap_id, "source_cell": s.source_cell,
                      "skipped_score": str(s.score)})
            continue
        seen_subcaps.add(s.subcap_id)
        cur.execute(
            """INSERT INTO subcap_scores
                 (run_id, subcap_id, capability_id, category_id, pillar_id,
                  score, confidence, source_cell)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (run_id, s.subcap_id, s.capability_id, s.category_id, s.pillar_id,
             s.score, s.confidence, s.source_cell),
        )

    if evidence:
        for s in workbook.scores:
            for e_id in s.evidence_refs:
                # Score rows cite package-LOCAL ids; only refs that resolved
                # to a stored row become links (a ref to an id the package
                # never carried is the evidence pass's problem, not a link).
                resolved = alias.get(e_id)
                if resolved and (resolved, s.subcap_id) not in seen_links:
                    seen_links.add((resolved, s.subcap_id))
                    cur.execute(
                        """INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
                           VALUES (%s,%s,%s,'score_row') ON CONFLICT DO NOTHING""",
                        (resolved, s.subcap_id, run_id))
        # Every link THIS scan states is now written, so anything the
        # superseded row still carries alone is a gap rather than a
        # competing basis — carry it, and only then count.
        _carry_forward()
        # The linker counts — written only now that both sides of the join
        # exist. The linker ran for this run, so an unlinked cell's count is
        # a computed zero; NULL is reserved for runs the linker never saw.
        recount_run(cur, run_id)

    # The scoring workbook's own observations, plus everything the companion
    # tabs could not read. A tab whose shape the parser does not recognise
    # lands as a NAMED row here rather than as an absent section — that is
    # what makes "why is this client's cohort empty" answerable without
    # opening the workbook.
    for o in list(workbook.observations) + list(companion_observations or []):
        cur.execute(
            """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
               VALUES (%s,%s,%s, now())""",
            (run_id, o.kind, json.dumps({"subcap_id": o.subcap_id, **o.detail})),
        )
        n_obs += 1

    # Peer cohort: only the named-peer scores are data. The tab's stated
    # median is read to VERIFY (recomputed from the very scores beside it);
    # a material disagreement is an observation, and nothing derivable is
    # stored (counts are computed, never stored).
    for p in (peers or []):
        scores = sorted(s for _, s in p["peers"] if s is not None)
        for peer_name, score in p["peers"]:
            cur.execute(
                """INSERT INTO peer_scores (run_id, peer_name, category_id, score)
                   VALUES (%s,%s,%s,%s)""",
                (run_id, peer_name, p["category_id"], score))
        if scores and p.get("stated_median") is not None:
            n = len(scores)
            mid = (scores[n // 2] if n % 2 else
                   (scores[n // 2 - 1] + scores[n // 2]) / 2)
            if abs(mid - p["stated_median"]) > Decimal("0.005"):
                _observe("artefact_disagreement", {
                    "figure": f"peer_median[{p['category_id']}]",
                    "stated": str(p["stated_median"]), "recomputed": str(mid),
                    "resolution": "recomputed from named-peer scores; stated value not stored"})

    for rec in (recommendations or []):
        cur.execute(
            """INSERT INTO recommendations_raw (run_id, rec_id, payload, artefact_id)
               VALUES (%s,%s,%s,%s)""",
            (run_id, rec["rec_id"], json.dumps(rec["payload"]), artefact_id))

    # The twelve structured report sections, at subsection grain. `page`
    # comes through as-parsed (None from a .docx — computed or null).
    for sec in (sections or []):
        cur.execute(
            """INSERT INTO document_sections
                 (run_id, section_kind, pillar_id, heading, body, page, artefact_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (run_id, sec.section_kind, sec.pillar_id, sec.heading, sec.body,
             sec.page, report_artefact_id))

    # Manifest-vs-workbook figure check: the workbook (priority 1) wins;
    # a material disagreement is an observation, never silently reconciled.
    m_overall = _stated_overall(manifest)
    if m_overall is not None and composite is not None and not composite_from_manifest:
        if abs(Decimal(str(m_overall)) - composite) > Decimal("0.005"):
            cur.execute(
                """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
                   VALUES (%s,'artefact_disagreement',%s, now())""",
                (run_id, json.dumps({
                    "figure": "composite", "workbook": str(composite),
                    "manifest": str(m_overall),
                    "resolution": "workbook wins (artefact priority 1)"})),
            )
            n_obs += 1

    conn.commit()
    return PersistResult(str(entity_id), str(run_id), run_seq,
                         len(seen_subcaps), n_obs)
