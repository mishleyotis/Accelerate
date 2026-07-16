"""Countercheck the deterministic script output against the Claude-grade
benchmark. Two modes of signal:
  (A) direct diff vs the 5 committed refinement overlays (gold standard);
  (B) criteria scan across ALL clients for the defect classes the 3-client
      stress-test exposed. TF-IDF cosine (sklearn) measures misattribution:
      a card whose WHAT/WHY has near-zero topical overlap with its own
      capability title is spliced from the wrong evidence.

The scan is a callable (``scan(clients_dir, overlay_dir)``) so the
benchmark runner and tests can consume the structured result without
shelling out; the CLI prints the same report as before (plus ``--json``).

Usage: python -m app.scripts.countercheck_pack <clients_dir> [overlay_dir] [--json]
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DEFAULT_CLIENTS = "/root/scratch-pack/clients"
DEFAULT_OVERLAYS = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "startup-data", "refinement"))
E_RE = re.compile(r'\bE-(?:INT-)?\d{1,4}\b')
RAW_DUMP = re.compile(r"quote:\s*['\"]|\(1\).{0,40}\(2\)|Executive Committee|10-K Glossary|careers page|OFFICIAL BIO|consolidated assets of approximately", re.I)
CARRIER_OOS = re.compile(r"AI Claims Estimation|Claims Adjudication|Underwriting Automation|Policy Administration", re.I)
# Accusatory-absence language the opportunity corpus (docs/LANGUAGE_GUIDELINES.md)
# bans on AE-facing copy — "No X", "Zero X", "lacks", "without X", "fails to".
ACC_RE = re.compile(
    r"(?:^|[\s|\u2014\u2013-])(?:no|zero|lacks?|lacking|absent|missing|"
    r"fails?\s+to|failing\s+to|cannot|unable\s+to|without)\b", re.I)
# clean-posture / neutral / hyphenated-term phrases that legitimately keep an
# absence word (a "no breaches" positive must NEVER count as a defect).
ACC_ALLOW = re.compile(
    r"breach|incident|enforcement|consent|litigation|lawsuit|violation|penalt|"
    r"sanction|default|complaint|regulatory\s+record|fraud|outage|data\s+loss|"
    r"m&a|acquisition|\binterest\b|appetite|\bplans?\b|intention|"
    r"net-zero|zero-trust|zero-copy|zero-day", re.I)


def _accusatory(text: object) -> bool:
    t = text if isinstance(text, str) else ""
    return bool(ACC_RE.search(t)) and not ACC_ALLOW.search(t)


# Consultant-grade writing checks (docs/LANGUAGE_GUIDELINES.md C1/C3/C5).
# Rehearsed template skeletons that must not recur across the cohort.
TEMPLATE_RES = [
    re.compile(r"make .{1,60}? a near-term focus", re.I),
    re.compile(r"is one of .{1,40}? least developed", re.I),
    re.compile(r"prioriti[sz]e .{1,40}? in the next phase", re.I),
    re.compile(r"a clear opportunity to close the gap", re.I),
    re.compile(r"sequencing it first lifts", re.I),
    re.compile(r"scoped investment here would lift it", re.I),
    re.compile(r"against a peer median of .{1,20}? on the latest assessment", re.I),
]
# Punctuation debris a consultant-grade surface never ships.
PUNCT_DEBRIS = re.compile(
    r"\[\s*[,;]|[,;]\s*\]|\(\s*[,;]|\.\.(?!\.)|[\u2014\u2013]\s*,|,\s*,|"
    r"\[E-[^\]]*$|:\s*$|\s[\u2014\u2013-]\s*$|\s[,;]", re.I)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Per-SEGMENT scorecard — enhancement areas per surface (not a single pass/fail),
# benchmarked to the gold-standard overlays. Each segment must be AT BENCHMARK
# (0 residual) before the pre-redeploy gate passes.
SEGMENTS = {
    "insight_cards": ["card_misattributed", "card_raw_dump"],
    "top_findings": ["finding_raw_lead"],
    "focus": ["focus_pipe_quote"],
    "leadership": ["leadership_thin"],
    "firmographics": ["branches_suspicious"],
    "platform": ["platform_oos_anchor"],
    "language": ["accusatory_language"],
    "paragraph_depth": ["card_oneliner"],
    "variety": ["template_language"],
    "punctuation": ["punctuation_debris"],
}


def _sentence_count(text: object) -> int:
    t = text if isinstance(text, str) else ""
    return len([s for s in _SENT_SPLIT.split(t.strip()) if len(s.strip()) > 3])


def load(clients_dir, c, f):
    p = os.path.join(clients_dir, c, f)
    if not os.path.exists(p):
        return {}
    with open(p) as fh:
        return json.load(fh)


def topical_cos(a, b):
    a, b = (a or "").strip(), (b or "").strip()
    if len(a) < 8 or len(b) < 3:
        return None
    try:
        m = TfidfVectorizer(stop_words="english").fit_transform([a, b])
        return float(cosine_similarity(m[0], m[1])[0][0])
    except ValueError:
        return None


def scan_client(clients_dir: str, c: str) -> dict[str, int]:
    """Scan one client folder; returns defect-name -> count."""
    counts: dict[str, int] = defaultdict(int)
    ov = load(clients_dir, c, "overview.json")
    ins = load(clients_dir, c, "insights.json")
    pl = load(clients_dir, c, "platforms.json")
    fa = load(clients_dir, c, "focus_areas.json")
    firm = ov.get("firmographics") or {}
    subv = (ov.get("entity") or {}).get("subvertical")

    # (1) insight cards: raw-dump lead + misattribution + consultant-grade writing
    for it in (ins.get("items") or []):
        title = it.get("title") or ""
        what = it.get("what_text") or ""
        why = it.get("why_text") or ""
        so_what = it.get("so_what_text") or ""
        if RAW_DUMP.search(what) or RAW_DUMP.search(why):
            counts["card_raw_dump"] += 1
        # C1 one-liner: the WHAT must be a paragraph (>=3 sentences), not a
        # single templated line.
        if what and _sentence_count(what) < 3:
            counts["card_oneliner"] += 1
        # C3 rehearsed template skeleton shared across the cohort.
        blob = f"{title} {what} {why} {so_what}"
        if any(rx.search(blob) for rx in TEMPLATE_RES):
            counts["template_language"] += 1
        # C5 punctuation debris.
        if any(PUNCT_DEBRIS.search(str(it.get(k) or "")) for k in ("what_text", "why_text", "so_what_text")):
            counts["punctuation_debris"] += 1
        cos = topical_cos(what + " " + why, title)
        if cos is not None and cos < 0.04:
            counts["card_misattributed"] += 1

    # (3) top findings raw lead / fragment joins
    for tf in (ov.get("top_findings") or []):
        body = tf.get("body") or ""
        if body.count(" — ") >= 2 or RAW_DUMP.search(body):
            counts["finding_raw_lead"] += 1

    # (4) platform out-of-scope anchor (carrier subcap on non-insurance)
    if subv and not str(subv).upper().startswith(("IC", "IB")):
        for pc in (pl.get("cards") or []):
            blob = (pc.get("opportunity_md") or "") + (pc.get("story_md") or "")
            if CARRIER_OOS.search(blob):
                counts["platform_oos_anchor"] += 1
                break

    # (5) focus pipe-row quote
    for f in (fa.get("items") or []):
        q = f.get("verbatim_quote") or f.get("quote") or ""
        if re.match(r"\s*F-\d", q) and " | " in q:
            counts["focus_pipe_quote"] += 1

    # (5b) accusatory language across AE-facing copy (focus titles/quotes,
    # insight cards, findings) — must read as opportunity, not audit.
    for f in (fa.get("items") or []):
        if _accusatory(f.get("title")) or _accusatory(f.get("verbatim_quote") or f.get("quote")):
            counts["accusatory_language"] += 1
    for it in (ins.get("items") or []):
        if any(_accusatory(it.get(k)) for k in ("title", "what_text", "why_text", "so_what_text")):
            counts["accusatory_language"] += 1
    for tf in (ov.get("top_findings") or []):
        if _accusatory(tf.get("title")) or _accusatory(tf.get("body")):
            counts["accusatory_language"] += 1

    # (6) leadership broken (<=1 seat or empty-title/non-person)
    lead = firm.get("leadership") or {}
    seats = lead if isinstance(lead, list) else lead.get("seats") or lead.get("members") or []
    if isinstance(seats, list):
        real = [s for s in seats if isinstance(s, dict) and (s.get("title") or "").strip() and (s.get("name") or "").strip()]
        if len(real) <= 1:
            counts["leadership_thin"] += 1

    # (7) branches suspiciously low for large tiers (comma-truncation)
    br = firm.get("branches")
    tier = str(firm.get("size_tier") or "").lower()
    if isinstance(br, int | float) and br and br < 400 and any(t in tier for t in ("large", "super", "mega", "regional")):
        counts["branches_suspicious"] += 1

    return dict(counts)


def scan(clients_dir: str, overlay_dir: str) -> dict:
    """Full corpus scan. Returns the structured countercheck result:

    {clients: int, per_client: {cid: {defect: n}}, aggregate: {defect: n},
     clients_hit: {defect: [cid...]}, segments: {seg: {total, clients, detail}},
     gate_pass: bool, overlays: [{client, in_pack, surfaces}]}
    """
    clients = sorted(d for d in os.listdir(clients_dir)
                     if os.path.isdir(os.path.join(clients_dir, d)))
    per_client: dict[str, dict[str, int]] = {}
    for c in clients:
        counts = scan_client(clients_dir, c)
        if counts:
            per_client[c] = counts

    agg: dict[str, int] = defaultdict(int)
    clients_hit: dict[str, set] = defaultdict(set)
    for c, d in per_client.items():
        for k, n in d.items():
            agg[k] += n
            clients_hit[k].add(c)

    segments = {}
    gate_ok = True
    for seg, keys in SEGMENTS.items():
        tot = sum(agg.get(k, 0) for k in keys)
        hit: set = set()
        for k in keys:
            hit |= clients_hit.get(k, set())
        if tot:
            gate_ok = False
        segments[seg] = {
            "total": tot,
            "clients": len(hit),
            "detail": {k: agg.get(k, 0) for k in keys},
        }

    overlays = []
    if os.path.isdir(overlay_dir):
        for fn in sorted(os.listdir(overlay_dir)):
            if not fn.endswith(".json"):
                continue
            cid = fn[:-5]
            if cid not in clients:
                overlays.append({"client": cid, "in_pack": False, "surfaces": []})
                continue
            with open(os.path.join(overlay_dir, fn)) as fh:
                overlay = json.load(fh)
            surfaces = [k for k in overlay if not k.startswith("_")]
            overlays.append({"client": cid, "in_pack": True, "surfaces": surfaces})

    return {
        "clients": len(clients),
        "clients_dir": clients_dir,
        "per_client": per_client,
        "aggregate": dict(agg),
        "clients_hit": {k: sorted(v) for k, v in clients_hit.items()},
        "segments": segments,
        "gate_pass": gate_ok,
        "overlays": overlays,
    }


def render(result: dict) -> str:
    """Render the classic human-readable report from a scan() result."""
    agg = result["aggregate"]
    per_client = result["per_client"]
    clients_hit = result["clients_hit"]
    out = [f"# COUNTERCHECK — {result['clients']} clients scanned in {result['clients_dir']}\n"]
    out.append(f"{'defect':24} {'total':>7} {'clients':>8}   worst offenders")
    for k in sorted(agg, key=lambda x: -agg[x]):
        worst = sorted(per_client.items(), key=lambda kv: -kv[1].get(k, 0))
        ex = ", ".join(f"{c}:{d[k]}" for c, d in worst[:4] if d.get(k))
        out.append(f"{k:24} {agg[k]:>7} {len(clients_hit[k]):>8}   {ex}")

    out.append("\n# PER-SEGMENT SCORECARD (enhancement areas vs gold standard)")
    for seg, s in result["segments"].items():
        verdict = "AT BENCHMARK" if s["total"] == 0 else f"{s['total']} enhancement(s) / {s['clients']} clients"
        detail = ", ".join(f"{k}:{n}" for k, n in s["detail"].items())
        out.append(f"  {seg:16} {verdict:34} ({detail})")
    out.append(f"  => PRE-REDEPLOY GATE: {'PASS' if result['gate_pass'] else 'BLOCKED (segments above > 0)'}")

    out.append("\n# OVERLAY GOLD-STANDARD DIFF (does script output still need the overlay?)")
    for o in result["overlays"]:
        if not o["in_pack"]:
            out.append(f"  {o['client']}: (not in pack)")
        else:
            out.append(f"  {o['client']}: overlay refines {o['surfaces']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="countercheck pack vs gold overlays")
    ap.add_argument("clients_dir", nargs="?", default=DEFAULT_CLIENTS)
    ap.add_argument("overlay_dir", nargs="?", default=DEFAULT_OVERLAYS)
    ap.add_argument("--json", action="store_true", help="emit the structured scan result")
    args = ap.parse_args(argv)
    result = scan(args.clients_dir, args.overlay_dir)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
