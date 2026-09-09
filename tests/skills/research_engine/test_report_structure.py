"""A report section has an ANATOMY, an APP COUNTERPART, and — where it is a
list — a card per row.

WHY THESE EXIST. The 2026-08-30 audit asked how each report section is
structured and how it aligns to the app, and the honest answer was: it
wasn't, and it didn't.

  · `Section` carried a heading, a word floor and its input sheets. Nothing
    anywhere said what a section CONTAINS. The generated agent tables printed
    the heading under a column headed "what it must argue", and the seven
    apparatus bullets under it were byte-identical for all sixteen.
  · The measurable consequence was in the artefact: the renderer emitted body
    paragraphs with no Heading2 of their own, so the app's Heading2-grained
    parser stored each section as one undifferentiated row that belonged to
    no pillar, and `embed.py` scoped every section at run level.
  · The legacy app had an explicit section→surface table. The current build
    lost it; what replaced it was prose in the page packs naming sections by
    description, several of which named sections that no longer exist.
  · And `narrative.write` UPDATED rather than appended whenever a row for
    that section already existed — so eight writes to the eight-card section
    produced one row, and `reports.check`'s blocking minimum of eight was
    unreachable through the only sanctioned writer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import narrative as N
from engine import report_spec as RS
from engine import reports as R

from fixtures import bank_evidence, new_run, report_ready_run


# ── every section declares its anatomy and its counterpart ───────────────

def test_every_section_declares_the_blocks_it_is_written_in():
    thin = [f"{k} §{s.id}" for k, spec in RS.SPECS.items()
            for s in spec.sections if not s.blocks]
    assert not thin, ("these sections declare no anatomy, so nothing tells a "
                      "producer what they contain: " + ", ".join(thin))


def test_every_section_that_feeds_the_app_names_the_surfaces_it_feeds():
    """Two sections legitimately feed no surface, and the Doc says so in
    their own control blocks: the research profile's §8 is the artefact
    index, and the assessment's §2 Methodology "exists for the reader of the
    document, not the app". Every other section is read by a surface, and
    says which."""
    unmapped = [f"{k} §{s.id} {s.heading}" for k, spec in RS.SPECS.items()
                for s in spec.sections if not s.surfaces]
    assert unmapped == ["client_research §8 Workbook References",
                        "assessment §2 Assessment Methodology"], (
        f"a section with no app counterpart is either a hole in the map or "
        f"prose nobody reads: {unmapped}")


def test_the_pillar_deep_dive_headings_carry_the_token_the_app_scopes_on(tmp_path):
    """`embed._PILLAR_TOKEN` looks for `(P1)`..`(P4)` in a heading, and the
    per-pillar deep dives are the ones whose vectors should be pillar-scoped.
    The Doc's own heading for a deep dive is one per pillar card; the
    renderer's heading for that card is what carries the token."""
    run = report_ready_run(tmp_path)
    wb = run.open()
    sec = next(s for s in RS.SPECS["assessment"].sections if s.kind == "pillar")
    for p in ("P1", "P2", "P3", "P4"):
        h = R._card_heading(wb, sec, {"Card_ID": p, "Heading": ""})
        assert f"({p})" in h, h
        assert h.startswith(f"{sec.id}."), h


