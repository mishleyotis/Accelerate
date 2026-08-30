"""The knowledge graph: DQs mapped, mode-filtered, routed by category.

The toolkit fixture is built to the MEASURED shape of the shipped
Pillar1_Scoring_Toolkit.xlsx: title rows 1-2, the header on row 3 naming
'Sub-Cap ID' / 'Diagnostic Question' / 'Internal Evidence Sources' /
'Public / External Evidence Sources' / 'Source Type', data from row 4."""
import json

import openpyxl
import pytest

from engine import contract as C, kg, ledger as L, orient, runstate
from engine.workbook import RunWorkbook

from fixtures import CAT, new_run

HDR = ["Category ID", "Category Name", "Cap ID", "Capability", "Sub-Cap ID",
       "Sub-Capability", "Tier", "Diagnostic Question",
       "Internal Evidence Sources", "Public / External Evidence Sources",
       "Source Type", "Weight %"]


def _toolkits(tmp_path, rows_by_pillar):
    d = tmp_path / "toolkits"
    d.mkdir(exist_ok=True)
    for pillar, rows in rows_by_pillar.items():
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Credit Unions"
        ws.append([f"Pillar {pillar[1]} Scoring Toolkit — Banking"])
        ws.append(["Strategy | Subcap grain"])
        ws.append(HDR)
        for r in rows:
            ws.append(r)
        wb.save(d / f"Pillar{pillar[1]}_Scoring_Toolkit.xlsx")
    return d


def _row(sid, question, source_type="Both",
         internal="1) Board pack", public="1) Annual Report"):
    cat = sid.split(".")[0]
    return [cat, "Digital Strategy & Vision", sid.rsplit(".", 1)[0],
            "Strategy Foundation", sid, "Some Subcapability", "T1",
            question, internal, public, source_type, "2.1%"]


