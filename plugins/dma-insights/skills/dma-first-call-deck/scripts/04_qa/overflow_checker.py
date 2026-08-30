#!/usr/bin/env python3
"""
overflow_checker.py — Pre-edit text overflow detection.

Calculates max characters per shape using font size and dimensions.
Flags shapes where replacement text exceeds capacity.
Headlines flagged if >2 lines.
"""
import argparse, json, math, sys

def check_overflow(shape_width_px, shape_height_px, font_pt, text, is_headline=False):
    if font_pt <= 0: return {"overflow": False, "reason": "no_font_info"}
    chars_per_line = shape_width_px / (font_pt * 0.55)
    max_lines = shape_height_px / (font_pt * 1.3)
    max_chars = int(chars_per_line * max_lines)
    est_lines = math.ceil(len(text) / chars_per_line) if chars_per_line > 0 else 0

    overflow = len(text) > max_chars
    headline_long = is_headline and est_lines > 2

    return {
        "overflow": overflow,
        "headline_too_long": headline_long,
        "max_chars": max_chars,
        "text_chars": len(text),
        "estimated_lines": est_lines,
        "chars_per_line": round(chars_per_line),
        "max_lines": round(max_lines),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checks", required=True, help="JSON: [{slide,shape,width_px,height_px,font_pt,text,is_headline}]")
    parser.add_argument("--out", help="Output JSON")
    args = parser.parse_args()

    with open(args.checks) as f: checks = json.load(f)
    results = []
    flagged = 0
    for c in checks:
        r = check_overflow(c["width_px"], c["height_px"], c["font_pt"], c["text"], c.get("is_headline", False))
        r["slide"] = c["slide"]
        r["shape"] = c["shape"]
        results.append(r)
        if r["overflow"] or r.get("headline_too_long"):
            flagged += 1
            icon = "🔴" if r["overflow"] else "🟡"
            print(f"  {icon} Slide {c['slide']} Sh{c['shape']}: {r['text_chars']}/{r['max_chars']} chars, ~{r['estimated_lines']} lines")

    if args.out:
        with open(args.out, "w") as f: json.dump(results, f, indent=2)
    print(f"\n{flagged}/{len(checks)} shapes flagged for overflow")
    if flagged: sys.exit(1)

if __name__ == "__main__":
    main()
