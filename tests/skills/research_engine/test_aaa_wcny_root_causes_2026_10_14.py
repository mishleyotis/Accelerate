"""AAA Western and Central New York (aaa-wcny-2026-10-14): the root causes
behind round 1's 13 failing categories, each closed at the write.

Round 1 returned 3 of 16 categories passing and 75 named cells failing:
boilerplate on 13 declared absences, challenge FAILs a write could have
refused (an owed facet never fired, a CEILING_ESTIMATE with no uncertainty),
a test-site citation, one URL banded two ways, and $28.04 of in-session
agent spend the driver never booked. Each test below reproduces the shape
the run hit and pins the refusal (or the read) that now stops it.
"""
from __future__ import annotations

import pytest

from engine import floors_gate
from engine import ledger as L

from fixtures import CAT, fire_volleys, new_run


def _proxy(wb, cell):
    q = f'"Acme Credit Union" {cell} proxy: "head of data" OR "data engineer"'
    L.append_search(wb, subcap=cell, facet="works", query=q, tool="exa",
                    hits=0, kept=0, outcome="no hits")
    return q


def _absence(wb, cell, hunted):
    fire_volleys(wb, cell, n=0)
    q = _proxy(wb, cell)
    return L.declare_absence(
        wb, cell, actor="research-p1c1-producer",
        ladder=[{"rung": "direct",
                 "query": f'"Acme Credit Union" {cell} rollout OR "went live"'},
                {"rung": "proxy", "query": q}],
        proxy_log=("hunted the job-posting proxy class — a role naming the "
                   "tool — on the careers page and two boards; nothing named it"),
        what_was_hunted=hunted)


# ── 1. a declared absence the gate would fail as boilerplate ─────────────

#: The shape P4C2.2.9 / P4C2.6.4 / P3C1.4.2 shipped: a long, honest-sounding
#: --hunted that names nothing a reader can check — no entity name, no
#: domain, no date, no E-id.
_UNANCHORED = ("searched the careers pages, the newsroom and trade press for "
               "data virtualization or federation tooling; every result was "
               "generic vendor copy, nothing about this club")


