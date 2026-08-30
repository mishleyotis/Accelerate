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

from .fixtures import bank_evidence, new_run


# ── every section declares its anatomy and its counterpart ───────────────

def test_every_section_declares_the_blocks_it_is_written_in():
    thin = [f"{k} §{s.id}" for k, spec in RS.SPECS.items()
            for s in spec.sections if not s.blocks]
    assert not thin, ("these sections declare no anatomy, so nothing tells a "
                      "producer what they contain: " + ", ".join(thin))


def test_every_section_that_feeds_the_app_names_the_surfaces_it_feeds():
    """§8 of the research profile is the artefact index — it describes where
    the files are and legitimately feeds nothing. Every other section is
    read by a surface, and says which."""
    unmapped = [f"{k} §{s.id} {s.heading}" for k, spec in RS.SPECS.items()
                for s in spec.sections if not s.surfaces]
    assert unmapped == ["client_research §8 Where each artefact lives"], (
        f"a section with no app counterpart is either a hole in the map or "
        f"prose nobody reads: {unmapped}")


def test_the_pillar_sections_carry_the_token_the_app_scopes_on():
    """`embed._PILLAR_TOKEN` looks for `(P1)`..`(P4)` in a heading, and the
    per-pillar sections are the ones whose vectors should be pillar-scoped.
    The parenthesised form in the block titles is what makes that true."""
    for key in ("client_research", "assessment"):
        sec = next(s for s in RS.SPECS[key].sections
                   if "pillar" in s.heading.lower())
        joined = " ".join(sec.blocks)
        for p in ("(P1)", "(P2)", "(P3)", "(P4)"):
            assert p in joined, (key, sec.id, p, sec.blocks)


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

