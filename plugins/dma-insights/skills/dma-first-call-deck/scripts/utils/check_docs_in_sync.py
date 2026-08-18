#!/usr/bin/env python3
"""
check_docs_in_sync.py — Verify generated docs match color_level_system.py.

Runs generate_color_docs into a temp dir and diffs against the checked-in
files in references/_generated/. Fails loudly if any differ. Intended for
CI or pre-commit use: if someone edits color_level_system.py without
regenerating, this will catch it.

Usage:
  python3 scripts/utils/check_docs_in_sync.py
    → exit 0 if all docs match, exit 1 if any drift (diff printed)

The script is idempotent and non-destructive — it never writes to the
canonical _generated/ folder; it only reads and compares.
"""
import difflib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent


def run_generator_to_tempdir():
    """Load both generators, monkeypatch _OUT, call their main() funcs.

    Returns the temp directory path containing freshly-generated docs.
    """
    tmp = tempfile.mkdtemp(prefix="docsync_")
    tmp_path = Path(tmp)

    # Silence the prints
    import io
    orig_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        for gen_name in ("generate_color_docs.py", "generate_dependency_graph.py"):
            gen_path = _HERE / gen_name
            spec = importlib.util.spec_from_file_location(f"gen_mod_{gen_name}", gen_path)
            gen_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gen_mod)
            gen_mod._OUT = tmp_path
            gen_mod.main()
    finally:
        sys.stdout = orig_stdout

    return tmp_path


def diff_file(expected_path, actual_path, label):
    """Return (is_same, diff_text)."""
    if not expected_path.exists():
        return False, f"{label}: MISSING from _generated/ — run generate_color_docs.py"
    expected = expected_path.read_text().splitlines(keepends=True)
    actual = actual_path.read_text().splitlines(keepends=True)
    if expected == actual:
        return True, ""
    diff = list(difflib.unified_diff(expected, actual,
                                     fromfile=f"{label} (checked-in)",
                                     tofile=f"{label} (regenerated)",
                                     n=3))
    return False, "".join(diff)


def main():
    expected_dir = _REPO / "references" / "_generated"
    tmp_dir = run_generator_to_tempdir()

    targets = ["color_authority.md", "per_slide_role_tables.md",
               "brand_level_tables.md", "input_dependency_graph.md"]
    drifts = []
    for name in targets:
        expected = expected_dir / name
        actual = tmp_dir / name
        same, diff = diff_file(expected, actual, name)
        if same:
            print(f"  ✓ {name} up to date")
        else:
            drifts.append((name, diff))
            print(f"  ✗ {name} DRIFTED")

    if drifts:
        print(f"\n{len(drifts)} file(s) drifted from source config.")
        print(f"Run `python3 scripts/utils/generate_color_docs.py` and")
        print(f"`python3 scripts/utils/generate_dependency_graph.py` to regenerate.\n")
        for name, diff in drifts:
            print(f"--- DIFF: {name} ---")
            print(diff[:3000])
            if len(diff) > 3000:
                print(f"... ({len(diff) - 3000} more chars)")
            print()
        sys.exit(1)

    print(f"\nAll {len(targets)} generated docs are in sync with color_level_system.py")
    sys.exit(0)


if __name__ == "__main__":
    main()
