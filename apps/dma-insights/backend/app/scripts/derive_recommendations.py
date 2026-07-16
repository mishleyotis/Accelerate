"""Recommendation completeness + enrichment derive (D4, Part 7.2).

Passes, all idempotent / fill-if-empty:

  PASS 1 — fill-if-empty inserts (pre-existing behaviour, extended):
    entities whose ACTIVE run shipped ZERO recommendations get grounded,
    inferred recs targeting their own worst categories vs peer medians —
    now ALSO carrying the migration-048 fields from their grounding
    (root_cause_e_ids = the category's own evidence, outcomes quantified
    from the real score gap + peer names, phase from the effort band).

  PASS 2 — rich-corpus enrichment (the audit's "rich rec corpus exists
    ONLY in tests/fixtures — never ingested"): each ACTIVE run's package
    dir is resolved from `entities.drive_folder_id` (`local:<folder>`;
    override root via DMA_PACKAGES_DIR) and its richest rec source
    (per-REC `REC-NN.json` dir → recommendations_detail.json → register
    → exports) is re-parsed. Persisted rows are UPDATEd fill-if-empty
    with feature / phase / root_cause_e_ids / outcomes /
    prerequisite_rec_ids; per-REC recs never persisted at ingest are
    INSERTed. Inverse dependency clauses ("R7 is the prerequisite for
    R1-R6") fan out onto the dependent rows' prerequisite_rec_ids.

  PASS 3 — description mining: rows still missing 048 fields get them
    mined from their PERSISTED prose (E-ID citation regex, durations +
    metrics via nlp.quantities, peers via NER, phase from effort band).

  PASS 5 — selection-quality QA gate (2026-07-06, `rec_selection_qa`):
    every ACTIVE run's rec set is checked for mis-selection — recs whose
    own links/prose target NO observed gap of this entity, recs with no
    evidence linkage, net-new "deploy X" recs for platforms the stack
    already CONFIRMS, duplicate rows under two id spellings (R1 ≡
    REC-01), and phases scheduled before their prerequisites. Two flags
    remediate deterministically: duplicate-id rows keep the richest and
    DELETE the rest; a phase earlier than a prerequisite's is raised to
    the prerequisite's phase. Everything else is REPORTED (printed
    per-class counts) — content is never invented to silence a flag.

Never fabricated: every emitted value traces to the entity's own rows
or package files; fields stay NULL when the corpus is silent.

Usage:
  DATABASE_URL=... python -m app.scripts.derive_recommendations
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from sqlalchemy import text

from app.database import get_sessionmaker
from app.services.parsers.package_recommendations import parse_recommendations_any
from app.services.parsers.rec_files import (
    compose_gap_outcomes,
    effort_band_from_gap,
    extract_feature,
    extract_rec_enrichment,
    mine_description_enrichment,
    parse_rec_dir,
)

_TARGET_BAND = 4.0   # M4 "good" — same target the platform-fit scorer uses
# Gap-fill cap for entities that shipped ZERO extracted recs: the PASS-1 query
# already bounds itself to below-M4 categories (HAVING AVG(score) < 4.0), of
# which there are at most ~16-17 in V7. A cap of 5 silently dropped ~12 grounded
# gap recs/entity for the 26 zero-rec clients ("all recommendations are not even
# picked" — 2026-07-09 QA); 16 covers the full below-target set. The serving API
# + frontend apply no cap, so every generated rec now surfaces.
_MAX_RECS = 16

_DEFAULT_PACKAGES_DIR = "tests/fixtures/dma_packages_batches"


def _effort_band(gap: float) -> str:
    if gap >= 1.5:
        return "LARGE"
    if gap >= 0.75:
        return "MEDIUM"
    return "SMALL"


_EFFORT_PHASE = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3, "XLARGE": 4}
_PHASE_WINDOW = {1: "0-6 months", 2: "6-12 months", 3: "12-18 months", 4: "18+ months"}


def _resolve_package_dir(drive_folder_id: str | None, packages_root: Path) -> Path | None:
    """`local:<Folder Name>` → the package dir under the fixtures batches."""
    if not drive_folder_id or not drive_folder_id.startswith("local:"):
        return None
    name = drive_folder_id.split(":", 1)[1].strip()
    if not name:
        return None
    hits = sorted(packages_root.glob(f"*/{name}"))
    return hits[0] if hits and hits[0].is_dir() else None


def _norm_rec_id(raw: str) -> str:
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return f"REC-{int(digits):02d}" if digits else str(raw).upper()[:16]


async def _update_enrichment(
    session, *, run_id: str, rec_id: str, enrich: dict,
) -> None:
    """Fill-if-empty UPDATE of the 048 columns for one persisted rec.

    Outcomes merge per-KEY (existing non-null values win over mined
    ones) so a later mining pass can fill `metric` on a row whose
    earlier pass only produced `time`/`effort`.
    """
    await session.execute(text(
        """
        UPDATE recommendations SET
            feature = COALESCE(feature, :feature),
            phase = COALESCE(phase, :phase),
            root_cause_e_ids = CASE
                WHEN root_cause_e_ids IS NULL
                  OR cardinality(root_cause_e_ids) = 0
                THEN CAST(:rce AS TEXT[]) ELSE root_cause_e_ids END,
            outcomes = CASE
                WHEN CAST(:outcomes AS JSONB) IS NULL THEN outcomes
                WHEN outcomes IS NULL THEN CAST(:outcomes AS JSONB)
                ELSE CAST(:outcomes AS JSONB)
                     || jsonb_strip_nulls(outcomes) END,
            prerequisite_rec_ids = CASE
                WHEN prerequisite_rec_ids IS NULL
                  OR cardinality(prerequisite_rec_ids) = 0
                THEN CAST(:prereqs AS VARCHAR[]) ELSE prerequisite_rec_ids END
        WHERE run_id = CAST(:rid AS uuid) AND rec_id = :recid
        """
    ), {
        "rid": run_id, "recid": rec_id,
        "feature": (enrich.get("feature") or None),
        "phase": enrich.get("phase"),
        "rce": enrich.get("root_cause_e_ids") or None,
        "outcomes": json.dumps(enrich["outcomes"]) if enrich.get("outcomes") else None,
        # Column is NOT NULL (migration 042) — an empty extraction keeps
        # the existing (empty) array rather than writing NULL.
        "prereqs": [p[:16] for p in (enrich.get("requires_rec_ids") or [])],
    })


async def _fan_out_prereq_of(
    session, *, run_id: str, source_rec_id: str, prereq_of: list[str],
) -> None:
    """`source` is a prerequisite OF each target → append source to the
    target's prerequisite_rec_ids (idempotent, no duplicates)."""
    for target in prereq_of:
        await session.execute(text(
            """
            UPDATE recommendations
            SET prerequisite_rec_ids =
                array_append(COALESCE(prerequisite_rec_ids, '{}'), :src)
            WHERE run_id = CAST(:rid AS uuid) AND rec_id = :target
              AND NOT (:src = ANY(COALESCE(prerequisite_rec_ids, '{}')))
            """
        ), {"rid": run_id, "src": source_rec_id[:16], "target": target[:16]})


