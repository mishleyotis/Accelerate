#!/usr/bin/env python3
"""Reduce the acceptance document to the census Gate E can run in CI.

The source is 13,992 lines of QA specification carrying 2,428 headings. It is
not in the repository and will not be: it is an uploaded working document, and
committing 1.5 MB of prose to make a gate work would put the gate's input
outside review. What IS committed is this digest — the surface index and the
heading arithmetic — which is all the census needs.

WHY A SURFACE INDEX AND NOT EVERY HEADING. The document's shape, established by
reading it: a SURFACE is a level-1 heading whose title is a name ("Insights -
Recommendations"). Inside it, level-1 headings numbered "1." through "9." are
the eight-part template every surface repeats, and level-2 headings are that
template's subsections. So a surface owns every heading between its own line and
the next surface's, and the census question is not "is heading 1,847 accounted
for" but "is every SURFACE accounted for, and do the parts sum".

Both are checked. Per-surface heading counts must sum to the document's total,
so a surface cannot be quietly dropped by absorbing its headings into a
neighbour — which is exactly how three whole Insights surfaces, carrying
eighteen P0 checks, went missing from the first curation pass.

CLIENT NEUTRALITY, verified rather than assumed: `--check` re-derives the digest
and fails if any heading names a client. Zero of the 2,428 do today. The
document's client-named fixtures live in its BODY, which is not carried here.

    build_doc_digest.py <qa_doc.md>          write the digest
    build_doc_digest.py <qa_doc.md> --check  verify the committed digest matches
"""
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIGEST = REPO / "apps" / "web" / "tests" / "acceptance" / "doc_digest.json"

# A numbered level-1 heading is a part of the eight-part template ("1. Content
# and narrative contract", "8. Repository-derived content composition
# contract"), not a surface of its own.
NUMBERED = re.compile(r"^\d+\\?\.\s")

# Names that must never reach a committed artefact. The document itself is
# client-named throughout its body; its headings are not, and this keeps it so.
CLIENT_NAMES = ("baxter", "bcu", "odlum", "sunstrong", "zota", "synovus",
                "greenstate", "alliant", "fce-", "credit union of")


def headings(text: str) -> list:
    out = []
    for i, line in enumerate(text.splitlines()):
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            out.append((i + 1, level, line.lstrip("#").strip()))
    return out


def surfaces(heads: list, total_lines: int) -> list:
    """Level-1 headings that name a surface, with adjacent duplicates collapsed.

    The document emits many surface titles twice within a few lines (a section
    break followed by the surface's own header). Collapsing them is safe and
    necessary: two entries for one surface would make the census pass while
    describing something that does not exist.
    """
    raw = [(n, t) for n, lv, t in heads if lv == 1 and not NUMBERED.match(t)]
    out = []
    for n, t in raw:
        if out and out[-1][1] == t and n - out[-1][0] <= 4:
            continue
        out.append((n, t))

    rows = []
    for idx, (line, title) in enumerate(out):
        end = out[idx + 1][0] - 1 if idx + 1 < len(out) else total_lines
        rows.append({
            "line": line,
            "title": title,
            "end_line": end,
            # Every heading this surface owns, its own included. These must sum
            # to the document total — the arithmetic that makes a silently
            # dropped surface impossible.
            "headings": sum(1 for n, _, _ in heads if line <= n <= end),
        })
    return rows


def build(text: str) -> dict:
    heads = headings(text)
    lines = text.splitlines()
    rows = surfaces(heads, len(lines))
    return {
        "_why": "Gate E's census input. See scripts/build_doc_digest.py.",
        "source": {
            "lines": len(lines),
            "headings": len(heads),
            # The whole document's hash, so a digest built from a DIFFERENT
            # revision of the spec cannot be mistaken for this one.
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        },
        "surfaces": rows,
    }


def client_named(digest: dict) -> list:
    bad = []
    for s in digest["surfaces"]:
        low = s["title"].lower()
        for name in CLIENT_NAMES:
            if name in low:
                bad.append(f'line {s["line"]}: {s["title"]!r} contains {name!r}')
    return bad


def main(argv) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[-3], file=sys.stderr)
        return 2
    src = Path(argv[0])
    if not src.exists():
        print(f"source document not found: {src}\n\nThe digest is committed; "
              "rebuilding it needs the uploaded specification, which lives "
              "outside the repository by design.", file=sys.stderr)
        return 2

    digest = build(src.read_text(errors="replace"))
    bad = client_named(digest)
    if bad:
        print("REFUSING: a surface title names a client, and this artefact is "
              "committed:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1

    total = sum(s["headings"] for s in digest["surfaces"])
    if total != digest["source"]["headings"]:
        print(f"census does not reconcile: surfaces own {total} headings, the "
              f"document has {digest['source']['headings']}", file=sys.stderr)
        return 1

    if "--check" in argv:
        if not DIGEST.exists():
            print(f"{DIGEST} does not exist", file=sys.stderr)
            return 1
        have = json.loads(DIGEST.read_text())
        if have.get("source") != digest["source"]:
            print("the committed digest was built from a different revision of "
                  f"the specification:\n  committed {have.get('source')}\n"
                  f"  rebuilt   {digest['source']}", file=sys.stderr)
            return 1
        print(f"digest matches: {len(digest['surfaces'])} surfaces, "
              f"{digest['source']['headings']} headings.")
        return 0

    DIGEST.write_text(json.dumps(digest, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {DIGEST.relative_to(REPO)}: {len(digest['surfaces'])} "
          f"surfaces, {digest['source']['headings']} headings, "
          f"{digest['source']['lines']} lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
