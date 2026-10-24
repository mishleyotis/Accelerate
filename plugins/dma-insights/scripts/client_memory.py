#!/usr/bin/env python3
"""Per-client memory: the synthesis record that outlives the session.

Owner instruction, 2026-08-20: "Ensure the routines have memory … research
outputs, and DMA package synthesis, do not get lost. It can record outputs
to a separate client.md file during sessions; this md file may be maintained
over time. Different md files for each clients rather than 1 md file for
all. MD file should have similar sections as the agent surfaces."

Why a file, and why per client. A fired session's disk does not survive
container reclaim (measured 2026-08-19), so anything a routine learns —
which searches came back empty, which evidence resolved to which subcap,
why a surface was written the way it was — dies with the container unless
it is written somewhere first. One file per client keeps one client's
record from ever being pasted into another's context; the file's sections
MIRROR the served surfaces (fixtures/served_sections.json, the same census
test_surface_coverage.py enforces owners for), so a producer resuming work
on overview.why_now knows exactly where the last session left its notes.

Where it lives. During a session: $DMA_CLIENT_MEMORY_DIR (default
/root/.dma/clients)/<client-slug>.md. Durably: uploaded to the CLIENT'S OWN
folder in the intake tree via the Google Drive connector at every
checkpoint — the discipline, including what may never be written into the
file, is 05-lifecycle/client-memory.md. It is NEVER committed to this
repository: the repository is public and the file is client work product.

Format contract, kept deliberately dumb so any session can parse it with a
regex and none can corrupt it structurally: '## ' opens a fixed section,
entries under a section are '- YYYY-MM-DD · run <id8> · <text>', newest
first. No hashtag numbering anywhere (owner, 2026-08-20).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
CENSUS = PLUGIN / "fixtures" / "served_sections.json"
DEFAULT_DIR = os.environ.get("DMA_CLIENT_MEMORY_DIR", "/root/.dma/clients")

# Sections beyond the surface mirror: the working memory the owner named.
WORKING_SECTIONS = [
    ("research log", "enrichment searches run, per facet — query, date, what "
                     "came back, INCLUDING empty results (a negative search "
                     "re-run is a session wasted)"),
    ("package synthesis", "what the DMA package itself established — workbook "
                          "shape, scored cells, sub-vertical scope, register "
                          "counts, quarantines"),
    ("thin subcap resolution", "cells flagged is_thin_evidence and what was "
                               "done about each: the ladder run, evidence "
                               "registered, or why it honestly stays thin"),
    ("evidence matching corrections", "evidence-to-subcap assignments a "
                                      "session corrected, so the matcher's "
                                      "feedback ledger and the next session "
                                      "start from the corrected state"),
    ("open questions", "handoffs to the next session — what is unresolved "
                       "and what would resolve it"),
]

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")

#: The cap, stated (QA audit F-G05-017): a memory file is read whole at
#: every session start, so it is budgeted like a prompt. Past 80% the
#: `note` output says so; at the cap it refuses until the file is pruned.
CAP_BYTES = 49_152
CONSOLIDATE_AT = 0.80


def version_of(text_body: str) -> str:
    """The version token: the content's own digest. A writer that read
    version X and asks to write on top of version X is writing on what it
    read; anything else is a lost update waiting to happen."""
    import hashlib
    return hashlib.sha256(text_body.encode("utf-8")).hexdigest()[:16]


def _file_lock(path: Path):
    """The engine's one file lock, shared with the workbook and the
    research notebooks — never a second implementation."""
    root = PLUGIN / "skills" / "dma-research"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from engine.workbook import file_lock                          # noqa: PLC0415
    return file_lock(path.with_name(path.name + ".lock"), why=f"client memory {path.name}")


def size_of(path: Path) -> dict:
    n = path.stat().st_size if path.exists() else 0
    return {"bytes": n, "cap": CAP_BYTES, "pct": round(100.0 * n / CAP_BYTES, 1),
            "consolidate_due": n >= CAP_BYTES * CONSOLIDATE_AT, "over_cap": n >= CAP_BYTES}


def write_note(path: Path, section: str, note: str, run: str | None, *,
               expect_version: str | None = None, client: str | None = None) -> dict:
    """The read-modify-write, under the lock, checked against the version
    the caller read. Returns the new version and the size report."""
    with _file_lock(path):
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(skeleton(client or path.stem), encoding="utf-8")
        body = path.read_text(encoding="utf-8")
        have = version_of(body)
        if expect_version and expect_version != have:
            raise SystemExit(
                f"memory version mismatch: you read {expect_version}, the file is "
                f"now {have} — another session wrote it. Re-read it (client_memory.py "
                f"version --client …), merge your note into what is there, and write "
                f"again with the current version. (QA audit F-G05-017)")
        size = size_of(path)
        if size["over_cap"]:
            raise SystemExit(
                f"{path.name} is {size['bytes']:,} bytes against a cap of {CAP_BYTES:,}: "
                f"prune resolved entries before noting more — a memory a session "
                f"cannot afford to read at start is a memory nobody reads.")
        new = add_note(body, section, note, run)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(new, encoding="utf-8")
        tmp.replace(path)
        return {"version": version_of(new), "previous": have, **size_of(path)}


def census_sections() -> list:
    d = json.loads(CENSUS.read_text())
    out = []
    for page in sorted(d["pages"]):
        for name in d["pages"][page]:
            out.append(f"{page}.{name}")
    return out


def memory_path(client: str, root: str | None = None) -> Path:
    if not _SLUG_RE.match(client):
        raise SystemExit(f"client slug {client!r} must be kebab-case "
                         f"(the serving display_id is the right value)")
    return Path(root or DEFAULT_DIR) / f"{client}.md"


def skeleton(client: str, title: str | None = None) -> str:
    today = _dt.date.today().isoformat()
    lines = [
        f"# {title or client} — synthesis memory",
        "",
        f"Client slug: {client} · created {today} · maintained by DMA "
        f"Insights sessions.",
        "One file per client. Sections mirror the served surfaces so notes "
        "land where the next producer will look. Entries are dated, newest "
        "first, and are appended — never rewritten. This file must never "
        "hold a credential, a token, or another client's data.",
        "",
        "## how to use this file",
        "- load it at session start (Google Drive, this client's folder); "
        "write back after each page and at session end",
        "- one entry per fact learned: '- YYYY-MM-DD · run <id8> · <text>'",
        "- supersede by adding the newer entry above the old one, never by "
        "deleting — the history is the memory",
        "",
    ]
    for section in census_sections():
        lines += [f"## {section}", "", "_no entries yet_", ""]
    for name, doc in WORKING_SECTIONS:
        lines += [f"## {name}", "", f"_{doc}_", ""]
    return "\n".join(lines)


def add_note(text_body: str, section: str, note: str, run: str | None) -> str:
    """Insert a dated entry at the TOP of the section's entry list."""
    header = f"## {section}"
    if f"\n{header}\n" not in f"\n{text_body}" and not text_body.startswith(header):
        raise SystemExit(
            f"no section {section!r} in this memory file — sections mirror "
            f"the served surfaces plus the working set; regenerate the "
            f"skeleton if the census has changed")
    stamp = _dt.date.today().isoformat()
    run8 = f" · run {run[:8]}" if run else ""
    entry = f"- {stamp}{run8} · {note.strip()}"
    lines = text_body.splitlines()
    out, i = [], 0
    while i < len(lines):
        out.append(lines[i])
        if lines[i].strip() == header:
            # skip the blank line after the header, drop a placeholder,
            # then the new entry goes first
            i += 1
            if i < len(lines) and not lines[i].strip():
                out.append(lines[i]); i += 1
            if i < len(lines) and lines[i].strip().startswith("_"):
                i += 1                      # the "_no entries yet_" line
            out.append(entry)
            continue
        i += 1
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="create the skeleton if absent")
    p_init.add_argument("--client", required=True)
    p_init.add_argument("--title")
    p_init.add_argument("--dir")
    p_note = sub.add_parser("note", help="append a dated entry to a section")
    p_note.add_argument("--client", required=True)
    p_note.add_argument("--section", required=True,
                        help="a served surface (page.section) or a working "
                             "section name")
    p_note.add_argument("--run", help="run id, stamped as its first 8 chars")
    p_note.add_argument("--text", required=True)
    p_note.add_argument("--dir")
    p_note.add_argument("--expect-version", default=None,
                        help="the version token you read (client_memory.py version); "
                             "the write is refused if the file has moved on")
    p_path = sub.add_parser("path", help="print the memory file path")
    p_path.add_argument("--client", required=True)
    p_path.add_argument("--dir")
    p_ver = sub.add_parser("version", help="print the file's version token and size")
    p_ver.add_argument("--client", required=True)
    p_ver.add_argument("--dir")
    a = ap.parse_args(argv)

    path = memory_path(a.client, getattr(a, "dir", None))
    if a.cmd == "path":
        print(path)
        return 0
    if a.cmd == "version":
        body = path.read_text(encoding="utf-8") if path.exists() else ""
        print(json.dumps({"path": str(path), "version": version_of(body) if body else None,
                          **size_of(path)}))
        return 0
    if a.cmd == "init":
        if path.exists():
            print(f"exists: {path}")
            return 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(skeleton(a.client, a.title), encoding="utf-8")
        print(f"created: {path}")
        return 0
    if a.cmd == "note":
        out = write_note(path, a.section, a.text, a.run,
                         expect_version=a.expect_version, client=a.client)
        print(f"noted under {a.section}: {path} · version {out['version']} · "
              f"{out['bytes']:,} bytes ({out['pct']}% of cap)"
              + (" · CONSOLIDATE DUE — prune resolved entries" if out["consolidate_due"] else ""))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
