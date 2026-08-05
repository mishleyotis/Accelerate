#!/usr/bin/env python3
"""Scan a payload for accusatory framing and unpaired gap statements.

    python scripts/check_language.py payload.json
    python scripts/check_language.py payload.json --strict

A prompt, not a gate: it finds the sentence, you decide. Everything on a client
dashboard is read by, or in front of, the client.
"""
from __future__ import annotations
import argparse, json, re, sys

# Constructions that assign fault or describe a deficiency rather than an opportunity.
ACCUSATORY = [
 (r"\blacks?\b",                    "deficit framing", "name what exists, then what is next"),
 (r"\bfail(?:s|ed|ure)?\s+to\b",    "assigns fault",   "state what happens instead"),
 (r"\bneglect(?:s|ed|ing)?\b",      "assigns fault",   "describe the state, not the omission"),
 (r"\bshould\s+have\b",             "adjudicates the past", "the assessment does not judge past decisions"),
 (r"\bought\s+to\s+have\b",         "adjudicates the past", "same"),
 (r"\binadequate\b",                "deficiency word", "say what it covers, and what it does not yet"),
 (r"\binsufficient\b",              "deficiency word", "say what the ladder found and what would settle it"),
 (r"\bpoor\b",                      "deficiency word", "quantify instead"),
 (r"\bweak(?:ness|nesses)?\b",      "deficiency word", "'thinnest at' reads as position, not judgement"),
 (r"\bdeficien(?:t|cy|cies)\b",     "deficiency word", "reframe as available value"),
 (r"\bimmature\b",                  "deficiency word", "use the maturity band, which is a defined scale"),
 (r"\bbehind\s+(?:the\s+curve|their|its|peers)\b", "comparative judgement", "state the peer position as a delta"),
 (r"\bfalling\s+behind\b",          "comparative judgement", "same"),
 (r"\bno\s+one\s+owns\b",           "accusatory absence", "an owner is the output of one session"),
 (r"\bnobody\s+(?:owns|has|knows)\b", "accusatory absence", "same"),
 (r"\bhas\s+not\s+bothered\b",      "assigns fault",   "remove"),
 (r"\boverlooked\b",                "assigns fault",   "describe the state"),
 (r"\bignor(?:es|ed|ing)\b",        "assigns fault",   "describe the state"),
 (r"\bimmaturity\b",                "deficiency word", "use the band"),
 (r"\bshortcoming\b",               "deficiency word", "reframe"),
 (r"\bcareless\b|\breckless\b|\bsloppy\b", "pejorative", "state the risk, attached to evidence"),
]
# "the team lacks", "staff have not" — capability sits with institutions, not people.
PERSONAL = [
 (r"\bthe\s+team\s+(?:lacks|has\s+not|does\s+not|failed)", "attributes to a team"),
 (r"\bstaff\s+(?:lack|have\s+not|do\s+not|are\s+not)",     "attributes to staff"),
 (r"\bmanagement\s+(?:has\s+failed|neglect|ignored)",       "attributes to individuals"),
 (r"\bthey\s+(?:failed|neglected|ignored)\b",               "attributes to individuals"),
]
# A gap sentence is stronger when something the client already has sits beside it.
ASSET_CUES = [
 # something the client already has
 r"\balready\b", r"\bpurchased\b", r"\bproduction\b", r"\bbuilt\b", r"\bdeployed\b",
 r"\bin place\b", r"\bexists?\b", r"\bavailable\b", r"\bboard.reviewed\b", r"\blicensed\b",
 r"\bresident\b", r"\bowns?\b", r"\bhas\s+(?:built|established|selected)\b",
 # the next step framed as available
 r"\bopportunity\b", r"\bnext step\b", r"\bextend", r"\bactivat", r"\bunlock",
 # CONTRASTIVE REFRAMING — "not X, but Y" is the pairing done rhetorically and is
 # the strongest form of it. Verbatim from a completed assessment:
 #   "not because capability is thin, but because coverage is narrow"
 r"\bnot\s+because\b.{0,80}?\bbut\b", r"\bnot\s+\w+[,]?\s+but\b",
 r"\brather\s+than\b", r"\bis\s+not\s+\w+\s*[;\u2014-]", r"\binstead\s+of\b",
]
GAP_CUES = [r"\bnot yet\b", r"\bno \w+ (?:is|are|has|have)\b", r"\bgap\b", r"\babsent\b",
            r"\bmissing\b", r"\bunused\b", r"\bthin\b", r"\bunmonitored\b", r"\buncounted\b"]

PROSE_KEYS = ("body","rationale","story","story_md","text","framing","synthesis","summary",
              "narrative","narrative_thread","consequence","what","why","so_what",
              "rejected_alternative","pattern_statement","detail","plain_label",
              "mix_implication","strategic_alignment","reason","note")

def walk(n, p=""):
    if isinstance(n, dict):
        for k, v in n.items(): yield from walk(v, f"{p}.{k}" if p else k)
    elif isinstance(n, list):
        for i, v in enumerate(n): yield from walk(v, f"{p}[{i}]")
    else: yield p, n

def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload"); ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    try: payload = json.load(open(a.payload, encoding="utf-8"))
    except Exception as e: print(f"could not read payload: {e}"); return 1

    hits, unpaired, checked = [], [], 0
    for path, val in walk(payload):
        if not isinstance(val, str) or len(val) < 12: continue
        if not any(path.lower().endswith(k) or f".{k}" in path.lower() for k in PROSE_KEYS): continue
        checked += 1
        for sent in sentences(val):
            for pat, kind, fix in ACCUSATORY:
                m = re.search(pat, sent, re.I)
                if m: hits.append((path, m.group(0), kind, fix, sent))
            for pat, kind in PERSONAL:
                m = re.search(pat, sent, re.I)
                if m: hits.append((path, m.group(0), kind, "capability sits with institutions", sent))
            has_gap   = any(re.search(p, sent, re.I) for p in GAP_CUES)
            has_asset = any(re.search(p, sent, re.I) for p in ASSET_CUES)
            if has_gap and not has_asset and len(sent.split()) > 8:
                unpaired.append((path, sent))

    print(f"\n  prose fields checked: {checked}")
    print(f"  accusatory constructions: {len(hits)}")
    print(f"  gap statements with no adjacent asset: {len(unpaired)}\n")

    if hits:
        print("  ACCUSATORY — rewrite these\n")
        for path, tok, kind, fix, sent in hits:
            print(f"    {path}")
            print(f"      \"{tok}\"  · {kind}")
            print(f"      {sent[:150]}{'…' if len(sent) > 150 else ''}")
            print(f"      → {fix}\n")
    if unpaired:
        print("  UNPAIRED GAPS — name what exists before naming what does not\n")
        for path, sent in unpaired[:12]:
            print(f"    {path}\n      {sent[:150]}{'…' if len(sent) > 150 else ''}\n")
        if len(unpaired) > 12: print(f"    … and {len(unpaired) - 12} more\n")
    if not hits and not unpaired:
        print("  clean — reads as opportunity framing throughout.\n")
        print("  Still read the framing line and the top finding aloud. The checker finds")
        print("  constructions; it cannot tell you whether the argument lands.")
    return 1 if hits or (a.strict and unpaired) else 0

if __name__ == "__main__":
    sys.exit(main())
