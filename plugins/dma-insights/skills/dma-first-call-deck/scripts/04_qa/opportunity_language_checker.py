#!/usr/bin/env python3
"""
opportunity_language_checker.py — Scan for banned gap/deficit/weakness language.
Suggests opportunity-framed replacements.
Exempt: Slides 5, 7 (read-only industry content).
Context-aware: "gap → outcome" structural references are acceptable.
"""
import argparse, json, re, os, sys, glob

BANNED = {
    "gap": "opportunity",
    "deficit": "room for growth",
    "weakness": "area of focus",
    "weak": "early-stage",
    "fails": "has not yet established",
    "failing": "has not yet established",
    "lacks": "has room to build",
    "lacking": "has room to build",
    "lack of": "opportunity to establish",
    "absence of": "opportunity to establish",
    "immature": "activating",
    "poor": "early-stage",
    "low maturity": "early-stage maturity",
    "falls behind": "positioned to accelerate toward",
    "trails": "positioned to close distance with",
    "lags": "has opportunity to advance toward",
    "underperforms": "has room for acceleration",
    "below benchmark": "highest-value transformation opportunity",
    "below median": "highest-value opportunity area",
    "not yet achievable": "positioned for activation once prerequisites are in place",
    "cannot": "is positioned to",
    "doesn't have": "is ready to invest in",
    "does not have": "is ready to invest in",
    "accumulated without orchestration": "breadth creates a consolidation opportunity",
}

# Regex patterns for negative "no [capability]" framing — CRITICAL severity
NO_CAPABILITY_PATTERNS = [
    r'\bno\s+(MDM|CDM|digital|self-service|unified|CRM|portal|governance)\b',
    r'\bno\s+digital\s+account\s+opening\b',
    r'\bno\s+self-service\s+portal\b',
    r'\bno\s+unified\s+(member|client|customer)\s+view\b',
]

# Internal reference codes — CRITICAL: never on client-facing slides
INTERNAL_CODE_PATTERNS = [
    r'\bISS-\d{3}\b',
    r'\bsubcaps?\b',
]
EXEMPT_SLIDES = {5, 7}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacked-dir", required=True)
    parser.add_argument("--out", help="Output JSON")
    args = parser.parse_args()
    
    findings = []
    for sf in sorted(glob.glob(os.path.join(args.unpacked_dir, "ppt/slides/slide*.xml"))):
        slide_num = int(os.path.basename(sf).replace("slide","").replace(".xml",""))
        if slide_num in EXEMPT_SLIDES:
            continue
        with open(sf) as f: content = f.read()
        texts = " ".join(re.findall(r'<a:t>([^<]+)</a:t>', content)).lower()
        
        for banned, replacement in BANNED.items():
            if banned in texts:
                if banned == "gap" and ("gap →" in texts or ("capability gap" in texts and "outcome" in texts)):
                    continue
                findings.append({"slide": slide_num, "found": banned, "suggested": replacement, "severity": "HIGH"})

        # Check for "no [capability]" patterns — CRITICAL
        for pattern in NO_CAPABILITY_PATTERNS:
            matches = re.findall(pattern, texts, re.IGNORECASE)
            for match in matches:
                findings.append({
                    "slide": slide_num,
                    "found": f"no {match}" if isinstance(match, str) else match,
                    "suggested": "Reframe as investment opportunity (see brand_guidelines.md reframing table)",
                    "severity": "CRITICAL",
                })

        # Check for internal reference codes — CRITICAL
        for pattern in INTERNAL_CODE_PATTERNS:
            matches = re.findall(pattern, texts, re.IGNORECASE)
            for match in matches:
                findings.append({
                    "slide": slide_num,
                    "found": match,
                    "suggested": "REMOVE — internal codes never on client-facing slides",
                    "severity": "CRITICAL",
                })
    
    if args.out:
        with open(args.out, "w") as f: json.dump(findings, f, indent=2)
    
    print(f"Found {len(findings)} banned language instances")
    for f in findings:
        print(f"  Slide {f['slide']}: '{f['found']}' → '{f['suggested']}'")

if __name__ == "__main__":
    main()
