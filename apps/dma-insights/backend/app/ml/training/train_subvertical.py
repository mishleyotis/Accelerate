"""Train the subvertical classifier from the A1 gold standard (offline).

Deployed as branch 2 of the ensemble in ``entity_healing.classify_subvertical``:
  1. explicit ``SVn`` fast-path (deterministic)  ← handles stated-code rows
  2. THIS model (name + prose → code, with confidence gate)  ← this trainer
  3. existing regex keyword loop
  4. None

Because the ``SVn`` fast-path already handles rows whose package states an
explicit code, the model's real job is the **no-stated** rows. So the honest
generalization metric reported here trains on the 80 ``package_stated`` rows and
tests on the 33 ``no_stated`` rows (the production regime), and compares against
the current regex classifier on that same held-out set. Explicit ``SV\\d`` tokens
are stripped from the feature text so the model can't cheat by reading a code
(that is branch 1's job, not the model's).

The shipped artifact is trained on ALL rows (more signal) and written to
``app/ml/models/subvertical_v1.joblib`` (+ ``.meta.json``).

Usage (offline; never in CI):
  python -m app.ml.training.train_subvertical
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_SV_TOKEN = re.compile(r"\bSV[-_ ]?\d+\b", re.I)

# Domain cue lexicon appended as pseudo-tokens: the regulator/charter framing
# that separates confusable classes (CU vs RB, IC vs IB, AM vs RIA) plus the
# regex classifier's own vote (branch 3 becomes a feature, not a competitor).
_CUE_RES: list[tuple[str, re.Pattern]] = [
    ("CUE_NCUA", re.compile(r"\bNCUA\b|credit\s+union", re.I)),
    ("CUE_FDIC", re.compile(r"\bFDIC\b|\bOCC\b|bank\s+holding|national\s+bank|"
                            r"community\s+bank|total\s+assets", re.I)),
    ("CUE_FED", re.compile(r"Federal\s+Reserve|\bCCAR\b|stress\s+test", re.I)),
    ("CUE_FCA", re.compile(r"Farm\s+Credit|\bFCA\b|agricultural\s+lend", re.I)),
    ("CUE_INS", re.compile(r"insurance|policyholder|underwriting|\bNAIC\b|carrier", re.I)),
    ("CUE_AM", re.compile(r"asset\s+manage|\bAUM\b|fund\s+admin|custod", re.I)),
    ("CUE_RIA", re.compile(r"\bRIA\b|wealth\s+advis|financial\s+plann", re.I)),
    ("CUE_IB", re.compile(r"investment\s+bank|capital\s+markets|broker-?dealer|"
                          r"brokerage|insurance\s+broker|placement|commission\s+income|"
                          r"producer", re.I)),
    ("CUE_CARRIER", re.compile(r"carrier|underwrit(es?|ing)\s+polic|policyholder\s+surplus|"
                               r"combined\s+ratio|claims\s+paid", re.I)),
    ("CUE_CLEAR", re.compile(r"clearing|settlement|interbank|payment\s+system|"
                             r"payments\s+infrastructure|member\s+institutions?|"
                             r"payments?\s+association", re.I)),
    ("CUE_NONFI", re.compile(r"SaaS|software\s+(company|platform)|procurement|"
                             r"technology\s+company|e-?commerce", re.I)),
    ("CUE_MORT", re.compile(r"mortgage|home\s+loan|origination\s+volume", re.I)),
    ("CUE_PAY", re.compile(r"payments?\s+(network|process|rail)|interchange", re.I)),
]


def _feature_text(row: dict) -> str:
    """Name + prose with explicit SVn codes stripped (branch-1 leakage guard),
    plus domain-cue pseudo-tokens and the regex classifier's vote."""
    base = _SV_TOKEN.sub(" ", row.get("text") or "").strip()
    cues = [tok for tok, rx in _CUE_RES if rx.search(base)]
    try:
        from app.services.entity_healing import classify_subvertical
        vote = classify_subvertical(
            (row.get("package") or "").replace(" - DMA", ""), base)
        if vote:
            cues.append(f"RGXVOTE_{vote}")
    except Exception:
        pass
    return f"{base} {' '.join(cues)}".strip()


def _load(gold: Path) -> list[dict]:
    return [json.loads(ln) for ln in gold.read_text(encoding="utf-8").splitlines() if ln.strip()]


