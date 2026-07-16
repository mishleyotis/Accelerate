"""WAVE-0 catalogue-presence guard for the derived-surfaces chain.

Guarantees the canonical capability catalogue (``ccg_l3_platforms`` +
``ccg_l4_features``) is populated in the DB BEFORE the enrichment/fit steps
that read it. This is the concrete "ensure the catalogue is loaded and
processed appropriately for enrichment" contract:

  * ``apply_catalogue_platforms`` re-parses the workbooks itself, so its
    subcap→platform tagging self-heals regardless of the DB tables.
  * BUT ``recompute_platform_fit`` (the analyst-recommendation fit engine),
    ``platform_affinity.load_catalogue_affinity`` and the enrichment sweep
    read the DB ``ccg_l4_features`` / ``ccg_l3_platforms`` rows directly. On
    an empty catalogue the L3/L4-coverage fit factor collapses to its neutral
    prior and enrichment loses its capability grounding — silently.

In production the hourly ``ccg_loader`` Cloud Scheduler keeps the catalogue
populated (136 L3 platforms + ~12k L4 features for v7.0). This guard closes
the gap for the fresh-DB deploy, the disabled/failed hourly cron, and any
staging environment: it self-heals so enrichment never grounds on nothing.

Idempotent + best-effort by construction:
  * When the catalogue is already present (the normal case) it is a cheap
    ``COUNT`` no-op — no workbook parse, no writes.
  * When thin/empty it invokes the SAME ``ccg_loader`` canonical-promote used
    hourly, against the workbooks baked into the image.
  * It NEVER fails the chain: DATABASE_URL unset, table missing, loader crash
    — every path exits 0. The hourly loader and the workbook-reparsing
    ``apply_catalogue_platforms`` remain the backstops (graceful degradation).

Usage:
  DATABASE_URL=postgresql+asyncpg://... \
    python -m app.scripts.ensure_catalogue [--version v7.0] \
      [--workbooks-dir docs/reference/catalogue/v7.0] [--min-features 500]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

# Reuse the PROVEN workbook-directory resolver (works from any CWD and inside
# the Cloud Run job) rather than duplicating the search logic.
from app.scripts.apply_catalogue_platforms import _resolve_workbooks_dir

# A version's canonical L4 feature set is ~12k rows; a bare ingest-time
# bootstrap stub is a handful. This floor sits well above the stubs and well
# below a real load, so "thin" reliably means "needs the loader".
_DEFAULT_MIN_FEATURES = 500


async def _count_features(dsn: str, version: str) -> int | None:
    """Return the ccg_l4_features row count for `version`, or None when the
    count cannot be taken (DSN bad, table absent, DB unreachable)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(dsn, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT COUNT(*) FROM ccg_l4_features WHERE version = :v"),
                {"v": version},
            )
            return int(row.scalar_one())
    except Exception as e:
        print(f"ensure_catalogue: feature count unavailable ({e!s}); "
              "treating as absent", flush=True)
        return None
    finally:
        await engine.dispose()


def _run_loader(version: str, workbooks_dir: Path) -> int:
    """Invoke the canonical ccg_loader against the baked workbooks. Returns the
    loader's exit code (0 on success). Output tail is echoed for the operator."""
    cmd = [
        sys.executable, "-m", "workers.ccg_loader.main",
        "--version", version, "--workbooks-dir", str(workbooks_dir),
    ]
    print(f"ensure_catalogue: running loader → {' '.join(cmd)}", flush=True)
    # `workers` lives one level above the backend package; the image bakes both
    # onto PYTHONPATH, but a bare local invocation needs them added so both
    # `workers.ccg_loader.main` AND the loader's `app.services.*` job-tracking
    # imports resolve (same fix apply_catalogue_platforms carries). Prepend the
    # app root (holds `workers/`) and the backend dir (holds `app/`) when they
    # exist so the loader writes its job_executions visibility row locally too.
    env = dict(os.environ)
    app_root = Path(__file__).resolve().parents[3]  # apps/dma-insights/
    extra_paths = [p for p in (app_root, app_root / "backend") if p.is_dir()]
    if extra_paths:
        joined = os.pathsep.join(str(p) for p in extra_paths)
        env["PYTHONPATH"] = (
            f"{joined}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
        )
    proc = subprocess.run(cmd, cwd=str(app_root), env=env,
                          capture_output=True, text=True, timeout=1200)
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-20:])
    print(f"ensure_catalogue: loader exit={proc.returncode}\n{tail}", flush=True)
    return proc.returncode


async def _run(args: argparse.Namespace) -> int:
    version = args.version
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ensure_catalogue: DATABASE_URL not set — skipping (best-effort); "
              "the hourly ccg_loader remains the backstop", flush=True)
        return 0

    count = await _count_features(dsn, version)
    if count is not None and count >= args.min_features:
        print(f"ensure_catalogue: catalogue present for {version} "
              f"({count} L4 features ≥ {args.min_features} floor) — no load "
              "needed", flush=True)
        return 0

    state = "empty/unreadable" if count is None else f"thin ({count} features)"
    print(f"ensure_catalogue: catalogue {state} for {version} — self-healing "
          "via ccg_loader", flush=True)

    workbooks_dir = _resolve_workbooks_dir(args.workbooks_dir)
    if not (workbooks_dir.is_dir() and any(workbooks_dir.glob("Pillar_*_v7.0.xlsx"))):
        print(f"ensure_catalogue: no v7.0 workbooks under {workbooks_dir} — "
              "cannot self-heal here; the hourly ccg_loader (GCS workbooks) "
              "remains the backstop", flush=True)
        return 0

    rc = _run_loader(version, workbooks_dir)
    after = await _count_features(dsn, version)
    if after is not None:
        print(f"ensure_catalogue: post-load L4 feature count for {version} = "
              f"{after}", flush=True)
    if rc != 0:
        print("ensure_catalogue: loader returned non-zero — continuing "
              "(best-effort; enrichment steps degrade gracefully)", flush=True)
    return 0  # never fail the chain


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--version", default=None,
                   help="catalogue version (default: settings.catalogue_default_version)")
    p.add_argument("--workbooks-dir", default="docs/reference/catalogue/v7.0",
                   help="dir holding the Pillar_*_v7.0.xlsx workbooks")
    p.add_argument("--min-features", type=int, default=_DEFAULT_MIN_FEATURES,
                   help="minimum ccg_l4_features rows below which a reload fires")
    args = p.parse_args()
    if not args.version:
        try:
            from app.config import settings
            args.version = settings.catalogue_default_version
        except Exception:
            args.version = "v7.0"
    try:
        return asyncio.run(_run(args))
    except Exception as e:
        print(f"ensure_catalogue: unexpected error ({e!s}) — skipping "
              "(best-effort)", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
