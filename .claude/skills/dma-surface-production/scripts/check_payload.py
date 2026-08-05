#!/usr/bin/env python3
"""Local pre-submit checks for a DMA Insights page payload.

Catches the cheap failures here so submissions spend their round trips on the
expensive ones — grain, identity and grounding — which only the server can check.

    python scripts/check_payload.py payload.json --page overview
    python scripts/check_payload.py payload.json --page heatmap --strict

Exit code 0 = clean, 1 = blocking problems found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# ── the section registry, by page ────────────────────────────────────
SECTIONS = {
    "overview": ["scores", "firmographics", "why_now", "exec_summary", "opportunity",
                 "findings", "leadership", "financial_series", "sentiment", "ceilings",
                 "evidence_coverage", "thought_leadership"],
    "insights": ["insights", "landscape"],
    "heatmap": ["workbook_scores", "focus_areas", "cell_evidence", "evidence",
                "value_chain", "alerts", "safeguard_gates", "evidence_age",
                "cohort_patterns"],
    "platform": ["platform_story", "recommendations", "starters", "roadmap", "stairstep"],
    "context": ["timeline", "issue_register", "regulatory_standing", "context_sentiment",
                "acquisitions"],
    "techstack": ["techstack"],
}
OPTIONAL = {"heatmap": {"value_chain", "cohort_patterns"}}

# Sections whose content is client-visible and therefore must declare redaction.
NEEDS_INTERNAL_ONLY = {
    "scores", "firmographics", "findings", "exec_summary", "opportunity", "ceilings",
    "evidence_coverage", "sentiment", "thought_leadership", "insights",
    "cell_evidence", "safeguard_gates", "cohort_patterns", "platform_story",
    "recommendations", "starters",
}

# ── vocabularies ─────────────────────────────────────────────────────
EID = re.compile(r"\b(?:E|EV|INT)-[A-Z0-9]+(?:-[A-Z0-9]+){0,3}(?![A-Za-z0-9-])")
SUBCAP = re.compile(r"^P[1-4]C\d{1,2}(?:\.\d{1,2}){0,2}[a-z]?$")
AGENT_IDS = {"ic_id": r"^IC-\d{1,3}$", "f_id": r"^F-\d{1,2}$", "fa_id": r"^FA-\d{1,2}$",
             "ts_id": r"^TS-\d{1,3}$", "wn_id": r"^WN-\d{1,2}$"}
TIERS = {"T1", "T2", "T3", "T4", "T5"}
RECENCY = {"CURRENT", "RECENT", "DATED", "STALE", "ARCHIVAL", "UNVERIFIED"}
CLAIMS = {"FACT", "INFERENCE", "HYPOTHESIS", "CEILING_ESTIMATE"}
STACK_LAYERS = {"OPS", "CUST", "DATA", "INFRA"}
STACK_STATUS = {"CONFIRMED", "INFERRED", "CLAIMED", "ABSENT"}
GATE_RESULT = {"PASS", "FAIL", "NOT_RUN"}
PEER_BASIS = {"table", "recomputed", "inferred", "cannot_estimate"}

BANNED_REGISTER = [
    (r"\bleverage\b", "consultant register"),
    (r"\bbest.in.class\b", "consultant register"),
    (r"\bjourney\b", "consultant register"),
    (r"\blacks\b", "deficit framing"),
    (r"\bfails to\b", "deficit framing"),
    (r"\bworld.class\b", "consultant register"),
    (r"^#{1,6}\s", "markdown heading in a text field"),
    (r"\*\*", "markdown emphasis in a text field"),
]
SENTINELS = [r"\bNaN\b", r"\bnan\b", r"\bnull\b(?!able)", r"\bundefined\b", r"\bN/A\b",
             r"\b-999\b", r"\bTBD\b", r"\bTODO\b"]

problems: list[tuple[str, str, str]] = []


def bad(sev, path, msg):
    problems.append((sev, path, msg))


def walk(node, path=""):
    """Yield (path, value) for every scalar in the payload."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, node


