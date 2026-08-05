#!/usr/bin/env python3
"""Score a synthesis prompt against the fourteen-attribute standard.

    python scripts/score_prompt.py my_prompt.txt
    cat prompt.txt | python scripts/score_prompt.py -

Under 10/14, or under 1,500 characters for a non-trivial surface, treat it as
unfinished. See 04-craft/5-prompt-standard.md for what each attribute means.
"""
import re, sys

ATTRS = [
 ("steps",       r"STEP \d", "Numbered steps — retrieval first, derivation only on failure"),
 ("out_shape",   r"\{[a-z_]+,|Emit\b|Return\b|Produce\b", "Every field named in one brace block"),
 ("word_budget", r"\b\d{1,3}\s*[\u2013\u2014-]\s*\d{1,3}\s*words?\b|at most \d+ words", "Per-field word budgets"),
 ("gates",       r"\bGATES?\b", "What will be asserted at submit"),
 ("empty_state", r"empty[_ ]state|verified_absent|verified_sparse|cannot|if none|if no ", "What to emit when the evidence is absent"),
 ("forbidden",   r"NEVER|MUST NOT|never |do not ", "Explicit prohibitions"),
 ("identity",    r"identity|contamina|legal name|THIS client|THIS entity", "The identity gate"),
 ("grain",       r"grain|same row|same cell|0\.05", "Grain lock"),
 ("citation",    r"e_id|E-ID|cite|citation", "Citation discipline"),
 ("register",    r"register|vocabulary|tone|jargon|out loud|say it aloud", "Register rules"),
 ("measured",    r"\b\d{2,4} (?:of |clients|cards|cells|violations)|measured|exemplar", "A measured exemplar"),
 ("provenance",  r"provenance|derived|analyst|source_kind", "Provenance marking"),
 ("audience",    r"internal_only|internal only|customer|redact", "Audience marking"),
 ("ordering",    r"order|rank|sequence|chronolog", "Ordering, where order carries meaning"),
]

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    got = [(n, bool(re.search(p, text, re.I)), why) for n, p, why in ATTRS]
    score = sum(1 for _, ok, _ in got if ok)
    n = len(text)

    print(f"\n  {n:,} characters   score {score}/{len(ATTRS)}\n")
    for name, ok, why in got:
        print(f"  [{'ok' if ok else '  '}] {name:12s} {'' if ok else why}")

    print()
    if score >= 12 and n >= 1500:
        print("  Solid. Check the exemplars are measured rather than abstract.")
    elif score >= 10:
        print("  Usable. Close the gaps above before shipping the surface.")
    else:
        print("  Unfinished. Below 10/14 an agent has to guess, and a guess that")
        print("  type-checks promotes silently wrong content.")
    if n < 800:
        print("  Under 800 characters — every prompt this short in the source set")
        print("  failed at least seven attributes.")
    missing = [x for x, ok, _ in got if not ok]
    if {"identity", "grain", "register", "audience"} & set(missing):
        print("\n  Note: identity, grain, register and audience are STANDING clauses.")
        print("  If they are absent because the prompt relies on standing-clauses.md,")
        print("  that is correct — say so in the prompt so the next reader knows.")
    return 0 if score >= 10 else 1

if __name__ == "__main__":
    sys.exit(main())
