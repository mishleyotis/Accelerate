"""Grade the exported pack against the Tab-09 100-point rubric.

Scores every client x surface-family instance in ``startup-data/clients``
with ``nlp.rubric100.score_item`` over the DB-less ``pack_state``. This is a
measurement tool (exit 0 always): the band histogram is the graded-QA
baseline the enhancement loop must move, REJECT items feed the negative
training set, and ``--emit-extras`` drops rubric metrics where
``benchmark_runner.collect_extras`` folds them into the next snapshot.

Usage:
    python -m app.scripts.qa_rubric_grade --clients-dir ../startup-data/clients \
        [--json] [--surfaces insights,findings,why_now,exec,focus,platforms] \
        [--emit-negatives PATH] [--emit-extras PATH] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# The rubric's G2 challenge only needs the bi-encoder; the cross-encoder's
# per-process wall-clock budget would dominate a 94-client sweep.
os.environ.setdefault("DMA_DISABLE_RERANK", "1")
from collections import Counter, defaultdict

from app.services.nlp.grader import Item
from app.services.nlp.pack_state import PackState, load_pack_state
from app.services.nlp.rubric100 import score_item

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", ".."))
DEFAULT_CLIENTS = os.path.normpath(os.path.join(
    _BACKEND, "..", "startup-data", "clients"))
_EID_RE = re.compile(r"\bE-(?:INT-)?\d{1,4}\b")

SURFACES = ("insights", "findings", "why_now", "exec", "focus", "platforms",
            "drilldowns", "evidence_segments", "roadmap")


def _numeric_leaves(obj, out: set[str] | None = None, depth: int = 0) -> set[str]:
    """Every numeric leaf in a pack row's structured fields is run-computed
    provenance (fit scores, prereq thresholds, counts, readiness values)."""
    out = out if out is not None else set()
    if depth > 6:
        return out
    if isinstance(obj, bool):
        return out
    if isinstance(obj, int | float):
        out.add(f"{obj:g}")
        out.add(str(obj))
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            _numeric_leaves(v, out, depth + 1)
    elif isinstance(obj, list):
        out.add(str(len(obj)))
        for v in obj[:200]:
            _numeric_leaves(v, out, depth + 1)
    return out
_FAMILY = {"insights": "insight_card", "findings": "finding",
           "why_now": "why_now", "exec": "exec", "focus": "focus",
           "platforms": "platform", "drilldowns": "subcap_drilldown",
           "evidence_segments": "evidence_segment", "roadmap": "roadmap"}
_DRILLDOWN_SAMPLE = 8  # widest-gap cells per client — the drawers an AE opens


def _read(clients_dir: str, cid: str, fname: str) -> dict:
    p = os.path.join(clients_dir, cid, fname)
    if not os.path.exists(p):
        return {}
    with open(p) as fh:
        return json.load(fh)


def _items_for(surface: str, clients_dir: str, cid: str,
               state: PackState) -> list[tuple[Item, dict]]:
    """Build (grader Item, siblings) rows for one surface of one client."""
    rows: list[tuple[Item, dict]] = []
    scores_sib = {"scores": state.all_score_values}
    if surface == "insights":
        for it in _read(clients_dir, cid, "insights.json").get("items") or []:
            rows.append((Item(
                surface="insight_card", title=it.get("title") or "",
                what=it.get("what_text") or "", why=it.get("why_text") or "",
                so_what=it.get("so_what_text") or "",
                anchor_subcap=it.get("linked_subcap_id"),
                e_ids=list(it.get("linked_e_ids") or [])),
                {"scores": state.all_score_values,
                 "computed_numbers": _numeric_leaves(it)}))
    elif surface == "findings":
        for tf in state.top_findings:
            rows.append((Item(
                surface="finding",
                title=tf.get("title") or tf.get("name") or "",
                # Grade the composed W/W/SW blocks the D1 FindingCard
                # actually renders; `body` is the legacy pre-decomposition
                # blob and only stands in when no composed WHAT exists.
                # (Instrument bug found 2026-07-12: body-first mapping and
                # an unmapped `why` hid the composed prose from the rubric —
                # ASK-OV6-3 "failed" on 71% of findings whose why was fine.)
                what=tf.get("what") or tf.get("body") or "",
                why=tf.get("why") or "",
                so_what=tf.get("so_what") or "",
                anchor_subcap=tf.get("subcap_id"),
                e_ids=list(tf.get("evidence") or [])),
                {"scores": state.all_score_values,
                 "computed_numbers": _numeric_leaves(tf)}))
    elif surface == "why_now":
        for sig in state.why_now_signals:
            if not isinstance(sig, dict):
                continue
            e_ids = sig.get("evidence") or []
            if isinstance(e_ids, str):
                e_ids = _EID_RE.findall(e_ids)
            rows.append((Item(
                surface="finding",  # grader cfg family; rubric family is why_now
                title=sig.get("label") or sig.get("title") or "",
                what=sig.get("detail") or sig.get("text") or "",
                why=sig.get("impact") or "",
                so_what=" ".join(str(sig.get(k) or "")
                                 for k in ("play", "risk")).strip(),
                e_ids=[e for e in e_ids if isinstance(e, str)]),
                {"scores": state.all_score_values,
                 "computed_numbers": _numeric_leaves(sig)}))
    elif surface == "exec":
        ov = _read(clients_dir, cid, "overview.json")
        md = ((ov.get("narrative") or {}).get("scqa_md")) or ""
        if md.strip():
            rows.append((Item(
                surface="exec", title="Executive summary", what=md,
                e_ids=_EID_RE.findall(md)), scores_sib))
    elif surface == "focus":
        for f in _read(clients_dir, cid, "focus_areas.json").get("items") or []:
            grounding = f.get("grounding") or {}
            e_ids = grounding.get("e_ids") if isinstance(grounding, dict) else []
            rows.append((Item(
                surface="focus", title=f.get("title") or "",
                what=f.get("verbatim_quote") or f.get("quote") or "",
                e_ids=[e for e in (e_ids or []) if isinstance(e, str)]),
                {"scores": state.all_score_values, "kpis": f.get("kpis")}))
    elif surface == "drilldowns":
        hm = _read(clients_dir, cid, "heatmap.json")
        md = (hm.get("narrative") or {}).get("per_subcap_md") or {}
        cells = {c.get("id"): c for c in hm.get("cells") or []}
        ranked = sorted(
            (sid for sid in md if sid in cells),
            key=lambda sid: (cells[sid].get("peer_gap")
                             if isinstance(cells[sid].get("peer_gap"), int | float)
                             else 0.0))
        for sid in ranked[:_DRILLDOWN_SAMPLE]:
            text = md.get(sid) or ""
            rows.append((Item(
                surface="focus",  # grader cfg neutral; rubric family below
                title=cells[sid].get("label") or sid, what=text,
                anchor_subcap=sid, e_ids=_EID_RE.findall(text)),
                {"scores": state.all_score_values,
                 "computed_numbers": _numeric_leaves(cells[sid])}))
    elif surface == "evidence_segments":
        for it in _read(clients_dir, cid, "insights.json").get("items") or []:
            e_ids = list(it.get("linked_e_ids") or [])
            rows.append((Item(
                surface="focus", title=it.get("title") or "",
                what=it.get("what_text") or "", e_ids=e_ids), scores_sib))
    elif surface == "roadmap":
        rm = _read(clients_dir, cid, "platforms_roadmap.json")
        for ph in rm.get("phases") or []:
            impact = ph.get("customer_impact")
            impact_txt = (json.dumps(impact) if isinstance(impact, dict)
                          else str(impact or ""))
            recs = [str(r) for r in (ph.get("recommendations") or [])]
            computed = _numeric_leaves(ph)
            # phase metric/target strings are run-computed renderings
            # ("P2C4 score 1.61 -> 4.0 (peer median 2.50)")
            from app.services.nlp import grader as _grader
            for key in ("metric", "target", "label"):
                computed |= set(_grader._numbers(str(ph.get(key) or "")))
            rows.append((Item(
                surface="focus",
                title=f"Phase {ph.get('phase')} {ph.get('name') or ''}",
                what=f"{ph.get('metric') or ''} {ph.get('target') or ''} "
                     f"duration {ph.get('duration_months')} months "
                     f"phase {ph.get('phase')}",
                why=impact_txt,
                e_ids=recs[:20]),
                {"scores": state.all_score_values,
                 "computed_numbers": computed}))
    elif surface == "platforms":
        for pc in _read(clients_dir, cid, "platforms.json").get("cards") or []:
            computed = _numeric_leaves(pc)
            fit = pc.get("fit_score")
            if isinstance(fit, int | float):
                computed |= {str(round(fit)), str(int(fit))}
            rows.append((Item(
                surface="platform", title=pc.get("display_name") or "",
                what=pc.get("opportunity_md") or "",
                why=pc.get("story_md") or "",
                e_ids=list(pc.get("evidence_ids") or [])),
                {"scores": state.all_score_values,
                 "computed_numbers": computed}))
    return rows


def run(clients_dir: str, surfaces: list[str], limit: int | None) -> dict:
    clients = sorted(d for d in os.listdir(clients_dir)
                     if os.path.isdir(os.path.join(clients_dir, d)))
    if limit:
        clients = clients[:limit]
    fam_bands: dict[str, Counter] = defaultdict(Counter)
    fam_totals: dict[str, list[float]] = defaultdict(list)
    fam_styles: dict[str, list[float]] = defaultdict(list)
    fam_hard: dict[str, Counter] = defaultdict(Counter)
    worst: dict[str, list] = defaultdict(list)
    negatives: list[dict] = []
    skipped: list[str] = []

    for cid in clients:
        try:
            state = load_pack_state(clients_dir, cid)
        except FileNotFoundError as exc:
            skipped.append(f"{cid}: {exc}")
            continue
        for surface in surfaces:
            family = _FAMILY[surface]
            for item, siblings in _items_for(surface, clients_dir, cid, state):
                r = score_item(item, state, surface=family, siblings=siblings)
                fam_bands[family][r.band] += 1
                fam_totals[family].append(r.total)
                fam_styles[family].append(_style_score(r))
                for hf in r.hard_fails:
                    fam_hard[family][hf] += 1
                worst[family].append((r.total, cid, item.title[:60], r.hard_fails))
                if r.band == "REJECT":
                    negatives.append({
                        "display_id": cid, "surface": family,
                        "text": item.full[:2000], "total": r.total,
                        "hard_fails": r.hard_fails,
                        "dims": r.dims,
                    })

    result: dict = {"clients": len(clients), "skipped": skipped, "families": {}}
    for family in sorted(fam_bands):
        totals = fam_totals[family]
        n = len(totals)
        bands = fam_bands[family]
        result["families"][family] = {
            "n": n,
            "mean": round(sum(totals) / n, 2) if n else None,
            "style_mean": round(sum(fam_styles[family]) / n, 2) if n else None,
            "bands": dict(bands),
            "gold_pct": round(100.0 * bands.get("GOLD", 0) / n, 2) if n else None,
            "reject_pct": round(100.0 * bands.get("REJECT", 0) / n, 2) if n else None,
            "hard_fails": dict(fam_hard[family].most_common()),
            "worst": [
                {"total": t, "client": c, "title": ti, "hard_fails": hf}
                for t, c, ti, hf in sorted(worst[family])[:5]
            ],
        }
    result["_negatives"] = negatives
    return result


def emit_extras(result: dict, path: str) -> None:
    metrics: dict = {}
    for family, f in result["families"].items():
        owner = {"finding": "deepen_narrative", "why_now": "deepen_narrative",
                 "exec": "deepen_narrative",
                 "subcap_drilldown": "derive_subcap_narratives",
                 "evidence_segment": "link_evidence_subcaps",
                 "roadmap": "derive_recommendations",
                 "platform": "recompute_platform_fit",
                 "focus": "derive_focus_areas"}.get(family, "derive_insights")
        base = {"unit": "pct", "owner_script": owner,
                "source": "qa_rubric_grade", "requires_db": False}
        metrics[f"rubric.{family}_gold_pct"] = {
            "value": f["gold_pct"], "direction": "up", "bound": 100.0, **base}
        metrics[f"rubric.{family}_mean"] = {
            "value": f["mean"], "unit": "score", "direction": "up",
            "bound": 100.0, **{k: v for k, v in base.items() if k != "unit"}}
        metrics[f"rubric.{family}_style_mean"] = {
            "value": f.get("style_mean"), "unit": "score", "direction": "up",
            "bound": 100.0, **{k: v for k, v in base.items() if k != "unit"}}
        hard_n = sum(f["hard_fails"].values())
        metrics[f"rubric.{family}_hard_fail_pct"] = {
            "value": round(100.0 * hard_n / f["n"], 2) if f["n"] else None,
            "direction": "down", "bound": 100.0, **base}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(metrics, fh, indent=2)


def grade_overlays(overlay_dir: str, clients_dir: str) -> dict:
    """Score the committed gold overlays through the SAME rubric — the
    gold-benchmark reference row script output is compared against."""
    fam_totals: dict[str, list[float]] = defaultdict(list)
    fam_style: dict[str, list[float]] = defaultdict(list)
    fam_bands: dict[str, Counter] = defaultdict(Counter)
    for fn in sorted(os.listdir(overlay_dir)):
        if not fn.endswith(".json"):
            continue
        cid = fn[:-5]
        try:
            state = load_pack_state(clients_dir, cid)
        except FileNotFoundError:
            continue
        with open(os.path.join(overlay_dir, fn)) as fh:
            overlay = json.load(fh)
        cards = overlay.get("insight_cards") or {}
        card_iter = cards.values() if isinstance(cards, dict) else cards
        for it in card_iter:
            if not isinstance(it, dict):
                continue
            item = Item(surface="insight_card", title=it.get("title") or "",
                        what=it.get("what_text") or "",
                        why=it.get("why_text") or "",
                        so_what=it.get("so_what_text") or "",
                        anchor_subcap=it.get("linked_subcap_id"),
                        e_ids=list(it.get("linked_e_ids") or []))
            r = score_item(item, state, surface="insight_card",
                           siblings={"scores": state.all_score_values,
                                     "computed_numbers": _numeric_leaves(it)})
            fam_totals["insight_card"].append(r.total)
            fam_bands["insight_card"][r.band] += 1
            fam_style["insight_card"].append(_style_score(r))
        for tf in overlay.get("top_findings") or []:
            if not isinstance(tf, dict):
                continue
            item = Item(surface="finding",
                        title=tf.get("name") or tf.get("title") or "",
                        # same composed-first mapping as the corpus grade —
                        # the bar and the corpus must read the same fields
                        what=tf.get("what") or tf.get("body") or "",
                        why=tf.get("why") or "",
                        so_what=tf.get("so_what") or "",
                        e_ids=list(tf.get("evidence") or []))
            r = score_item(item, state, surface="finding",
                           siblings={"scores": state.all_score_values,
                                     "computed_numbers": _numeric_leaves(tf)})
            fam_totals["finding"].append(r.total)
            fam_bands["finding"][r.band] += 1
            fam_style["finding"].append(_style_score(r))
    return {
        fam: {"n": len(totals), "mean": round(sum(totals) / len(totals), 2),
              "style_mean": round(sum(fam_style[fam]) / len(totals), 2),
              "bands": dict(fam_bands[fam])}
        for fam, totals in fam_totals.items() if totals
    }


def _style_score(r) -> float:
    """Grounding-independent quality: the dimensions comparable across runs
    (overlay E-IDs are scoped to the run they were authored against, so
    run-scoped grounding hard-fails are expected on historical gold)."""
    from app.services.nlp.rubric100 import WEIGHTS
    dims = ("specificity", "value_led", "self_interrogation", "peer_context")
    got = sum(r.dims.get(d, 0.0) for d in dims)
    top = sum(WEIGHTS[d] for d in dims)
    return 100.0 * got / top


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tab-09 rubric grade over the pack")
    ap.add_argument("--clients-dir", default=DEFAULT_CLIENTS)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--surfaces", default=",".join(SURFACES))
    ap.add_argument("--emit-negatives", default=None)
    ap.add_argument("--emit-extras", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--grade-overlays", action="store_true",
                    help="score the gold overlays themselves — the benchmark "
                         "reference row")
    ap.add_argument("--overlay-dir", default=os.path.normpath(os.path.join(
        _BACKEND, "..", "startup-data", "refinement")))
    args = ap.parse_args(argv)

    if args.grade_overlays:
        ref = grade_overlays(args.overlay_dir, args.clients_dir)
        print("# GOLD-BENCHMARK REFERENCE (the 5 committed overlays, same rubric)")
        print("# (mean = full rubric under CURRENT-run grounding — historical")
        print("#  E-IDs hard-fail by design; style_mean = the run-independent")
        print("#  quality bar: specificity+value_led+ask+peer, /100)")
        for fam, f in ref.items():
            print(f"  {fam:14} n={f['n']:4} mean={f['mean']:6.1f} "
                  f"style_mean={f['style_mean']:6.1f}  {f['bands']}")
        return 0

    surfaces = [s.strip() for s in args.surfaces.split(",") if s.strip() in SURFACES]
    result = run(args.clients_dir, surfaces, args.limit)
    negatives = result.pop("_negatives")

    if args.emit_negatives:
        os.makedirs(os.path.dirname(args.emit_negatives) or ".", exist_ok=True)
        with open(args.emit_negatives, "a") as fh:
            for row in negatives:
                fh.write(json.dumps(row) + "\n")
    if args.emit_extras:
        emit_extras(result, args.emit_extras)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"# TAB-09 RUBRIC GRADE — {result['clients']} clients")
        for family, f in result["families"].items():
            bands = " ".join(f"{b}:{n}" for b, n in sorted(f["bands"].items()))
            print(f"  {family:14} n={f['n']:5} mean={f['mean']:6.1f} "
                  f"style={f['style_mean']:6.1f} "
                  f"gold={f['gold_pct']:5.1f}% reject={f['reject_pct']:5.1f}%  [{bands}]")
            if f["hard_fails"]:
                print(f"  {'':14} hard_fails: {f['hard_fails']}")
        for s in result["skipped"][:5]:
            print(f"  skipped: {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
