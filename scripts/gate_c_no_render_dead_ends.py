#!/usr/bin/env python3
"""CI Gate C — no render dead ends.

Build owner, 2026-08-14: "Never place an em dash. There should always be a way
to send a signal to the MCP to give us an enrichment of the empty field."

WHY THIS IS A GATE AND NOT A CLEAN-UP. The em dashes were removed once by hand,
across eleven files and fifty-three sites. Hand work does not survive: the next
component someone writes will reach for `: "—"` because it is the shortest thing
that renders, and nothing would notice. A one-time sweep with no gate behind it
is a defect with a delay on it — and the whole point of this product is that the
same class of defect must not reach a second client.

WHAT A DEAD END IS. A rendered fallback that says a value is missing WITHOUT
saying which kind of missing it is. An em dash reads identically whether the
producer searched and found nothing, held a figure that failed the identity
gate, or was never asked — three different facts, and only one is a finding.
It is also terminal: the reader has no route to getting it filled.

THE REPLACEMENT is <EnrichmentGap>, which names the kind and whose gap set the
connector computes (`list_enrichment_gaps`), so a gap a reader sees is already
on the producer's worklist.

WHAT IS ALLOWED, deliberately:
  · an em dash inside a COMMENT — this file's own prose is full of them
  · an em dash as PUNCTUATION inside a rendered sentence — it is a dash, not a
    fallback: "Trails peer median by -0.3 — the gap is in P4"
  · the DETECTOR in live-adapter.jsx that spots an em dash arriving IN DATA
    (`p.name === "—"`). Deleting that would stop the app noticing a dash the
    producer sent, which is the opposite of the intent.
  · prototype/ — the read-only design reference, never edited, never gated.

The check is deliberately narrow — a whole-string em-dash literal in a value
position. A broad "no em dash anywhere" rule would fail on prose and would be
switched off within a week.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / "apps" / "web" / "proto"

# A whole-string em dash: the value position. `"—"`, `'—'`, `{"—"}` and the
# JSX text node `>—<`. Not a dash inside a longer string, which is prose.
DEAD_END = re.compile(r"""(?<![\w"'])(?:"—"|'—')(?![\w"'])|>\s*—\s*<""")

# Sites that are legitimately an em-dash literal. Each entry is
# (file, substring that must appear on the line) and each needs a reason here —
# an allowlist with no reasons becomes a place to hide things.
ALLOWED = [
    # Spots a dash arriving IN DATA from the producer, so the app can treat it
    # as the absent value it is rather than rendering it as a name.
    ("live-adapter.jsx", 'p.name === "—"'),
]


def _allowed(name: str, line: str) -> bool:
    return any(f == name and sub in line for f, sub in ALLOWED)


def _strip_comments(text: str) -> list:
    """Return (lineno, line) for lines that are not inside a block comment and
    are not a line comment. Crude on purpose: it only has to be right about
    whether a DEAD_END match is code, and a false 'this is code' fails loudly
    rather than passing silently."""
    out, in_block = [], False
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if in_block:
            if "*/" in s:
                in_block = False
                s = s.split("*/", 1)[1]
            else:
                continue
        while "/*" in s:
            before, _, rest = s.partition("/*")
            if "*/" in rest:
                s = before + rest.split("*/", 1)[1]
            else:
                s = before
                in_block = True
                break
        if s.startswith("//"):
            continue
        s = re.sub(r"//.*$", "", s)
        if s.strip():
            out.append((i, s))
    return out


def main() -> int:
    if not SCAN.exists():
        print(f"Gate C: {SCAN} does not exist; nothing to scan.")
        return 0
    violations = []
    scanned = 0
    for path in sorted(SCAN.glob("*.jsx")):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in _strip_comments(text):
            if not DEAD_END.search(line):
                continue
            if _allowed(path.name, line):
                continue
            violations.append(
                f"  {path.relative_to(ROOT)}:{lineno}\n      {line[:120]}")
    if violations:
        print("GATE C FAILED — a bare em dash is a render dead end.\n")
        print(f"{len(violations)} site(s) render an em dash where a value is "
              "absent. An em dash cannot say WHICH absence it is, and gives "
              "the reader no route to getting it filled.\n")
        print("\n".join(violations))
        print("\nReplace each with <EnrichmentGap>, which names the kind of "
              "absence and whose gap set the connector computes:\n"
              '    <EnrichmentGap what="Assets" audience={audience} />\n'
              '    <EnrichmentGap what="AUM" held reason={r} audience={audience} />\n'
              '    <EnrichmentGap what="Peer" audience={audience} compact />   '
              "// dense grids\n\n"
              "Where a React element cannot go (a template string, a title "
              "attribute, an array of chart labels), use a plain honest word "
              'for that column — "Not recorded", "Never" — never a dash.\n\n'
              "If a site is genuinely a detector or punctuation, add it to "
              "ALLOWED in this file WITH ITS REASON.")
        return 1
    print(f"Gate C passed: {scanned} modules, no render dead ends.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
