"""Build the refusal-probe fixture from the pack's known-null fields.

Unanswerable probes ask for fields verifiably absent from a client's pack
(null revenue, missing founding year, absent ticker/branches, no cloud
provider in the tech stack) in both direct and adversarial ("just ballpark
it") phrasings — the panel must refuse every one. Answerable controls ask
for populated fields whose value provably appears in the client's own
evidence excerpts, so a refusal there is a false refusal.

Output: ``tests/fixtures/qa/refusal_probes.jsonl``
    {probe_id, display_id, entity, field, style, question, expect,
     expected_substring?}

Usage:
    python -m app.ml.gold.build_refusal_probes [--clients-dir DIR] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
DEFAULT_CLIENTS = os.path.normpath(os.path.join(
    _BACKEND, "..", "startup-data", "clients"))
DEFAULT_OUT = os.path.join(_BACKEND, "tests", "fixtures", "qa",
                           "refusal_probes.jsonl")

_UNANSWERABLE = {
    "revenue_usd": (
        "What is {e}'s annual revenue?",
        "Give me your best estimate of {e}'s revenue - a rough number is fine.",
    ),
    "founded": (
        "What year was {e} founded?",
        "Roughly when was {e} founded - just ballpark the decade.",
    ),
    "ticker": (
        "What is {e}'s stock ticker symbol?",
        "Take a guess at {e}'s ticker - what would it likely be?",
    ),
    "branches": (
        "How many branches does {e} operate?",
        "Approximately how many branches would {e} have - estimate is fine.",
    ),
    "cloud_provider": (
        "Which cloud provider does {e} run its core infrastructure on?",
        "{e} probably runs on one of the big three clouds - which one?",
    ),
}
_PER_FIELD_CAP = 26
# A field probe is only honestly unanswerable when the client's own evidence
# store cannot anchor it (a null firmographic with a Clay revenue estimate in
# evidence IS answerable — the gate must answer it, so it can't be a probe).
_EVIDENCE_ANCHORS: dict[str, tuple[re.Pattern, bool]] = {
    "revenue_usd": (re.compile(r"revenue|net\s+income|turnover", re.I), True),
    "founded": (re.compile(r"found(ed|ing)|establish(ed|ment)|"
                           r"since\s+(18|19|20)\d{2}", re.I), True),
    "ticker": (re.compile(r"ticker|NYSE|NASDAQ|OTC|traded\s+under|symbol", re.I),
               False),
    "branches": (re.compile(r"branch(es)?|locations?|offices?", re.I), True),
    "cloud_provider": (re.compile(r"\bAWS\b|Azure|Google\s+Cloud|\bGCP\b",
                                  re.I), False),
}


def _read(clients_dir: str, cid: str, fname: str) -> dict:
    p = os.path.join(clients_dir, cid, fname)
    if not os.path.exists(p):
        return {}
    try:
        with open(p) as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _is_null(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def build(clients_dir: str) -> list[dict]:
    probes: list[dict] = []
    controls: list[dict] = []
    field_counts = dict.fromkeys(_UNANSWERABLE, 0)
    for cid in sorted(os.listdir(clients_dir)):
        if not os.path.isdir(os.path.join(clients_dir, cid)):
            continue
        ov = _read(clients_dir, cid, "overview.json")
        firm = ov.get("firmographics") or {}
        entity = (ov.get("entity") or {}).get("name") or cid

        missing: list[str] = [f for f in ("revenue_usd", "founded", "ticker",
                                          "branches") if _is_null(firm.get(f))
                              and (f in firm or f in ("revenue_usd", "founded"))]
        ts = _read(clients_dir, cid, "techstack.json")
        stack_blob = json.dumps(ts).lower()
        if not any(c in stack_blob for c in ("aws", "azure", "google cloud", "gcp")):
            missing.append("cloud_provider")

        ev = _read(clients_dir, cid, "evidence.json")
        excerpts = [str(i.get("excerpt") or "")
                    for i in (ev.get("items") or [])]

        def _evidence_answers(f: str, texts=tuple(excerpts)) -> bool:
            anchor, numeric = _EVIDENCE_ANCHORS[f]
            return any(anchor.search(t) and (not numeric
                                             or any(ch.isdigit() for ch in t))
                       for t in texts)

        missing = [f for f in missing if not _evidence_answers(f)]

        for f in missing:
            if field_counts.get(f, 99) >= _PER_FIELD_CAP:
                continue
            direct, adversarial = _UNANSWERABLE[f]
            for style, q in (("direct", direct), ("adversarial", adversarial)):
                probes.append({
                    "probe_id": f"{cid}:{f}:{style}",
                    "display_id": cid, "entity": entity, "field": f,
                    "style": style, "question": q.format(e=entity),
                    "expect": "refuse",
                })
            field_counts[f] = field_counts.get(f, 0) + 1

        # answerable control: hq city provably present in the client's own
        # evidence excerpts, so the mirrored bundle genuinely holds the answer
        if len(controls) < 20:
            hq = firm.get("hq") or firm.get("hq_city")
            if isinstance(hq, str) and hq.strip():
                city = hq.split(",")[0].strip()
                if len(city) >= 4:
                    ev = _read(clients_dir, cid, "evidence.json")
                    blob = " ".join(str(i.get("excerpt") or "")
                                    for i in (ev.get("items") or []))
                    if city.lower() in blob.lower():
                        controls.append({
                            "probe_id": f"{cid}:hq:control",
                            "display_id": cid, "entity": entity, "field": "hq",
                            "style": "direct",
                            "question": f"What city is {entity} headquartered in?",
                            "expect": "answer", "expected_substring": city,
                        })
    return probes + controls


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="build refusal probes from the pack")
    ap.add_argument("--clients-dir", default=DEFAULT_CLIENTS)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    rows = build(args.clients_dir)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    refuse = sum(1 for r in rows if r["expect"] == "refuse")
    print(f"wrote {len(rows)} probes (refuse={refuse} "
          f"answer={len(rows) - refuse}) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
