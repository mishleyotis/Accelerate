#!/usr/bin/env python3
"""Artefacts the plugin writes that nothing reads.

    audit_dead_contracts.py [--strict] [--json] [--root DIR]

WHY THIS EXISTS. Measured 28-09-2026 (QA audit F-J02-011): six artefacts had
a writer and no reader — a handback file whose docstring said the
re-dispatch reads it, a `context.json` beside every run, a bundle checksum
manifest, the scoring gate's findings file, a canonical-sources registry
named only in prose, and three JSON schemas nothing loaded. A tab with a
writer, a gate and no reader is the most expensive shape there is
(engine/assemble.py, on Entity_Timeline): the work is done, the file is
maintained, and nothing downstream ever benefits. The audit found them by
hand; this check finds them on every push.

WHAT IS A WRITER. A Python line under the plugin that writes a file —
`.write_text(`, `json.dump(`, `open(..., "w")`, `csv.DictWriter(`,
`.to_csv(`, `shutil.copy2(`, `.replace(out)` after a tmp write — whose name
is a literal in the same statement or the six lines above it, directly or
through a module constant (`HANDBACK_DIR = "handbacks"`). The artefact TOKEN
is the literal basename (`scoring.json`) or directory (`handbacks`).

WHAT IS A READER. Any OTHER file that names the token: Python under the
plugin (code reader), Markdown under the plugin (a documented consumer — an
agent told to read it), or Python under apps/worker, apps/api and
packages/shared (the app ingests the package). Tests are not readers: a
test that reads a file proves the writer works, not that the file is used.

`--strict` exits 1 when any artefact has no reader at all. An artefact with
only a documentary reader is reported as DOC-ONLY and does not fail: the
consumer is a person or an agent, which is a real consumer, and the line
that names it is where a future code reader starts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
REPO = PLUGIN.parent.parent

SKIP_PARTS = {"__pycache__", "deprecated", "node_modules", ".git", "tests", "_generated"}
WRITE_RE = re.compile(
    r"\.write_text\(|\.write_bytes\(|json\.dump\(|open\([^)]*[\"'][wa]b?[\"']|"
    r"DictWriter\(|\.to_csv\(|shutil\.copy2?\(|make_archive\(|\.replace\(out\)")
TOKEN_RE = re.compile(
    r"[\"']([\w./ -]*?([\w-]+\.(?:json|jsonl|csv|md|txt|xlsx|docx|sha256|png)))[\"']")
DIR_TOKEN_RE = re.compile(r"[\"'](\d\d_[a-z_]+/[\w-]+|handbacks|approvals)[\"']")
CONST_RE = re.compile(r"^([A-Z][A-Z0-9_]+)\s*=\s*[\"']([^\"']+)[\"']", re.M)
READ_RE = re.compile(
    r"\.read_text\(|\.read_bytes\(|json\.load\(|open\([^)]*[\"']r|DictReader\(|"
    r"load_workbook\(|\.is_file\(|\.exists\(|\.glob\(|read_csv\(")
LOOKBACK = 6
#: Scratch the stress walks leave behind is not a contract: nothing reads it
#: because nothing should.
WRITER_FILE_SKIP = re.compile(r"(^|/)stress_[\w]+\.py$")
#: A retired writer keeps its legacy body for reference behind a refusal
#: (`main()` writes RETIRED and returns 1); the writes below it never run.
RETIRED_MARK = 'RETIRED = """REFUSED'

#: Tokens that look like artefacts and are not: the thing written is not a
#: contract anyone consumes by name, and naming it here says why.
NOT_A_CONTRACT = {
    "requirements.txt": "pip's own file, not a plugin artefact",
    ".sha256": "a suffix, not a file; verify_packet reads the sidecar it names",
}

#: The app's readers of a package live outside the plugin.
APP_READER_ROOTS = ("apps/worker", "apps/api", "packages/shared")

#: Artefacts whose reader takes the path from the environment or a flag, so
#: no reader names the file. Each entry says who reads it and how.
READ_BY_OTHER_MEANS = {
    "cost_baseline.json": "engine.cost.measured_baseline reads the path from "
                          "$DMA_COST_BASELINE (cost.py: `export ... # every "
                          "projection then starts here`)",
    "report_reviews.jsonl": "engine.narrative.latest_reviews reads it through "
                            "_reviews_path(), which joins REVIEWS_FILE — the "
                            "read line names neither, so the read-back scan "
                            "misses it; the writer that feeds the next "
                            "REVISE round its validator's whole note",
}