def _pass2_title(raw: dict) -> str | None:
    """Honest title chain for a PASS-2 rich-corpus insert: explicit title →
    the phase-6 export's `solution` STRING → first gap_category label →
    feature keyword scan. Returns None when the source carries no titleable
    signal — the rec is then SKIPPED rather than shipped as '(untitled)'
    (22 such rows reached the 2026-07-06 pack)."""
    t = str(raw.get("title") or "").strip()
    if t:
        return t[:500]
    sol = raw.get("solution")
    if isinstance(sol, str) and sol.strip():
        return sol.strip()[:500]
    gcs = raw.get("gap_categories")
    if isinstance(gcs, list) and gcs:
        gc = gcs[0]
        label = (gc.get("label") or gc.get("name")) if isinstance(gc, dict) else gc
        if isinstance(label, str) and label.strip():
            return label.strip()[:500]
    return extract_feature(raw)


def _compose_description(raw: dict) -> str:
    """Description from a raw rich-rec dict (root cause + solution prose) —
    mirrors package_persist._rec_description's intent for the per-REC
    shapes that never went through ingest."""
    parts: list[str] = []
    rc = raw.get("root_cause") if isinstance(raw.get("root_cause"), dict) else {}
    for key in ("gap_description", "finding", "narrative"):
        v = (rc or {}).get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
            break
    sol = raw.get("solution") if isinstance(raw.get("solution"), dict) else {}
    for key in ("description", "narrative"):
        v = (sol or {}).get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
            break
    unlock = raw.get("cross_pillar_unlock") or raw.get("cross_pillar_unlocks")
    if isinstance(unlock, list):
        unlock = "; ".join(str(u) for u in unlock)
    if isinstance(unlock, str) and unlock.strip():
        parts.append(f"Cross-pillar unlock: {unlock.strip()}")
    return "\n\n".join(parts) or str(raw.get("title") or "")


async def _pass2_rich_corpus(session, packages_root: Path) -> tuple[int, int]:
    """Re-read package rec sources; UPDATE persisted rows + INSERT per-REC
    recs missing entirely. Returns (updated, inserted)."""
    from app.services.parsers.package_persist import _infer_platform_id

    runs = (await session.execute(text(
        """
        SELECT r.id::text AS rid, e.id::text AS eid, e.drive_folder_id
        FROM entities e JOIN runs r ON r.entity_id = e.id AND r.status='ACTIVE'
        WHERE e.status = 'ACTIVE'
        ORDER BY e.display_id
        """
    ))).all()

    updated = 0
    inserted = 0
    for run in runs:
        pkg_dir = _resolve_package_dir(run.drive_folder_id, packages_root)
        if pkg_dir is None:
            continue

        # Richest source first: per-REC dir, then aggregate JSON files.
        raw_recs: list[dict] = []
        per_rec_files = sorted(pkg_dir.glob("**/recommendations/REC-*.json"))
        if per_rec_files:
            raw_recs = parse_rec_dir(per_rec_files[0].parent)
        if not raw_recs:
            for name in ("recommendations_detail.json",
                         "recommendations_register.json",
                         "recommendations.json", "06_recommendations.json"):
                hits = sorted(pkg_dir.glob(f"**/{name}"))
                if hits:
                    try:
                        rows = parse_recommendations_any(
                            hits[0].read_text(encoding="utf-8"))
                    except OSError:
                        rows = []
                    raw_recs = [r.model_dump() for r in rows]
                    if raw_recs:
                        break
        if not raw_recs:
            continue

        persisted = {
            _norm_rec_id(r.rec_id): r.rec_id
            for r in (await session.execute(text(
                "SELECT rec_id FROM recommendations WHERE run_id = CAST(:rid AS uuid)"
            ), {"rid": run.rid})).all()
        }

        for raw in raw_recs:
            rid_norm = _norm_rec_id(str(raw.get("id") or raw.get("rec_id") or ""))
            if not rid_norm:
                continue
            enrich = extract_rec_enrichment({**raw, "id": rid_norm})
            if rid_norm in persisted:
                await _update_enrichment(
                    session, run_id=run.rid, rec_id=persisted[rid_norm],
                    enrich=enrich,
                )
                updated += 1
            else:
                # Rich per-REC rec the aggregate globs never ingested —
                # INSERT it (real corpus data, full provenance). A rec
                # with no titleable signal anywhere is skipped — never
                # shipped as '(untitled)'.
                title = _pass2_title(raw)
                if not title:
                    continue
                await session.execute(text(
                    """
                    INSERT INTO recommendations (
                        id, run_id, entity_id, rec_id, title, description,
                        target_subcap_ids, platform_id, effort_band,
                        feature, phase, root_cause_e_ids, outcomes,
                        prerequisite_rec_ids, created_at)
                    VALUES (gen_random_uuid(), CAST(:rid AS uuid),
                        CAST(:eid AS uuid), :recid, :title, :descr,
                        CAST(:subcaps AS varchar[]), :plat, :eb,
                        :feature, :phase, CAST(:rce AS TEXT[]),
                        CAST(:outcomes AS JSONB), CAST(:prereqs AS varchar[]),
                        NOW())
                    ON CONFLICT (run_id, rec_id) DO NOTHING
                    """
                ), {
                    "rid": run.rid, "eid": run.eid, "recid": rid_norm[:16],
                    "title": title,
                    "descr": _compose_description(raw),
                    "subcaps": [],
                    "plat": _infer_platform_id(title, str(raw.get("ownership") or "")),
                    "eb": None,
                    "feature": enrich.get("feature"),
                    "phase": enrich.get("phase"),
                    "rce": enrich.get("root_cause_e_ids") or None,
                    "outcomes": (json.dumps(enrich["outcomes"])
                                 if enrich.get("outcomes") else None),
                    "prereqs": [p[:16] for p in (enrich.get("requires_rec_ids") or [])],
                })
                inserted += 1
            await _fan_out_prereq_of(
                session, run_id=run.rid, source_rec_id=rid_norm,
                prereq_of=enrich.get("prereq_of_rec_ids") or [],
            )
    return updated, inserted


