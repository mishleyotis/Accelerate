"""Acceptance: the seven reported issues, each as the owner wrote it.

Issue 8 (orchestration and context) has its own file, because it is the one
whose mechanism did not exist at all.

Every test here is named for the complaint it answers, and every assertion
is against the SHIPPED path — the same functions the CLI calls and the
agents run. Where a complaint has two halves (the failure must be refused,
and the correct work must be able to pass) both halves are asserted, in
that order.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import assemble, assessment as A, brief, contract as C
from engine import floors_gate, gold_standard as GS
from engine import ledger as L, narrative as N, report_spec as RS
from engine import runstate, ship, template as T, workbook as W
from engine.ledger import LedgerRefusal

from fixtures import (bank_evidence, declare_absent, fire_volleys,
                      make_shippable,
                      good_synthesis, new_run, researched_run, score_stage,
                      scored_run, section_record, synthesise)

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "dma-insights"


# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 1 · "some subcaps are marked as no evidence without any enrichment
#            efforts … not even looking at the 5 volley structure and
#            related DQ set"
# ═══════════════════════════════════════════════════════════════════════════

def test_issue1_a_cell_cannot_close_as_no_evidence_without_the_five_volleys(tmp_path):
    """The reported shape, reproduced: one query fired, the row left at
    NO_EVIDENCE, the category closed. Both blocking terms name the cell."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cells = wb.selected_subcaps()
    for c in cells[:5]:
        synthesise(wb, c, good_synthesis(c, bank_evidence(wb, c, n=5)))
    L.append_search(wb, subcap=cells[5], facet="works", tool="web_search",
                    query=f'"Acme Credit Union" {cells[5]} strategy',
                    hits=0, kept=0, outcome="no hits")

    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "FAIL"
    assert "volleys_incomplete" in v["blocking"]
    assert "absence_undeclared_empty" in v["blocking"]
    owed = [x for x in v["volleys_incomplete"] if x["subcap"] == cells[5]]
    assert owed and set(owed[0]["missing"]) == {
        "fails", "value", "contradicts", "corroborates"}, owed


def test_issue1_the_declared_absence_is_the_only_way_a_cell_ends_empty(tmp_path):
    """And it is refused until the volleys and the ladder are real, so the
    honest path costs the work rather than a sentence."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[5]

    with pytest.raises(LedgerRefusal, match="volley"):
        L.declare_absence(wb, cell, actor="research-p1c1-producer",
                          ladder=[{"rung": "direct", "query": "x"}],
                          proxy_log="hunted the named-owner proxy class and found nothing at all",
                          what_was_hunted="a public artefact naming the capability at the entity")

    for c in wb.selected_subcaps()[:5]:
        synthesise(wb, c, good_synthesis(c, bank_evidence(wb, c, n=5)))
    declare_absent(wb, cell)                       # the real path, in full
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    assert L.is_declared_absent(wb.scoring_row(cell))


def test_issue1_evidence_the_run_already_bought_cannot_be_left_unconsolidated(tmp_path):
    """"limited evidence is consolidated in most runs making the entire
    assessment very evidence deficient" — the coherence half of it.

    Two things must hold, and this asserts both. FIRST, the sanctioned path
    cannot produce the divergence at all: `append_evidence` attaches its id
    to every cell the row names, so after a real category there is no row
    the register names for a cell that the cell does not cite. That is the
    property, asserted rather than assumed — it is what makes the register
    and the citations one fact instead of two.

    SECOND, if anything ever breaks it — an out-of-band edit, a patch, a
    future writer that sets `Evidence_IDs` itself — the run says so instead
    of shipping a cell that reads as empty while the run holds its evidence.
    A cell declared ABSENT over the register is refused at the write path and
    blocked at the gate; a cell merely not citing it is reported."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cells = wb.selected_subcaps()
    target = cells[5]
    for c in cells:
        synthesise(wb, c, good_synthesis(c, bank_evidence(wb, c, n=5)))

    # the property: nothing the run bought sits outside the cell it names
    assert brief.unattached(wb, "P1C1") == []
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    assert v["evidence_unattached"] == []

    banked = [i for i in str(wb.scoring_row(target)["Evidence_IDs"]).split(",")
              if i.strip()]
    banked = [i.strip().split(":")[0] for i in banked]
    assert len(banked) >= 3

    # an out-of-band edit drops the citations the register still names
    wb.set_scoring(target, {"Evidence_IDs": C.NO_EVIDENCE})
    got = [x for x in brief.unattached(wb, "P1C1") if x["subcap"] == target]
    assert got and set(banked) <= set(got[0]["e_ids"])
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert "evidence_unattached" in v["advisory"]

    # and the cell cannot be closed as EMPTY over those rows
    wb.set_scoring(target, {"Dominant_Claim": None, "Absence_Claimed": None})
    with pytest.raises(LedgerRefusal, match="register already names it"):
        declare_absent(wb, target)

    # forced through anyway (an out-of-band edit), the gate blocks it
    wb.set_scoring(target, {"Absence_Claimed": "YES",
                            "Dominant_Claim": "No evidence located",
                            "Evidence_IDs": C.NO_EVIDENCE})
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert "absence_over_evidence" in v["blocking"], v["blocking"]
    assert any(x["subcap"] == target and set(banked) <= set(x["e_ids"])
               for x in v["absence_over_evidence"])
    assert "evidence_unattached" not in v["blocking"]

    # and the reuse read an agent makes names the rows to consolidate
    got = brief.reusable(wb, target)
    assert set(banked) <= {i["e_id"] for i in got["names_this_cell"]}
    assert got["read_before_searching"] is True


