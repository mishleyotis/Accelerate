#!/usr/bin/env python3
"""Repack an unpacked OOXML directory into a .pptx.

    python3 scripts/00_util/pack_pptx.py unpacked/ working/deck.pptx

The skill used to call `/mnt/skills/public/pptx/scripts/office/pack.py`.
That path is not the plugin's to own — it belongs to a separately installed
public skill, it is absolute, and on the machine this was packaged on it does
not exist, so the one documented repack step in the deck workflow was a
dangling reference. `template_preparer.py` already carried a zipfile fallback
for the unpack half; this is the pack half, bundled rather than borrowed.

Two details that matter for PowerPoint:

  * `[Content_Types].xml` is written first. Readers that stream the archive
    look for it at the front.
  * It is stored, not deflated, which is what the OPC writers PowerPoint
    itself produces do. Everything else is deflated.

Directory entries are omitted — an OPC package addresses parts by name and a
stray directory entry makes some validators complain.
"""
from __future__ import annotations

import os
import sys
import zipfile

CONTENT_TYPES = "[Content_Types].xml"


def pack(src: str, dest: str) -> int:
    if not os.path.isdir(src):
        print(f"not a directory: {src}", file=sys.stderr)
        return 2
    ct = os.path.join(src, CONTENT_TYPES)
    if not os.path.exists(ct):
        print(f"{src} has no {CONTENT_TYPES} — is it an unpacked OOXML package?",
              file=sys.stderr)
        return 2

    parts: list[str] = []
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(root, f), src).replace(os.sep, "/")
            if rel != CONTENT_TYPES:
                parts.append(rel)

    parent = os.path.dirname(os.path.abspath(dest))
    if parent:
        os.makedirs(parent, exist_ok=True)

    with zipfile.ZipFile(dest, "w") as z:
        z.write(ct, CONTENT_TYPES, compress_type=zipfile.ZIP_STORED)
        for rel in parts:
            z.write(os.path.join(src, rel), rel,
                    compress_type=zipfile.ZIP_DEFLATED)

    print(f"{dest}  ({len(parts) + 1} parts, "
          f"{os.path.getsize(dest) / 1024:.0f} KiB)")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    if any(a in ("-h", "--help") for a in argv[1:]) or len(args) != 2:
        print(__doc__)
        print("usage: pack_pptx.py <unpacked-dir> <out.pptx>")
        return 0 if any(a in ("-h", "--help") for a in argv[1:]) else 2
    return pack(args[0], args[1])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