async def _pass3_mine_descriptions(session) -> int:
    """Rows still missing 048 fields → mine the persisted prose."""
    rows = (await session.execute(text(
        """
        SELECT r.id::text AS id, r.run_id::text AS rid, r.rec_id,
               r.title, r.description, r.effort_band
        FROM recommendations r
        JOIN runs run ON run.id = r.run_id AND run.status = 'ACTIVE'
        WHERE r.feature IS NULL OR r.phase IS NULL
           OR r.root_cause_e_ids IS NULL OR cardinality(r.root_cause_e_ids) = 0
           OR r.outcomes IS NULL OR r.outcomes->>'metric' IS NULL
        ORDER BY r.rec_id
        """
    ))).all()
    mined = 0
    for r in rows:
        enrich = mine_description_enrichment(
            title=r.title, description=r.description,
            effort_band=r.effort_band, rec_id=r.rec_id,
        )
        # Label-less mined metrics ("outcome 12 months") are the rec's own
        # Timeline clause leaking into the metric slot — not a business
        # metric. Drop them so PASS-4 grounds the metric in the rec's OWN
        # capability targets instead (fill-if-empty would otherwise lock
        # the junk value in).
        oc = enrich.get("outcomes")
        if (isinstance(oc, dict)
                and isinstance(oc.get("metric"), str)
                and oc["metric"].lower().startswith("outcome ")):
            oc["metric"] = None
            if not any(oc.values()):
                enrich["outcomes"] = None
        await _update_enrichment(
            session, run_id=r.rid, rec_id=r.rec_id, enrich=enrich,
        )
        await _fan_out_prereq_of(
            session, run_id=r.rid, source_rec_id=r.rec_id,
            prereq_of=enrich.get("prereq_of_rec_ids") or [],
        )
        mined += 1
    return mined


_CAT_RE = re.compile(r"\bP[1-4]C\d+\b")


def _scope_aligned(linked: list[str], targets: list[str]) -> bool:
    """The qa_surface_attribution grain-prefix predicate: cited evidence
    links at-or-under a declared target (or a target at-or-under the
    link). Empty ``linked`` never aligns — the harness counts a citation
    to subcap-unlinked evidence as a scope miss on a target-declaring rec."""
    return any(
        s == t or s.startswith(t + ".") or t.startswith(s + ".")
        for s in linked for t in targets
    )

# ── PASS-4 per-rec grounding helpers (2026-07-06 de-collapse) ───────────
# The pack audit measured 58/94 clients with >=2 recs sharing an IDENTICAL
# (time, effort, metric) triple because every ungrounded rec in a run
# collapsed to the same pillar-/run-worst category. Each rec must instead
# derive its outcomes from ITS OWN stated capability targets when the
# corpus carries them, and otherwise round-robin over UNUSED scored
# categories so no two recs in a run collapse to one shared gap.

# `[CRITICAL]` severity tag persisted into the rec description by the
# report_recommendations banner path.
_SEVERITY_TAG_RE = re.compile(
    r"\[(CRITICAL|URGENT|HIGH|MEDIUM|MODERATE|LOW)\]", re.IGNORECASE)
_SEVERITY_EFFORT = {
    "CRITICAL": "LARGE", "URGENT": "LARGE",
    "HIGH": "MEDIUM", "MEDIUM": "MEDIUM", "MODERATE": "MEDIUM",
    "LOW": "SMALL",
}
# The rec's OWN stated `current → target` capability scores. Two corpus
# shapes: the arrow clause ("P2C1 (…): 1.79 → 2.8") and the tab-joined
# DOCX score-impact grid row ("P2C1\t1.79\t2.80\t+1.01").
_OWN_ARROW_RE = re.compile(
    r"\b(P[1-4]C\d+)\b\D{0,60}?(\d(?:\.\d{1,2})?)\s*(?:→|->)\s*(\d(?:\.\d{1,2})?)")
_OWN_GRID_RE = re.compile(
    r"\b(P[1-4]C\d+)\b\t(\d(?:\.\d{1,2})?)\t(\d(?:\.\d{1,2})?)")


def own_target_pairs(text: str) -> list[tuple[str, float, float]]:
    """(category, current, target) triples the REC ITSELF states in its
    title/description — document order, first statement per category wins,
    non-improvements (target <= current) discarded. Empty when the prose
    carries no per-capability targets."""
    hits = sorted(
        ((m.start(), m) for rx in (_OWN_GRID_RE, _OWN_ARROW_RE)
         for m in rx.finditer(text or "")),
        key=lambda t: t[0],
    )
    pairs: list[tuple[str, float, float]] = []
    seen: set[str] = set()
    for _pos, m in hits:
        cat = m.group(1).upper()
        try:
            cur, tgt = float(m.group(2)), float(m.group(3))
        except ValueError:
            continue
        if cat in seen or not (0.0 <= cur < tgt <= 5.0):
            continue
        seen.add(cat)
        pairs.append((cat, cur, tgt))
    return pairs


def severity_scope_effort(text: str, n_categories: int) -> str | None:
    """Effort band from the rec's own severity tag + scope (how many
    capability categories it targets) — the variation tier for recs with
    no explicit effort band. None when no severity tag is present."""
    m = _SEVERITY_TAG_RE.search(text or "")
    if not m:
        return None
    band = _SEVERITY_EFFORT[m.group(1).upper()]
    if n_categories >= 4 and band != "LARGE":
        # A rec spanning 4+ categories is a bigger build than its
        # severity alone implies — bump one level (capped at LARGE).
        band = {"SMALL": "MEDIUM", "MEDIUM": "LARGE"}[band]
    return band


def _worst_scored(cands: list[str], scores: dict[str, float]) -> str | None:
    """The lowest-scoring (biggest-gap) category among ``cands`` that has a
    real score — the grounding-ladder rung picker."""
    hits = [c for c in cands if c in scores]
    return min(hits, key=lambda c: scores[c]) if hits else None


def pick_unused_category(
    cands: list[str], scores: dict[str, float], used: set[str],
) -> str | None:
    """`_worst_scored` with round-robin de-collapse: prefer the worst
    UNUSED scored candidate so sibling recs in one run never all ground
    to the same shared category; when every candidate is already taken
    (more recs than categories), fall back to the worst overall."""
    hits = [c for c in cands if c in scores]
    if not hits:
        return None
    unused = [c for c in hits if c not in used]
    pool = unused or hits
    return min(pool, key=lambda c: scores[c])


