"""Train the report-section classifier from the A2 gold (offline).

Deployed as the local fallback in ``assessment_report.classify_heading``: the
regex dictionary stays primary (high precision); when it returns ``"other"`` the
model predicts a canonical kind above a confidence gate (else stays ``"other"``).

Eval: the model is trained + cross-validated ONLY on rows with a real kind
(regex weak-labels + operator-curated), excluding the un-approved ``other`` rows.
Because most training labels are regex-derived, CV measures how well the model
GENERALISES the regex + curated rules to unseen headings (the production value —
it must resolve headings the regex misses). Shipped artifact trains on all
labelled rows → ``app/ml/models/report_section_v1.joblib``.

Usage:  python -m app.ml.training.train_report_section
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def _build_pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.preprocessing import FunctionTransformer

    from app.ml.report_section_features import pillar_features
    word = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)
    # Explicit pillar-number one-hot: the CV error set was 12/14 pillar
    # confusions on headings whose suffix is identical across the four
    # deep-dive classes ("P{n} Capability Scorecard") — the decisive
    # token needs its own column, not a 1/20000 TF-IDF weight.
    pillar = FunctionTransformer(pillar_features, validate=False)
    return Pipeline([
        ("feats", FeatureUnion([("word", word), ("char", char),
                                ("pillar", pillar)])),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=4.0, random_state=0)),
    ])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gold", default="tests/fixtures/ml/report_section_labels.jsonl")
    ap.add_argument("--out", default="app/ml/models/report_section_v1.joblib")
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    try:
        import joblib
        from sklearn import __version__ as skver
        from sklearn.metrics import accuracy_score, f1_score
        from sklearn.model_selection import cross_val_predict
    except ImportError as e:
        print(f"ERROR: sklearn/joblib required: {e}", file=sys.stderr)
        return 2

    gold = Path(args.gold)
    rows = [json.loads(ln) for ln in gold.read_text(encoding="utf-8").splitlines() if ln.strip()]
    labeled = [r for r in rows if r["section_kind"] != "other"]
    # keep only classes with >=3 members so CV folds are valid
    counts = Counter(r["section_kind"] for r in labeled)
    keep = {k for k, n in counts.items() if n >= 3}
    train = [r for r in labeled if r["section_kind"] in keep]
    dropped = [k for k in counts if k not in keep]
    X = [r["heading"] for r in train]
    y = [r["section_kind"] for r in train]
    print(f"# gold: {len(rows)} headings, {len(labeled)} labelled (non-other), "
          f"{len(train)} in {len(keep)} classes with n>=3 "
          f"(dropped tiny: {dropped or 'none'})")

    cvpred = cross_val_predict(_build_pipeline(), X, y, cv=3)
    acc = accuracy_score(y, cvpred)
    f1 = f1_score(y, cvpred, average="macro", zero_division=0)
    print(f"## 3-fold CV over {len(train)} labelled headings: acc={acc:.3f} macro-F1={f1:.3f}")
    print(f"## class distribution: {dict(sorted(counts.items(), key=lambda x:-x[1]))}")

    final = _build_pipeline()
    final.fit(X, y)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, out)
    meta = {
        "name": "report_section", "version": args.version, "sklearn_version": skver,
        "classes": sorted(keep), "n_train": len(train),
        "train_data_sha256": hashlib.sha256(gold.read_bytes()).hexdigest(),
        "artifact_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "cv": {"acc": round(acc, 4), "macro_f1": round(f1, 4)},
        "feature": "word(1,2)+char_wb(3,5) TF-IDF",
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"# wrote {out} ({out.stat().st_size} bytes) + meta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
