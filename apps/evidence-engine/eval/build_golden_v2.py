#!/usr/bin/env python3
"""Golden v2: the same rows as a golden v1 build, each asked with the
SUBCAP'S OWN DIAGNOSTIC QUESTION from the pillar scoring toolkits instead
of a question derived from the excerpt's vocabulary (owner, 2026-10-11:
"are you checking the connectors against the subcap requirements and
diagnostic questions?").

    python3 eval/build_golden_v2.py --from v1 --toolkits <dir with Pillar*_Scoring_Toolkit.xlsx> \
        --sheet CU [--out eval/golden/v2]

The toolkits are Drive-sourced and are NOT committed; the rows (gitignored
like v1's) carry `question`, `subcap_id` and `subcap_name`. A row with no
subcap that has a toolkit question is dropped and counted in the manifest.
The manifest records the toolkit files' sha256 so a run names its inputs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "eval" / "golden"
PLUGIN_RESEARCH = ROOT.parents[1] / "plugins" / "dma-insights" / "skills" / "dma-research"


def load_questions(toolkit_dir: Path, sheet: str) -> dict[str, dict]:
    sys.path.insert(0, str(PLUGIN_RESEARCH))
    from engine import kg  # the plugin's own loader; one reading of the toolkits
    cells, notes = kg.load_toolkits(str(toolkit_dir), sheet)
    if notes:
        print("toolkit notes:", *notes, sep="\n  ", file=sys.stderr)
    return cells


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="src", default="v1")
    ap.add_argument("--toolkits", required=True)
    ap.add_argument("--sheet", default="CU", help="kg.TOOLKIT_SHEETS code of the clients' sub-vertical")
    ap.add_argument("--out", default=str(GOLDEN / "v2"))
    a = ap.parse_args(argv)
    src = GOLDEN / a.src
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    questions = load_questions(Path(a.toolkits), a.sheet)
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    counts = {}
    for split in ("tuning", "heldout"):
        rows = json.loads((src / f"{split}_positives.json").read_text(encoding="utf-8"))
        kept, dropped = [], 0
        for r in rows:
            hit = next(((s, questions[s]) for s in (r.get("supports_subcap_ids") or []) if s in questions), None)
            if hit is None:
                dropped += 1
                continue
            sid, cell = hit
            r2 = dict(r)
            r2["question"] = cell["question"]
            r2["subcap_id"] = sid
            r2["subcap_name"] = cell.get("name")
            r2["question_source"] = f"toolkit:{cell.get('sheet')}"
            kept.append(r2)
        (out / f"{split}_positives.json").write_text(json.dumps(kept, indent=1, ensure_ascii=False), encoding="utf-8")
        shutil.copy(src / f"{split}_negatives.json", out / f"{split}_negatives.json")
        counts[split] = {"positives": len(kept), "dropped_no_toolkit_question": dropped,
                         "distinct_positive_urls": len({r["url"] for r in kept}),
                         "distinct_subcaps": len({r["subcap_id"] for r in kept})}
    tk = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(a.toolkits).glob("Pillar*_Scoring_Toolkit.xlsx"))}
    manifest.update({"version": out.name, "built": dt.date.today().isoformat(), "derived_from": a.src,
                     "question_source": {"toolkits": tk, "sheet_code": a.sheet,
                                         "rule": "the first supports_subcap_id with a toolkit question; its diagnostic question verbatim"},
                     "counts_v2": counts})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(counts, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
