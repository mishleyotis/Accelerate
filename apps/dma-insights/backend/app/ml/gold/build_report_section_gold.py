"""Build the report-section-classification gold standard (corpus-grounded).

Mines every heading from the corpus ``04_reports/Assessment_Report*.docx`` files
and weak-labels each with the current regex classifier
(``assessment_report.classify_heading``). Headings the regex maps to a canonical
kind are grounded weak labels; headings that fall to ``"other"`` are the
ambiguous rows that NEED human approval (they are exactly what the local ML
fallback must learn to resolve).

Gold row: {heading, section_kind, package, source: regex_weak|human, confidence}.

Usage:
  python -m app.ml.gold.build_report_section_gold \
      --corpus tests/fixtures/dma_packages_batches \
      --out tests/fixtures/ml/report_section_labels.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from app.services.parsers.assessment_report import classify_heading

# Operator-approved curation (2026-06-18): the confidently-mappable recurring
# `other` heading forms → canonical SectionKind. Keyed by normalized heading
# (lowercased, leading numbering stripped). Only high-confidence forms are here;
# genuinely ambiguous recurring forms (sentiment overview, entity profile, pillar
# deep dives, assumptions register, overall assessment by pillar, pillar-level
# scorecard, key strengths) are intentionally LEFT as `other` for the ML fallback
# to resolve — we do not poison the gold with uncertain labels.
HUMAN_KIND_MAP: dict[str, str] = {
    "issue registry": "issue_register",           # regex gap: "registry" vs "register"
    "strategic recommendations": "recommendations",
    "phased roadmap": "roadmap",
    "evidence sources": "evidence_registry",
    "gap priority register": "gap_prioritization",
    "prioritization methodology": "gap_prioritization",
    "severity-capped capability impact analysis": "gap_prioritization",
    "critical gaps": "gap_prioritization",
    "critical development areas": "gap_prioritization",
    "digital evolution timeline": "trend_analysis",
    "maturity trajectory": "trend_analysis",
    "financial growth trajectory": "trend_analysis",
    "peer set overview": "benchmark_comparison",
}


def _norm_heading(h: str) -> str:
    return re.sub(r"^\s*[\d.]+\s*", "", h).strip().lower()


def _iter_headings(pkg: Path):
    try:
        import docx  # python-docx
    except ImportError:
        return
    for p in sorted(pkg.glob("04_reports/**/*.docx")):
        name = p.name.lower()
        if "assessment" not in name and "report" not in name:
            continue
        try:
            doc = docx.Document(str(p))
        except Exception:
            continue
        for para in doc.paragraphs:
            style = (para.style.name if para.style else "") or ""
            txt = para.text.strip()
            # Only TOP-LEVEL section headers (Heading 1/2 + the base "Title"/
            # "Heading" style). Deeper levels are sub-sub-headings / ToC noise
            # that flood the set with 'other' and are not section boundaries.
            top = style in ("Heading 1", "Heading 2", "Title", "Heading")
            if txt and top and 3 <= len(txt) <= 140:
                yield txt


def build(corpus: Path) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []
    for batch in sorted(corpus.iterdir()):
        if not batch.is_dir():
            continue
        for pkg in sorted(batch.iterdir()):
            if not pkg.is_dir():
                continue
            for heading in _iter_headings(pkg):
                kind = classify_heading(heading)
                source, confidence = "regex_weak", "weak"
                grounding = "assessment_report.classify_heading over corpus DOCX headings"
                if kind == "other":
                    curated = HUMAN_KIND_MAP.get(_norm_heading(heading))
                    if curated:
                        kind, source, confidence = curated, "human", "approved"
                        grounding += " | curated recurring-form -> " + curated
                    else:
                        source, confidence = "human", "needs_approval"
                key = (heading.lower(), kind)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "heading": heading,
                    "section_kind": kind,
                    "package": pkg.name,
                    "source": source,
                    "grounding": grounding,
                    "confidence": confidence,
                })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", default="tests/fixtures/dma_packages_batches")
    ap.add_argument("--out", default="tests/fixtures/ml/report_section_labels.jsonl")
    args = ap.parse_args()
    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"ERROR: corpus dir not found: {corpus}", file=sys.stderr)
        return 2
    rows = build(corpus)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    other = [r for r in rows if r["section_kind"] == "other"]
    print(f"# report-section gold: {len(rows)} distinct headings "
          f"({len(rows)-len(other)} regex-labelled, {len(other)} 'other'/need approval)")
    print(f"# kind distribution: {dict(sorted(Counter(r['section_kind'] for r in rows).items(), key=lambda x:-x[1]))}")
    print(f"# wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
