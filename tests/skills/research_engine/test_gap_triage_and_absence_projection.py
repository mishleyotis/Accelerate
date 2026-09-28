"""The gap dossier, the coordinator's triage, the exclusion list in the
relay brief, and the projected absence.

Measured 28-09-2026 (QA audit D-12..D-16, F-CG15-016): a declared absence
carried 4 of the dossier's 11 fields; no disposition per gap was written
anywhere; relay briefs stated no prior-query exclusion list; and a staged
heatmap's 61 hand-written absences shared 34 ladders and 119 eight-word
spans. These tests pin: the dossier the absence writes (computed facet
status, catalogue proxy and settling artefact, inference + question,
cost); one disposition per gap from the substrate; the brief that names
what was already asked; and a projector that renders per-cell records
per cell and OMITS records that are one sentence with the name swapped.
"""
import json

import pytest

from engine import brief, contract as C, ledger as L, relay, surface_export as X
from fixtures import (bank_evidence, declare_absent, fire_volleys, new_run,
                      two_category_selection)


def _declare(wb, cell, *, hunted, proxy_log, tool="exa", fire=True, **kw):
    proxy_q = f'"Acme Credit Union" {cell} proxy: {hunted[:30]}'
    if fire:
        fire_volleys(wb, cell, n=0)
        L.append_search(wb, subcap=cell, facet="works", query=proxy_q, tool=tool,
                        hits=0, kept=0, outcome="no hits")
    return L.declare_absence(
        wb, cell, actor="research-p1c1-producer",
        ladder=[{"rung": "direct",
                 "query": f'"Acme Credit Union" {cell} rollout OR "went live"'},
                {"rung": "proxy", "query": proxy_q}],
        proxy_log=proxy_log, what_was_hunted=hunted, **kw)


PER_CELL = {
    "P1C1.1.1": ("a published digital strategy document — a named strategy page, an "
                 "investor letter section or a board paper — on the site, in the "
                 "annual report and in the trade press; the searches returned only "
                 "vendor pages",
                 "hunted the leadership_title proxy class — a chief digital officer "
                 "or head of digital named anywhere; the leadership page lists "
                 "a CFO and a COO and nobody with a digital remit"),
    "P1C1.1.2": ("a business-alignment artefact — a strategy map tying digital "
                 "initiatives to lending or deposit targets — in the annual "
                 "report and investor materials; the report carries only a "
                 "mission statement",
                 "hunted an artifact_disclosure proxy — any KPI slide linking "
                 "digital spend to a business line; the 2025 report shows "
                 "branch counts and nothing on digital investment"),
    "P1C1.1.3": ("a strategy refresh cadence — a dated revision, a board review "
                 "minute, a 'strategy 2027' announcement — in board minutes, the "
                 "newsroom and the regulator's filings; the newsroom has product "
                 "launches and no strategy item since 2021",
                 "hunted the regulator_filing proxy — a strategic plan referenced "
                 "in the call report narrative or an examination note; the "
                 "call report narrative is blank on strategy"),
}


# ── the dossier ───────────────────────────────────────────────────────────

