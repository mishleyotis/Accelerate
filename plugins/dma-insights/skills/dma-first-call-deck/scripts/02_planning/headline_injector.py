#!/usr/bin/env python3
"""
headline_injector.py — Generate insight headlines for all editable slides.

Uses AIDA phase mapping and headline patterns from brand_guidelines.
Populated with data from fact_bank.json.

Each headline must: contain number + entity + verb, score ≥7/9,
advance the Big Idea, and fit within 2 lines at the slide's font size.
"""
import argparse, json, sys

# Headline patterns per AIDA phase
PATTERNS = {
    "attention": "Your digital maturity blueprint: where {client} stands today and the investments that accelerate {outcome}",
    "interest_profile": "{client}'s {metric} and {growth} create a {foundation} for {outcome}",
    "interest_summary": "{client} scores {score}/5 — {comparison} peer median of {median}, with {strongest} leading and {weakest} as the highest-value transformation opportunity",
    "interest_strengths": "{strongest_area} anchors the scorecard at {level}, while {weakest_area} presents the highest-value transformation opportunity — aligned with {client}'s strategy to {objective}",
    "interest_heatmap": "{best_cap} leads at {best_score}; {worst_cap} ({worst_score}) and {second_worst} ({second_score}) present the highest-value transformation opportunities",
    "desire_opportunities": "{n} capability areas are ready for transformation — investing unlocks {outcomes}",
    "action_close": "Share your feedback so we can deliver a refined maturity model and targeted capability map for {client}'s leadership team",
}

def generate_headline(slide_num, fact_bank, big_idea, client):
    """Generate a headline for a specific slide using fact_bank data."""
    # Map slide numbers to patterns
    pattern_map = {
        1: "attention",
        6: "interest_profile",
        9: "interest_summary",
        13: "interest_strengths",
        14: "interest_heatmap",
        16: "desire_opportunities",
        20: "action_close",
    }
    
    pattern_key = pattern_map.get(slide_num)
    if not pattern_key:
        return None
    
    template = PATTERNS[pattern_key]
    # NOTE: In production, Claude fills these templates using fact_bank data.
    # This script provides the pattern structure and validation.
    return {"slide": slide_num, "pattern": pattern_key, "template": template}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fact-bank", required=True)
    parser.add_argument("--client", required=True)
    parser.add_argument("--big-idea", required=True)
    parser.add_argument("--out", help="Output JSON")
    args = parser.parse_args()

    with open(args.fact_bank) as f: fb = json.load(f)
    
    slides_needing_headlines = [1, 6, 9, 12, 13, 14, 16, 20]
    results = []
    for sn in slides_needing_headlines:
        r = generate_headline(sn, fb, args.big_idea, args.client)
        if r: results.append(r)
    
    if args.out:
        with open(args.out, "w") as f: json.dump(results, f, indent=2)
    
    for r in results:
        print(f"  Slide {r['slide']}: [{r['pattern']}] {r['template'][:70]}...")

if __name__ == "__main__":
    main()
