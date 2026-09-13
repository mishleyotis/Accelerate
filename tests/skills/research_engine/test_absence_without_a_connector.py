"""The one refusal a container can be unable to satisfy.

Measured 2026-09-12 on a live run: no enrichment connector was bound, so no
cell could be declared absent, so no floors gate could pass, so the driver
re-dispatched sixteen lanes until it had spent $96.65 against a $20 budget.
Every OTHER check on an absence — the five volleys, the primary question,
both ladder rungs, the proxy log — a lane satisfies with the built-in web
tools. `absence_single_tool` it cannot, and no agent can bind a connector
from inside a run: they bind once, at session start.

Refusing anyway does not buy the enrichment. It buys re-dispatch.

So the refusal lifts on a MEASUREMENT and never on a claim: the caller asks
for the degraded path AND the run's own recorded connector baseline — written
by the preflight, before any cell was worked — must prove the connector was
never there. The absence is then written with its rigour reduced and the
reason on the row, because "no connector answered" and "the world holds
nothing" read identically in a payload and mean opposite things.

The gate reads the same measurement (AUD-0117: read and write must agree), so
the writer and the gate cannot disagree about the same cell.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from engine import brief, floors_gate, ledger as L
import fixtures as F

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
sys.path.insert(0, str(PLUGIN / "scripts"))
import connector_contract as cc  # noqa: E402

LADDER_PROXY = ("hunted the leadership_title proxy class across the site, "
                "LinkedIn and the annual report; nothing names one")


def _bound_tools():
    fam = cc.families()
    return [fam["exa"][0], fam["tavily"][0], fam["clay"][0]]


def _run(tmp_path, tools, n=4):
    """A run whose cells are fully worked THROUGH WEB SEARCH ONLY — every
    askable volley, both ladder rungs, nothing else missing."""
    run = F.new_run(tmp_path, n=n)
    wb = run.open()
    if tools is not None:
        cc.write_baseline(tools, str(run.root))
    for cell in wb.selected_subcaps():
        F.fire_volleys(wb, cell, n=1)
        for rung in ("direct", "proxy"):
            L.append_search(wb, subcap=cell, facet="works",
                            query=f'"Acme Credit Union" {cell} {rung} probe',
                            tool="web_search", hits=0, kept=0, outcome="no hits")
    return run, wb


def _declare(wb, cell, *, opt_in):
    return L.declare_absence(
        wb, cell, actor="research-p1c1-producer",
        ladder=[{"rung": "direct",
                 "query": f'"Acme Credit Union" {cell} direct probe'},
                {"rung": "proxy",
                 "query": f'"Acme Credit Union" {cell} proxy probe'}],
        proxy_log=LADDER_PROXY,
        what_was_hunted=(f"a public artefact naming {cell} at Acme Credit Union "
                         f"across five volleys and two ladder rungs since 2024; "
                         f"nothing bears on the cell"),
        enrichment_unavailable=opt_in)


# ── what the baseline says, and only the baseline ───────────────────────

def test_no_baseline_means_unverified_not_unavailable(tmp_path):
    run, wb = _run(tmp_path, None, n=1)
    b = L.enrichment_binding(wb)
    assert b["known"] is False and b["bound"] is False, (
        "an absent baseline proves nothing — and every caller must read "
        "`known` before `bound`")


def test_the_baseline_says_bound_when_the_connectors_are_there(tmp_path):
    run, wb = _run(tmp_path, _bound_tools(), n=1)
    b = L.enrichment_binding(wb)
    assert b["known"] and b["bound"] and b["missing"] == []


def test_the_baseline_names_what_is_missing(tmp_path):
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"], n=1)
    b = L.enrichment_binding(wb)
    assert b["known"] and not b["bound"]
    assert b["missing"] and "exa" in b["missing"]
    assert "bind at start" in b["reason"], (
        "the reason must say why no agent can fix this from inside the run")


# ── the writer ──────────────────────────────────────────────────────────

def test_the_deadlock_still_reproduces_without_the_opt_in(tmp_path):
    """THE REPRODUCTION. Unchanged behaviour is the default: a lane that does
    not ask for the degraded path meets the refusal it always met."""
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"], n=1)
    with pytest.raises(L.LedgerRefusal) as e:
        _declare(wb, wb.selected_subcaps()[0], opt_in=False)
    assert "an absence is declared only after an enrichment connector" in str(e.value)


def test_a_measured_unavailability_lets_the_absence_through(tmp_path):
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"], n=1)
    cell = wb.selected_subcaps()[0]
    out = _declare(wb, cell, opt_in=True)
    assert out["rigour"] == "REDUCED"
    assert "short of" in out["degraded_reason"]


def test_the_row_says_the_absence_was_worked_with_one_hand_tied(tmp_path):
    """A degradation nobody can read from the workbook is a silent thinning.
    It lands on the row AND on the provenance record."""
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"], n=1)
    cell = wb.selected_subcaps()[0]
    _declare(wb, cell, opt_in=True)
    fresh = run.open()
    assert "REDUCED RIGOUR" in str(fresh.scoring_row(cell)["Triangulation"])
    prov = [r for r in fresh.rows("Provenance")
            if str(r.get("SubCap_ID")) == cell
            and str(r.get("Step")) == "absence"]
    assert prov and "REDUCED RIGOUR" in str(prov[0]["Detail"])


def test_a_bound_connector_that_was_never_asked_is_still_refused(tmp_path):
    """THE ANTI-HOLLOWING PROPERTY. The lane cannot claim a degradation it
    does not have — the baseline, not the lane, is the witness."""
    run, wb = _run(tmp_path, _bound_tools(), n=1)
    with pytest.raises(L.LedgerRefusal) as e:
        _declare(wb, wb.selected_subcaps()[0], opt_in=True)
    msg = str(e.value)
    assert "does not apply" in msg
    assert "WAS available and was not asked" in msg


def test_an_unverifiable_claim_is_refused(tmp_path):
    """No baseline, so nothing here can prove the connector was absent. A run
    that skipped its preflight does not get the degraded path by default."""
    run, wb = _run(tmp_path, None, n=1)
    with pytest.raises(L.LedgerRefusal) as e:
        _declare(wb, wb.selected_subcaps()[0], opt_in=True)
    assert "An unverified claim is not a degradation" in str(e.value)


def test_every_other_refusal_survives_the_degraded_path(tmp_path):
    """Only the connector rung lifts. Unfired volleys, a missing ladder rung
    and a thin proxy log are all still refused with --enrichment-unavailable,
    because a lane can satisfy every one of them with the web tools alone."""
    run = F.new_run(tmp_path, n=1)
    wb = run.open()
    cc.write_baseline(["Read", "Bash", "WebSearch"], str(run.root))
    cell = wb.selected_subcaps()[0]
    with pytest.raises(L.LedgerRefusal) as e:          # nothing fired at all
        _declare(wb, cell, opt_in=True)
    assert "volley(s) never fired" in str(e.value)

    F.fire_volleys(wb, cell, n=1)                      # volleys, but no ladder
    with pytest.raises(L.LedgerRefusal) as e:
        _declare(wb, cell, opt_in=True)
    assert "are owed on every absence" in str(e.value)


# ── the gate, reading the same measurement ──────────────────────────────

def test_a_degraded_category_reaches_a_passing_gate(tmp_path):
    """THE POINT. Four cells, honestly worked and honestly declared, in a
    container with no connector: the gate passes, so the category is scored
    rather than re-dispatched forever."""
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"])
    for cell in wb.selected_subcaps():
        _declare(wb, cell, opt_in=True)
    g = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert g["gate"] == "PASS", g["blocking"]
    assert "absence_single_tool" not in g["blocking"]


def test_the_lifted_term_is_still_computed_and_still_disclosed(tmp_path):
    """It stops BLOCKING; it does not stop being true. A finding that
    vanished when it stopped blocking would be a relaxation nobody can see."""
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"])
    cells = wb.selected_subcaps()
    for cell in cells:
        _declare(wb, cell, opt_in=True)
    g = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert len(g["absence_single_tool"]) == len(cells)
    assert "absence_single_tool" in g["advisory"]
    eb = g["enrichment_binding"]
    assert eb["known"] and not eb["bound"] and eb["absence_rigour"] == "REDUCED"
    assert "exa" in eb["missing"]


def test_the_term_still_blocks_where_a_connector_was_available(tmp_path):
    """The gate reads the run's baseline, exactly as the writer does, so the
    two cannot disagree about the same cell."""
    run, wb = _run(tmp_path, _bound_tools())
    g = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert "absence_single_tool" in g["blocking"]
    assert g["enrichment_binding"]["absence_rigour"] == "FULL"


def test_an_unverified_run_keeps_the_term_blocking(tmp_path):
    run, wb = _run(tmp_path, None)
    g = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert "absence_single_tool" in g["blocking"]
    assert g["enrichment_binding"]["known"] is False


def test_the_degraded_category_reaches_the_scoring_stage(tmp_path):
    """"What matters is that all categories are scored" (owner, 2026-09-13).
    A passing gate is only half of it — `research_ready` is what opens
    scoring, and it must not refuse over this either."""
    from engine import assessment
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"])
    for cell in wb.selected_subcaps():
        _declare(wb, cell, opt_in=True)
    floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert assessment.research_ready(wb, run.qa_dir) == []


# ── the driver's disclosure path ────────────────────────────────────────

def test_a_category_blocked_only_by_connector_terms_is_disclosable(tmp_path):
    """`enrichment_failing_only` required a PASSING gate, which made it
    unreachable in the case it exists for: with no connector the gate FAILS
    on the connector-derived terms, so the category was refused as an
    ordinary failure instead of disclosed."""
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"], n=1)
    L.append_gate(wb, gate="FLOORS", scope="P1C1", verdict="FAIL",
                  detail="absence_single_tool", blocking=True)
    assert brief.enrichment_failing_only(wb, ["P1C1"]) == ["P1C1"]


def test_a_category_blocked_by_anything_else_is_not(tmp_path):
    """Terms with any other cause still disqualify it — a lane that left
    cells undeclared is not an enrichment problem, and the degraded path is
    exactly what lets it declare them."""
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"], n=1)
    L.append_gate(wb, gate="FLOORS", scope="P1C1", verdict="FAIL",
                  detail="absence_single_tool; absence_undeclared_empty",
                  blocking=True)
    assert brief.enrichment_failing_only(wb, ["P1C1"]) == []
    assert brief.CONNECTOR_DERIVED_TERMS == {"absence_single_tool"}


def test_a_verifier_refusal_still_disqualifies(tmp_path):
    """A lane that fabricated its work is not an enrichment problem."""
    run, wb = _run(tmp_path, ["Read", "Bash", "WebSearch"], n=1)
    L.append_gate(wb, gate="FLOORS", scope="P1C1", verdict="PASS",
                  detail="all terms met", blocking=False)
    L.append_gate(wb, gate="DISPATCH_VERIFY", scope="P1C1", verdict="FAIL",
                  detail="the lane reported work the ledger does not carry",
                  blocking=True)
    assert brief.enrichment_failing_only(wb, ["P1C1"]) == []


# ── the CLI ─────────────────────────────────────────────────────────────

def test_the_flag_exists_and_is_threaded_through():
    import inspect
    from engine import cli
    text = inspect.getsource(cli.main)
    assert '"--enrichment-unavailable", action="store_true"' in text
    assert "enrichment_unavailable=a.enrichment_unavailable" in text