def check_structure(page, payload):
    expected = set(SECTIONS[page])
    optional = OPTIONAL.get(page, set())
    got = set(payload)
    for missing in sorted(expected - got - optional):
        bad("BLOCK", page, f"required section '{missing}' is absent")
    for extra in sorted(got - expected):
        bad("BLOCK", f"{page}.{extra}", "section is not in this page's contract")
    for opt in sorted((expected & optional) - got):
        bad("INFO", f"{page}.{opt}", "optional section omitted")


def check_envelope(page, payload):
    for sec, body in payload.items():
        if not isinstance(body, dict):
            bad("BLOCK", f"{page}.{sec}", "section body must be an object")
            continue
        for field in ("produced_at", "producer_version", "e_ids"):
            if field not in body:
                bad("BLOCK", f"{page}.{sec}", f"universal envelope missing '{field}'")
        if sec in NEEDS_INTERNAL_ONLY and "internal_only" not in body:
            bad("BLOCK", f"{page}.{sec}",
                "client-visible section declares no internal_only paths — "
                "an unmarked internal rung reaches the client")
        eids = body.get("e_ids")
        if isinstance(eids, list):
            if len(eids) != len(set(eids)):
                bad("WARN", f"{page}.{sec}.e_ids", "contains duplicates")
            for e in eids:
                if isinstance(e, str) and not EID.fullmatch(e):
                    bad("BLOCK", f"{page}.{sec}.e_ids", f"'{e}' is not a valid evidence id")
                if isinstance(e, str) and (e.startswith("[") or e.endswith("]")):
                    bad("BLOCK", f"{page}.{sec}.e_ids",
                        f"'{e}' is bracketed — brackets belong to the chip, not the id")


def check_scalars(page, payload):
    for path, val in walk(payload, page):
        if not isinstance(val, str):
            continue
        low = path.lower()
        # sentinels anywhere
        for pat in SENTINELS:
            if re.search(pat, val):
                bad("BLOCK", path,
                    f"sentinel value {val!r} — a derived value is computed or null")
                break
        # register rules on prose fields only
        if any(k in low for k in ("body", "rationale", "story", "text", "framing",
                                  "synthesis", "summary", "title", "headline",
                                  "statement", "narrative", "consequence")):
            for pat, why in BANNED_REGISTER:
                if re.search(pat, val, re.I | re.M):
                    bad("WARN", path, f"{why}: matched /{pat}/")
            if re.search(r"\bP[1-4]C\d", val):
                bad("BLOCK", path, "raw taxonomy code in client-visible prose — "
                                   "humanise the capability name")
            if re.match(r"^\s*[A-Z0-9.]+\s+scores?\s+\d", val) or \
               re.match(r"^\s*(?:At|With)\s+\d\.\d", val):
                bad("WARN", path, "score-predicate opener")
            # Titles and headlines are labels, not sentences — no terminal stop.
            is_label = any(low.endswith(x) for x in (".title", ".headline", ".statement"))
            if val and not is_label and val.strip()[-1] not in ".?!\"')]":
                bad("WARN", path, "prose does not end in terminal punctuation — "
                                  "clipped text was a measured defect")
            if is_label and len(val.split()) > 20:
                bad("WARN", path, f"label is {len(val.split())} words — titles are claims, "
                                  "not sentences; keep them tight")
        # vocabularies
        if low.endswith(".tier") and val not in TIERS:
            bad("BLOCK", path, f"tier {val!r} outside T1–T5")
        if low.endswith("recency_tag") and val not in RECENCY:
            bad("BLOCK", path, f"recency {val!r} not in the one vocabulary")
        if low.endswith("claim_type") and val not in CLAIMS:
            bad("BLOCK", path, f"claim_type {val!r} unknown")
        if low.endswith(".layer") and val not in STACK_LAYERS:
            bad("BLOCK", path, f"layer {val!r} — use OPS/CUST/DATA/INFRA, never L2–L5 "
                               "(they collide with evidence levels)")
        if low.endswith(".status") and "techstack" in page and val not in STACK_STATUS:
            bad("BLOCK", path, f"stack status {val!r} unknown")
        if low.endswith(".result") and "gate" in low and val not in GATE_RESULT:
            bad("BLOCK", path, f"gate result {val!r} — must be PASS, FAIL or NOT_RUN")
        if low.endswith("peer_basis") and val not in PEER_BASIS:
            bad("BLOCK", path, f"peer_basis {val!r} unknown")
        if low.endswith("subcap_id") and not SUBCAP.match(val):
            bad("BLOCK", path, f"'{val}' is not a well-formed cell id")
        for field, pat in AGENT_IDS.items():
            if low.endswith(field) and not re.match(pat, val):
                bad("BLOCK", path, f"{field} {val!r} does not match {pat}")
        # excerpts
        if low.endswith(".excerpt"):
            n = len(val)
            if n < 50:
                bad("BLOCK", path, f"excerpt is {n} chars — minimum 50")
            if n > 500:
                bad("BLOCK", path, f"excerpt is {n} chars — maximum 500")
            if val.strip().startswith("http"):
                bad("BLOCK", path, "excerpt is a bare URL, not a quotation")


