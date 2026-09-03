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


#: A section's declared block, as `narrative.write` requires it in the body.
_BLOCK_LINE = re.compile(r"^\s*##\s+(.+?)\s*$")


def _emit_body(doc, body: str) -> None:
    """Write a section body, promoting its `## ` block lines to Heading2.

    The blocks are not decoration. The app parses a report at Heading2
    grain (`report_parser`) and scopes its vectors from tokens inside those
    headings (`embed._PILLAR_TOKEN`), so a section rendered as one
    undivided run of paragraphs arrives as a single row belonging to no
    pillar — which is what every section did before `Section.blocks`
    existed. Promoting them here is what makes the declared anatomy real in
    the artefact rather than only in the workbook.
    """
    buf: list[str] = []

    def flush():
        if buf:
            doc.add_paragraph("\n".join(buf).strip())
            buf.clear()

    for line in (body or "").splitlines():
        m = _BLOCK_LINE.match(line)
        if m:
            flush()
            doc.add_heading(m.group(1), level=2)
        elif not line.strip():
            flush()
        else:
            buf.append(line)
    flush()


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

    from . import narrative as _N
    for b in curated["blocks"]:
        sec = b["section"]
        total += b["words"]
        if b["words"] < _N.min_words_for(wb, sec):
            problems.append(
                f"§{sec.id} {sec.heading}: {b['words']} words against a "
                f"blocking minimum of {_N.min_words_for(wb, sec)}. Write it into "
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
        if sec.kind in RS.CARD_KINDS:
            n = len([r for r in b["rows"]
                     if str(r.get("Kind") or "") == sec.kind])
            floor = _N.card_floor_for(wb, sec)
            if n < floor:
                problems.append(
                    f"§{sec.id} {sec.heading}: {n} {sec.kind.replace('_', ' ')}"
                    f"(s) against the template's blocking minimum of "
                    f"{floor}.")
            elif sec.cards_max and n > int(sec.cards_max):
                problems.append(
                    f"§{sec.id} {sec.heading}: {n} {sec.kind}s, the template "
                    f"allows at most {sec.cards_max}.")
        # The countable MINIMUM DATA / MUST NOT rules of the Doc's control
        # block, re-checked on what will actually be rendered.
        whole = "\n".join(str(r.get("Body") or "") for r in b["rows"])
        for why in _N._check_counts(sec, whole, per_card=False):
            problems.append(f"§{sec.id} {sec.heading}: {why}")
        if sec.kind in RS.CARD_KINDS:
            for r in b["rows"]:
                for why in _N._check_counts(sec, str(r.get("Body") or ""),
                                            per_card=True):
                    problems.append(
                        f"§{sec.id} {sec.heading} card "
                        f"{r.get('Card_ID')}: {why}")
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

    if total < _N.report_min_words_for(wb, spec):
        problems.append(
            f"whole report: {total} words against a blocking minimum of "
            f"{_N.report_min_words_for(wb, spec)}")
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
    _brand(doc, spec, entity, md)
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
    _front_matter(doc, wb, spec, md)

    for b in curated["blocks"]:
        sec = b["section"]
        doc.add_heading(f"{sec.id}. {sec.heading}", level=1)
        if sec.kind in RS.CARD_KINDS and b["rows"]:
            _emit_cards(doc, wb, sec, b["rows"])
        elif b["body"]:
            _emit_body(doc, b["body"])
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

    doc.add_heading("Sources cited", level=1)
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


def _brand(doc, spec, entity: str, md: dict) -> None:
    """The branded chrome the reference package carries (header1.xml), so the
    document is authored INTO a template rather than as a blank `Document()`
    — goeasy GSY-05, gold gate GS-RPT-BRANDING."""
    sec = doc.sections[0]
    h = sec.header.paragraphs[0] if sec.header.paragraphs else sec.header.add_paragraph()
    h.text = f"Zennify · Digital Maturity Assessment · {spec.title} · {entity}"
    h.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for r in h.runs:
        r.font.size = Pt(8)
        r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    f = sec.footer.paragraphs[0] if sec.footer.paragraphs else sec.footer.add_paragraph()
    f.text = (f"Run {md.get('run_id')} · catalogue {md.get('catalogue_version')} "
              f"({str(md.get('catalogue_hash'))[:8]}) · prepared by Zennify "
              f"Digital Maturity Assessment · confidential")
    f.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r in f.runs:
        r.font.size = Pt(8)


def _front_matter(doc, wb, spec, md: dict) -> None:
    """The Doc's two unnumbered front sections, filled from the run.

    'Document Control and Catalogue Binding' resolves every value from the
    workbook — nothing typed — and 'Surface Alignment' is the Doc's own
    section -> app-surface table, rendered from the pinned spec so it cannot
    drift from what the sections declare they feed. Unnumbered Heading1s are
    front matter to the app's parser and are never stored as sections."""
    doc.add_heading("Document Control and Catalogue Binding", level=1)
    doc.add_paragraph(
        "Every value below is resolved at render time from the run's own "
        "workbook and the active catalogue. Nothing here is typed by hand.")
    tax = C.taxonomy()
    lock = wb.handoff_lock()
    rows = [
        ["Catalogue version", str(md.get("catalogue_version"))],
        ["Catalogue content hash", str(md.get("catalogue_hash"))],
        ["Structure counts", f"{tax.n_pillars} pillars / {tax.n_categories} "
                             f"categories / {tax.n_capabilities} capabilities / "
                             f"{tax.n_cells} subcapabilities"],
        ["Sub-vertical", str(md.get("sub_vertical") or "")],
        ["Evidence mode", str(md.get("evidence_mode") or "")],
        ["Scope", f"{md.get('scope_mode')} — {md.get('subcaps_selected')} "
                  f"subcapabilities selected"],
        ["Reference date", str(md.get("reference_date"))],
        ["Workbook contract", f"{md.get('workbook_contract')} · engine "
                              f"{md.get('engine_version')}"],
        ["Scoring workbook", wb.path.name],
        ["Template binding", str(md.get("template_binding") or "UNBOUND")],
        ["Peer set", str(lock.get("locked_peer_set") or "not locked")],
        ["Stage", str(md.get("stage") or "research")],
    ]
    _write_table(doc, {"cols": ["Field", "Value"], "rows": rows})
    doc.add_heading("Surface Alignment", level=1)
    doc.add_paragraph(
        "This report is one input to the DMA Insights app. Each section "
        "feeds the named app surfaces; producing a section without knowing "
        "what it feeds is how a report and a dashboard end up disagreeing "
        "under the same client name.")
    _write_table(doc, {
        "cols": ["Section", "Feeds app surface"],
        "rows": [[f"{s.id}. {s.heading}",
                  ", ".join(s.surfaces) or "No served surface; internal"]
                 for s in spec.sections]})


def _card_heading(wb, sec, row) -> str:
    """The Doc's own heading for one card — '5.N Pillar deep dive (P1): …'
    with the served score and median, or 'REC-NN: Title'."""
    card = str(row.get("Card_ID") or "").strip()
    title = str(row.get("Heading") or "").strip()
    if sec.kind == "pillar":
        n = card[1:] if card.startswith("P") else "?"
        score = median = gap = "—"
        for r in wb.rows("Pillar_Rollup"):
            if str(r.get("pillar_id") or "").strip() == card:
                score = str(r.get("score") or "—")
                median = str(r.get("peer_median") or "—")
                gap = str(r.get("gap") or "—")
        name = C.PILLAR_NAMES.get(card, title or card)
        # '(P1)' is the token the app's parser (DEEP_DIVE_PILLAR) and the
        # embedder (_PILLAR_TOKEN) scope on; it stays in the heading.
        return (f"{sec.id}.{n} Pillar deep dive ({card}): {name} — score "
                f"{score} against median {median} ({gap})")
    if title and title != sec.heading and not title.startswith(card):
        return f"{card}: {title}"
    return title or card


def _emit_cards(doc, wb, sec, rows) -> None:
    """A list section: one Heading2 per card, its blocks as Heading3s.

    That is the Doc's shape ('## 5.N …' / '### Capability scorecard';
    '## REC-NN: …' / '#### Root cause') and the grain the app parses: rows
    land per Heading2, so a pillar's four blocks arrive under one heading
    carrying its pillar token, and a recommendation's under its REC id."""
    def key(r):
        c = str(r.get("Card_ID") or "")
        m = re.search(r"(\d+)$", c)
        return (0, int(m.group(1))) if m else (1, c)
    for r in sorted(rows, key=key):
        doc.add_heading(_card_heading(wb, sec, r), level=2)
        buf: list[str] = []

        def flush():
            if buf:
                doc.add_paragraph("\n".join(buf).strip())
                buf.clear()
        for line in str(r.get("Body") or "").splitlines():
            m = _BLOCK_LINE.match(line)
            if m:
                flush()
                doc.add_heading(m.group(1), level=3)
            elif not line.strip():
                flush()
            else:
                buf.append(line)
        flush()


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
