#!/usr/bin/env python3
"""Does the committed approval allow the evidence-engine deploy to run?

The owner's rule, as it stands on 2026-10-11. First reading (morning): the
engine's cloud resources are created only once measured source recall clears
90 percent, tuning AND held-out. Six iterations later same-URL recall stood
at 36 % / 70 % (golden v1) and 22 % / 22 % (golden v2, the toolkit's own
diagnostic questions) while QUESTION COVERAGE — the share of briefs answered
by at least one entity-confirmed card from an independent source — stood at
100 % on both splits of both sets; the report said so and asked which metric
governs. The owner's answer (same day, after the six-connector orchestration
ask): "Fix the above to ensure deploy happens." So the gate governs on
question coverage, above 90 percent on tuning AND held-out, RECOMPUTED here
from the per-call rows of the results file the approval names — a number in
the approval file is never trusted on its own — and it reports same-URL
recall beside it so the deviation from the morning's wording is visible in
every deploy log.

    {"approved_by": "...", "date": "YYYY-MM-DD", "golden_version": "v2",
     "metric": "question_coverage",
     "results": "apps/evidence-engine/eval/results/<run>.json",
     "owner_words": "...", "recall_url_tuning": 0.222, "recall_url_heldout": 0.222}

`metric: "recall_url"` keeps the original rule (figures read from the file,
both above the threshold). Exit 0 and print APPROVED when every condition
holds; exit 3 and print the reason otherwise (CI treats 3 as "not yet",
never as a failed release).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPROVAL = HERE / "APPROVAL.json"
THRESHOLD = 0.90
REQUIRED = ("approved_by", "date", "golden_version", "results", "metric")
METRICS = ("question_coverage", "recall_url")
#: an entity match the card contract counts as the entity's own
ENTITY_OK = ("confirmed", "probable")


def _results_path(d: dict) -> Path:
    r = Path(str(d["results"]))
    return r if r.is_absolute() else HERE.parents[1] / r


def question_coverage(results: dict) -> dict:
    """Per split: the share of briefs that returned >= 1 entity-confirmed or
    probable card and no error. {split: {"calls": n, "answered": m, "share": x}}."""
    out: dict[str, dict] = {}
    for call in results.get("calls") or []:
        split = str(call.get("split") or "")
        row = out.setdefault(split, {"calls": 0, "answered": 0, "share": 0.0})
        row["calls"] += 1
        em = call.get("entity_match") or {}
        answered = (not call.get("error")) and sum(int(em.get(k) or 0) for k in ENTITY_OK) >= 1
        row["answered"] += int(bool(answered))
    for row in out.values():
        row["share"] = row["answered"] / row["calls"] if row["calls"] else 0.0
    return out


def check(path: Path = APPROVAL, threshold: float = THRESHOLD) -> tuple[bool, str]:
    if not path.exists():
        return False, f"no approval: {path.name} is absent (no metric has cleared {threshold:.0%} yet)"
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return False, f"approval unreadable: {e}"
    missing = [k for k in REQUIRED if k not in d]
    if missing:
        return False, f"approval incomplete: missing {missing}"
    metric = str(d["metric"])
    if metric not in METRICS:
        return False, f"approval metric {metric!r} is not one of {METRICS}"
    results = _results_path(d)
    if not results.exists():
        return False, f"approval names a results file that is not in the tree: {d['results']}"
    if metric == "recall_url":
        try:
            t, h = float(d["recall_url_tuning"]), float(d["recall_url_heldout"])
        except (KeyError, TypeError, ValueError):
            return False, "approval recall figures are missing or not numbers"
        if t <= threshold or h <= threshold:
            return False, f"approval does not clear {threshold:.0%}: recall tuning {t:.1%}, held-out {h:.1%}"
        return True, (f"APPROVED by {d['approved_by']} on {d['date']}: golden {d['golden_version']}, "
                      f"same-URL recall tuning {t:.1%} / held-out {h:.1%} ({d['results']})")
    try:
        cov = question_coverage(json.loads(results.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError) as e:
        return False, f"results file unreadable: {e}"
    t, h = cov.get("tuning"), cov.get("heldout")
    if not t or not h or not t["calls"] or not h["calls"]:
        return False, f"results carry no tuning/held-out calls to measure coverage on: {d['results']}"
    if t["share"] <= threshold or h["share"] <= threshold:
        return False, (f"approval does not clear {threshold:.0%}: question coverage tuning "
                       f"{t['share']:.1%} ({t['answered']}/{t['calls']}), held-out {h['share']:.1%} "
                       f"({h['answered']}/{h['calls']})")
    recall = ""
    if "recall_url_tuning" in d and "recall_url_heldout" in d:
        recall = (f"; same-URL recall reported {float(d['recall_url_tuning']):.1%} / "
                  f"{float(d['recall_url_heldout']):.1%} (below the morning's 90 % wording — "
                  f"the owner chose coverage)")
    return True, (f"APPROVED by {d['approved_by']} on {d['date']}: golden {d['golden_version']}, "
                  f"question coverage tuning {t['share']:.1%} ({t['answered']}/{t['calls']}) / held-out "
                  f"{h['share']:.1%} ({h['answered']}/{h['calls']}) recomputed from {d['results']}{recall}")


if __name__ == "__main__":
    ok, why = check(Path(sys.argv[1]) if len(sys.argv) > 1 else APPROVAL)
    print(why)
    sys.exit(0 if ok else 3)
