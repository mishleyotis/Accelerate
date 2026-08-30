#!/usr/bin/env python3
"""Gate F — a key the contract declares has a reader in the frontend.

The defect class, three times measured and once per layer:

    the enrichment register declared five surfaces and one had a renderer
    `context_sentiment.context_tiles` validated at submit and was dropped at
      promotion
    `platform_story` served sixteen keys per platform and the page read two

The last one is why this exists. Finding it took a hand-written census against
a live payload: dump every leaf key the API serves, grep the frontend for each
name, subtract. Nineteen keys — `fit_score`, `estate_reach`, `peer_synthesis`,
the readiness detail, both pathways — appeared in no frontend file at all. The
producer had run the searches, argued against itself and cited the results, and
a reader saw a name and a paragraph.

Nothing was broken in a way any test could see. The payload was correct, the
promote was correct, the suite was green, and the content was invisible.

WHY THE CONTRACT AND NOT A PAYLOAD. A payload census needs a promoted run, and
CI has none — `fixtures/served` does not exist, so the audit job that would
carry this skips. The contract is committed, is the authority on what a
producer may emit (Surface Specification: "payload shapes are law; never invent
a field"), and states item keys in its `doc` text, which is the only place they
are stated. So the census runs against the contract and needs no run at all.

WHY A RATCHET RATHER THAN ZERO. Plenty of declared keys legitimately have no
frontend reader: envelope and provenance keys the API consumes, internal_only
paths the walker strips, fields a surface has not been built for yet. Demanding
zero would be a lie that gets suppressed. So the count is pinned to what is
actually there — the same discipline as `gate_b_ceiling_ratchet.py` — and the
list may SHRINK and never GROW. A new declared key with no reader fails; fixing
one is a baseline update in the same commit.

Usage:
    gate_f_declared_keys_have_readers.py            # check against the baseline
    gate_f_declared_keys_have_readers.py --update   # re-pin after wiring readers
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "packages" / "shared" / "contracts_data.json"
BASELINE = REPO / "packages" / "shared" / "unread_keys_baseline.json"
FRONTEND = REPO / "apps" / "web" / "proto"

# Keys the frontend never reads BY DESIGN, so listing them as debt would be
# noise rather than a worklist. These are the transport envelope and the
# provenance the API consumes on the reader's behalf.
STRUCTURAL = {
    "doc", "type", "item_type", "required", "surface_id", "fields", "_notes",
    "data", "data_source", "provenance", "produced_at", "producer_version",
    "internal_only", "empty_state",
}

_PER_ITEM = re.compile(r"Per [a-z ]+?:\s*\{([^}]*)\}")
_FIELD_BRACE = re.compile(r"\b([a-z_][a-z0-9_]*)\[\]\s*\{([^}]*)\}")
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*\[?\]?$")


def declared_keys(contract: dict) -> dict:
    """{key -> [where it is declared]}, from field names AND the item shapes
    stated in `doc` text. The doc text is read with the same expressions the
    validator's AG-03 uses: a shape neither can see is enforced by neither."""
    out: dict = {}

    def note(key, where):
        out.setdefault(key, []).append(where)

    for page, psec in contract.items():
        if not isinstance(psec, dict):
            continue
        for section, ssec in psec.items():
            if not isinstance(ssec, dict):
                continue
            for fname, spec in (ssec.get("fields") or {}).items():
                note(fname, f"{page}.{section}.{fname}")
                doc = (spec or {}).get("doc") or ""
                groups = [m.group(1) for m in _PER_ITEM.finditer(doc)]
                groups += [m.group(2) for m in _FIELD_BRACE.finditer(doc)]
                for g in groups:
                    for raw in g.split(","):
                        k = raw.strip().rstrip("[]")
                        if _IDENT.match(k):
                            note(k, f"{page}.{section}.{fname}[].{k}")
    return out


def frontend_source() -> str:
    parts = []
    for p in sorted(FRONTEND.rglob("*")):
        if p.suffix in (".jsx", ".js") and p.is_file():
            parts.append(p.read_text(errors="replace"))
    return "\n".join(parts)


def unread(contract: dict) -> dict:
    """Declared keys whose NAME appears nowhere in the frontend source.

    Name-level, deliberately. A path-level check would be stronger and is not
    reachable from a contract alone — the frontend reads through an adapter
    that renames — so this catches the total absence and says so plainly. A key
    read for one section and ignored in another still passes here; that is the
    known ceiling, recorded rather than papered over.
    """
    src = frontend_source()
    out = {}
    for key, wheres in declared_keys(contract).items():
        if key in STRUCTURAL:
            continue
        if not re.search(rf"\b{re.escape(key)}\b", src):
            out[key] = sorted(set(wheres))
    return out


def main(argv) -> int:
    contract = json.loads(CONTRACT.read_text())
    found = unread(contract)

    if "--update" in argv:
        BASELINE.write_text(json.dumps(
            {"_why": "Gate F: contract keys with no frontend reader. May "
                     "SHRINK, never GROW. Pinned to the measured set, never "
                     "to a round number.",
             "keys": {k: v for k, v in sorted(found.items())}},
            indent=1) + "\n")
        print(f"Gate F baseline re-pinned at {len(found)} unread key(s).")
        return 0

    if not BASELINE.exists():
        print("Gate F: no baseline. Run with --update once, and read the list "
              "before committing it — every entry is a contract field no "
              "reader will ever see.", file=sys.stderr)
        return 1

    base = set(json.loads(BASELINE.read_text())["keys"])
    new = sorted(set(found) - base)
    fixed = sorted(base - set(found))

    if new:
        print(f"Gate F FAILED: {len(new)} declared key(s) gained no reader.",
              file=sys.stderr)
        for k in new:
            print(f"  {k}", file=sys.stderr)
            for w in found[k][:3]:
                print(f"      declared at {w}", file=sys.stderr)
        print("\nA contract field with no read path is validated at submit, "
              "written at promotion and seen by nobody. Wire a reader, or "
              "re-pin with --update in the same commit and say why.",
              file=sys.stderr)
        return 1

    msg = f"Gate F passed: {len(found)} unread key(s), baseline {len(base)}."
    if fixed:
        msg += (f" {len(fixed)} now read ({', '.join(fixed[:6])}"
                f"{'…' if len(fixed) > 6 else ''}) — re-pin with --update.")
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