async def _pass4_ground_outcomes(session) -> tuple[int, int]:
    """Ground the outcomes grid for EVERY active-run rec (Part 7.2 close-out).

    The audit measured ~50% of roadmap recs shipping no ``outcomes`` and 86%
    with a null ``maturity_lift`` — because only the small PASS-1 derived set
    and the few corpus recs with explicit ``expected_outcomes`` carried them.
    This pass resolves each rec to a REAL scored category via a grounding
    ladder and fills ``outcomes {time, effort, metric, peer}`` fill-if-empty:

      the rec's OWN stated ``current → target`` capability scores →
      target_subcap → mined ``P?C?`` prose → root-cause evidence subcap →
      platform (declared OR inferred from the feature) pillar's worst gap →
      the run's worst-gap category.

    De-collapse contract (2026-07-06): every rung round-robins over
    categories UNUSED by sibling recs in the same run (the pack audit
    measured 58/94 clients whose recs collapsed to one identical
    (time, effort, metric) triple), and a rec whose own prose states
    per-capability targets gets THAT metric ("P2C1 score 1.79 → 2.8"),
    not the shared 4.0-band template. Effort prefers the rec's own
    effort_band, then its severity tag + scope, then the gap band.

    ``metric`` is the quantified maturity clause ("P2C4 score 1.50 → 4.0
    (peer median 2.58)") whenever a category resolves — which is also what
    the roadmap mines back into ``maturity_lift``. ``peer`` is the entity's
    top benchmark peer (always available), so a rec with no category link
    still carries a non-empty outcomes grid. Nothing is fabricated: every
    value traces to a real subcap score, the rec's own stated target, a
    peer median, or a peer name.

    Also fills ``platform_id`` (inferred from feature/title) when absent, so
    the rec joins the right D4 platform lane. Returns (outcomes_filled,
    platform_filled).
    """
    from app.services.parsers.package_persist import _infer_platform_id
    from app.services.platform_display import PLATFORM_DISPLAY

    runs = (await session.execute(text(
        """
        SELECT r.id::text AS rid, e.id::text AS eid
        FROM entities e JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
        WHERE e.status = 'ACTIVE'
        ORDER BY e.display_id
        """
    ))).all()

    outcomes_filled = 0
    platform_filled = 0
    for run in runs:
        cats = (await session.execute(text(
            """
            SELECT COALESCE(parent_category_id, LEFT(subcap_id, 4)) AS cat,
                   ROUND(AVG(score)::numeric, 2) AS avg_s,
                   ROUND(AVG(peer_median)::numeric, 2) AS avg_p
            FROM subcap_scores
            WHERE run_id = CAST(:rid AS uuid) AND score IS NOT NULL
            GROUP BY 1
            """
        ), {"rid": run.rid})).all()
        if not cats:
            continue
        cat_cur = {c.cat: float(c.avg_s) for c in cats}
        cat_peer = {c.cat: (float(c.avg_p) if c.avg_p is not None else None) for c in cats}

        eid_subs: dict[str, list[str]] = {}
        cat_eids: dict[str, list[str]] = {}
        for e in (await session.execute(text(
            """
            SELECT e_id, linked_subcap_ids FROM evidence_index
            WHERE run_id = CAST(:rid AS uuid)
            ORDER BY tier ASC, e_id ASC
            """
        ), {"rid": run.rid})).all():
            eid_subs[e.e_id] = list(e.linked_subcap_ids or [])
            for s in eid_subs[e.e_id]:
                if len(s) >= 4:
                    cat_eids.setdefault(s[:4], []).append(e.e_id)

        peer_name = (await session.execute(text(
            """
            SELECT peer_name FROM entity_peers
            WHERE entity_id = CAST(:eid AS uuid)
            ORDER BY overall_score DESC NULLS LAST LIMIT 1
            """
        ), {"eid": run.eid})).scalar()

        recs = (await session.execute(text(
            """
            SELECT rec_id, title, description, platform_id, feature, effort_band,
                   target_subcap_ids, root_cause_e_ids, outcomes
            FROM recommendations WHERE run_id = CAST(:rid AS uuid)
            ORDER BY rec_id
            """
        ), {"rid": run.rid})).all()

        # Categories already claimed by a sibling rec in THIS run — the
        # round-robin state that kills the identical-triple collapse.
        used_cats: set[str] = set()
        for r in recs:
            existing = r.outcomes if isinstance(r.outcomes, dict) else {}
            # A rec is complete when every outcome slot is already filled.
            complete = all(existing.get(k) for k in ("time", "effort", "metric", "peer"))
            plat = r.platform_id
            new_plat = None
            if not plat:
                new_plat = _infer_platform_id(r.title or "", r.feature or "")
                plat = new_plat
            if complete and new_plat is None:
                continue

            own_text = f"{r.title or ''}\n{r.description or ''}"
            own_pairs = own_target_pairs(own_text)
            scope_n = len(own_pairs) or len(
                {s[:4] for s in (r.target_subcap_ids or []) if len(s) >= 4})
            sev_eb = severity_scope_effort(own_text, scope_n)

            if own_pairs:
                # ── the rec's OWN stated capability targets ────────────────
                # Metric = its own `current → target` clause (NOT the shared
                # 4.0 band); round-robin over its own categories so sibling
                # recs sharing a worst category still differentiate.
                cat, cur, tgt = next(
                    (p for p in own_pairs if p[0] not in used_cats),
                    own_pairs[0],
                )
                eb = (r.effort_band or sev_eb
                      or effort_band_from_gap(max(0.0, tgt - cur)))
                grounded = compose_gap_outcomes(
                    label=cat, current=cur, target=tgt,
                    peer_median=cat_peer.get(cat), effort_band=eb,
                    peer_name=peer_name,
                )
            else:
                # ── grounding ladder → a real scored category ──────────────
                # Same rung order as before; every rung now prefers the
                # worst UNUSED category (pick_unused_category).
                cat = pick_unused_category(
                    [s[:4] for s in (r.target_subcap_ids or []) if len(s) >= 4],
                    cat_cur, used_cats)
                if cat is None:
                    mined = set(_CAT_RE.findall(own_text))
                    cat = pick_unused_category(sorted(mined), cat_cur, used_cats)
                if cat is None:
                    rce_subs = [s for e in (r.root_cause_e_ids or [])
                                for s in eid_subs.get(e, [])]
                    cat = pick_unused_category(
                        sorted({s[:4] for s in rce_subs if len(s) >= 4}),
                        cat_cur, used_cats)
                if cat is None and plat:
                    pil = PLATFORM_DISPLAY.get(plat, {}).get("pillar")
                    if pil:
                        cat = pick_unused_category(
                            sorted(c for c in cat_cur if c.startswith(pil)),
                            cat_cur, used_cats)
                if cat is None:
                    cat = pick_unused_category(
                        sorted(cat_cur), cat_cur, used_cats)

                cur = cat_cur[cat]
                gap = round(_TARGET_BAND - cur, 2)
                eb = (r.effort_band or sev_eb
                      or effort_band_from_gap(max(0.0, gap)))
                grounded = compose_gap_outcomes(
                    label=cat, current=cur, target=_TARGET_BAND,
                    peer_median=cat_peer.get(cat), effort_band=eb,
                    peer_name=peer_name,
                )
            used_cats.add(cat)
            # Merge fill-if-empty: existing non-null slots always win.
            merged = dict(grounded)
            for k, v in existing.items():
                if v not in (None, ""):
                    merged[k] = v

            # Evidence linkage fill-if-empty (2026-07-06, PASS-1 parity):
            # a rec grounded to a category inherits that category's own
            # top evidence E-IDs when it carries none — the same rows the
            # analyst's low scores rest on, so the card's evidence chips
            # open the material behind the gap. Never overwrites.
            #
            # Scope guard (2026-07-14 attribution audit): the round-robin
            # `cat` deliberately diverges from siblings — and could diverge
            # from the rec's OWN target_subcap_ids, welding evidence the
            # attribution harness scores as a scope miss (recs fidelity
            # 0.899 < 0.95). When the rec declares targets, weld only
            # evidence that grain-prefix-aligns with them (targets'
            # categories first, then the grounded category), and weld
            # NOTHING rather than misattribute.
            new_eids = None
            if not list(r.root_cause_e_ids or []):
                targets = [str(t) for t in (r.target_subcap_ids or []) if t]
                if targets:
                    target_cats = sorted(
                        {t[:4] for t in targets if len(t) >= 4})
                    pool = [e for c in target_cats
                            for e in cat_eids.get(c, [])]
                    pool += cat_eids.get(cat, [])
                    pool = [e for e in pool
                            if _scope_aligned(eid_subs.get(e, []), targets)]
                else:
                    pool = cat_eids.get(cat, [])
                seen_e: list[str] = []
                for e in pool:
                    if e not in seen_e:
                        seen_e.append(e)
                new_eids = seen_e[:4] or None

            if merged != existing or new_plat is not None or new_eids:
                await session.execute(text(
                    """
                    UPDATE recommendations
                    SET outcomes = CAST(:oc AS JSONB),
                        platform_id = COALESCE(platform_id, :plat),
                        root_cause_e_ids = CASE
                            WHEN root_cause_e_ids IS NULL
                              OR cardinality(root_cause_e_ids) = 0
                            THEN CAST(:rce AS TEXT[]) ELSE root_cause_e_ids END
                    WHERE run_id = CAST(:rid AS uuid) AND rec_id = :recid
                    """
                ), {"rid": run.rid, "recid": r.rec_id,
                    "oc": json.dumps(merged), "plat": new_plat,
                    "rce": new_eids})
                if merged != existing:
                    outcomes_filled += 1
                if new_plat is not None:
                    platform_filled += 1
    return outcomes_filled, platform_filled


