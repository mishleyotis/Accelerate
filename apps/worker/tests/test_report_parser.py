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


# ── AUD-0039 · the number is not the identity ───────────────────────────

def test_a_v8_report_is_kinded_by_heading_not_by_count(tmp_path):
    """The measured defect: this parser mapped Heading1 NUMBER -> kind
    against a 12-section report, so on the pinned v8 report every section
    from §3 on was stored under the wrong kind. §3 "Maturity by pillar"
    landed as `trend_analysis` — and nothing was lost, which is worse,
    because a wrongly-kinded section reads as a correct one."""
    body = (
        _p("1. Executive summary", "Heading1")
        + _p("What we found", "Heading2") + _p("The bank is Building.")
        + _p("3. Maturity by pillar", "Heading1")
        + _p("P1", "Heading2") + _p("Strategy scores 2.1.")
        + _p("5. Findings", "Heading1")
        + _p("Finding 1", "Heading2") + _p("The register is thin.")
        + _p("7. Recommendations", "Heading1")
        + _p("Rec 1", "Heading2") + _p("Consolidate the estate.")
        + _p("8. What would change this assessment", "Heading1")
        + _p("Limits", "Heading2") + _p("Two categories are unevidenced.")
    )
    rows = parse_report(_docx(tmp_path, body))
    kinds = [r.section_kind for r in rows]
    assert kinds == ["executive_summary", "assessment_results", "findings",
                     "recommendations", "data_gaps_confidence"]
    assert "trend_analysis" not in kinds


def test_the_legacy_twelve_section_report_still_maps(tmp_path):
    """The control: the numbered vocabulary must keep working, because the
    corpus is full of reports written to it."""
    body = (
        _p("3. Trend Analysis", "Heading1")
        + _p("Trajectory", "Heading2") + _p("Scores rose.")
        + _p("6. Pillar Deep Dives (P2)", "Heading1")
        + _p("Pillar 2 (P2)", "Heading2") + _p("Detail.")
    )
    rows = parse_report(_docx(tmp_path, body))
    assert [(r.section_kind, r.pillar_id) for r in rows] == [
        ("trend_analysis", None), ("pillar_deep_dive", "P2")]


def test_an_unrecognised_numbered_section_keeps_its_own_name(tmp_path):
    body = (_p("9. Acquisition history and integration debt", "Heading1")
            + _p("Acquisitions", "Heading2") + _p("Three since 2019."))
    obs = []
    rows = parse_report(_docx(tmp_path, body), obs)
    assert rows[0].section_kind.startswith("unmapped:"), rows[0].section_kind
    assert "acquisition" in rows[0].section_kind
    assert obs and obs[0].kind == "report_section_unmapped"


def test_front_and_back_matter_stay_out_of_scope(tmp_path):
    body = (_p("Table of Contents", "Heading1") + _p("1. Exec ... 3")
            + _p("Appendix A: Capability Definitions", "Heading1")
            + _p("Defs", "Heading2") + _p("Never stored.")
            + _p("Glossary", "Heading1") + _p("Terms", "Heading2") + _p("x"))
    obs = []
    assert parse_report(_docx(tmp_path, body), obs) == []
    assert obs == [], "front matter is out of scope, not an unmapped section"


def test_every_legacy_kind_is_reachable_from_its_own_heading():
    """The number fallback was removed, so this is what keeps the legacy
    twelve working: each name must match its own title pattern."""
    from dma_worker.report_parser import SECTION_KINDS, section_kind_for
    for n, kind in SECTION_KINDS.items():
        title = f"{n}. " + kind.replace("_", " ").title()
        assert section_kind_for(n, title) == (kind, "heading"), title
