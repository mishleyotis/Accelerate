#!/usr/bin/env python3
"""Deep search across ONE client's pulled package corpus.

Owner instruction, 2026-08-20: "if it is not in a workbook, where else can
it be found? How can it do deep client corpus searches?" — this is the
mechanical answer. It extracts text from every synthesis-input file in the
pulled package (workbooks tab by tab, CSVs, reports via their DOCX XML,
manifests, markdown) into a local index, then answers ranked queries with
file + line + snippet. Producers search HERE FIRST — the package usually
already holds the URL, date or excerpt a gap needs — and reach for web
enrichment only when the corpus comes back empty (that refusal is what a
`search_requests` entry is for).

  index  --package DIR            build/refresh DIR/.corpus_index/
  search --package DIR --query "core banking nCino" [--limit 8] [--json]
  search --package DIR --eid E-017            # exact evidence-id mode

Slides are excluded by policy (the corpus rule); PDFs are indexed only when
a text extractor is importable — canonical packages carry a DOCX twin of
every report, which indexes fully. Skipped files are named in the manifest,
never silently dropped.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from package_map import SLIDES_RE  # noqa: E402

INDEX_DIR = ".corpus_index"
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t]+")
TEXT_EXT = {".csv", ".md", ".txt", ".json", ".jsonl", ".log"}


def _docx_text(path: Path) -> str:
    out = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith("word/") and name.endswith(".xml") \
                    and ("document" in name or "header" in name
                         or "footer" in name):
                xml = z.read(name).decode("utf-8", errors="replace")
                xml = xml.replace("</w:p>", "\n")
                out.append(WS_RE.sub(" ", TAG_RE.sub(" ", xml)))
    return "\n".join(out)


def _xlsx_text(path: Path) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    out = []
    try:
        for ws in wb.worksheets:
            out.append(f"## tab: {ws.title}")
            for row in ws.iter_rows(max_row=3000, values_only=True):
                cells = [str(c) for c in row if c not in (None, "")]
                if cells:
                    out.append(" | ".join(cells))
    finally:
        wb.close()
    return "\n".join(out)


def _pdf_text(path: Path) -> str | None:
    try:
        import pypdf                                   # noqa: PLC0415
    except ImportError:
        return None
    try:
        return "\n".join((pg.extract_text() or "")
                         for pg in pypdf.PdfReader(str(path)).pages)
    except Exception:                                  # noqa: BLE001
        return None


def _extract(path: Path) -> str | None:
    low = path.name.lower()
    ext = path.suffix.lower()
    if SLIDES_RE.search(str(path).lower()):
        return None                                    # policy exclusion
    if ext in TEXT_EXT:
        raw = path.read_bytes()
        if ext == ".csv":
            try:
                rows = list(csv.reader(io.StringIO(
                    raw.decode("utf-8-sig", errors="replace"))))
                return "\n".join(" | ".join(r) for r in rows)
            except Exception:                          # noqa: BLE001
                pass
        return raw.decode("utf-8", errors="replace")
    if ext in (".xlsx", ".xlsm"):
        try:
            return _xlsx_text(path)
        except Exception as e:                         # noqa: BLE001
            return f"[unreadable workbook: {e}]"
    if ext == ".docx":
        try:
            return _docx_text(path)
        except Exception as e:                         # noqa: BLE001
            return f"[unreadable docx: {e}]"
    if ext == ".pdf":
        return _pdf_text(path)
    if low == ".ds_store" or ext in (".png", ".jpg", ".jpeg", ".gif",
                                     ".zip", ".pptx", ".ppt"):
        return None
    try:
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def build_index(package: Path) -> dict:
    idx = package / INDEX_DIR
    idx.mkdir(exist_ok=True)
    manifest = {"indexed": [], "skipped": []}
    for p in sorted(package.rglob("*")):
        if not p.is_file() or INDEX_DIR in p.parts:
            continue
        rel = str(p.relative_to(package))
        text = _extract(p)
        if text is None:
            manifest["skipped"].append(
                {"path": rel,
                 "reason": ("slides excluded by the corpus rule"
                            if SLIDES_RE.search(rel.lower())
                            else "no extractor for this type")})
            continue
        out = idx / (rel.replace("/", "__") + ".txt")
        out.write_text(text, encoding="utf-8")
        manifest["indexed"].append({"path": rel, "chars": len(text)})
    (idx / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def search(package: Path, query: str, limit: int = 8,
           exact: bool = False) -> list:
    idx = package / INDEX_DIR
    if not (idx / "manifest.json").is_file():
        build_index(package)
    if exact:
        pattern = re.compile(re.escape(query), re.I)
        terms = [query.lower()]
    else:
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 1]
        pattern = re.compile("|".join(re.escape(t) for t in terms), re.I)
    hits = []
    for f in idx.glob("*.txt"):
        text = f.read_text(encoding="utf-8", errors="replace")
        low = text.lower()
        score = sum(low.count(t) for t in terms)
        if not score:
            continue
        lines = []
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                snippet = line.strip()
                if len(snippet) > 240:
                    m = pattern.search(snippet)
                    s = max(0, (m.start() if m else 0) - 100)
                    snippet = "…" + snippet[s:s + 220] + "…"
                lines.append({"line": i, "snippet": snippet})
                if len(lines) >= 3:
                    break
        hits.append({"file": f.name[:-4].replace("__", "/"),
                     "score": score, "matches": lines})
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_i = sub.add_parser("index")
    p_i.add_argument("--package", required=True)
    p_s = sub.add_parser("search")
    p_s.add_argument("--package", required=True)
    p_s.add_argument("--query")
    p_s.add_argument("--eid")
    p_s.add_argument("--limit", type=int, default=8)
    p_s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    package = Path(a.package)
    if not package.is_dir():
        print(f"not a directory: {package}", file=sys.stderr)
        return 2
    if a.cmd == "index":
        m = build_index(package)
        print(f"indexed {len(m['indexed'])} files, "
              f"skipped {len(m['skipped'])} "
              f"({sum(1 for s in m['skipped'] if 'slides' in s['reason'])} "
              f"by the slides rule)")
        return 0
    q = a.eid or a.query
    if not q:
        ap.error("search needs --query or --eid")
    hits = search(package, q, a.limit, exact=bool(a.eid))
    if a.json:
        print(json.dumps(hits, indent=1))
    else:
        if not hits:
            print(f"no corpus hits for {q!r} — the corpus cannot answer "
                  f"this; a search_requests entry (web) is the next rung")
        for h in hits:
            print(f"{h['score']:5d}  {h['file']}")
            for m in h["matches"]:
                print(f"        L{m['line']}: {m['snippet'][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