def test_issue1_a_siblings_source_is_offered_before_a_cell_searches_again(tmp_path):
    """The other half of under-consolidation: a source registered against a
    NEIGHBOURING cell under the same capability. It is not this cell's
    evidence and the gate does not demand it — but a producer that searches
    without reading it pays twice for one source, sixteen lanes over. The
    brief hands it over; the producer decides."""
    run, wb, cells, ev = researched_run(tmp_path)
    sib = cells[1]
    got = brief.reusable(wb, sib)
    assert brief.capability_of(sib) == brief.capability_of(cells[0])
    assert got["capability_siblings"], got
    assert all(i["e_id"] not in got["cites_now"]
               for i in got["capability_siblings"])
    # the gate does NOT block on a sibling's row: it is a read, not a duty
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]


# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 2 · "Report writing starts without scoring happening. Worse still,
#            the reports do not follow the required format. Can these
#            templates be retrieved from the repo?"
# ═══════════════════════════════════════════════════════════════════════════

def test_issue2_the_templates_are_in_the_repo_and_they_are_the_spec():
    """Yes — retrieved from the owner's two Docs, pinned, and LOADED as the
    section spec rather than transcribed into code."""
    d = PLUGIN / "references" / "templates"
    for f in T.PINNED_FILES:
        assert (d / f).is_file(), f
    spec = json.loads((d / "report_templates.json").read_text())
    for key, rep in spec["reports"].items():
        loaded = RS.SPECS[key]
        assert [s["id"] for s in rep["sections"]] == \
            [s.id for s in loaded.sections]
        assert [s["heading"] for s in rep["sections"]] == \
            [s.heading for s in loaded.sections]
        assert loaded.drive_doc_id == rep["drive_doc_id"]
    assert len(RS.SPECS["client_research"].sections) == 8
    assert len(RS.SPECS["assessment"].sections) == 11


def test_issue2_no_report_section_can_be_written_before_scoring(tmp_path):
    """The reported failure, refused at the writer — not warned about."""
    run, wb, cells, ev = researched_run(tmp_path)
    pre = N.stage_preconditions(wb, "assessment", run.qa_dir)
    assert any("research stage" in p for p in pre), pre
    assert any("SCORING gate" in p for p in pre), pre

    sec = RS.SPECS["assessment"].section("4")
    with pytest.raises(N.NarrativeRefusal, match="not ready for the Digital Maturity"):
        N.write(wb, "assessment", "4",
                section_record("4", ev[cells[0]], report="assessment"),
                actor="report-assessment-producer", run=run)

    score_stage(run, wb, cells, ev)                # do the scoring, properly
    make_shippable(wb)                             # and finish the workbook
    assert N.stage_preconditions(wb, "assessment", run.qa_dir) == []
    out = N.write(wb, "assessment", "4",
                  section_record("4", ev[cells[0]], report="assessment"),
                  actor="report-assessment-producer", run=run)
    assert out["section"] == "4"


