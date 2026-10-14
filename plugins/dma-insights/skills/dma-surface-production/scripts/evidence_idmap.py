#!/usr/bin/env python3
"""Register evidence ONCE: the local↔server id map, keyed by content hash.

    evidence_idmap.py register <run_id> <items.json> --map <run>/07_qa/evidence_id_map.json [--dry-run]
    evidence_idmap.py lookup <items.json> --map <map.json>

WHY THIS EXISTS. Measured 28-09-2026 (QA audit F-O11-036): no persisted
map between what a producer registered and the `e_id` the server minted,
so a re-run re-registered the same spans and only the server's
content-hash dedup stopped duplicates — silently, and only per entity. The
map makes the registration idempotent on THIS side: an item whose content
hash is already recorded is not sent, and the recorded `e_id` is what the
producer cites.

The hash is the server's own recipe (`register.py` `_HASH_SQL`):
sha256 of `url | claim_type | lower(left(whitespace-collapsed excerpt, 500))`,
so a lookup here answers exactly the question the server's dedup asks.
`items.json` is a list of `register_evidence` items ({run_id is passed
separately}); the map records {hash: {e_id, deduped, run_id, at,
source_url}}. Nothing here mints an id — the server allocates every one.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def content_hash(source_url, claim_type, excerpt) -> str:
    """The server's dedup key, computed here."""
    span = re.sub(r"\s+", " ", str(excerpt or ""))[:500].lower()
    key = f"{source_url or ''}|{claim_type or ''}|{span}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def item_hash(item: dict) -> str:
    return content_hash(item.get("source_url"), item.get("claim_type"),
                        item.get("excerpt"))


def load_map(path: Path) -> dict:
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            return doc if isinstance(doc, dict) else {}
        except ValueError:
            return {}
    return {}


def save_map(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _mcp():
    spec = importlib.util.spec_from_file_location("ship_page", HERE / "ship_page.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.mcp


def register(run_id: str, items: list[dict], map_path: Path, *, call=None,
             dry_run: bool = False) -> dict:
    """Send only what the map does not already hold; record what came back."""
    call = call or _mcp()
    doc = load_map(map_path)
    out = {"run_id": run_id, "items": len(items), "reused": [], "registered": [],
           "deduped_by_server": [], "errors": [], "map": str(map_path)}
    for item in items:
        h = item_hash(item)
        known = doc.get(h)
        if known and known.get("e_id"):
            out["reused"].append({"hash": h[:12], "e_id": known["e_id"]})
            continue
        if dry_run:
            out["registered"].append({"hash": h[:12], "e_id": None, "dry_run": True})
            continue
        res = call("register_evidence", {"run_id": run_id, "item": item})
        eid = res.get("e_id") if isinstance(res, dict) else None
        if not eid:
            out["errors"].append({"hash": h[:12], "source_url": item.get("source_url"),
                                  "detail": (res.get("errors") or res.get("_error") or res)
                                  if isinstance(res, dict) else res})
            continue
        rec = {"e_id": eid, "deduped": bool(res.get("deduped")), "run_id": run_id,
               "at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source_url": item.get("source_url")}
        doc[h] = rec
        (out["deduped_by_server"] if rec["deduped"] else out["registered"]).append(
            {"hash": h[:12], "e_id": eid})
    if not dry_run:
        save_map(map_path, doc)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register", help="register every item not already in the map")
    r.add_argument("run_id")
    r.add_argument("items", type=Path)
    r.add_argument("--map", required=True, type=Path)
    r.add_argument("--dry-run", action="store_true")
    lk = sub.add_parser("lookup", help="which items the map already holds")
    lk.add_argument("items", type=Path)
    lk.add_argument("--map", required=True, type=Path)
    a = ap.parse_args(argv)
    items = json.loads(a.items.read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("worklist") or []
    if a.cmd == "lookup":
        doc = load_map(a.map)
        rows = [{"hash": item_hash(i)[:12], "e_id": (doc.get(item_hash(i)) or {}).get("e_id"),
                 "source_url": i.get("source_url")} for i in items]
        print(json.dumps({"items": len(rows), "known": sum(1 for x in rows if x["e_id"]),
                          "rows": rows}, indent=2))
        return 0
    out = register(a.run_id, items, a.map, dry_run=a.dry_run)
    print(json.dumps(out, indent=2))
    return 1 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
