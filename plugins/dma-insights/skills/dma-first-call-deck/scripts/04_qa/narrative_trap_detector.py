#!/usr/bin/env python3
"""
narrative_trap_detector.py — Detect 5 narrative anti-patterns.

1. Insight Without Stakes: numbers without consequence language
2. All Evidence No Tension: no complication slides
3. Solution Without Urgency: no time language in recommendation slides
4. Generic Close: slide 20 missing mobilization elements
5. Label Creep: >30% of body headlines are labels
"""
import argparse, json, re, os, sys, glob

CONSEQUENCE_WORDS = ["means", "results in", "implies", "enables", "unlocks", "translates to",
                     "creates", "drives", "positions", "opportunity"]
URGENCY_WORDS = ["by ", "before ", "deadline", "week of", "starts ", "schedule", "within"]
LABEL_PATTERNS = ["overview","summary","agenda","next steps","key findings","assessment",
                  "current state","heat map","key strengths","opportunities","profile"]

def extract_text(unpacked_dir, slide_num):
    sf = os.path.join(unpacked_dir, f"ppt/slides/slide{slide_num}.xml")
    if not os.path.exists(sf): return ""
    with open(sf) as f: content = f.read()
    return " ".join(re.findall(r'<a:t>([^<]+)</a:t>', content)).lower()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacked-dir", required=True)
    parser.add_argument("--out", help="Output JSON")
    args = parser.parse_args()

    traps = []

    # Trap 1: Insight Without Stakes (data slides 9, 13, 14, 16)
    for sn in [9, 13, 14, 16]:
        text = extract_text(args.unpacked_dir, sn)
        has_numbers = bool(re.search(r'\d', text))
        has_consequence = any(w in text for w in CONSEQUENCE_WORDS)
        if has_numbers and not has_consequence:
            traps.append({"trap": "Insight Without Stakes", "slide": sn,
                          "detail": "Data present but no consequence language (means/enables/unlocks)"})

    # Trap 3: Solution Without Urgency (slides 16, 20)
    for sn in [16, 20]:
        text = extract_text(args.unpacked_dir, sn)
        if not any(w in text for w in URGENCY_WORDS):
            traps.append({"trap": "Solution Without Urgency", "slide": sn,
                          "detail": "No time-specific language found"})

    # Trap 4: Generic Close (slide 20)
    text20 = extract_text(args.unpacked_dir, 20)
    elements = sum([
        any(w in text20 for w in ["week of", "action", "owner"]),
        any(w in text20 for w in ["bring", "deliver", "refined"]),
        any(w in text20 for w in ["positioned", "first step", "enables"]),
    ])
    if elements < 2:
        traps.append({"trap": "Generic Close", "slide": 20,
                      "detail": f"Only {elements}/3 mobilization elements present"})

    # Trap 5: Label Creep (slides 6-20 headlines)
    label_count = 0
    total_checked = 0
    for sn in range(6, 21):
        text = extract_text(args.unpacked_dir, sn)
        # First significant text block is likely the headline
        first_line = text[:80]
        total_checked += 1
        if any(p in first_line for p in LABEL_PATTERNS) and len(first_line.split()) <= 6:
            label_count += 1
    
    if total_checked > 0 and (label_count / total_checked) > 0.3:
        traps.append({"trap": "Label Creep", "slide": "6-20",
                      "detail": f"{label_count}/{total_checked} headlines ({label_count/total_checked:.0%}) are labels"})

    if args.out:
        with open(args.out, "w") as f: json.dump(traps, f, indent=2)
    
    print(f"Narrative traps detected: {len(traps)}")
    for t in traps:
        print(f"  ⚠ {t['trap']} (Slide {t['slide']}): {t['detail']}")
    if traps: sys.exit(1)

if __name__ == "__main__":
    main()