def test_issue2_the_preliminary_check_names_every_reason_at_once(tmp_path):
    """"can the report writing agents do a preliminary check on scoring and
    ensure the workbook is complete before writing any report?" — this is
    that check, and it returns a LIST so an unattended agent can act on all
    of it rather than discovering one reason per attempt."""
    run = new_run(tmp_path, n=2, prelim=False)
    pre = N.stage_preconditions(run.open(), "assessment", run.qa_dir)
    assert len(pre) >= 3
    assert any("PRELIM" in p for p in pre)
    assert any("gate" in p for p in pre)


def test_issue2_a_body_that_is_not_the_docs_shape_is_refused(tmp_path):
    """"the reports do not follow the required format" — the format is the
    Doc's, and the writer holds the body to it: the blocks in order, the
    card ids, and the countable minimum data of the control block."""
    run, wb, cells, ev = scored_run(tmp_path)
    make_shippable(wb)          # the preconditions are a different test
    eids = ev[cells[0]]

    rec = section_record("4", eids, report="assessment")
    rec["Body"] = rec["Body"].replace("## ", "")
    with pytest.raises(N.NarrativeRefusal, match="missing the block heading"):
        N.write(wb, "assessment", "4", rec,
                actor="report-assessment-producer", run=run)

    thin = section_record("4", eids, report="assessment")
    thin["Body"] = "\n".join(
        l for l in thin["Body"].splitlines()
        if not l.startswith("Control block"))
    with pytest.raises(N.NarrativeRefusal, match="MINIMUM DATA"):
        N.write(wb, "assessment", "4", thin,
                actor="report-assessment-producer", run=run)

    with pytest.raises(N.NarrativeRefusal, match="REC-"):
        N.write(wb, "assessment", "8",
                section_record("8", eids, report="assessment"),
                actor="report-assessment-producer", run=run, card="R-1")


# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 3 · "The workbook always defaults to the wrong structure each time;
#            missing fields etc. Missing formatting; missing subcaps names"
# ═══════════════════════════════════════════════════════════════════════════

def test_issue3_the_workbook_is_the_templates_shape_not_a_remembered_one(tmp_path):
    """Every sheet the pinned workbook template names exists, with the
    columns it names, in a workbook this engine creates from scratch."""
    tmpl = json.loads(
        (PLUGIN / "references" / "templates" / "workbook_template.json").read_text())
    wb = new_run(tmp_path, n=2).open()
    have = {ws.title for ws in wb._wb.worksheets}          # noqa: SLF001
    missing = [s for s in tmpl["sheets"] if s not in have
               and s not in tmpl.get("known_divergences", {})]
    assert missing == [], missing
    assert len(C.SHEETS) >= len(tmpl["sheets"]) - len(
        tmpl.get("known_divergences", {}))


def test_issue3_every_scored_row_carries_its_catalogue_name(tmp_path):
    """"missing subcaps names" — seeded at create, and an unnamed cell is
    refused rather than left blank for a client to read."""
    wb = new_run(tmp_path, n=6).open()
    names = C.subcap_names()
    for r in wb.scoring_rows():
        cell = str(r["SubCap_ID"]).strip()
        assert str(r["SubCap_Name"]).strip() == names[cell], cell


def test_issue3_every_sheet_is_formatted(tmp_path):
    """"Missing formatting" — a header row a reader can see, frozen, and
    filterable, on every sheet with columns."""
    wb = new_run(tmp_path, n=2).open()
    for ws in wb._wb.worksheets:                            # noqa: SLF001
        if ws.max_row < 1 or ws.max_column < 1:
            continue
        head = ws.cell(row=1, column=1)
        if not head.value:
            continue
        assert head.font.bold, ws.title
        assert ws.freeze_panes, ws.title


# ═══════════════════════════════════════════════════════════════════════════
# ISSUES 4 & 5 · "templates and gold standard examples … deeply ingrained in
#                 the verification scripts with clear hooks and automatic
#                 tooling that invokes the templates even before the process
#                 begins" · "the depth of all 3 output artifacts should
#                 match the gold standards"
# ═══════════════════════════════════════════════════════════════════════════

