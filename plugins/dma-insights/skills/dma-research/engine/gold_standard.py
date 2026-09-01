#!/usr/bin/env python3
"""The gold standard a client package must meet BEFORE anyone believes it.

    python3 -m engine.gold_standard workbook <scoring_workbook.xlsx>
    python3 -m engine.gold_standard report   <report.docx> [--template t.docx] [--kind research|assessment]
    python3 -m engine.gold_standard package   <client_folder> [--json]

CALIBRATED TO THE REFERENCE PACKAGE: Golden 1 Credit Union (DMA-2026-GOLDEN1-001),
named by the engagement owner as "the best gold standard so far" (2026-09-01). Every
threshold below is what that package meets, not an invention.

WHY THIS EXISTS (the goeasy-Ltd findings). The engine already had gates — `validator`
checks the RESEARCH workbook's shape, `completeness` checks tabs, `quality` measures
content. Each is real, and NONE of them is the gold standard: the reference ASSESSMENT
workbook (43 sheets, weighted rollups, an Executive_Summary dashboard, Firmographics,
Focus_Areas, an Issue_Register, a Coverage sheet that discloses evidence gaps as
"Unknown", M-band labels) FAILS the research validator's rule 2/4 outright, because it
is a different and richer artefact produced by the assessment stage, not the research
stage. goeasy shipped the 23-sheet RESEARCH workbook hand-scored in place — which is
why it lacked the dashboard, the firmographics tab, the weighted rollups and the
coverage disclosure the reference carries. THE ROOT CAUSE was skipping the assessment
stage that builds the gold-standard workbook, and then having no single gate that knew
what that workbook should contain. This is that gate.

FINDINGS -> GATES (full register: docs/goeasy-findings-register.md):
  GSY-01 unscored cells render blank        -> GS-WB-SCORES (every subcap numeric 1..5)
  GSY-02 zero / hedge in a value column     -> GS-WB-NOZERO, GS-WB-NOHEDGE
  GSY-03 blank SubCap_Name                   -> GS-WB-NAMES
  GSY-04 peer scores "Not established"       -> GS-WB-PEERS, GS-RPT-NOHEDGE
  GSY-05 report built as a blank docx        -> GS-RPT-BRANDING (branded header kept)
  GSY-06 report missing template sections    -> GS-RPT-SECTIONS
  GSY-07 leftover {{template tokens}}        -> GS-RPT-NOTOKENS
  GSY-08 shallow / thin evidence use         -> GS-RPT-CITATIONS, GS-RPT-LENGTH
  GSY-09 no AI-and-data overlay              -> GS-RPT-AIOVERLAY (assessment, per pillar)
  GSY-10 recommendations with no rebuttal    -> GS-RPT-REBUTTALS
  GSY-11 a fifth (Transformational) BAND     -> GS-RPT-BANDS  (M1..M5 the scale is fine)
  GSY-12 grains missing / duplicated         -> GS-WB-GRAINS
  GSY-13 numbers drift report<->workbook     -> GS-RPT-RECONCILE
  GSY-14 not conducive for app ingestion     -> GS-ING-*
  GSY-15 wrong artefact: RESEARCH workbook    -> GS-WB-STAGE (the 43-sheet assessment set)
         shipped where the ASSESSMENT workbook belonged
  GSY-16 coverage hidden, gaps proxied silently -> GS-WB-COVERAGE (Coverage discloses
         Scored / Unknown_EvidenceGap / Coverage_Pct; Executive_Summary headlines it)
  GSY-17 no Executive_Summary dashboard       -> GS-WB-DASHBOARD
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

# ── the verdict shape ────────────────────────────────────────────────────

class Finding(dict):
    def __init__(self, code: str, detail: str, prevents: str = "", **kw):
        super().__init__(code=code, detail=detail, prevents=prevents, **kw)

    def __str__(self):
        p = f" [{self['prevents']}]" if self.get("prevents") else ""
        return f"{self['code']}: {self['detail']}{p}"


# The literals a client-facing deliverable must never ship — every one appeared in a
# shipped goeasy draft. Matched as a standalone value or leading phrase, casefolded.
BANNED_HEDGES = (
    "not established this run", "to be established at the platform",
    "to be established at surface", "surface-production stage",
    "no score yet", "no score exists yet", "queued for enrichment",
    "tbd", "todo", "placeholder", "lorem ipsum", "coming soon",
)
# A FIFTH band is the invariant breach — not the M1..M5 maturity SCALE, which the
# reference package uses throughout ("2.25 (M2)"). Only a reachable 5th band word.
BANNED_BAND_WORDS = ("transformational",)

# The gold-standard ASSESSMENT workbook's sheet set (from the Golden 1 reference).
# A workbook missing these is a RESEARCH workbook shipped where an assessment belongs.
GOLD_SHEETS = (
    "Executive_Summary", "P1_Subcap_Scoring", "P2_Subcap_Scoring",
    "P3_Subcap_Scoring", "P4_Subcap_Scoring", "Pillar_Summary", "Category_Detail",
    "Coverage", "Peer_Benchmarks", "Firmographics", "Focus_Areas",
    "Issue_Register", "Recommendations", "Tech_Register",
)
# The dashboard's own fields — the numbers an executive reads first.
EXEC_FIELDS = ("Institution", "Sub-Vertical", "Evidence Mode", "Overall Maturity",
               "Peer Median", "Gap to Peer", "Subcaps Scored",
               "Evidence Gaps", "Headline")

WORKBOOK_EMPTY_OK = {"Source_URLs"}
SCORE_SHEETS = ("P1_Subcap_Scoring", "P2_Subcap_Scoring",
                "P3_Subcap_Scoring", "P4_Subcap_Scoring")


def _norm(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _is_hedge(text: str) -> bool:
    t = _norm(text).casefold().strip(" .()[]-—:")
    return bool(t) and any(t == b or t.startswith(b) for b in BANNED_HEDGES)


# ── WORKBOOK gate ────────────────────────────────────────────────────────

def workbook_findings(path) -> list[Finding]:
    import openpyxl
    path = Path(path)
    out: list[Finding] = []
    wb = openpyxl.load_workbook(path, data_only=True)
    have = set(wb.sheetnames)

    # GS-WB-STAGE / GS-WB-DASHBOARD — the assessment (not research) artefact.
    missing = [s for s in GOLD_SHEETS if s not in have]
    if missing:
        out.append(Finding("GS-WB-STAGE",
            f"missing gold-standard sheet(s): {missing} — this looks like a "
            f"research workbook, not the assessment package", "GSY-15/17"))

    def rows(sh):
        ws = wb[sh]; rr = list(ws.iter_rows(values_only=True))
        return (rr[0], rr[1:]) if rr else ((), [])

    # GS-WB-DASHBOARD — the Executive_Summary carries the headline numbers.
    if "Executive_Summary" in have:
        _, data = rows("Executive_Summary")
        fields = {_norm(r[0]).casefold(): _norm(r[1]) for r in data if r and r[0]}
        for f in EXEC_FIELDS:
            if not any(f.casefold() in k for k in fields):
                out.append(Finding("GS-WB-DASHBOARD",
                    f"Executive_Summary missing field ~{f!r}", "GSY-17"))

    # GS-WB-COVERAGE — evidence gaps DISCLOSED (Scored / Unknown / Coverage_Pct), not hidden.
    if "Coverage" in have:
        hdr, data = rows("Coverage")
        low = {_norm(h).casefold() for h in hdr}
        if not (any("unknown" in h for h in low) and any("coverage" in h for h in low)):
            out.append(Finding("GS-WB-COVERAGE",
                "Coverage sheet does not disclose Unknown_EvidenceGap / Coverage_Pct", "GSY-16"))

    # GS-WB-SCORES / GS-WB-NOZERO / GS-WB-NAMES — every subcap valued and named.
    for sh in SCORE_SHEETS:
        if sh not in have:
            continue
        hdr, data = rows(sh); ix = {h: i for i, h in enumerate(hdr)}
        for r in data:
            sid = r[ix.get("SubCap_ID", 0)] if hdr else None
            if not sid:
                continue
            sc = r[ix["Score"]] if "Score" in ix else None
            if not isinstance(sc, (int, float)):
                out.append(Finding("GS-WB-SCORES",
                    f"{sid}: Score not numeric ({_norm(sc)!r})", "GSY-01"))
            elif sc == 0 or not (1.0 <= sc <= 5.0):
                out.append(Finding("GS-WB-NOZERO", f"{sid}: Score {sc} outside 1..5", "GSY-02"))
            if "SubCap_Name" in ix:
                nm = r[ix["SubCap_Name"]]
                if not _norm(nm) or _is_hedge(nm) or _norm(nm).casefold() in ("n/a", "na"):
                    out.append(Finding("GS-WB-NAMES", f"{sid}: SubCap_Name blank/placeholder", "GSY-03"))

    # GS-WB-EMPTY / GS-WB-NOHEDGE — no blank or hedge in a reader-facing sheet.
    for sh in list(SCORE_SHEETS) + ["Pillar_Summary", "Category_Detail", "Coverage",
                                    "Peer_Benchmarks", "Firmographics", "Focus_Areas",
                                    "Issue_Register", "Recommendations", "Tech_Register"]:
        if sh not in have:
            continue
        hdr, data = rows(sh); ncol = len([h for h in hdr if h is not None])
        empt = hedged = 0
        for r in data:
            if not any(_norm(c) for c in r):
                continue
            for j in range(ncol):
                v = r[j]
                if (v is None or not _norm(v)) and hdr[j] not in WORKBOOK_EMPTY_OK:
                    empt += 1
                elif _is_hedge(v):
                    hedged += 1
        if empt:
            out.append(Finding("GS-WB-EMPTY", f"{sh}: {empt} empty cell(s)", "GSY-01"))
        if hedged:
            out.append(Finding("GS-WB-NOHEDGE", f"{sh}: {hedged} hedge/placeholder cell(s)", "GSY-04"))

    # GS-WB-GRAINS — pillar rollup present (4 pillars, an OVERALL is fine), categories, recs.
    if "Pillar_Summary" in have:
        _, data = rows("Pillar_Summary")
        ids = [_norm(r[0]) for r in data if r and _norm(r[0])]
        pil = {i for i in ids if re.fullmatch(r"P[1-4]", i)}
        if len(ids) != len(set(ids)):
            out.append(Finding("GS-WB-GRAINS", f"duplicate pillar rows: {ids}", "GSY-12"))
        if pil != {"P1", "P2", "P3", "P4"}:
            out.append(Finding("GS-WB-GRAINS", f"pillars not all present: {sorted(pil)}", "GSY-12"))
    # Recommendations may live in the Recommendations tab OR the Solution_Catalogue
    # (the reference carries the recs in the report §8 and the catalogue).
    rec_rows = sol_rows = 0
    if "Recommendations" in have:
        _, data = rows("Recommendations"); rec_rows = len([r for r in data if r and _norm(r[0])])
    if "Solution_Catalogue" in have:
        _, data = rows("Solution_Catalogue"); sol_rows = len([r for r in data if r and _norm(r[0])])
    if rec_rows < 1 and sol_rows < 1:
        out.append(Finding("GS-WB-GRAINS",
            "no recommendations in Recommendations nor Solution_Catalogue", "GSY-12"))

    # GS-WB-PEERS — a peer benchmark is actually established.
    if "Peer_Benchmarks" in have:
        hdr, data = rows("Peer_Benchmarks")
        real = [r for r in data if r and _norm(r[0])]
        if not real:
            out.append(Finding("GS-WB-PEERS", "Peer_Benchmarks is empty", "GSY-04"))
        else:
            hedge = sum(1 for r in real for c in r if _is_hedge(c))
            if hedge:
                out.append(Finding("GS-WB-PEERS", f"{hedge} hedge cell(s) in Peer_Benchmarks", "GSY-04"))
    return out


# ── REPORT gate ──────────────────────────────────────────────────────────

def _docx(path):
    import docx
    d = docx.Document(str(path))
    whole = "\n".join(p.text for p in d.paragraphs)
    h1 = [p.text.strip() for p in d.paragraphs
          if p.style and p.style.name in ("Heading 1", "Title") and p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            for c in row.cells:
                whole += "\n" + c.text
    with zipfile.ZipFile(str(path)) as z:
        names = z.namelist()
    fonts = [n for n in names if n.startswith("word/fonts/")]
    chrome = [n for n in names if re.match(r"word/(header|footer)\d*\.xml", n)]
    return whole, h1, fonts, chrome


def _template_sections(template_path):
    _, h1, _, _ = _docx(template_path)
    return [h for h in h1 if re.match(r"^\d+\.", h.strip())]


def report_findings(report_path, template_path=None, scores=None, kind="auto") -> list[Finding]:
    report_path = Path(report_path)
    out: list[Finding] = []
    whole, h1, fonts, chrome = _docx(report_path)
    low = whole.casefold()
    if kind == "auto":
        kind = "assessment" if "assessment" in report_path.name.lower() else "research"

    if template_path:
        want = _template_sections(template_path)
        havenums = {re.match(r"^(\d+)\.", h.strip()).group(1)
                    for h in h1 if re.match(r"^\d+\.", h.strip())}
        for s in want:
            if re.match(r"^(\d+)\.", s.strip()).group(1) not in havenums:
                out.append(Finding("GS-RPT-SECTIONS", f"missing template section {s!r}", "GSY-06"))

    tok = re.findall(r"\{\{[^}]*\}\}", whole)
    if tok:
        out.append(Finding("GS-RPT-NOTOKENS", f"{len(tok)} leftover token(s): {tok[:3]}", "GSY-07"))

    for bad in BANNED_HEDGES:
        if bad in ("tbd", "todo", "placeholder"):
            if re.search(rf"\b{re.escape(bad)}\b", low):
                out.append(Finding("GS-RPT-NOHEDGE", f"stub marker {bad!r}", "GSY-04"))
        elif bad in low:
            out.append(Finding("GS-RPT-NOHEDGE", f"{low.count(bad)}x hedge {bad!r}", "GSY-04"))

    # GS-RPT-BANDS — a reachable FIFTH band, not the M1..M5 scale, is the breach.
    for bad in BANNED_BAND_WORDS:
        if re.search(rf"\b{re.escape(bad)}\b", low):
            out.append(Finding("GS-RPT-BANDS", f"off-scale band word {bad!r}", "GSY-11"))

    # GS-RPT-BRANDING — the reference brands via a header, not embedded fonts.
    if not chrome and not fonts:
        out.append(Finding("GS-RPT-BRANDING",
            "no header/footer or embedded font — authored as a blank document", "GSY-05"))

    cites = len(set(re.findall(r"\b(?:E|ENR|PB|TS|INT|US)-\d+", whole)))
    floor = 60 if kind == "assessment" else 60
    if cites < floor:
        out.append(Finding("GS-RPT-CITATIONS", f"{cites} distinct citations (< {floor})", "GSY-08"))
    words = len(re.findall(r"\w+", whole))
    wfloor = 3500 if kind == "assessment" else 2500
    if words < wfloor:
        out.append(Finding("GS-RPT-LENGTH", f"{words} words (< {wfloor})", "GSY-08"))

    # GS-RPT-COVERAGE — the report discloses coverage, as the reference does.
    if "coverage" not in low and "unknown" not in low:
        out.append(Finding("GS-RPT-COVERAGE", "no coverage / evidence-gap disclosure", "GSY-16"))

    if kind == "assessment":
        if low.count("ai and data overlay") < 4:
            out.append(Finding("GS-RPT-AIOVERLAY",
                f"AI-and-data overlay x{low.count('ai and data overlay')} (need 4)", "GSY-09"))
        recs = len(set(re.findall(r"rec-r?\d+", low)))
        rebut = max(low.count("strongest counter"), low.count("rebuttal"))
        if recs and rebut < recs:
            out.append(Finding("GS-RPT-REBUTTALS", f"{rebut} rebuttals for {recs} recs", "GSY-10"))

    if scores and scores.get("overall") is not None:
        ov = scores["overall"]
        if f"{ov:.2f}" not in whole and f"{ov:.1f}" not in whole:
            out.append(Finding("GS-RPT-RECONCILE", f"overall {ov} not in report", "GSY-13"))
    return out


# ── PACKAGE / ingestion gate ─────────────────────────────────────────────

def package_findings(folder) -> list[Finding]:
    folder = Path(folder)
    out: list[Finding] = []
    man = folder / "run_manifest.json"
    if not man.exists():
        out.append(Finding("GS-ING-MANIFEST", "run_manifest.json absent", "GSY-14"))
    wb = list(folder.glob("DMA_Scoring_Workbook_*.xlsx")) or list(folder.glob("*Scoring_Workbook*.xlsx"))
    if not wb:
        out.append(Finding("GS-ING-DELIVERABLES", "no scoring workbook at root", "GSY-14"))
    else:
        out += workbook_findings(wb[0])
    for pat, k in ((("Client_Profile_Research_*.docx", "*Research_Report*.docx"), "research"),
                   (("DMA_Assessment_Report_*.docx", "*Assessment_Report*.docx"), "assessment")):
        hit = []
        for p in pat:
            hit += list(folder.glob(p))
        if not hit:
            out.append(Finding("GS-ING-DELIVERABLES", f"no {k} report at root", "GSY-14"))
        else:
            out += report_findings(hit[0], kind=k)
    if not list(folder.glob("Technographic_Scan_*.docx")) and not list(folder.glob("*Tech*Scan*.docx")):
        out.append(Finding("GS-ING-SCAN", "no technographic scan deliverable", "GSY-14"))
    return out


# ── CLI ──────────────────────────────────────────────────────────────────

def _print(findings, as_json):
    if as_json:
        print(json.dumps([dict(f) for f in findings], indent=1))
    elif not findings:
        print("GOLD STANDARD: PASS — 0 findings")
    else:
        print(f"GOLD STANDARD: {len(findings)} finding(s)")
        for f in findings:
            print("  -", f)
    return 0 if not findings else 1


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Gold-standard gate for DMA deliverables.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("workbook"); w.add_argument("path"); w.add_argument("--json", action="store_true")
    r = sub.add_parser("report"); r.add_argument("path"); r.add_argument("--template")
    r.add_argument("--scores"); r.add_argument("--kind", default="auto"); r.add_argument("--json", action="store_true")
    p = sub.add_parser("package"); p.add_argument("folder"); p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "workbook":
        return _print(workbook_findings(a.path), a.json)
    if a.cmd == "report":
        scores = json.loads(Path(a.scores).read_text()) if a.scores else None
        return _print(report_findings(a.path, a.template, scores, a.kind), a.json)
    if a.cmd == "package":
        return _print(package_findings(a.folder), a.json)


if __name__ == "__main__":
    sys.exit(main())