def check_numbers(page, payload):
    for path, val in walk(payload, page):
        low = path.lower()
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if low.endswith("ers"):
                bad("WARN", path, "the server computes the rank score — sending it is ignored")
            if low.endswith(("score", "median")) and not (0 <= val <= 5):
                bad("BLOCK", path, f"{val} outside the 1–5 maturity scale")
            if low.endswith("_pct") and not (0 <= val <= 100):
                bad("BLOCK", path, f"{val} is not a percentage")
            if low.endswith("cohort_size") and val < 5:
                bad("BLOCK", path, f"cohort of {val} — below five it is not published")
        if val is None and low.endswith(("status", "severity")):
            bad("BLOCK", path, "status and severity are always populated")


def check_gates_section(page, payload):
    sg = payload.get("safeguard_gates")
    if not isinstance(sg, dict):
        return
    if "caps" not in sg or "gates" not in sg:
        bad("BLOCK", f"{page}.safeguard_gates",
            "must carry BOTH caps[] (what the assessment capped) and gates[] "
            "(the SG results) — they are different things")
    for i, g in enumerate(sg.get("gates", []) or []):
        p = f"{page}.safeguard_gates.gates[{i}]"
        if not g.get("plain_label"):
            bad("BLOCK", p, "plain_label is required — this card renders to the client")
        elif not 6 <= len(g["plain_label"].split()) <= 24:
            bad("WARN", p, "plain_label should be a human sentence of roughly 8–18 words")
        if g.get("result") == "NOT_RUN" and not g.get("not_run_reason"):
            bad("BLOCK", p, "NOT_RUN requires a reason — a silent NOT_RUN is a PASS in disguise")


def check_empty_states(page, payload):
    for sec, body in payload.items():
        if not isinstance(body, dict):
            continue
        arrays = {k: v for k, v in body.items() if isinstance(v, list)}
        if arrays and all(len(v) == 0 for v in arrays.values()):
            es = body.get("empty_state")
            if not es:
                bad("BLOCK", f"{page}.{sec}",
                    "every array is empty and no empty_state is declared — "
                    "an absence with no record is a research failure, not a finding")
            elif isinstance(es, dict) and not es.get("sources_searched"):
                bad("WARN", f"{page}.{sec}.empty_state",
                    "declares no sources_searched — state what established the absence")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("--page", required=True, choices=sorted(SECTIONS))
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    a = ap.parse_args()

    try:
        payload = json.load(open(a.payload, encoding="utf-8"))
    except Exception as e:
        print(f"could not read payload: {e}")
        return 1
    if not isinstance(payload, dict):
        print("payload must be an object keyed by section name")
        return 1

    for fn in (check_structure, check_envelope, check_scalars, check_numbers,
               check_gates_section, check_empty_states):
        fn(a.page, payload)

    order = {"BLOCK": 0, "WARN": 1, "INFO": 2}
    problems.sort(key=lambda p: (order[p[0]], p[1]))
    blocks = sum(1 for s, *_ in problems if s == "BLOCK")
    warns = sum(1 for s, *_ in problems if s == "WARN")

    print(f"page: {a.page}   sections: {len(payload)}   "
          f"blocking: {blocks}   warnings: {warns}\n")
    for sev, path, msg in problems:
        print(f"  [{sev:5s}] {path}\n            {msg}")
    if not problems:
        print("  clean — the local checks pass. Grain, identity and grounding are still "
              "checked server-side at submit.")
    return 1 if blocks or (a.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
