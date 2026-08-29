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

# ── the number is not the identity ──────────────────────────────────────
#
# AUD-0039: this parser mapped Heading1 NUMBER -> kind, against a report
# whose sections were numbered 1-12. The pinned v8 Assessment Report has a
# different order and a different count, so on a v8 report EVERY SECTION FROM
# §3 ON was stored under the wrong kind: §3 "Maturity by pillar" landed as
# `trend_analysis`, §5 "Findings" as `assessment_results`, and so on down.
# Nothing was lost — which is worse, because a wrongly-kinded section reads
# as a correctly-kinded one to every consumer.
#
# So the HEADING decides, and the number is only a fallback for a heading
# nothing recognises. A section that matches neither is stored under its own
# derived kind with the heading preserved, and an observation says so —
# never silently assigned to whatever the count happened to reach.
_TITLE_KINDS = (
    (r"executive\s+summary", "executive_summary"),
    (r"\bmethod(olog)?y|scope\s+and\s+limits|method,\s*scope", "methodology"),
    (r"trend|trajector", "trend_analysis"),
    (r"issue\s+register|open\s+matters", "issue_register"),
    (r"maturity\s+by\s+pillar|assessment\s+results|scores?\s+by\s+pillar",
     "assessment_results"),
    (r"pillar\s+deep[\s-]?dive|deep[\s-]?dive", "pillar_deep_dive"),
    (r"peer\s+position|benchmark|peer\s+comparison", "benchmark_comparison"),
    (r"gap\s+prioriti|priorit", "gap_prioritization"),
    (r"recommendation", "recommendations"),
    (r"roadmap|transformation\s+plan|sequenc", "transformation_roadmap"),
    (r"data\s+gaps?|confidence|what\s+would\s+change|limits\s+of\s+the\s+evidence",
     "data_gaps_confidence"),
    (r"evidence\s+(and|sources?|base)|citations?|sources?\s+cited",
     "evidence_sources"),
    (r"\bfinding", "findings"),
)
_TITLE_RES = [(re.compile(rx, re.I), kind) for rx, kind in _TITLE_KINDS]

_KIND_SLUG = re.compile(r"[^a-z0-9]+")


#: Heading1 blocks that are not report sections. UNNUMBERED front and back
#: matter was already out of scope by construction (no number, no kind) and
#: stays out: the derived-kind fallback below applies to NUMBERED sections
#: only, which is where AUD-0039's mis-filing happened.
_OUT_OF_SCOPE = re.compile(
    r"^\s*(table\s+of\s+contents|contents|appendix\b|glossary|"
    r"document\s+control|revision\s+history)", re.I)


def section_kind_for(number: int | None, heading: str) -> tuple:
    """(kind, basis) for a Heading1. `basis` names what decided it.

    Heading text first, number second, and a derived slug last — because a
    NUMBERED section this vocabulary has never seen is a new section, and
    filing it under whichever name the count reached is the AUD-0039 defect.

    An UNNUMBERED heading is front or back matter and returns (None, …), as
    it always did: the table of contents and the appendices are not report
    sections and storing them would be a different defect."""
    title = re.sub(r"^\d{1,2}[.)]\s*", "", heading or "").strip()
    if _OUT_OF_SCOPE.match(title) or number is None:
        return None, "out_of_scope"
    for rx, kind in _TITLE_RES:
        if rx.search(title):
            return kind, "heading"
    # NO NUMBER FALLBACK. Every one of the legacy twelve names matches its
    # own pattern above (asserted in test_report_parser), so reaching here
    # means the heading is one this vocabulary has genuinely never seen —
    # and filing THAT under whichever numbered name the count reached is
    # precisely AUD-0039. It gets its own kind, derived from its own
    # heading, and an observation names it.
    slug = _KIND_SLUG.sub("_", title.lower()).strip("_")[:60]
    return (f"unmapped:{slug}" if slug else None), "unmapped"


@dataclass
class Observation:
    """What the reader could not recognise, in the shape persist stores.

    Deliberately structural, not a dict: `persist_package` drains
    `companion_observations` and reads `.kind`, `.subcap_id` and `.detail`
    off each item."""
    kind: str
    subcap_id: str | None
    detail: dict


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


def parse_report(path: str, observations: list | None = None) -> list:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body_el = root.find(f"{W}body")
    if body_el is None:
        return []

    out: list = []
    unmapped: list = []              # headings this vocabulary has not seen
    kind: str | None = None          # active section, or None
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
            kind, basis = section_kind_for(
                int(m.group(1)) if m else None, text)
            if basis == "unmapped" and kind:
                unmapped.append({"heading": text, "stored_as": kind})
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
    if unmapped and observations is not None:
        # The SAME shape persist writes (`o.kind`, `o.subcap_id`, `o.detail`),
        # because `companion_observations` is a single list drained into
        # parser_observations — a dict here would raise on `o.kind` at the
        # end of a package ingest, which is the worst place to find out.
        observations.append(Observation(
            kind="report_section_unmapped",
            subcap_id=None,
            detail={
                "count": len(unmapped), "sections": unmapped[:8],
                "reason": "these Heading1 sections match no kind in the "
                          "vocabulary. They are stored under a kind derived "
                          "from their own heading, NOT under whichever "
                          "numbered name the count reached — that "
                          "substitution is what stored every v8 section from "
                          "the third onward under the wrong kind.",
            }))
    return out
