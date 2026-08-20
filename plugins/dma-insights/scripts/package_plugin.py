#!/usr/bin/env python3
"""Build the claude.ai-uploadable zip of the dma-insights plugin.

The upload validator's rules arrive one failed upload at a time (a top-level
bin/ on 2026-08-20, then a 500-character description cap the same night), so
packaging is a script with a test rather than an ad-hoc zip command: every
rule the validator has ever named is asserted HERE, before a person burns an
upload attempt on it. `claude plugin validate` passes manifests the uploader
refuses — measured: it accepted a 734-character description — so the CLI
validator is necessary but nowhere near sufficient.

    python3 scripts/package_plugin.py [--out DIR]

Writes dma-insights-<version>.zip and prints one line per check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store"}
EXCLUDE_SUFFIX = {".pyc"}

# Every rule the claude.ai upload validator has enforced against this plugin,
# with the date it was learned. Add to this list; never remove.
DESCRIPTION_MAX = 500          # "at most 500 characters" (2026-08-20)
FORBIDDEN_TOP_LEVEL = {"bin"}  # "may not ship bin/ executables" (2026-08-20)
MAX_ZIP_BYTES = 50 * 1024 * 1024  # not yet validator-confirmed; sanity bound


def iter_files():
    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(PLUGIN)
        if EXCLUDE_PARTS & set(rel.parts) or rel.suffix in EXCLUDE_SUFFIX:
            continue
        yield rel


def check(manifest: dict, entries: list) -> list:
    """Return failure strings; empty means uploadable as far as we know."""
    fails = []
    desc = manifest.get("description") or ""
    if len(desc) > DESCRIPTION_MAX:
        fails.append(f"description is {len(desc)} chars (max {DESCRIPTION_MAX})")
    if not re.search(r"\(\d+ tools\)", desc):
        fails.append("description lost its '(N tools)' count — doctor.py's "
                     "roster reconciliation parses it")
    tops = {str(e).split("/", 1)[0] for e in entries}
    for bad in FORBIDDEN_TOP_LEVEL & tops:
        fails.append(f"top-level {bad}/ present — claude.ai refuses PATH-added "
                     "executables")
    if ".claude-plugin/plugin.json" not in {str(e) for e in entries}:
        fails.append("manifest missing from archive root")
    if not re.fullmatch(r"\d+\.\d+\.\d+", manifest.get("version") or ""):
        fails.append(f"version {manifest.get('version')!r} is not semver")
    for e in entries:
        if "__pycache__" in str(e) or str(e).endswith(".pyc"):
            fails.append(f"bytecode shipped: {e}")
    return fails


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    entries = list(iter_files())
    fails = check(manifest, entries)
    for f in fails:
        print(f"FAIL {f}", file=sys.stderr)
    if fails:
        return 1

    out_dir = Path(args.out) if args.out else PLUGIN.parent.parent
    out = out_dir / f"dma-insights-{manifest['version']}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in entries:
            z.write(PLUGIN / rel, str(rel))
    size = out.stat().st_size
    if size > MAX_ZIP_BYTES:
        print(f"FAIL zip is {size} bytes (bound {MAX_ZIP_BYTES})", file=sys.stderr)
        return 1
    print(f"ok  {out}  {len(entries)} files  {size//1024} KiB  "
          f"description {len(manifest['description'])}/{DESCRIPTION_MAX} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
