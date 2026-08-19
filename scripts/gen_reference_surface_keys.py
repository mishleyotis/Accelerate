#!/usr/bin/env python3
"""Extract the reference clients' observed surface keys, per section.

The contract's item grammar (`item_keys`) is deliberately narrow — it parses
one "Per item:" lead-in per field doc, which for a section like
platform.platform_story yields the GAPS row schema and not the card schema.
An allowlist generated from it alone would strip fit_basis, readiness and
story fields that both promoted reference clients legitimately serve. The
brief's rule is the repair: the customer allowlist derives from the
REFERENCE surface set — what Baxter (the positive pattern) and Logix (the
worked test client) actually promoted — unioned with the contract.

This script reads staged page payloads (JSON files, one per page, as saved
by get_staged_payload) and emits fixtures/reference_surface_keys.json:
{"page.section": {"keys": [...], "items": {field: [item keys]}}}, with the
excluded serve classes already removed. The output is COMMITTED and
reviewed; regeneration requires the payload snapshots, so the committed file
is the record of the reference surface at the time it was cut.

Usage: python scripts/gen_reference_surface_keys.py <dir-with-<client>_<page>.json ...>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("overview", "heatmap", "insights", "platform", "context", "techstack")
CLASSES = json.loads(
    (ROOT / "packages" / "shared" / "serve_classes.json").read_text())
EXCLUDED = frozenset(
    k for cls in ("probe_keys", "method_keys", "cap_keys")
    for k in CLASSES[cls]["keys"])


def scan(acc: dict, page: str, sections: dict) -> None:
    for name, body in sections.items():
        if not isinstance(body, dict):
            continue
        slot = acc.setdefault(f"{page}.{name}", {"keys": set(), "items": {}})
        for key, val in body.items():
            if key in EXCLUDED:
                continue
            slot["keys"].add(key)
            if isinstance(val, list):
                item_keys = slot["items"].setdefault(key, set())
                for row in val:
                    if isinstance(row, dict):
                        item_keys.update(
                            k for k in row if k not in EXCLUDED)


def main(argv) -> int:
    dirs = [Path(a) for a in argv[1:]]
    if not dirs:
        print("usage: gen_reference_surface_keys.py <payload-dir> [...]",
              file=sys.stderr)
        return 2
    acc: dict = {}
    files = 0
    for d in dirs:
        for f in sorted(d.glob("*.json")):
            page = next((p for p in PAGES
                         if f.stem == p or f.stem.endswith(f"_{p}")), None)
            if page is None:
                continue
            data = json.loads(f.read_text())
            # accept either {section: body} directly or a {data|sections} wrap
            sections = data.get("sections") if isinstance(
                data.get("sections"), dict) else data
            if not isinstance(sections, dict):
                continue
            scan(acc, page, sections)
            files += 1
    out = {
        "_doc": "Observed surface keys of the promoted reference clients "
                "(Baxter c1351d25, Logix d7ed1d90), minus the excluded "
                "serve classes. Input to scripts/gen_customer_allowlist.py; "
                "GENERATED — regenerate from payload snapshots, never edit.",
        "sections": {
            k: {"keys": sorted(v["keys"]),
                "items": {f: sorted(ks) for f, ks in sorted(v["items"].items())
                          if ks}}
            for k, v in sorted(acc.items())},
    }
    target = ROOT / "fixtures" / "reference_surface_keys.json"
    target.write_text(json.dumps(out, indent=1) + "\n")
    print(f"reference_surface_keys.json: {len(out['sections'])} sections "
          f"from {files} page files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