def test_issue4_the_gold_reference_is_measured_not_recalled():
    """Golden 1's own numbers, in the repo, with the reference's WEAKNESSES
    recorded beside its strengths — the volley counts that make it a floor
    for shape and not for depth."""
    g = GS.gold_reference()
    assert g["workbook"]["sheets_total"] >= 43
    assert g["workbook"]["named"] == g["workbook"]["subcaps"]
    assert g["reports"]["assessment"]["distinct_e_ids"] >= 100
    assert g["workbook"]["search_facets"]["fails"] == 3      # the weakness
    assert "readme" in {k.lower().strip("_") for k in g}


def test_issue4_the_run_is_bound_to_the_templates_before_any_work(tmp_path):
    """"automatic tooling that invokes the templates even before the process
    begins" — the binding is written by `start`, and the first work card is
    withheld until it exists."""
    from engine import orient
    run = new_run(tmp_path, n=3)
    wb = run.open()
    binding = Path(run.root) / "00_entity_profile" / "template_binding.json"
    assert binding.is_file()
    rec = json.loads(binding.read_text())
    assert rec["digest"] == T.pinned_digest()["_all"]
    assert rec["digest"].startswith(
        str(wb.metadata()["template_binding"]).strip()[:16])
    st = T.binding_state(wb)
    assert st["bound"] and st["current"] and st["fix"] is None
    assert st["recorded"].startswith(rec["digest"][:16])
    assert st["pinned_now"] == rec["digest"][:16]
    for key, rep_ in rec["reports"].items():
        assert Path(rep_["markdown"]).is_file(), key

    wb.set_metadata("template_binding", "")
    out = orient.orient(wb, "P1C1", qa_dir=run.qa_dir)
    assert out.get("next_card") in (None, {}, [])
    assert any("template" in str(x).lower() for x in out["do_first"]), out["do_first"]


def test_issue5_the_depth_floors_are_at_least_the_gold_standard():
    """The three artefacts' floors are read off Golden 1 rather than chosen:
    the reports' word and citation floors, and the workbook's naming."""
    g = GS.gold_reference()
    assert RS.SPECS["assessment"].min_words >= 8000
    assert RS.SPECS["client_research"].min_words >= 3000
    assert RS.SPECS["assessment"].min_words <= \
        g["reports"]["assessment"]["words_including_tables"]
    per_pillar = next(s for s in RS.SPECS["assessment"].sections
                      if s.kind == "pillar")
    assert per_pillar.card_min_words >= 800
    assert any(c.min >= 5 for c in per_pillar.checks
               if "E-ID" in (c.label or ""))


def test_issue4_the_hooks_name_the_templates_on_every_session():
    """"clear hooks" — the session brief an agent reads at start says where
    the templates are and that the run is bound to them."""
    text = (PLUGIN / "scripts" / "hooks" / "session_brief.py").read_text()
    assert "references/templates" in text
    assert "template" in text.lower() and "bind" in text.lower()


# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 6 · "The reports and scoring workbook should spin multiple agents and
#            subagents … a clear workflow with clear gating requirements"
# ═══════════════════════════════════════════════════════════════════════════

