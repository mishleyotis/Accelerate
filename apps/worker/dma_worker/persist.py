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
from decimal import Decimal, ROUND_HALF_UP

from .entity_resolution import DMA_ASM, resolve
from .workbook_parser import WorkbookParse, mine_evidence_from_rationales

# Mirrors CONTENT_HASH_EXPR in migrations/versions/0005_ingested_tier.py with
# claim_type NULL (the package path never asserts a claim type). Used to find
# the kept row after the (entity_id, content_hash) dedup index rejects an
# insert — the recompute must stay byte-identical to the generated column.
_HASH_SQL = r"""encode(digest(coalesce(%s,'') || '|' || '' || '|' ||
                lower(left(regexp_replace(%s,'\s+',' ','g'),500)),
         'sha256'),'hex')"""


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
    a mangled date must not sink the package or masquerade as data)."""
    a = manifest.get("assessment")
    candidates = [a.get("date") if isinstance(a, dict) else None,
                  manifest.get("assessment_date"), manifest.get("completed_at"),
                  manifest.get("generated_at"), manifest.get("execution_timestamp"),
                  manifest.get("last_updated")]
    for c in candidates:
        if isinstance(c, str) and _ISOISH.match(c.strip()):
            return c.strip()
    return None


def _entity_token(manifest: dict) -> str:
    """The token that qualifies this package's local ids globally."""
    m = DMA_ASM.match(str(manifest.get("run_id", "")).strip().upper())
    if m:
        return m.group("entity")
    name = _institution(manifest).get("name") or ""
    return re.sub(r"[^A-Z0-9]", "", name.upper())[:8] or "UNK"


