#!/usr/bin/env python3
"""The two client-facing reports, curated from the workbook.

    reports.py --run RUN --report client_research|assessment|both

WHY THIS EXISTS.

  AUD-0003  of the three canonical artefacts, the Assessment Report had NO
      PRODUCER AT ALL ("grep for any render/generate/build_report entry point
      against the pinned v8 template across apps/worker, apps/api, apps/mcp
      and both skill trees returns zero"), and the Client Research Report was
      emitted as `client_profile.md`, which the app's classifier returns None
      for. One artefact could not be made and the other could not be ingested.
  AUD-0052  and the renderer that did exist read five JSON files and zero
      sheets, so "a curated report and a recording workbook can disagree about
      the same assessment and both ship".
  AUD-0033  which is how a delivered report shipped with 6 of 21 cited E-ids
      unresolvable, with the check that would catch it documented and never
      implemented.

Three rules, all enforced before a file is written:

  1. Every section is curated from named workbook sheets. Nothing is read
     from anywhere else.
  2. Every `[E-xxx]` in the rendered text is resolved against Evidence_Detail.
     One dead citation refuses the render. There is no "warn and ship".
  3. Every blocking minimum is measured — section word counts, the report
     word count, the insight-card floor.

A refusal names what is missing and what would fix it, because an unattended
run has to be able to act on it.
"""
from __future__ import annotations

# Runnable both ways. `python3 -m engine.<mod>` is the documented invocation,
# but every audit and every operator reaches for `python3 <path> --help`
# first, and a relative import dies there. Binding __package__ makes the two
# equivalent instead of making one of them a trap.
if __package__ in (None, ""):  # noqa: E402  (must precede the relative imports)
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from . import contract as C
from . import quality as Q
from . import report_spec as RS
from . import runstate
from .workbook import RunWorkbook, _split_ids

CITE_RE = re.compile(r"\[(E-\d+)(?::F\d+)?\]")


class ReportRefused(SystemExit):
    pass


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", text or ""))


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", (s or "")).strip("_") or "client"


# ── curation ─────────────────────────────────────────────────────────────

def curate(wb: RunWorkbook, spec: RS.ReportSpec) -> dict:
    """Assemble the report's blocks from the workbook, without rendering.

    Separate from rendering so the checks below run against exactly what
    would be written — not against a summary of it."""
    md = wb.metadata()
    narrative = [r for r in wb.rows("Report_Narrative")
                 if str(r.get("Report") or "") == spec.key]
    by_section: dict[str, list[dict]] = {}
    for r in narrative:
        by_section.setdefault(str(r.get("Section_ID") or ""), []).append(r)

    blocks = []
    for sec in spec.sections:
        rows = by_section.get(sec.id, [])
        body = "\n\n".join(str(r.get("Body") or "").strip() for r in rows
                           if str(r.get("Body") or "").strip())
        tables = _tables_for(wb, sec)
        declared = [s for s in sec.inputs if s in C.SHEETS]
        empty_inputs = [s for s in declared if not wb.rows(s)]
        # A section has NO SOURCE only when EVERY declared input is empty.
        # A focused engagement legitimately leaves three pillar sheets empty,
        # and calling that "no source" would refuse a correct run — the
        # opposite error to AUD-0107's, and just as wrong. Partially empty
        # inputs are STATED in the document as scope, not treated as a defect.
        no_source = bool(declared) and len(empty_inputs) == len(declared)
        blocks.append({
            "section": sec, "rows": rows, "body": body, "tables": tables,
            "words": _words(body) + sum(t["words"] for t in tables),
            "citations": sorted(set(CITE_RE.findall(body))
                                | {c for t in tables for c in t["citations"]}),
            "empty_inputs": empty_inputs, "no_source": no_source,
            "declared_inputs": declared,
        })
    return {"meta": md, "spec": spec, "blocks": blocks}