def test_issue6_the_scoring_tier_exists_and_is_five_agents():
    d = PLUGIN / "agents" / "scoring"
    got = sorted(p.stem for p in d.glob("*.md"))
    assert got == ["scoring-critic", "scoring-p1-producer",
                   "scoring-p2-producer", "scoring-p3-producer",
                   "scoring-p4-producer"], got
    manifest = json.loads(
        (PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    listed = json.dumps(manifest)
    for name in got:
        assert name in listed, name


def test_issue6_the_scoring_stage_is_gated_at_both_ends(tmp_path):
    """It opens only on a finished research run, and nothing downstream
    moves until its own gate records a PASS."""
    run = new_run(tmp_path, n=3)
    wb = run.open()
    with pytest.raises(A.ScoringRefusal, match="not ready to be scored"):
        A.open_stage(wb, run.qa_dir)

    run, wb, cells, ev = researched_run(tmp_path / "b")
    A.open_stage(wb, run.qa_dir)
    v = A.gate(wb, run.qa_dir)
    assert v["gate"] == "FAIL" and "unscored" in v["blocking"]
    score_stage(run, wb, cells, ev)
    v = A.gate(wb, run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    assert any(g["Gate"] == "SCORING" and g["Verdict"] == "PASS"
               for g in wb.rows("Gate_Log"))


def test_issue6_a_pillars_scorer_cannot_be_its_own_critic(tmp_path):
    """The reason there are five agents and not one: the critic is a
    DIFFERENT actor, and the engine enforces it rather than the prompt."""
    run, wb, cells, ev = researched_run(tmp_path)
    A.open_stage(wb, run.qa_dir)
    from fixtures import score_all
    score_all(wb, cells, ev)
    note = ("Re-derived 4 of 6 rows across the capabilities; the ceilings "
            "hold and the differentiation is real; would move nothing.")
    with pytest.raises(A.ScoringRefusal, match="cannot be its critic"):
        A.critique(wb, pillar="P1", verdict="PASS",
                   actor="scoring-p1-producer", note=note)
    assert A.critique(wb, pillar="P1", verdict="PASS",
                      actor="scoring-critic", note=note)["verdict"] == "PASS"


def test_issue6_the_workflow_order_cannot_be_walked_around(tmp_path):
    """Each stage refuses its predecessor's absence, so the order is a
    property of the engine rather than of the runbook."""
    run = new_run(tmp_path, n=3)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    with pytest.raises(A.ScoringRefusal):                  # score before open
        A.score(wb, cell, score=3.0, confidence="MEDIUM",
                rationale="x" * 200, actor="scoring-p1-producer",
                ai_applicability="ASSISTIVE", data_dependency="x",
                data_readiness="AMBER")
    with pytest.raises(N.NarrativeRefusal):                # report before gate
        N.write(wb, "assessment", "4",
                section_record("4", bank_evidence(wb, cell, n=3),
                               report="assessment"),
                actor="report-assessment-producer", run=run)


# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 7 · "token bleed in promoting the DMA to the web app … as research
#            and assessment progresses … submit the results to the MCP
#            connector … such that when the assessment ends, the promotion
#            is already done"
# ═══════════════════════════════════════════════════════════════════════════

def test_issue7_pages_are_shippable_before_the_assessment_ends(tmp_path):
    """The readiness reader: PRELIM's own work already feeds pages, and the
    scoring gate releases the rest — so nothing waits for everything."""
    run, wb, cells, ev = researched_run(tmp_path)
    early = ship.state(wb)
    assert early["ready_pages"], early
    assert "heatmap" not in early["ready_pages"]           # needs SCORING

    score_stage(run, wb, cells, ev)
    late = ship.state(wb)
    assert "heatmap" in late["ready_pages"], late
    assert set(early["ready_pages"]) <= set(late["ready_pages"])
    assert late["dispatch_now"]


def test_issue7_the_checkpoint_refuses_before_the_scoring_gate(tmp_path):
    """The scored workbook is pushed to the client folder mid-run — but only
    once it says something, so the app never ingests a half-scored run."""
    run, wb, cells, ev = researched_run(tmp_path)
    with pytest.raises(SystemExit, match="SCORING"):
        assemble.checkpoint(run, tmp_path / "out", push=False,
                            stage_reached="SCORED")
    score_stage(run, wb, cells, ev)
    out = assemble.checkpoint(run, tmp_path / "out", push=False,
                              stage_reached="SCORED")
    folder = Path(out["folder"])
    assert folder.is_dir()
    manifest = json.loads((folder / "run_manifest.json").read_text())
    assert manifest["status"] == "IN_PROGRESS"
    assert manifest["stage_reached"] == "SCORED"


def test_issue7_the_producer_is_told_to_read_the_readiness_reader():
    """The mechanism is only worth anything if the agent that ships pages
    knows it exists."""
    text = (PLUGIN / "agents" / "orchestration" / "surface-producer.md").read_text()
    assert "engine.ship state" in text
    assert "--incremental" in text
    assert "dispatch_now" in text
