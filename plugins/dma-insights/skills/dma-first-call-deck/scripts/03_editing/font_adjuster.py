#!/usr/bin/env python3
"""
font_adjuster.py — Adjust font sizes on specific shapes within slide XML.

Modifies sz= attributes on <a:rPr> and <a:defRPr> elements for a target shape,
preserving all other formatting (bold, italic, color, typeface).

Safe Font Size Ranges (from editing contract Section 12):
  Slide 16 Sh3 headline:     26pt → 21pt (safe min)
  Slide 16 Sh8/9/10 cards:   11pt → 9pt (safe min)
  Slide 16 Sh12 outcomes:    10pt → 9pt (safe min)
  Slide 17-19 Sh5/11/14 desc:12pt → 10pt (safe min)
  Slide 20 Sh0/Sh8 body:     11pt → 10pt (safe min)

Absolute minimums: 17pt headlines, 7pt body, 6pt labels.

Usage:
    python3 font_adjuster.py --slide unpacked/ppt/slides/slide16.xml \\
        --shapes 3:2100,8:900,9:900,10:900,12:900
    # shape_index:target_size_in_hundredths_pt (e.g. 2100 = 21pt)
"""
import argparse, re, sys, xml.etree.ElementTree as ET

DRAW_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PRES_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

ABSOLUTE_MINIMUMS = {
    "headline": 1700,  # 17pt in hundredths
    "body": 700,       # 7pt
    "label": 600,      # 6pt
}


def adjust_shape_font(slide_path: str, shape_idx: int, target_sz: int) -> dict:
    """Adjust all font sizes in a shape to target_sz.

    Args:
        slide_path: Path to slide XML file
        shape_idx: 0-based shape index within <p:sp> elements
        target_sz: Target size in hundredths of a point (e.g. 2100 = 21pt)

    Returns:
        dict with old_sizes, new_size, runs_changed
    """
    ET.register_namespace("", PRES_NS)
    ET.register_namespace("a", DRAW_NS)

    tree = ET.parse(slide_path)
    root = tree.getroot()

    shapes = root.findall(f".//{{{PRES_NS}}}sp")
    if shape_idx >= len(shapes):
        print(f"ERROR: Shape index {shape_idx} out of range (max {len(shapes)-1})",
              file=sys.stderr)
        return {"error": True}

    sp = shapes[shape_idx]
    old_sizes = set()
    runs_changed = 0

    # Adjust <a:rPr> (run properties)
    for rpr in sp.findall(f".//{{{DRAW_NS}}}rPr"):
        old_sz = rpr.get("sz")
        if old_sz:
            old_sizes.add(int(old_sz))
        rpr.set("sz", str(target_sz))
        runs_changed += 1

    # Adjust <a:defRPr> (default run properties)
    for drpr in sp.findall(f".//{{{DRAW_NS}}}defRPr"):
        old_sz = drpr.get("sz")
        if old_sz:
            old_sizes.add(int(old_sz))
        drpr.set("sz", str(target_sz))
        runs_changed += 1

    # Adjust <a:endParaRPr> (end-of-paragraph run properties)
    for epr in sp.findall(f".//{{{DRAW_NS}}}endParaRPr"):
        old_sz = epr.get("sz")
        if old_sz:
            old_sizes.add(int(old_sz))
        epr.set("sz", str(target_sz))
        runs_changed += 1

    tree.write(slide_path, xml_declaration=True, encoding="UTF-8")

    result = {
        "shape_idx": shape_idx,
        "old_sizes_pt": sorted([s / 100 for s in old_sizes]),
        "new_size_pt": target_sz / 100,
        "runs_changed": runs_changed,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="Adjust font sizes on slide shapes")
    parser.add_argument("--slide", required=True, help="Path to slide XML file")
    parser.add_argument(
        "--shapes", required=True,
        help="Comma-separated shape_index:target_size pairs. "
             "Size in hundredths of pt (e.g. 3:2100 = Sh3 to 21pt)"
    )
    args = parser.parse_args()

    pairs = []
    for item in args.shapes.split(","):
        idx_str, sz_str = item.strip().split(":")
        idx, sz = int(idx_str), int(sz_str)

        # Validate against absolute minimums
        if sz < ABSOLUTE_MINIMUMS["label"]:
            print(f"ERROR: Target {sz/100}pt for Sh{idx} is below absolute minimum "
                  f"({ABSOLUTE_MINIMUMS['label']/100}pt)", file=sys.stderr)
            sys.exit(1)
        pairs.append((idx, sz))

    print(f"Adjusting {len(pairs)} shape(s) in {args.slide}:")
    for idx, sz in pairs:
        result = adjust_shape_font(args.slide, idx, sz)
        if result.get("error"):
            sys.exit(1)
        old = result["old_sizes_pt"]
        print(f"  Sh{idx}: {old} → {result['new_size_pt']}pt "
              f"({result['runs_changed']} runs changed)")

    print("Done.")


if __name__ == "__main__":
    main()