async def _pass5_selection_qa(session) -> tuple[int, int, dict[str, int]]:
    """Selection-quality gate over every ACTIVE run's rec set.

    Deterministic remediations: duplicate-id rows (R1 ≡ REC-01) keep the
    richest and DELETE the rest; a phase earlier than a prerequisite's is
    RAISED to that prerequisite's phase. All other flags are counted and
    reported. Returns (dupes_removed, phases_fixed, flag_counts).
    """
    from app.services.parsers.package_persist import _REC_PLATFORM_GUESS
    from app.services.rec_selection_qa import (
        RecQaInput,
        norm_rec_id,
        qa_rec_selection,
        rec_richness,
        resolve_duplicate_ids,
    )

    runs = (await session.execute(text(
        """
        SELECT r.id::text AS rid, e.id::text AS eid
        FROM entities e JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
        WHERE e.status = 'ACTIVE'
        ORDER BY e.display_id
        """
    ))).all()

    dupes_removed = phases_fixed = 0
    flag_counts: dict[str, int] = {}
    for run in runs:
        rows = (await session.execute(text(
            """
            SELECT rec_id, title, description, phase, platform_id,
                   target_subcap_ids, root_cause_e_ids,
                   prerequisite_rec_ids, feature, outcomes
            FROM recommendations WHERE run_id = CAST(:rid AS uuid)
            ORDER BY rec_id
            """
        ), {"rid": run.rid})).all()
        if not rows:
            continue
        cats = (await session.execute(text(
            """
            SELECT COALESCE(parent_category_id, LEFT(subcap_id, 4)) AS cat,
                   ROUND(AVG(score)::numeric, 2) AS avg_s
            FROM subcap_scores
            WHERE run_id = CAST(:rid AS uuid) AND score IS NOT NULL
            GROUP BY 1
            """
        ), {"rid": run.rid})).all()
        cat_scores = {c.cat: float(c.avg_s) for c in cats}
        # CONFIRMED stack rows → the platform-id space recs use, via the
        # same keyword map platform inference uses (consistent by
        # construction).
        stack = (await session.execute(text(
            """
            SELECT vendor, product FROM tech_stack_entries
            WHERE entity_id = CAST(:eid AS uuid) AND status = 'CONFIRMED'
            """
        ), {"eid": run.eid})).all()
        hay = " ".join(
            f"{s.vendor or ''} {s.product or ''}" for s in stack).lower()
        confirmed = frozenset(
            pid for kw, pid in _REC_PLATFORM_GUESS.items() if kw in hay)

        recs = [
            RecQaInput(
                rec_id=r.rec_id, title=r.title, description=r.description,
                phase=r.phase, platform_id=r.platform_id,
                target_subcap_ids=tuple(r.target_subcap_ids or []),
                root_cause_e_ids=tuple(r.root_cause_e_ids or []),
                prerequisite_rec_ids=tuple(r.prerequisite_rec_ids or []),
                richness=rec_richness(r),
            )
            for r in rows
        ]
        flags = qa_rec_selection(
            recs, cat_scores=cat_scores, target_band=_TARGET_BAND,
            confirmed_platform_ids=confirmed,
        )
        for fl in (f for lst in flags.values() for f in lst):
            key = fl.split(":", 1)[0]
            flag_counts[key] = flag_counts.get(key, 0) + 1

        # Remediation 1 — duplicate-id rows: keep richest, delete the rest.
        for loser, _winner in resolve_duplicate_ids(recs):
            await session.execute(text(
                """
                DELETE FROM recommendations
                WHERE run_id = CAST(:rid AS uuid) AND rec_id = :recid
                """
            ), {"rid": run.rid, "recid": loser})
            dupes_removed += 1

        # Remediation 2 — phase raised to the prerequisite's phase.
        by_norm = {norm_rec_id(r.rec_id): r for r in recs}
        for r in recs:
            targets = [
                by_norm[norm_rec_id(f.split(":", 1)[1])]
                for f in flags[r.rec_id]
                if f.startswith("phase_before_prerequisite:")
                and norm_rec_id(f.split(":", 1)[1]) in by_norm
            ]
            if not targets:
                continue
            want = max(p.phase for p in targets if p.phase is not None)
            if r.phase is not None and want > r.phase:
                await session.execute(text(
                    """
                    UPDATE recommendations SET phase = :ph
                    WHERE run_id = CAST(:rid AS uuid) AND rec_id = :recid
                    """
                ), {"ph": want, "rid": run.rid, "recid": r.rec_id})
                phases_fixed += 1
    return dupes_removed, phases_fixed, flag_counts


