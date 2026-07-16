"""Content-coverage matrix (plan Part 7), offline edition.

Runs `parse_package` across an entire package corpus and, for each
content block on each page, classifies the result as:

  - EXTRACTED — the IngestedPackage carries the block's data.
  - FAIL      — a source file for the block is demonstrably present in the
                package, yet the block came out empty (a parser gap/bug —
                exactly the regression class this session has been closing).
  - PENDING   — no source for the block shipped (honest empty).
  - (derived blocks have no file source → EXTRACTED vs EMPTY only.)

Pure / no DB (parse-only), so it runs anywhere `parse_package` does and
doubles as a regression guard: `tests/test_content_coverage.py` asserts
per-block EXTRACTED floors + a FAIL ceiling so the corpus-wide gains from
the extraction work can't silently regress.

CLI:
    python -m app.scripts.parse_coverage --dir <fixtures> --out docs/DMA_CONTENT_COVERAGE.md
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.parsers.dma_package import _find_root, parse_package


def _fh(pkg: Any) -> dict:
    f = pkg.firmographics
    return getattr(f, "financial_highlights", {}) or {} if f else {}


def _sent(pkg: Any) -> dict:
    f = pkg.firmographics
    return getattr(f, "sentiment", {}) or {} if f else {}


def _peer_source_present(root: Path, pkg: Any) -> bool:
    """A peer file is only a usable source if the package has CATEGORIES to
    hang medians on. cats=0 background-research stubs (DovenMuehle/Echelon)
    are honest PENDING — there is nothing to attach a peer median to."""
    if not getattr(pkg, "category_scores", None):
        return False
    return any(
        next(root.glob(g), None) is not None
        for g in ("**/peer_comparison_table.csv", "**/peer_benchmarks.json")
    )


def _has_entity_scores_source(root: Path, pkg: Any = None) -> bool:
    """An ENTITY-level scoring source (export_scoring_detail/summary CSV, a
    scoring workbook, or a non-peer scores JSON). Excludes peer_scores_*.json
    so background-research-only packages (DovenMuehle/Echelon — peer scores
    but no entity assessment) are honest PENDING, not a parser FAIL."""
    # Subcap-level sources only — a scoring workbook can be category-only
    # (MidFirst), which is NOT a subcap-score source, so it must not
    # FAIL-flag the subcap block.
    for pat in ("**/export_scoring_detail*.csv", "**/export_*summary*.csv"):
        if next(root.glob(pat), None) is not None:
            return True
    return any(
        not p.name.lower().startswith("peer")
        for p in root.glob("**/*scores*.json")
    )


def _has_insight_source(root: Path, pkg: Any = None) -> bool:
    """A section_analysis file counts as an insight source only if it
    actually carries a findings-bearing key — a section-summary variant
    (entity metadata / strategic objectives only, e.g. Tristate) is not a
    parser FAIL, it is honestly PENDING."""
    import json
    keys = ("top_findings", "priority_capabilities", "caution_capabilities",
            "critical_gaps")
    for p in root.glob("**/section_analysis_*.json"):
        try:
            d = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(d, dict) and any(
            isinstance(d.get(k), list) and d.get(k) for k in keys
        ):
            return True
    return False


@dataclass(frozen=True)
class Block:
    name: str
    page: str
    has_data: Callable[[Any], bool]
    # Recursive globs that indicate a source for this block shipped. None →
    # a DERIVED block (no FAIL classification; just EXTRACTED vs EMPTY).
    source_globs: tuple[str, ...] | None = None
    # Optional content-aware source check (overrides source_globs) for blocks
    # where mere file presence over-reports FAIL.
    source_fn: Callable[[Path, Any], bool] | None = None


BLOCKS: tuple[Block, ...] = (
    Block("D1.scqa", "D1",
          lambda p: any(s.kind == "executive_summary_scqa" for s in p.report_sections),
          # Structured SCQA source only — a DOCX without a classifiable
          # exec-summary is a legitimate empty, not a parser FAIL.
          ("**/report_synthesis.md",)),
    Block("D1.firmographics", "D1",
          lambda p: bool(p.firmographics and (
              p.firmographics.legal_name or p.firmographics.total_assets
              or p.firmographics.primary_regulator)),
          ("**/entity_profile.json", "**/research_handoff*.json",
           "**/financial_baseline.json")),
    Block("D1.scores", "D1", lambda p: len(p.subcap_scores) > 0,
          source_fn=_has_entity_scores_source),
    Block("D2.insights", "D2", lambda p: len(p.insight_cards) > 0,
          source_fn=_has_insight_source),
    Block("D3.peer_benchmarks", "D3",
          lambda p: any(c.peer_median is not None for c in p.category_scores),
          source_fn=_peer_source_present),
    Block("D3.categories", "D3", lambda p: len(p.category_scores) > 0, None),
    Block("D4.recommendations", "D4", lambda p: len(p.recommendations) > 0,
          ("**/recommendations*.json", "**/06_recommendations.json")),
    Block("D5.timeline", "D5", lambda p: len(p.timeline_events) > 0, None),
    Block("D5.financials", "D5",
          # multi-year series OR single-period scalar metrics — both are real
          # financial data the D5 card renders.
          lambda p: bool(_fh(p).get("series") or _fh(p).get("metrics")
                         or {k for k in _fh(p) if k not in ("series", "lines")}),
          ("**/A[0-9]*[Ff]inancial*[Tt]rends*.csv",)),
    Block("D5.sentiment", "D5", lambda p: bool(_sent(p).get("sources")),
          ("**/A[0-9]*[Ss]entiment*.csv", "**/*sentiment_data*.csv")),
    Block("D6.audit", "D6",
          lambda p: bool(getattr(p, "audit_logs", None) and (
              p.audit_logs.contradictions or p.audit_logs.reasoning_chain)),
          ("**/contradiction_log.csv", "**/reasoning_chain_log.json")),
    Block("D6.caps", "D6", lambda p: len(p.caps_applied_log) > 0,
          ("**/caps_applied_log.csv",)),
    Block("D6.qa_verdict", "D6",
          # A package may ship only an L1 verdict (Penderfund) — that IS its
          # captured QA verdict (surfaced as qa_verdict_l1 on D6 Gates).
          lambda p: p.qa_verdict is not None or p.qa_verdict_l1 is not None,
          ("**/*qa_verdict*.json",)),
    Block("D7.tech", "D7", lambda p: len(p.tech_stack) > 0,
          ("**/*[Tt]ech*[Ss]tack*.csv", "**/tech_inventory.json",
           "**/tech_stack.json", "**/*Explorium*.xlsx")),
)


@dataclass
class BlockCoverage:
    extracted: int = 0
    fail: int = 0
    pending: int = 0  # source absent (or, for derived blocks, empty)
    fail_entities: list[str] = field(default_factory=list)


def _source_present(root: Path, globs: tuple[str, ...] | None) -> bool:
    if not globs:
        return False
    return any(next(root.glob(g), None) is not None for g in globs)


def compute_coverage(packages_dir: Path) -> tuple[dict[str, BlockCoverage], int, int]:
    """Return (per-block coverage, eligible_count, ineligible_count)."""
    cov = {b.name: BlockCoverage() for b in BLOCKS}
    eligible = ineligible = 0
    entities = [d for d in sorted(packages_dir.glob("batch_*/*")) if d.is_dir()]
    for ent in entities:
        try:
            root = _find_root(ent)
        except FileNotFoundError:
            ineligible += 1
            continue
        try:
            pkg = parse_package(ent)
        except Exception:
            ineligible += 1
            continue
        eligible += 1
        for b in BLOCKS:
            c = cov[b.name]
            if b.has_data(pkg):
                c.extracted += 1
                continue
            source_present = (
                b.source_fn(root, pkg) if b.source_fn is not None
                else _source_present(root, b.source_globs)
            )
            if source_present:
                c.fail += 1
                c.fail_entities.append(ent.name)
            else:
                c.pending += 1
    return cov, eligible, ineligible


def render_markdown(cov: dict[str, BlockCoverage], eligible: int, ineligible: int) -> str:
    lines = [
        "# DMA content-coverage matrix",
        "",
        f"Corpus: **{eligible} eligible** packages "
        f"({ineligible} ineligible/empty, skipped). Generated by "
        "`python -m app.scripts.parse_coverage`.",
        "",
        "`FAIL` = a source file for the block shipped but the block came out "
        "empty (parser gap). `PENDING` = no source shipped (honest empty); for "
        "derived blocks (no source file) it means computed-empty.",
        "",
        "| Block | EXTRACTED | FAIL | PENDING |",
        "|---|---:|---:|---:|",
    ]
    for b in BLOCKS:
        c = cov[b.name]
        lines.append(f"| `{b.name}` | {c.extracted} | {c.fail} | {c.pending} |")
    fails = {n: c.fail_entities for n, c in cov.items() if c.fail_entities}
    if fails:
        lines += ["", "## FAIL detail (source present, block empty)", ""]
        for name, ents in fails.items():
            shown = ", ".join(ents[:8]) + (" …" if len(ents) > 8 else "")
            lines.append(f"- `{name}` ({len(ents)}): {shown}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    cov, eligible, ineligible = compute_coverage(args.dir)
    md = render_markdown(cov, eligible, ineligible)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md)
        print(f"wrote {args.out}  ({eligible} eligible, {ineligible} ineligible)")
    else:
        print(md)


if __name__ == "__main__":
    main()
