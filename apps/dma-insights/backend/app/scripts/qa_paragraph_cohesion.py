"""Paragraph-cohesion sweep over every narrative surface (per client).

The gold-standard overlays read as connected consultant prose: each
sentence advances the argument, nothing is spliced in from raw analyst
notes, nothing repeats, nothing dangles. This checker makes "cohesive"
measurable with deterministic, per-paragraph defect classes:

  dup_sentence   -- the same (normalized) sentence appears twice in one
                    paragraph ("F-001 nCino CONFIRMED LIVE. F-001 nCino ...")
  fragment       -- a "sentence" with no verb-bearing shape: <=3 tokens
                    ("Unknown.", "None.") or a bare label ending in a period
  splice_debris  -- note-splice artifacts: '+.', '(:', ' = ' used as a
                    verb, doubled periods, orphaned brackets, dangling dashes
  shout_run      -- >=3 consecutive ALL-CAPS words mid-prose (raw analyst
                    emphasis, not acronyms; anchors/E-IDs are stripped first)
  disconnected   -- adjacent sentences that share ZERO significant tokens
                    AND the second opens with no connective -- the bolted-on
                    sentence class (a paragraph is a chain, not a pile)

Surfaces swept: finding W/W/SW, insight-card W/W/SW, SCQA, why-now
detail/text, focus narratives, heatmap drawer rationales, platform
opportunity/story, roadmap customer impact, issue rationales.

Usage:
    python -m app.scripts.qa_paragraph_cohesion [--clients-dir DIR]
        [--examples N] [--emit-extras BENCH_DIR] [--json]
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import sys
from collections import Counter, defaultdict

_HERE = os.path.dirname(__file__)
DEFAULT_CLIENTS = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "startup-data", "clients"))

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_EID_RE = re.compile(r"\[?\bE-(?:INT-)?\d{1,4}\b[^\]]*\]?")
_SUBCAP_RE = re.compile(r"\bP[1-4]C[\d.x]+\b")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")
_STOP = {"the", "a", "an", "and", "or", "but", "of", "in", "on", "to", "for",
         "with", "is", "are", "was", "were", "it", "its", "this", "that",
         "these", "those", "as", "at", "by", "be", "has", "have", "had",
         "from", "not", "no", "yet", "their", "they"}
_CONNECTIVES = re.compile(
    r"^(this|that|these|those|it|the result|so |because|however|against|"
    r"with |without|beyond|closing|peers?|the (peer|cohort|gap|spread|"
    r"assessment|shortfall|capability|issue register)|on the|at |"
    r"in zennify|zennify|"
    r"modernizing|prioriti|together|combined|as a result|meanwhile|"
    r"in (the|this|that)|for )", re.I)
_SPLICE_RES = [
    ("plus_period", re.compile(r"\+\s*\.")),
    ("open_colon", re.compile(r"\(\s*:")),
    ("equals_verb", re.compile(r"[a-z”\"']\s+=\s+[A-Z$\d]")),
    ("double_period", re.compile(r"\.\s*\.(?!\.)")),
    ("empty_bracket", re.compile(r"\[\s*\]|\(\s*\)")),
    ("dangling_dash", re.compile(r"[\u2014\u2013-]\s*[.;,]")),
    ("orphan_close", re.compile(r"^[^(\[]{0,80}[\)\]](?:\s|$)")),
]
_ACRONYM_OK = {
    "FDIC", "NCUA", "GLBA", "CISO", "CDO", "CMO", "CIO", "CTO", "CFO",
    "CFPB", "FFIEC", "NIST", "SIEM", "SOC", "SOAR", "API", "APIS", "CRM",
    "ERP", "LOS", "AML", "BSA", "KYC", "GRC", "ESG", "FCA", "OCC", "SBA",
    "ROI", "SLA", "SLO", "KPI", "GENAI", "AI", "ML", "BI", "RPA", "PEO",
    "AUM", "FDX", "ACH", "RTP", "CUSO", "HELOC", "IRA", "SOC2", "PDF",
    "MSC", "USDA", "REIT", "NYSE", "IPO", "LP", "GP", "RIA", "SEC",
    "FINTRAC", "FINCEN", "OSFI", "HRIS",
}


_ABBREV_END = re.compile(
    r"\b(?:e\.g|i\.e|vs|cf|approx|No|Inc|Corp|Co|Ltd|Jr|Sr|Mr|Ms|Dr|"
    r"U\.S|a\.m|p\.m)\.$")


def _sentences(text: str) -> list[str]:
    # naive [.!?]-splitting fractures "(e.g. Data lake: 1.5 vs 2.5)" into
    # two fake sentences that then read as disconnected/fragments —
    # rejoin chunks whose boundary is an abbreviation, not a full stop
    parts = [s.strip() for s in _SENT_SPLIT.split((text or "").strip())
             if len(s.strip()) > 1]
    out: list[str] = []
    for p in parts:
        if out and _ABBREV_END.search(out[-1]):
            out[-1] = f"{out[-1]} {p}"
        else:
            out.append(p)
    return out


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()[:120]


def _sig_tokens(s: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(s)
            if len(w) >= 4 and w.lower() not in _STOP}


_REFERENTIAL = re.compile(
    r"\b(it|its|itself|they|their|them|both|each|this|that|these|those|"
    r"the (bank|firm|credit union|"
    r"institution|company|team|platform)|he|she)\b", re.I)


def check_paragraph(text: str, entity_name: str = "") -> list[str]:
    """Defect classes present in one paragraph (deduped class names)."""
    if not text or len(text) < 40:
        return []
    # a serialized table (tab-separated DOCX rows) is DATA the UI renders
    # as a table, not a paragraph — prose rules don't apply
    if text.count("\t") >= 3:
        return []
    # para_break: a ``\n\n`` that does NOT fall at a real sentence boundary
    # (mid-name/mid-sentence paragraph split — "EverBank, N.A.¶¶can put …").
    # Checked BEFORE the flattening _sentences pass below, whose abbreviation
    # rejoin used to HEAL exactly this defect out of the analysis
    # (2026-07-14 audit). Single definition shared with pack_quality_gate.
    if "\n\n" in text:
        from app.scripts.pack_quality_gate import para_break_defects
        if para_break_defects(text):
            flat = check_paragraph(text.replace("\n\n", " "), entity_name)
            return ["para_break", *flat]
    # substitute a placeholder (never blank): stripping "(P1C1.1.1)" to
    # "()" would self-inflict empty_bracket / fragment hits
    clean = _SUBCAP_RE.sub("REF", _EID_RE.sub("REF", text))
    out: list[str] = []
    sents = _sentences(clean)
    # dup_sentence: same normalized sentence twice (>=6 words so score
    # stubs like "Scores 2/5." can legitimately recur across fields)
    seen: Counter = Counter(_norm(s) for s in sents
                            if len(s.split()) >= 6)
    if any(n >= 2 for n in seen.values()):
        out.append("dup_sentence")
    # fragment: <=3 tokens with no digits (numbers can be honest chips)
    for s in sents:
        toks = _WORD_RE.findall(s)
        if len(toks) <= 2 and not any(ch.isdigit() for ch in s) \
                and len(s) <= 24:
            out.append("fragment")
            break
    for name, rx in _SPLICE_RES:
        m = rx.search(clean)
        if not m:
            continue
        # '=' inside an additive chain ("865 Conventional + 143 HELOC +
        # other = 1,008+") is arithmetic notation, not a name-shorthand
        # splice — a digit shortly before the '=' marks the equation
        if name == "equals_verb" and re.search(
                r"\d", clean[max(0, m.start() - 24):m.start()]):
            continue
        out.append(f"splice:{name}")
        break
    # shout_run: >=3 consecutive ALL-CAPS words (>=4 chars, not acronyms),
    # at least one of them >=7 chars — a run of short tokens (TILA RESPA
    # ECOA FCRA, cert lists, vendor modules) is domain initialisms, not
    # shouting. Verbatim quoted spans are exempt — a quotation is cited
    # source material (job postings, page titles), allowed to shout; the
    # rule polices the COMPOSED prose around it. Excerpt quotes run long
    # and the composer clips some closing quotes, so the exemption covers
    # long spans and an unclosed trailing quote. E-ID citation chips of
    # every family read as tokens, not words.
    unquoted = re.sub(r'"[^"\n]{0,600}(?:"|$)', " ", clean)
    unquoted = re.sub(r"\bE-[A-Z0-9]{1,6}(?:-[A-Z0-9]{1,6})?\b", "REF",
                      unquoted)
    caps_run: list[str] = []
    for w in re.findall(r"[A-Za-z][\w/&-]*", unquoted):
        if w.isupper() and len(w) >= 4 and w.upper() not in _ACRONYM_OK:
            caps_run.append(w)
            if len(caps_run) >= 3 and any(len(x) >= 7 for x in caps_run):
                out.append("shout_run")
                break
        else:
            caps_run = []
    # disconnected: adjacent sentences, zero shared significant tokens,
    # no connective opener on the second (>=8 words each so chips and
    # citations don't trip it)
    name_toks = {t.lower() for t in _WORD_RE.findall(entity_name or "")
                 if len(t) >= 3}
    for a, b in itertools.pairwise(sents):
        if len(a.split()) < 8 or len(b.split()) < 8:
            continue
        if _sig_tokens(a) & _sig_tokens(b):
            continue
        if _CONNECTIVES.match(b.strip()):
            continue
        # referential cohesion (Halliday & Hasan): a pronoun or the
        # entity's own name anywhere in the sentence ties it back —
        # "An 8.9% growth rate ... give IT the balance sheet" is
        # connected prose, not a bolted-on note
        if _REFERENTIAL.search(b) or (
                name_toks and name_toks & {w.lower()
                                           for w in _WORD_RE.findall(b)}):
            continue
        out.append("disconnected")
        break
    return list(dict.fromkeys(out))


def _load(cdir: str, fname: str):
    p = os.path.join(cdir, fname)
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _iter_paragraphs(cdir: str):
    """(surface, label, text) for every narrative paragraph of one client."""
    ov = _load(cdir, "overview.json") or {}
    for tf in ov.get("top_findings") or []:
        if isinstance(tf, dict):
            for f in ("what", "why", "so_what"):
                yield "finding", f"{tf.get('name') or ''}:{f}", tf.get(f)
    # SCQA + overview narrative sections live under narrative.*_md
    nar = ov.get("narrative") or {}
    if isinstance(nar, dict):
        for k in ("scqa_md", "benchmark_md", "gap_prioritization_md"):
            if isinstance(nar.get(k), str):
                yield "scqa", k, nar[k]
    for sig in ov.get("why_now_signals") or []:
        if isinstance(sig, dict):
            yield "why_now", sig.get("label") or "", sig.get("detail")
    ins = _load(cdir, "insights.json") or {}
    for it in ins.get("items") or []:
        for f in ("what_text", "why_text", "so_what_text"):
            yield "insight_card", f"{it.get('title') or ''}:{f}", it.get(f)
    # focus prose lives in the KPI rationales
    fa = _load(cdir, "focus_areas.json") or {}
    for a in fa.get("items") or fa.get("focus_areas") or []:
        if isinstance(a, dict):
            for kpi in a.get("kpis") or []:
                if isinstance(kpi, dict) and isinstance(kpi.get("rationale"), str):
                    yield ("focus", f"{a.get('title') or ''}:"
                           f"{kpi.get('label') or ''}", kpi["rationale"])
    # drawer synthesis: heatmap narrative.per_subcap_md (the same source
    # the rubric's subcap_drilldown family grades)
    hm = _load(cdir, "heatmap.json") or {}
    for sid, md in ((hm.get("narrative") or {}).get("per_subcap_md")
                    or {}).items():
        if isinstance(md, str):
            yield "drawer", sid, md
    pl = _load(cdir, "platforms.json") or {}
    for c in pl.get("cards") or []:
        for f in ("opportunity_md", "story_md"):
            yield "platform", f"{c.get('platform_id') or ''}:{f}", c.get(f)
    cx = _load(cdir, "context.json") or {}
    for ir in cx.get("issue_register") or []:
        if isinstance(ir, dict) and ir.get("rationale"):
            yield "issue", ir.get("title") or "", ir.get("rationale")


def run(clients_dir: str, examples: int) -> dict:
    per_surface: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    n_paras: Counter = Counter()
    ex: dict[str, list[str]] = defaultdict(list)
    for cid in sorted(os.listdir(clients_dir)):
        cdir = os.path.join(clients_dir, cid)
        if not os.path.isdir(cdir):
            continue
        ename = (((_load(cdir, "overview.json") or {}).get("entity")
                  or {}).get("name")) or ""
        for surface, label, text in _iter_paragraphs(cdir):
            if not isinstance(text, str) or len(text) < 40:
                continue
            n_paras[surface] += 1
            for d in check_paragraph(text, ename):
                per_surface[surface][d] += 1
                totals[d] += 1
                if len(ex[d]) < examples:
                    ex[d].append(f"{cid}/{surface} {label[:40]!r}: "
                                 f"{text[:110]!r}")
    return {"per_surface": {k: dict(v) for k, v in per_surface.items()},
            "paragraphs": dict(n_paras), "totals": dict(totals),
            "examples": dict(ex)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="paragraph cohesion sweep")
    ap.add_argument("--clients-dir", default=DEFAULT_CLIENTS)
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--emit-extras", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = run(args.clients_dir, args.examples)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print("# PARAGRAPH COHESION SWEEP")
        for surf in sorted(rep["paragraphs"]):
            n = rep["paragraphs"][surf]
            defs = rep["per_surface"].get(surf, {})
            bad = sum(defs.values())
            print(f"  {surf:14s} paragraphs={n:5d} defects={bad:4d} {defs}")
        print(f"  TOTALS: {rep['totals']}")
        for d, rows in rep["examples"].items():
            print(f"  -- {d}:")
            for r in rows:
                print(f"     {r}")
    if args.emit_extras:
        path = os.path.join(args.emit_extras, "raw", "extras", "cohesion.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        base = {"unit": "count", "direction": "down", "bound": 0.0,
                "owner_script": "deepen_narrative",
                "source": "qa_paragraph_cohesion", "requires_db": False}
        with open(path, "w") as fh:
            json.dump({f"cohesion.{k}": {"value": float(v), **base}
                       for k, v in rep["totals"].items()}, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