def _tables_for(wb: RunWorkbook, sec: RS.Section) -> list[dict]:
    """The workbook-derived tables a section carries.

    These are the CURATION: the numbers in the report are the numbers in the
    sheets, read at render time, so the two cannot disagree."""
    out = []
    if "Coverage" in sec.inputs:
        rows = wb.coverage()
        if rows:
            out.append(_table("Coverage by category", list(C.COVERAGE_COLUMNS),
                              [[r[c] for c in C.COVERAGE_COLUMNS] for r in rows]))
    if "Evidence_Detail" in sec.inputs:
        ev = wb.rows("Evidence_Detail")
        if ev:
            cols = ["E_ID", "Source_Name", "Tier", "Date_Published",
                    "Recency", "Claim_Type", "Origin"]
            out.append(_table("Evidence register", cols,
                              [[e[c] for c in cols] for e in ev]))
    if "Gate_Log" in sec.inputs:
        g = wb.rows("Gate_Log")
        if g:
            cols = ["Gate", "Scope", "Verdict", "Detail"]
            out.append(_table("Gates run on this assessment", cols,
                              [[x[c] for c in cols] for x in g]))
    if "Search_Log" in sec.inputs:
        s = wb.rows("Search_Log")
        cols = ["Seq", "SubCap_ID", "Facet", "Query", "Hits", "Kept", "Outcome"]
        out.append(_table(f"Searches run ({len(s)})", cols,
                          [[x[c] for c in cols] for x in s]))
    scoring = [i for i in sec.inputs if i.endswith("_Subcap_Scoring")]
    if scoring:
        rows = []
        for sheet in scoring:
            for r in wb.rows(sheet):
                claim = str(r.get("Dominant_Claim") or "").strip()
                if not claim:
                    continue
                rows.append([r["SubCap_ID"], r.get("Ceiling_Band"),
                             r.get("Claim_Label"), claim,
                             r.get("Evidence_IDs")])
        if rows:
            out.append(_table("Capability findings",
                              ["SubCap", "Band", "Claim", "Dominant claim",
                               "Evidence"], rows))
    return out


def _table(title, cols, rows) -> dict:
    text = " ".join(str(c) for r in rows for c in r if c is not None)
    return {"title": title, "cols": cols, "rows": rows,
            "words": _words(text),
            "citations": sorted(set(CITE_RE.findall(text)))}


# ── the checks that refuse ───────────────────────────────────────────────

def check(wb: RunWorkbook, curated: dict) -> list[str]:
    spec = curated["spec"]
    register = wb.evidence_index()
    problems: list[str] = []
    total = 0

    for b in curated["blocks"]:
        sec = b["section"]
        total += b["words"]
        if b["words"] < sec.min_words:
            problems.append(
                f"§{sec.id} {sec.heading}: {b['words']} words against a "
                f"blocking minimum of {sec.min_words}. Write it into "
                f"Report_Narrative (Report={spec.key}, Section_ID={sec.id}).")
        dead = [c for c in b["citations"] if c not in register]
        if dead:
            problems.append(
                f"§{sec.id} {sec.heading}: cites {dead}, which do not resolve "
                f"in Evidence_Detail. A citation that opens an empty drawer "
                f"under the client's name is the AUD-0033 defect.")
        if sec.requires_citation and not b["citations"]:
            problems.append(
                f"§{sec.id} {sec.heading}: carries no citation at all.")
        if b["no_source"]:
            problems.append(
                f"§{sec.id} {sec.heading}: every declared input "
                f"{b['declared_inputs']} is empty, so the section has no "
                f"source at all. Populate them or remove the section from "
                f"the spec.")
        if sec.kind in ("insight_card", "recommendation", "finding"):
            n = len([r for r in b["rows"]
                     if str(r.get("Kind") or "") == sec.kind])
            if sec.kind == "insight_card" and n < RS.INSIGHT_CARD_MIN:
                problems.append(
                    f"§{sec.id} {sec.heading}: {n} insight cards against the "
                    f"template's blocking minimum of {RS.INSIGHT_CARD_MIN}.")
            elif sec.kind != "insight_card" and n == 0:
                problems.append(
                    f"§{sec.id} {sec.heading}: no {sec.kind} rows.")
        # Functional language on everything a client reads: report bodies
        # are impact prose by definition, so both tiers apply — verdict
        # words and blame constructions alike
        # (references/functional_language.md).
        for r in b["rows"]:
            why = Q.accusatory(str(r.get("Body") or ""), impact_field=True)
            if why:
                problems.append(
                    f"§{sec.id} {sec.heading}: {why}")
                break

    if total < spec.min_words:
        problems.append(
            f"whole report: {total} words against a blocking minimum of "
            f"{spec.min_words}")
    return problems


# ── rendering ────────────────────────────────────────────────────────────

