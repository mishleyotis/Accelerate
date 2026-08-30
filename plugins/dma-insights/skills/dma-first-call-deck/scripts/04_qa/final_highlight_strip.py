#!/usr/bin/env python3
"""
final_highlight_strip.py — FINAL highlight strip + verification on packed PPTX.

Runs as the ABSOLUTE LAST step before delivery. Unpacks the PPTX, strips ALL
<a:highlight> elements from ALL slides, repacks, and VERIFIES zero remain.

This catches highlights that:
  - Were missed by per-batch strip (e.g., batch edits introduced new ones)
  - Exist in slides that weren't edited (template leftovers)
  - Were reintroduced by python-pptx or str_replace operations

Usage:
    python3 scripts/04_qa/final_highlight_strip.py \
        --pptx working/deck.pptx \
        --out working/deck.pptx

Exit codes: 0 = clean (no highlights found or all removed + verified)
            1 = FAILED verification (highlights persist after strip — manual fix needed)
"""
import argparse, glob, os, re, shutil, subprocess, sys, tempfile, zipfile


HIGHLIGHT_PATTERNS = [
    # Standard: <a:highlight><a:srgbClr val="FFFF00"/></a:highlight>
    re.compile(r'<a:highlight>\s*<a:srgbClr[^/]*/>\s*</a:highlight>', re.DOTALL),
    # Any highlight color, not just yellow
    re.compile(r'<a:highlight>.*?</a:highlight>', re.DOTALL),
]


def unpack_pptx(pptx_path, dest_dir):
    """Unpack PPTX (which is a ZIP) to dest_dir."""
    with zipfile.ZipFile(pptx_path, 'r') as z:
        z.extractall(dest_dir)


def repack_pptx(src_dir, pptx_path):
    """Repack directory into PPTX."""
    with zipfile.ZipFile(pptx_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                fp = os.path.join(root, f)
                arcname = os.path.relpath(fp, src_dir)
                z.write(fp, arcname)


def strip_all_highlights(unpacked_dir):
    """Strip ALL highlight elements from ALL slide XMLs. Returns total removed."""
    slides_dir = os.path.join(unpacked_dir, "ppt", "slides")
    if not os.path.isdir(slides_dir):
        print(f"  ERROR: {slides_dir} not found", file=sys.stderr)
        return -1

    total = 0
    for xml_path in sorted(glob.glob(os.path.join(slides_dir, "slide*.xml"))):
        fname = os.path.basename(xml_path)
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()

        count = 0
        for pattern in HIGHLIGHT_PATTERNS:
            matches = len(pattern.findall(content))
            if matches > 0:
                content = pattern.sub("", content)
                count += matches

        if count > 0:
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(content)
            total += count
            print(f"  {fname}: stripped {count} highlight(s)")

    return total


def verify_clean(unpacked_dir):
    """Verify ZERO highlights remain in any slide XML."""
    slides_dir = os.path.join(unpacked_dir, "ppt", "slides")
    remaining = 0
    dirty_slides = []

    for xml_path in sorted(glob.glob(os.path.join(slides_dir, "slide*.xml"))):
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()
        for pattern in HIGHLIGHT_PATTERNS:
            matches = len(pattern.findall(content))
            if matches > 0:
                remaining += matches
                dirty_slides.append(os.path.basename(xml_path))

    return remaining, dirty_slides


def main():
    parser = argparse.ArgumentParser(description="Final highlight strip + verification")
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--out", help="Output path (default: overwrite input)")
    args = parser.parse_args()

    out_path = args.out or args.pptx

    # Work in a temp directory
    tmpdir = tempfile.mkdtemp(prefix="highlight_strip_")
    try:
        # Unpack
        unpack_pptx(args.pptx, tmpdir)

        # Strip
        removed = strip_all_highlights(tmpdir)
        if removed == 0:
            print("\n✓ No highlights found — deck is already clean.")
        elif removed > 0:
            print(f"\n  Stripped {removed} total highlight(s).")

        # Verify
        remaining, dirty = verify_clean(tmpdir)
        if remaining > 0:
            print(f"\n✗ VERIFICATION FAILED: {remaining} highlights still remain in: {', '.join(dirty)}")
            print(f"  These may use a non-standard highlight format. Manual XML inspection needed.")
            sys.exit(1)
        else:
            print(f"  ✓ Verification PASSED — zero highlights remain.")

        # Repack
        repack_pptx(tmpdir, out_path)
        print(f"  ✓ Saved clean deck to {out_path}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