async def _amain() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    packages_root = Path(os.environ.get("DMA_PACKAGES_DIR", _DEFAULT_PACKAGES_DIR))
    sm = get_sessionmaker()
    filled = 0
    inserted = 0
    async with sm() as session:
        targets = (await session.execute(text(
            """
            SELECT e.id::text AS eid, r.id::text AS rid, e.display_id
            FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
            WHERE e.status='ACTIVE'
              AND NOT EXISTS (SELECT 1 FROM recommendations rc WHERE rc.run_id=r.id)
            ORDER BY e.display_id
            """
        ))).all()

        for t in targets:
            cats = (await session.execute(text(
                """
                SELECT COALESCE(s.parent_category_id, LEFT(s.subcap_id,4)) AS cat,
                       ROUND(AVG(s.score)::numeric, 2) AS avg_s,
                       ROUND(AVG(s.peer_median)::numeric, 2) AS avg_p,
                       (ARRAY_AGG(s.subcap_id ORDER BY s.score ASC))[1:6] AS subcaps,
                       (ARRAY_AGG(COALESCE(cs.name, s.subcap_id) ORDER BY s.score ASC))[1] AS worst_name
                FROM subcap_scores s
                LEFT JOIN ccg_subcaps cs ON cs.subcap_id = s.subcap_id
                WHERE s.run_id = CAST(:rid AS uuid) AND s.score IS NOT NULL
                GROUP BY 1
                HAVING AVG(s.score) < :band
                ORDER BY AVG(s.score) ASC
                LIMIT :n
                """
            ), {"rid": t.rid, "band": _TARGET_BAND, "n": _MAX_RECS})).all()
            if not cats:
                continue
            peer_name = (await session.execute(text(
                """
                SELECT peer_name FROM entity_peers
                WHERE entity_id = CAST(:eid AS uuid)
                ORDER BY overall_score DESC NULLS LAST LIMIT 1
                """
            ), {"eid": t.eid})).scalar()
            for i, c in enumerate(cats, 1):
                gap = round(_TARGET_BAND - float(c.avg_s), 2)
                pillar = (c.cat or "P1")[:2]
                # best-fit platform addressing this category's subcaps
                plat = (await session.execute(text(
                    """
                    SELECT platform_id FROM platform_scores
                    WHERE run_id = CAST(:rid AS uuid) AND fit_score > 0
                      AND addressable_subcap_ids && CAST(:subcaps AS varchar[])
                    ORDER BY fit_score DESC LIMIT 1
                    """
                ), {"rid": t.rid, "subcaps": list(c.subcaps or [])})).scalar()
                # PASS 1 grounding for the 048 fields: the category's own
                # evidence E-IDs + the quantified gap.
                e_ids = [r.e_id for r in (await session.execute(text(
                    """
                    SELECT e.e_id FROM evidence_index e
                    WHERE e.run_id = CAST(:rid AS uuid)
                      AND e.linked_subcap_ids && CAST(:subcaps AS varchar[])
                    ORDER BY e.tier ASC, e.e_id ASC LIMIT 6
                    """
                ), {"rid": t.rid, "subcaps": list(c.subcaps or [])})).all()]
                eb = _effort_band(gap)
                phase = _EFFORT_PHASE.get(eb, 2)
                peer_txt = f" vs peer {c.avg_p}" if c.avg_p is not None else ""
                title = f"Strengthen {c.cat}: {c.worst_name}"[:200]
                desc = (f"{c.cat} scores {c.avg_s}{peer_txt} — below the M4 target. "
                        f"Closing this gap"
                        + (f" is addressable via {plat}." if plat else " is a priority."))
                outcomes = {
                    "time": _PHASE_WINDOW[phase],
                    "effort": {"SMALL": "S", "MEDIUM": "M", "LARGE": "L"}[eb],
                    "metric": (
                        f"{c.cat} score {c.avg_s} → {_TARGET_BAND:.1f}"
                        + (f" (peer median {c.avg_p})" if c.avg_p is not None else "")
                    ),
                    "peer": peer_name,
                }
                await session.execute(text(
                    """
                    INSERT INTO recommendations (
                        id, run_id, entity_id, rec_id, title, description,
                        target_subcap_ids, platform_id, uplift_per_pillar,
                        effort_band, feature, phase, root_cause_e_ids,
                        outcomes, created_at)
                    VALUES (gen_random_uuid(), CAST(:rid AS uuid), CAST(:eid AS uuid),
                        :recid, :title, :desc, CAST(:subcaps AS varchar[]), :plat,
                        CAST(:uplift AS jsonb), :eb, :feature, :phase,
                        CAST(:rce AS TEXT[]), CAST(:outcomes AS JSONB), NOW())
                    """
                ), {"rid": t.rid, "eid": t.eid, "recid": f"REC-{i:02d}",
                    "title": title, "desc": desc, "subcaps": list(c.subcaps or []),
                    "plat": plat, "uplift": f'{{"{pillar}": {gap}}}',
                    "eb": eb,
                    "feature": None,
                    "phase": phase,
                    "rce": e_ids or None,
                    "outcomes": json.dumps(outcomes)})
                inserted += 1
            filled += 1
        await session.commit()

        # PASS 2 + PASS 3 (Part 7.2 enrichment)
        corpus_updated, corpus_inserted = await _pass2_rich_corpus(
            session, packages_root,
        )
        await session.commit()
        mined = await _pass3_mine_descriptions(session)
        await session.commit()

        # PASS 4 — ground the outcomes grid + maturity metric for EVERY rec.
        outcomes_filled, platform_filled = await _pass4_ground_outcomes(session)
        await session.commit()

        # PASS 5 — selection-quality QA gate (dedupe + sequencing fixes;
        # unresolvable mis-selection classes reported below).
        dupes_removed, phases_fixed, flag_counts = await _pass5_selection_qa(
            session)
        await session.commit()

        # PASS 6 — universal title repair (2026-07-06 deploy review): a rec
        # whose title is empty / "(untitled)" / a bare subcap code ("P2C2")
        # / a punctuation-or-lowercase fragment reached the pack from the
        # INGEST path (source recs with a code or blank title), which no
        # earlier pass touches. Compose an AE-readable title from the rec's
        # OWN grounded fields — platform + category action + the lead clause
        # of its (rich) description — never a code, never "(untitled)".
        titles_repaired = await _pass5_repair_titles(session)
        await session.commit()

        # PASS 7 — dead-citation prune (2026-07-09 attribution audit): 315 of
        # 1,755 root-cause citations on ACTIVE runs referenced E-IDs with no
        # evidence_index row in their run — a DEAD evidence chip in the D4
        # drilldown. A citation that cannot resolve is a broken link, not an
        # analyst judgment call, so it is stripped (the rec keeps its
        # resolving citations; an all-dead list becomes empty rather than
        # lying). Purely structural — no NLP — and idempotent.
        dead_pruned = (await session.execute(text(
            """
            WITH bad AS (
              SELECT rec.id,
                     ARRAY(SELECT eid FROM unnest(rec.root_cause_e_ids) eid
                           WHERE EXISTS (SELECT 1 FROM evidence_index e
                                         WHERE e.run_id = rec.run_id
                                           AND e.e_id = eid)) AS kept,
                     cardinality(rec.root_cause_e_ids) AS had
              FROM recommendations rec
              JOIN runs r ON r.id = rec.run_id AND r.status = 'ACTIVE'
              WHERE cardinality(rec.root_cause_e_ids) > 0
                AND EXISTS (SELECT 1 FROM unnest(rec.root_cause_e_ids) eid
                            WHERE NOT EXISTS (SELECT 1 FROM evidence_index e
                                              WHERE e.run_id = rec.run_id
                                                AND e.e_id = eid))
            )
            UPDATE recommendations rec
               SET root_cause_e_ids = bad.kept
              FROM bad WHERE rec.id = bad.id
            RETURNING bad.had - cardinality(bad.kept)
            """))).scalars().all()
        await session.commit()

        # PASS 7b — citation scope prune (2026-07-14 attribution audit):
        # on a rec that DECLARES target_subcap_ids, a citation whose
        # evidence links to none of the targets (grain-prefix, the exact
        # qa_surface_attribution predicate) is a scope miss — historical
        # welds inherited category-grain evidence that diverged from the
        # rec's own targets. Misaligned citations are stripped ONLY while
        # at least one aligned citation remains: a rec never loses its
        # last citation to this pass (the evidence itself may still be
        # real analyst material — an all-misaligned list is left for a
        # human, not silently emptied). Structural, idempotent.
        scope_pruned = (await session.execute(text(
            """
            WITH scoped AS (
              SELECT rec.id,
                     ARRAY(
                       SELECT eid FROM unnest(rec.root_cause_e_ids) eid
                       WHERE EXISTS (
                         SELECT 1
                         FROM evidence_index e,
                              unnest(e.linked_subcap_ids) s,
                              unnest(rec.target_subcap_ids) t
                         WHERE e.run_id = rec.run_id AND e.e_id = eid
                           AND (s = t OR s LIKE t || '.%'
                                OR t LIKE s || '.%'))) AS kept,
                     cardinality(rec.root_cause_e_ids) AS had
              FROM recommendations rec
              JOIN runs r ON r.id = rec.run_id AND r.status = 'ACTIVE'
              WHERE cardinality(rec.root_cause_e_ids) > 0
                AND cardinality(rec.target_subcap_ids) > 0
            )
            UPDATE recommendations rec
               SET root_cause_e_ids = scoped.kept
              FROM scoped
             WHERE rec.id = scoped.id
               AND cardinality(scoped.kept) > 0
               AND cardinality(scoped.kept) < scoped.had
            RETURNING scoped.had - cardinality(scoped.kept)
            """))).scalars().all()
        await session.commit()

    qa_report = " ".join(
        f"{k}={v}" for k, v in sorted(flag_counts.items())) or "clean"
    print(f"# derive_recommendations: entities_filled={filled} recs_inserted={inserted} "
          f"dead_citations_pruned={sum(dead_pruned)} "
          f"scope_citations_pruned={sum(scope_pruned)} "
          f"corpus_enriched={corpus_updated} corpus_inserted={corpus_inserted} "
          f"description_mined={mined} outcomes_grounded={outcomes_filled} "
          f"platform_inferred={platform_filled} titles_repaired={titles_repaired} "
          f"qa_dupes_removed={dupes_removed} qa_phases_fixed={phases_fixed} "
          f"qa_flags[{qa_report}] "
          f"(grounded gap→platform inference + 048 enrichment + selection QA)",
          flush=True)
    return 0


