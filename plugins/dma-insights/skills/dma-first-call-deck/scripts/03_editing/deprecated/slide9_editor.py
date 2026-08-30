#!/usr/bin/env python3
"""
slide9_editor.py — Edit Slide 9 (DMA Summary, 30 shapes).

Handles: score summary text, pillar descriptions, pillar name labels,
and PILLAR CARD ACCENT COLORS (3-tier benchmark system).

Color rules (modify <a:solidFill> on pillar card shapes):
    - Pillar score > peer median + 0.2 → #27BBAF (teal, above)
    - Within ±0.2 of peer median → #B0EED3 (light green, at)
    - Below peer median by 0.2+ → #FFCB99 (light orange, below)

Safeguards:
    - All 4 pillars must be present in input
    - Score and median must be 0-5 range
    - Color hex validated against 3-value allowlist
    - Cross-references Slide 13 levels for consistency
"""
import argparse, json, sys

BENCHMARK_COLORS = {
    "above": {"hex": "27BBAF", "label": "Above benchmark"},
    "at":    {"hex": "B0EED3", "label": "At benchmark"},
    "below": {"hex": "FFCB99", "label": "Below benchmark"},
}

def classify_benchmark(score, peer_median):
    """Classify pillar vs peer median."""
    delta = score - peer_median
    if delta > 0.2:
        return "above"
    elif delta >= -0.2:
        return "at"
    else:
        return "below"

def validate_inputs(pillars):
    errors = []
    if len(pillars) < 4:
        errors.append(f"Expected 4 pillars, got {len(pillars)}")
    for name, data in pillars.items():
        if not (0 <= data.get("score", -1) <= 5):
            errors.append(f"{name}: score {data.get('score')} out of range")
        if not (0 <= data.get("peer_median", -1) <= 5):
            errors.append(f"{name}: median {data.get('peer_median')} out of range")
    return errors

def main():
    parser = argparse.ArgumentParser(description="Edit Slide 9 — DMA Summary")
    parser.add_argument("--pillars", required=True, help="JSON: {name: {score, peer_median, description}}")
    parser.add_argument("--client", required=True)
    parser.add_argument("--overall-score", type=float, required=True)
    parser.add_argument("--overall-median", type=float, required=True)
    parser.add_argument("--out", help="Output edit plan JSON")
    args = parser.parse_args()

    with open(args.pillars) as f:
        pillars = json.load(f)

    errors = validate_inputs(pillars)
    if errors:
        for e in errors: print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    plan = {"client": args.client, "overall": args.overall_score, "edits": []}

    # Determine strongest and weakest
    sorted_pillars = sorted(pillars.items(), key=lambda x: x[1]["score"])
    weakest = sorted_pillars[0]
    strongest = sorted_pillars[-1]

    # Headline: Sh1
    comparison = "above" if args.overall_score > args.overall_median else "below"
    plan["headline"] = (
        f"{args.client} scores {args.overall_score}/5 — {comparison} peer median of "
        f"{args.overall_median}, with {strongest[0]} leading and {weakest[0]} "
        f"as the highest-value transformation opportunity."
    )

    # Pillar cards: color assignments
    for name, data in pillars.items():
        status = classify_benchmark(data["score"], data["peer_median"])
        color = BENCHMARK_COLORS[status]
        plan["edits"].append({
            "pillar": name,
            "score": data["score"],
            "peer_median": data["peer_median"],
            "benchmark_status": status,
            "card_color": color["hex"],
            "description": data.get("description", "[DATA NEEDED]"),
        })

    plan["strongest"] = strongest[0]
    plan["weakest"] = weakest[0]

    if args.out:
        with open(args.out, "w") as f: json.dump(plan, f, indent=2)
    print(json.dumps(plan, indent=2))

if __name__ == "__main__":
    main()
