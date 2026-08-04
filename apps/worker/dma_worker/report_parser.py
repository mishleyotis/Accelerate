"""Parse the assessment Report.docx into the twelve structured report
sections (Backend Schema: document_sections; PRD artefact table row 2).

The shipped reports number their Heading1 sections 1-12; the number is
the section identity and the mapping below is the vocabulary. Table of
Contents and the appendices sit outside the twelve and are not stored.

Grain: one row per Heading2 subsection (Heading3 headings fold into the
body as `## `-prefixed lines, tables as tab-joined lines), plus one row
for a section's own preamble where it has body text before the first
Heading2. pillar_id is extracted only inside the pillar deep-dive
section — every other section stores NULL, per the schema.

`page` is always None from a .docx parse: the file carries only hard
page breaks (natural text flow adds pages the XML cannot see), and a
page number that is systematically low is a default that looks like
data. A PDF-side parse can supply real pages later.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

SECTION_KINDS = {
    1: "executive_summary",
    2: "methodology",
    3: "trend_analysis",
    4: "issue_register",
    5: "assessment_results",
    6: "pillar_deep_dive",
    7: "benchmark_comparison",
    8: "gap_prioritization",
    9: "recommendations",
    10: "transformation_roadmap",
    11: "data_gaps_confidence",
    12: "evidence_sources",
}

H1_NUM = re.compile(r"^(\d{1,2})\.\s+\S")
DEEP_DIVE_PILLAR = re.compile(r"\(P([1-4])\)")


@dataclass
class ReportSection:
    section_kind: str
    pillar_id: str | None
    heading: str
    body: str
    page: None = None


def _para_text(p) -> str:
    return "".join(t.text or "" for t in p.iter(f"{W}t")).strip()


def _table_lines(tbl) -> list:
    lines = []
    for tr in tbl.iter(f"{W}tr"):
        cells = ["".join(t.text or "" for t in tc.iter(f"{W}t")).strip()
                 for tc in tr.iter(f"{W}tc")]
        if any(cells):
            lines.append("\t".join(cells))
    return lines


def _style(p) -> str | None:
    ps = p.find(f"{W}pPr/{W}pStyle")
    return ps.get(f"{W}val") if ps is not None else None


def parse_report(path: str) -> list:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body_el = root.find(f"{W}body")
    if body_el is None:
        return []

    out: list = []
    kind: str | None = None          # active numbered section, or None
    heading: str | None = None       # active row heading (H1 preamble or H2)
    lines: list = []

    def flush():
        nonlocal lines
        text = "\n".join(l for l in lines if l).strip()
        if kind and heading and text:
            pillar = None
            if kind == "pillar_deep_dive":
                m = DEEP_DIVE_PILLAR.search(heading)
                pillar = f"P{m.group(1)}" if m else None
            out.append(ReportSection(kind, pillar, heading, text))
        lines = []

    for el in body_el:
        if el.tag == f"{W}tbl":
            lines.extend(_table_lines(el))
            continue
        if el.tag != f"{W}p":
            continue
        style, text = _style(el), _para_text(el)
        if style == "Heading1":
            flush()
            m = H1_NUM.match(text)
            kind = SECTION_KINDS.get(int(m.group(1))) if m else None
            heading = text if kind else None
        elif style == "Heading2":
            flush()
            heading = text
        elif style == "Heading3":
            if text:
                lines.append(f"## {text}")
        elif text:
            lines.append(text)
    flush()
    return out