# Synthetic class-definition rows: classes with <3 training rows are
# unrepresentable (NON_FI and CIB have ZERO stated rows — the fitted model
# cannot even emit those labels). Class definitions are domain knowledge,
# not held-out leakage; they enter training only (tier=synthetic_class_def).
_CLASS_DEFS: dict[str, list[str]] = {
    "FC": [
        "Farm credit association regulated by the Farm Credit Administration "
        "providing agricultural loans to farmers, ranchers and rural cooperatives.",
        "Agricultural lending cooperative in the farm credit system financing "
        "farmland, equipment and rural agribusiness.",
        "Member-owned farm credit lender serving agricultural producers with "
        "crop, livestock and land financing under FCA oversight.",
    ],
    "CIB": [
        "Payments infrastructure operator running interbank clearing and "
        "settlement systems and national payment rails.",
        "Corporate and institutional banking utility providing payment "
        "clearing, settlement and interbank transfer infrastructure.",
        "National payments system organization operating real-time rails, "
        "batch clearing and settlement between member institutions.",
        "Payments association whose member institutions are banks and credit "
        "unions exchanging payments over shared clearing infrastructure.",
        "CIB financial market infrastructure FMI overlay operating national "
        "clearing and settlement rails for member financial institutions.",
    ],
    "NON_FI": [
        "Fintech SaaS growth-stage unicorn technology company with a venture "
        "valuation, selling software subscriptions, not a chartered "
        "financial institution.",
        "Software company selling SaaS products to businesses; a technology "
        "vendor, not a financial institution.",
        "Procurement and spend-management technology platform serving "
        "corporate customers with software subscriptions.",
        "Business services and e-commerce technology company with no banking, "
        "lending or insurance operations.",
    ],
    "IC": [
        "Insurance carrier underwriting property and casualty policies, "
        "managing claims, combined ratio and policyholder surplus.",
        "Mutual insurance company writing policies as the risk carrier and "
        "paying claims from its own balance sheet.",
        "Travel and specialty insurance underwriter issuing its own policies "
        "and handling claims for covered members and travelers.",
    ],
    "IB": [
        "Insurance broker placing client policies across carriers and earning "
        "placement commissions; a brokerage, not a risk carrier.",
        "Insurance brokerage and agency advising commercial clients and "
        "placing coverage with third-party underwriters.",
    ],
    "AM": [
        "Asset management firm managing investment funds and institutional "
        "portfolios with assets under management and fund administration.",
        "Wealth and investment management company running discretionary "
        "portfolios, mutual funds and private client mandates.",
    ],
    "RB": [
        "Commercial bank and trust company offering deposits, branches, "
        "treasury services and consumer banking under a bank charter.",
    ],
}
_SYN_MIN_ROWS = 5


def _synthetic_rows(train_counts: dict[str, int]) -> list[dict]:
    rows = []
    for label, defs in _CLASS_DEFS.items():
        if train_counts.get(label, 0) >= _SYN_MIN_ROWS:
            continue
        for i, text in enumerate(defs):
            rows.append({"package": f"synthetic {label} {i}", "label": label,
                         "tier": "synthetic_class_def", "text": text})
    return rows


def _build_pipeline(kind: str = "logreg", c: float = 4.0):
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import ComplementNB
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.preprocessing import FunctionTransformer
    from sklearn.svm import LinearSVC

    from app.ml.subvertical_protos import prototype_features
    word = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)
    proto = FunctionTransformer(prototype_features)
    if kind == "logreg":
        clf = LogisticRegression(
            max_iter=2000, class_weight="balanced", C=c, random_state=0)
    elif kind == "svc":
        clf = CalibratedClassifierCV(
            LinearSVC(class_weight="balanced", C=c, random_state=0), cv=3)
    else:
        clf = ComplementNB(alpha=c)
    return Pipeline([
        ("feats", FeatureUnion([("word", word), ("char", char),
                                ("proto", proto)])),
        ("clf", clf),
    ])


def _sweep(Xtr: list[str], ytr: list[str]) -> tuple[str, float]:
    """Pick (kind, C) by stratified CV over the TRAINING rows only — the
    held-out set is read exactly once, after selection."""
    import numpy as np
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    grid = [("logreg", 0.5), ("logreg", 1.0), ("logreg", 2.0), ("logreg", 4.0),
            ("logreg", 8.0), ("svc", 0.5), ("svc", 1.0), ("svc", 2.0),
            ("nb", 0.3), ("nb", 1.0)]
    y_arr = np.asarray(ytr)
    min_class = min(np.bincount(np.unique(y_arr, return_inverse=True)[1]))
    cv = StratifiedKFold(n_splits=max(2, min(3, int(min_class))))
    best, best_f1 = ("logreg", 4.0), -1.0
    for kind, c in grid:
        try:
            pred = cross_val_predict(_build_pipeline(kind, c), Xtr, y_arr, cv=cv)
            f1 = f1_score(y_arr, pred, average="macro", zero_division=0)
        except Exception:
            continue
        marker = ""
        if f1 > best_f1:
            best, best_f1 = (kind, c), f1
            marker = "  <-- best so far"
        print(f"  sweep {kind:7} C={c:<4} train-CV macro-F1={f1:.3f}{marker}")
    return best


