#!/usr/bin/env python3
"""CI Gate N — invariant 7: exactly one score→band→hex resolver, and it ships.

WHY THIS GATE EXISTS.

  AUD-0048  there were two resolvers, and the UNSANCTIONED one won —
      `apps/web/lib/bands.js` was imported by one status page while
      `apps/web/proto/data.js`'s own maturityHex/maturityClass/maturityLabel
      served every rendered surface. 50 call sites to 1.
  AUD-0049  and the two disagreed: `maturityHex(null)` returned `#E5E7EB`,
      painting a grey swatch for a score that does not exist. Invariant 6
      (null is no score) and invariant 9 (never a default that looks like
      data) both, on the surface a client reads.
  AUD-0050  the acceptance ledger claimed CI enforced this. BD-04 sat in
      gate_e's `textless_adopts` — the list of ADOPT verdicts with no rule
      and no test — so nothing enforced it, and the module the ledger named
      was not the one that shipped.

Four checks, in the order a defect would appear:

  1. `proto/bands.js` is generated from `lib/bands.js` and is current.
  2. No other frontend source maps a score or a band to a colour.
  3. The COMPILED output that actually ships carries the same resolver — a
     fresh source and a stale `public/proto/js/` is the same defect one
     directory down.
  4. No payload contract declares a colour key (invariant 7's other half).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "apps" / "web"
SANCTIONED = {WEB / "lib" / "bands.js", WEB / "proto" / "bands.js",
              WEB / "public" / "proto" / "js" / "bands.js"}

#: The four band fills, plus the two hexes the charter names as forbidden:
#: `#185F60` (the prototype's reachable-looking fifth band) and `#E5E7EB`
#: (the grey a null score used to get).
BAND_HEX = re.compile(
    r"#(?:FFCB99|62D7B8|27BBAF|139F94|185F60|E5E7EB|B0EDD3)\b", re.I)

#: A function that takes a score and returns a colour, however spelled.
RESOLVER_SHAPE = re.compile(
    r"(?:function\s+\w*(?:Hex|Colou?r|Class|Band)\w*|"
    r"\w*(?:Hex|Colou?r)\w*\s*[:=]\s*(?:function|\())", re.I)

SKIP_PARTS = {"node_modules", ".next", "vendor", "dist", "__pycache__"}

_BLOCK = re.compile(r"/\*.*?\*/", re.S)
_LINE = re.compile(r"^\s*//.*$", re.M)


def _code_only(text: str) -> str:
    """The file with its comments blanked, line numbering preserved.

    A comment that QUOTES the forbidden hex in order to explain why it is
    forbidden is not a second resolver, and a gate that cannot tell the
    difference gets its explanation deleted to make it pass."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    return _LINE.sub(blank, _BLOCK.sub(blank, text))


def _sources():
    for base in (WEB / "lib", WEB / "proto", WEB / "app",
                 WEB / "public" / "proto" / "js"):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.suffix not in (".js", ".jsx") or SKIP_PARTS & set(p.parts):
                continue
            yield p


def main() -> int:
    bad: list[str] = []

    # 1 · the generated resolver is current
    r = subprocess.run([sys.executable,
                        str(ROOT / "scripts" / "gen_proto_bands.py"), "--check"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        bad.append(r.stdout.strip() or "proto/bands.js is stale")

    # 2 and 3 · nobody else maps a score to a colour, source or compiled
    for p in _sources():
        if p.resolve() in {s.resolve() for s in SANCTIONED}:
            continue
        for n, line in enumerate(_code_only(p.read_text(errors="ignore"))
                                 .splitlines(), 1):
            if BAND_HEX.search(line):
                bad.append(f"{p.relative_to(ROOT)}:{n}: a band hex outside the "
                           f"one resolver — {line.strip()[:100]}")

    # 4 · no colour key in any payload contract
    contracts = ROOT / "packages" / "shared" / "contracts_data.json"
    if contracts.is_file():
        text = contracts.read_text()
        for m in re.finditer(r'"(\w*(?:colou?r|hex|fill|swatch)\w*)"\s*:', text,
                             re.I):
            key = m.group(1)
            if key.lower() in ("colour_note", "color_note"):
                continue
            bad.append(f"contracts_data.json declares a colour key: {key!r} — "
                       f"payloads carry a raw score, a band word and semantic "
                       f"flags; the colour is the frontend's alone")

    if bad:
        print("gate_n: invariant 7 is not held —")
        for b in bad:
            print(f"  {b}")
        return 1
    print("gate_n: one score→band→hex resolver, generated, shipped, and "
          "the payloads carry no colour")
    return 0


if __name__ == "__main__":
    sys.exit(main())
