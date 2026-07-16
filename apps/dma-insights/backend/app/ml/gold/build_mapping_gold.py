"""Build the evidence→subcap mapping gold set from analyst-tagged package
evidence.

Ground truth source: the per-pillar ``01_evidence/*.json`` files inside each
DMA package under ``tests/fixtures/dma_packages_batches``. Analyst evidence
items there carry ``facts`` (verbatim extracted claims) and
``subcaps_mapped`` (the subcaps the analyst attributed the item to) — the
labels the Training Specification's Tab 01 §2.2 designates as positives
("every Evidence_IDs cell in shipped scoring workbooks yields positives").

Shapes drift across batches (ADR 0015), so the walker is structural: any
dict at any depth carrying both ``facts``/``fact`` (or an excerpt string)
and ``subcaps_mapped`` (non-empty list) is a labelled row.

Output (one JSON object per line):
    {"entity", "package", "evidence_id", "excerpt", "tier",
     "published": str|None, "subcap_ids": [...], "categories": [...]}

``categories`` is the P#C# prefix set of ``subcap_ids`` — the coarse level
every batch labels consistently; slug-level IDs are kept verbatim for
packages that provide them.

Usage:
    python -m app.ml.gold.build_mapping_gold \
        [--dir tests/fixtures/dma_packages_batches] \
        [--out ../benchmarks/eval/evidence_subcap_labels.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
DEFAULT_DIR = os.path.join(_BACKEND, "tests", "fixtures", "dma_packages_batches")
DEFAULT_OUT = os.path.normpath(os.path.join(
    _BACKEND, "..", "benchmarks", "eval", "evidence_subcap_labels.jsonl"))

_CAT_RE = re.compile(r"^(P\d+C\d+)")


def _category(subcap_id: str) -> str | None:
    m = _CAT_RE.match(str(subcap_id).strip())
    return m.group(1) if m else None


def _excerpt_of(item: dict) -> str | None:
    facts = item.get("facts") or item.get("fact")
    if isinstance(facts, list):
        parts = []
        for f in facts:
            t = str(f.get("text") or "").strip() if isinstance(f, dict) else str(f).strip()
            if t:
                parts.append(t)
        text = " ".join(parts)
    elif isinstance(facts, str):
        text = facts.strip()
    else:
        text = ""
    if not text:
        for k in ("excerpt", "quote", "summary", "text"):
            v = item.get(k)
            if isinstance(v, str) and v.strip():
                text = v.strip()
                break
    return text or None


def _walk(node, found: list[dict]) -> None:
    if isinstance(node, dict):
        subcaps = node.get("subcaps_mapped") or node.get("subcap_mappings")
        if isinstance(subcaps, list) and subcaps:
            excerpt = _excerpt_of(node)
            if excerpt:
                found.append({
                    "evidence_id": node.get("id") or node.get("evidence_id"),
                    "excerpt": excerpt,
                    "tier": node.get("tier"),
                    "ers": node.get("ers_score"),
                    "recency": node.get("recency_tag"),
                    "published": node.get("publish_date") or node.get("published"),
                    "subcap_ids": [str(s).strip() for s in subcaps if str(s).strip()],
                })
        for v in node.values():
            _walk(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk(v, found)


def build(packages_dir: str) -> list[dict]:
    rows: list[dict] = []
    for root, _dirs, files in os.walk(packages_dir):
        if os.path.basename(root) != "01_evidence":
            continue
        package = os.path.basename(os.path.dirname(root))
        entity = package.replace(" - DMA", "").strip()
        for fn in sorted(files):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(root, fn)) as fh:
                    payload = json.load(fh)
            except (json.JSONDecodeError, OSError):
                continue
            found: list[dict] = []
            _walk(payload, found)
            for item in found:
                cats = sorted({c for c in (_category(s) for s in item["subcap_ids"]) if c})
                if not cats:
                    continue
                rows.append({
                    "entity": entity,
                    "package": package,
                    "source_file": fn,
                    **item,
                    "categories": cats,
                })
    # de-duplicate identical (entity, evidence_id, excerpt) rows across
    # updated/deepened file variants — keep the last (most-refined) one.
    seen: dict[tuple, dict] = {}
    for r in rows:
        seen[(r["entity"], r["evidence_id"], r["excerpt"][:200])] = r
    return list(seen.values())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="build evidence→subcap gold labels")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    rows = build(args.dir)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    entities = len({r["entity"] for r in rows})
    slugged = sum(1 for r in rows if any("_" in s for s in r["subcap_ids"]))
    print(f"wrote {len(rows)} labelled rows from {entities} entities "
          f"({slugged} with slug-level subcap ids) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
