"""Build the peer/name-matching gold standard (corpus-grounded, free truth).

Every corpus package folder belongs to exactly ONE institution, stated in its
``run_manifest.json`` (``institution_name`` + ``run_id``). That gives free
ground truth for the name-matching fallback in ``scripts/derive_peers`` and
``sheets_client.fuzzy_match_assignee``: given a package's folder/name tokens and
the roster of all institution names, the matcher must resolve to the correct
institution — uniquely, with no false match.

Gold row: {package, folder_tokens_source, institution_name (truth), run_id}.

The benchmark (app/ml/benchmark.py) will, for each row, hide the run_id and ask
the name matcher to pick the institution from the full roster, scoring match
accuracy + false-match rate.

Usage:
  python -m app.ml.gold.build_peer_match_gold \
      --corpus tests/fixtures/dma_packages_batches \
      --out tests/fixtures/ml/peer_match_labels.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _read_manifest(pkg: Path) -> dict:
    for mf in sorted(pkg.glob("**/run_manifest.json")) + sorted(pkg.glob("**/MANIFEST.json")):
        try:
            with mf.open(encoding="utf-8") as fh:
                obj = json.load(fh)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return {}


def _folder_identity(folder_name: str) -> str:
    """Ground-truth institution identity from the folder name: strip the
    trailing ' - DMA' / stray 'DMA' engagement suffix. Always present, so it is
    the authoritative label; the manifest institution_name (when present) is a
    corroborating cross-check, not the primary source."""
    s = re.sub(r"\s*-\s*DMA\s*$", "", folder_name).strip()
    s = re.sub(r"\bDMA\b", "", s).strip()
    return re.sub(r"\s+", " ", s)


def build(corpus: Path) -> list[dict]:
    rows: list[dict] = []
    for batch in sorted(corpus.iterdir()):
        if not batch.is_dir():
            continue
        for pkg in sorted(batch.iterdir()):
            if not pkg.is_dir():
                continue
            m = _read_manifest(pkg)
            manifest_inst = (m.get("institution_name") or m.get("institution") or "").strip()
            run_id = (m.get("run_id") or "").strip()
            truth = _folder_identity(pkg.name)
            # Corroboration: does the manifest name agree with the folder identity?
            agree = bool(manifest_inst) and (
                manifest_inst.lower() in truth.lower() or truth.lower() in manifest_inst.lower()
            )
            rows.append({
                "package": pkg.name,
                "institution_name": truth or None,
                "manifest_institution_name": manifest_inst or None,
                "run_id": run_id or None,
                "grounding": "folder identity (' - DMA' stripped); "
                             + ("manifest corroborates" if agree
                                else "manifest absent/differs — folder is authoritative"),
                "confidence": "high" if truth else "needs_approval",
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", default="tests/fixtures/dma_packages_batches")
    ap.add_argument("--out", default="tests/fixtures/ml/peer_match_labels.jsonl")
    args = ap.parse_args()
    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"ERROR: corpus dir not found: {corpus}", file=sys.stderr)
        return 2
    rows = build(corpus)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_named = sum(1 for r in rows if r["institution_name"])
    n_runid = sum(1 for r in rows if r["run_id"])
    print(f"# peer-match gold: {len(rows)} packages "
          f"({n_named} with institution_name, {n_runid} with run_id, "
          f"{len(rows)-n_named} need manual name)")
    print(f"# wrote {out}")
    for r in rows:
        if not r["institution_name"]:
            print(f"#   MISSING institution_name: {r['package']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
