"""SCORING is priced before it is handed, and every agent before it starts.

MEASURED 2026-10-12 (R-INTERAC-20261010). The SCORING envelope was $25; the
stage cost $87.52 — 11 scorer agents $67.82 ($0.095 a row), 8 critic rounds
$15.87, 4 rescores $1.52, the solutions duty $0.73. The handoff printed
"est $None" and every pillar's invocation carried the whole $25 as its
`remaining`, and `dma-pillar-scoring.js` logged the envelope and checked
nothing. So the overrun surfaced only when the stage closed.

Now `pipeline._scoring_price` prices each pillar from `cost.SCORING_TIER_USD`,
refuses before dispatch when a binding envelope cannot fund the stage, and
hands each pillar its share; the workflow prices every scorer (with its
critic held in reserve), critic and rescore before starting it.
"""
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import cost
from engine import pipeline as PL

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "scoring_governor_harness.mjs"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _driver(rounds=2):
    d = PL.Pipeline.__new__(PL.Pipeline)
    d.opts = SimpleNamespace(critic_rounds=rounds)
    d._stage_budget_hit = None
    return d


def _briefs(tmp_path, pillar, rows):
    out = []
    for n, k in enumerate(rows, 1):
        md = tmp_path / f"scoring-{pillar}-0{n}.md"
        md.write_text("brief")
        md.with_suffix(".json").write_text(json.dumps(
            {"rows_to_score": [{"subcap": f"{pillar}C1.{i}.1"} for i in range(k)]}))
        out.append(str(md))
    return out


def _inv(tmp_path):
    return [{"pillar": "P1", "briefs": _briefs(tmp_path, "P1", [60, 60, 64]),
             "solutions_brief": "sol.md", "budget": None},
            {"pillar": "P2", "briefs": _briefs(tmp_path, "P2", [77, 77]),
             "solutions_brief": "", "budget": None}]


def _env(remaining, binding=True):
    return {"family": "SCORING", "ceiling": remaining, "spent": 0.0,
            "remaining": remaining, "over": False, "binding": binding}


def test_the_stage_is_priced_from_the_measured_tiers(tmp_path):
    inv = _inv(tmp_path)
    est = _driver()._scoring_price(inv, _env(200.0))
    t = cost.SCORING_TIER_USD
    p1 = round(184 * t["scorer_per_row"] + 2 * (t["critic"] + t["rescore"]) + t["solutions"], 2)
    assert est["by_pillar"]["P1"] == pytest.approx(p1, abs=0.05)
    assert est["usd"] == pytest.approx(sum(est["by_pillar"].values()), abs=0.01)
    assert est["usd"] is not None


def test_a_binding_envelope_too_small_for_the_stage_refuses_before_dispatch(tmp_path):
    d = _driver()
    with pytest.raises(PL.StageRefused, match="AT_STAGE_BUDGET before dispatch") as e:
        d._scoring_price(_inv(tmp_path), _env(25.0))
    assert "No agent was paid for" in str(e.value)
    assert d._stage_budget_hit["fits_envelope"] is False


def test_a_reporting_only_envelope_does_not_refuse(tmp_path):
    est = _driver()._scoring_price(_inv(tmp_path), _env(25.0, binding=False))
    assert est["fits_envelope"] is False


def test_each_pillar_gets_its_share_and_its_prices(tmp_path):
    inv = _inv(tmp_path)
    _driver()._scoring_price(inv, _env(100.0))
    shares = [i["budget"]["share_usd"] for i in inv]
    assert sum(shares) == pytest.approx(100.0, abs=0.05)
    for i in inv:
        b = i["budget"]
        assert len(b["brief_usd"]) == len(i["briefs"])
        assert b["usd_per_runtime_token"] == cost.RUNTIME_USD_PER_TOKEN
        assert b["tier_usd"] == cost.SCORING_TIER_USD


def _run(tmp_path, budget, critic=("PASS",), briefs=3, solutions=""):
    args = {"pillar": "P1", "run": "R", "root": "/r", "eng": "/e", "plugin": "/p",
            "briefs": [f"/b/scoring-P1-0{i + 1}.md" for i in range(briefs)],
            "critic_brief": "", "rounds": 2, "budget": budget,
            "solutions_brief": solutions}
    f = tmp_path / "scen.json"
    f.write_text(json.dumps({"args": args, "critic": list(critic)}))
    out = subprocess.run(["node", str(HARNESS), str(f)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _budget(share, remaining=None, brief=6.0, binding=True):
    return {"ceiling": 100, "spent": 0, "remaining": share if remaining is None else remaining,
            "share_usd": share, "binding": binding, "brief_usd": [brief] * 3,
            "tier_usd": dict(cost.SCORING_TIER_USD),
            "usd_per_runtime_token": cost.RUNTIME_USD_PER_TOKEN}


@needs_node
@pytest.mark.parametrize("share", [0, 1, 7.9, 8.0, 14, 20, 21, 25, 40])
def test_the_workflow_never_spends_past_its_share(tmp_path, share):
    r = _run(tmp_path, _budget(share), critic=("FAIL", "FAIL"))
    assert r["spent_usd"] <= share + 1e-6
    labels = [c["label"] for c in r["calls"]]
    scorers = [x for x in labels if " score " in x]
    if scorers:
        # a scorer never starts without its first critic round funded
        assert any("critic r1" in x for x in labels)
    else:
        assert r["result"]["verdict"] == "AT_STAGE_BUDGET"


@needs_node
def test_a_funded_pillar_runs_every_agent(tmp_path):
    r = _run(tmp_path, _budget(40.0), critic=("FAIL", "PASS"))
    labels = [c["label"] for c in r["calls"]]
    assert sum(" score " in x for x in labels) == 3
    assert [x for x in labels if "critic" in x or "rescore" in x] == \
        ["P1 critic r1", "P1 rescore r1", "P1 critic r2"]
    assert r["result"]["verdict"] == "PASS"


@needs_node
def test_a_non_binding_envelope_is_reported_not_enforced(tmp_path):
    r = _run(tmp_path, _budget(1.0, binding=False))
    assert sum(" score " in c["label"] for c in r["calls"]) == 3
    assert any("not binding" in l for l in r["logs"])


@needs_node
def test_the_run_envelope_is_shared_across_pillars(tmp_path):
    """budget.spent() is the turn's pool: a pillar whose share is large but
    whose run envelope another pillar already spent starts nothing more."""
    r = _run(tmp_path, _budget(40.0, remaining=7.0))
    assert r["spent_usd"] <= 7.0 + 1e-6