def test_a_declared_absence_writes_a_dossier_with_computed_fields(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    hunted, proxy = PER_CELL["P1C1.1.1"]
    out = _declare(wb, "P1C1.1.1", hunted=hunted, proxy_log=proxy,
                   inferable="Strategy is set by the CEO and CFO without a "
                             "digital owner, given the leadership roster",
                   validation_question="Who owns the digital strategy internally?")
    assert out["dossier"] and out["dossier"].endswith(L.GAP_DOSSIERS_NAME)
    d = L.read_gap_dossiers(run)["P1C1.1.1"]
    assert d["schema_version"] == L.GAP_DOSSIER_SCHEMA
    # per-facet status is COMPUTED from the Search_Log, never taken
    assert all(v["status"] == "SEARCHED" for v in d["facets_status"].values())
    assert set(d["facets_status"]) == set(L.askable_facets(wb, "P1C1.1.1"))
    assert d["proxy_class"] == C.proxy_classes()["P1C1.1.1"]
    assert d["proxy_candidates"][0] == d["proxy_class"]
    assert {"peer", "regulatory"} <= set(d["proxy_candidates"]), "the rungs not yet climbed"
    assert d["settling_artefact"] == C.settling_artefacts()["P1C1.1.1"]
    assert d["inferable"] == {"claim": "Strategy is set by the CEO and CFO without a "
                                       "digital owner, given the leadership roster",
                              "validation_question": "Who owns the digital strategy internally?"}
    assert d["ladder"]["rungs"] == ["direct", "proxy"] and d["ladder"]["claimed_not_fired"] == []
    assert d["enrichment_tools"] == ["exa"] and d["rigour"] == "FULL"
    assert d["est_cost_usd"] is None or d["est_cost_usd"] > 0
    assert len(d["searches"]) == out["searches"]
    assert out["facets_status"] == d["facets_status"]


def test_an_inference_without_its_question_is_refused_and_vice_versa(tmp_path):
    wb = new_run(tmp_path).open()
    hunted, proxy = PER_CELL["P1C1.1.1"]
    with pytest.raises(L.LedgerRefusal, match="validation-question"):
        _declare(wb, "P1C1.1.1", hunted=hunted, proxy_log=proxy,
                 inferable="Strategy is set by the CEO and CFO without a digital owner")
    # the volleys are in the log now; a second declaration attempt must not
    # re-fire them (that is the duplicate the ledger refuses)
    with pytest.raises(L.LedgerRefusal, match="together"):
        _declare(wb, "P1C1.1.1", hunted=hunted, proxy_log=proxy, fire=False,
                 validation_question="Who owns the digital strategy internally?")
    with pytest.raises(L.LedgerRefusal, match="not-determinable"):
        _declare(wb, "P1C1.1.1", hunted=hunted, proxy_log=proxy, fire=False,
                 not_determinable="no")
    assert "P1C1.1.1" not in L.declared_absences(wb)


def test_the_cli_absence_carries_the_dossier_flags(tmp_path, capsys):
    from engine import cli
    run = new_run(tmp_path)
    wb = run.open()
    cell = "P1C1.1.2"
    fire_volleys(wb, cell, n=0)
    proxy_q = f'"Acme Credit Union" {cell} proxy: any KPI slide on digital spend'
    L.append_search(wb, subcap=cell, facet="works", query=proxy_q, tool="exa",
                    hits=0, kept=0, outcome="no hits")
    hunted, proxy = PER_CELL[cell]
    rc = cli.main(["absence", "--run", run.run_id, "--root", str(run.root),
                   "--subcap", cell, "--actor", "research-p1c1-producer",
                   "--ladder", json.dumps([
                       {"rung": "direct", "query": f'"Acme Credit Union" {cell} rollout OR "went live"'},
                       {"rung": "proxy", "query": proxy_q}]),
                   "--proxy-log", proxy, "--hunted", hunted,
                   "--not-determinable", "Digital investment is not broken out in "
                                         "any public filing for a credit union of this size"])
    assert rc == 0, capsys.readouterr().err
    out = json.loads(capsys.readouterr().out)
    assert out["dossier"] and out["proxy_candidates"]
    assert L.read_gap_dossiers(run)[cell]["not_determinable"].startswith("Digital investment")


# ── the triage ────────────────────────────────────────────────────────────

def test_one_disposition_per_gap_decided_from_the_substrate(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(4))
    wb = run.open()
    cells = wb.selected_subcaps()
    a, b, c = [x for x in cells if brief.category_of(x) == "P1C1"][:3]
    # d and its sibling sit under ANOTHER capability: a registered row on a
    # capability sibling of a, b or c would (rightly) triage them
    # cross_card_remap first
    others = [x for x in cells if brief.capability_of(x) not in
              {brief.capability_of(y) for y in (a, b, c)}]
    d, sib = [x for x in others if brief.capability_of(x) == brief.capability_of(others[0])][:2]
    # a: every public rung climbed at FULL rigour → internal_only
    _declare(wb, a, hunted=PER_CELL["P1C1.1.1"][0], proxy_log=PER_CELL["P1C1.1.1"][1])
    # b: declared with the dossier saying nothing public decides it → internal_only
    _declare(wb, b, hunted=PER_CELL["P1C1.1.2"][0], proxy_log=PER_CELL["P1C1.1.2"][1],
             not_determinable="Digital investment is not broken out in any public "
                              "filing for a credit union of this size")
    # c: one volley fired through web_search only, nothing declared → proxy
    L.append_search(wb, subcap=c, facet="works", query=f'"Acme Credit Union" {c} rollout',
                    tool="web_search", hits=0, kept=0)
    # d: untouched, but a row is registered against its capability sibling
    # — read that before searching → cross_card_remap
    bank_evidence(wb, sib, n=1)
    out = brief.triage(wb, run)
    by = {g["subcap"]: g for g in out["gaps"]}
    assert by[a]["disposition"] == "internal_only" and by[a]["discovery_question"].endswith("?")
    assert by[b]["disposition"] == "internal_only" and "dossier says" in by[b]["why"]
    assert by[c]["disposition"] == "proxy" and "enrichment connector" in by[c]["why"]
    assert by[c]["queries_already_run"][0]["query"] == f'"Acme Credit Union" {c} rollout'
    assert by[d]["disposition"] == "cross_card_remap" and "engine.cli attach" in by[d]["next"]
    assert set(out["counts"]) == set(L.DISPOSITIONS)
    assert (run.qa_dir / L.GAP_TRIAGE_NAME).is_file()
    assert L.read_gap_triage(run)["schema_version"] == L.GAP_TRIAGE_SCHEMA
    assert {q["subcap"] for q in out["discovery_questions"]} == {a, b}
    # the CLI prints the same document
    from engine import brief as _b
    assert _b.main(["triage", "--run", run.run_id, "--root", str(run.root)]) in (0, None)


def test_a_cell_nothing_decides_is_unknown_and_says_what_would_decide_it(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fire_volleys(wb, cell, n=0)
    L.append_search(wb, subcap=cell, facet="works", query=f'"Acme Credit Union" {cell} via exa',
                    tool="exa", hits=0, kept=0)
    g = {x["subcap"]: x for x in brief.triage(wb, run)["gaps"]}[cell]
    assert g["disposition"] == "unknown" and "engine.cli absence" in g["next"]


# ── the relay brief states what was already asked ─────────────────────────

def test_the_relay_prompt_states_the_exclusion_list_and_flags_a_repeat(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fired = f'"Acme Credit Union" {cell} board technology committee charter'
    L.append_search(wb, subcap=cell, facet="works", query=fired, tool="exa",
                    hits=0, kept=0, outcome="no hits")
    brief.triage(wb, run)
    queue = relay.queue_path(run)
    queue.parent.mkdir(parents=True, exist_ok=True)
    for q in (fired, f'"Acme Credit Union" {cell} technology steering group minutes'):
        req = relay._one({"query": q, "subcap": cell, "tool": "exa"}, cell.split(".")[0])
        req.update({"event": "open", "at": "2026-09-28T00:00:00Z", "lane": "test", "round": 0})
        relay._append(run, req)
    out = relay.batch(run, wb, out_dir=tmp_path / "relay_r0")
    assert out["queries"] == 2 and out["groups"][0]["already_fired"] == 1
    text = (tmp_path / "relay_r0" / f"{out['groups'][0]['key']}.md").read_text()
    assert "## Already asked for these cells" in text
    assert fired in text and "ALREADY FIRED" in text and "F-D05-033" in text
    assert "triage `" + cell + "`: **proxy**" in text


# ── the projector ─────────────────────────────────────────────────────────

def test_per_cell_records_project_per_cell_with_the_trio_and_no_template(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    for cell, (hunted, proxy) in PER_CELL.items():
        _declare(wb, cell, hunted=hunted, proxy_log=proxy)
    out = X.absence_rows(wb, run=run)
    assert out["declared"] == 3 and out["projected"] == 3 and out["omitted_identical"] == []
    for row in out["cells"]:
        assert row["thin"] is True and row["e_ids"] == [] and row["grounded_on"] == 0
        assert row["closure_condition"].startswith("An internal artefact would settle it: ")
        assert any('searched for: "' in s and "direct rung via" in s for s in row["sources_searched"])
        assert C.subcap_names()[row["subcap_id"]] in row["synthesis"]
        assert row["provenance"]["grade"] == "declared" and row["provenance"]["actor"]
    syn = {r["subcap_id"]: r["synthesis"] for r in out["cells"]}
    assert "vendor pages" in syn["P1C1.1.1"] and "mission statement" in syn["P1C1.1.2"]
    groups, checker = X._template_groups(syn)
    assert groups == [], checker


def test_one_sentence_with_the_name_swapped_is_omitted_not_projected(tmp_path):
    """The fixture's own declare_absent writes the same hunted/proxy text for
    every cell — exactly the 61-times-one-sentence shape the audit measured.
    The projector must not render it."""
    run = new_run(tmp_path)
    wb = run.open()
    for cell in wb.selected_subcaps()[:3]:
        declare_absent(wb, cell)
    out = X.absence_rows(wb, run=run)
    assert out["declared"] == 3 and out["projected"] == 0
    assert sorted(o["subcap_id"] for o in out["omitted_identical"]) == sorted(wb.selected_subcaps()[:3])
    assert "CG-15" in out["omitted_identical"][0]["reason"]


def test_the_cli_writes_the_file_and_exits_3_when_it_omitted(tmp_path, capsys):
    run = new_run(tmp_path)
    wb = run.open()
    hunted, proxy = PER_CELL["P1C1.1.1"]
    _declare(wb, "P1C1.1.1", hunted=hunted, proxy_log=proxy,
             inferable="Strategy is set by the CEO and CFO without a digital owner, "
                       "given the leadership roster",
             validation_question="Who owns the digital strategy internally?")
    rc = X.main(["absence", "--run", run.run_id, "--root", str(run.root),
                 "--out", str(tmp_path / "drafts")])
    assert rc == 0
    doc = json.loads((tmp_path / "drafts" / X.ABSENCES_NAME).read_text())
    row = doc["cells"][0]
    assert row["closure_condition"] == "Who owns the digital strategy internally?"
    assert "INFERENCE — " in row["synthesis"]
    for cell in wb.selected_subcaps()[1:4]:
        declare_absent(wb, cell)
    assert X.main(["absence", "--run", run.run_id, "--root", str(run.root),
                   "--out", str(tmp_path / "drafts")]) == 3
    assert "omitted as identical" in capsys.readouterr().out
