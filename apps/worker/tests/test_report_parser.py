"""Stage 1.3 report parsing — the twelve structured sections, without IO
beyond a synthetic .docx built in-test (client reports never enter the
repo)."""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.report_parser import SECTION_KINDS, parse_report

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CONTENT_TYPES = """<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="xml" ContentType="application/xml"/>
 <Override PartName="/word/document.xml"
  ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

RELS = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Target="word/document.xml"
  Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>
</Relationships>"""


def _p(text, style=None):
    pr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{pr}<w:r><w:t>{text}</w:t></w:r></w:p>"


def _tbl(rows):
    trs = "".join(
        "<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>"
                           for c in row) + "</w:tr>"
        for row in rows)
    return f"<w:tbl>{trs}</w:tbl>"


def _docx(tmp_path, body_xml):
    doc = (f'<?xml version="1.0"?><w:document xmlns:w="{W}">'
           f"<w:body>{body_xml}</w:body></w:document>")
    path = tmp_path / "report.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", doc)
    return str(path)


def test_twelve_kinds_and_out_of_scope_content_is_skipped(tmp_path):
    body = (
        _p("Table of Contents", "Heading1") + _p("1. Executive Summary ... 3")
        + _p("1. Executive Summary", "Heading1")
        + _p("SCQA Context", "Heading2") + _p("Situation. A bank exists.")
        + _p("12. Evidence Sources", "Heading1")
        + _p("Sources", "Heading2") + _p("E-001 Annual Report")
        + _p("Appendix A: Capability Definitions", "Heading1")
        + _p("Defs", "Heading2") + _p("Never stored.")
    )
    rows = parse_report(_docx(tmp_path, body))
    assert [(r.section_kind, r.heading) for r in rows] == [
        ("executive_summary", "SCQA Context"),
        ("evidence_sources", "Sources"),
    ]
    # ToC body ("1. Executive Summary ... 3") and appendix content are absent
    assert all("Never stored" not in r.body and "... 3" not in r.body for r in rows)


def test_preamble_pillars_tables_and_page_semantics(tmp_path):
    body = (
        _p("6. Pillar Deep Dives", "Heading1")
        + _p("Read each pillar against its peer cohort.")     # section preamble
        + _p("Pillar 2: Member/Customer Experience (P2) — Score 1.51", "Heading2")
        + _p("Capability Scorecard", "Heading3")
        + _tbl([["Capability", "Score"], ["P2C1.1", "1.4"]])
        + _p("What We See", "Heading3") + _p("Narrow channels.")
        + _p("8. Gap Prioritization", "Heading1")
        + _p("Gap Priority Register", "Heading2")
        + _p("P1C1 leads at priority 7.5.")
    )
    rows = parse_report(_docx(tmp_path, body))
    pre, dive, gap = rows
    assert pre.heading == "6. Pillar Deep Dives" and pre.pillar_id is None
    assert dive.pillar_id == "P2"
    assert "## Capability Scorecard" in dive.body        # H3 folded into body
    assert "P2C1.1\t1.4" in dive.body                    # table rows kept
    # pillar ids stay NULL outside the deep-dive section, whatever the prose
    assert gap.section_kind == "gap_prioritization" and gap.pillar_id is None
    assert all(r.page is None for r in rows)             # computed or null


def test_the_vocabulary_is_exactly_twelve():
    assert len(SECTION_KINDS) == 12
    assert len(set(SECTION_KINDS.values())) == 12