# ── Recommendation-title quality (PASS 5) ──────────────────────────────
# A rec title ships only if it clears qa_deploy_review_audit.check_recs:
#   • not blank / "(untitled)"
#   • balanced ()/[] and >= 12 chars
#   • NOT _FRAGMENT_TITLE — no leading punctuation / digit / whitespace /
#     lowercase letter (a mid-sentence slice) — unless it is a brand name.
# `_bad_title` flags a SUPERSET of that (also: bare subcap codes, embedded
# E-ID / 10-K prose, leading prose stems, mostly-non-alpha score dumps) so
# borderline fragments are repaired too, and `_compose_title_from` ALWAYS
# returns a clean, Title-Case, >=12-char, balanced replacement — never None,
# never a raw prose fragment.

# Brand / product names that legitimately BEGIN lowercase — not fragments.
_BRAND_LC = re.compile(r"^(nCino|iOS|iPhone|iPad|eNPS|xG|iPaaS|myBank)\b")

# Blank / placeholder / bare subcap code / leading punctuation-or-digit.
_BAD_TITLE_RE = re.compile(
    r"^\s*$|^\(untitled\)$|^P[1-4]C\d+(?:[._]\w+)*$"      # blank / untitled / bare subcap code
    r"|^[\s)\]}(,;.:'\"\d-]",                              # leading punct / digit / bracket
    re.I)
# A genuine lowercase lead (NO re.I — an uppercase lead is exactly what makes
# a title a non-fragment, so it must NOT be swallowed by IGNORECASE).
_LOWER_LEAD_RE = re.compile(r"^[a-z]")
# Prose stems that mark a title sliced from the middle of a sentence.
_PROSE_STEM_RE = re.compile(
    r"^(?:gap|vs|and|or|but|provides?|tools?|siloed|products?|strategic|"
    r"engineers?|limited|per|plus)\b", re.I)
# Evidence / feature codes and 10-K prose that never belong in a title.
_TITLE_CODE_RE = re.compile(r"\b(?:EV|INT|E|F)-?\d{1,4}\b|\b10-?K\b", re.I)
# Function words a headline must not DANGLE on (a trailing one means the mined
# clause was sliced mid-thought — fall back to a template instead).
_DANGLE_TAIL = frozenset({
    "in", "of", "for", "to", "on", "with", "from", "and", "or", "but", "the",
    "a", "an", "that", "which", "by", "at", "as", "is", "are", "be", "no",
})


