"""Pack quality gate — scans the EXPORTED startup-data pack (what production
actually serves) for the content-quality defects tracked by the 2026-07-08
live-QA remediation plan (segments S1-S14).

Why this exists (the validation-gap the user kept hitting): the qa-gates
self-healing audit runs against a step-10 *re-derived* DB, not the step-3
*exported* pack. Content that violated intent could therefore pass a green
build. This gate closes the loop by asserting on the committed
``startup-data/clients/*`` JSON — the same bytes ``snapshotOrApi`` serves.

Two modes:
  --audit  : print the per-segment violation counts + a few examples; exit 0.
  (default): gate mode — exit 12 if any *enforced* segment exceeds its ceiling.

Each check is a pure function over the loaded pack; no DB, no heavy deps
(``json`` + ``re`` + ``glob`` only) so it runs identically in CI and locally.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

# ---------------------------------------------------------------------------
# Detection regexes. Kept in ONE place so the gate and the fixes agree on what
# "clean" means. Citation-protected: bracketed "[E-059, E-079]" and paren
# "(E-002, AM Best, T1)" grounding is stripped BEFORE the jargon scan (mirrors
# text_hygiene.plain), so a legitimate E-P#C#-### id is never mis-flagged.
# ---------------------------------------------------------------------------
_CITE_RE = re.compile(
    r"\[[^\[\]]*\b(?:EV|INT|E)-[A-Za-z0-9][^\[\]]*\]"
    r"|\([^()]*\b(?:EV|INT|E)-\d[^()]*\)"
)

# S1 — raw taxonomy codes / internal jargon that must never reach a stakeholder.
_JARGON_RES: list[tuple[str, re.Pattern[str]]] = [
    ("subcap_code", re.compile(r"(?:^|[^-A-Za-z0-9])P[1-4]C\d")),
    ("urf_code", re.compile(r"\bURF-\d+-\d+", re.I)),
    ("f_code", re.compile(r"(?:^|[^-A-Za-z0-9])F-\d{2,}\b")),
    ("maturity_band", re.compile(r"(?:^|[^-A-Za-z0-9])M[1-5]\b(?!-\d)")),  # M1-360 = product name, not a band
    ("rec_req_id", re.compile(r"\b(?:REC|REQ)-\d+\b")),
    ("recommended_move", re.compile(r"\bRecommended (?:move|play):", re.I)),
    ("targets_n_caps", re.compile(r"\btargets?\s+\d+\s+capabilit", re.I)),
    ("consultant_speak", re.compile(
        r"peer[- ]cohort|priority lever|cross[- ]pillar|\bthe pillar\b|\bsub-?cap")),
    ("severity_tail", re.compile(r"[\u2014\u2013-]\s*(?:CRITICAL|HIGH|MEDIUM)\b")),
]

# S2 — accusatory / deficit framing (gaps must read as opportunities).
_ACCUS_RES: list[tuple[str, re.Pattern[str]]] = [
    ("no_x_lead", re.compile(r"(?:^|[.;:]\s|\|\s*)No\s+[A-Z]")),
    ("deficit_word", re.compile(r"\b(lacks?|lacking|absent|missing|weak|immature|nascent)\b", re.I)),
    ("fails_to", re.compile(r"\bfails?\s+to\b|\bdoes\s+not\b|\bcannot\b", re.I)),
    ("none_tail", re.compile(r"[\u2014\u2013-]\s*NONE\b|\bNONE\s+Identified\b")),
]

# LOB-family leaf suffixes (Insurance Carrier / Brokerage etc.) — a card
# anchored on one of these is the S5 mis-anchor defect on a non-insurance entity.
_LOB_LEAF_RE = re.compile(r"\.(?:IC|IB|WM|CB|RB|CU|PB)\d+$")

NARRATIVE_MIN = 160  # S3 top-finding body depth floor

# S15 — exec-summary (narrative.scqa_md) structural prose defects
# (2026-07-14 audit: the highest-visibility surface was entirely unscanned).
# A register-severity parenthetical welded into prose:
_SEV_PAREN_RE = re.compile(r"\(\s*(?:critical|high|medium|low)\s+severity\s*\)", re.I)
# Abbreviations that end with a period but are NOT sentence ends — a
# paragraph break right after one is a mid-name/mid-sentence split
# (mirrors nlp.segment._ABBREVIATIONS; kept local so the gate stays
# dependency-free per its module contract).
_ABBREV_BEFORE_BREAK_RE = re.compile(
    r"\b(?:inc|corp|co|ltd|llc|n\.a|u\.s|e\.g|i\.e|etc|vs|dr|mr|mrs|ms|"
    r"jr|sr|st|no|dept|approx)\.$", re.I)


def para_break_defects(md: str) -> list[str]:
    """Paragraph breaks (``\\n\\n``) that do NOT fall at a real sentence
    boundary: the left side must end in sentence-final punctuation that is
    not an abbreviation period, and the right side must not open
    lowercase. Pure and citation-tolerant (closing brackets/quotes/markdown
    after the period are fine)."""
    out: list[str] = []
    paras = (md or "").split("\n\n")
    for i in range(len(paras) - 1):
        left = paras[i].rstrip()
        right = paras[i + 1].lstrip()
        if not left or not right:
            continue
        tail = re.sub(r"[)\]\"'”’*_]+$", "", left).rstrip()  # noqa: RUF001
        if not re.search(r"[.!?:]$", tail):
            out.append(f"break after non-sentence-end {left[-45:]!r}")
        elif _ABBREV_BEFORE_BREAK_RE.search(tail):
            out.append(f"break after abbreviation {left[-45:]!r}")
        elif right[:1].islower():
            out.append(f"paragraph opens lowercase {right[:45]!r}")
    return out


# S16 — headline / label hygiene (2026-07-14, W6 follow-through). A tile
# HEADLINE (why_now label, finding name, insight title) must read as a
# complete, AE-scannable phrase: never clipped mid-thought (a dangling
# connective, or a source-title ingest ellipsis "… by…"), and never a raw
# score recital ("1.6/5", "vs a 2.8 peer") — the score belongs in the stat
# chip, the headline in words. The W6 pass drove both to 0 across all 94
# clients; this gate keeps them there. Distinct from the paragraph-cohesion
# sweep, which grades prose BODIES (>=40 chars) and never sees the labels.
# Case-SENSITIVE on the connective (a genuine mid-sentence clip ends on a
# LOWERCASE connective — "… went live on"; a Title-Case headline ending
# "… Lock-In" / "… Opt-In" is a whole word, not a dangle). The lookbehind
# also rejects a hyphenated word ("Lock-In") and any word-internal match.
_HEADLINE_DANGLE_RE = re.compile(
    r"(?<![.\w-])(?:and|or|at|vs|of|the|to|for|an|in|on|with|by|from|as|"
    r"is|are|was|were|that|which|its|it)\s*$|\.\.\.|…")
_HEADLINE_SCORE_RE = re.compile(
    r"\d(?:\.\d)?\s*/\s*5|\bvs\b[^,]*\bpeer\b|\bpeer median\b", re.I)


def headline_defects(label: object) -> list[str]:
    """Defect classes in one rendered headline/label (empty when clean):
    ``mid_thought`` (dangling connective / ellipsis clip) and
    ``score_quoting`` (a score recital that belongs in the stat chip)."""
    s = str(label or "").strip()
    if len(s) < 6:
        return []
    out: list[str] = []
    if _HEADLINE_DANGLE_RE.search(s):
        out.append("mid_thought")
    if _HEADLINE_SCORE_RE.search(s):
        out.append("score_quoting")
    return out


def _strip_cites(s: str) -> str:
    return _CITE_RE.sub(" ", s or "")


def _load(client_dir: str, fname: str):
    p = os.path.join(client_dir, fname)
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _jargon_hits(text: str) -> list[str]:
    clean = _strip_cites(text or "")
    return [name for name, rx in _JARGON_RES if rx.search(clean)]


def _accus_hits(text: str) -> list[str]:
    return [name for name, rx in _ACCUS_RES if rx.search(text or "")]


# ---------------------------------------------------------------------------
# Per-client scan → dict of segment -> list[detail strings]
# ---------------------------------------------------------------------------
def scan_client(cdir: str) -> dict[str, list[str]]:
    cid = os.path.basename(cdir)
    out: dict[str, list[str]] = {}

    def add(seg: str, detail: str) -> None:
        out.setdefault(seg, []).append(f"{cid}: {detail}")

    insights = _load(cdir, "insights.json") or {}
    for it in insights.get("items", []) or []:
        for f in ("what_text", "why_text", "so_what_text", "title"):
            hits = _jargon_hits(str(it.get(f) or ""))
            if hits:
                add("S1_jargon", f"insight.{f} [{','.join(hits)}] {str(it.get(f))[:70]!r}")
            if _accus_hits(str(it.get(f) or "")):
                add("S2_accusatory", f"insight.{f} {str(it.get(f))[:70]!r}")
        anchor = str(it.get("linked_subcap_id") or "")
        if _LOB_LEAF_RE.search(anchor) and "insurance" not in cid:
            add("S5_lob_anchor", f"insight {it.get('ic_id')} anchor={anchor}")

    ov = _load(cdir, "overview.json") or {}
    for tf in ov.get("top_findings", []) or []:
        body = str(tf.get("body") or "")
        if len(body) < NARRATIVE_MIN:
            add("S3_thin", f"finding {str(tf.get('name'))[:40]!r} body={len(body)}c")
        if "[E-" not in body and "[EV-" not in body and not (tf.get("evidence")):
            add("S3_no_cite", f"finding {str(tf.get('name'))[:40]!r}")
        if _accus_hits(body):
            add("S3_accusatory", f"finding {body[:70]!r}")
        if _jargon_hits(body):
            add("S1_jargon", f"finding.body {body[:60]!r}")

    # S15 — exec summary (narrative.scqa_md): the page's highest-visibility
    # prose. Structural defects (mid-sentence paragraph breaks, welded
    # register-severity labels) + the standard jargon/accusatory scans.
    nar = ov.get("narrative") or {}
    scqa = str(nar.get("scqa_md") or "")
    if scqa:
        for d in para_break_defects(scqa):
            add("S15_para_break_mid_sentence", d)
        for m in _SEV_PAREN_RE.finditer(scqa):
            ctx15 = scqa[max(0, m.start() - 40):m.end()]
            add("S15_severity_label", f"{ctx15!r}")
        hits = _jargon_hits(scqa)
        if hits:
            add("S1_jargon", f"narrative.scqa_md [{','.join(hits)}] {scqa[:60]!r}")

    # S16 — headline / label hygiene across the AE-visible tile headlines
    # (why_now labels, finding names, insight titles). These render as the
    # scannable one-liner on each card and are checked by NO other segment.
    for sig in (ov.get("why_now") or ov.get("why_now_signals") or []):
        if isinstance(sig, dict):
            for d in headline_defects(sig.get("label")):
                add(f"S16_headline_{d}",
                    f"why_now.label {str(sig.get('label'))[:60]!r}")
    for tf in ov.get("top_findings", []) or []:
        if isinstance(tf, dict):
            for d in headline_defects(tf.get("name")):
                add(f"S16_headline_{d}",
                    f"finding.name {str(tf.get('name'))[:60]!r}")
    for it in insights.get("items", []) or []:
        if isinstance(it, dict):
            for d in headline_defects(it.get("title")):
                add(f"S16_headline_{d}",
                    f"insight.title {str(it.get('title'))[:60]!r}")

    # S6 — financial trajectory series depth (among disclosers)
    ft = ov.get("financial_trajectory")
    if isinstance(ft, dict):
        headline = ft.get("headline")
        highlights = ft.get("highlights") or []
        discloses = bool(headline or highlights or ft.get("cagr") or ft.get("series"))
        series = ft.get("series") or {}
        pts = []
        for v in series.values():
            if isinstance(v, list):
                pts.append([x for x in v if x is not None])
        max_pts = max((len(p) for p in pts), default=0)
        distinct = max((len(set(p)) for p in pts), default=0)
        if discloses and (max_pts < 3 or distinct < 2):
            add("S6_financials", f"series max_pts={max_pts} distinct={distinct} headline={str(headline)[:40]!r}")

    # S7 — firmographics per-field dashes (applicable-but-empty)
    fm = ov.get("firmographics") or {}
    for f in ("hq", "hq_address", "founded", "branches", "revenue_usd"):
        if f in fm and (fm.get(f) in (None, "", "—", "N/A")):
            add(f"S7_firmo_{f}", f"{f} empty")

    # S8 — sentiment displayed lines
    sent = ov.get("sentiment") or {}
    lines = 0
    for k in ("qualitative", "customer", "employee"):
        v = sent.get(k)
        if isinstance(v, list):
            lines += len([x for x in v if x])
    if lines <= 1:
        add("S8_sentiment_thin", f"displayed_lines={lines}")

    # S9 — focus-area validity + KPI completeness
    fa = _load(cdir, "focus_areas.json") or {}
    for it in fa.get("items", []) or []:
        title = str(it.get("title") or "")
        if re.match(r"^(No |Not |\[MATURITY|F-\d)", title):
            add("S9_focus_invalid", f"title={title[:60]!r}")
        for kpi in it.get("kpis", []) or []:
            if not (kpi.get("target") not in (None, "") and kpi.get("rationale")):
                add("S9_kpi_incomplete", f"kpi {str(kpi.get('label'))[:30]!r}")
                break

    # S13 — platform cards lead with score/subcap, not opportunity
    plat = _load(cdir, "platforms.json") or {}
    for c in plat.get("cards", []) or []:
        for f in ("opportunity_md", "story_md"):
            txt = str(c.get(f) or "")
            lead = _strip_cites(txt)[:120]
            if re.search(r"\d+/100 fit|scores?\s+\d(?:\.\d)?/5|\d+\s+scored capability gaps|(?:^|[^-A-Za-z0-9])P[1-4]C\d", lead):
                add("S13_platform_score_lead", f"{f} {lead[:70]!r}")
                break

    # S17 — exec-summary platform-fit number must match the platform tab
    # (quality ratchet, 2026-07-15). Our composer renders a synthetic clause
    # ("… ranks first (N/100 fit)…"); a KEPT summary froze that N after the fit
    # engine changed, so a stale exec summary cited a fit the platform tab no
    # longer showed (Sunflower shipped "22/100" when the corrected lead was 52).
    # The composer now recomposes an offside clause; this gate hard-fails a
    # deploy whose exec-summary fit still disagrees with the rank-1 card.
    if scqa:
        _fit_cards = [c for c in (plat.get("cards") or [])
                      if isinstance(c, dict) and c.get("fit_score") is not None]
        _m_fit = re.search(r"\((\d+)\s*/\s*100\s*fit\)", scqa)
        if _fit_cards and _m_fit:
            _lead = min(_fit_cards, key=lambda c: (
                c.get("sequence_rank") if c.get("sequence_rank") is not None else 99,
                -float(c.get("fit_score") or 0.0)))
            try:
                _lead_fit = round(float(_lead.get("fit_score")))
            except (TypeError, ValueError):
                _lead_fit = None
            if _lead_fit is not None and abs(int(_m_fit.group(1)) - _lead_fit) > 1:
                add("S17_exec_fit_stale",
                    f"scqa cites {_m_fit.group(1)}/100, lead card {_lead_fit}/100")

    # S14 — issue register: real issues, headlines, rationale
    ctx = _load(cdir, "context.json") or {}
    for ir in ctx.get("issue_register", []) or []:
        title = str(ir.get("title") or "")
        if title.startswith("Capability gap:"):
            add("S14_capability_gap_title", f"{title[:60]!r}")
        if not ir.get("rationale"):
            add("S14_blank_rationale", f"{title[:40]!r}")
        if _accus_hits(title) or re.search(r"[\u2014\u2013-]\s*NONE", title):
            add("S14_accusatory_title", f"{title[:60]!r}")
        if _jargon_hits(title):
            add("S14_jargon_title", f"{title[:60]!r}")

    # S11 — Regions rename residue anywhere in this client's pack text
    if "regions" in cid:
        for fname in ("overview.json", "context.json", "insights.json"):
            raw = None
            p = os.path.join(cdir, fname)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    raw = fh.read()
            if raw and "regions-business-bank" in raw.lower():
                add("S11_regions_slug", f"{fname} contains regions-business-bank")
            if raw and "Regions Business Bank" in raw:
                add("S11_regions_name", f"{fname} contains 'Regions Business Bank'")

    return out


# Segments enforced as a HARD gate in WAVE 1 (build fails if > ceiling).
# Narrative-quality segments (S2/S3 depth, S13) are REPORTED in WAVE 1 and
# enforced after WAVE 2 lands the refinement overlay.
ENFORCED_CEILINGS: dict[str, int] = {
    "S1_jargon": 0,
    "S5_lob_anchor": 0,
    "S11_regions_slug": 0,
    "S11_regions_name": 0,
    "S14_capability_gap_title": 0,
    "S14_jargon_title": 0,
    "S15_para_break_mid_sentence": 0,
    "S15_severity_label": 0,
    "S16_headline_mid_thought": 0,
    "S16_headline_score_quoting": 0,
    "S17_exec_fit_stale": 0,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=None, help="startup-data dir (default: repo)")
    ap.add_argument("--audit", action="store_true", help="report only; never fail")
    ap.add_argument("--examples", type=int, default=3)
    args = ap.parse_args()

    pack = args.pack
    if pack is None:
        here = os.path.dirname(os.path.abspath(__file__))
        pack = os.path.normpath(os.path.join(here, "../../../startup-data"))
    clients_dir = os.path.join(pack, "clients")
    client_dirs = sorted(d for d in glob.glob(os.path.join(clients_dir, "*"))
                         if os.path.isdir(d))

    totals: dict[str, list[str]] = {}
    n_clients_with: dict[str, set[str]] = {}
    for cdir in client_dirs:
        res = scan_client(cdir)
        for seg, details in res.items():
            totals.setdefault(seg, []).extend(details)
            n_clients_with.setdefault(seg, set()).add(os.path.basename(cdir))

    print(f"=== PACK QUALITY GATE — {len(client_dirs)} clients — pack={pack} ===")
    print(f"{'segment':<28}{'violations':>11}{'clients':>9}   examples")
    failed: list[str] = []
    for seg in sorted(totals):
        details = totals[seg]
        nclients = len(n_clients_with.get(seg, set()))
        ceil = ENFORCED_CEILINGS.get(seg)
        flag = ""
        if ceil is not None and len(details) > ceil:
            flag = f"  <== ENFORCED FAIL (ceil {ceil})"
            failed.append(seg)
        ex = "; ".join(d.split(": ", 1)[-1][:48] for d in details[:args.examples])
        print(f"{seg:<28}{len(details):>11}{nclients:>9}   {ex[:90]}{flag}")

    if not totals:
        print("(no violations detected)")

    if args.audit:
        print("\n[audit mode] exit 0")
        return 0
    if failed:
        print(f"\n::error::pack_quality_gate FAILED — enforced segments over ceiling: {failed}")
        return 12
    print("\npack_quality_gate PASS (all enforced segments within ceiling)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