@pytest.fixture()
def built_run(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    cells = wb.selected_subcaps()
    toolkits = _toolkits(tmp_path, {"P1": [
        _row(cells[0], "Does the organization have a formal digital strategy?",
             "Both"),
        _row(cells[1], "Is there a defined cadence for refreshing the "
                       "strategy?", "Internal Only"),
        _row(cells[2], "How well are digital initiatives aligned to business "
                       "outcomes?", "Public Only"),
    ]})
    out = kg.build(wb, toolkit_dir=toolkits,
                   kg_path=run.root / "00_entity_profile" / "kg.json")
    return run, wb, cells, out


# ── the DQ map ───────────────────────────────────────────────────────────

def test_every_subcap_carries_nine_questions(built_run):
    """The pinned bank's own arithmetic: 5 facet probes + 3 AI overlay per
    subcap, plus the toolkit primary where one exists."""
    run, wb, cells, out = built_run
    rows = wb.rows("DQ_Bank")
    per = {c: [r for r in rows if r["SubCap_ID"] == c] for c in cells}
    for c in cells:
        facets = sorted(str(r["Facet"]) for r in per[c])
        assert len(per[c]) == 9, f"{c}: {facets}"
        assert set(facets) == set(C.DQ_FACETS)
    assert out["counts"]["dqs"] == 27
    assert out["counts"]["with_toolkit_primary"] == 3


def test_the_ai_overlay_rides_every_subcap_with_its_probe_tier(built_run):
    run, wb, cells, out = built_run
    ai = [r for r in wb.rows("DQ_Bank") if r["Facet"] in C.AI_FACETS]
    assert len(ai) == 9
    assert {str(r["Probe_Tier"]) for r in ai} == {"AI_OVERLAY"}


def test_a_closed_toolkit_question_is_regraded_open(built_run):
    """'Does X have Y?' cannot produce a graded answer; the works probe
    carries the open form and the arc requirement."""
    run, wb, cells, out = built_run
    works = next(r for r in wb.rows("DQ_Bank")
                 if r["SubCap_ID"] == cells[0] and r["Facet"] == "works")
    q = str(works["Question"])
    assert not q.lower().startswith("does ")
    assert "To what extent" in q
    assert "earliest signal" in q


def test_an_already_open_question_is_left_alone():
    q = "How well are digital initiatives aligned to business outcomes?"
    assert kg.grade_question(q) == q


def test_the_toolkits_source_lists_ride_the_dq_rows(built_run):
    """Column I and J are the routing gold: the toolkit names, per subcap,
    which artefacts answer its question."""
    run, wb, cells, out = built_run
    primary = next(r for r in wb.rows("DQ_Bank")
                   if r["SubCap_ID"] == cells[0] and r["Facet"] == "primary")
    assert "Board pack" in str(primary["Internal_Sources"])
    assert "Annual Report" in str(primary["Public_Sources"])


# ── mode filtering ───────────────────────────────────────────────────────

def test_an_internal_only_dq_is_deferred_in_a_public_run(built_run):
    run, wb, cells, out = built_run          # runs are PUBLIC by default
    split = kg.dqs_for(wb, cells[1])
    deferred_facets = {d["facet"] for d in split["deferred"]}
    assert "primary" in deferred_facets
    assert split["mode"] == "PUBLIC"


def test_deferral_is_disclosure_not_deletion(built_run):
    """The deferred question is carried as INT-Q with the reason — a
    question nobody asked is a defect; one nobody could answer is a finding."""
    run, wb, cells, out = built_run
    routed = kg.route(wb, CAT)
    deferred = routed["categories"][CAT]["deferred"]
    assert deferred, "the Internal Only subcap must defer something"
    assert all(d["discovery_question"].startswith("INT-Q:") for d in deferred
               if "internal" in d["why"].lower() or "INTERNAL" in d["why"])
    assert all("silent" in d["why"] for d in deferred)


def test_contradicts_and_corroborates_stay_askable_whatever_the_toolkit_says(built_run):
    """They ask what the OUTSIDE world says, so they are public by
    construction — an Internal Only primary must not drag them under."""
    run, wb, cells, out = built_run
    split = kg.dqs_for(wb, cells[1], "PUBLIC")
    askable = {d["facet"] for d in split["ask"]}
    assert {"contradicts", "corroborates"} <= askable


def test_hybrid_mode_asks_everything(built_run):
    run, wb, cells, out = built_run
    for c in cells:
        split = kg.dqs_for(wb, c, "HYBRID")
        assert split["deferred"] == []


def test_a_public_only_dq_is_deferred_in_an_internal_run(built_run):
    run, wb, cells, out = built_run
    split = kg.dqs_for(wb, cells[2], "INTERNAL")
    assert any(d["facet"] == "primary" for d in split["deferred"])


# ── routing ──────────────────────────────────────────────────────────────

def test_the_route_names_the_category_agent(built_run):
    run, wb, cells, out = built_run
    routed = kg.route(wb)
    assert routed["categories"][CAT]["agent"] == "research-p1c1-producer"
    assert routed["categories"][CAT]["subcaps"] == sorted(cells)


def test_the_checksum_detects_a_drifted_bank(built_run):
    run, wb, cells, out = built_run
    assert kg.verify(wb) == []
    wb.append("DQ_Bank", {"SubCap_ID": cells[0], "Order": 9,
                          "Facet": "works", "Probe_Tier": "CATALOGUE",
                          "Question": "smuggled", "Mode_Fit": "BOTH"})
    drift = kg.verify(wb)
    assert drift and "changed since the KG was built" in drift[0]


def test_an_unbuilt_kg_says_so_at_resume(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    assert any("never built" in d for d in kg.verify(wb))
    _, state = runstate.resume(run.run_id, run.root)
    assert state["kg_built"] is False


# ── the card consumes the graph ──────────────────────────────────────────

def test_the_work_card_asks_only_what_the_mode_allows(built_run):
    run, wb, cells, out = built_run
    card = orient.orient(wb, CAT, qa_dir=run.qa_dir)["next_card"]
    assert card["kg_built"] is True
    assert card["evidence_mode"] == "PUBLIC"
    blob = json.dumps(card)
    assert "{entity}" not in blob
    facets = {q["facet"] for q in card["questions"]}
    assert "primary" in facets or card["id"] != cells[0]


def test_the_card_carries_the_deferred_questions(built_run):
    run, wb, cells, out = built_run
    # drain to the Internal Only subcap's card
    from fixtures import bank_evidence, good_synthesis, synthesise
    for c in sorted(cells):
        card = orient.orient(wb, CAT, qa_dir=run.qa_dir)["next_card"]
        if card["id"] == cells[1]:
            break
        synthesise(wb, card["id"],
                   good_synthesis(card["id"], bank_evidence(wb, card["id"])))
    assert card["id"] == cells[1]
    assert card["deferred_questions"], "the Internal Only primary must ride as deferred"
    assert all("{entity}" not in d["discovery_question"]
               for d in card["deferred_questions"])


def test_the_toolkit_source_hints_reach_the_card(built_run):
    run, wb, cells, out = built_run
    card = orient.orient(wb, CAT, qa_dir=run.qa_dir)["next_card"]
    hints = [q for q in card["questions"] if q.get("public_sources")]
    assert hints, "the card must carry the toolkit's own source lists"


# ── degradation is reported, never silent ────────────────────────────────

def test_a_missing_toolkit_degrades_loudly_and_still_builds(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    out = kg.build(wb, toolkit_dir=tmp_path / "nowhere")
    assert out["toolkit_problems"], "the degradation must be stated"
    assert out["counts"]["with_toolkit_primary"] == 0
    assert out["counts"]["dqs"] == 2 * 8      # facets + AI, no primaries


def test_the_search_ledger_accepts_the_overlay_facets(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    n = L.append_search(wb, subcap=wb.selected_subcaps()[0],
                        facet="ai_deployment",
                        query='"Acme Credit Union" AI underwriting live',
                        tool="web_search", hits=3, kept=1)
    assert n == 1