def _rec(section: str, eids, report="client_research", **over) -> dict:
    sec = RS.SPECS[report].section(section)
    para = (
            "The public record for this institution is read here against the "
            "question the block asks, and the reading is stated so a reader "
            "can disagree with it rather than accept it. Nothing in this "
            "paragraph rests on a source that is not in the run's own "
            "register, and every figure it carries can be reopened from the "
            "excerpt that supplied it rather than recalled from anywhere "
            "else in the record of the engagement. Where the record is "
            "silent the silence is reported as silence, with the ladder "
            "that establishes it, rather than being read as an answer in "
            "either direction; and where two sources disagree the "
            "disagreement is carried forward rather than resolved by "
            "preference. That is the standard the whole section is written "
            "to, and it is the standard a reader should hold it to when "
            "deciding whether any single sentence here has earned its "
            "place in an argument about this institution.")
    # Scale the filler to the section's own floor: these tests are about the
    # refusals, and a body that trips the word floor first proves nothing
    # about the anatomy the test is aiming at.
    floor = sec.card_min_words or sec.min_words
    nblocks = len(sec.blocks) or 1
    w = len(para.split())
    per = max(1, -(-floor // (nblocks * w)) + 1)
    body = []
    for b in sec.blocks or ("",):
        if b:
            body.append(f"## {b}")
        body.extend([para] * per)
        # The renderer reads citations out of the BODY (`reports.CITE_RE`),
        # not out of Evidence_IDs, so a section that cites in the column and
        # not in the prose reads as uncited to the artefact a client opens.
        body.append("Sources for this block: "
                    + " ".join(f"[{e}]" for e in eids) + ".")
        body.append("")
    rec = {
        "Body": "\n".join(body).strip(),
        "Evidence_IDs": ", ".join(eids),
        "Weighing": (
            "The reading above was weighed against the opposite one — that "
            "the silence in the public record reflects an absence of "
            "practice rather than an absence of disclosure — and the "
            "conservative reading was preferred because the institution is "
            "member-owned and publishes little of either kind."),
        "Assumptions": (
            "Assumed that what a member-owned institution publishes "
            "understates what it does; that cuts toward under-reading it."),
        "Bias_Notes": (
            "A public-evidence run over-reads what a client publishes and "
            "under-reads what it does not; this section leans that way."),
        "Inference_Tags": "",
        "Absence_Basis": "",
    }
    rec.update(over)
    return rec


def test_a_body_without_its_blocks_is_refused(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    rec = _rec("3", eids)
    rec["Body"] = rec["Body"].replace("## ", "")
    with pytest.raises(N.NarrativeRefusal, match="missing the block heading"):
        N.write(wb, "client_research", "3", rec, actor="report-research-producer")


def test_blocks_out_of_order_are_refused(tmp_path):
    run = new_run(tmp_path)
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
    run = new_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    N.write(wb, "client_research", "3", _rec("3", eids),
            actor="report-research-producer")
    row = N.rows_for(wb, "client_research")["3"]
    assert row["Body"].startswith("## ")
    assert len(N.blocks_in(row["Body"])) == 3


# ── a list section is a list ─────────────────────────────────────────────

def test_a_list_section_refuses_a_write_with_no_card_id(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    with pytest.raises(N.NarrativeRefusal, match="needs its own --card"):
        N.write(wb, "client_research", "5", _rec("5", eids),
                actor="report-research-producer")


def test_a_passage_section_refuses_a_card_id(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    with pytest.raises(N.NarrativeRefusal, match="--card does not"):
        N.write(wb, "client_research", "3", _rec("3", eids),
                actor="report-research-producer", card="IC-1")


def test_eight_cards_land_as_eight_rows(tmp_path):
    """The floor `reports.check` enforces was unreachable through the only
    sanctioned writer: every write overwrote the last, so the section held
    one row against a blocking minimum of eight."""
    run = new_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    for i in range(RS.INSIGHT_CARD_MIN):
        out = N.write(wb, "client_research", "5", _rec("5", eids),
                      actor="report-research-producer", card=f"IC-{i + 1}")
    assert out["cards_in_section"] == RS.INSIGHT_CARD_MIN
    rows = N.all_rows_for(wb, "client_research")["5"]
    assert len(rows) == RS.INSIGHT_CARD_MIN
    assert {r["Card_ID"] for r in rows} == {
        f"IC-{i + 1}" for i in range(RS.INSIGHT_CARD_MIN)}
    # and rewriting one card touches only that card
    N.write(wb, "client_research", "5", _rec("5", eids),
            actor="report-research-producer", card="IC-3")
    assert len(N.all_rows_for(wb, "client_research")["5"]) == \
        RS.INSIGHT_CARD_MIN


def test_a_list_sections_floor_is_measured_across_its_cards(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    N.write(wb, "client_research", "5", _rec("5", eids),
            actor="report-research-producer", card="IC-1")
    sec = next(s for s in N.state(wb, "client_research")["reports"]
               ["client_research"]["sections"] if s["section"] == "5")
    assert sec["status"] == "SHORT"
    assert sec["cards"] == 1 and sec["card_floor"] == RS.INSIGHT_CARD_MIN
    assert "of 8 insight cards" in sec["detail"]


# ── the two reports do not overwrite each other ──────────────────────────

def test_writing_the_other_reports_section_one_does_not_eat_this_one(tmp_path):
    """Both specs number their sections 1..8. `update_row` matched on
    Section_ID alone, walked the sheet, found the OTHER report's §1 first and
    overwrote it — relabelling the victim as belonging to the other report,
    because the values dict carries `Report` too."""
    run = new_run(tmp_path)
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

    from .fixtures import sign_off_sections

    run = new_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    spec = RS.SPECS["client_research"]
    for sec in spec.sections:
        if sec.kind in RS.CARD_KINDS:
            for i in range(RS.INSIGHT_CARD_MIN):
                N.write(wb, spec.key, sec.id, _rec(sec.id, eids),
                        actor="report-research-producer", card=f"IC-{i + 1}")
        else:
            N.write(wb, spec.key, sec.id, _rec(sec.id, eids),
                    actor="report-research-producer")
    sign_off_sections(wb)
    out = R.render(wb, spec, tmp_path / "out", force=False)
    path = Path(out["path"] if isinstance(out, dict) else out)
    doc = Document(str(path))
    h2 = [p.text for p in doc.paragraphs if p.style.name == "Heading 2"]
    for sec in spec.sections:
        for b in sec.blocks:
            assert b in h2, (sec.id, b, h2)


def test_writing_all_sixteen_sections_through_the_writer_renders(tmp_path):
    """No test anywhere exercised `narrative.write` as the path into a
    rendered report — every renderer test appended Report_Narrative rows
    directly with `wb.append`, so the writer and the renderer could disagree
    and did. This walks the real path for both reports."""
    from .fixtures import sign_off_sections

    run = new_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    for key, spec in RS.SPECS.items():
        for sec in spec.sections:
            if sec.kind in RS.CARD_KINDS:
                floor = (RS.INSIGHT_CARD_MIN if sec.kind == "insight_card"
                         else 1)
                for i in range(floor):
                    N.write(wb, key, sec.id, _rec(sec.id, eids, report=key),
                            actor=f"report-{key}-producer", card=f"C-{i + 1}")
            else:
                N.write(wb, key, sec.id, _rec(sec.id, eids, report=key),
                        actor=f"report-{key}-producer")
    sign_off_sections(wb)
    st = N.state(wb)
    assert st["ready"], st["blocking"]
    for key, spec in RS.SPECS.items():
        problems = R.check(wb, R.curate(wb, spec))
        assert problems == [], (key, problems)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
