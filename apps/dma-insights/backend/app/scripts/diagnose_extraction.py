"""Corpus-wide extraction coverage diagnostic.

Runs the real `parse_package` over every DMA package under a corpus dir
(default: the 113 fixture packages) and reports per-surface coverage +
quality. This is the proof + regression artifact behind the data-quality
work: it answers "does extraction work for ALL clients?" without a DB,
because `parse_package` is a pure function over a package directory.

Usage:
    python -m app.scripts.diagnose_extraction [--dir <corpus_root>] [--json]

Surfaces measured per package:
  - leadership:     # people in firmographics.leadership
  - tech_stack:     # rows; # with a resolved status enum / l3_id
  - insight_cards:  # cards; # with non-empty so_what; # with >=1 evidence;
                    # flagged as a real gap vs. a mislabeled strength
  - scqa:           executive_summary_scqa section present (parsed or derived)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Silence the structlog/parse chatter so the census table is readable.
logging.disable(logging.INFO)
warnings.filterwarnings("ignore")

_DEFAULT_CORPUS = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "dma_packages_batches"
)

_SYNTHETIC_TITLE_SUFFIXES = (": maturity gap", ": relative priority", ": low maturity")


@dataclass
class SurfaceCounts:
    packages: int = 0
    # leadership
    lead_nonempty: int = 0
    lead_people: int = 0
    # tech
    tech_nonempty: int = 0
    tech_rows: int = 0
    tech_with_status_enum: int = 0
    tech_with_l3: int = 0
    # insights
    ic_nonempty: int = 0
    ic_rows: int = 0
    ic_with_sowhat: int = 0
    ic_with_evidence: int = 0
    ic_synthetic_title: int = 0
    # scqa
    scqa_present: int = 0
    # errors
    parse_errors: int = 0
    error_names: list[str] = field(default_factory=list)


# The FULL by-design status vocabulary: the ingest states plus the Part 9
# Zennify-taxonomy classification states (INFERRED/CLAIMED/ABSENT render;
# UNKNOWN_VENDOR is review-queue-only; ENGINEERING_SIGNAL is stored but
# never AE-rendered as a platform). The census invariant is "every row
# carries a KNOWN status" — not "predates the taxonomy" (fixed 2026-07-04;
# the stale 3-value set failed 1368 legitimately-classified rows).
_STATUS_ENUM = {
    "DETECTED", "CONFIRMED", "CONFIRMED_REMOVED",
    "INFERRED", "CLAIMED", "ABSENT",
    "UNKNOWN_VENDOR", "ENGINEERING_SIGNAL",
}


def _measure(pkg, counts: SurfaceCounts) -> None:
    firm = getattr(pkg, "firmographics", None)
    leadership = list(getattr(firm, "leadership", []) or []) if firm else []
    if leadership:
        counts.lead_nonempty += 1
        counts.lead_people += len(leadership)

    tech = list(getattr(pkg, "tech_stack", []) or [])
    if tech:
        counts.tech_nonempty += 1
        counts.tech_rows += len(tech)
        for t in tech:
            status = (getattr(t, "status", None) or "").upper()
            if status in _STATUS_ENUM:
                counts.tech_with_status_enum += 1
            if getattr(t, "l3_id", None):
                counts.tech_with_l3 += 1

    cards = list(getattr(pkg, "insight_cards", []) or [])
    if cards:
        counts.ic_nonempty += 1
        counts.ic_rows += len(cards)
        for c in cards:
            if (getattr(c, "so_what_text", "") or "").strip():
                counts.ic_with_sowhat += 1
            if list(getattr(c, "linked_e_ids", []) or []):
                counts.ic_with_evidence += 1
            title = (getattr(c, "title", "") or "")
            if any(title.endswith(s) for s in _SYNTHETIC_TITLE_SUFFIXES):
                counts.ic_synthetic_title += 1

    sections = list(getattr(pkg, "report_sections", []) or [])
    if any(getattr(s, "kind", "") == "executive_summary_scqa" for s in sections):
        counts.scqa_present += 1


def run(corpus_root: Path) -> SurfaceCounts:
    from app.services.parsers.dma_package import parse_package

    pkgs = [
        d
        for b in sorted(corpus_root.glob("batch_*"))
        for d in sorted(b.iterdir())
        if d.is_dir()
    ]
    if not pkgs:  # not a batched corpus — treat each child as a package
        pkgs = [d for d in sorted(corpus_root.iterdir()) if d.is_dir()]

    counts = SurfaceCounts()
    for d in pkgs:
        counts.packages += 1
        try:
            pkg = parse_package(d)
        except Exception as e:
            counts.parse_errors += 1
            counts.error_names.append(f"{d.name}: {type(e).__name__}")
            continue
        _measure(pkg, counts)
    return counts


def _fmt(counts: SurfaceCounts) -> str:
    n = counts.packages or 1
    lines = [
        f"Corpus packages parsed: {counts.packages} ({counts.parse_errors} parse errors)",
        "",
        f"  leadership   non-empty: {counts.lead_nonempty:3}/{n}  "
        f"({counts.lead_people} people total)",
        f"  tech stack   non-empty: {counts.tech_nonempty:3}/{n}  "
        f"(rows={counts.tech_rows}, status_enum={counts.tech_with_status_enum}, l3={counts.tech_with_l3})",
        f"  insight cards non-empty: {counts.ic_nonempty:3}/{n}  "
        f"(rows={counts.ic_rows}, so_what={counts.ic_with_sowhat}, "
        f"evidence={counts.ic_with_evidence}, synthetic_title={counts.ic_synthetic_title})",
        f"  scqa section present:   {counts.scqa_present:3}/{n}",
    ]
    if counts.error_names:
        lines += ["", "  parse errors:"] + [f"    {e}" for e in counts.error_names]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, default=_DEFAULT_CORPUS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    counts = run(args.dir)
    if args.json:
        print(json.dumps(asdict(counts), indent=2))
    else:
        print(_fmt(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