def render(wb: RunWorkbook, spec: RS.ReportSpec, out_dir: Path,
           *, force: bool = False) -> dict:
    curated = curate(wb, spec)
    problems = check(wb, curated)
    # Every section carries an INDEPENDENT verdict, or the report does not
    # render. AUD-0153: the renderer refused a MISSING section and accepted
    # an unreviewed one, so a report could ship on prose nobody had
    # adversarially read.
    if not force:
        from . import narrative as N
        try:
            N.require_ready(wb, spec.key)
        except N.NarrativeRefusal as e:
            problems = list(problems) + [str(e)]
    if problems and not force:
        raise ReportRefused(
            f"REFUSED: {spec.title} is not renderable yet —\n  "
            + "\n  ".join(problems))
    md = curated["meta"]
    entity = str(md.get("entity_name") or "client")
    name = spec.filename.format(entity=_slug(entity),
                                date=str(md.get("reference_date"))[:10])
    out = Path(out_dir) / name
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()
    _style(doc)
    doc.add_heading(spec.title, level=0)
    p = doc.add_paragraph(entity)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph(
        f"Run {md.get('run_id')} · catalogue {md.get('catalogue_version')} "
        f"({str(md.get('catalogue_hash'))[:12]}) · reference date "
        f"{md.get('reference_date')} · engine {md.get('engine_version')}")
    doc.add_paragraph(
        "Every figure and every citation in this document is read from the "
        "assessment workbook at render time. The report and the workbook "
        "cannot disagree, because there is only one of them.")

    for b in curated["blocks"]:
        sec = b["section"]
        doc.add_heading(f"{sec.id}. {sec.heading}", level=1)
        if b["body"]:
            for para in b["body"].split("\n\n"):
                doc.add_paragraph(para.strip())
        elif force:
            _warn(doc, f"NO SOURCE — §{sec.id} has no narrative in "
                       f"Report_Narrative and its inputs are "
                       f"{list(sec.inputs)}.")
        for t in b["tables"]:
            doc.add_heading(t["title"], level=2)
            _write_table(doc, t)
        if b["no_source"] and force:
            _warn(doc, f"NO SOURCE — every declared input "
                       f"{b['declared_inputs']} is empty for this section.")
        elif b["empty_inputs"]:
            doc.add_paragraph(
                "Scope: this section draws on "
                + ", ".join(i for i in b["declared_inputs"]
                            if i not in b["empty_inputs"])
                + ". Not in this engagement's scope, and therefore not "
                  "reported on: " + ", ".join(b["empty_inputs"]) + ".")

    doc.add_heading("Citations", level=1)
    register = wb.evidence_index()
    used = sorted({c for b in curated["blocks"] for c in b["citations"]})
    if not used:
        _warn(doc, "This report cites nothing.")
    for e in used:
        r = register.get(e, {})
        doc.add_paragraph(
            f"[{e}] {r.get('Source_Name')} — {r.get('Source_URL')} "
            f"(tier {r.get('Tier')}, {r.get('Recency')}, published "
            f"{r.get('Date_Published') or 'undated'})", style="List Bullet")

    doc.save(out)
    return {
        "report": spec.key, "path": str(out), "sections": len(curated["blocks"]),
        "words": sum(b["words"] for b in curated["blocks"]),
        "citations": len(used), "unresolved": [c for c in used
                                               if c not in register],
        "forced": bool(problems and force), "problems": problems,
    }


def _style(doc) -> None:
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)


def _warn(doc, text: str) -> None:
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.color.rgb = RGBColor(0xB0, 0x00, 0x20)


def _write_table(doc, t) -> None:
    table = doc.add_table(rows=1, cols=len(t["cols"]))
    table.style = "Light Grid Accent 1"
    for i, c in enumerate(t["cols"]):
        table.rows[0].cells[i].text = str(c)
    for row in t["rows"]:
        cells = table.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = "" if v is None else str(v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--root")
    ap.add_argument("--report", default="both",
                    choices=["client_research", "assessment", "both"])
    ap.add_argument("--out")
    ap.add_argument("--spec", help="JSON export of a template's control blocks")
    ap.add_argument("--force", action="store_true",
                    help="render anyway, marking every unmet block NO SOURCE")
    a = ap.parse_args(argv)
    r = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = r.open()
    out_dir = Path(a.out) if a.out else r.deliverables
    keys = list(RS.SPECS) if a.report == "both" else [a.report]
    override = RS.from_json(json.loads(Path(a.spec).read_text())) if a.spec else None
    results = []
    for k in keys:
        spec = override if override and override.key == k else RS.SPECS[k]
        results.append(render(wb, spec, out_dir, force=a.force))
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
