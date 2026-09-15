"""PRELIM buys the deep background once, before any category is dispatched.

Owner, 2026-08-31: "Let the technographic scans happen in the prelim
alongside leadership enrichment with contacts and thought leadership signals
such that when the category research happens they already have deep
background from enrichment."

WHAT WAS WRONG. PRELIM's technology baseline closed on ONE Tech_Register
row, and the deliberate four-layer scan ran AFTER the categories. So the
baseline was whatever the first search happened to trip over, and sixteen
researchers then rediscovered the estate one system at a time, each blind to
what the other fifteen had found — paying for the same context sixteen times
and getting a worse version of it. Leadership closed on a description of a
structure ("digital ownership sits with a Chief Digital Officer"), which is
not a fact a researcher can search, date, or match to a platform decision.

These pin the floors that move that work forward.
"""
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2].parent / (
    "plugins/dma-insights/skills/dma-research")
sys.path.insert(0, str(ENGINE))

from engine import contract as C, ledger as L, prelim, techscan  # noqa: E402
from fixtures import close_prelim, new_run  # noqa: E402


def _profile_evidence(wb):
    """One registered institution-profile source, which every PRELIM
    section must cite: an uncited paragraph about a named institution is
    refused before any of the floors below are even reached."""
    return L.append_evidence(
        wb, source_name="NCUA Call Report — 2025 Q4",
        source_url="https://ncua.example/callreport/2025", tier="T1",
        excerpt=("Acme Credit Union is a state-chartered, federally insured "
                 "credit union serving 1.1 million members across 72 "
                 "branches, with 1,850 full-time employees as at 31 "
                 "December 2025."),
        subcaps=[], published="2025-12-31")


def _state(wb, section):
    return next(s for s in prelim.state(wb)["sections"]
                if s["section"] == section)


# ── the four-layer floor ──────────────────────────────────────────────────