def test_the_generated_agents_do_not_drift_from_the_spec():
    """`gen_report_agents.py --check` is the build's guard; run it here so a
    spec change that forgets to regenerate fails the suite, not the deploy."""
    import subprocess
    import sys
    from pathlib import Path
    script = (Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
              / "scripts" / "gen_report_agents.py")
    out = subprocess.run([sys.executable, str(script), "--check"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


# ── the anatomy is enforced at the write ─────────────────────────────────

from fixtures import section_record as _rec  # noqa: E402  (shared with test_scoring_stage)


def test_a_body_without_its_blocks_is_refused(tmp_path):
    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    rec = _rec("3", eids)
    rec["Body"] = rec["Body"].replace("## ", "")
    with pytest.raises(N.NarrativeRefusal, match="missing the block heading"):
        N.write(wb, "client_research", "3", rec, actor="report-research-producer")


def test_blocks_out_of_order_are_refused(tmp_path):
    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    sec = RS.SPECS["client_research"].section("3")
    rec = _rec("3", eids)
    lines = rec["Body"].splitlines()
    # swap the first and last block headings
    first = lines.index(f"## {sec.blocks[0]}")
    last = lines.index(f"## {sec.blocks[-1]}")
    lines[first], lines[last] = lines[last], lines[first]
    rec["Body"] = "\n".join(lines)
    with pytest.raises(N.NarrativeRefusal, match="out of order"):
        N.write(wb, "client_research", "3", rec, actor="report-research-producer")


def test_the_written_body_keeps_its_line_structure(tmp_path):
    """`_clean` collapses every run of whitespace, newlines included. Applied
    to Body it deleted the very structure the same module then refused the
    body for lacking."""
    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    N.write(wb, "client_research", "3", _rec("3", eids),
            actor="report-research-producer")
    row = N.rows_for(wb, "client_research")["3"]
    assert row["Body"].startswith("## ")
    sec = RS.SPECS["client_research"].section("3")
    assert len(N.blocks_in(row["Body"])) == len(sec.blocks) == 4


# ── a list section is a list ─────────────────────────────────────────────

#: The Doc's two list sections are both in the ASSESSMENT report: §5 is one
#: deep dive per pillar (P1..P4) and §8 is REC-NN, five to eight of them. The
#: research profile's insight cards live INSIDE its §5 passage as IC-NNN ids
#: (a countable check), not as rows.
REC = RS.SPECS["assessment"].section("8")


def test_a_list_section_refuses_a_write_with_no_card_id(tmp_path):
    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    with pytest.raises(N.NarrativeRefusal, match="needs its own --card"):
        N.write(wb, "assessment", REC.id, _rec(REC.id, eids, report="assessment"),
                actor="report-assessment-producer")


def test_a_card_id_must_wear_the_docs_shape(tmp_path):
    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    with pytest.raises(N.NarrativeRefusal, match="REC-"):
        N.write(wb, "assessment", REC.id, _rec(REC.id, eids, report="assessment"),
                actor="report-assessment-producer", card="IC-1")
    with pytest.raises(N.NarrativeRefusal, match="no selected subcapability"):
        N.write(wb, "assessment", "5", _rec("5", eids, report="assessment"),
                actor="report-assessment-producer", card="P3")


def test_a_passage_section_refuses_a_card_id(tmp_path):
    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    with pytest.raises(N.NarrativeRefusal, match="--card does not"):
        N.write(wb, "client_research", "3", _rec("3", eids),
                actor="report-research-producer", card="IC-1")


def test_five_cards_land_as_five_rows(tmp_path):
    """The floor `reports.check` enforces was unreachable through the only
    sanctioned writer: every write overwrote the last, so the section held
    one row against a blocking minimum. The Doc's floor for §8 is five."""
    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    floor = REC.card_floor
    assert floor == 5 and REC.cards_max == 8
    for i in range(floor):
        out = N.write(wb, "assessment", REC.id, _rec(REC.id, eids, report="assessment"),
                      actor="report-assessment-producer", card=f"REC-{i + 1:02d}")
    assert out["cards_in_section"] == floor
    rows = N.all_rows_for(wb, "assessment")[REC.id]
    assert len(rows) == floor
    assert {r["Card_ID"] for r in rows} == {f"REC-{i + 1:02d}" for i in range(floor)}
    # and rewriting one card touches only that card
    N.write(wb, "assessment", REC.id, _rec(REC.id, eids, report="assessment"),
            actor="report-assessment-producer", card="REC-03")
    assert len(N.all_rows_for(wb, "assessment")[REC.id]) == floor
    # a ninth card is refused: the Doc allows at most eight
    for i in range(floor, REC.cards_max):
        N.write(wb, "assessment", REC.id, _rec(REC.id, eids, report="assessment"),
                actor="report-assessment-producer", card=f"REC-{i + 1:02d}")
    with pytest.raises(N.NarrativeRefusal, match="at most 8"):
        N.write(wb, "assessment", REC.id, _rec(REC.id, eids, report="assessment"),
                actor="report-assessment-producer", card="REC-09")


def test_a_list_sections_floor_is_measured_across_its_cards(tmp_path):
    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    N.write(wb, "assessment", REC.id, _rec(REC.id, eids, report="assessment"),
            actor="report-assessment-producer", card="REC-01")
    sec = next(s for s in N.state(wb, "assessment")["reports"]
               ["assessment"]["sections"] if s["section"] == REC.id)
    assert sec["status"] == "SHORT"
    assert sec["cards"] == 1 and sec["card_floor"] == REC.card_floor == 5
    assert "of 5 recommendations" in sec["detail"]


def test_the_pillar_floor_is_the_pillars_this_run_assesses(tmp_path):
    """The Doc owes one deep dive per pillar. A run whose engagement set
    selects only P1 owes ONE, and its word floor is one card's worth — the
    writer refuses P2..P4 as out of scope, so a four-card floor would be a
    wall nothing could pass."""
    run = report_ready_run(tmp_path)
    wb = run.open()
    sec = RS.SPECS["assessment"].section("5")
    assert sec.card_floor == 4
    assert N.card_floor_for(wb, sec) == 1
    assert N.min_words_for(wb, sec) == sec.card_min_words
    assert N.report_min_words_for(wb, RS.SPECS["assessment"]) == \
        RS.SPECS["assessment"].min_words - 3 * sec.card_min_words


# ── the two reports do not overwrite each other ──────────────────────────

def test_writing_the_other_reports_section_one_does_not_eat_this_one(tmp_path):
    """Both specs number their sections 1..8. `update_row` matched on
    Section_ID alone, walked the sheet, found the OTHER report's §1 first and
    overwrote it — relabelling the victim as belonging to the other report,
    because the values dict carries `Report` too."""
    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    N.write(wb, "client_research", "3", _rec("3", eids),
            actor="report-research-producer")
    N.write(wb, "assessment", "4", _rec("4", eids, report="assessment"),
            actor="report-assessment-producer")
    # rewrite the first one; the second must survive, still labelled its own
    N.write(wb, "client_research", "3", _rec("3", eids),
            actor="report-research-producer")

    rows = [r for r in wb.rows("Report_Narrative") if r.get("Report")]
    cr = [r for r in rows if r["Report"] == "client_research"
          and str(r["Section_ID"]) == "3"]
    asmt = [r for r in rows if r["Report"] == "assessment"
            and str(r["Section_ID"]) == "4"]
    assert len(cr) == 1 and len(asmt) == 1, [
        (r["Report"], r["Section_ID"]) for r in rows]
    assert asmt[0]["Author"] == "report-assessment-producer"


# ── the rendered artefact carries the anatomy ────────────────────────────

def test_the_renderer_promotes_blocks_to_real_headings(tmp_path):
    """The blocks become real Heading2s in the .docx. That is the grain the
    app's report parser reads at, and the grain `embed.py` scopes on — a
    section rendered as one undivided run of paragraphs arrives as a single
    row belonging to no pillar."""
    from docx import Document

    from fixtures import sign_off_sections, write_report

    run = report_ready_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    spec = RS.SPECS["client_research"]
    write_report(wb, spec.key, eids)
    sign_off_sections(wb)
    out = R.render(wb, spec, tmp_path / "out", force=False)
    path = Path(out["path"] if isinstance(out, dict) else out)
    doc = Document(str(path))
    h2 = [p.text for p in doc.paragraphs if p.style.name == "Heading 2"]
    for sec in spec.sections:
        for b in sec.blocks:
            assert b in h2, (sec.id, b, h2)


def test_writing_every_section_of_both_reports_through_the_writer_renders(tmp_path):
    """No test anywhere exercised `narrative.write` as the path into a
    rendered report — every renderer test appended Report_Narrative rows
    directly with `wb.append`, so the writer and the renderer could disagree
    and did. This walks the real path for both reports, on a run that has
    been researched, gated and SCORED — the assessment report's own
    precondition, and the only state in which its §3 inputs (Cap_Triggers,
    Subcap_Scores, Caps_Applied_Log) exist to be read."""
    from fixtures import (make_shippable, scored_run, sign_off_sections,
                          write_report)

    run, wb, cells, ev = scored_run(tmp_path)
    make_shippable(wb)
    eids = bank_evidence(wb, cells[0], n=7)
    for key in RS.SPECS:
        write_report(wb, key, eids, run=run)
    sign_off_sections(wb)
    st = N.state(wb)
    assert st["ready"], st["blocking"]
    for key, spec in RS.SPECS.items():
        problems = R.check(wb, R.curate(wb, spec))
        assert problems == [], (key, problems)
        out = R.render(wb, spec, tmp_path / "out", force=False)
        assert Path(out["path"] if isinstance(out, dict) else out).exists()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
