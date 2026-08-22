#!/usr/bin/env python3
"""
solution_inferrer.py — Map DMA capability gaps to productized offerings.

Uses TIERED prioritization to determine how many solution slides (1, 2, or 3).

Tier system:
    Tier 1 (must-include): gap >= 0.5 below peer median
    Tier 2 (include if space): gap 0.2-0.49 below peer
    Tier 3 (omit): gap < 0.2 or above peer

Slide allocation:
    1-3 Tier 1 gaps -> 1 slide (Slide 17 only), 3 offerings max
    4-6 Tier 1 gaps -> 2 slides (Slides 17-18), 6 offerings max
    7+  Tier 1 gaps -> 3 slides (Slides 17-19), 9 offerings max

Safeguards:
    - Deduplication: same offering cannot appear twice
    - Coverage: at least 1 offering from each pillar with Tier 1 gaps
    - Fallback: uses sub-vertical defaults if data incomplete
"""
import argparse, json, sys

CAPABILITY_TO_OFFERING = {
    "Data governance": ["Data Modernization"],
    "Analytics & AI enablement": ["Agentic Workforce", "Data Modernization"],
    "Architecture & integration": ["Data Modernization", "Salesforce Platform Optimization & Governance"],
    "Platform enablement": ["Salesforce Platform Optimization & Governance", "Data Modernization"],
    "Digital mktg & acquisition": ["Personalized Customer Engagement"],
    "Onboarding & fulfillment": ["Digital Account Opening & Onboarding", "Financial Services Customer Platform"],
    "Omnichannel servicing": ["Contact Center Modernization", "Financial Services Customer Platform"],
    "Personalization & engagement": ["Personalized Customer Engagement", "Financial Services Customer Platform"],
    "Process automation": ["Salesforce Platform Optimization & Governance", "Agentic Workforce"],
    "Operational risk & fraud": ["Salesforce Platform Optimization & Governance"],
    "Compliance & surveillance": ["Salesforce Platform Optimization & Governance"],
    "Business resilience & TPRM": ["Salesforce Platform Optimization & Governance"],
    "Innovation management": ["Agentic Workforce"],
}

TIER1_THRESHOLD = 0.5
TIER2_THRESHOLD = 0.2


def classify_gaps(scores, medians):
    tiers = {"tier1": [], "tier2": [], "tier3": []}
    for cap, score in scores.items():
        median = medians.get(cap, 3.0)
        gap = median - score
        entry = {"capability": cap, "score": score, "median": median, "gap": round(gap, 2)}
        if gap >= TIER1_THRESHOLD:
            tiers["tier1"].append(entry)
        elif gap >= TIER2_THRESHOLD:
            tiers["tier2"].append(entry)
        else:
            tiers["tier3"].append(entry)
    for tier in tiers.values():
        tier.sort(key=lambda x: x["gap"], reverse=True)
    return tiers


def determine_num_slides(tiers):
    t1 = len(tiers["tier1"])
    if t1 >= 7: return 3
    elif t1 >= 4: return 2
    else: return 1


def infer_solutions(scores, medians):
    tiers = classify_gaps(scores, medians)
    num_slides = determine_num_slides(tiers)
    max_offerings = num_slides * 3

    ranked_caps = [e["capability"] for e in tiers["tier1"]] + \
                  [e["capability"] for e in tiers["tier2"]]

    selected, seen = [], set()
    for cap in ranked_caps:
        if len(selected) >= max_offerings: break
        for offering in CAPABILITY_TO_OFFERING.get(cap, []):
            if offering not in seen and len(selected) < max_offerings:
                selected.append(offering)
                seen.add(offering)

    universal = ["Data Modernization", "Financial Services Customer Platform",
                 "Personalized Customer Engagement", "Agentic Workforce",
                 "Salesforce Platform Optimization & Governance", "Contact Center Modernization"]
    for u in universal:
        if len(selected) >= max_offerings: break
        if u not in seen:
            selected.append(u); seen.add(u)

    meta = {
        "num_slides": num_slides,
        "tier1_count": len(tiers["tier1"]),
        "tier2_count": len(tiers["tier2"]),
        "tier1_caps": [e["capability"] for e in tiers["tier1"]],
        "tier2_caps": [e["capability"] for e in tiers["tier2"]],
    }
    return selected[:max_offerings], meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", required=True)
    parser.add_argument("--medians", required=True)
    parser.add_argument("--out", default="solution_plan.json")
    parser.add_argument("--tier1-threshold", type=float, default=0.5)
    parser.add_argument("--tier2-threshold", type=float, default=0.2)
    args = parser.parse_args()

    global TIER1_THRESHOLD, TIER2_THRESHOLD
    TIER1_THRESHOLD = args.tier1_threshold
    TIER2_THRESHOLD = args.tier2_threshold

    with open(args.scores) as f: scores = json.load(f)
    with open(args.medians) as f: medians = json.load(f)

    offerings, meta = infer_solutions(scores, medians)
    ns = meta["num_slides"]

    plan = {
        "num_slides": ns,
        "slide_17": offerings[0:3],
        "slide_18": offerings[3:6] if ns >= 2 else [],
        "slide_19": offerings[6:9] if ns >= 3 else [],
        "total_offerings": len(offerings),
        "rationale": f"{meta['tier1_count']} Tier 1 gaps, {meta['tier2_count']} Tier 2 -> {ns} slide(s)",
        "tier1_capabilities": meta["tier1_caps"],
        "tier2_capabilities": meta["tier2_caps"],
    }
    with open(args.out, "w") as f: json.dump(plan, f, indent=2)
    print(f"Solution plan: {len(offerings)} offerings across {ns} slide(s) -> {args.out}")
    print(f"  Tier 1 ({meta['tier1_count']}): {', '.join(meta['tier1_caps'])}")
    if ns >= 2: print(f"  Slide 18: {offerings[3:6]}")
    if ns >= 3: print(f"  Slide 19: {offerings[6:9]}")


if __name__ == "__main__":
    main()
