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
  GSY-18 no 5-year financial trajectory        -> GS-WB-FINANCIALS, GS-RPT-FINANCIALS
         (depth: >=5 fiscal years of real metrics, in a Financial_Trends sheet or
          dispersed as the reference carries it; the report renders it with a trend)
"""
from __future__ import annotations

import json
import math
import re
import sys
import zipfile
from pathlib import Path

#: The pinned templates and the measured reference (references/templates/).
#: Every threshold below is read against gold_reference.json by
#: tests/skills/research_engine/test_gold_reference.py: a floor this gate
#: demands that the Golden 1 package itself would fail is a floor nobody
#: measured, and is refused by the suite.
_TEMPLATES = Path(__file__).resolve().parents[3] / "references" / "templates"


def _pinned_sections(kind: str) -> list[str]:
    """`N. Heading` for every numbered section the pinned Doc carries."""
    try:
        from . import report_spec as RS
    except Exception:            # noqa: BLE001 — the gate must still run
        return []
    key = "assessment" if kind == "assessment" else "client_research"
    return RS.numbered_headings(key)


def gold_reference() -> dict:
    p = _TEMPLATES / "gold_reference.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}

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

# An AI-and-data overlay block runs 150-250 words in the reference; 55 is the
# floor that separates a real overlay from the one-line "AI and data overlay:
# models." heading that cleared the old presence-only count (owner 2026-09-05,
# "AI overlays not thorough enough"). The evidence tie is enforced at the score
# (assessment.score, evidenced cells), the depth here.
AIOVERLAY_WORD_FLOOR = 55

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
#: Columns that are legitimately blank on SOME rows of an engine-built
#: assessment workbook, by sheet — structurally optional fields whose emptiness
#: is a readable state, not an unfinished cell. Measured 2026-09-03: a flat
#: exemption of `Source_URLs` alone flagged every ABSENT firmographic's Value,
#: every peer row without quartiles and every issue without a cap, so the
#: engine's own artefact emitted GS-WB-EMPTY by construction.
#: The scoring sheets' WORKING AREA (columns L onward — the synthesis,
#: ladder and challenge fields) is analysis, not the reader-facing core A–K:
#: `Contradiction_Disposition` is blank when nothing contradicted,
#: `Negative_Ladder` when the cell has evidence, `Ceiling_Band` on a documented
#: absence (null means no score, invariant 9). The reference's own scoring
#: sheets carry the eleven core columns; the gate judges those.
_WORKING_AREA_BLANK_OK = {
    "Dominant_Claim", "Claim_Label", "What_We_Found", "Facet_Coverage",
    "DQ_Works", "DQ_Fails", "DQ_Value", "DQ_Corroborates", "Triangulation",
    "Ceiling_Reasoning", "Why_It_Matters", "DMA_Impact", "DQ_Contradicts",
    "Contradiction_Disposition", "Absence_Claimed", "Proxy_Log",
    "Negative_Ladder", "Discovery_Questions", "Challenge_Verdict",
    "Ceiling_Band", "Uncertainty", "Retrieved_At",
    # core A–K fields that are blank by contract when nothing applies
    "Caps_Applied",
}
OPTIONAL_BLANK: dict[str, set[str]] = {
    "P1_Subcap_Scoring": _WORKING_AREA_BLANK_OK,
    "P2_Subcap_Scoring": _WORKING_AREA_BLANK_OK,
    "P3_Subcap_Scoring": _WORKING_AREA_BLANK_OK,
    "P4_Subcap_Scoring": _WORKING_AREA_BLANK_OK,
    "Firmographics": {"Value", "Unit", "As at", "Evidence", "Conf.", "Reason", "Route"},
    "Peer_Benchmarks": {"Peer_Names", "Peer_Scores", "Peer_P25", "Peer_P75",
                        "Entity_Score", "Peer_Median", "Source_Cell", "As_Of",
                        "Category_Name"},
    "Category_Detail": {"Gap_to_Peer", "Priority_Tier", "Peer_Median", "Coverage",
                        "Priority_Score"},
    "Pillar_Summary": {"Gap_to_Peer", "Peer_Median"},
    "Issue_Register": {"Cap", "As_Of"},
    "Tech_Register": {"Evidence_IDs", "Source_URLs", "SubCap_IDs", "As_Of",
                      "Providers", "DMA_Impact"},
    # Projected from the report's REC cards (`engine.grains recommendations`):
    # a card that names no single category, owner or horizon projects blanks.
    "Recommendations": {"Owner", "Horizon", "Category_ID"},
    "Focus_Areas": {"Currency_Note", "Page"},
    "Coverage": {"Verdict"},
}
#: Per-row rule: on these sheets a row in an ABSENT/QUARANTINED state may
#: leave its value columns blank — the state IS the value.
_STATE_BLANK_OK = {"Firmographics": ("State", ("ABSENT", "QUARANTINED")),
                   "Tech_Register": ("Status", ("ABSENT",))}
#: A grain row whose SCORE is blank is a pillar or category this engagement
#: did not assess (a focused engagement states its scope); its other value
#: columns are blank by construction and are not unfinished cells.
_UNASSESSED_GRAIN_OK = {"Pillar_Summary": "Score", "Category_Detail": "Score"}
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
    # Two shapes satisfy it: the reference's own `Coverage` sheet (Category,
    # Subcaps, Scored, Unknown_EvidenceGap, Coverage_Pct) and the engine's
    # `Coverage_Map` (category_id, subcaps, evidenced, evidence_gap,
    # coverage_pct), which is the same disclosure under the contract's names.
    # Measured 2026-09-03: the gate read only the sheet named `Coverage`, whose
    # engine columns are the research FLOORS, so an engine-built assessment
    # workbook could never pass its own gold gate.
    def _discloses(sheet):
        hdr, _ = rows(sheet)
        low = {_norm(h).casefold() for h in hdr}
        gap = any(("unknown" in h) or ("evidence_gap" in h) or ("gap" in h) for h in low)
        pct = any("coverage" in h for h in low)
        return gap and pct
    if "Coverage_Map" in have and _discloses("Coverage_Map"):
        pass
    elif "Coverage" in have and _discloses("Coverage"):
        pass
    elif "Coverage" in have or "Coverage_Map" in have:
        out.append(Finding("GS-WB-COVERAGE",
            "neither Coverage_Map nor Coverage discloses the evidence gap "
            "(Unknown_EvidenceGap / evidence_gap) with a coverage percentage", "GSY-16"))

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
        optional = WORKBOOK_EMPTY_OK | OPTIONAL_BLANK.get(sh, set())
        state_rule = _STATE_BLANK_OK.get(sh)
        state_ix = (list(hdr).index(state_rule[0])
                    if state_rule and state_rule[0] in hdr else None)
        grain_col = _UNASSESSED_GRAIN_OK.get(sh)
        grain_ix = list(hdr).index(grain_col) if grain_col in hdr else None
        for r in data:
            if not any(_norm(c) for c in r):
                continue
            row_absent = (state_ix is not None and state_rule is not None
                          and _norm(r[state_ix]).upper() in state_rule[1])
            if grain_ix is not None and not _norm(r[grain_ix]):
                row_absent = True            # an unassessed grain, stated as scope
            for j in range(ncol):
                v = r[j]
                if (v is None or not _norm(v)):
                    if hdr[j] in optional or row_absent:
                        continue
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

    # GS-WB-FINANCIALS — a real multi-year financial trajectory is present
    # ("depth and all 5-year trends including 5-year financials", GSY-18). The
    # reference (Golden 1) carries it dispersed across its scoring and evidence
    # sheets, so the floor is depth-of-series, NOT a mandated sheet name: at
    # least one sheet must show >=5 distinct fiscal years co-occurring with
    # financial metrics.
    year_re = re.compile(r"(?<!\d)20[0-3]\d(?!\d)")  # matches FY2020, 2020, 2020-24
    fin_re = re.compile(r"revenue|asset|income|deposit|loan|equity|eps|cagr|"
                        r"net charge|roe|roa|dividend|margin|capital", re.I)
    best_years, best_sheet = 0, None
    for sh in wb.sheetnames:
        yrs, kw = set(), False
        for r in wb[sh].iter_rows(values_only=True):
            for c in r:
                t = _norm(c)
                if not t:
                    continue
                yrs.update(year_re.findall(t))
                kw = kw or bool(fin_re.search(t))
        if kw and len(yrs) > best_years:
            best_years, best_sheet = len(yrs), sh
    if best_years < 5:
        out.append(Finding("GS-WB-FINANCIALS",
            f"no 5-year financial trajectory in the workbook (deepest series: "
            f"{best_years} fiscal year(s) in {best_sheet!r})", "GSY-18"))

    # When a dedicated financial-trends sheet exists it must be a real series:
    # >=5 fiscal-year columns, >=5 metric rows, and a growth/CAGR/trend column.
    fin_sheet = next((s for s in wb.sheetnames if s.lower()
                      in ("financial_trends", "financials", "financial_summary")), None)
    if fin_sheet:
        hdr, data = rows(fin_sheet)
        hdr_n = [_norm(h) for h in hdr]
        if "Fiscal_Year" in hdr_n and "Metric" in hdr_n:
            # The ENGINE's long format (contract v7): one row per
            # (metric, fiscal year); the renderer pivots it wide and computes
            # the CAGR. Depth is distinct years × distinct metrics.
            yi, mi = hdr_n.index("Fiscal_Year"), hdr_n.index("Metric")
            years = {_norm(r[yi]) for r in data if r and _norm(r[yi])}
            metrics = {_norm(r[mi]) for r in data if r and _norm(r[mi])}
            if len(years) < 5:
                out.append(Finding("GS-WB-FINANCIALS",
                    f"{fin_sheet}: only {len(years)} fiscal year(s), need >=5", "GSY-18"))
            if len(metrics) < 3:
                out.append(Finding("GS-WB-FINANCIALS",
                    f"{fin_sheet}: only {len(metrics)} metric(s), need >=3", "GSY-18"))
        else:
            # The reference's WIDE shape: metric rows × fiscal-year columns
            # with an explicit CAGR/growth column.
            yr_cols = [h for h in hdr if year_re.search(_norm(h))]
            has_trend = any(re.search(r"cagr|growth|trend|delta|change", _norm(h), re.I)
                            for h in hdr)
            metric_rows = [r for r in data if r and _norm(r[0])]
            if len(yr_cols) < 5:
                out.append(Finding("GS-WB-FINANCIALS",
                    f"{fin_sheet}: only {len(yr_cols)} fiscal-year column(s), need >=5", "GSY-18"))
            if len(metric_rows) < 5:
                out.append(Finding("GS-WB-FINANCIALS",
                    f"{fin_sheet}: only {len(metric_rows)} metric row(s), need >=5", "GSY-18"))
            if not has_trend:
                out.append(Finding("GS-WB-FINANCIALS",
                    f"{fin_sheet}: no CAGR/growth/trend column", "GSY-18"))
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


def _docx_shape(path) -> dict:
    """The report's STRUCTURE, measured: how many tables, how big each is, and
    how the words divide between prose and tables.

    Separate from `_docx` because that returns one flattened string, and a
    flattened string cannot tell a report that TABULATES its register from one
    that describes it in paragraphs. Both carry the same words; only one is the
    format the pinned Doc asks for. Measured 2026-09-06 on a delivered pair:
    50 tables against the reference's 92, and 26 against 39, while paragraph
    words ran 1.41x and 1.33x ABOVE the reference — prose had been written
    where the template declares a table, and every volume floor passed.
    """
    from docx import Document

    def w(text):                      # the same count the volume gate uses
        return len(re.findall(r"\w+", text or ""))

    d = Document(str(path))
    para_words = sum(w(p.text) for p in d.paragraphs)
    sizes = []
    for t in d.tables:
        sizes.append(sum(w(c.text) for r in t.rows for c in r.cells))
    return {"tables": len(d.tables), "table_words": sum(sizes),
            "table_sizes": sizes, "paragraph_words": para_words,
            "largest_table": max(sizes) if sizes else 0}


def _docx_layout(path) -> dict:
    """The report in DOCUMENT ORDER — headings, paragraphs and tables as they
    appear — so the gate can ask WHERE a table sits, not just how many there
    are. `_docx_shape` counts; this one places, which is what the cover, the
    front matter and the per-section distribution checks need (measured
    2026-09-07: a delivered pair carried the right TOTAL tables while a whole
    section stood barren and another was a dump)."""
    from docx import Document
    from docx.text.paragraph import Paragraph
    from docx.table import Table

    d = Document(str(path))
    items: list[tuple] = []
    for child in d.element.body:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(child, d)
            style = (p.style.name if p.style is not None else "") or ""
            kind = ("h1" if style in ("Heading 1", "Title") else
                    "h2" if style == "Heading 2" else "para")
            items.append((kind, p.text or ""))
        elif tag == "tbl":
            t = Table(child, d)
            rows = [[c.text for c in r.cells] for r in t.rows]
            items.append(("table", rows))

    cover_tables: list[list[list[str]]] = []
    front_h1: list[str] = []
    sections: dict[str, int] = {}
    seen_numbered = False
    current: str | None = None
    tables: list[list[list[str]]] = []
    for kind, payload in items:
        if kind == "h1":
            m = re.match(r"^\s*(\d+)\.", payload)
            if m:
                seen_numbered = True
                current = m.group(1)
                sections.setdefault(current, 0)
            else:
                current = None
                if not seen_numbered:
                    front_h1.append(payload.strip())
        elif kind == "table":
            tables.append(payload)
            if not seen_numbered:
                cover_tables.append(payload)
            elif current is not None:
                sections[current] = sections.get(current, 0) + 1
    paras = [p for k, p in items if k == "para" and p.strip()]
    return {"cover_tables": cover_tables, "front_h1": front_h1,
            "sections": sections, "tables": tables, "paras": paras}


def _flat(cells) -> str:
    return " ".join(str(c or "") for row in cells for c in row).casefold()


def _degenerate_table(rows: list[list[str]]) -> bool:
    """A table that carries no information a reader can argue with: excluding
    the first (label) column, EVERY column is empty or one repeated value, so
    no column varies row to row. This is the `Field | STATED | (blank)` table
    the owner flagged 2026-09-07 — the Firmographics dump rendered as a status
    strip. A table whose non-label columns all vary (the identity-check table's
    Basis column, say) is NOT degenerate even when one column is constant."""
    if len(rows) < 4:                        # header + >= 3 data rows
        return False
    header, data = rows[0], rows[1:]
    ncols = len(header)
    if ncols < 2:
        return False
    for j in range(1, ncols):
        col = [(r[j].strip() if j < len(r) else "") for r in data]
        non_empty = [c for c in col if c]
        if non_empty and len(set(col)) > 1:
            return False                     # this column varies — not degenerate
    return True


_DUMP_CITE = re.compile(r"\b(?:E|ENR|PB|TS|INT|US)-\d+")


def _prose_dump_clauses(para: str) -> int:
    """How many `;`-separated clauses in ONE paragraph are a SHORT, cited
    field entry — the shape of a register typed as a sentence ('website X
    ([E-1], High); employees 265 ([E-1], Medium); assets $1.18B ([E-2]); …').
    The reference's interpretive paragraphs cite inline and use semicolons
    too, but their clauses are whole sentences; the <=14-word bound keeps a
    field:value:citation entry and drops an argued clause, so the count
    separates a dump from an argument (measured 2026-09-07: the reference's
    busiest paragraph carries 1 such clause, a delivered §1.1 carried ten)."""
    n = 0
    for c in para.split(";"):
        words = len(re.findall(r"\w+", c))
        # 3..12 words: a `field value (citation)` entry. Below 3 is a bare
        # citation fragment a sentence-spanning `;` split off (the reference's
        # `; [E-021];`); above 12 is an argued clause, not a register row.
        if _DUMP_CITE.search(c) and 3 <= words <= 12:
            n += 1
    return n


#: Golden 1's own depth, per subcap, as the fallback when gold_reference.json
#: is unreadable: distinct citations, paragraph words and TABLES over 690
#: subcaps. The table count is the half of "depth" a word count cannot see.
_GOLD_DEPTH_FALLBACK = {"research": (47, 4910, 39), "assessment": (115, 11633, 92)}
_GOLD_SUBCAPS_FALLBACK = 690

#: A report may run this far above the reference's PARAGRAPH words before the
#: prose is doing a table's job. Set at 1.25x — the delivered pair that
#: prompted this check ran 1.33x and 1.41x while carrying barely half the
#: reference's tables, and the reference itself sits at 1.0 by construction.
PROSE_INFLATION_LIMIT = 1.25

#: One table may hold this share of all table words before it is a DATA DUMP
#: rather than a curated table. Golden 1 averages ~126 words per table across
#: 92 tables; the delivered assessment averaged ~2,313 across 50, because whole
#: 690-row and 3,309-row sheets were emitted where the Doc asks for a curated
#: extract. A reader cannot argue with a sheet.
TABLE_DUMP_SHARE = 0.35

#: How far the AVERAGE table may run above the reference's average before the
#: report is emitting sheets rather than curating tables. The share test above
#: cannot see this: a report that dumps SIX whole sheets has no single dominant
#: table and is still six sheets. 4x leaves real headroom — the delivered
#: assessment sat at 18x.
TABLE_DUMP_FACTOR = 4.0

#: A numbered section owes at least this share of the reference's own table
#: count FOR THAT SECTION, scaled to the run. The whole-report `tables` floor
#: already fixes the TOTAL depth; this fixes the DISTRIBUTION, so a report
#: cannot pass by dumping every table into one section and leaving the rest
#: barren (measured 2026-09-07: a delivered assessment carried its tables in
#: six sections and left five carrying prose alone). Kept well under 1.0 so a
#: section the reference gives one table still only owes one, and the reference
#: itself clears every floor.
SECTION_TABLE_SHARE = 0.25

#: This many SHORT cited field-clauses in a single paragraph is a field
#: register typed as a sentence, not an argument (GS-RPT-PROSE-DUMP). Measured
#: 2026-09-07: neither reference has a paragraph with even one such clause; a
#: delivered §1.1 had nine. Four leaves clear margin above the reference and
#: still catches the dump.
PROSE_DUMP_CLAUSES = 4


def section_floors(kind: str, subcaps: int | None = None) -> dict:
    """Per-numbered-section table floors, plus the cover labels and front
    matter the reference carries — the anatomy `depth_floors` does not see.
    Every floor is at or below the reference's own count for that section
    (SECTION_TABLE_SHARE < 1), so the reference passes its own gate."""
    kind = "assessment" if kind == "assessment" else "research"
    g = gold_reference()
    rep = g.get("reports", {}).get(kind, {})
    ref_sub = _GOLD_SUBCAPS_FALLBACK
    try:
        ref_sub = int(g["workbook"]["subcaps"])
    except (KeyError, TypeError, ValueError):
        pass
    n = int(subcaps) if subcaps else ref_sub
    scale = n / ref_sub if ref_sub else 1.0
    sec = rep.get("section_tables", {}) or {}
    floors = {k: max(1, math.floor(int(v) * scale * SECTION_TABLE_SHARE))
              for k, v in sec.items()}
    return {"section_floors": floors,
            "section_reference": {k: int(v) for k, v in sec.items()},
            "cover_labels": [str(x) for x in rep.get("cover_labels", [])],
            "front_matter_h1": [str(x) for x in rep.get("front_matter_h1", [])]}


def depth_floors(kind: str, subcaps: int | None = None) -> dict:
    """Citation and word floors for a report over `subcaps` cells, at the
    density the Golden 1 reference meets — never above what the reference
    itself would pass (a flat 60 citations failed Golden 1's own research
    report, which carries 47; measured 2026-09-03). `subcaps` defaults to
    the reference's 690, so a bare `gold_standard report <docx>` holds a
    full-size run to the full Golden 1 depth."""
    kind = "assessment" if kind == "assessment" else "research"
    g = gold_reference()
    try:
        ref_sub = int(g["workbook"]["subcaps"])
        ref_c = int(g["reports"][kind]["distinct_e_ids"])
        ref_w = int(g["reports"][kind]["words_paragraphs"])
        ref_t = int(g["reports"][kind]["tables"])
    except (KeyError, TypeError, ValueError):
        ref_sub = _GOLD_SUBCAPS_FALLBACK
        ref_c, ref_w, ref_t = _GOLD_DEPTH_FALLBACK[kind]
    n = int(subcaps) if subcaps else ref_sub
    scale = n / ref_sub
    # The WORD floor is the pinned Doc's own contract (the section LENGTH
    # minima summed: 8,400 assessment / 3,050 research at full size), scaled
    # to the run — the Doc is the format the owner asked for, and Golden 1
    # exceeds it (11,633 / 4,910 paragraph words), so the contract is the
    # floor and the reference proves it reachable. Falls back to the
    # reference's own words when the spec cannot be read.
    try:
        from . import report_spec as RS
        spec_min = RS.SPECS["assessment" if kind == "assessment"
                            else "client_research"].min_words
        words = math.ceil(spec_min * scale)
    except Exception:            # noqa: BLE001 — the gate must still run
        words = math.ceil(ref_w * scale)
    words = min(words, math.ceil(ref_w * scale))     # never above the reference
    # The TABLE floor scales the same way and is never above the reference's
    # own count, by the same discipline: a structure floor Golden 1 would fail
    # is a floor nobody measured.
    return {"citations": max(1, math.ceil(ref_c * scale)), "words": max(1, words),
            "tables": max(1, math.ceil(ref_t * scale)),
            "reference_paragraph_words": math.ceil(ref_w * scale),
            "subcaps": n, "reference_subcaps": ref_sub}


def _gold_avg_table_words(kind: str) -> int:
    """Words per table in the reference — the number that separates a curated
    table from a sheet emitted whole. Golden 1: ~126 (assessment), ~184
    (research). A delivered assessment averaged ~2,247."""
    kind = "assessment" if kind == "assessment" else "research"
    try:
        r = gold_reference()["reports"][kind]
        table_words = int(r["words_including_tables"]) - int(r["words_paragraphs"])
        return max(1, round(table_words / max(int(r["tables"]), 1)))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return 126 if kind == "assessment" else 184


def report_findings(report_path, template_path=None, scores=None, kind="auto",
                    subcaps: int | None = None) -> list[Finding]:
    report_path = Path(report_path)
    out: list[Finding] = []
    whole, h1, fonts, chrome = _docx(report_path)
    low = whole.casefold()
    if kind == "auto":
        kind = "assessment" if "assessment" in report_path.name.lower() else "research"

    # GS-RPT-SECTIONS — every numbered section of the PINNED template, by
    # number AND heading. A docx template is accepted for a one-off check, but
    # the default is the pin the engine renders to, so the gate and the
    # renderer cannot disagree about what "the required format" is.
    want = _template_sections(template_path) if template_path else _pinned_sections(kind)
    have_h1 = {}
    for h in h1:
        m = re.match(r"^(\d+)\.\s*(.*)$", h.strip())
        if m:
            have_h1[m.group(1)] = m.group(2).strip()
    for s_ in want:
        m = re.match(r"^(\d+)\.\s*(.*)$", s_.strip())
        if not m:
            continue
        n, head = m.group(1), m.group(2).strip()
        if n not in have_h1:
            out.append(Finding("GS-RPT-SECTIONS", f"missing template section {s_!r}", "GSY-06"))
        elif head and have_h1[n].casefold() != head.casefold() \
                and not have_h1[n].casefold().startswith(head.casefold()):
            out.append(Finding("GS-RPT-SECTIONS",
                f"section {n} is titled {have_h1[n]!r}; the template says {head!r}",
                "GSY-06"))

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
    floors = depth_floors(kind, subcaps)
    if cites < floors["citations"]:
        out.append(Finding("GS-RPT-CITATIONS",
            f"{cites} distinct citations (< {floors['citations']}, the Golden 1 "
            f"density over {floors['subcaps']} subcaps)", "GSY-08"))
    words = len(re.findall(r"\w+", whole))
    if words < floors["words"]:
        out.append(Finding("GS-RPT-LENGTH",
            f"{words} words (< {floors['words']}, the Golden 1 density over "
            f"{floors['subcaps']} subcaps)", "GSY-08"))

    # ── STRUCTURE, not just volume (GSY-19) ──────────────────────────────
    # Every check above counts words or ids, and a report can pass all of
    # them while being the wrong SHAPE: prose written where the pinned Doc
    # declares a table. Measured 2026-09-06 on a delivered pair — 50 tables
    # against the reference's 92 and 26 against 39, with paragraph words
    # 1.41x and 1.33x ABOVE the reference — and every volume floor passed,
    # because more prose helps a word floor while being exactly the defect.
    shape = _docx_shape(report_path)
    if shape["tables"] < floors["tables"]:
        out.append(Finding("GS-RPT-TABLES",
            f"{shape['tables']} tables (< {floors['tables']}, the Golden 1 "
            f"density over {floors['subcaps']} subcaps). The pinned Doc states "
            f"its registers, rollups, caps and peer sets as TABLES; a section "
            f"that describes one in a paragraph carries the same words and "
            f"none of the structure a reader can scan or argue with", "GSY-19"))

    ref_prose = floors["reference_paragraph_words"]
    if (shape["tables"] < floors["tables"]
            and shape["paragraph_words"] > ref_prose * PROSE_INFLATION_LIMIT):
        out.append(Finding("GS-RPT-PROSE-FOR-STRUCTURE",
            f"{shape['paragraph_words']} paragraph words against the "
            f"reference's {ref_prose} ("
            f"{shape['paragraph_words'] / max(ref_prose, 1):.2f}x) while "
            f"carrying {shape['tables']} of {floors['tables']} tables — prose "
            f"is standing in for structure. The repair is to MOVE the content "
            f"into the table the section declares, not to cut the prose",
            "GSY-19"))

    # A DUMP is not caught by "one table dominates" — a report that emits six
    # whole sheets has no single dominant table and is still six sheets. The
    # measure that sees it is the AVERAGE table, against the reference's.
    gold_avg = _gold_avg_table_words(kind)
    avg = shape["table_words"] / shape["tables"] if shape["tables"] else 0
    if avg > gold_avg * TABLE_DUMP_FACTOR:
        out.append(Finding("GS-RPT-TABLE-DUMP",
            f"tables average {avg:,.0f} words against the reference's "
            f"{gold_avg} ({avg / gold_avg:.0f}x). A 690-row or 3,309-row sheet "
            f"emitted whole is not a table a reader can argue with — it is the "
            f"workbook, pasted. Curate the extract each section reasons from, "
            f"and let the workbook carry the rest", "GSY-19"))
    elif shape["table_words"] and shape["largest_table"] > shape["table_words"] * TABLE_DUMP_SHARE:
        share = shape["largest_table"] / shape["table_words"]
        out.append(Finding("GS-RPT-TABLE-DUMP",
            f"one table holds {share:.0%} of all table content "
            f"({shape['largest_table']:,} of {shape['table_words']:,} words). "
            f"That is a sheet emitted whole, not a curated table: Golden 1 "
            f"averages ~{gold_avg} words across {floors['tables']} tables. "
            f"Curate the extract the section argues from", "GSY-19"))

    # ── COVER, FRONT MATTER and DISTRIBUTION (owner 2026-09-07: "the cover
    # page is off … a lot of placeholder and unnecessary text") ──────────
    # The volume and total-table gates above still pass a report whose cover
    # is a bare Title heading, whose front matter skips the Document Control
    # binding, whose tables all pile into one section, or which types a field
    # register as a paragraph. The reference does none of these; these read
    # its own anatomy (section_floors) and hold the report to it.
    layout = _docx_layout(report_path)
    anat = section_floors(kind, subcaps)

    # GS-RPT-COVER — a boxed title carrying the entity, then a metadata grid
    # carrying the Doc's own labels (OVERALL MATURITY / SUB-VERTICAL / …).
    cover_flat = _flat([r for t in layout["cover_tables"] for r in t])
    missing_labels = [lb for lb in anat["cover_labels"]
                      if lb.casefold() not in cover_flat]
    if len(layout["cover_tables"]) < 2:
        out.append(Finding("GS-RPT-COVER",
            f"the cover carries {len(layout['cover_tables'])} table(s); the "
            f"pinned Doc opens with a boxed title AND a metadata grid "
            f"(the O2 identity strip: {', '.join(anat['cover_labels'][:4])} …). "
            f"A bare Title heading is not the cover", "GSY-05"))
    elif missing_labels:
        out.append(Finding("GS-RPT-COVER",
            f"the cover grid is missing the label(s) "
            f"{', '.join(missing_labels)} — the Doc's identity strip is "
            f"resolved from the run, not dropped", "GSY-05"))

    # GS-RPT-FRONTMATTER — the two unnumbered H1s the reference opens with.
    have_front = {h.casefold() for h in layout["front_h1"]}
    for want in anat["front_matter_h1"]:
        if not any(want.casefold() in h for h in have_front):
            out.append(Finding("GS-RPT-FRONTMATTER",
                f"front matter is missing the {want!r} section — the reference "
                f"carries it before section 1 (Contents + the catalogue "
                f"binding that resolves every figure from the run)", "GSY-06"))

    # GS-RPT-SECTION-DISTRIBUTION — no numbered section barren where the
    # reference tabulates. Total depth is GS-RPT-TABLES' job; this is spread.
    for num, floor in sorted(anat["section_floors"].items(),
                             key=lambda kv: int(kv[0])):
        got = layout["sections"].get(num)
        if got is None:                       # section absent — GS-RPT-SECTIONS owns that
            continue
        if got < floor:
            ref_n = anat["section_reference"].get(num, floor)
            out.append(Finding("GS-RPT-SECTION-DISTRIBUTION",
                f"section {num} carries {got} table(s); the reference carries "
                f"{ref_n} there, so this run owes at least {floor}. The section "
                f"states its register/scorecard/cards as a table, not a "
                f"paragraph", "GSY-19"))

    # GS-RPT-DEGENERATE-TABLE — a table whose non-label columns are all
    # constant or empty carries nothing per row (the `Field | STATED | ` strip).
    degen = sum(1 for t in layout["tables"] if _degenerate_table(t))
    if degen:
        out.append(Finding("GS-RPT-DEGENERATE-TABLE",
            f"{degen} table(s) carry no column that varies row to row — a "
            f"repeated status word ('STATED') or an empty column is not data. "
            f"Render the fields' own values (value, unit, as-of, evidence), or "
            f"drop the table and let the prose carry the point", "GSY-19"))

    # GS-RPT-PROSE-DUMP — a field register typed as a `;`-separated sentence.
    dumps = [n for n in (_prose_dump_clauses(p) for p in layout["paras"])
             if n >= PROSE_DUMP_CLAUSES]
    if dumps:
        out.append(Finding("GS-RPT-PROSE-DUMP",
            f"{len(dumps)} paragraph(s) list {max(dumps)}+ cited field clauses "
            f"in one sentence ('website X ([E-1]); employees Y ([E-1]); …') — "
            f"that is the Firmographics register typed as prose. Move the "
            f"fields into the table that owns them; keep the paragraph for what "
            f"the figures MEAN", "GSY-19"))

    # GS-RPT-COVERAGE — the report discloses coverage, as the reference does.
    if "coverage" not in low and "unknown" not in low:
        out.append(Finding("GS-RPT-COVERAGE", "no coverage / evidence-gap disclosure", "GSY-16"))

    if kind == "assessment":
        # One overlay per pillar DEEP DIVE the report carries — four on a full
        # engagement, fewer on a focused one that states its scope (the Doc's
        # §5 is one card per pillar in scope). Counted from the card headings
        # the renderer emits; a report with no deep-dive headings at all is
        # held to the full four.
        dives = len(re.findall(r"pillar deep dive \(p[1-4]\)", low))
        need = dives if 1 <= dives <= 4 else 4
        n_overlay = low.count("ai and data overlay")
        if n_overlay < need:
            out.append(Finding("GS-RPT-AIOVERLAY",
                f"AI-and-data overlay x{n_overlay} "
                f"(need {need}, one per pillar deep dive)", "GSY-09"))
        else:
            # DEPTH, not just presence (owner 2026-09-05, "AI overlays not
            # thorough enough"). The reference's overlays run 150-250 words and
            # CITE the evidence for the readiness and applicability they assert;
            # a three-word "AI and data overlay: models." cleared the old
            # heading count while the structured Subcap_Scores overlay columns
            # stayed empty (AUD-0052). Each block must carry substance AND a
            # citation. 55 words is the floor — well under the reference, well
            # over the one-line defect.
            thin = []
            for m in re.finditer(r"ai and data overlay", low):
                seg = whole[m.start(): m.start() + 1400]
                nxt = re.search(r"(?i)(ai and data overlay|pillar deep dive)", seg[20:])
                if nxt:
                    seg = seg[: nxt.start() + 20]
                w = len(re.findall(r"\w+", seg))
                if w < AIOVERLAY_WORD_FLOOR:
                    thin.append(w)
            if thin:
                out.append(Finding("GS-RPT-AIOVERLAY-DEPTH",
                    f"{len(thin)} AI-and-data overlay block(s) below depth "
                    f"(e.g. {min(thin)} words): a substantive overlay is "
                    f"~150-250 words on the readiness and applicability of AI for "
                    f"the pillar — the evidence tie is enforced at the score, the "
                    f"depth here, not a one-line heading", "GSY-09"))
        recs = len(set(re.findall(r"rec-r?\d+", low)))
        rebut = max(low.count("strongest counter"), low.count("rebuttal"))
        if recs and rebut < recs:
            out.append(Finding("GS-RPT-REBUTTALS", f"{rebut} rebuttals for {recs} recs", "GSY-10"))

    # GS-RPT-FINANCIALS — the report renders a multi-year financial trajectory
    # ("depth and all 5-year trends including 5-year financials", GSY-18): >=5
    # distinct fiscal years, a financial metric, and an explicit trend word.
    fyears = set(re.findall(r"(?<!\d)20[0-3]\d(?!\d)", whole))
    has_fin = bool(re.search(r"revenue|asset|income|deposit|loan|equity|eps|cagr|"
                             r"net charge|roe|roa|dividend|margin|capital", low))
    has_trend = bool(re.search(r"cagr|growth|grew|year-over-year|yoy|compound|"
                               r"trajectory|five-year|5-year", low))
    if not (len(fyears) >= 5 and has_fin and has_trend):
        out.append(Finding("GS-RPT-FINANCIALS",
            f"no 5-year financial trajectory ({len(fyears)} yrs, "
            f"fin={has_fin}, trend={has_trend})", "GSY-18"))

    if scores and scores.get("overall") is not None:
        ov = scores["overall"]
        if f"{ov:.2f}" not in whole and f"{ov:.1f}" not in whole:
            out.append(Finding("GS-RPT-RECONCILE", f"overall {ov} not in report", "GSY-13"))
    return out


def _subcap_count(workbook_path) -> int | None:
    """Selected cells in the scoring workbook — the size the report floors
    scale by. None when the workbook cannot be read."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
        n = 0
        for sh in SCORE_SHEETS:
            if sh in wb.sheetnames:
                for r in wb[sh].iter_rows(min_row=2, values_only=True):
                    if r and r[0] is not None and _norm(r[0]):
                        n += 1
        wb.close()
        return n or None
    except Exception:            # noqa: BLE001 — the gate must still run
        return None


# ── PACKAGE / ingestion gate ─────────────────────────────────────────────

#: The four technographic layers, verbatim from the scan's own vocabulary
#: (techscan.C.TECH_LAYERS). Kept here so a rename in one place is caught by
#: the other rather than drifting silently.
_SCAN_LAYERS = ("OPS", "CUST", "DATA", "INFRA")


def _scan_layers_unlooked_from_docx(folder) -> list:
    """The docx fallback: its Coverage table prints a Detections count per
    layer by the same route as the json's by_layer, so a layer at 0 is one
    never looked at."""
    hit = (list(Path(folder).glob("Technographic_Scan_*.docx"))
           or list(Path(folder).glob("*Tech*Scan*.docx")))
    if not hit:
        return []
    try:
        from docx import Document
        d = Document(str(hit[0]))
    except Exception:                                       # noqa: BLE001
        return []
    for t in d.tables:
        head = [c.text.strip() for c in t.rows[0].cells]
        if head[:2] == ["Layer", "Detections"]:
            return [row.cells[0].text.strip() for row in t.rows[1:]
                    if row.cells[0].text.strip() in _SCAN_LAYERS
                    and row.cells[1].text.strip() in ("0", "", "—")]
    return []


def scan_findings(folder) -> list[Finding]:
    """GS-SCAN-DEPTH — the technographic scan looked at all four layers.

    package_findings already refuses a MISSING scan (GS-ING-SCAN); this is the
    depth floor it never had. It enforces INVESTIGATION, not detections: the
    scan's own engine computes `layers_never_looked_at` (techscan.scan_state)
    and its docx prints a red "NOT SCANNED — a gap in the scan, not a clean
    estate" banner for exactly those layers — the scanner's stated failure
    mode — yet nothing at the package gate read it, so a scan that covered OPS
    and left three layers blank passed as a complete estate picture.

    A layer with an ABSENT row is looked-at-and-empty and PASSES; a layer with
    NO row was never looked at and FAILS. Counting detections instead would
    push a producer to manufacture them — the opposite of what this build
    wants — so the floor is depth of investigation, which the reference's own
    four-layer scan clears by construction.
    """
    folder = Path(folder)
    js = folder / "technographic_scan.json"
    if not js.is_file():
        js = next(iter(folder.glob("technographic_scan*.json")), None)
    if js and js.is_file():
        try:
            doc = json.loads(js.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            doc = {}
        counts = doc.get("counts") or {}
        never = counts.get("layers_never_looked_at")
        if never is None:
            by_layer = counts.get("by_layer") or {}
            never = [l for l in _SCAN_LAYERS if not by_layer.get(l)]
    else:
        never = _scan_layers_unlooked_from_docx(folder)
    return [Finding(
        "GS-SCAN-DEPTH",
        f"technographic scan: layer {l} was never looked at — no detection "
        f"was attempted, so an unscanned gap reads as a clean estate. Record "
        f"its ABSENT rows with the searches that establish them, or the "
        f"searches that found products; a scan that covers one layer and "
        f"leaves the others blank is a fraction of an estate picture.",
        "GSY-14") for l in (never or [])]


def package_findings(folder) -> list[Finding]:
    folder = Path(folder)
    out: list[Finding] = []
    man = folder / "run_manifest.json"
    if not man.exists():
        out.append(Finding("GS-ING-MANIFEST", "run_manifest.json absent", "GSY-14"))
    wb = list(folder.glob("DMA_Scoring_Workbook_*.xlsx")) or list(folder.glob("*Scoring_Workbook*.xlsx"))
    subcaps = None
    if not wb:
        out.append(Finding("GS-ING-DELIVERABLES", "no scoring workbook at root", "GSY-14"))
    else:
        out += workbook_findings(wb[0])
        subcaps = _subcap_count(wb[0])
    for pat, k in ((("Client_Profile_Research_*.docx", "*Research_Report*.docx"), "research"),
                   (("DMA_Assessment_Report_*.docx", "*Assessment_Report*.docx"), "assessment")):
        hit = []
        for p in pat:
            hit += [x for x in folder.glob(p) if not x.name.startswith("DRAFT_")]
        if not hit:
            out.append(Finding("GS-ING-DELIVERABLES", f"no {k} report at root", "GSY-14"))
        else:
            out += report_findings(hit[0], kind=k, subcaps=subcaps)
    if not list(folder.glob("Technographic_Scan_*.docx")) and not list(folder.glob("*Tech*Scan*.docx")):
        out.append(Finding("GS-ING-SCAN", "no technographic scan deliverable", "GSY-14"))
    else:
        out += scan_findings(folder)
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
    r.add_argument("--subcaps", type=int, default=None,
                   help="the run's selected cell count, so the depth floors scale "
                        "to this engagement (default: the reference's 690); "
                        "`package` reads it from the workbook")
    r.add_argument("--workbook", help="read --subcaps from this scoring workbook")
    p = sub.add_parser("package"); p.add_argument("folder"); p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "workbook":
        return _print(workbook_findings(a.path), a.json)
    if a.cmd == "report":
        scores = json.loads(Path(a.scores).read_text()) if a.scores else None
        subcaps = a.subcaps or (_subcap_count(a.workbook) if a.workbook else None)
        return _print(report_findings(a.path, a.template, scores, a.kind,
                                      subcaps=subcaps), a.json)
    if a.cmd == "package":
        return _print(package_findings(a.folder), a.json)


if __name__ == "__main__":
    sys.exit(main())
