"""A report can pass every volume floor and still be the wrong SHAPE.

THE DEFECT THESE TESTS PIN, measured 2026-09-06 on a delivered pair of reports
that the gate of the day passed with zero findings:

    assessment   50 tables against the reference's 92, paragraph words 1.57x
    research     26 tables against the reference's 39, paragraph words 1.57x

The owner's report was "the 2 reports lack depth ... do not adhere to template
requirements eg where tables are, I see paragraphs." The gate counted words,
citations and section headings, none of which can tell a report that TABULATES
its register from one that describes it in a paragraph — and because more prose
raises a word count, the defect was not merely uncaught, it was REWARDED.

The root cause was in the renderer, not the writer: `reports._emit_body` turned
every body line into a paragraph, so the only tables a report could contain were
the whole sheets `_tables_for` emits per declared input (~44 for the assessment).
Golden 1 carries 92, so roughly half of the reference's tables are AUTHORED
inside section bodies — which the renderer had no way to produce. A writer asked
for a table could not make one.

So three things are asserted here: the new gates catch the shape, the renderer
can now render an authored table, and the anti-patterns reach the writer before
it writes (engine/authoring.py) rather than only the gate after it ships.
"""
from __future__ import annotations

import json
import zipfile

import pytest

from engine import authoring as A
from engine import gold_standard as GS
from engine import report_spec as RS
from engine import reports as R
from engine import template as T


@pytest.fixture(scope="module")
def gold() -> dict:
    return json.loads((T.TEMPLATES_DIR / "gold_reference.json").read_text())


# ── the calibration discipline, extended to the structure floors ──────────

def test_the_table_floor_is_at_or_below_what_golden_1_meets(gold):
    """The rule gold_standard.py has stated since it was written: a floor the
    reference itself would fail is a floor nobody measured."""
    for kind in ("research", "assessment"):
        floors = GS.depth_floors(kind)
        assert floors["tables"] <= gold["reports"][kind]["tables"], (kind, floors)


def test_the_prose_and_dump_limits_do_not_refuse_the_reference(gold):
    for kind in ("research", "assessment"):
        ref = gold["reports"][kind]
        floors = GS.depth_floors(kind)
        # The reference's own prose sits inside the inflation limit …
        assert ref["words_paragraphs"] <= (
            floors["reference_paragraph_words"] * GS.PROSE_INFLATION_LIMIT)
        # … and its own average table is, by construction, 1x its average.
        assert GS._gold_avg_table_words(kind) >= 1


def test_the_table_floor_scales_with_the_run_and_never_vanishes():
    small = GS.depth_floors("assessment", subcaps=6)
    full = GS.depth_floors("assessment")
    assert 1 <= small["tables"] < full["tables"]


# ── fixtures: a report of a chosen shape ──────────────────────────────────

def _report(path, *, tables, rows_per_table, prose_words, kind="assessment"):
    """A synthetic report carrying an exact number of tables of an exact size,
    and an exact quantity of prose — so a shape finding can be provoked or
    avoided on purpose."""
    import docx
    d = docx.Document()
    for h in RS.numbered_headings(kind if kind == "assessment" else "client_research"):
        d.add_paragraph(h, style="Heading 1")
    # citations, so the volume gates are not what fires
    d.add_paragraph(" ".join(f"[E-{i}]" for i in range(1, 200)))
    d.add_paragraph(" ".join(["word"] * prose_words))
    for _ in range(tables):
        t = d.add_table(rows=1, cols=3)
        for i, c in enumerate(("A", "B", "C")):
            t.rows[0].cells[i].text = c
        for _ in range(rows_per_table):
            cells = t.add_row().cells
            for i in range(3):
                cells[i].text = "cell value here"
    d.save(str(path))
    with zipfile.ZipFile(str(path), "a") as z:
        z.writestr("word/header1.xml", "<hdr/>")
    return path


def _codes(path, kind="assessment", subcaps=690):
    return {f["code"] for f in GS.report_findings(path, kind=kind, subcaps=subcaps)}


# ── detection ─────────────────────────────────────────────────────────────

def test_prose_where_a_table_belongs_is_refused(tmp_path):
    """Few tables, inflated prose — the delivered pair's exact shape."""
    p = _report(tmp_path / "thin.docx", tables=50, rows_per_table=2,
                prose_words=20000)
    codes = _codes(p)
    assert "GS-RPT-TABLES" in codes
    assert "GS-RPT-PROSE-FOR-STRUCTURE" in codes


def test_a_sheet_emitted_whole_is_refused(tmp_path):
    """Enough tables, but each one is a pasted sheet rather than an extract."""
    p = _report(tmp_path / "dump.docx", tables=92, rows_per_table=400,
                prose_words=11000)
    assert "GS-RPT-TABLE-DUMP" in _codes(p)


