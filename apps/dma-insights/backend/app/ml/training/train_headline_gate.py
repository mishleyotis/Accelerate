"""Train the headline/So-What quality gate (Training Spec Tab 01 §2.2).

Three binary heads over TF-IDF word(1,2)+char_wb(3,5) features:
  * gold_reject — the pre-ship gate; spec bar: macro-F1 >= 0.9 on the
    gold/reject set, evaluated entity-disjoint (GroupKFold pooled
    out-of-fold predictions so the overlay-heavy gold class can't leak);
  * vendor_first / threat_tone — rule-labelled auxiliary heads that
    generalize the deterministic regexes.

Artifacts: ``app/ml/models/headline_gate_v1.joblib`` (dict of fitted
pipelines) + ``.meta.json`` (per-head pooled-OOF precision/recall/F1).

Usage:
    python -m app.ml.training.train_headline_gate [--labels PATH]
        [--out-dir app/ml/models] [--emit-extras PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import FunctionTransformer

from app.ml.headline_features import numeric_features

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
DEFAULT_LABELS = os.path.join(_BACKEND, "tests", "fixtures", "ml",
                              "headline_labels.jsonl")
DEFAULT_OUT = os.path.join(_BACKEND, "app", "ml", "models")


def _pipeline(c: float = 4.0) -> Pipeline:
    return Pipeline([
        ("features", FeatureUnion([
            ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                                     min_df=2)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                     sublinear_tf=True, min_df=2)),
            ("shape", FunctionTransformer(numeric_features)),
        ])),
        ("clf", LogisticRegression(class_weight="balanced", max_iter=2000,
                                   C=c, random_state=0)),
    ])


def _oof_eval(texts: list[str], y: list[int], groups: list[str],
              c: float, n_splits: int = 5) -> dict:
    y_arr = np.asarray(y)
    preds = np.zeros(len(y), dtype=int)
    gkf = GroupKFold(n_splits=min(n_splits, len(set(groups))))
    for train_idx, test_idx in gkf.split(texts, y_arr, groups):
        if len(set(y_arr[train_idx])) < 2:
            continue
        pipe = _pipeline(c)
        pipe.fit([texts[i] for i in train_idx], y_arr[train_idx])
        preds[test_idx] = pipe.predict([texts[i] for i in test_idx])
    p, r, f1, _ = precision_recall_fscore_support(
        y_arr, preds, average="macro", zero_division=0)
    return {"p": round(float(p), 4), "r": round(float(r), 4),
            "f1": round(float(f1), 4), "n": len(y),
            "n_pos": int(y_arr.sum()), "C": c}


def train(labels_path: str, out_dir: str) -> dict:
    with open(labels_path) as fh:
        rows = [json.loads(line) for line in fh]
    # Synthetic threat-injection rows exist to teach the threat head the
    # doom-clause boundary; in the gold/reject head they would label
    # otherwise-gold prose as reject and blur the quality boundary.
    natural = [r for r in rows if r.get("source") != "synthetic"]
    heads: dict[str, tuple[list[dict], list[int]]] = {
        "gold_reject": (natural,
                        [1 if r["label"] == "gold" else 0 for r in natural]),
        "vendor_first": (natural,
                         [1 if "vendor_first" in r["flags"] else 0
                          for r in natural]),
        "threat_tone": (rows,
                        [1 if "threat_tone" in r["flags"]
                         or r.get("source") == "synthetic" else 0
                         for r in rows]),
    }
    metrics: dict[str, dict] = {}
    artifact: dict[str, Pipeline] = {}
    for head, (head_rows, y) in heads.items():
        # surface-conditioned text: a terse gold HEADLINE and a one-liner
        # reject SO-WHAT are lexically close; the surface token separates them
        texts = [f"[{r['surface']}] {r['text']}" for r in head_rows]
        groups = [r["entity"] for r in head_rows]
        if sum(y) < 5 or sum(y) > len(y) - 5:
            metrics[head] = {"skipped": "class too small", "n_pos": sum(y)}
            continue
        best = max((_oof_eval(texts, y, groups, c) for c in (1.0, 4.0, 8.0)),
                   key=lambda m: m["f1"])
        metrics[head] = best
        pipe = _pipeline(best["C"])
        pipe.fit(texts, y)
        artifact[head] = pipe

    os.makedirs(out_dir, exist_ok=True)
    model_path = os.path.join(out_dir, "headline_gate_v1.joblib")
    joblib.dump(artifact, model_path)
    with open(labels_path, "rb") as fh:
        data_sha = hashlib.sha256(fh.read()).hexdigest()
    with open(model_path, "rb") as fh:
        artifact_sha = hashlib.sha256(fh.read()).hexdigest()
    meta = {
        "name": "headline_gate", "version": "v1",
        "sklearn_version": sklearn.__version__,
        "classes": ["reject", "gold"], "n_train": len(rows),
        "n_natural": len(natural),
        "train_data_sha256": data_sha, "artifact_sha256": artifact_sha,
        "cv": metrics,
        "feature": "word(1,2)+char_wb(3,5) TF-IDF; GroupKFold by entity",
    }
    with open(model_path.replace(".joblib", ".meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="train the headline gate")
    ap.add_argument("--labels", default=DEFAULT_LABELS)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--emit-extras", default=None)
    args = ap.parse_args(argv)
    meta = train(args.labels, args.out_dir)
    print(json.dumps(meta["cv"], indent=2))
    f1 = (meta["cv"].get("gold_reject") or {}).get("f1")
    if args.emit_extras:
        os.makedirs(os.path.dirname(args.emit_extras), exist_ok=True)
        with open(args.emit_extras, "w") as fh:
            json.dump({"ml.headline_gate_gold_reject_f1": {
                "value": f1, "unit": "f1", "direction": "up",
                "owner_script": "train_headline_gate",
                "source": "headline_gate_v1.meta.json", "bound": 1.0,
                "requires_db": False}}, fh, indent=2)
    if f1 is not None:
        print(f"gold/reject macro-F1 = {f1} "
              f"({'MEETS' if f1 >= 0.9 else 'BELOW'} the 0.9 spec bar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
