#!/usr/bin/env python3
"""
highlight_stripper.py — Remove ALL <a:highlight> elements from slide XML files.

Template uses <a:highlight><a:srgbClr val="FFFF00"/></a:highlight> as visual
markers for text needing replacement. These MUST be stripped after editing.

Usage:
    python3 highlight_stripper.py --unpacked-dir unpacked/
"""
import argparse, glob, os, re, sys


def strip_highlights(unpacked_dir: str) -> dict:
    """Remove all <a:highlight>...</a:highlight> from slide XMLs.
    
    Returns dict: {slide_filename: count_removed}
    """
    slides_dir = os.path.join(unpacked_dir, "ppt", "slides")
    if not os.path.isdir(slides_dir):
        print(f"ERROR: {slides_dir} not found", file=sys.stderr)
        sys.exit(1)

    # Pattern matches <a:highlight> ... </a:highlight> including nested content
    # Works on single-line and multi-line variants
    pattern = re.compile(
        r'<a:highlight>\s*<a:srgbClr[^/]*/>\s*</a:highlight>',
        re.DOTALL
    )

    results = {}
    total = 0
    for xml_path in sorted(glob.glob(os.path.join(slides_dir, "slide*.xml"))):
        fname = os.path.basename(xml_path)
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()

        count = len(pattern.findall(content))
        if count > 0:
            content = pattern.sub("", content)
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(content)
            results[fname] = count
            total += count
            print(f"  {fname}: removed {count} highlight(s)")

    if total == 0:
        print("  No highlights found — deck is clean.")
    else:
        print(f"\n  TOTAL: {total} highlights removed across {len(results)} slide(s).")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strip yellow highlights from all slides")
    parser.add_argument("--unpacked-dir", required=True, help="Path to unpacked PPTX directory")
    args = parser.parse_args()

    results = strip_highlights(args.unpacked_dir)
    sys.exit(1 if results else 0)  # Non-zero if highlights were found
