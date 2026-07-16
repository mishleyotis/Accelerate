"""
Local-filesystem variant of the DMA-Drive parse-only audit.

`historical_backfill.py --parse-only --sample N` walks the production
Google Drive folder and emits one `PARSEONLY <json>` line per sampled
folder. That path requires Drive credentials (SA with Viewer access on
the DMA Assets root) and a network round-trip per file.

This script provides the SAME audit contract — same JSON shape, same
emitter prefix, same return semantics — against a local directory of
unpacked DMA package folders. Two use cases:

  1. Operator audit when Drive is unavailable (sandbox, CI, locked-down
     network). Drop a representative slice of packages on disk; run
     `python -m app.scripts.parse_audit_local --dir <path> --sample 50`.

  2. Parser regression in CI. The simulate-all-deploy-stages.sh harness
     runs this against `tests/fixtures/dma_packages_real_samples/` to
     prove every parser change still handles the real-input distribution
     end-to-end. No Drive creds required → runs in every environment.

Discovery rule (deliberately narrow, matches the production layout):
  Each child directory of `--dir` that contains a top-level
  `MANIFEST.json` OR a `03_scoring_workbook/` subdirectory is treated
  as a candidate DMA package. Other children are skipped silently with
  a `SKIP: <name> — not a DMA package` line on stderr so the operator
  can see what was ignored.

Sampling: identical semantics to historical_backfill — `--sample N`
random-shuffles the candidates and takes the first N. `DMA_SAMPLE_SEED`
pins the seed so re-runs against the same input pick the same set
(useful for diffing a parser change's effect).

Exit codes:
  0 — every sampled package parsed (warnings allowed, never fatal)
  1 — at least one parse raised; the harness aggregates and exits non-
      zero so CI fails loud
  2 — argv invalid (missing --dir, --sample with no value, etc.)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

# We import lazily inside main() so `python -m app.scripts.parse_audit_local
# --help` works without paying the parse_package import cost (+ side-effects).


def _is_dma_package_dir(p: Path) -> bool:
    """Heuristic: a directory looks like a DMA package if it contains
    either MANIFEST.json at the top or 03_scoring_workbook/ as a
    subdirectory. Mirrors what `parse_package` actually requires."""
    if not p.is_dir():
        return False
    if (p / "MANIFEST.json").exists():
        return True
    return (p / "03_scoring_workbook").is_dir()


def _discover_packages(root: Path) -> list[Path]:
    """Return all DMA-package candidate directories directly under root,
    sorted by name for deterministic enumeration."""
    if not root.exists():
        raise FileNotFoundError(f"--dir does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"--dir is not a directory: {root}")
    return sorted(
        (child for child in root.iterdir() if _is_dma_package_dir(child)),
        key=lambda p: p.name,
    )


def _summarise(pkg, folder_path: Path) -> dict:
    """Build the same JSON payload shape that historical_backfill.py
    emits for `PARSEONLY` lines, with `folder_id` set to the absolute
    local path so downstream grep/jq pipelines stay uniform."""
    return {
        "folder_id": str(folder_path.resolve()),
        "folder_name": folder_path.name,
        "run_id": pkg.run_manifest.run_id,
        "institution": pkg.run_manifest.institution_name,
        "subcap_count": len(pkg.subcap_scores),
        "evidence_count": len(pkg.evidence),
        "recommendation_count": len(pkg.recommendations),
        "peers_count": len(pkg.peers),
        "parser_warnings_count": len(pkg.parser_warnings),
        "parser_warnings": pkg.parser_warnings[:10],
        "parser_observations_count": len(pkg.parser_observations),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="parse_audit_local",
        description="Local-filesystem variant of the DMA parse-only audit.",
    )
    ap.add_argument(
        "--dir", required=True, type=Path,
        help="Root directory containing unpacked DMA package folders.",
    )
    ap.add_argument(
        "--sample", type=int, default=None,
        help="Random-shuffle and take first N candidates. Defaults to all.",
    )
    ap.add_argument(
        "--seed", type=str, default=None,
        help=(
            "Random seed (overrides DMA_SAMPLE_SEED env). Pins the "
            "shuffle for reproducible diffs across parser changes."
        ),
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = _build_arg_parser()
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        # argparse exits 2 on its own for bad input — match historical_backfill.
        return int(e.code) if isinstance(e.code, int) else 2

    if args.sample is not None and args.sample <= 0:
        print("FATAL: --sample N must be > 0", file=sys.stderr, flush=True)
        return 2

    try:
        candidates = _discover_packages(args.dir)
    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"FATAL: {e}", file=sys.stderr, flush=True)
        return 2

    print(
        f"parse_audit_local: scanning {args.dir.resolve()} — "
        f"found {len(candidates)} candidate package(s)",
        flush=True,
    )

    if args.sample is not None and args.sample < len(candidates):
        seed = args.seed or os.environ.get("DMA_SAMPLE_SEED")
        if seed:
            random.seed(seed)
        random.shuffle(candidates)
        candidates = candidates[: args.sample]
        print(
            f"parse_audit_local: --sample {args.sample} narrowed to "
            f"{len(candidates)} folder(s) "
            f"(seed={'pinned' if seed else 'random'})",
            flush=True,
        )

    if not candidates:
        print("parse_audit_local: nothing to do.", flush=True)
        return 0

    # Lazy import — keeps `--help` cheap and lets a missing dependency
    # surface as a clear ImportError at the right time.
    from app.services.parsers.dma_package import parse_package

    fail_count = 0
    warn_total = 0
    obs_total = 0
    for i, folder in enumerate(candidates, start=1):
        print(f"[{i}/{len(candidates)}] {folder.name}", flush=True)
        try:
            pkg = parse_package(folder)
        except Exception as e:
            print(
                f"PARSEONLY_ERROR {folder.name}: "
                f"{type(e).__name__}: {e}",
                flush=True,
            )
            fail_count += 1
            continue
        summary = _summarise(pkg, folder)
        warn_total += summary["parser_warnings_count"]
        obs_total += summary["parser_observations_count"]
        print("PARSEONLY " + json.dumps(summary, ensure_ascii=False), flush=True)

    print(
        f"parse_audit_local: done — {len(candidates)} parsed, "
        f"{fail_count} failed, {warn_total} parser_warnings total, "
        f"{obs_total} parser_observations total",
        flush=True,
    )
    return 1 if fail_count else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
