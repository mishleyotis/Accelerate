#!/usr/bin/env python3
"""
headline_scorer.py — Score headlines on the 9-point rubric.

Specificity (3): number, entity, verb. Arguability (2): debatable, not tautology.
Source defensibility (2): traceable, no inventions. Narrative fit (2): advances story,
connects to adjacent. Clarity (1): reads naturally.

Threshold: ≥7 = production-ready. <7 → rewrite. <4 → CRITICAL (likely a label).
"""
import argparse, json, re, sys

def score_headline(text, slide_num, exempt_slides=None):
    if exempt_slides and slide_num in exempt_slides:
        return {"slide": slide_num, "text": text, "score": 9, "status": "EXEMPT", "issues": []}

    issues = []
    words = text.split()
    score = 0

    # Specificity (3 pts)
    has_number = bool(re.search(r'\d', text))
    has_entity = bool(re.search(r'[A-Z][a-z]{2,}', text[1:])) if len(text) > 1 else False
    has_verb = len(words) > 4 and any(w.lower().endswith(('s','ed','ing','es','ize','ate','fy')) for w in words)
    if has_number: score += 1
    else: issues.append("Missing number")
    if has_entity: score += 1
    else: issues.append("Missing entity name")
    if has_verb: score += 1
    else: issues.append("Missing verb or too short")

    # Arguability (2 pts)
    label_patterns = ["overview", "summary", "agenda", "next steps", "key findings",
                      "assessment results", "current state", "heat map", "key strengths",
                      "opportunities", "the assessment", "organizational profile"]
    is_label = any(p in text.lower() for p in label_patterns) and len(words) <= 5
    if not is_label and len(words) >= 8:
        score += 2
    elif not is_label:
        score += 1
        issues.append("Borderline arguability — consider adding a claim")
    else:
        issues.append("Label detected — not an insight headline")

    # Source defensibility (2 pts) — assume good unless flagged externally
    score += 2

    # Narrative fit (1 pt partial — full check needs storyline context)
    if len(words) >= 6:
        score += 1

    # Clarity (1 pt)
    if len(words) <= 25:
        score += 1
    else:
        issues.append(f"Headline too long ({len(words)} words)")

    status = "PASS" if score >= 7 else ("CRITICAL" if score < 4 else "REWRITE")

    # Additional penalties (applied after base scoring)
    # Slide 1: must be narrative blueprint, 65-80 chars
    if slide_num == 1:
        if len(text) < 65:
            score -= 3
            issues.append(f"Slide 1 headline too short ({len(text)} chars, min 65)")
        if ":" in text and text.index(":") < len(text) // 2:
            score -= 3
            issues.append("Slide 1 uses 'Client: stat' colon format — use narrative blueprint")

    # Slide 9: must include score, peer median, and pillar names
    if slide_num == 9:
        if not has_number:
            score -= 5
            issues.append("Slide 9 headline MUST include overall score and peer median")
        generic_patterns = ["stands and what comes next", "where we are", "current state"]
        if any(p in text.lower() for p in generic_patterns):
            score -= 5
            issues.append("Slide 9 headline is generic — must include specific scores and pillars")

    # Slide 16: max 124 chars at 21pt (after mandatory font reduction)
    if slide_num == 16 and len(text) > 124:
        score -= 10
        issues.append(f"Slide 16 headline exceeds 124 chars ({len(text)} chars) — overflow even at 21pt")

    # Any headline with zero numeric values
    if not has_number and slide_num in (1, 6, 9, 14, 16):
        score -= 2
        issues.append("Data-driven headline required — include at least one number")

    status = "PASS" if score >= 7 else ("CRITICAL" if score < 4 else "REWRITE")
    return {"slide": slide_num, "text": text[:80], "score": score, "status": status, "issues": issues}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headlines", required=True, help="JSON: [{slide: N, text: '...'}]")
    parser.add_argument("--exempt", default="2,8,10,11,15,22", help="Comma-separated exempt slides")
    parser.add_argument("--out", help="Output JSON")
    args = parser.parse_args()

    with open(args.headlines) as f: headlines = json.load(f)
    exempt = set(int(x) for x in args.exempt.split(","))

    results = [score_headline(h["text"], h["slide"], exempt) for h in headlines]
    below_threshold = [r for r in results if r["status"] in ("REWRITE", "CRITICAL")]

    report = {"total": len(results), "passing": len(results)-len(below_threshold),
              "failing": len(below_threshold), "results": results}

    if args.out:
        with open(args.out, "w") as f: json.dump(report, f, indent=2)
    
    for r in results:
        icon = "✓" if r["status"] in ("PASS","EXEMPT") else "✗"
        print(f"  {icon} Slide {r['slide']:2d}: {r['score']}/9 [{r['status']}] {r['text'][:60]}")
    
    if below_threshold:
        print(f"\n⚠ {len(below_threshold)} headlines need rewriting before XML editing")
        sys.exit(1)

if __name__ == "__main__":
    main()
