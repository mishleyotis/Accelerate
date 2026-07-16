"""QA — per-surface evidence-ATTRIBUTION fidelity on the live corpus.

The 2026-07-09 audit found surface populators attaching evidence/subcap links
by regex, token overlap, SQL join or recency — never verifying the link is
ABOUT the thing it decorates (issue→subcap 40.5% unrelated, meeting-prep
bundle 51.5% off-topic, timeline attach 15.8% below floor). Those attachments
are what the AE clicks as "the evidence for this claim", so a wrong one is a
misattribution the UI presents as grounding.

The metric is MECHANISM-AWARE — judging every attachment by text similarity
would both miss real defects and flag correct data:

* GUESSED attachments (a model/heuristic chose the link) are judged
  SEMANTICALLY with the same cross-encoder fusion the derive-path write gates
  use — fidelity = fraction of sampled links at/above the 0.30 support floor.
  Surfaces: issues (CSV category codes, CE-healed by derive_issues), timeline
  (derive-attached ``evidence_e_ids`` — ingest-declared ``e_id`` rows are
  excluded: they are the event's literal source by construction),
  subcap_narr, meeting_prep (MiniLM vs the brief's topic).

* DECLARED attachments (the analyst/document names the link explicitly) are
  judged STRUCTURALLY — the citation must resolve and stay consistent — and
  are never semantically pruned: the document is the ground truth. Surfaces:
  recs (root_cause_e_ids must resolve in evidence_index and, when the rec has
  target_subcap_ids, the cited evidence must link at-or-under a target — the
  evidence→subcap links themselves are CE-verified by link_evidence_subcaps),
  focus (involved_subcap_ids are subcap ids written IN the profile document;
  fidelity = fraction resolving in the run's catalogue).

Usage:
  export DATABASE_URL=postgresql+asyncpg://...   (models via DMA_ST_MODEL_DIR/…)
  python -m app.scripts.qa_surface_attribution [--surfaces a,b] [--sample N]
  python -m app.scripts.qa_surface_attribution --min-fidelity 0.95   # CI gate

Exit code: 0 in report mode; with --min-fidelity, 1 when any measured surface
with >= 20 samples falls below the bar. Empty surfaces report n=0 and never
fail. Cold NLP tier: semantic surfaces are skipped (nothing meaningful to
measure lexically); structural surfaces still run.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text

from app.database import get_sessionmaker

FLOOR = 0.30
_SAMPLE = 300


def _fused_many(idx, topic: str, cands: list[str]) -> list[float]:
    """Cross-encoder fused support for one topic against many candidates —
    the SAME judge the derive-path write gates use, batched per topic."""
    from app.services.nlp import rerank
    return rerank.support_scores(
        topic, [(c, idx.relevance(topic, c)) for c in cands])


async def _names_for(session, versions: set[str]) -> dict[tuple[str, str], str]:
    names: dict[tuple[str, str], str] = {}
    for cv in sorted(v for v in versions if v):
        for c in (await session.execute(text(
            "SELECT subcap_id, name, COALESCE(description,'') AS d "
            "FROM ccg_subcaps WHERE version = :v"), {"v": cv})).all():
            names[(cv, c.subcap_id)] = f"{c.name}. {c.d}"[:240]
    return names


def _grain_cands(names, cv: str, sid: str) -> list[str]:
    """Exact leaf text, or up to 12 leaf texts under a category-grain id."""
    if (cv, sid) in names:
        return [names[(cv, sid)]]
    return [t for (v, s), t in names.items()
            if v == cv and s.startswith(sid + ".")][:12]


# ── GUESSED surfaces — semantic (CE fusion) ────────────────────────────────
async def measure_issues(session, idx, sample: int) -> tuple[int, int]:
    rows = (await session.execute(text("""
        SELECT ir.title, ir.rationale, ir.linked_subcap_ids,
               r.ccg_catalog_version AS cv
        FROM issue_register ir
        JOIN runs r ON r.id = ir.run_id
        JOIN entities e ON e.id = r.entity_id
        WHERE e.status='ACTIVE' AND COALESCE(ir.kind,'client')='client'
          AND array_length(ir.linked_subcap_ids,1) > 0
        ORDER BY ir.id LIMIT :n"""), {"n": sample})).all()
    names = await _names_for(session, {r.cv for r in rows})
    n = ok = 0
    for r in rows:
        txt = f"{r.title or ''}. {(r.rationale or '')[:280]}".strip(". ")
        if len(txt) < 12 or not r.cv:
            continue
        for sid in r.linked_subcap_ids[:6]:
            cands = _grain_cands(names, r.cv, sid)
            if not cands:
                continue
            n += 1
            ok += int(max(_fused_many(idx, txt, cands)) >= FLOOR)
    return n, ok


async def measure_timeline(session, idx, sample: int) -> tuple[int, int]:
    # derive-attached (guessed) rows ONLY: an ingest-declared te.e_id is the
    # event's literal source by construction and is not a guess to score.
    rows = (await session.execute(text("""
        SELECT te.title, te.body, te.evidence_e_ids, te.entity_id
        FROM timeline_events te
        JOIN entities e ON e.id = te.entity_id AND e.status = 'ACTIVE'
        WHERE array_length(te.evidence_e_ids,1) > 0 AND te.e_id IS NULL
        ORDER BY te.id LIMIT :n"""), {"n": sample})).all()
    n = ok = 0
    for r in rows:
        txt = f"{r.title or ''} {(r.body or '')[:240]}".strip()
        if len(txt) < 12:
            continue
        exc = (await session.execute(text("""
            SELECT COALESCE(excerpt,'') AS x FROM evidence_index
            WHERE entity_id = :eid AND e_id = ANY(:ids)
              AND length(COALESCE(excerpt,'')) > 40 LIMIT 3"""),
            {"eid": r.entity_id, "ids": list(r.evidence_e_ids)[:3]})).all()
        if not exc:
            continue
        sups = _fused_many(idx, txt, [row.x[:400] for row in exc])
        n += len(sups)
        ok += sum(int(s >= FLOOR) for s in sups)
    return n, ok


async def measure_subcap_narr(session, idx, sample: int) -> tuple[int, int]:
    rows = (await session.execute(text("""
        SELECT sn.narrative_md, sn.subcap_id, r.ccg_catalog_version AS cv
        FROM subcap_narratives sn
        JOIN runs r ON r.id = sn.run_id AND r.status='ACTIVE'
        WHERE length(COALESCE(sn.narrative_md,'')) > 60
        ORDER BY sn.id LIMIT :n"""), {"n": sample})).all()
    names = await _names_for(session, {r.cv for r in rows})
    n = ok = 0
    for r in rows:
        cap = names.get((r.cv, r.subcap_id))
        if not cap:
            continue
        n += 1
        ok += int(_fused_many(idx, cap, [r.narrative_md[:400]])[0] >= FLOOR)
    return n, ok


async def measure_meeting_prep(session, idx, sample: int) -> tuple[int, int]:
    from app.services.intelligence_builder import _ctx_meeting_prep
    dids = [r.display_id for r in (await session.execute(text(
        "SELECT e.display_id FROM entities e JOIN runs r ON r.entity_id=e.id "
        "AND r.status='ACTIVE' WHERE e.status='ACTIVE' "
        "ORDER BY e.display_id LIMIT 12"))).all()]
    n = ok = 0
    for did in dids:
        ctx = await _ctx_meeting_prep(session, did)
        topic = " ".join(filter(None, [
            str(ctx.get("entity_name") or ""),
            str(ctx.get("top_findings") or ""),
            str(ctx.get("scqa_situation") or "")[:280]])).strip()
        lines = [ln for ln in str(ctx.get("recent_evidence") or "").splitlines()
                 if ln.startswith("- E-")]
        if len(topic) < 12:
            continue
        for ln in lines:
            n += 1
            ok += int(idx.relevance(topic, ln[:400]) >= FLOOR)
        if n >= sample:
            break
    return n, ok


# ── DECLARED surfaces — structural ─────────────────────────────────────────
async def measure_recs(session, idx, sample: int) -> tuple[int, int]:
    """A rec's cited root-cause E-ID is valid when it RESOLVES in the run's
    evidence_index and, when the rec declares target_subcap_ids, the cited
    evidence links at-or-under a target (grain-prefix; those evidence→subcap
    links are themselves CE-verified by link_evidence_subcaps)."""
    rows = (await session.execute(text("""
        SELECT rec.root_cause_e_ids, rec.target_subcap_ids, rec.run_id
        FROM recommendations rec
        JOIN runs r ON r.id = rec.run_id AND r.status = 'ACTIVE'
        WHERE array_length(rec.root_cause_e_ids,1) > 0
        ORDER BY rec.id LIMIT :n"""), {"n": sample})).all()
    n = ok = 0
    for r in rows:
        ev = (await session.execute(text("""
            SELECT e_id, linked_subcap_ids FROM evidence_index
            WHERE run_id = :rid AND e_id = ANY(:ids)"""),
            {"rid": r.run_id, "ids": list(r.root_cause_e_ids)[:6]})).all()
        by_id = {e.e_id: list(e.linked_subcap_ids or []) for e in ev}
        targets = [t for t in (r.target_subcap_ids or []) if t]
        for eid in list(r.root_cause_e_ids)[:6]:
            n += 1
            linked = by_id.get(eid)
            if linked is None:
                continue                       # unresolvable citation → fail
            if not targets:
                ok += 1                        # resolves; no declared scope
                continue
            ok += int(any(s == t or s.startswith(t + ".") or t.startswith(s + ".")
                          for s in linked for t in targets))
    return n, ok


async def measure_focus(session, idx, sample: int) -> tuple[int, int]:
    """Focus-area subcap ids are DECLARED in the profile document text —
    fidelity = fraction resolving in the run's catalogue (grain-aware)."""
    rows = (await session.execute(text("""
        SELECT fa.involved_subcap_ids, r.ccg_catalog_version AS cv
        FROM focus_areas fa
        JOIN runs r ON r.id = fa.run_id
        JOIN entities e ON e.id = r.entity_id AND e.status='ACTIVE'
        WHERE array_length(fa.involved_subcap_ids,1) > 0
        ORDER BY fa.id LIMIT :n"""), {"n": sample})).all()
    names = await _names_for(session, {r.cv for r in rows})
    n = ok = 0
    for r in rows:
        if not r.cv:
            continue
        for sid in r.involved_subcap_ids[:6]:
            n += 1
            ok += int(bool(_grain_cands(names, r.cv, sid)))
    return n, ok