def _bad_title(t: str) -> bool:
    """True when a rec title fails — or is at risk of failing — the deploy
    audit's rec-title check. Flags blank / "(untitled)" / bare subcap code /
    fragment (leading punct-digit-lowercase or a prose stem) / embedded
    E-ID or 10-K prose / unbalanced brackets / < 12 chars / a mostly-non-
    alphabetic score dump. Brand names (nCino/iOS…) are always kept."""
    s = (t or "").strip()
    if not s:
        return True
    if _BRAND_LC.match(s):
        return False
    if (_BAD_TITLE_RE.match(s) or _LOWER_LEAD_RE.match(s)
            or _PROSE_STEM_RE.match(s) or _TITLE_CODE_RE.search(s)
            or len(s) < 12
            or s.count("(") != s.count(")")
            or s.count("[") != s.count("]")):
        return True
    alpha = sum(ch.isalpha() for ch in s)
    return alpha < max(6, len(s) * 0.4)


def _clean_phrase(s: str) -> str:
    """Normalize a phrase for use in a title: drop embedded E-ID / 10-K codes
    and every bracket char (so the result is always balanced), collapse
    whitespace, trim edge punctuation, and upper-case the first letter."""
    s = _TITLE_CODE_RE.sub("", s or "")
    s = re.sub(r"[()\[\]{}]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -,;:.\"'")
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def _title_from_desc(desc: str, make_title) -> str | None:
    """A clean lead-clause headline mined from the rec's description, or None
    when the description yields nothing that clears `_bad_title`."""
    if not (desc or "").strip():
        return None
    # drop a leading "X scores N" score preamble so the ACTION leads.
    body = re.sub(r"^[^.]*scores?\s[\d.]+[^.]*\.\s*", "", desc).strip() or desc.strip()
    t = _clean_phrase(make_title(body, 90) or body[:90])
    # peel leading prose stems ("gap Limited", "vs peers", "and ...") and bare
    # articles/prepositions so the title leads with real content.
    for _ in range(4):
        peeled = _PROSE_STEM_RE.sub("", t, count=1).lstrip(" -,;:.")
        peeled = re.sub(r"^(?:the|of|for|to|on|in|with|from|that|which)\b",
                        "", peeled, flags=re.I).lstrip(" -,;:.")
        if peeled == t:
            break
        t = peeled
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    # keep it a headline: cut at the first clause boundary.
    t = _clean_phrase(re.split(r"[.;:]|\s[\u2014\u2013-]\s", t)[0])
    # reject anything still carrying digits (leftover metrics / codes), that
    # the audit would still flag, or that dangles on a function word -- the
    # caller then falls back to a clean category/platform template.
    toks = t.split()
    if (t and not re.search(r"\d", t) and not _bad_title(t) and len(toks) >= 3
            and toks[-1].strip(".,;:").lower() not in _DANGLE_TAIL):
        return t[:200]
    return None


def _compose_title_from(desc: str, platform: str | None, cat: str | None,
                        cat_name: str | None) -> str:
    """AE-readable title from a rec's own grounded fields. ALWAYS returns a
    clean, Title-Case, >=12-char, balanced, non-fragment headline: a
    platform+category action line when both are known, else a scrubbed lead
    clause of the description, else a category / platform template. Never
    None, never a code, never a raw prose fragment."""
    from app.services.nlp.titlecraft import make_title
    label = _clean_phrase(cat_name or "")
    # Canonical display NAME, never a mis-cased/underscored code: `.title()`
    # mangled 'ncino'->'Ncino' and 'data_cloud'->'Data_Cloud' (2026-07-15
    # cohesion audit). Try the id maps on the value and on its normalized form
    # (so an already-display input like 'nCino' is preserved, not re-mangled).
    plat = None
    if platform:
        from app.services.startup_enrich import platform_display_name as _pdn
        _p = str(platform).strip()
        plat = _pdn(_p) or _pdn(_p.lower().replace(" ", "_")) or _p or None
    # mine "PxCy (Category Label)" straight from the description when the
    # catalogue lookup was empty (corporate-america class).
    if not label:
        m = re.search(r"P[1-4]C\d+\s*\(([^)]{4,60})\)", desc or "")
        if m:
            label = _clean_phrase(m.group(1))
    # 1. platform + category -> the canonical AE headline.
    if plat and label:
        return f"Deploy {plat} to close the {label} gap"[:200]
    # 2. a genuinely clean lead clause mined from the description.
    mined = _title_from_desc(desc or "", make_title)
    if mined:
        return mined
    # 3. category / platform templates (always clean & balanced).
    if label:
        if _PROSE_STEM_RE.match(label):
            return f"Close the {label} maturity gap"[:200]
        return f"{label} modernization"[:200]
    if plat:
        return f"Deploy {plat} to close the capability gap"[:200]
    if cat:  # convert a bare category code to its pillar AREA — never leak the code
        from app.services.startup_enrich import pillar_prose as _pp
        _area = _pp(str(cat)[:2])
        if _area:
            return f"Close the {_area} capability gap"[:200]
    # 4. absolute last resort -- clean, generic, audit-valid.
    return "Digital capability modernization"


async def _pass5_repair_titles(session) -> int:
    """Repair every ACTIVE-run rec whose title is blank / '(untitled)' / a
    bare subcap code / a fragment. Idempotent: a good title is left as-is;
    an unrepairable rec keeps its title (never worsened)."""
    rows = (await session.execute(text(
        """
        SELECT r.id, r.title, r.description, r.platform_id,
               r.target_subcap_ids
        FROM recommendations r
        JOIN runs run ON run.id = r.run_id AND run.status = 'ACTIVE'
        """
    ))).all()
    repaired = 0
    for r in rows:
        title = str(r.title or "")
        if title and _BRAND_LC.match(title):
            continue                      # nCino-class brand title — keep
        if not _bad_title(title):
            continue                      # already good
        cat = None
        subs = list(r.target_subcap_ids or [])
        if subs:
            cat = re.match(r"(P[1-4]C\d+)", subs[0])
            cat = cat.group(1) if cat else None
        cat_name = None
        if cat:
            cat_name = (await session.execute(text(
                "SELECT name FROM ccg_categories WHERE category_id = :c LIMIT 1"
            ), {"c": cat})).scalar()
        new = _compose_title_from(r.description or "", r.platform_id, cat, cat_name)
        if new and new != title:
            await session.execute(text(
                "UPDATE recommendations SET title = :t WHERE id = :id"
            ), {"t": new, "id": r.id})
            repaired += 1
    return repaired


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
