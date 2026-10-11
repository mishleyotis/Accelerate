"""R-INTERAC-20261010, 2026-10-11 — research workflows that failed and had to
be restarted by hand. Three defects, one budget handshake:

1. THE SHARE. With the envelope funding the whole scope, the driver split it
   by cells (`remaining x cells / total`). A category's orchestrator and
   challenge are a fixed ~$1.40 whatever its size, so P3C2 and P3C4 ($0.81),
   P1C3 ($1.22) and P4C1 ($1.49) were handed less than one first wave
   ($1.74): the governor refused every wave and they returned
   AT_STAGE_BUDGET in milliseconds, no agent run.
2. THE SPEND ORDER. Only wave 1 held the orchestrator-and-challenge reserve.
   The gap wave and round 2 spent it on collectors, so P1C3 and P3C1 ended
   "syntheses written, challenge not affordable": repair evidence bought,
   never synthesised, no gate verdict.
3. THE VERDICT. A round-2 wave that did not fit replaced the round-1 gate
   verdict (FAIL, with its cells) with a bare AT_STAGE_BUDGET.

The workflow tests run the real workflow source under node against a stubbed
runtime (`research_governor_harness.mjs`), so they test the spend order, not
a reading of it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engine import floors_gate, ledger as L
from engine import pipeline as P, pipeline_stub as S, preflight
from fixtures import (bank_evidence, challenge, good_synthesis, new_run, preflight_doc,
                      researched_run)

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "research_governor_harness.mjs"

# the governor's wave prices from the live R-INTERAC-20261010 handoff
TIER = {"collector_batch": 0.3359, "orchestrator": 0.9472, "challenge": 0.4571}
WAVE = TIER["collector_batch"] + TIER["orchestrator"] + TIER["challenge"]


def _inv(cat, batches=(), repair_batches=(), share=None, rounds=2):
    return {
        "pillar": cat[:2], "cats": [cat], "run": "R-TEST-1",
        "batches": {cat: [list(b) for b in batches]},
        "repairs": {cat: {c: ["absence_single_tool"] for b in repair_batches for c in b}},
        "repair_batches": {cat: [list(b) for b in repair_batches]},
        "models": {"collector": "haiku", "synthesis": "sonnet", "challenge": "sonnet"},
        "batch_cells": 12, "cards_dir": "/tmp/cards", "root": "/tmp/run",
        "eng": "/tmp/eng", "plugin": "/tmp/plugin", "rounds": rounds,
        "entity": "Acme", "domain": "acme.example", "degraded": True,
        "budget": {"family": "RESEARCH", "ceiling": 130.0, "spent": 80.0,
                   "remaining": 50.0, "tier_usd": dict(TIER),
                   "usd_per_output_token": 6.439e-05, "usd_per_runtime_token": 7.5e-06,
                   "share_usd": share, "fits_envelope": True},
    }


# ── 1. the share ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("cat,batches,repair_batches,old_share", [
    ("P3C2", [], [["P3C2.2.1", "P3C2.2.2"]], 0.8136),
    ("P3C4", [["P3C4.8"]], [["P3C4.4.3", "P3C4.5.4"]], 0.8136),
    ("P1C3", [], [["P1C3.1.4", "P1C3.3.3"]], 1.2205),
    ("P4C1", [], [["P4C1.1.8", "P4C1.3.4"]], 1.4917),
])
def test_the_round_floor_covers_the_first_wave_the_interac_shares_did_not(
        cat, batches, repair_batches, old_share):
    inv = _inv(cat, batches, repair_batches)
    floor = P._round_floor_usd(inv, TIER)
    nb = len(batches) + len(repair_batches)
    assert floor == pytest.approx(nb * TIER["collector_batch"]
                                  + TIER["orchestrator"] + TIER["challenge"], abs=1e-4)
    assert old_share < WAVE - 1e-4 and floor >= WAVE - 1e-4, (old_share, floor)


def test_a_category_with_no_batches_is_floored_at_its_gate_only_batch():
    assert P._round_floor_usd(_inv("P2C1"), TIER) == pytest.approx(WAVE, abs=1e-4)


def _handoff(tmp_path, research_budget):
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    p = P.Pipeline(run, P.Options(
        dispatcher=S.StubDispatcher(handlers={"research-p": S.lane_noop,
                                              "finding-challenger": S.lane_noop}),
        reads=S.StubReads(), shipper=S.StubShipper(), push=False,
        folder_root=tmp_path / "out", ingest_poll_s=0, sleep=lambda s: None,
        log=lambda s: None, until="RESEARCH", research_mode="workflow",
        stage_budget={"RESEARCH": research_budget}))
    out = p.run_all()
    if out["outcome"] != "AWAITING_WORKFLOW":
        return out, None
    return out, json.loads(Path(out["handoff"]).read_text())


def test_every_handed_share_funds_a_whole_round_and_the_shares_fit_the_envelope(tmp_path):
    _, doc = _handoff(tmp_path, 1000.0)
    assert doc is not None
    tier = doc["budget"]["tier_usd"]
    remaining = doc["budget"]["remaining"]
    shares = []
    for inv in doc["invocations"]:
        share = inv["budget"]["share_usd"]
        assert share + 1e-6 >= P._round_floor_usd(inv, tier), (inv["cats"], share)
        shares.append(share)
    assert sum(shares) <= remaining + 1e-3


@pytest.mark.parametrize("scale", [0.6, 0.9, 1.0, 1.1, 1.5, 3.0])
def test_no_envelope_size_hands_a_share_below_one_round(tmp_path, scale):
    """Swept around the scope estimate: either the stage refuses before any
    agent is paid for, or every share handed funds one whole round."""
    _, full = _handoff(tmp_path / "full", 1000.0)
    est = full["estimate"]["usd"]
    out, doc = _handoff(tmp_path / f"s{scale}", round(est * scale, 2))
    if doc is None:
        assert out["outcome"] == "STOPPED_STAGE_BUDGET", out
        return
    tier = doc["budget"]["tier_usd"]
    for inv in doc["invocations"]:
        assert inv["budget"]["share_usd"] + 1e-6 >= P._round_floor_usd(inv, tier), \
            (scale, inv["cats"], inv["budget"]["share_usd"])


def test_the_handoff_tiers_are_the_ones_the_floor_is_priced_with(tmp_path):
    _, doc = _handoff(tmp_path, 1000.0)
    t = doc["budget"]["tier_usd"]
    assert set(t) == {"collector_batch", "orchestrator", "challenge"}
    assert all(isinstance(v, float) and v > 0 for v in t.values())


# ── 2 & 3. the spend order and the verdict (the real workflow, under node) ──

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _run(tmp_path, inv, gaps=(), gate="FAIL"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    f = tmp_path / f"scen_{abs(hash(json.dumps(inv, sort_keys=True) + str(gaps) + gate))}.json"
    f.write_text(json.dumps({"args": inv, "gaps": list(gaps), "gate": gate}))
    r = subprocess.run(["node", str(HARNESS), str(f)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    d["labels"] = [c["label"] for c in d["calls"]]
    d["cat"] = d["result"]["categories"][0]
    return d


@needs_node
def test_p1c3_at_its_old_share_challenges_instead_of_buying_unsynthesisable_evidence(tmp_path):
    """The live P1C3 shape: one repair batch, $2.00, the orchestrator names a
    gap. Before: collect, orchestrate, gap collect — and no challenge."""
    d = _run(tmp_path, _inv("P1C3", [], [["P1C3.1.4", "P1C3.3.3"]], share=2.0),
             gaps=["P1C3.1.4: absence_single_tool"])
    assert d["labels"][-1] == "P1C3 challenge r1", d["labels"]
    assert not any("w1g collect" in l for l in d["labels"]), d["labels"]
    assert d["cat"]["gate"] == "FAIL", d["cat"]


@needs_node
def test_p3c4_at_the_drivers_floor_runs_both_batches(tmp_path):
    inv = _inv("P3C4", [["P3C4.8"]], [["P3C4.4.3", "P3C4.5.4"]])
    inv["budget"]["share_usd"] = P._round_floor_usd(inv, TIER)
    d = _run(tmp_path, inv)
    assert sum("w1 collect" in l for l in d["labels"]) == 2, d["labels"]
    assert "P3C4 p1 orchestrate" in d["labels"] and "P3C4 challenge r1" in d["labels"]


@needs_node
def test_a_funded_gap_wave_is_synthesised_before_the_challenge(tmp_path):
    d = _run(tmp_path, _inv("P2C1", [], [["P2C1.1.4"]], share=6.0),
             gaps=["P2C1.1.4: absence_single_tool"])
    i_gap = next(i for i, l in enumerate(d["labels"]) if "w1g collect" in l)
    i_p2 = d["labels"].index("P2C1 p1g orchestrate")
    i_ch = d["labels"].index("P2C1 challenge r1")
    assert i_gap < i_p2 < i_ch, d["labels"]


@needs_node
def test_a_round_two_that_does_not_fit_hands_back_the_gate_verdict(tmp_path):
    d = _run(tmp_path, _inv("P4C4", [], [["P4C4.1.2"]], share=WAVE + 0.01))
    assert "P4C4 challenge r1" in d["labels"]
    assert d["cat"]["gate"] == "FAIL", d["cat"]
    assert d["cat"]["blocking_terms"] == ["challenge_failed: P4C4.1.1"], d["cat"]


@needs_node
def test_every_agent_writes_its_ops_files_in_its_own_directory_under_the_run(tmp_path):
    """P4C1's challenger re-ran an ops file P1C3's had overwritten in the
    shared scratchpad and recorded P1C3's verdicts again: the prompts said
    'ONE ops file' without naming it. Every collector, orchestrator and
    challenge prompt now names its own directory under the run root."""
    seen = []
    for cat in ("P1C3", "P4C1"):
        inv = _inv(cat, [[f"{cat}.1"], [f"{cat}.2"]], [[f"{cat}.3.1", f"{cat}.4.2"]], share=20.0)
        d = _run(tmp_path, inv, gaps=[f"{cat}.3.1: absence_single_tool"])
        for c in d["calls"]:
            assert c["ops"], f"{c['label']} names no OPS DIR"
            assert c["ops"].startswith(inv["root"] + "/07_qa/ops/"), c
            assert f"/{cat}_" in c["ops"], c
            seen.append(c["ops"])
    assert len(seen) == len(set(seen)), sorted(seen)


@needs_node
def test_the_ops_directory_is_stable_so_a_resume_replays_from_cache(tmp_path):
    inv = _inv("P2C2", [["P2C2.1"]], [], share=20.0)
    a = [c["ops"] for c in _run(tmp_path, inv)["calls"]]
    b = [c["ops"] for c in _run(tmp_path / "again", inv)["calls"]]
    assert a == b


@needs_node
@pytest.mark.parametrize("gaps", [(), ("X.1.1: absence_single_tool",)])
def test_whatever_the_share_bought_evidence_is_always_synthesised_and_challenged(tmp_path, gaps):
    """The invariant behind all three defects: a category either runs no
    agent at all (refused before spend) or its last collector is followed by
    an orchestrator pass and a challenge."""
    for cents in range(0, 701, 25):
        share = cents / 100
        inv = _inv("P2C3", [["P2C3.1"]], [["P2C3.2.1"], ["P2C3.3.1"]], share=share)
        d = _run(tmp_path, inv, gaps=gaps)
        labels, cat = d["labels"], d["cat"]
        assert "challenge not affordable" not in json.dumps(cat), (share, labels, cat)
        assert "orchestrator pass not affordable" not in json.dumps(cat), (share, labels, cat)
        if not labels:
            assert cat["gate"] == "AT_STAGE_BUDGET", (share, cat)
            continue
        last_collect = max(i for i, l in enumerate(labels) if "collect" in l)
        after = labels[last_collect + 1:]
        assert any("orchestrate" in l for l in after) and any("challenge" in l for l in after), \
            (share, labels)
        assert d["spent_usd"] <= share + 1e-6, (share, d["spent_usd"], labels)


# ── 5. a declared absence that later carries evidence ─────────────────────
#
# P1C1 (five cells) and P4C1.4.3: a repair wave collected for an
# absence_single_tool cell and attached rows, nothing re-synthesised it, and
# the gate called it challenge_missing — a term only a challenger acts on,
# and `record_challenge` refuses a cell with no synthesis author. Handed back
# every round, closable by nobody.

def test_an_evidenced_declared_absence_is_owed_a_synthesis_not_a_challenge(tmp_path):
    run, wb, cells, _ = researched_run(tmp_path, n=6, absent=1)
    cell = cells[-1]
    new = bank_evidence(wb, cell, n=3)            # the repair wave's rows
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "FAIL"
    assert "absence_superseded" in v["blocking"], v["blocking"]
    assert [e["subcap"] for e in v["absence_superseded"]] == [cell]
    assert cell not in v["challenge_missing"], v["challenge_missing"]
    assert floors_gate.blocking_cells(v) == {cell: ["absence_superseded"]}
    with pytest.raises(L.LedgerRefusal, match="no recorded synthesis author"):
        challenge(wb, cell)                        # why challenge_missing could never close
    L.append_synthesis(wb, cell, good_synthesis(cell, new), actor="research-p1c1-producer")
    challenge(wb, cell)
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]


@needs_node
def test_the_orchestrator_is_told_which_absences_it_must_synthesise(tmp_path):
    inv = _inv("P1C1", [], [["P1C1.1.3", "P1C1.2.3"]], share=20.0)
    inv["repairs"]["P1C1"] = {"P1C1.1.3": ["absence_superseded"],
                              "P1C1.2.3": ["absence_single_tool"]}
    d = _run(tmp_path, inv)
    orch = [c for c in d["calls"] if "orchestrate" in c["label"]]
    assert orch and orch[0]["superseded"] == "P1C1.1.3", orch
    assert all(c["superseded"] is None for c in d["calls"] if "orchestrate" not in c["label"])


# ── 6. every blocking term has a repair instruction ───────────────────────
#
# absence_single_tool was the commonest blocking term on the run and the
# collector's repair lines never named it: every repair wave re-fired
# WebSearch, which proves no enrichment effort, and re-failed (P3C2.2.CIB1:
# 27 searches over three rounds, all web_search).

_RENDER = r"""
const fs = require('fs')
const src = fs.readFileSync(process.argv[1], 'utf8')
const b = src.indexOf('// --- PROMPTS BEGIN'), e = src.indexOf('// --- PROMPTS END')
const A = {root: '/r', run: 'R', eng: '/e', repairs: {P1C1: {}}, degraded: JSON.parse(process.argv[2])}
const P = new Function('A', 'ENG', 'R', 'DOMAIN', 'MODELS', 'CARDS',
  src.slice(b, e) + '\nreturn {collectPrompt}')(A, '/e', '--run R', 'd', {}, '/c')