def test_one_row_no_longer_closes_the_technology_baseline(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    eid = _profile_evidence(wb)
    techscan.record(wb, product="Alkami", vendor="Alkami", layer="CUST",
                    status="CONFIRMED", method="public_document",
                    basis="named as the digital banking platform",
                    providers=["web"], subcaps=[], evidence_ids=[eid],
                    source_urls=["https://example.test/a"], as_of="2025-12-31")
    st = _state(wb, "tech_baseline")
    assert st["status"] == "OPEN", (
        "one row is a lucky find, not a scan — and it used to be enough")
    for layer in ("OPS", "DATA", "INFRA"):
        assert layer in st["detail"]
    assert "CUST" not in st["detail"].split("nothing for")[-1]


def test_all_four_layers_close_it(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    eid = _profile_evidence(wb)
    for layer in C.TECH_LAYERS:
        techscan.record(wb, product=f"{layer} system", vendor="Vendor",
                        layer=layer, status="CONFIRMED",
                        method="public_document",
                        basis=f"named in the filing as the {layer} platform",
                        providers=["web"], subcaps=[], evidence_ids=[eid],
                        source_urls=["https://example.test/a"],
                        as_of="2025-12-31")
    assert _state(wb, "tech_baseline")["status"] == "RESEARCHED"


def test_a_layer_searched_and_empty_closes_as_absent_not_as_a_gap(tmp_path):
    """THE DISTINCTION THE WHOLE FLOOR RESTS ON. A layer left out and a layer
    with nothing in it are the same shape in the register and opposite facts
    downstream: one is 'we did not look', the other is 'we looked and this
    client has nothing there'. ABSENT is how the scan says the second."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    eid = _profile_evidence(wb)
    for layer in C.TECH_LAYERS:
        absent = layer == "INFRA"
        techscan.record(
            wb, product=f"{layer} platform", vendor="Vendor", layer=layer,
            status="ABSENT" if absent else "CONFIRMED",
            method="public_document",
            basis=("searched filings, the careers site and three vendor "
                   "case-study indexes; nothing names a hosting platform"
                   if absent else f"named in the filing as the {layer} tier"),
            providers=["web"], subcaps=[], evidence_ids=[eid],
            source_urls=["https://example.test/a"], as_of="2025-12-31")
    assert _state(wb, "tech_baseline")["status"] == "RESEARCHED"
    assert "ABSENT" in C.TECH_STATUS


def test_the_open_fix_says_to_scan_now_rather_than_after_the_categories(
        tmp_path):
    run = new_run(tmp_path, prelim=False)
    fix = _state(run.open(), "tech_baseline")["fix"]
    assert "PRELIM" in fix and "not after the categories" in fix
    assert "ABSENT" in fix


# ── leadership is a contact pass, not a description of a structure ────────

def test_a_structure_without_names_does_not_close_leadership(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    eid = _profile_evidence(wb)
    prelim.narrate(
        wb, "leadership", heading=None, evidence=[eid],
        body=("Digital ownership sits with a Chief Digital Officer reporting "
              "to the chief executive, alongside a Chief Information Officer "
              "who owns the core platform. Both roles predate the current "
              "programme, so the institution is not standing up digital "
              "ownership for the first time."))
    st = _state(wb, "leadership")
    assert st["status"] == "OPEN", (
        "this is the exact prose that used to close the section")
    assert "0 identifiable people" in st["detail"]
    assert "Clay or" in st["fix"] and "Explorium" in st["fix"]


def test_named_people_close_it(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    eid = _profile_evidence(wb)
    prelim.narrate(
        wb, "leadership", heading=None, evidence=[eid],
        body=("Maria Alvarez has been Chief Digital Officer since 2022, "
              "reporting to chief executive Devon Whitfield. The Chief "
              "Information Officer seat has been vacant since March, which "
              "is itself a finding about how the programme is resourced."))
    assert _state(wb, "leadership")["status"] == "RESEARCHED"


def test_a_role_title_is_never_mistaken_for_a_person():
    """The floor must not be satisfiable by capitalised job titles, or it
    passes on exactly the prose it exists to reject."""
    for title in ("Chief Digital Officer", "Credit Union", "Vice President",
                  "Managing Director", "Information Technology"):
        assert not prelim._named_people(title), title
    assert prelim._named_people("Devon Whitfield") == ["Devon Whitfield"]


# ── thought leadership ───────────────────────────────────────────────────

def test_thought_leadership_is_a_prelim_section(tmp_path):
    assert "thought_leadership" in prelim.SECTIONS
    run = new_run(tmp_path, prelim=False)
    assert "thought_leadership" in prelim.state(run.open())["open"]


def test_thought_leadership_blocks_category_dispatch_until_closed(tmp_path):
    """It is a gate, not a nice-to-have: a category researcher weighs its
    findings against what the client has SAID it is doing."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    st = prelim.state(wb)
    assert st["blocks_category_dispatch"]
    with pytest.raises(prelim.PrelimRefusal) as e:
        prelim.require_complete(wb)
    assert "thought_leadership" in str(e.value)


def test_it_may_be_declared_absent_with_a_ladder(tmp_path):
    """A client whose leaders publish nothing is a real client. The absence
    is recorded with the search behind it, never left open and never faked."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    prelim.declare(
        wb, "thought_leadership",
        ladder=("searched conference programmes for the two named leaders, "
                "the trade press archive and the institution's own newsroom "
                "for 2023-2025; no bylines, talks or interviews found"))
    assert _state(wb, "thought_leadership")["status"] != "OPEN"


# ── the phase closes, end to end, through the real refusals ──────────────

def test_the_fixture_closes_prelim_under_every_new_floor(tmp_path):
    run = new_run(tmp_path, prelim=False)
    close_prelim(run)
    st = prelim.state(run.open())
    assert st["prelim_status"] == "COMPLETE" and not st["open"]
    assert not st["blocks_category_dispatch"]


# ── the background reaches the researcher, not just the workbook ──────────

def test_orient_hands_over_the_background_rather_than_pointing_at_it(
        tmp_path):
    """PRELIM's STATUS was always in orient's payload; its CONTENT never
    was. So the compass every researcher runs first said 'PRELIM is closed'
    and left the material to be found — and an agent that has to go and find
    context mostly does not, which is how sixteen researchers each spent a
    volley rediscovering a core platform the run had already named."""
    from engine import orient as O
    run = new_run(tmp_path, prelim=False)
    close_prelim(run)
    out = O.orient(run.open(), "P1C1")
    bg = out["background"]
    assert bg and bg["read_this_before_your_first_search"]

    # the people, by name — the whole point of the contact pass
    assert "Maria Alvarez" in bg["leadership"]["named"]
    assert bg["thought_leadership"], "what they say in public"

    # the estate, by layer, so a system is recognised and not rediscovered
    assert set(bg["tech_estate"]["by_layer"]) == set(C.TECH_LAYERS)
    assert any(r["product"] == "Fiserv DNA"
               for r in bg["tech_estate"]["by_layer"]["OPS"])

    assert bg["peers"] and bg["timeline"]["events"] >= 3


def test_a_layer_searched_and_empty_is_flagged_as_already_paid_for(tmp_path):
    """The distinction a researcher acts on: re-running a search the run
    already made is the duplicated spend this whole change exists to stop."""
    from engine import orient as O
    run = new_run(tmp_path, prelim=False)
    close_prelim(run)
    bg = O.orient(run.open(), "P1C1")["background"]
    assert bg["tech_estate"]["searched_and_empty"] == ["INFRA"]
    assert "already paid for it" in bg["tech_estate"]["note"]


def test_there_is_no_background_while_prelim_is_open(tmp_path):
    """A half-filled background block reads as a complete one, and no card
    is served at that point anyway."""
    from engine import orient as O
    run = new_run(tmp_path, prelim=False)
    assert O.orient(run.open(), "P1C1")["background"] is None
