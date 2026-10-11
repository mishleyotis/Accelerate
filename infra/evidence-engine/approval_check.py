#!/usr/bin/env python3
"""Does the committed approval allow the evidence-engine deploy to run?

The owner's rule (2026-10-11): the evidence engine's cloud resources are
created only once measured source recall clears 90 percent — tuning AND
held-out, same-URL recall on the golden set. The approval is a committed
file, `infra/evidence-engine/APPROVAL.json`, that names the evaluation run
the number comes from, so a deploy is traceable to a measurement:

    {"approved_by": "...", "date": "YYYY-MM-DD", "golden_version": "v1",
     "results": "apps/evidence-engine/eval/results/<run>.json",
     "recall_url_tuning": 0.92, "recall_url_heldout": 0.91}

Exit 0 and print APPROVED when every condition holds; exit 3 and print the
reason otherwise (CI treats 3 as "not yet", never as a failed release).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPROVAL = HERE / "APPROVAL.json"
THRESHOLD = 0.90
REQUIRED = ("approved_by", "date", "golden_version", "results", "recall_url_tuning", "recall_url_heldout")


def check(path: Path = APPROVAL, threshold: float = THRESHOLD) -> tuple[bool, str]:
    if not path.exists():
        return False, f"no approval: {path.name} is absent (recall has not cleared {threshold:.0%} yet)"
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return False, f"approval unreadable: {e}"
    missing = [k for k in REQUIRED if k not in d]
    if missing:
        return False, f"approval incomplete: missing {missing}"
    try:
        t, h = float(d["recall_url_tuning"]), float(d["recall_url_heldout"])
    except (TypeError, ValueError):
        return False, "approval recall figures are not numbers"
    if t <= threshold or h <= threshold:
        return False, f"approval does not clear {threshold:.0%}: tuning {t:.1%}, held-out {h:.1%}"
    results = (HERE.parents[1] / d["results"]) if not Path(d["results"]).is_absolute() else Path(d["results"])
    if not results.exists():
        return False, f"approval names a results file that is not in the tree: {d['results']}"
    return True, (f"APPROVED by {d['approved_by']} on {d['date']}: golden {d['golden_version']}, "
                  f"recall tuning {t:.1%} / held-out {h:.1%} ({d['results']})")


if __name__ == "__main__":
    ok, why = check(Path(sys.argv[1]) if len(sys.argv) > 1 else APPROVAL)
    print(why)
    sys.exit(0 if ok else 3)