def test_a_report_of_the_reference_shape_passes_every_structure_gate(tmp_path):
    """The floors must be reachable: a report built to Golden 1's own measured
    shape raises none of the three structure findings."""
    p = _report(tmp_path / "good.docx", tables=92, rows_per_table=3,
                prose_words=11000)
    codes = _codes(p)
    for code in ("GS-RPT-TABLES", "GS-RPT-PROSE-FOR-STRUCTURE",
                 "GS-RPT-TABLE-DUMP"):
        assert code not in codes, (code, codes)


def test_long_prose_alone_is_not_refused_when_the_tables_are_there(tmp_path):
    """The finding is prose STANDING IN FOR structure, not prose. A section
    that tabulates what it should and still argues at length is not the
    defect, and a gate that punished it would push producers to cut analysis."""
    p = _report(tmp_path / "rich.docx", tables=92, rows_per_table=3,
                prose_words=30000)
    assert "GS-RPT-PROSE-FOR-STRUCTURE" not in _codes(p)


# ── the root cause: a writer can now author a table ───────────────────────

def test_an_authored_pipe_table_renders_as_a_real_table():
    """Before 2026-09-06 this rendered as a paragraph of pipe characters, so a
    writer asked for a table could not produce one and wrote prose instead."""
    import docx
    d = docx.Document()
    R._emit_body(d, "## Capability scorecard\n\n"
                    "| Cell | Score | Peer |\n"
                    "|---|---|---|\n"
                    "| P4C1.2.1 | 1.6 | 3.0 |\n"
                    "| P4C1.2.2 | 1.25 | 3.0 |\n\n"
                    "The scorecard above states the two cells this rests on.")
    assert len(d.tables) == 1
    t = d.tables[0]
    assert [c.text for c in t.rows[0].cells] == ["Cell", "Score", "Peer"]
    assert t.rows[1].cells[0].text == "P4C1.2.1"
    # the prose after the table is still a paragraph, not swallowed by it
    assert any("states the two cells" in p.text for p in d.paragraphs)


def test_prose_that_merely_contains_a_pipe_is_still_a_paragraph():
    import docx
    d = docx.Document()
    R._emit_body(d, "The estate splits OPS | CUST | DATA across four layers.")
    assert len(d.tables) == 0
    assert any("four layers" in p.text for p in d.paragraphs)


# ── the anti-patterns reach the writer BEFORE it writes ───────────────────

def test_every_antipattern_names_a_gate_and_a_repair():
    pats = A.antipatterns()
    assert pats, "the anti-pattern register must not be empty"
    for a in pats:
        for field in ("id", "gate", "what", "measured", "repair"):
            assert a.get(field), (a.get("id"), field)


def test_the_register_covers_every_structure_gate():
    """A gate with no entry in the register is a rule the writer is never told
    about until it refuses them."""
    gates = {a["gate"] for a in A.antipatterns()}
    for code in ("GS-RPT-TABLES", "GS-RPT-PROSE-FOR-STRUCTURE",
                 "GS-RPT-TABLE-DUMP"):
        assert code in gates, (code, gates)


def test_the_brief_binds_the_antipatterns_to_this_sections_own_tables():
    """A general rule is advice; the section's own declared inputs are an
    instruction. §6 of the assessment declares the technology estate sheets."""
    text = A.brief("assessment", "6")
    assert "Benchmark and Technology Estate" in text
    assert "TABLES THIS SECTION OWES" in text
    for sheet in A.table_inputs(
            next(s for s in RS.SPECS["assessment"].sections if str(s.id) == "6")):
        assert sheet in text
    for a in A.antipatterns():
        assert a["id"] in text


def test_the_brief_names_an_empty_declared_input_as_the_thing_to_fix_first():
    """An input that carries no rows renders no table, and the section then
    'lacks a table' for a reason no amount of writing can repair."""
    class _WB:
        def rows(self, name):
            return [] if name == "Tech_Register" else [{"x": 1}]

    text = A.brief("assessment", "6", _WB())
    assert "Tech_Register" in text
    assert "EMPTY" in text
    ob = A.section_obligations("assessment", "6", _WB())
    assert "Tech_Register" in ob["tables_empty"]
    assert "Tech_Register" not in ob["tables_that_will_render"]


def test_preflight_reports_the_whole_reports_table_position():
    class _WB:
        def rows(self, name):
            return [{"x": 1}]

    out = A.preflight("assessment", _WB())
    assert out["tables_declared"] > 0
    assert out["tables_that_will_render"] == out["tables_declared"]
    assert out["empty_declared_inputs"] == []
    assert len(out["sections"]) == len(RS.SPECS["assessment"].sections)
