#!/usr/bin/env python3
"""
word_economy_checker.py — Flag wordy phrases and suggest concise alternatives.
"""
import argparse, json, re, os, sys, glob

WORDY = {
    "in order to": "to",
    "at this point in time": "now",
    "due to the fact that": "because",
    "a large number of": "[specific number]",
    "leverage synergies": "[specific action]",
    "going forward": "[remove]",
    "it is important to note that": "[remove]",
    "in terms of": "[rephrase]",
    "with respect to": "about",
    "in the event that": "if",
    "at the end of the day": "[remove]",
    "on a go-forward basis": "[remove]",
    "in close proximity to": "near",
    "a significant number of": "[specific number]",
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpacked-dir", required=True)
    parser.add_argument("--out", help="Output JSON")
    args = parser.parse_args()

    findings = []
    for sf in sorted(glob.glob(os.path.join(args.unpacked_dir, "ppt/slides/slide*.xml"))):
        slide_num = int(os.path.basename(sf).replace("slide","").replace(".xml",""))
        with open(sf) as f: content = f.read()
        texts = " ".join(re.findall(r'<a:t>([^<]+)</a:t>', content)).lower()
        for wordy, concise in WORDY.items():
            if wordy in texts:
                findings.append({"slide": slide_num, "found": wordy, "suggested": concise})

    if args.out:
        with open(args.out, "w") as f: json.dump(findings, f, indent=2)
    print(f"Found {len(findings)} wordy phrases")
    for f in findings: print(f"  Slide {f['slide']}: '{f['found']}' → '{f['suggested']}'")

if __name__ == "__main__":
    main()
