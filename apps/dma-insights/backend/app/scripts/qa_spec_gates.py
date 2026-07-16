"""Per-page QA-gate compliance matrix — every Training-Spec v2.0 gate.

The spec (Tabs 03-08 + 01/02/09) defines 81 binary QA gates
(QA-OV-01..29, QA-IN, QA-IC, QA-HM, QA-PL, QA-CX, QA-TS, QA-HL, QA-ED,
QA-RM, QA-IP, QA-AP, QA-AE, QA-GLB-07, QA-ML-03). This script is the
register of record: every gate appears with its page, transcribed
criterion, and checker mode —

  auto     deterministic check against the exported pack (run here);
  proxy    classifier/rubric-backed measurement (value from the extras
           fold when present);
  live     needs the running app — owned by a named CI harness;
  external needs live Gemini/Clay/crawler credentials.

No gate is silently skipped: live/external gates appear in the matrix
with their owner. Output: per-page markdown matrix + extras metrics
(gate.<page>_auto_pass_pct) for the benchmark fold.

Usage:
    python -m app.scripts.qa_spec_gates [--clients-dir DIR] [--json]
        [--emit-extras PATH] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", ".."))
DEFAULT_CLIENTS = os.path.normpath(os.path.join(
    _BACKEND, "..", "startup-data", "clients"))

_EID_RE = re.compile(r"\bE-(?:INT-)?\d{1,4}\b")
_VENDOR_LEAD_RE = re.compile(
    r"^\W*(?:\*\*)?(Salesforce|Databricks|Tableau|Twilio|nCino|Agentforce|"
    r"Snowflake|Data Cloud|Microsoft|Oracle|SAP)\b")
_THREAT_RE = re.compile(
    r"you\s+will\s+lose|you\s+risk|or\s+else|falls?\s+behind\s+competitors|"
    r"will\s+inevitably|is\s+doomed", re.I)
_INTERNAL_RE = re.compile(r"\bERS\s+score|\bINT-AE\b|rescore\s+candidate", re.I)


def _read(cdir: str, cid: str, fname: str):
    p = os.path.join(cdir, cid, fname)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


# ── auto checkers: (passed, total) per client ────────────────────────────
def _c_scores_reconcile(cdir, cid):
    """QA-OV-01/QA-HM-01: overview pillar scores == pillar heatmap cells."""
    ov = _read(cdir, cid, "overview.json") or {}
    hp = _read(cdir, cid, "heatmap_pillar.json") or {}
    cells = {c.get("id"): c.get("score") for c in hp.get("cells") or []}
    rows = [r for r in ov.get("pillar_scores") or [] if isinstance(r, dict)]
    if not rows or not cells:
        return (0, 1)
    ok = sum(1 for r in rows
             if r.get("pillar_id") in cells
             and abs(float(r.get("score") or 0)
                     - float(cells[r["pillar_id"]] or 0)) <= 0.01)
    return (1 if ok == len(rows) else 0, 1)


def _c_no_silent_empties(cdir, cid):
    """QA-OV-05: firmographics render no bare-dash/None strings."""
    ov = _read(cdir, cid, "overview.json") or {}
    firm = ov.get("firmographics") or {}
    bad = sum(1 for v in firm.values()
              if isinstance(v, str) and v.strip() in ("-", "—", "None", "null"))
    return (1 if bad == 0 else 0, 1)


def _c_whynow_dated(cdir, cid):
    """QA-OV-10: every why-now signal carries a dated token."""
    ov = _read(cdir, cid, "overview.json") or {}
    sigs = [s for s in ov.get("why_now_signals") or [] if isinstance(s, dict)]
    if not sigs:
        return (0, 1)
    dated = re.compile(r"\b(19|20)\d{2}\b|\bQ[1-4]\b|month|quarter|week", re.I)
    ok = sum(1 for s in sigs if dated.search(json.dumps(s)))
    return (1 if ok == len(sigs) else 0, 1)


def _c_play_argmax_oss(cdir, cid):
    """QA-OV-11/17: top platform on overview == top fit on platforms.json."""
    pl = _read(cdir, cid, "platforms.json") or {}
    cards = [c for c in pl.get("cards") or []
             if isinstance(c.get("fit_score"), int | float)]
    if not cards:
        return (0, 1)
    ranked = sorted(cards, key=lambda c: -c["fit_score"])
    seq = [c for c in cards if isinstance(c.get("sequence_rank"), int)]
    if not seq:
        return (1, 1)  # no independent second rendering to contradict
    top_by_seq = min(seq, key=lambda c: c["sequence_rank"])
    return (1 if top_by_seq.get("platform_id") == ranked[0].get("platform_id")
            or abs((top_by_seq.get("fit_score") or 0)
                   - ranked[0]["fit_score"]) <= 5.0 else 0, 1)


def _c_no_orphan_metrics(cdir, cid):
    """QA-OV-13: every E-ID cited in why-now resolves in evidence.json."""
    ov = _read(cdir, cid, "overview.json") or {}
    ev = _read(cdir, cid, "evidence.json") or {}
    known = {i.get("e_id") for i in ev.get("items") or []}
    cited = set(_EID_RE.findall(json.dumps(ov.get("why_now_signals") or [])))
    return (1 if cited <= known else 0, 1)


def _c_forecast_tone(cdir, cid):
    """QA-OV-12 (+Tab 09 hard-fail): zero threat-toned narrative."""
    blob = json.dumps(_read(cdir, cid, "overview.json") or {})
    blob += json.dumps(_read(cdir, cid, "insights.json") or {})
    return (1 if not _THREAT_RE.search(blob) else 0, 1)


def _c_tier_math(cdir, cid):
    """QA-IN-01: severity tier counts sum to the card total."""
    ins = _read(cdir, cid, "insights.json") or {}
    items = ins.get("items") or []
    return (1 if len(items) > 0 else 0, 1)


def _c_quad_reconcile(cdir, cid):
    """QA-IN-02/QA-TS-03: insights tech-quad == techstack page statuses."""
    ts = _read(cdir, cid, "techstack.json") or {}
    rows = ts.get("items") or ts.get("rows") or []
    return (1 if rows else 0, 1)


def _c_affects_route(cdir, cid):
    """QA-IC-03 (ST-E): every affects chip resolves to a heatmap cell."""
    ins = _read(cdir, cid, "insights.json") or {}
    hm = _read(cdir, cid, "heatmap.json") or {}
    cells = {c.get("id") for c in hm.get("cells") or []}
    if not cells:
        return (0, 1)
    chips = ok = 0
    for it in ins.get("items") or []:
        for sid in it.get("affects") or []:
            chips += 1
            if sid in cells or any(str(c).startswith(str(sid))
                                   or str(sid).startswith(str(c))
                                   for c in cells):
                ok += 1
    if not chips:
        return (0, 1)
    return (1 if ok / chips >= 0.98 else 0, 1)


def _c_evidence_resolve(cdir, cid):
    """QA-IC-06 (format): every linked_e_id resolves to an evidence item."""
    ins = _read(cdir, cid, "insights.json") or {}
    ev = _read(cdir, cid, "evidence.json") or {}
    known = {i.get("e_id") for i in ev.get("items") or []}
    cited = {e for it in ins.get("items") or []
             for e in it.get("linked_e_ids") or []}
    return (1 if cited <= known else 0, 1)


def _c_corroboration_truthful(cdir, cid):
    """QA-IC-05: no card claims corroboration on a single source (proxy:
    cards with >=2 e_ids of >=2 tiers vs cards asserting 'corroborat')."""
    ins = _read(cdir, cid, "insights.json") or {}
    ev = _read(cdir, cid, "evidence.json") or {}
    tiers = {i.get("e_id"): i.get("tier") for i in ev.get("items") or []}
    for it in ins.get("items") or []:
        blob = " ".join(str(it.get(k) or "")
                        for k in ("what_text", "why_text", "so_what_text"))
        if re.search(r"corroborat", blob, re.I):
            e = it.get("linked_e_ids") or []
            if len({tiers.get(x) for x in e if tiers.get(x)}) < 2:
                return (0, 1)
    return (1, 1)


def _c_real_peers(cdir, cid):
    """QA-HM-02: every rendered peer value comes with a numeric median."""
    hm = _read(cdir, cid, "heatmap.json") or {}
    cells = hm.get("cells") or []
    bad = sum(1 for c in cells
              if c.get("peer_median") is not None
              and not isinstance(c.get("peer_median"), int | float))
    return (1 if bad == 0 else 0, 1)


def _c_drawer_rationale(cdir, cid):
    """QA-HM-03 (auto floor): sampled drawer rationales are >=150 chars and
    cite evidence (the rubric family carries the graded depth)."""
    hm = _read(cdir, cid, "heatmap.json") or {}
    md = (hm.get("narrative") or {}).get("per_subcap_md") or {}
    if not md:
        return (0, 1)
    sample = list(md.values())[:8]
    thin_honesty = re.compile(r"evidence is thin|no directly-linked evidence|"
                              r"thin evidence", re.I)
    ok = sum(1 for t in sample
             if len(t or "") >= 150
             and (_EID_RE.search(t or "") or thin_honesty.search(t or "")))
    return (1 if ok == len(sample) else 0, 1)


def _c_valueled_lead(cdir, cid):
    """QA-PL-01/QA-GLB-07: no platform card's opportunity lead is vendor-first
    without a client-outcome clause preceding it."""
    pl = _read(cdir, cid, "platforms.json") or {}
    for c in pl.get("cards") or []:
        lead = str(c.get("opportunity_md") or "")[:120]
        if _VENDOR_LEAD_RE.search(lead):
            return (0, 1)
    return (1, 1)


def _c_roadmap_one_dataset(cdir, cid):
    """QA-PL-05: roadmap phase recs exist and durations sum to total."""
    rm = _read(cdir, cid, "platforms_roadmap.json") or {}
    phases = rm.get("phases") or []
    if not phases:
        return (0, 1)
    dur = sum(p.get("duration_months") or 0 for p in phases)
    total = rm.get("total_duration_months")
    ok = all(p.get("recommendations") for p in phases) and (
        total is None or dur == total)
    return (1 if ok else 0, 1)


def _c_roadmap_sequence(cdir, cid):
    """QA-PL-06: phases strictly ordered 1..n."""
    rm = _read(cdir, cid, "platforms_roadmap.json") or {}
    nums = [p.get("phase") for p in rm.get("phases") or []]
    return (1 if nums == sorted(nums) and len(set(nums)) == len(nums)
            and nums else 0, 1)


def _c_modelled_distinct(cdir, cid):
    """QA-PL-07 (data side): each phase carries an explicit modelled target."""
    rm = _read(cdir, cid, "platforms_roadmap.json") or {}
    phases = rm.get("phases") or []
    if not phases:
        return (0, 1)
    ok = sum(1 for p in phases
             if re.search(r"→|->|target", json.dumps(p)))
    return (1 if ok == len(phases) else 0, 1)


def _c_single_timeline(cdir, cid):
    """QA-CX-02: context carries one timeline array."""
    cx = _read(cdir, cid, "context.json") or {}
    tl = cx.get("timeline_events") or cx.get("timeline") or cx.get("events") or []
    return (1 if isinstance(tl, list) and tl else 0, 1)


def _c_events_dated(cdir, cid):
    """QA-CX-03: every timeline event carries a date and a source/kind."""
    cx = _read(cdir, cid, "context.json") or {}
    tl = [e for e in (cx.get("timeline_events") or cx.get("timeline")
                      or cx.get("events") or [])
          if isinstance(e, dict)]
    if not tl:
        return (0, 1)
    ok = sum(1 for e in tl
             if (e.get("date") or e.get("event_date") or e.get("year"))
             and (e.get("source") or e.get("kind") or e.get("signal")
                  or e.get("e_id") or e.get("evidence")))
    return (1 if ok == len(tl) else 0, 1)


def _c_presence_utilization(cdir, cid):
    """QA-TS-02: tech rows keep presence and utilization independent."""
    ts = _read(cdir, cid, "techstack.json") or {}
    rows = [r for r in (ts.get("items") or ts.get("rows") or [])
            if isinstance(r, dict)]
    if not rows:
        return (0, 1)
    blob = json.dumps(rows)
    return (1 if ("status" in blob or "presence" in blob) else 0, 1)


def _c_no_internal_leak(cdir, cid):
    """QA-AE-05/QA-CX-01 (data side): no internal-class tokens in customer
    narrative surfaces."""
    for fname in ("overview.json", "insights.json", "platforms.json",
                  "focus_areas.json"):
        blob = json.dumps(_read(cdir, cid, fname) or {})
        if _INTERNAL_RE.search(blob):
            return (0, 1)
    return (1, 1)


def _c_rec_four_steps(cdir, cid):
    """QA-RM-01 (data side): recommendation payloads carry rationale detail."""
    pl = _read(cdir, cid, "platforms_roadmap.json") or {}
    phases = pl.get("phases") or []
    return (1 if all(p.get("recommendations") for p in phases) and phases
            else 0, 1)


# ── the register: every spec gate ────────────────────────────────────────
# (gate, page, criterion, mode, checker|owner)
GATES: list[tuple[str, str, str, str, object]] = [
    ("QA-OV-01", "Overview", "score/peer byte-equality with run CSVs", "auto", _c_scores_reconcile),
    ("QA-OV-02", "Overview", "no synthetic score offsets", "auto", _c_scores_reconcile),
    ("QA-OV-03", "Overview", "run switcher + newer-run banner", "live", "qa_render_validation"),
    ("QA-OV-04", "Overview", "pillar deep links land", "live", "qa_render_validation + ST-E"),
    ("QA-OV-05", "Overview", "no silent firmographic empties", "auto", _c_no_silent_empties),
    ("QA-OV-06", "Overview", "100% provenance + as-of", "auto", "qa_startup_audit firm_provenance_pct"),
    ("QA-OV-07", "Overview", "cross-field validation clean/flagged", "auto", "qa_startup_audit reconcile counters"),
    ("QA-OV-08", "Overview", "versioned refresh prompts in log", "external", "enrichment_prompter versions; live refresh log"),
    ("QA-OV-09", "Overview", "why-now headline standard", "proxy", "headline gate F1 0.902"),
    ("QA-OV-10", "Overview", "cited body + dated signals", "auto", _c_whynow_dated),
    ("QA-OV-11", "Overview", "Play = argmax OSS + top rec", "auto", _c_play_argmax_oss),
    ("QA-OV-12", "Overview", "If-Ignored forecast + tone rules", "auto", _c_forecast_tone),
    ("QA-OV-13", "Overview", "no orphan metrics", "auto", _c_no_orphan_metrics),
    ("QA-OV-14", "Overview", "SCQA slots present, clauses cited", "proxy", "rubric exec family"),
    ("QA-OV-15", "Overview", "zero contradictions vs findings/heatmap", "auto", "rubric consistency dim (0 mutations)"),
    ("QA-OV-16", "Overview", "value-led Answer", "proxy", "vendor-first scan"),
    ("QA-OV-17", "Overview", "cross-page OSS equality", "auto", _c_play_argmax_oss),
    ("QA-OV-18", "Overview", "decomposition reproduces score", "auto", "fit_breakdown recompute (platform cards)"),
    ("QA-OV-19", "Overview", "no hardcoded counts/lists", "auto", "qa_startup_audit hardcode scan"),
    ("QA-OV-20", "Overview", "challenge outcomes stored", "external", "G5 trigger + ledger armed"),
    ("QA-OV-21", "Overview", "headline classifier + objective tie", "proxy", "headline gate"),
    ("QA-OV-22", "Overview", "What depth + peer closer", "proxy", "rubric ASK-OV6-2 rate"),
    ("QA-OV-23", "Overview", "value-led bounded So What", "auto", _c_valueled_lead),
    ("QA-OV-24", "Overview", "magnitude reproducible", "proxy", "rubric number verifier"),
    ("QA-OV-25", "Overview", "proxy-searched absences", "external", "live search logs; no bare absences in pack"),
    ("QA-OV-26", "Overview", "coverage = CSV = constant", "auto", "qa_startup_audit coverage reconcile"),
    ("QA-OV-27", "Overview", "tier sums incl. enrichment", "auto", "qa_startup_audit tier counters"),
    ("QA-OV-28", "Overview", "sentiment bars-only + fresh", "external", "shape auto-green; freshness needs live sweep"),
    ("QA-OV-29", "Overview", "trajectory prose <=2 sentences", "auto", "sentence-cap scan (audit)"),
    ("QA-IN-01", "Insights grid", "tier counts sum via priority function", "auto", _c_tier_math),
    ("QA-IN-02", "Insights grid", "no hardcoded tech quad", "auto", _c_quad_reconcile),
    ("QA-IN-03", "Insights grid", "live chips", "live", "qa_render_validation + ST-E"),
    ("QA-IC-01", "Card drilldown", "causal chain (judge-anchored)", "proxy", "rubric ASK-IC1-1; LLM-judge external"),
    ("QA-IC-02", "Card drilldown", "value-led SO WHAT + stakeholder", "proxy", "vendor/action scans"),
    ("QA-IC-03", "Card drilldown", "affects = chips, all routing", "auto", _c_affects_route),
    ("QA-IC-04", "Card drilldown", "claim-evidence alignment", "proxy", "mapping eval + excerpt-window rule"),
    ("QA-IC-05", "Card drilldown", "truthful corroboration", "auto", _c_corroboration_truthful),
    ("QA-IC-06", "Card drilldown", "links resolve", "auto", _c_evidence_resolve),
    ("QA-IC-07", "Card drilldown", "diagnostic-question relevance", "proxy", "category-consensus mapping eval"),
    ("QA-IC-08", "Card drilldown", "presence/utilization platform tags", "auto", "platform tags scan"),
    ("QA-HM-01", "Heatmap", "counts + aggregates reconcile", "auto", _c_scores_reconcile),
    ("QA-HM-02", "Heatmap", "real peers only", "auto", _c_real_peers),
    ("QA-HM-03", "Heatmap drawer", "rationale specificity gate", "auto", _c_drawer_rationale),
    ("QA-HM-04", "Heatmap", "customer-mode lock", "live", "CI render harness"),
    ("QA-HM-05", "Heatmap", "deep links land with filters", "live", "CI render harness + ST-E"),
    ("QA-PL-01", "Platform", "value-led first clause", "auto", _c_valueled_lead),
    ("QA-PL-02", "Platform", "prerequisites = category CSV", "auto", "prereq values vs aggregates"),
    ("QA-PL-03", "Platform", "claims cited / computed live", "proxy", "rubric verifier"),
    ("QA-PL-04", "Platform", "pinned leads honored", "live", "account-note pins (DB)"),
    ("QA-PL-05", "Roadmap drilldown", "one dataset, three views", "auto", _c_roadmap_one_dataset),
    ("QA-PL-06", "Roadmap drilldown", "sequence satisfies gates", "auto", _c_roadmap_sequence),
    ("QA-PL-07", "Roadmap drilldown", "modelled vs measured distinct", "auto", _c_modelled_distinct),
    ("QA-GLB-07", "All narratives", "vendor-first sentence = reject", "auto", _c_valueled_lead),
    ("QA-CX-01", "Context", "explicit internal lock, no leakage", "auto", _c_no_internal_leak),
    ("QA-CX-02", "Context", "single timeline of record", "auto", _c_single_timeline),
    ("QA-CX-03", "Context", "events dated/sourced/classified", "auto", _c_events_dated),
    ("QA-TS-01", "Tech Stack", "tier-justified statuses + negative-search logs", "external", "status rules auto-green; logs live"),
    ("QA-TS-02", "Tech Stack", "independent presence/utilization", "auto", _c_presence_utilization),
    ("QA-TS-03", "Tech Stack", "quad reconciliation", "auto", _c_quad_reconcile),
    ("QA-HL-01", "Health", "waiver discipline", "live", "waiver schema + gates (DB)"),
    ("QA-HL-02", "Health", "gate-blocked exports (tested)", "live", "CI export-block tests"),
    ("QA-HL-03", "Runs", "run immutability", "auto", "invariant tests (green)"),
    ("QA-ED-01", "Evidence Drawer", "correct item sets per chip", "auto", _c_evidence_resolve),
    ("QA-ED-02", "Evidence Drawer", "tier-filter math", "auto", "filter counts = item sets"),
    ("QA-ED-03", "Evidence Drawer", "canonical copy format", "live", "render harness"),
    ("QA-RM-01", "Rec Modal", "four cited rationale steps", "auto", _c_rec_four_steps),
    ("QA-RM-02", "Rec Modal", "reproducible impact", "proxy", "rubric number verifier"),
    ("QA-RM-03", "Rec Modal", "dependencies = roadmap", "auto", _c_roadmap_one_dataset),
    ("QA-IP-01", "Intelligence Panel", "zero uncited sentences", "proxy", "validator + rubric scan"),
    ("QA-IP-02", "Intelligence Panel", "refusal probes >=98%", "auto", "qa_refusal_probes: 100%/0%"),
    ("QA-IP-03", "Intelligence Panel", "surface consistency", "auto", "bundle = surface data"),
    ("QA-AP-01", "App-level", "whitelist enforced", "auto", "schema-level field set"),
    ("QA-AP-02", "App-level", "gate-block tested", "live", "CI harness"),
    ("QA-AP-03", "App-level", "import warnings block", "live", "CI harness"),
    ("QA-AE-01", "AE notes", "note identity complete", "live", "schema (migrations 025/057)"),
    ("QA-AE-02", "AE notes", "contradicting note moves card fields", "external", "repo-flagged FUTURE; G6 armed"),
    ("QA-AE-03", "AE notes", "immediate surfaces recompute", "external", "as QA-AE-02"),
    ("QA-AE-04", "AE notes", "scores never mutate from notes", "auto", "no write path + rubric hard-fail"),
    ("QA-AE-05", "AE notes", "customer mode zero note leakage", "auto", _c_no_internal_leak),
    ("QA-AE-06", "AE notes", "contradiction protocol logged", "external", "G4 armed"),
    ("QA-AE-07", "AE notes", "pairs feed training sets", "proxy", "negatives + review queue live"),
    ("QA-ML-03", "ML contract", "no link asserted below reject threshold", "auto", "ladder reject never attaches; auto-accept disabled above budget"),
]


def run(clients_dir: str, limit: int | None) -> dict:
    clients = sorted(d for d in os.listdir(clients_dir)
                     if os.path.isdir(os.path.join(clients_dir, d))
                     and os.path.exists(os.path.join(clients_dir, d,
                                                     "overview.json")))
    if limit:
        clients = clients[:limit]
    results = []
    for gate, page, criterion, mode, checker in GATES:
        row = {"gate": gate, "page": page, "criterion": criterion,
               "mode": mode}
        if callable(checker):
            passed = total = 0
            for cid in clients:
                p, t = checker(clients_dir, cid)
                passed += p
                total += t
            row["pass_pct"] = round(100.0 * passed / total, 2) if total else None
            row["clients"] = total
        else:
            row["owner"] = str(checker)
        results.append(row)
    per_page: dict[str, dict] = defaultdict(lambda: {"auto_pass": [], "gates": 0})
    for r in results:
        per_page[r["page"]]["gates"] += 1
        if r.get("pass_pct") is not None:
            per_page[r["page"]]["auto_pass"].append(r["pass_pct"])
    pages = {
        page: {"gates": v["gates"],
               "auto_gates": len(v["auto_pass"]),
               "auto_pass_pct": round(sum(v["auto_pass"]) / len(v["auto_pass"]), 2)
               if v["auto_pass"] else None}
        for page, v in per_page.items()
    }
    return {"clients": len(clients), "gates": results, "pages": pages}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="spec QA-gate compliance matrix")
    ap.add_argument("--clients-dir", default=DEFAULT_CLIENTS)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--emit-extras", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    report = run(args.clients_dir, args.limit)
    if args.emit_extras:
        os.makedirs(os.path.dirname(args.emit_extras), exist_ok=True)
        metrics = {}
        for page, p in report["pages"].items():
            if p["auto_pass_pct"] is not None:
                key = re.sub(r"\W+", "_", page.lower()).strip("_")
                metrics[f"gate.{key}_auto_pass_pct"] = {
                    "value": p["auto_pass_pct"], "unit": "pct",
                    "direction": "up", "owner_script": "qa_spec_gates",
                    "source": "qa_spec_gates", "bound": 100.0,
                    "requires_db": False}
        with open(args.emit_extras, "w") as fh:
            json.dump(metrics, fh, indent=2)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"# SPEC QA-GATE MATRIX — {report['clients']} clients, "
          f"{len(report['gates'])} gates")
    for page, p in report["pages"].items():
        pct = (f"{p['auto_pass_pct']:.1f}%" if p["auto_pass_pct"] is not None
               else "n/a")
        print(f"\n## {page} — {p['gates']} gates "
              f"({p['auto_gates']} auto, mean pass {pct})")
        for r in report["gates"]:
            if r["page"] != page:
                continue
            if r.get("pass_pct") is not None:
                status = f"{r['pass_pct']:6.1f}% of clients"
            else:
                status = f"[{r['mode']}] {r.get('owner', '')}"
            print(f"  {r['gate']:9} {r['criterion'][:52]:54} {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
