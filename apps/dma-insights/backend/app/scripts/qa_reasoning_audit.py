"""Reasoning audit: challenge every inference class the composers assert.

Each class is a deterministic, corpus-wide check of a CLAIM against the
run's own data (never a style opinion). Classes come from the 2026-07-12
benchmark reads — each one is a way a script asserted more than the data
supports:

  R1 superlative      -- 'widest/strongest/top' claims verified against the
                         run's actual ranking (a superlative is only honest
                         for the argmax)
  R2 dynamics         -- dynamic peer-behaviour claims ('compounding',
                         'each cycle', 'pulling away') in GROUNDED slots;
                         the If-Ignored/risk slot is a consultative-forecast
                         slot and is exempt when hedged (tends/risks/may/
                         'becomes')
  R3 relation         -- 'connects to X' must carry the shared-evidence
                         wording the composer emits only on a verified pair;
                         'depend(s) on it' asserts a dependency graph
                         nothing verifies
  R4 claim_class      -- a why-now signal labelled FACT must render dated,
                         evidence-backed content

Usage:
    python -m app.scripts.qa_reasoning_audit [--clients-dir DIR]
        [--examples N] [--emit-extras BENCH_DIR]
Exit 1 when any class has violations (regression-gateable).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

_HERE = os.path.dirname(__file__)
DEFAULT_CLIENTS = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "startup-data", "clients"))

_DYNAMIC_RE = re.compile(
    r"compounding an advantage|each cycle|pulling away|accelerating away",
    re.I)
_HEDGE_RE = re.compile(r"\btends?\b|\brisks?\b|\bmay\b|\blikely\b|\bbecomes\b",
                       re.I)
_DEPEND_RE = re.compile(r"\bdepends? on it\b", re.I)
# only the COMPOSED capability-relation frames — literal system-to-system
# integration facts ("Marketing Cloud connects to Data Cloud") are cited
# technical statements, not the fabricated-relation class
_CONNECT_RE = re.compile(r"\bIt (?:also )?connects to\b")
_SHARED_EV_RE = re.compile(r"same evidence", re.I)
_DATED_RE = re.compile(r"\b(19|20)\d{2}\b|\bQ[1-4]\b")


def _load(cdir: str, fname: str):
    p = os.path.join(cdir, fname)
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def audit_client(cdir: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    hm = _load(cdir, "heatmap.json") or {}
    md = (hm.get("narrative") or {}).get("per_subcap_md") or {}
    cells = {c.get("id"): c for c in hm.get("cells") or []}
    below = {sid: -g for sid, c in cells.items()
             if isinstance((g := c.get("peer_gap")), int | float) and g < 0}
    max_below = max(below.values(), default=None)
    for sid, txt in md.items():
        if not isinstance(txt, str):
            continue
        if "widest peer gap in this run" in txt:
            g = below.get(sid)
            if max_below is None or g is None or g < max_below - 0.01:
                out.append(("R1_superlative", f"drawer {sid}: 'widest' but "
                            f"gap {g} < run max {max_below}"))
        if _DYNAMIC_RE.search(txt):
            out.append(("R2_dynamics", f"drawer {sid}: {txt[:90]!r}"))

    ov = _load(cdir, "overview.json") or {}
    for tf in ov.get("top_findings") or []:
        if not isinstance(tf, dict):
            continue
        blob = " ".join(str(tf.get(k) or "") for k in ("what", "why", "so_what"))
        if _DYNAMIC_RE.search(blob):
            out.append(("R2_dynamics", f"finding {tf.get('name')}: "
                        f"{blob[:90]!r}"))
        if _DEPEND_RE.search(blob):
            out.append(("R3_relation", f"finding {tf.get('name')}: "
                        f"'depends on it'"))
    for sig in ov.get("why_now_signals") or []:
        if not isinstance(sig, dict):
            continue
        blob = f"{sig.get('detail') or ''} {sig.get('risk') or ''}"
        # risk slot is a forecast slot — only UNHEDGED peer-behaviour
        # dynamics fail
        if _DYNAMIC_RE.search(blob) and not _HEDGE_RE.search(blob):
            out.append(("R2_dynamics", f"why_now {sig.get('label')}: "
                        f"{blob[:90]!r}"))
        if str(sig.get("claim") or "").upper() == "FACT" and not (
                sig.get("evidence") and _DATED_RE.search(
                    f"{sig.get('detail') or ''} {sig.get('window') or ''} "
                    f"{json.dumps(sig.get('timeline') or {})}")):
            out.append(("R4_claim_class", f"why_now {sig.get('label')}: "
                        f"FACT without dated evidence"))

    ins = _load(cdir, "insights.json") or {}
    for it in ins.get("items") or []:
        blob = " ".join(str(it.get(k) or "")
                        for k in ("what_text", "why_text", "so_what_text"))
        if _DYNAMIC_RE.search(blob):
            out.append(("R2_dynamics", f"card {str(it.get('title'))[:40]}: "
                        f"dynamic claim"))
        if _DEPEND_RE.search(blob):
            out.append(("R3_relation", f"card {str(it.get('title'))[:40]}: "
                        f"'depends on it'"))
        if _CONNECT_RE.search(blob) and not _SHARED_EV_RE.search(blob):
            out.append(("R3_relation", f"card {str(it.get('title'))[:40]}: "
                        f"'connects to' without shared-evidence grounding"))

    # SCQA exec summaries make the same relational claims (the AlmaBank
    # vetting sample: 'the capabilities that depend on it compound the
    # gain' in a kept answer slot) — audit them under the same R3 rule
    narr = (_load(cdir, "overview.json") or {}).get("narrative") or {}
    scqa = str(narr.get("scqa_md") or "")
    if _DEPEND_RE.search(scqa):
        out.append(("R3_relation", "scqa: 'depends on it'"))
    if _CONNECT_RE.search(scqa) and not _SHARED_EV_RE.search(scqa):
        out.append(("R3_relation",
                    "scqa: 'connects to' without shared-evidence grounding"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="reasoning audit")
    ap.add_argument("--clients-dir", default=DEFAULT_CLIENTS)
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--emit-extras", default=None)
    args = ap.parse_args(argv)
    counts: Counter = Counter()
    ex: dict[str, list[str]] = defaultdict(list)
    for cid in sorted(os.listdir(args.clients_dir)):
        cdir = os.path.join(args.clients_dir, cid)
        if not os.path.isdir(cdir):
            continue
        for cls, detail in audit_client(cdir):
            counts[cls] += 1
            if len(ex[cls]) < args.examples:
                ex[cls].append(f"{cid}: {detail}")
    print("# REASONING AUDIT")
    for cls in ("R1_superlative", "R2_dynamics", "R3_relation",
                "R4_claim_class"):
        print(f"  {cls:16s} violations={counts.get(cls, 0)}")
        for row in ex.get(cls, []):
            print(f"     {row}")
    if args.emit_extras:
        path = os.path.join(args.emit_extras, "raw", "extras",
                            "reasoning_audit.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        base = {"unit": "count", "direction": "down", "bound": 0.0,
                "owner_script": "composers", "source": "qa_reasoning_audit",
                "requires_db": False}
        with open(path, "w") as fh:
            json.dump({f"reason.{k}": {"value": float(v), **base}
                       for k, v in counts.items()}, fh, indent=2)
    return 1 if counts else 0


if __name__ == "__main__":
    sys.exit(main())
