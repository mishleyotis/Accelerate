#!/usr/bin/env python3
"""Artifact-coverage census generator (Part 12.6).

Walks the committed corpus (tests/fixtures/dma_packages_batches),
normalizes every file into a shape pattern (A-number prefixes, entity
tokens, and dates collapsed), counts how many PACKAGES ship each
pattern, and classifies each pattern's consumer/status against the
parser registry. The output regenerates
``docs/reference/ARTIFACT_COVERAGE.md``.

Usage (from apps/dma-insights/backend):
    .venv/bin/python scripts/artifact_coverage_census.py \
        [--corpus tests/fixtures/dma_packages_batches] [--write]

Without --write the markdown is printed to stdout.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.artifact_manifest import classify_path

# (regex, consumer, status) — first match wins. Status vocabulary:
#   CONSUMED   — a dedicated parser persists it into domain tables
#   KNOWLEDGE  — new Part-12.6 parser → client_knowledge_sections
#   GENERIC    — generic section-miner rung (+ pattern_gap learning row)
#   EXCLUDED   — documented exclusion (cosmetic / recomputable / audit)
_RULES: list[tuple[str, str, str]] = [
    # ── Consumed core (scoring / evidence / identity) ──
    (r"export_scoring_detail.*\.csv$", "package_csvs.parse_scoring_detail_csv → subcap_scores", "CONSUMED"),
    (r"export_pillar_summary.*\.csv$", "package_csvs.parse_pillar_summary_csv → pillar rows", "CONSUMED"),
    (r"export_category_summary.*\.csv$", "package_csvs.parse_category_summary_csv → category rows", "CONSUMED"),
    (r"export_.*\.csv$", "package_csvs (export family)", "CONSUMED"),
    (r"evidence_index\.(csv|json)$", "package_csvs.parse_evidence_csv / json → evidence_index", "CONSUMED"),
    (r"evidence_(inventory|master|summary)|merged_evidence", "duplicates evidence_index content (dedup engine owns it)", "EXCLUDED"),
    (r"evidence_ers_ranking", "evidence ERS ranking (folded into evidence rows)", "EXCLUDED"),
    (r"research_handoff.*\.json$", "research_workbook.cross_reference_with_handoff → evidence/firmographics", "CONSUMED"),
    (r"run_manifest.*\.json$", "dma_package._parse_run_manifest_tolerant → runs/entities", "CONSUMED"),
    (r"(^|/)manifest\.json$", "package_json.parse_top_manifest", "CONSUMED"),
    (r"verdict.*\.json$", "package_json.parse_qa_verdict → runs.qa_verdict_l1/l2", "CONSUMED"),
    (r"audit_summary\.json$", "manifest variant fallback", "CONSUMED"),
    (r"(00_)?parameters\.json$", "dma_package._synthesize_run_manifest_from_parameters", "CONSUMED"),
    (r"issue_register.*\.(csv|json)$", "package_csvs.parse_issue_register_csv → issue_register", "CONSUMED"),
    (r"recommendations?_(detail|register)\.json$", "package_recommendations → recommendations", "CONSUMED"),
    (r"rec-\d+.*\.json$", "package_recommendations (per-REC files)", "CONSUMED"),
    (r"recommendation_validation\.json$", "recommendation_validation.parse_rec_prerequisites", "CONSUMED"),
    (r"caps_applied_log\.csv$", "caps_applied_log parser → caps_applied_log", "CONSUMED"),
    (r"contradiction_log\.csv$", "governance_audit → runs.audit_logs", "CONSUMED"),
    (r"reasoning_chain_log\.json$", "governance_audit → runs.audit_logs", "CONSUMED"),
    (r"assumptions?_register", "assumptions_register → runs.assumptions_register", "CONSUMED"),
    (r"peer_scores_.*\.json$", "package_json.parse_peer_score → peers", "CONSUMED"),
    (r"peer_comparison_table\.csv$", "package_peers.load_peer_benchmarks", "CONSUMED"),
    (r"peer_benchmarks\.json$", "package_peers.load_peer_benchmarks", "CONSUMED"),
    (r"section_analysis_\d+\.json$", "section_analysis → insight_cards", "CONSUMED"),
    (r"report_synthesis\.md$", "report_synthesis → D1 SCQA section", "CONSUMED"),
    (r"entity_profile\.json$", "entity_profile parser → firmographics", "CONSUMED"),
    (r"financial_trends\.csv$", "package_financials.load_financial_trends", "CONSUMED"),
    (r"financial_baseline\.json$", "package_financials.load_financial_baseline", "CONSUMED"),
    (r"sentiment_data\.csv$", "package_financials.load_sentiment", "CONSUMED"),
    (r"tech_?stack|tech_utilization", "package_techstack.load_tech_stack → tech_stack_entries", "CONSUMED"),
    (r"assessment_report.*\.docx$|.*report.*\.docx$", "assessment_report → document_sections", "CONSUMED"),
    (r"client_profile.*\.docx$", "client_profile → focus_areas/firmographics/leadership", "CONSUMED"),
    (r"\.xlsx$|\.xlsm$|\.xls$", "scoring_workbook XLSX fallback / research workbook sheets", "CONSUMED"),
    (r"subcap_taxonomy\.json$", "catalogue bootstrap input", "CONSUMED"),
    # ── Part 12.6 knowledge parsers (previously unconsumed) ──
    (r"zennify_opportunit", "parsers/zennify_opportunities → client_knowledge_sections('zennify_opportunity')", "KNOWLEDGE"),
    (r"uncertainty_(register|bands)", "parsers/uncertainty_register → client_knowledge_sections('uncertainty') + runs.uncertainty_bands", "KNOWLEDGE"),
    (r"org_capabilit", "parsers/org_capability → client_knowledge_sections('org_capability')", "KNOWLEDGE"),
    # ── Documented exclusions ──
    (r"(proxy_)?search_log", "audit search log — optional provenance only", "EXCLUDED"),
    (r"scoring_scratchpad", "scoring scratchpad — recomputable from workbook", "EXCLUDED"),
    (r"\.(png|jpe?g|gif|svg|bmp)$", "VIZ / deck imagery (cosmetic)", "EXCLUDED"),
    (r"\.pptx?$|05_narrative_deck/", "narrative deck (cosmetic; operator-confirmed skip)", "EXCLUDED"),
    (r"\.pdf$", "evidence PDFs (stored raw; OCR only in lenient mode)", "EXCLUDED"),
]

_COMPILED = [(re.compile(p, re.I), c, s) for p, c, s in _RULES]

_A_PREFIX = re.compile(r"^a\d+_", re.I)
_DATEISH = re.compile(r"(20\d{6}|20\d{2}[-_]\d{2}[-_]\d{2}|20\d{2})")


def normalize_pattern(rel_path: str) -> str:
    """Collapse per-entity noise so shapes aggregate: A-number prefixes
    → 'A#_', dates → '<date>', entity tokens in report names → '*'."""
    base = rel_path.rsplit("/", 1)[-1].lower()
    base = _A_PREFIX.sub("A#_", base)
    base = _DATEISH.sub("<date>", base)
    # Entity-prefixed report names: keep the stable tail token.
    for tail in (
        "assessment_report", "client_profile_research_report",
        "client_profile", "run_manifest", "qa_verdict",
        "scoring_toolkit", "explorium_tech_stack",
    ):
        if tail in base and not base.startswith(tail):
            suffix = base.rsplit(".", 1)[-1]
            return f"*_{tail}.{suffix}"
    return base


def classify(rel_path: str) -> tuple[str, str]:
    low = rel_path.lower()
    for rx, consumer, status in _COMPILED:
        if rx.search(low):
            return consumer, status
    if classify_path(rel_path) == "cosmetic":
        return "cosmetic (artifact_manifest)", "EXCLUDED"
    return (
        "generic section-miner → client_knowledge_sections('generic') "
        "+ nlp.patterns pattern_gap", "GENERIC",
    )


def build_census(corpus: Path):
    from app.scripts.historical_backfill import _find_local_package_roots
    roots = _find_local_package_roots(corpus)
    per_pattern_pkgs: dict[str, set[str]] = defaultdict(set)
    per_pattern_meta: dict[str, tuple[str, str]] = {}
    for root in roots:
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(root).as_posix()
            pattern = normalize_pattern(rel)
            consumer, status = classify(rel)
            per_pattern_pkgs[pattern].add(str(root))
            prev = per_pattern_meta.get(pattern)
            # Prefer the strongest status when a pattern spans classes.
            rank = {"CONSUMED": 0, "KNOWLEDGE": 1, "GENERIC": 2, "EXCLUDED": 3}
            if prev is None or rank[status] < rank[prev[1]]:
                per_pattern_meta[pattern] = (consumer, status)
    return len(roots), per_pattern_pkgs, per_pattern_meta


def render_markdown(corpus: Path) -> str:
    n_roots, pkgs, meta = build_census(corpus)
    rows = sorted(
        (
            (pattern, len(pkg_set), *meta[pattern])
            for pattern, pkg_set in pkgs.items()
        ),
        key=lambda r: (-r[1], r[0]),
    )
    by_status: dict[str, int] = defaultdict(int)
    for _, _, _, status in rows:
        by_status[status] += 1
    lines = [
        "# Artifact coverage census — DMA package corpus",
        "",
        f"Generated by `backend/scripts/artifact_coverage_census.py` on "
        f"{date.today().isoformat()} against "
        f"`backend/tests/fixtures/dma_packages_batches` "
        f"({n_roots} package roots).",
        "",
        "Status vocabulary:",
        "",
        "- **CONSUMED** — a dedicated parser persists the artifact into "
        "domain tables (scores/evidence/recs/peers/sections/…).",
        "- **KNOWLEDGE** — Part 12.6 unconsumed-artifact parser → "
        "`client_knowledge_sections` (+ `runs.uncertainty_bands`).",
        "- **GENERIC** — no fingerprint matched; the generic section-miner "
        "persists capped `artifact_kind='generic'` sections AND records an "
        "`nlp.patterns` pattern_gap so the registry learns the shape.",
        "- **EXCLUDED** — documented exclusion (narrative-deck placeholders, "
        "VIZ PNGs, duplicate xlsx twins ride the CONSUMED workbook path, "
        "scoring scratchpads are recomputable, search logs are optional "
        "provenance, evidence twins duplicate `evidence_index`).",
        "",
        "Every MATERIAL artifact — whatever its status — is additionally "
        "persisted compressed into `raw_artifacts` (Part 12.2: zstd-9 for "
        "text-likes, verbatim for docx/xlsx/pdf, global sha256 dedup), so "
        "re-parse never re-downloads and provenance is byte-exact.",
        "",
        "| Status | distinct patterns |",
        "|---|---|",
    ]
    for status in ("CONSUMED", "KNOWLEDGE", "GENERIC", "EXCLUDED"):
        lines.append(f"| {status} | {by_status.get(status, 0)} |")
    lines += [
        "",
        "## Census (pattern x packages x consumer x status)",
        "",
        "`packages` = number of package roots shipping ≥1 file matching "
        "the normalized pattern (`A#_` collapses A-number prefixes; "
        "`<date>`/`*_` collapse per-entity tokens).",
        "",
        "Long-tail singletons (a pattern seen in exactly ONE package) are "
        "rolled up per status below the table — every one of them still "
        "flows through the GENERIC/EXCLUDED machinery above.",
        "",
        "| pattern | packages | consumer | status |",
        "|---|---|---|---|",
    ]
    singleton_rollup: dict[str, int] = defaultdict(int)
    for pattern, n, consumer, status in rows:
        if n == 1 and status in ("GENERIC", "EXCLUDED"):
            singleton_rollup[status] += 1
            continue
        lines.append(f"| `{pattern}` | {n} | {consumer} | {status} |")
    for status, n in sorted(singleton_rollup.items()):
        lines.append(
            f"| _(+{n} single-package {status} patterns — rolled up)_ "
            f"| 1 each | see status vocabulary | {status} |"
        )
    lines += [
        "",
        "## Contract",
        "",
        "- The `artifact_coverage_no_unknowns` intent: any NEW artifact "
        "shape lands in GENERIC (never silently dropped) and surfaces as "
        "a pattern_gap in `runs.parser_warnings.pattern_gaps` + the "
        "qa_language_audit zero-day report. Promoting a recurring GENERIC "
        "pattern to a dedicated parser = add a fingerprint via "
        "`nlp.patterns.register` + a leaf parser under "
        "`app/services/parsers/`.",
        "- Regenerate this file after adding parsers: "
        "`.venv/bin/python scripts/artifact_coverage_census.py --write`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--corpus", default="tests/fixtures/dma_packages_batches",
    )
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"FATAL: corpus not found: {corpus}", file=sys.stderr)
        return 2
    md = render_markdown(corpus)
    if args.write:
        out = Path(__file__).resolve().parents[2] / "docs" / "reference" / \
            "ARTIFACT_COVERAGE.md"
        out.write_text(md, encoding="utf-8")
        print(f"wrote {out} ({len(md.splitlines())} lines)")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
