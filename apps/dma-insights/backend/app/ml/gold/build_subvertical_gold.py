"""Build the subvertical-classification gold standard (corpus-grounded).

Two grounded tiers over the 113-package corpus:

  Tier 1 — package_stated : the package's OWN analyst-stated classification,
    read via ``dma_package._subvertical_from_artifacts`` and canonicalized by
    ``package_persist._canonical_subvertical``. High-confidence ground truth;
    used to TRAIN the classifier, not to score it.
  Tier 2 — no_stated : the package states nothing, so the current regex
    classifier decides. These are the rows the model must actually get right,
    so they are the held-out SCORING set — every label is human-approved.

Taxonomy (decided with the operator): the 9 existing codes
  RB CU CL FC IB IC AM RIA CIB
plus a new ``NON_FI`` code for genuinely non-financial entities (e.g. a
procurement-SaaS vendor that slipped into the corpus). Exact entity identity is
verified — a name is never force-bucketed.

HUMAN_CORRECTIONS below overrides a stated-but-wrong or classifier-guessed label
with the grounded correct code + a one-line rationale. Every override is listed
in the plan's A1 approval gate.

Usage (reproducible, read-only against the corpus):
  python -m app.ml.gold.build_subvertical_gold \
      --corpus tests/fixtures/dma_packages_batches \
      --out tests/fixtures/ml/subvertical_labels.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from app.services.entity_healing import classify_subvertical, extract_subvertical_text
from app.services.parsers.dma_package import _subvertical_from_artifacts
from app.services.parsers.package_persist import _canonical_subvertical

VALID_CODES = {"RB", "CU", "CL", "FC", "IB", "IC", "AM", "RIA", "CIB", "NON_FI"}

# Grounded human corrections, keyed by NORMALIZED package name (lowercased, the
# trailing " - dma"/"dma" tokens stripped, whitespace collapsed). Each value is
# (code, rationale). Surfaced verbatim in the plan A1 approval list.
HUMAN_CORRECTIONS: dict[str, tuple[str, str]] = {
    # Tier-1 stated-but-wrong / canonicalizer-miss
    "guaranteed rate": ("CL", "independent mortgage bank; stated 'BL-IMB' canonicalized to None"),
    "sl green realty": ("AM", "office REIT; stated 'CIB' is wrong — REIT->AM convention"),
    "first united bank": ("RB", "exact-name check: it is a bank; stated 'Credit Union' is wrong"),
    # Tier-2 classifier misses / no-match
    "farm credit mid america": ("FC", "Farm Credit System member; classifier said CL"),
    "chemung canal trust": ("RB", "regional bank / trust company; classifier said RIA"),
    "commece trust": ("AM", "Commerce Trust wealth/asset mgmt arm; classifier said RIA"),
    "navacord": ("IB", "insurance brokerage; classifier returned None"),
    "atb": ("RB", "Alberta Treasury Branches — a bank; classifier returned None"),
    "mag mutual": ("IC", "medical professional mutual insurer; classifier returned None"),
    "ziphq": ("NON_FI", "procurement SaaS vendor — not a financial institution"),
    # Operator-approved (2026-06-18): the 3 uncertain Tier-2 rows, verified by
    # exact entity identity in the package.
    "ima financial": ("IB", "IMA Financial Group — insurance brokerage; DOCX states insurance broker; classifier said IC"),
    "aaa club alliance": ("IC", "AAA motor club — insurance carrier/membership; classifier said IC (kept, confirmed)"),
    "spg": ("IB", "Specialty Program Group (Hub Intl MGA) — DOCX 'SV7 Insurance Brokers'; classifier said IC"),
}


def _norm(folder_name: str) -> str:
    s = folder_name.lower()
    s = re.sub(r"\bdma\b", " ", s)
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build(corpus: Path) -> list[dict]:
    rows: list[dict] = []
    for batch in sorted(corpus.iterdir()):
        if not batch.is_dir():
            continue
        for pkg in sorted(batch.iterdir()):
            if not pkg.is_dir():
                continue
            norm = _norm(pkg.name)
            try:
                raw = _subvertical_from_artifacts(pkg)
            except Exception:
                raw = None
            svt = ""
            try:
                svt = extract_subvertical_text(pkg)
            except Exception:
                svt = ""
            text = f"{pkg.name} {svt}".strip()

            if raw:
                tier, source = "package_stated", "package_stated"
                label = _canonical_subvertical(raw, pkg.name)
                grounding = f"_subvertical_from_artifacts -> '{raw}'"
                confidence = "high"
            else:
                tier, source = "no_stated", "classifier_candidate"
                label = classify_subvertical(pkg.name, svt)
                grounding = "no stated label in package; regex-classifier prediction"
                confidence = "needs_approval"

            correction = None
            for key, (code, why) in HUMAN_CORRECTIONS.items():
                if key == norm or norm.startswith(key + " ") or f" {key} " in f" {norm} ":
                    label, source, confidence = code, "human", "approved"
                    correction = f"corrected -> {code}: {why}"
                    break

            rows.append({
                "package": pkg.name,
                "text": text[:600],
                "label": label,
                "tier": tier,
                "source": source,
                "grounding": grounding + (f" | {correction}" if correction else ""),
                "confidence": confidence,
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", default="tests/fixtures/dma_packages_batches")
    ap.add_argument("--out", default="tests/fixtures/ml/subvertical_labels.jsonl")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"ERROR: corpus dir not found: {corpus}", file=sys.stderr)
        return 2
    rows = build(corpus)

    # Validate every emitted label is in the taxonomy (None allowed only as an
    # explicit un-approved Tier-2 gap, surfaced for human labelling).
    bad = [r for r in rows if r["label"] is not None and r["label"] not in VALID_CODES]
    if bad:
        print(f"ERROR: {len(bad)} rows carry an out-of-taxonomy label: "
              f"{sorted({r['label'] for r in bad})}", file=sys.stderr)
        return 3

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary to stdout for the approval gate.
    from collections import Counter
    tier1 = [r for r in rows if r["tier"] == "package_stated"]
    tier2 = [r for r in rows if r["tier"] == "no_stated"]
    human = [r for r in rows if r["source"] == "human"]
    unlabeled = [r for r in rows if r["label"] is None]
    print(f"# subvertical gold: {len(rows)} packages "
          f"({len(tier1)} package_stated, {len(tier2)} no_stated, "
          f"{len(human)} human-corrected, {len(unlabeled)} still-unlabeled)")
    print(f"# label distribution: {dict(sorted(Counter(r['label'] for r in rows).items(), key=lambda x: -x[1]))}")
    print(f"# wrote {out}")
    if unlabeled:
        print("# STILL-UNLABELED (need human approval):")
        for r in unlabeled:
            print(f"#   {r['package']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