def _qualify(e_id: str, token: str) -> str:
    """Package Evidence_Master ids are workbook-LOCAL (every General-DMA
    template starts at E-001), but evidence_index.e_id is a global PK. The
    stored id is entity-qualified — E-047 becomes E-{ENT}-047 — the same
    scheme the TRD documents for the other package-local id (REC-{ENT}-nn),
    and a shape the one recogniser already accepts. Bare ids stay the
    package-facing form; qualification is this one choke point."""
    return f"E-{token}-{e_id[2:]}" if e_id.startswith("E-") else e_id


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
                    research: dict | None = None) -> PersistResult:
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

    cur.execute("SELECT COALESCE(max(run_seq), 0) + 1 FROM runs WHERE entity_id = %s", (entity_id,))
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
                             completed_at, source_folder_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'INGESTED',%s,%s) RETURNING id""",
        (entity_id, manifest.get("run_id"), run_seq, pinned,
         len({s.subcap_id for s in workbook.scores}), catalogue_cells, composite,
         _stated_completed_at(manifest), source_folder_id),
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
    landed: set[str] = set()     # stored ids that own a row after this loop

    def _observe(kind: str, detail: dict) -> None:
        nonlocal n_obs
        cur.execute(
            """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
               VALUES (%s,%s,%s, now())""", (run_id, kind, json.dumps(detail)))
        n_obs += 1

    def _land_evidence(ev: dict) -> str | None:
        """Insert one package item; return the stored id its local id
        resolves to, or None (recorded) when nothing can hold it."""
        ers = ev.get("ers")
        if ers is not None and not (Decimal("1") <= ers <= Decimal("5")):
            # A stated ERS outside the 1–5 rubric (some packages score on
            # 0–10): landed as NULL and recorded — never rescaled, a
            # made-up conversion would be data that was never stated.
            _observe("ers_out_of_range",
                     {"package_local_id": ev["e_id"], "stated": str(ers)})
            ev = {**ev, "ers": None}
        qualified = _qualify(ev["e_id"], token)
        for candidate in (qualified, f"{qualified}-R{run_seq}"):
            cur.execute(
                """INSERT INTO evidence_index
                     (e_id, entity_id, origin, source_name, source_url, excerpt,
                      tier, claim_type, ers, published_date, reference_date)
                   VALUES (%s,%s,'package',%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING RETURNING e_id""",
                (candidate, entity_id, ev.get("source_name"), ev.get("source_url"),
                 ev.get("excerpt"), ev.get("tier"), ev.get("claim_type"),
                 ev.get("ers"), ev.get("published_date"), reference_date))
            if cur.fetchone():
                landed.add(candidate)
                return candidate
            # The bare ON CONFLICT covers both uniques; work out which fired.
            cur.execute(
                f"""SELECT entity_id = %s,
                           content_hash IS NOT DISTINCT FROM {_HASH_SQL}
                      FROM evidence_index WHERE e_id = %s""",
                (entity_id, ev.get("source_url"), ev.get("excerpt"), candidate))
            row = cur.fetchone()
            if row is None:
                # No PK hit -> the (entity_id, content_hash) dedup index
                # fired: this content already lives under another of this
                # entity's ids. Map to it and record — never silently.
                cur.execute(
                    f"""SELECT e_id FROM evidence_index
                        WHERE entity_id = %s AND content_hash = {_HASH_SQL}""",
                    (entity_id, ev.get("source_url"), ev.get("excerpt")))
                hit = cur.fetchone()
                if hit is None:
                    # Neither lookup resolved: the insert conflicted on a
                    # constraint this branch cannot attribute. Record it and
                    # drop THIS item — one unattributable row must not sink a
                    # whole package, and a silent alias to the wrong row would
                    # be worse than an absent citation.
                    _observe("evidence_conflict_unresolved", {
                        "package_local_id": ev["e_id"],
                        "candidate": candidate,
                        "has_url": bool(ev.get("source_url")),
                        "has_excerpt": bool(ev.get("excerpt")),
                        "reason": "ON CONFLICT fired but neither the e_id nor "
                                  "the (entity_id, content_hash) lookup matched"})
                    return None
                kept = hit[0]
                branch = ("duplicate_within_run" if kept in landed
                          else "dedup_same_entity")
                cur.execute(
                    f"""INSERT INTO evidence_dedup_audit
                          (e_id, content_hash, branch, matched_e_id, occurred_at)
                        VALUES (NULL, {_HASH_SQL}, %s, %s, now())""",
                    (ev.get("source_url"), ev.get("excerpt"), branch, kept))
                _observe("evidence_dedup", {"package_local_id": ev["e_id"],
                                            "incoming_e_id": candidate,
                                            "kept_e_id": kept, "branch": branch})
                return kept
            same_entity, same_content = row
            if same_entity and same_content:
                # Idempotent re-scan of a package this entity already holds.
                landed.add(candidate)
                return candidate
            # Same stored id but different content (a re-assessment reusing
            # the local number), or — under a name-derived token — another
            # entity's row. NEVER alias to it; retry once run-qualified.
            _observe("evidence_id_collision",
                     {"package_local_id": ev["e_id"], "stored_id": candidate,
                      "same_entity": bool(same_entity),
                      "retry": f"{qualified}-R{run_seq}"})
        _observe("evidence_unpersistable", {"package_local_id": ev["e_id"],
                                            "qualified": qualified})
        return None

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

    for ev in (evidence or []):
        r = rledger.get(ev["e_id"]) or {}
        # authoritative-where-present, never overwriting a stated value with a
        # blank one
        for field in ("ers", "published_date", "stated_recency", "tier",
                      "fact_count", "claim_type"):
            if r.get(field) is not None and ev.get(field) is None:
                ev = {**ev, field: r[field]}
        if r.get("excerpt"):
            # a verbatim 50–500 char passage beats a mined fragment
            ev = {**ev, "excerpt": r["excerpt"]}
        m = mined.get(ev["e_id"]) or {}
        if not ev.get("excerpt") and m.get("excerpt"):
            ev = {**ev, "excerpt": m["excerpt"]}
        if not ev.get("subcaps") and m.get("subcaps"):
            # The ledger's SubCaps column carries corpus tokens like
            # ENTITY_PROFILE rather than cell ids; the cells that actually
            # cite this item are the ones the drawer should link to.
            ev = {**ev, "subcaps": m["subcaps"]}
        resolved = _land_evidence(ev)
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
        # The linker count — written only now that both sides of the join
        # exist. The linker ran for this run, so an unlinked cell's count is
        # a computed zero; NULL is reserved for runs the linker never saw.
        cur.execute(
            """UPDATE subcap_scores sc
                  SET linked_evidence_count =
                        (SELECT count(*) FROM evidence_subcap_links l
                          WHERE l.run_id = sc.run_id AND l.subcap_id = sc.subcap_id)
                WHERE sc.run_id = %s""",
            (run_id,))

    for o in workbook.observations:
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
