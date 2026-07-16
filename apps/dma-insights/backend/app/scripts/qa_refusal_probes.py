"""Run the refusal probes against the grounding contract's pre-call gate.

For each probe, mirrors live retrieval by ranking the client's own
``evidence.json`` excerpts against the question (lexical index, top-k) and
asks ``grounding_contract.should_refuse`` whether that bundle can honestly
answer. Targets (Training Spec Tab 08 §8.3): refusal >= 98% on unanswerable
probes, 0% false-refusals on answerable controls. Exit 1 on a miss.

Usage:
    python -m app.scripts.qa_refusal_probes [--probes PATH] [--clients-dir DIR]
        [--top-k 8] [--min-support 0.18] [--emit-extras BENCH_DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

from app.services.grounding_contract import should_refuse
from app.services.nlp.similarity import LexicalIndex

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", ".."))
DEFAULT_PROBES = os.path.join(_BACKEND, "tests", "fixtures", "qa",
                              "refusal_probes.jsonl")
DEFAULT_CLIENTS = os.path.normpath(os.path.join(
    _BACKEND, "..", "startup-data", "clients"))


def _bundle_for(clients_dir: str, cid: str, question: str,
                top_k: int, cache: dict) -> list[dict]:
    if cid not in cache:
        p = os.path.join(clients_dir, cid, "evidence.json")
        docs = []
        if os.path.exists(p):
            with open(p) as fh:
                for item in json.load(fh).get("items") or []:
                    text = f"{item.get('source_name') or ''}: {item.get('excerpt') or ''}"
                    if len(text) > 12:
                        docs.append((item.get("e_id"), text))
        idx = LexicalIndex()
        if docs:
            idx.fit(docs)
        cache[cid] = (idx, dict(docs))
    idx, by_id = cache[cid]
    if not by_id:
        return []
    hits = idx.top_k(question, k=top_k)
    return [{"text": by_id[eid]} for eid, _s in hits if eid in by_id]


def run(probes_path: str, clients_dir: str, top_k: int,
        min_support: float) -> dict:
    with open(probes_path) as fh:
        probes = [json.loads(line) for line in fh]
    cache: dict = {}
    refused_when_should = 0
    n_refuse = 0
    false_refusals = []
    missed_refusals = []
    reasons: Counter = Counter()
    for probe in probes:
        bundle = _bundle_for(clients_dir, probe["display_id"],
                             probe["question"], top_k, cache)
        refuse, reason = should_refuse(probe["question"], bundle,
                                       min_support=min_support)
        if probe["expect"] == "refuse":
            n_refuse += 1
            if refuse:
                refused_when_should += 1
                reasons[reason] += 1
            else:
                missed_refusals.append(probe["probe_id"])
        else:
            if refuse:
                false_refusals.append((probe["probe_id"], reason))
    n_answer = len(probes) - n_refuse
    return {
        "probes": len(probes), "unanswerable": n_refuse, "controls": n_answer,
        "refusal_rate_pct": round(100.0 * refused_when_should / n_refuse, 2)
        if n_refuse else None,
        "false_refusal_pct": round(100.0 * len(false_refusals) / n_answer, 2)
        if n_answer else None,
        "refusal_reasons": dict(reasons),
        "missed_refusals": missed_refusals[:10],
        "false_refusals": false_refusals[:10],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="refusal probe harness")
    ap.add_argument("--probes", default=DEFAULT_PROBES)
    ap.add_argument("--clients-dir", default=DEFAULT_CLIENTS)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--min-support", type=float, default=0.18)
    ap.add_argument("--emit-extras", default=None)
    args = ap.parse_args(argv)
    report = run(args.probes, args.clients_dir, args.top_k, args.min_support)
    print(json.dumps(report, indent=2))
    if args.emit_extras:
        path = os.path.join(args.emit_extras, "raw", "extras",
                            "refusal_probes.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        base = {"unit": "pct", "owner_script": "rag_answer",
                "source": "qa_refusal_probes", "bound": 100.0,
                "requires_db": False}
        with open(path, "w") as fh:
            json.dump({
                "probe.refusal_rate_pct": {
                    "value": report["refusal_rate_pct"],
                    "direction": "up", **base},
                "probe.false_refusal_pct": {
                    "value": report["false_refusal_pct"],
                    "direction": "down", **base},
            }, fh, indent=2)
    ok = ((report["refusal_rate_pct"] or 0) >= 98.0
          and (report["false_refusal_pct"] or 0) <= 0.0)
    print(f"=> {'PASS' if ok else 'FAIL'} "
          f"(targets: refusal >= 98%, false refusal = 0%)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