def _skip(p: Path) -> bool:
    return bool(SKIP_PARTS & set(p.parts))


def writers(root: Path) -> dict[str, list[str]]:
    """token -> [file:line, ...] for every literal artefact a plugin script writes."""
    out: dict[str, list[str]] = {}
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        if _skip(rel) or WRITER_FILE_SKIP.search(str(rel)):
            continue
        text = p.read_text(errors="ignore")
        if RETIRED_MARK in text:
            continue
        consts = dict(CONST_RE.findall(text))
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not WRITE_RE.search(line):
                continue
            window = "\n".join(lines[max(0, i - LOOKBACK):i + 1])
            # substitute the module's own constants so `HANDBACK_DIR` resolves
            for name, val in consts.items():
                if name in window:
                    window += f'\n"{val}"'
            toks = set()
            for whole, base in TOKEN_RE.findall(window):
                if "{" in whole:                 # an f-string path: dynamic
                    continue
                toks.add(base)
            for d in DIR_TOKEN_RE.findall(window):
                toks.add(d.split("/")[-1] if "/" in d else d)
            for t in toks:
                if t in NOT_A_CONTRACT:
                    continue
                out.setdefault(t, []).append(f"{p.relative_to(root)}:{i + 1}")
    return out


def _reads_back(text: str, token: str) -> bool:
    """A writer module that later READS its own artefact (a read line naming
    the token, or the constant that holds it) is that artefact's reader."""
    consts = {name for name, val in CONST_RE.findall(text) if token in val}
    for line in text.splitlines():
        if READ_RE.search(line) and (token in line or any(c in line for c in consts)):
            return True
    return False


def readers(root: Path, token: str, writer_files: set[str]) -> dict[str, list[str]]:
    """Files that name the token, by kind. A writer file counts only when
    it reads the artefact back."""
    found = {"code": [], "doc": [], "app": []}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.suffix not in (".py", ".md", ".json", ".yml", ".yaml") or _skip(rel):
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if token not in text:
            continue
        if str(rel) in writer_files:
            if p.suffix == ".py" and _reads_back(text, token):
                found["code"].append(str(rel) + " (reads back)")
            continue
        found["code" if p.suffix == ".py" else "doc"].append(str(rel))
    repo = root.parent.parent
    for sub in APP_READER_ROOTS:
        base = repo / sub
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            if _skip(p.relative_to(base)):
                continue
            try:
                if token in p.read_text(errors="ignore"):
                    found["app"].append(str(p.relative_to(repo)))
            except OSError:
                continue
    return found


def audit(root: Path | None = None) -> dict:
    root = root or PLUGIN
    w = writers(root)
    rows = []
    for token, sites in sorted(w.items()):
        writer_files = {s.rsplit(":", 1)[0] for s in sites}
        r = readers(root, token, writer_files)
        if token in READ_BY_OTHER_MEANS:
            r["code"].append("(by other means) " + READ_BY_OTHER_MEANS[token])
        status = ("READ" if r["code"] or r["app"] else
                  "DOC-ONLY" if r["doc"] else "ORPHAN")
        rows.append({"artefact": token, "status": status, "writers": sites,
                     "code_readers": r["code"] + r["app"], "doc_readers": r["doc"]})
    return {"root": str(root), "artefacts": rows,
            "orphans": [r["artefact"] for r in rows if r["status"] == "ORPHAN"],
            "doc_only": [r["artefact"] for r in rows if r["status"] == "DOC-ONLY"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=None)
    a = ap.parse_args(argv)
    out = audit(Path(a.root) if a.root else None)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for r in out["artefacts"]:
            if r["status"] == "READ":
                continue
            print(f"{r['status']:8} {r['artefact']}  written at {', '.join(r['writers'][:3])}"
                  + (f"  documented in {', '.join(r['doc_readers'][:2])}" if r["doc_readers"] else ""))
        print(f"audit_dead_contracts: {len(out['artefacts'])} artefact(s) written, "
              f"{len(out['orphans'])} with no reader, {len(out['doc_only'])} documented only")
    return 1 if (a.strict and out["orphans"]) else 0


if __name__ == "__main__":
    sys.exit(main())