process.stdout.write(P.collectPrompt('P1C1', ['P1C1.1'], 1, {'P1C1.1.1': ['absence_single_tool']}))
"""


def _collect_prompt(degraded: bool) -> str:
    wf = HERE.parents[2] / "plugins" / "dma-insights" / "workflows" / "dma-pillar-research.js"
    r = subprocess.run(["node", "-e", _RENDER, str(wf), json.dumps(degraded)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


@needs_node
def test_every_blocking_gate_term_tells_the_repair_wave_who_closes_it():
    import re
    text = _collect_prompt(True)
    per_term = text[text.index("Per term:"):]
    unrouted = [t for t in floors_gate.BLOCKING_TERMS
                if not re.search(rf"\b{t}\b[^→]*→", per_term)]
    assert not unrouted, f"blocking terms with no repair instruction: {unrouted}"


@needs_node
@pytest.mark.parametrize("degraded", [True, False])
def test_a_single_tool_absence_is_repaired_through_an_enrichment_tool(degraded):
    text = _collect_prompt(degraded)
    line = text[text.index("absence_single_tool →"):]
    line = line[:line.index(". ", line.index("nothing_found"))]
    assert "searxng" in line and "--tool searxng" in line
    assert "never closes this term" in line


@needs_node
def test_an_engine_timeout_falls_back_to_searxng_before_websearch():
    text = _collect_prompt(True)
    assert "An engine error or TIMEOUT sends you to searxng" in text


def test_websearch_is_not_an_enrichment_tool():
    from engine import contract as CC
    assert "web_search" not in CC.ENRICHMENT_TOOLS
    assert {"searxng", "evidence_engine"} <= set(CC.ENRICHMENT_TOOLS)


@needs_node
def test_the_challenge_never_works_a_packet_an_earlier_handoff_left():
    """P3C4, P4C1 and P3C1's challengers found packets 3-8 from earlier
    handoffs in wf_challenge_<CAT>_r1 (every handoff restarts at r1); they
    ignored them, but nothing made them."""
    wf = HERE.parents[2] / "plugins" / "dma-insights" / "workflows" / "dma-pillar-research.js"
    render = _RENDER.replace("return {collectPrompt}", "return {collectPrompt, challengePrompt}").replace(
        "process.stdout.write(P.collectPrompt('P1C1', ['P1C1.1'], 1, {'P1C1.1.1': ['absence_single_tool']}))",
        "process.stdout.write(P.challengePrompt('P1C1', 1))")
    r = subprocess.run(["node", "-e", render, str(wf), "true"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out_dir = "/r/briefs/wf_challenge_P1C1_r1"
    step1 = r.stdout[r.stdout.index("1) "):r.stdout.index("2) ")]
    assert step1.index(f"rm -rf {out_dir}") < step1.index("challenge-batch"), step1
    assert "ONLY the packets this command lists" in step1
