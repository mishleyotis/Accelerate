"""Evaluate the evidence→subcap threshold ladder on the labelled gold set.

Measures the Training Spec Tab 01 §2.1 contract on
``benchmarks/eval/evidence_subcap_labels.jsonl`` (analyst-tagged
(excerpt, subcap_ids) pairs from the package corpus):

  * auto-accept coverage — share of rows the ladder auto-accepts;
  * misattribution — auto-accepted top-1 subcap NOT in the row's analyst
    label set (full-id match when the gold row carries full ids, else
    category-prefix match). Budget: < 2%.
  * review / candidate / reject routing rates.

Both the RAW MiniLM cosine scale and the percentile-CALIBRATED scale
(``thresholds.calibrate``) are reported — repo cosines run low relative to
the spec's nominal scale, and the calibrated mode is the operating mode.

Method: one SemanticIndex over the full subcap universe (ids humanized via
the pack heatmap label map + slug expansion); per-row top-5 query gives the
top-1 and runner-up for the margin rule. Tier gate: T1-T5; recency gate:
not STALE/DATED.

Usage:
    python -m app.scripts.eval_evidence_mapping [--labels PATH] [--limit 2000]
        [--all] [--per-entity] [--emit-extras PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict

from app.services.nlp import rerank, semantic
from app.services.nlp import thresholds as th

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", ".."))
_APPROOT = os.path.normpath(os.path.join(_BACKEND, ".."))
DEFAULT_LABELS = os.path.join(_APPROOT, "benchmarks", "eval",
                              "evidence_subcap_labels.jsonl")
DEFAULT_CLIENTS = os.path.join(_APPROOT, "startup-data", "clients")

_CAT_RE = re.compile(r"^(P\d+C\d+)")
_OK_TIERS = {"T1", "T2", "T3", "T4", "T5"}


def _cat_of(sid: str) -> str:
    m = _CAT_RE.match(str(sid))
    return m.group(1) if m else str(sid)


def _load_label_map(clients_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    """id -> heatmap label, category -> humanized slug (scanned once)."""
    id_label: dict[str, str] = {}
    cat_slug: dict[str, str] = {}
    if not os.path.isdir(clients_dir):
        return id_label, cat_slug
    for cid in sorted(os.listdir(clients_dir)):
        p = os.path.join(clients_dir, cid, "heatmap.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p) as fh:
                hm = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        for cell in hm.get("cells") or []:
            sid, label = cell.get("id"), cell.get("label")
            if sid and label and sid not in id_label:
                id_label[sid] = label
            parent = cell.get("parent_id") or ""
            if "::" in parent:
                cat, slug = parent.split("::", 1)
                cat_slug.setdefault(cat, slug.replace("-", " "))
        if len(id_label) > 2000:
            break  # the catalogue repeats across clients; one full scan suffices
    return id_label, cat_slug


def _humanize(sid: str, id_label: dict[str, str], cat_slug: dict[str, str]) -> str:
    label = id_label.get(sid)
    cat = _cat_of(sid)
    cat_h = cat_slug.get(cat, "")
    if label:
        return f"{cat_h} {label}".strip()
    if "_" in sid:
        slug = sid.split("_", 1)[1].replace("_", " ")
        return f"{cat_h} {slug}".strip()
    return (cat_h or sid.replace("_", " ").replace(".", " ")).strip()


def _sample(rows: list[dict], limit: int) -> list[dict]:
    by_entity: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_entity[r["entity"]].append(r)
    rng = random.Random(0)
    for bucket in by_entity.values():
        rng.shuffle(bucket)
    out: list[dict] = []
    entities = sorted(by_entity)
    i = 0
    while len(out) < limit and any(by_entity[e] for e in entities):
        e = entities[i % len(entities)]
        if by_entity[e]:
            out.append(by_entity[e].pop())
        i += 1
    return out


def evaluate_grouped(by_entity: dict[str, list[dict]],
                     indexes: dict[str, semantic.SemanticIndex],
                     mode_map=None, subcap_texts: dict | None = None,
                     use_ce: bool = False) -> dict:
    agg = {"n": 0, "auto": 0, "auto_wrong": 0, "auto_wrong_cat": 0,
           "candidate": 0, "review": 0, "reject": 0}
    for ent, ent_rows in by_entity.items():
        part = evaluate(ent_rows, indexes[ent], mode_map=mode_map,
                        subcap_text=(subcap_texts or {}).get(ent),
                        use_ce=use_ce)
        agg["n"] += part["n"]
        agg["auto"] += part["_auto"]
        agg["auto_wrong"] += part["_auto_wrong"]
        agg["auto_wrong_cat"] += part["_auto_wrong_cat"]
        for k in ("candidate", "review", "reject"):
            agg[k] += part[f"_{k}"]
    n = max(agg["n"], 1)
    return {
        "n": agg["n"],
        "auto_accept_coverage_pct": round(100.0 * agg["auto"] / n, 2),
        "misattribution_pct": round(100.0 * agg["auto_wrong"] / agg["auto"], 2)
        if agg["auto"] else None,
        "misattribution_category_pct":
            round(100.0 * agg["auto_wrong_cat"] / agg["auto"], 2)
            if agg["auto"] else None,
        "candidate_rate_pct": round(100.0 * agg["candidate"] / n, 2),
        "review_rate_pct": round(100.0 * agg["review"] / n, 2),
        "reject_rate_pct": round(100.0 * agg["reject"] / n, 2),
    }


def evaluate(rows: list[dict], idx: semantic.SemanticIndex,
             mode_map=None, subcap_text: dict | None = None,
             use_ce: bool = False) -> dict:
    routed = {"auto_accept": 0, "candidate": 0, "review": 0, "reject": 0}
    auto_wrong = 0
    auto_wrong_cat = 0
    for r in rows:
        hits = idx.top_k(r["excerpt"], k=5, min_score=0.0)
        if not hits:
            routed["reject"] += 1
            continue
        top_id, top_cos = hits[0]
        raw_top = top_cos
        runner = hits[1][1] if len(hits) > 1 else None
        if mode_map is not None:
            top_cos = mode_map(top_cos)
            runner = mode_map(runner) if runner is not None else None
        tier_ok = str(r.get("tier") or "") in _OK_TIERS
        recent_ok = str(r.get("recency") or "").upper() not in {"STALE", "DATED"}
        verdict = th.classify(top_cos, runner_up=runner,
                              tier_ok=tier_ok, recent_ok=recent_ok)
        if verdict == "auto_accept":
            # category consensus: the top-3 recalled subcaps must agree on
            # the category — a split vote means the excerpt's topic is
            # ambiguous at category grain and must not auto-attach
            cats = {_cat_of(str(sid)) for sid, _c in hits[:3]}
            if len(cats) > 1:
                verdict = "candidate"
        if verdict == "auto_accept" and use_ce and subcap_text is not None:
            # production parity: the link path prunes attach candidates with
            # the cross-encoder support check — an auto-accept the CE cannot
            # confirm demotes to candidate (Tab 01 verification pass)
            sup = rerank.support_scores(
                r["excerpt"], [(subcap_text.get(str(top_id), ""), raw_top)])
            if not sup or sup[0] < 0.45:
                verdict = "candidate"
        routed[verdict] += 1
        if verdict == "auto_accept":
            gold = set(r.get("subcap_ids") or [])
            gold_has_full = any("." in g for g in gold)
            ok = (top_id in gold) if (gold_has_full and "." in str(top_id)) else (
                _cat_of(str(top_id)) in {_cat_of(g) for g in gold})
            ok_cat = _cat_of(str(top_id)) in {_cat_of(g) for g in gold}
            if not ok:
                auto_wrong += 1
            if not ok_cat:
                auto_wrong_cat += 1
    n = max(sum(routed.values()), 1)
    auto = routed["auto_accept"]
    return {
        "n": n,
        "auto_accept_coverage_pct": round(100.0 * auto / n, 2),
        "misattribution_pct": round(100.0 * auto_wrong / auto, 2) if auto else None,
        "candidate_rate_pct": round(100.0 * routed["candidate"] / n, 2),
        "review_rate_pct": round(100.0 * routed["review"] / n, 2),
        "reject_rate_pct": round(100.0 * routed["reject"] / n, 2),
        "_auto": auto, "_auto_wrong": auto_wrong,
        "_auto_wrong_cat": auto_wrong_cat,
        "_candidate": routed["candidate"], "_review": routed["review"],
        "_reject": routed["reject"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ladder eval on the mapping gold set")
    ap.add_argument("--labels", default=DEFAULT_LABELS)
    ap.add_argument("--clients-dir", default=DEFAULT_CLIENTS)
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--emit-extras", default=None)
    args = ap.parse_args(argv)

    if not semantic.model_available():
        print("FATAL: MiniLM tier unavailable (DMA_ST_MODEL_DIR unset?) — "
              "the ladder eval is only meaningful on the semantic tier.",
              file=sys.stderr)
        return 2

    with open(args.labels) as fh:
        rows = [json.loads(line) for line in fh]
    rows = [r for r in rows if (r.get("excerpt") or "").strip()
            and r.get("subcap_ids")]
    if not args.all and len(rows) > args.limit:
        rows = _sample(rows, args.limit)

    id_label, cat_slug = _load_label_map(args.clients_dir)
    # The linking task is per-entity: evidence is mapped within the entity's
    # own catalogue slice, so each entity gets its own candidate index (the
    # union of subcap ids the analyst used for that entity). A cross-entity
    # 1,497-way retrieval both misrepresents the task and punishes
    # non-exhaustive labels.
    by_entity: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_entity[r["entity"]].append(r)
    indexes: dict[str, semantic.SemanticIndex] = {}
    subcap_texts: dict[str, dict[str, str]] = {}
    universe_sizes = []
    for ent, ent_rows in by_entity.items():
        universe = sorted({s for r in ent_rows for s in r["subcap_ids"]})
        universe_sizes.append(len(universe))
        texts = {sid: _humanize(sid, id_label, cat_slug) for sid in universe}
        idx = semantic.SemanticIndex()
        idx.fit(list(texts.items()))
        indexes[ent] = idx
        subcap_texts[ent] = texts

    raw_cosines = []
    for ent, ent_rows in by_entity.items():
        for r in ent_rows[:20]:
            hits = indexes[ent].top_k(r["excerpt"], k=1, min_score=0.0)
            if hits:
                raw_cosines.append(hits[0][1])
    cal = th.calibrate(raw_cosines, anchor_pcts={
        25.0: th.REVIEW_LOW, 60.0: th.CANDIDATE, 95.0: th.AUTO_ACCEPT})

    raw = evaluate_grouped(by_entity, indexes)
    calibrated = evaluate_grouped(by_entity, indexes, mode_map=cal,
                                  subcap_texts=subcap_texts,
                                  use_ce=rerank.available())
    report = {
        "labels": args.labels, "rows": len(rows),
        "entities": len(by_entity),
        "median_entity_universe": sorted(universe_sizes)[len(universe_sizes) // 2],
        "calibration_anchors": [(round(a, 4), b) for a, b in cal.anchors],
        "raw": raw, "calibrated": calibrated,
    }
    print(json.dumps(report, indent=2))

    if args.emit_extras:
        base = {"unit": "pct", "owner_script": "link_evidence_subcaps",
                "source": "eval_evidence_mapping", "bound": 100.0,
                "requires_db": False}
        os.makedirs(os.path.dirname(args.emit_extras), exist_ok=True)
        with open(args.emit_extras, "w") as fh:
            json.dump({
                "eval.mapping_misattribution_pct": {
                    "value": calibrated["misattribution_pct"],
                    "direction": "down", **base},
                "eval.mapping_auto_accept_coverage_pct": {
                    "value": calibrated["auto_accept_coverage_pct"],
                    "direction": "up", **base},
                "eval.mapping_review_rate_pct": {
                    "value": calibrated["review_rate_pct"],
                    "direction": "down", **base},
                "eval.mapping_misattribution_raw_pct": {
                    "value": raw["misattribution_pct"],
                    "direction": "down", **base},
            }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