_SEMANTIC = {
    "issues": measure_issues,
    "timeline": measure_timeline,
    "subcap_narr": measure_subcap_narr,
    "meeting_prep": measure_meeting_prep,
}
_STRUCTURAL = {
    "recs": measure_recs,
    "focus": measure_focus,
}
_SURFACES = {**_SEMANTIC, **_STRUCTURAL}


async def main_async(args: argparse.Namespace) -> int:
    from app.services.nlp import rerank
    from app.services.nlp.semantic import SemanticIndex, model_available
    hot = model_available()
    print(f"# tiers: minilm={hot} ce={rerank.available()}  floor={FLOOR}")
    idx = SemanticIndex() if hot else None
    wanted = [s.strip() for s in args.surfaces.split(",")] if args.surfaces \
        else list(_SURFACES)
    failures: list[str] = []
    sm = get_sessionmaker()
    for name in wanted:
        fn = _SURFACES.get(name)
        if fn is None:
            print(f"#   {name}: unknown surface — skipped")
            continue
        if name in _SEMANTIC and not hot:
            print(f"#   {name:13} SKIPPED (semantic surface, NLP tier cold)")
            continue
        async with sm() as session:
            n, ok = await fn(session, idx, args.sample)
        fid = (ok / n) if n else None
        kind = "semantic" if name in _SEMANTIC else "structural"
        print(f"#   {name:13} [{kind:10}] n={n:4}  fidelity="
              f"{f'{fid:.3f}' if fid is not None else 'n/a (no rows)'}",
              flush=True)
        if args.min_fidelity is not None and n >= 20 and fid is not None \
                and fid < args.min_fidelity:
            failures.append(f"{name}={fid:.3f}")
    if failures:
        print(f"# SURFACE-ATTRIBUTION GATE: FAIL "
              f"(below {args.min_fidelity}): {', '.join(failures)}")
        return 1
    print("# SURFACE-ATTRIBUTION: PASS" if args.min_fidelity is not None
          else "# SURFACE-ATTRIBUTION: report complete")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--surfaces", default=None,
                   help="comma list (default: all): " + ",".join(_SURFACES))
    p.add_argument("--sample", type=int, default=_SAMPLE)
    p.add_argument("--min-fidelity", type=float, default=None,
                   help="gate: fail when any measured surface (n>=20) is below")
    args = p.parse_args()
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
