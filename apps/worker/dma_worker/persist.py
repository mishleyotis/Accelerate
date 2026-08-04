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
from .workbook_parser import WorkbookParse

# Mirrors CONTENT_HASH_EXPR in migrations/versions/0005_ingested_tier.py with
# claim_type NULL (the package path never asserts a claim type). Used to find
# the kept row after the (entity_id, content_hash) dedup index rejects an
# insert — the recompute must stay byte-identical to the generated column.
_HASH_SQL = r"""encode(digest(coalesce(%s,'') || '|' || '' || '|' ||
                lower(left(regexp_replace(%s,'\s+',' ','g'),500)),
         'sha256'),'hex')"""


def _entity_token(manifest: dict) -> str:
    """The token that qualifies this package's local ids globally."""
    m = DMA_ASM.match(str(manifest.get("run_id", "")).strip().upper())
    if m:
        return m.group("entity")
    name = manifest.get("institution", {}).get("name") or ""
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
                    report_artefact_id: str | None = None) -> PersistResult:
    cur = conn.cursor()
    inst = manifest.get("institution", {})
    resolution = resolve(
        manifest_identity=inst.get("name"),
        request_id=manifest.get("run_id"),
        document_header=None,
        folder_name=None,
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

    # Pin the catalogue version the assessment was scored against.
    taxonomy = str(manifest.get("versions", {}).get("taxonomy", "")).strip()
    pinned = taxonomy if taxonomy.startswith("v") else (f"v{taxonomy}" if taxonomy else None)
    catalogue_cells = None
    if pinned:
        cur.execute("SELECT cell_count FROM ccg_versions WHERE version = %s", (pinned,))
        r = cur.fetchone()
        catalogue_cells = r[0] if r else None

    cur.execute("SELECT COALESCE(max(run_seq), 0) + 1 FROM runs WHERE entity_id = %s", (entity_id,))
    run_seq = cur.fetchone()[0]
    composite = _round_once(workbook.composite)   # rounded ONCE
    composite_from_manifest = False
    if composite is None and manifest.get("scores", {}).get("overall") is not None:
        # The workbook generation carries no composite figure; the manifest's
        # stated overall is READ (not derived), with its provenance recorded.
        composite = _round_once(Decimal(str(manifest["scores"]["overall"])))
        composite_from_manifest = True
    cur.execute(
        """INSERT INTO runs (entity_id, request_id, run_seq, ccg_catalog_version,
                             scored_cells, catalogue_cells, composite, status,
                             completed_at, source_folder_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'INGESTED',%s,%s) RETURNING id""",
        (entity_id, manifest.get("run_id"), run_seq, pinned,
         workbook.scored_cells, catalogue_cells, composite,
         manifest.get("assessment", {}).get("date"), source_folder_id),
    )
    run_id = cur.fetchone()[0]

    cur.execute("INSERT INTO run_manifest (run_id, payload) VALUES (%s, %s)",
                (run_id, json.dumps(manifest)))
    n_obs = 0
    if composite_from_manifest:
        cur.execute(
            """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
               VALUES (%s,'composite_from_manifest',%s, now())""",
            (run_id, json.dumps({"value": str(composite),
                                 "reason": "workbook carries no composite figure"})))
        n_obs += 1

    reference_date = manifest.get("assessment", {}).get("date")
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
        qualified = _qualify(ev["e_id"], token)
        for candidate in (qualified, f"{qualified}-R{run_seq}"):
            cur.execute(
                """INSERT INTO evidence_index
                     (e_id, entity_id, origin, source_name, source_url, excerpt,
                      tier, ers, published_date, reference_date)
                   VALUES (%s,%s,'package',%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING RETURNING e_id""",
                (candidate, entity_id, ev.get("source_name"), ev.get("source_url"),
                 ev.get("excerpt"), ev.get("tier"), ev.get("ers"),
                 ev.get("published_date"), reference_date))
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
                kept = cur.fetchone()[0]
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

    for ev in (evidence or []):
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

    for s in workbook.scores:
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
    m_overall = manifest.get("scores", {}).get("overall")
    if m_overall is not None and composite is not None:
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
                         workbook.scored_cells, n_obs)
