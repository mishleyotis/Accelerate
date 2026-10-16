#!/usr/bin/env python3
"""Build the versioned golden set from the real corpus (brief §4).

Inputs are the staged `heatmap.evidence` sections of the three reference
runs, read from the live connector (`get_staged_payload`) and saved as JSON
beside this script's invocation — never fetched here, never fabricated.

    python3 eval/build_golden.py --version v1 \
        --tuning golden1=<path> --tuning baxter=<path> --heldout logix=<path> \
        --out eval/golden

Positives: every row with a public URL (the engine re-finds sources; a
client's internal package row has no URL to re-find). Negatives: rows that
fail the card contract today — clause-truncated spans, undated rows that
the engine must label UNVERIFIED rather than guess, connector/scan rows
that are not web evidence — each tagged with the defect class it
exemplifies, so the evaluator can assert the engine emits none of them.

The golden set NAMES real clients. It lives under eval/golden/, which the
no-client-strings test excludes by construction; nothing in
evidence_engine/ reads it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_engine import contract as C  # noqa: E402

_CONNECTOR_HOSTS = ("vibeprospecting.explorium.ai", "explorium.ai")


def fetch_evidence_section(run_id: str) -> dict:
    """The staged `heatmap.evidence` section of a run, whole, through the
    repo's connector client (scripts/dma_connector.py) — inline when it
    fits, reassembled from numbered parts when it does not, exactly as
    scripts/fetch_staged_fixtures.py does."""
    import importlib.util
    repo = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("dma_connector", repo / "scripts" / "dma_connector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    call = mod.call
    head = call("get_staged_payload", run_id=run_id, page="heatmap", section="evidence")
    if "data" in head:
        return head["data"]
    parts = head.get("parts")
    if not parts:
        raise RuntimeError(f"{run_id}: {head.get('error')} — {str(head.get('hint', ''))[:200]}")
    chunks = []
    for i in range(1, parts + 1):
        got = call("get_staged_payload", run_id=run_id, page="heatmap", section="evidence", part=i)
        chunks.append(got["chunk"])
    return json.loads("".join(chunks))


def _rows(path: Path) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    if "data" in d and isinstance(d["data"], dict) and "evidence" in d["data"]:
        d = d["data"]
    return d["evidence"]


def _host(url: str) -> str:
    return C.host_of(url)


def classify(row: dict, client: str) -> dict:
    url = row.get("url") or ""
    ex = row.get("excerpt") or ""
    defects = []
    if not url or not re.match(r"^https?://", url):
        defects.append("no_public_url")
    if any(h in url for h in _CONNECTOR_HOSTS) or "technographic" in (row.get("source_name") or "").lower():
        defects.append("connector_or_scan_row")
    if len(ex) in (80, 100, 120, 140) and ex[-1:].isalnum():
        defects.append("hard_clip")
    if not C.sentence_complete(ex):
        defects.append("not_sentence_complete")
    if len(ex) < C.EXCERPT_MIN or len(ex) > C.EXCERPT_MAX:
        defects.append("length_out_of_contract")
    if ex.lstrip().startswith('"averageUserRating"') or ex.lstrip().startswith("{"):
        defects.append("machine_text")
    if not row.get("published_date"):
        defects.append("undated")
    if re.search(r"\b(P[1-4]C\d(\.\d+)*|Carry-Forward|\(T[1-5], (CURRENT|RECENT|DATED|STALE|ARCHIVAL|UNVERIFIED)\))", ex):
        defects.append("internal_jargon")
    kind = "positive" if not [d for d in defects if d not in ("undated",)] else "negative"
    return {
        "golden_id": "G-" + hashlib.sha256(f"{client}|{row.get('e_id')}".encode()).hexdigest()[:8],
        "client": client,
        "e_id": row.get("e_id"),
        "url": url,
        "host": _host(url),
        "source_name": row.get("source_name"),
        "excerpt": ex,
        "tier": row.get("tier"),
        "claim_type": row.get("claim_type"),
        "published_date": row.get("published_date"),
        "supports_subcap_ids": row.get("supports_subcap_ids") or [],
        "kind": kind,
        "defects": defects,
    }


def build(sets: dict[str, list[tuple[str, Path]]], version: str, out: Path) -> dict:
    manifest = {"version": version, "built": dt.date.today().isoformat(),
                "inputs": {}, "counts": {}}
    out_dir = out / version
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, members in sets.items():
        rows_out = []
        for client, path in members:
            raw = _rows(path)
            manifest["inputs"][client] = {"path": str(path), "rows": len(raw),
                                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            rows_out += [classify(r, client) for r in raw]
        pos = [r for r in rows_out if r["kind"] == "positive"]
        neg = [r for r in rows_out if r["kind"] == "negative"]
        (out_dir / f"{split}_positives.json").write_text(json.dumps(pos, indent=1), encoding="utf-8")
        (out_dir / f"{split}_negatives.json").write_text(json.dumps(neg, indent=1), encoding="utf-8")
        manifest["counts"][split] = {
            "rows": len(rows_out), "positives": len(pos), "negatives": len(neg),
            "distinct_positive_urls": len({r["url"] for r in pos}),
            "defects": dict(Counter(d for r in neg for d in r["defects"])),
            "positive_tiers": dict(Counter(r["tier"] for r in pos)),
        }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", required=True)
    ap.add_argument("--tuning", action="append", default=[], metavar="client=path")
    ap.add_argument("--heldout", action="append", default=[], metavar="client=path")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "golden"))
    ap.add_argument("--fetch", action="append", default=[], metavar="client=run_id",
                    help="read the staged heatmap.evidence of this run through the connector "
                         "into <out>/<version>/raw/<client>.json (needs connector credentials)")
    a = ap.parse_args(argv)
    for spec in a.fetch:
        client, run_id = spec.split("=", 1)
        raw_dir = Path(a.out) / a.version / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        data = fetch_evidence_section(run_id)
        (raw_dir / f"{client}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        print(f"fetched {client}: {len(data.get('evidence', []))} rows -> {raw_dir / (client + '.json')}")
    def parse(items):
        return [(s.split("=", 1)[0], Path(s.split("=", 1)[1])) for s in items]
    m = build({"tuning": parse(a.tuning), "heldout": parse(a.heldout)}, a.version, Path(a.out))
    print(json.dumps(m["counts"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
