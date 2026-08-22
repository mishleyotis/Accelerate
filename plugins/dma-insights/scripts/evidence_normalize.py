#!/usr/bin/env python3
"""Merge every evidence store in a package into schema-fit records.

Owner instruction, 2026-08-20: the pipeline must "retrieve the evidence
URLs, or even enrich where required to fit the required schema formats".
The corpus survey measured why: evidence lives in up to ten stores per
package (workbook register tabs, CSVs under three different folders,
JSON/JSONL ledgers), no CSV in the corpus carries a 50-char excerpt, one
generation has no URL column at all, another has URLs but no dates.

This module makes the package answer for itself before anything reaches
the web:

  1. MERGE — every store package_map names, keyed by evidence id; fields
     unified through a header-synonym map; same id + conflicting values is
     a CONFLICT row (adjudicated, never averaged).
  2. CORPUS FILL — a record missing url/date/excerpt searches the client's
     OWN corpus first (corpus_search): a fill found there is package data
     with provenance, not enrichment.
  3. GAPS OUT — whatever the corpus cannot answer becomes a ready
     `search_requests` entry for the top session's connectors. A row is
     never registered bare, never dropped silently; undated stays
     UNVERIFIED until a date is actually found.

Usage:
  evidence_normalize.py --package DIR [--client SLUG] [--out normalized.jsonl]

Output: one JSON record per evidence id; gaps + conflicts to stdout.
Cross-client ledger form of every id: <client>:<eid>.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus_search  # noqa: E402
import package_map  # noqa: E402

EID_RE = re.compile(r"^(E[-_][A-Z0-9]+[-_]?\d*)(:F\d+)?$", re.I)
URL_IN_TEXT = re.compile(r"https?://[^\s\"'|<>\)\]]+", re.I)
DATE_IN_TEXT = re.compile(r"\b(20[12]\d[-/]\d{1,2}[-/]\d{1,2}|"
                          r"\d{1,2}/\d{1,2}/20[12]\d)\b")

SYN = {
    "eid": ("evidence_id", "evidence id", "e_id", "id"),
    "source": ("source_name", "source_title", "source", "publisher",
               "kb_source_id", "title"),
    "url": ("url", "link", "source_url"),
    # ordered best-first: a publication-flavoured column outranks a bare
    # "date", which in fact-level rows carries EVENT dates (E-083's 1979
    # is a timeline fact, not when its source was published — measured)
    "date": ("date_published", "publish_date", "publication_date",
             "published_date", "as_of_date", "date"),
    "excerpt": ("evidence_excerpt", "excerpt", "quote", "key_extract",
                "text", "claim", "passage"),
    "tier": ("tier",),
    "ers": ("ers_total", "ers_score", "ers", "ers_core"),
    "subcaps": ("subcaps_supported", "subcaps", "subcap_id",
                "categories_referenced", "pillars_mapped"),
}


def _pick(row: dict, field: str):
    for rank, k in enumerate(SYN[field]):
        v = row.get(k)
        if v not in (None, ""):
            return str(v).strip(), rank
    return None, None


def _rows_from_csv(path: Path):
    try:
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        rd = csv.DictReader(io.StringIO(text))
        for r in rd:
            yield {(k or "").strip().lower(): (v or "") for k, v in r.items()}
    except Exception as e:                                  # noqa: BLE001
        print(f"unreadable csv {path.name}: {e}", file=sys.stderr)


def _rows_from_json(path: Path):
    try:
        raw = path.read_bytes().decode("utf-8", errors="replace")
        if path.suffix == ".jsonl":
            items = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
        else:
            data = json.loads(raw)
            items = (data if isinstance(data, list) else
                     next((v for v in data.values()
                           if isinstance(v, list) and v
                           and isinstance(v[0], dict)), []))
        for it in items:
            if isinstance(it, dict):
                yield {str(k).lower(): ("" if v is None else v)
                       for k, v in it.items()}
    except Exception as e:                                  # noqa: BLE001
        print(f"unreadable json {path.name}: {e}", file=sys.stderr)


def _rows_from_xlsx(path: Path):
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as e:                                  # noqa: BLE001
        print(f"unreadable workbook {path.name}: {e}", file=sys.stderr)
        return
    try:
        for ws in wb.worksheets:
            if "evidence" not in ws.title.lower():
                continue
            rows = ws.iter_rows(max_row=3000, values_only=True)
            hdr = None
            for r in rows:
                cells = ["" if c is None else str(c).strip() for c in r]
                if hdr is None:
                    if sum(1 for c in cells if c) >= 3:
                        hdr = [c.lower() for c in cells]
                    continue
                if any(cells):
                    yield dict(zip(hdr, cells))
    finally:
        wb.close()


def _base_eid(value: str) -> str | None:
    m = EID_RE.match(value.strip())
    return m.group(1).upper() if m else None


def merge(package: Path) -> tuple[dict, list]:
    pm = package_map.map_package(package)
    stores = list(pm["evidence_tables"])
    if pm["research"]["primary"]:
        stores.append(str(Path(pm["research"]["primary"]).relative_to(package)))
    if pm["scoring"]["primary"]:
        stores.append(str(Path(pm["scoring"]["primary"]).relative_to(package)))
    records: dict[str, dict] = {}
    conflicts: list[dict] = []
    for rel in stores:
        path = package / rel
        if path.suffix in (".csv",):
            rows = _rows_from_csv(path)
        elif path.suffix in (".json", ".jsonl"):
            rows = _rows_from_json(path)
        elif path.suffix in (".xlsx", ".xlsm"):
            rows = _rows_from_xlsx(path)
        else:
            continue
        for row in rows:
            raw_id, _ = _pick(row, "eid")
            if not raw_id:
                raw_id = next((v for v in row.values()
                               if isinstance(v, str) and _base_eid(v)), None)
            if not raw_id:
                continue
            eid = _base_eid(str(raw_id))
            if not eid:
                continue
            rec = records.setdefault(eid, {"eid": eid, "provenance": []})
            rec["provenance"].append(rel)
            for field in ("source", "url", "date", "excerpt", "tier",
                          "ers", "subcaps"):
                v, rank = _pick(row, field)
                if v is None:
                    continue
                if field == "excerpt" and len(v) < 50:
                    continue                    # below the floor — not one
                old = rec.get(field)
                if old is None:
                    rec[field] = v
                    rec.setdefault("_rank", {})[field] = rank
                    rec.setdefault("_store", {})[field] = rel
                    continue
                if field == "url" and old.rstrip("/") != v.rstrip("/"):
                    conflicts.append({"eid": eid, "field": "url",
                                      "values": [old, v], "store": rel})
                elif field == "date" and old != v:
                    old_rank = rec.get("_rank", {}).get("date", 99)
                    if rank < old_rank:
                        rec["date"] = v          # better column wins quietly
                        rec["_rank"]["date"] = rank
                        rec["_store"]["date"] = rel
                    elif (rank == old_rank
                          and rec.get("_store", {}).get("date") != rel):
                        conflicts.append({"eid": eid, "field": "date",
                                          "values": [old, v], "store": rel})
    return records, conflicts


def corpus_fill(package: Path, records: dict) -> int:
    filled = 0
    for eid, rec in records.items():
        missing = [f for f in ("url", "date", "excerpt")
                   if not rec.get(f)]
        if not missing:
            continue
        hits = corpus_search.search(package, eid, limit=4, exact=True)
        for h in hits:
            for m in h["matches"]:
                line = m["snippet"]
                if "url" in missing and not rec.get("url"):
                    u = URL_IN_TEXT.search(line)
                    if u:
                        rec["url"] = u.group(0)
                        rec.setdefault("fills", []).append(
                            {"field": "url", "from": h["file"],
                             "line": m["line"]})
                        missing.remove("url")
                        filled += 1
                if "date" in missing and not rec.get("date"):
                    d = DATE_IN_TEXT.search(line)
                    if d:
                        rec["date"] = d.group(0)
                        rec.setdefault("fills", []).append(
                            {"field": "date", "from": h["file"],
                             "line": m["line"]})
                        missing.remove("date")
                        filled += 1
                if "excerpt" in missing and not rec.get("excerpt"):
                    text = line.strip("… ").strip()
                    if len(text) >= 50 and eid.lower() in line.lower():
                        rec["excerpt"] = text[:500]
                        rec.setdefault("fills", []).append(
                            {"field": "excerpt", "from": h["file"],
                             "line": m["line"]})
                        missing.remove("excerpt")
                        filled += 1
            if not missing:
                break
    return filled


DATE_IN_NAME = re.compile(
    r"(20\d{2})[-_.]?(0[1-9]|1[0-2])(?:[-_.]?(0[1-9]|[12]\d|3[01]))?")
ISO_DATE = re.compile(r"20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])")


def collection_date(package: Path) -> tuple:
    """(iso_date, basis) — the package's own latest date stamp, or (None,
    reason). WHY (owner, 2026-08-20: 'for most evidence, recency is tagged
    unverified — improve this'): most ingested rows carry no publication
    date, but every row in an assessment package was OBSERVED no later than
    the package's own stamp, and 'observed as of the assessment date' is a
    real, defensible date with explicit provenance — strictly more honest
    than UNVERIFIED for a fact the assessors verified when they wrote it.
    File mtimes are NEVER used (a Drive pull stamps download time); only
    dates the package itself states: file/folder names first, then the
    heads of export CSVs and JSON stores. A publication date still outranks
    it — gaps_out keeps emitting dating search_requests for these rows."""
    hits = []
    for f in package.rglob("*"):
        if f.is_dir():
            continue
        m = DATE_IN_NAME.search(f.name)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3) or "01"
            hits.append((f"{y}-{mo}-{d}", f"file name {f.name!r}"))
        if f.suffix.lower() in (".csv", ".json", ".jsonl"):
            try:
                head = f.open(errors="ignore").read(2048)
            except OSError:
                continue
            for iso in ISO_DATE.findall(head):
                hits.append((iso, f"head of {f.name!r}"))
    from datetime import date as _date
    today = _date.today().isoformat()
    hits = [h for h in hits if h[0] <= today]     # never a future stamp
    if not hits:
        return None, ("no date stamp in package file names or store heads — "
                      "rows without dates stay UNVERIFIED")
    best = max(hits)
    return best[0], f"latest package stamp: {best[1]}"


def apply_collection_date(records: dict, cdate: str, basis: str) -> int:
    """Date the still-dateless rows at collection, provenance explicit."""
    n = 0
    for rec in records.values():
        if not rec.get("date"):
            rec["date"] = cdate
            rec["date_provenance"] = "collection"
            rec["date_basis"] = basis
            n += 1
    return n


def gaps_out(records: dict, client: str | None) -> list:
    out = []
    for eid, rec in sorted(records.items()):
        missing = [f for f in ("url", "date", "excerpt")
                   if not rec.get(f)]
        if not rec.get("date"):
            rec["recency"] = "UNVERIFIED"
        elif rec.get("date_provenance") == "collection":
            missing = sorted(set(missing) | {"publication_date"})
        if not missing:
            continue
        src = rec.get("source") or ""
        q = " ".join(x for x in (client or "", src,
                                 (rec.get("excerpt") or "")[:60]) if x)
        note = ("dated at collection ({}) — a publication date outranks it; "
                "connector search upgrades the row".format(
                    rec.get("date_basis", "package stamp"))
                if rec.get("date_provenance") == "collection" else
                "corpus exhausted — web retrieval through the session's "
                "connectors; undated stays UNVERIFIED until a real date lands")
        out.append({"eid": (f"{client}:{eid}" if client else eid),
                    "missing": missing,
                    "query": q.strip() or eid,
                    "note": note})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--package", required=True)
    ap.add_argument("--client", default=None,
                    help="client slug — prefixes ids in the gaps output")
    ap.add_argument("--out", default=None,
                    help="write normalized records as JSONL here")
    ap.add_argument("--assessment-date", default=None,
                    help="ISO date the package was collected; overrides "
                         "auto-derivation from the package's own stamps")
    a = ap.parse_args(argv)
    package = Path(a.package)
    if not package.is_dir():
        print(f"not a directory: {package}", file=sys.stderr)
        return 2
    records, conflicts = merge(package)
    filled = corpus_fill(package, records)
    if a.assessment_date:
        cdate, basis = a.assessment_date, "owner-supplied --assessment-date"
    else:
        cdate, basis = collection_date(package)
    dated_at_collection = (
        apply_collection_date(records, cdate, basis) if cdate else 0)
    gaps = gaps_out(records, a.client)
    if a.out:
        with open(a.out, "w") as fh:
            for eid in sorted(records):
                rec = {k: v for k, v in records[eid].items()
                       if not k.startswith("_")}
                fh.write(json.dumps(rec) + "\n")
    full = sum(1 for r in records.values()
               if r.get("url") and r.get("date") and r.get("excerpt"))
    print(json.dumps({
        "records": len(records), "schema_complete": full,
        "corpus_fills": filled,
        "collection_date": cdate, "collection_basis": basis,
        "dated_at_collection": dated_at_collection,
        "conflicts": conflicts[:20],
        "conflict_count": len(conflicts),
        "gaps": gaps[:25], "gap_count": len(gaps)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
