"""Inspect a directory of DMA sample packages.

Audit-required helper: runs `parse_package` against every immediate
sub-directory of `$DMA_REAL_SAMPLE_DIR` (or the directory passed on
the command line) and prints:

  * per-sample parser counts (subcaps / evidence / recs / peers /
    issues / tech / sections / firmographics)
  * per-sample parser warnings
  * institution-name + run_id resolved
  * cross-sample acceptance check against the audit thresholds

Usage:
    DMA_REAL_SAMPLE_DIR=/path/to/samples python -m app.scripts.inspect_dma_samples
    python -m app.scripts.inspect_dma_samples /path/to/samples

Exit codes:
  0  all samples meet audit acceptance thresholds
  1  at least one sample below threshold OR raised an exception
  2  $DMA_REAL_SAMPLE_DIR not provided / not a directory
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from app.services.parsers.dma_package import parse_package

# Per-sample acceptance thresholds from the 2026-05-28 audit:
#   sub  >= 690    (XLSX fallback covers all 5 samples)
#   ev   >= 100    (evidence CSV/JSON variants)
#   peer >=   3
#   firm == True
_THRESHOLDS = {
    "subcaps_min": 690,
    "evidence_min": 100,
    "peers_min": 3,
}


def _inner_package_root(sample_dir: Path) -> Path:
    """A sanitized sample zip extracts to two layers — outer entity-name
    folder, then the actual canonical layout. If the immediate dir has
    `01_evidence/` directly under it, that IS the package root.
    Otherwise descend one level.
    """
    if (sample_dir / "01_evidence").is_dir() or (sample_dir / "03_scoring_workbook").is_dir():
        return sample_dir
    inner = [p for p in sample_dir.iterdir() if p.is_dir() and not p.name.startswith("__")]
    if len(inner) == 1:
        return inner[0]
    # Fall back to the original dir; parse_package will raise if there's
    # truly no layout.
    return sample_dir


def main() -> int:
    sample_dir_str = (
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DMA_REAL_SAMPLE_DIR", "")
    )
    if not sample_dir_str:
        print(
            "FATAL: pass a directory path or set DMA_REAL_SAMPLE_DIR",
            file=sys.stderr,
        )
        return 2
    sample_dir = Path(sample_dir_str)
    if not sample_dir.is_dir():
        print(f"FATAL: {sample_dir} is not a directory", file=sys.stderr)
        return 2

    rows: list[tuple[str, dict]] = []
    samples = sorted(
        p for p in sample_dir.iterdir()
        if p.is_dir() and not p.name.startswith("__") and not p.name.startswith(".")
    )
    print(f"Inspecting {len(samples)} sample directory entries under {sample_dir}")
    for s in samples:
        root = _inner_package_root(s)
        try:
            pkg = parse_package(root)
            rows.append((s.name, {
                "status": "OK",
                "institution": pkg.run_manifest.institution_name or "",
                "run_id": pkg.run_manifest.run_id or "",
                "subcaps": len(pkg.subcap_scores),
                "evidence": len(pkg.evidence),
                "recs": len(pkg.recommendations),
                "peers": len(pkg.peers),
                "issues": len(pkg.issue_register),
                "tech": len(pkg.tech_stack),
                "sections": len(pkg.report_sections or []),
                "firm": pkg.firmographics is not None,
                "warnings_count": len(pkg.parser_warnings),
                "warnings_sample": pkg.parser_warnings[:3],
            }))
        except Exception as e:
            rows.append((s.name, {
                "status": "FAIL",
                "error": f"{type(e).__name__}: {e!s}",
            }))

    print()
    print(f"{'sample':<22} {'status':<6} {'sub':<4} {'ev':<4} {'rec':<4} {'peer':<4} {'iss':<4} {'tch':<4} {'sec':<4} firm  institution")
    print("-" * 120)
    failures = 0
    below_threshold = 0
    for name, r in rows:
        if r["status"] == "FAIL":
            print(f"{name:<22} FAIL   - error: {r['error']}")
            failures += 1
            continue
        firm = "Y" if r["firm"] else "N"
        print(
            f"{name:<22} OK     {r['subcaps']:<4} {r['evidence']:<4} {r['recs']:<4} "
            f"{r['peers']:<4} {r['issues']:<4} {r['tech']:<4} {r['sections']:<4} "
            f"{firm:<5} {r['institution']!r}"
        )
        if r["subcaps"] < _THRESHOLDS["subcaps_min"]:
            print(f"  ⚠ below threshold: subcaps={r['subcaps']} (need >= {_THRESHOLDS['subcaps_min']})")
            below_threshold += 1
        if r["evidence"] < _THRESHOLDS["evidence_min"]:
            print(f"  ⚠ below threshold: evidence={r['evidence']} (need >= {_THRESHOLDS['evidence_min']})")
            below_threshold += 1
        if r["peers"] < _THRESHOLDS["peers_min"]:
            print(f"  ⚠ below threshold: peers={r['peers']} (need >= {_THRESHOLDS['peers_min']})")
            below_threshold += 1
        if r["warnings_sample"]:
            for w in r["warnings_sample"]:
                print(f"  • {w[:140]}")
        if r["warnings_count"] > 3:
            print(f"  • … +{r['warnings_count'] - 3} more warnings")

    print()
    print(f"summary: {len(rows) - failures}/{len(rows)} parsed; "
          f"{failures} failed; {below_threshold} below-threshold counts")
    return 1 if (failures or below_threshold) else 0


if __name__ == "__main__":
    raise SystemExit(main())