def test_an_absence_whose_found_text_names_nothing_is_refused_at_the_write(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    with pytest.raises(L.LedgerRefusal, match="boilerplate"):
        _absence(wb, cell, _UNANCHORED)
    assert cell not in L.declared_absences(wb)


def test_an_anchored_absence_passes_the_write_and_the_gate_agrees(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    _absence(wb, cell, "searched acme-cu.org careers, the Acme Credit Union "
                       "newsroom and CU Times for data virtualization tooling; "
                       "nothing named it")
    assert cell in L.declared_absences(wb)
    v = floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    assert not [b for b in v["boilerplate"] if b["subcap"] == cell], v["boilerplate"]


# ── 2. the orchestrator's own absence template was refused by the ledger ──

def test_every_absence_template_carries_the_flag_pair_the_ledger_demands():
    """The workflow sheet's 'exact command' carried --validation-question
    without --inferable; the ledger refuses one without the other, so every
    orchestrator that copied it was refused (11 times on AAA WCNY) and
    re-wrote the line by trial. Any prompt surface that spells the command
    out must spell the pair."""
    from pathlib import Path
    plugin = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
    offenders = []
    for f in [*plugin.glob("workflows/*.js"), *plugin.glob("agents/**/*.md"),
              *plugin.glob("skills/dma-research/references/*.md")]:
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if "cli absence" not in line and "absence ${R}" not in line:
                continue
            q = "--validation-question" in line
            inf = "--inferable" in line
            if q != inf:
                offenders.append(f"{f.name}:{i}")
    assert not offenders, offenders


def test_the_sheet_tells_the_orchestrator_how_an_evidenced_cell_bounds_its_claim():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
          / "workflows" / "dma-pillar-research.js").read_text()
    assert '"Absence_Claimed": "YES"' in js and '"Proxy_Log"' in js


# ── 3. a CEILING_ESTIMATE carries its ± range, and the challenger sees it ─

def _ceiling_estimate(cell, eids, **over):
    from fixtures import good_synthesis
    rec = good_synthesis(cell, eids)
    rec.update({"Claim_Label": "CEILING_ESTIMATE", "Ceiling_Band": "Building",
                "Ceiling_Reasoning": ("T2 annual report rows cap the ceiling; "
                                      "concluded at 2.5, Building, with the "
                                      "rollout unconfirmed by a second year.")})
    rec.pop("Uncertainty", None)
    rec.update(over)
    return rec


def test_a_ceiling_estimate_without_its_uncertainty_is_refused(tmp_path):
    from fixtures import bank_evidence
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = bank_evidence(wb, cell, n=3)
    with pytest.raises(L.LedgerRefusal, match="Uncertainty"):
        L.append_synthesis(wb, cell, _ceiling_estimate(cell, eids),
                           actor="research-p1c1-producer")
    L.append_synthesis(wb, cell, _ceiling_estimate(cell, eids, Uncertainty=0.5),
                       actor="research-p1c1-producer")
    assert str(wb.scoring_row(cell).get("Uncertainty")) in ("0.5", "0.50")


def test_the_challenge_packet_carries_the_uncertainty_it_is_judged_on(tmp_path):
    from engine import brief
    from fixtures import bank_evidence
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = bank_evidence(wb, cell, n=3)
    L.append_synthesis(wb, cell, _ceiling_estimate(cell, eids, Uncertainty=0.5),
                       actor="research-p1c1-producer")
    pkt = brief._challenge_cell(wb, wb.scoring_row(cell), cell,
                                wb.evidence_index())
    assert pkt["uncertainty"] in ("0.5", "0.50"), pkt


# ── 4. a volley the collectors never fired is a gap, not a synthesis ──────

def test_a_synthesis_over_an_unfired_owed_facet_is_refused_before_a_challenge(tmp_path):
    """P1C1 x5, P3C4 x3, P4C4 x2: synthesised with owed facets unsearched,
    challenged, FAILed on facet_coverage, re-collected, re-synthesised and
    re-challenged. The write now names the gap instead."""
    from fixtures import bank_evidence, good_synthesis
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = bank_evidence(wb, cell, n=3)
    # take one owed volley back out of the Search_Log, as a collector that
    # never fired `fails` leaves it
    n = wb.delete_rows_where("Search_Log", {"SubCap_ID": cell, "Facet": "fails"})
    assert n >= 1
    with pytest.raises(L.LedgerRefusal, match="volleys_incomplete.*fails"):
        L.append_synthesis(wb, cell, good_synthesis(cell, eids),
                           actor="research-p1c1-producer")


# ── 5. one page, one date; a test host is never the entity speaking ──────

_SPAN = ("Members can refer a friend and both receive a discount on the next "
         "AAA tour booked through the Buffalo travel office this season.")


def _register(wb, cell, url, published=None, excerpt=_SPAN, name="Club page"):
    return L.append_evidence(wb, source_name=name, source_url=url, tier="T5",
                             excerpt=excerpt, subcaps=[cell],
                             published=published)


def test_a_test_or_staging_host_is_refused_at_registration(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    for url in ("https://test.westerncentralnyaaa.com/refer",
                "https://staging.acme-cu.org/rates",
                "https://uat2.acme-cu.org/x",
                "https://www.preview.acme-cu.co.uk/y"):
        with pytest.raises(L.LedgerRefusal, match="non-production host"):
            _register(wb, cell, url)
    # the live host, and a registrable domain that merely starts with dev
    assert _register(wb, cell, "https://westerncentralnyaaa.com/refer")
    assert not L.nonproduction_host("https://dev.to/acme/post")
    assert not L.nonproduction_host("https://testimonials.acme-cu.org/")


def test_one_page_carries_one_date_and_one_recency_band(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    a, b = wb.selected_subcaps()[:2]
    url = "https://westerncentralnyaaa.com/blog/phishing-warning"
    e1 = _register(wb, a, url)                               # undated first
    e2 = _register(wb, b, url, published="2025-11-03",
                   excerpt=_SPAN.replace("discount", "saving"))
    rows = {r["E_ID"]: r for r in wb.rows("Evidence_Detail")}
    assert rows[e1]["Recency"] == rows[e2]["Recency"], "one page banded twice"
    assert str(rows[e1]["Date_Published"])[:10] == "2025-11-03"
    # an omitted date inherits the page's
    e3 = _register(wb, a, url, excerpt=_SPAN.replace("discount", "rebate"))
    assert str({r["E_ID"]: r for r in wb.rows("Evidence_Detail")}[e3]
               ["Date_Published"])[:10] == "2025-11-03"
    # a different date for the same page is refused
    with pytest.raises(L.LedgerRefusal, match="one publication date"):
        _register(wb, b, url, published="2023-01-01",
                  excerpt=_SPAN.replace("discount", "credit"))


# ── 6. an in-session agent briefed by a file under the run root is booked ─

def test_an_agent_whose_prompt_points_into_the_run_root_is_charged(tmp_path):
    """41 repair agents, $28.04, unbooked: each prompt read 'Your complete
    brief is the file <root>/briefs/research_agents/<CAT>_<step>.md' and
    named no run id, so capture skipped every one."""
    import json
    from engine import cost
    run = new_run(tmp_path, n=3, prelim=False)
    d = tmp_path / "proj" / "sess" / "subagents"
    d.mkdir(parents=True)
    brief = run.root / "briefs" / "research_agents" / "P2C2_challenge.md"
    lines = [json.dumps({"type": "user", "message": {"content":
             f"Your complete brief is the file {brief}. Read it in full first."}})]
    lines += [json.dumps({"type": "assistant", "message": {
        "model": "claude-sonnet-x", "usage": {"input_tokens": 10,
        "cache_read_input_tokens": 50_000, "cache_creation_input_tokens": 500,
        "output_tokens": 40}}})] * 4
    (d / "agent-r1.jsonl").write_text("\n".join(lines))
    # a helper that merely READ a run file later is still not the run's spend
    other = [json.dumps({"type": "user", "message": {"content": "summarise logs"}}),
             json.dumps({"type": "assistant", "message": {"content": [
                 {"type": "text", "text": f"read {brief}"}], "model": "claude-sonnet-x",
                 "usage": {"output_tokens": 5}}})]
    (d / "agent-h1.jsonl").write_text("\n".join(other))
    got = cost.capture_workflows(run, base=tmp_path)
    assert got["captured"] == 1 and got["turns"] == 4 and got["usd"] > 0, got