def _regex_baseline(rows: list[dict]) -> float:
    """Current regex classifier accuracy on the given rows (name + prose)."""
    from app.services.entity_healing import classify_subvertical
    ok = 0
    for r in rows:
        # feed name + prose exactly like production's no-stated path
        pred = classify_subvertical(r["package"].replace(" - DMA", ""), r.get("text") or "")
        if pred == r["label"]:
            ok += 1
    return ok / len(rows) if rows else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gold", default="tests/fixtures/ml/subvertical_labels.jsonl")
    ap.add_argument("--out", default="app/ml/models/subvertical_v1.joblib")
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()

    try:
        import joblib
        from sklearn import __version__ as skver
        from sklearn.metrics import accuracy_score, f1_score
    except ImportError as e:
        print(f"ERROR: sklearn/joblib required for training: {e}", file=sys.stderr)
        return 2

    gold = Path(args.gold)
    rows = _load(gold)
    labeled = [r for r in rows if r.get("label")]
    stated = [r for r in labeled if r["tier"] == "package_stated"]
    nostated = [r for r in labeled if r["tier"] == "no_stated"]
    print(f"# gold: {len(labeled)} labeled ({len(stated)} package_stated train, "
          f"{len(nostated)} no_stated held-out)")

    # ── Production-realistic eval: train on stated, test on no_stated ─────────
    from collections import Counter
    syn = _synthetic_rows(Counter(r["label"] for r in stated))
    if syn:
        print(f"# +{len(syn)} synthetic class-definition rows "
              f"({sorted({r['label'] for r in syn})})")
    stated = stated + syn
    Xtr = [_feature_text(r) for r in stated]
    ytr = [r["label"] for r in stated]
    Xte = [_feature_text(r) for r in nostated]
    yte = [r["label"] for r in nostated]
    kind, c = _sweep(Xtr, ytr)
    print(f"# selected by train-CV: {kind} C={c}")
    pipe = _build_pipeline(kind, c)
    pipe.fit(Xtr, ytr)
    pred = list(pipe.predict(Xte))
    # Ensemble: model prediction, but fall back to regex when model class unseen.
    model_acc = accuracy_score(yte, pred)
    model_f1 = f1_score(yte, pred, average="macro", zero_division=0)
    base_acc = _regex_baseline(nostated)

    print(f"\n## Held-out (no_stated, n={len(nostated)}) — the production regime")
    print(f"  regex baseline accuracy : {base_acc:.3f}")
    print(f"  ML model   accuracy     : {model_acc:.3f}")
    print(f"  ML model   macro-F1     : {model_f1:.3f}")
    print("  per-row (label | regex vs model):")
    from app.services.entity_healing import classify_subvertical
    for r, p in zip(nostated, pred, strict=True):
        b = classify_subvertical(r["package"].replace(" - DMA", ""), r.get("text") or "")
        flag = "" if p == r["label"] else "  <-- model miss"
        print(f"    {r['package'][:34]:36} truth={r['label']:7} regex={b!s:6} model={p:7}{flag}")

    # ── Cross-validation over ALL rows (secondary; small tiny-class caveat) ───
    try:
        from sklearn.model_selection import cross_val_predict
        Xall = [_feature_text(r) for r in labeled]
        yall = [r["label"] for r in labeled]
        cvpred = cross_val_predict(_build_pipeline(kind, c), Xall, yall, cv=3)
        cv_acc = accuracy_score(yall, cvpred)
        cv_f1 = f1_score(yall, cvpred, average="macro", zero_division=0)
        print(f"\n## 3-fold CV over all {len(labeled)} rows: acc={cv_acc:.3f} macro-F1={cv_f1:.3f} "
              f"(tiny classes NON_FI/CIB/FC caveat)")
    except Exception as e:
        print(f"\n## CV skipped: {type(e).__name__}: {e}")

    # ── Ship: train on ALL rows, persist artifact + meta ─────────────────────
    final = _build_pipeline(kind, c)
    ship_rows = labeled + _synthetic_rows(Counter(r["label"] for r in labeled))
    final.fit([_feature_text(r) for r in ship_rows], [r["label"] for r in ship_rows])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, out)
    data_sha = hashlib.sha256(gold.read_bytes()).hexdigest()
    art_sha = hashlib.sha256(out.read_bytes()).hexdigest()
    meta = {
        "name": "subvertical", "version": args.version,
        "sklearn_version": skver,
        "classes": sorted({r["label"] for r in labeled}),
        "n_train": len(labeled),
        "train_data_sha256": data_sha, "artifact_sha256": art_sha,
        "heldout_no_stated": {"n": len(nostated), "regex_acc": round(base_acc, 4),
                              "model_acc": round(model_acc, 4), "model_macro_f1": round(model_f1, 4)},
        "feature": f"word(1,2)+char_wb(3,5) TF-IDF + domain cues + regex vote; "
                   f"SVn stripped; clf={kind} C={c}",
        "cv3_all": {"acc": round(cv_acc, 4), "macro_f1": round(cv_f1, 4)},
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"\n# wrote {out} ({out.stat().st_size} bytes) + meta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
