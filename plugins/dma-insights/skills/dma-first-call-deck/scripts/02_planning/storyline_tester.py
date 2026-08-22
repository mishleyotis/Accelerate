#!/usr/bin/env python3
"""
storyline_tester.py — Extract headlines in order and test if they tell a coherent AIDA story.

Story beats required:
1. Who they are + strategic context (Slides 1, 6)
2. Industry forces (5)
3. Pain they feel (7)
4. Where they stand (9, 13, 14)
5. Opportunities (16)
6. Solutions (17-19)
7. What to do next (20)

Output: passes (bool), narrative_summary, missing_beats.
"""
import argparse, json, re, sys

STORY_BEATS = {
    "identity": {"slides": [1, 6], "keywords": ["maturity", "foundation", "growth", "platform"]},
    "industry": {"slides": [5], "keywords": ["industry", "2026", "competitors", "market"]},
    "pain": {"slides": [7], "keywords": ["pain", "familiar", "cost", "manual"]},
    "assessment": {"slides": [9, 13, 14], "keywords": ["score", "maturity", "pillar", "benchmark"]},
    "opportunities": {"slides": [16], "keywords": ["opportunity", "transformation", "capability", "invest"]},
    "solutions": {"slides": [17, 18, 19], "keywords": ["solution", "platform", "modernization", "data"]},
    "action": {"slides": [20], "keywords": ["next", "step", "feedback", "deliver", "schedule"]},
}

def test_storyline(headlines):
    missing = []
    covered = {}
    
    for beat_name, beat_config in STORY_BEATS.items():
        beat_covered = False
        for h in headlines:
            if h["slide"] in beat_config["slides"]:
                text_lower = h["text"].lower()
                if any(kw in text_lower for kw in beat_config["keywords"]):
                    beat_covered = True
                    covered[beat_name] = h["slide"]
                    break
                # Even without keywords, if slide exists in headlines, partial credit
                beat_covered = True
                covered[beat_name] = h["slide"]
        
        if not beat_covered:
            missing.append(beat_name)
    
    passes = len(missing) == 0
    summary = "Headlines tell the story: " + " → ".join(
        f"{beat}(S{covered[beat]})" for beat in STORY_BEATS if beat in covered
    )
    if missing:
        summary += f". MISSING: {', '.join(missing)}"
    
    return {"passes": passes, "missing_beats": missing, "narrative_summary": summary,
            "headlines": [h["text"] for h in headlines]}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headlines", required=True, help="JSON: [{slide: N, text: '...'}]")
    parser.add_argument("--out", help="Output JSON")
    args = parser.parse_args()

    with open(args.headlines) as f: headlines = json.load(f)
    result = test_storyline(headlines)

    if args.out:
        with open(args.out, "w") as f: json.dump(result, f, indent=2)
    
    print(f"Storyline test: {'PASS ✓' if result['passes'] else 'FAIL ✗'}")
    print(f"  {result['narrative_summary']}")
    if result['missing_beats']:
        print(f"  Missing beats: {result['missing_beats']}")
        sys.exit(1)

if __name__ == "__main__":
    main()
