"""Build the gold/reject headline-gate label set (Training Spec Tab 01 §2.2).

The quality classifier that gates headlines and So-Whats pre-ship trains on
gold/reject pairs: gold = the 5 committed refinement overlays + pack items
meeting the consultant bar + the spec's gold exemplars; reject = template/
accusatory/one-liner pack items + the spec's reject exemplars. Every row also
carries deterministic rule flags (vendor_first / threat_tone / generic) that
train the auxiliary heads.

Output: ``tests/fixtures/ml/headline_labels.jsonl``
    {text, surface: headline|so_what, label: gold|reject, flags: [...],
     source: overlay|pack|spec, entity}

Usage:
    python -m app.ml.gold.build_headline_gold [--clients DIR] [--overlays DIR]
        [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys

from app.scripts.countercheck_pack import TEMPLATE_RES, _accusatory, _sentence_count

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
_APPROOT = os.path.normpath(os.path.join(_BACKEND, ".."))
DEFAULT_CLIENTS = os.path.join(_APPROOT, "startup-data", "clients")
DEFAULT_OVERLAYS = os.path.join(_APPROOT, "startup-data", "refinement")
DEFAULT_OUT = os.path.join(_BACKEND, "tests", "fixtures", "ml",
                           "headline_labels.jsonl")

_EID_RE = re.compile(r"\bE-\d{1,4}\b")
VENDOR_RE = re.compile(
    r"Salesforce|Databricks|Tableau|Twilio|nCino|Agentforce|Snowflake|"
    r"Data Cloud|Microsoft|Oracle|SAP", re.I)
OUTCOME_RE = re.compile(
    r"\b(cut|close[sd]?|unlock|sav(e|ing)|reduc|grow|faster|one\s+member|"
    r"one\s+record|stop|scale|fund|prove|win|member|customer|client)\b", re.I)
THREAT_RE = re.compile(
    r"will\s+lose|risks?\s+falling|or\s+risk|faces?\s+extinction|"
    r"will\s+be\s+left\s+behind|competitors\s+will", re.I)

SPEC_GOLD = [
    "One member, one record, every channel - Data Cloud unifies the three "
    "cores that fragment the profile today",
    "Close a CCAR cycle in under an hour with lineage examiners accept, "
    "instead of a multi-day run plus manual audit assembly",
    "A 12-day origination cycle cut toward 4, using a tool already bought "
    "in the migration",
    "The team generates insight faster than it acts on it",
]
SPEC_GOLD_STARTERS = [
    "Today a CCAR cycle at your scale spends a multi-day run window and then "
    "a second effort assembling the audit trail by hand - and examiners are "
    "asking for lineage, not screenshots.",
    "Your origination cycle runs about 12 days with hand-offs living in "
    "email and spreadsheets. First Citizens took the same cycle from 11 days "
    "to 4 by switching on the nCino Workflow Engine - a capability you have "
    "already bought inside the migration you are already running.",
    "Members stop repeating themselves - one profile means the contact-center "
    "rep sees the mortgage, the deposit, and the card without asking.",
    "Insight that reaches operators without new infrastructure - Tableau "
    "Pulse rides the 1,800-user rollout already paid for.",
    "Service capacity that scales without headcount, once the data substrate "
    "is fixed.",
    "Every acquired customer cross-sold like a legacy customer, in the first "
    "year instead of the third.",
]
_THREAT_CLAUSES = [
    " Act now or risk falling behind competitors for good.",
    " Without this, the institution will be left behind as peers pull away.",
    " Delay means you will lose members to faster rivals, quarter after quarter.",
    " The franchise faces extinction if this window closes unanswered.",
    " Competitors will eat this book of business while the board deliberates.",
]
SPEC_REJECT = [
    "FCE trails peer median by 0.4 points",
    "FCE has new leadership and is evaluating data platforms. This creates "
    "urgency for digital transformation initiatives. Zennify can help FCE "
    "on its journey.",
    "FCE is a leading agricultural lender facing digital challenges in a "
    "rapidly evolving landscape. It must transform to meet member "
    "expectations.",
    "FCE has data fragmentation issues. This impacts member experience. "
    "FCE should consider a customer data platform.",
    "Salesforce Data Cloud is a leading CDP that unifies customer data",
    "Databricks offers a unified lakehouse platform with best-in-class ML "
    "capabilities that M&T should consider adopting as part of its "
    "modernization journey.",
    "This subcapability demonstrates developing maturity with opportunities "
    "for improvement relative to industry standards.",
    "We recommend implementing nCino Workflow Engine to improve loan "
    "origination efficiency.",
]


def vendor_first(text: str) -> bool:
    head = " ".join((text or "").split()[:6])
    vm = VENDOR_RE.search(head)
    if not vm:
        return False
    om = OUTCOME_RE.search(head)
    return om is None or vm.start() < om.start()


def threat_tone(text: str) -> bool:
    return bool(THREAT_RE.search(text or ""))


def _flags(text: str) -> list[str]:
    flags = []
    if vendor_first(text):
        flags.append("vendor_first")
    if threat_tone(text):
        flags.append("threat_tone")
    if any(rx.search(text) for rx in TEMPLATE_RES):
        flags.append("generic")
    return flags


def _row(text: str, surface: str, label: str, source: str, entity: str) -> dict:
    return {"text": text.strip(), "surface": surface, "label": label,
            "flags": _flags(text), "source": source, "entity": entity}


def _overlay_texts(overlays_dir: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.isdir(overlays_dir):
        return rows
    for fn in sorted(os.listdir(overlays_dir)):
        if not fn.endswith(".json"):
            continue
        entity = fn[:-5]
        with open(os.path.join(overlays_dir, fn)) as fh:
            overlay = json.load(fh)
        cards = overlay.get("insight_cards") or {}
        card_iter = cards.values() if isinstance(cards, dict) else cards
        for card in card_iter:
            if not isinstance(card, dict):
                continue
            if isinstance(card.get("title"), str) and card["title"].strip():
                rows.append(_row(card["title"], "headline", "gold", "overlay", entity))
            if isinstance(card.get("so_what_text"), str) and card["so_what_text"].strip():
                rows.append(_row(card["so_what_text"], "so_what", "gold", "overlay", entity))
        for tf in overlay.get("top_findings") or []:
            if not isinstance(tf, dict):
                continue
            title = tf.get("name") or tf.get("title")
            if isinstance(title, str) and title.strip():
                rows.append(_row(title, "headline", "gold", "overlay", entity))
            if isinstance(tf.get("so_what"), str) and tf["so_what"].strip():
                rows.append(_row(tf["so_what"], "so_what", "gold", "overlay", entity))
    return rows


def _pack_texts(clients_dir: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.isdir(clients_dir):
        return rows
    for cid in sorted(os.listdir(clients_dir)):
        p = os.path.join(clients_dir, cid, "insights.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p) as fh:
                items = json.load(fh).get("items") or []
        except (json.JSONDecodeError, OSError):
            continue
        for it in items:
            title = it.get("title") or ""
            so_what = it.get("so_what_text") or ""
            blob = " ".join([title, it.get("what_text") or "",
                             it.get("why_text") or "", so_what])
            template_hit = any(rx.search(blob) for rx in TEMPLATE_RES)
            acc_title = _accusatory(title)
            one_liner = so_what and _sentence_count(so_what) < 2 and len(so_what) < 120
            if template_hit and so_what:
                rows.append(_row(so_what, "so_what", "reject", "pack", cid))
            if acc_title and title:
                rows.append(_row(title, "headline", "reject", "pack", cid))
            if one_liner:
                rows.append(_row(so_what, "so_what", "reject", "pack", cid))
            if (so_what and len(set(_EID_RE.findall(so_what))) >= 1
                    and _sentence_count(so_what) >= 3
                    and any(ch.isdigit() for ch in so_what)
                    and not template_hit and not _accusatory(so_what)):
                rows.append(_row(so_what, "so_what", "gold", "pack", cid))
                if title and not acc_title:
                    rows.append(_row(title, "headline", "gold", "pack", cid))
    return rows


def build(clients_dir: str = DEFAULT_CLIENTS,
          overlays_dir: str = DEFAULT_OVERLAYS) -> list[dict]:
    rows = _overlay_texts(overlays_dir) + _pack_texts(clients_dir)
    rows += [_row(t, "so_what", "gold", "spec", "spec") for t in SPEC_GOLD]
    rows += [_row(t, "so_what", "gold", "spec", "spec")
             for t in SPEC_GOLD_STARTERS]
    rows += [_row(t, "so_what", "reject", "spec", "spec") for t in SPEC_REJECT]
    # Synthetic threat-tone rows: doom clauses injected onto otherwise-gold
    # texts teach the threat head the boundary (Tab 09 hard-fail class).
    rng_syn = random.Random(7)
    donors = [r["text"] for r in rows if r["label"] == "gold"][:30]
    for i, donor in enumerate(donors):
        clause = _THREAT_CLAUSES[i % len(_THREAT_CLAUSES)]
        rows.append(_row(donor + clause, "so_what", "reject",
                         "synthetic", f"syn-{i % 5}"))
    del rng_syn
    seen: dict[str, dict] = {}
    for r in rows:
        key = " ".join(r["text"].casefold().split())
        if key and key not in seen:
            seen[key] = r
    rows = list(seen.values())
    gold = [r for r in rows if r["label"] == "gold"]
    reject = [r for r in rows if r["label"] == "reject"]
    rng = random.Random(0)
    cap = 3 * max(min(len(gold), len(reject)), 1)
    for bucket in (gold, reject):
        rng.shuffle(bucket)
    gold = gold[:cap]
    reject = reject[:cap]
    out = gold + reject
    rng.shuffle(out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="build headline-gate gold labels")
    ap.add_argument("--clients", default=DEFAULT_CLIENTS)
    ap.add_argument("--overlays", default=DEFAULT_OVERLAYS)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    rows = build(args.clients, args.overlays)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    gold = sum(1 for r in rows if r["label"] == "gold")
    print(f"wrote {len(rows)} rows (gold={gold} reject={len(rows) - gold}) "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
