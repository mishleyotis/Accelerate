"""Two ways a run burned money without anyone being told.

1. NOBODY ASKED WHETHER THE WORK FITS THE LANE. At T1_CORE scope the
   per-subcap design needs 37.7 lane-equivalents of turns and the driver is
   given 16 — every category was over its lane's 200-turn ceiling. A lane
   that cannot finish does not fail loudly: it runs out of turns, hands back,
   and is re-dispatched, re-paying its ~18K-token context floor cold. That is
   knowable before a single lane starts and was never computed.

   Two changes closed it together, and neither closes it alone: capability
   grain (3,905 turns, 48% off) and a ceiling sized to the work (340, because
   the largest category needs 309). Grain alone is 19.5 lane-equivalents;
   340 alone is 22.2. These tests pin both halves and the arithmetic between
   them.

2. THE WATCHDOG SPENT MORE ON A RUN THAT COULD NOT PROGRESS. A run with no
   enrichment connector reads as STALLED, and the hourly `dma-watchdog`
   Routine is told to `--revive` a STALLED run — a signal meaning "burning
   time, writing nothing" wired to a process authorised to spend more on it.
   `--revive` also walked ACTIONABLE rather than AGENT_ADVANCEABLE, so it
   re-dispatched even the states that list already excluded.
"""
from __future__ import annotations

import sys
from pathlib import Path

from engine import contract as C, cost, runstate, watchdog as W
import fixtures as F

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
sys.path.insert(0, str(PLUGIN / "scripts"))
import connector_contract as cc  # noqa: E402


# ── lane fit ────────────────────────────────────────────────────────────

def test_the_turn_cap_is_read_from_the_manifests_not_restated():
    """There is no `--max-turns` on the claude CLI, so the manifest value is
    the ONLY cap a lane has. A second copy here would drift from it in
    silence, which is how the version floors failed."""
    import re
    caps = set()
    for f in sorted((PLUGIN / "agents" / "research" / "categories").glob("*.md")):
        m = re.search(r"^maxTurns:\s*(\d+)", f.read_text(), re.M)
        if m:
            caps.add(int(m.group(1)))
    assert caps, "the research manifests must declare maxTurns"
    assert cost.lane_turn_budget() == min(caps)


def _full_scope(tmp_path):
    tax = C.taxonomy()
    return runstate.start(
        run_id="R-FIT", entity_name="Acme", entity_id="acme",
        sub_vertical="CU", scope_mode="T1_CORE",
        reference_date="2026-08-29", root=tmp_path / "run",
        selected=list(tax.selected(scope="T1_CORE", sv=None)))


def test_the_per_subcap_design_never_fitted_and_still_would_not(tmp_path):
    """THE MEASUREMENT the grain change had to beat, kept as the baseline it
    is measured against. 686 T1_CORE cells x (9 declared facets + 2 overhead)
    = 7,546 turns. Against a 200-turn lane that was 37.7 lane-equivalents for
    16 lanes, and every category over — which is not a slow run, it is a run
    that cannot finish, so it hands back and is re-dispatched, re-paying its
    ~18K-token context floor cold each time."""
    fit = cost.lane_fit(_full_scope(tmp_path).open())
    assert fit["per_subcap_turns"] == 7546, fit["per_subcap_turns"]
    assert fit["per_subcap_turns"] / 200 > 16, (
        "more lane-equivalents of work than there are lanes — at the ceiling "
        "that was in the manifests when this was measured")


def test_capability_grain_is_what_makes_a_full_run_fit(tmp_path):
    """The pairing. Measured 2026-09-13: 686 cells under 129 capabilities;
    one discovery pass per capability plus two smear-legal differentiating
    searches per cell costs 3,905 turns — 48% of the per-subcap design. The
    largest category (P2C2) needs 309, which is why the manifests sit at 340
    and not at the 260 an aggregate reading would have suggested: 16 x 260 =
    4,160 clears the TOTAL and leaves six categories individually over, and a
    category that cannot finish is re-dispatched whatever the total says."""
    fit = cost.lane_fit(_full_scope(tmp_path).open())
    assert fit["grain"] == "capability"
    assert fit["projected_turns"] == 3905, fit["projected_turns"]
    assert fit["saving_vs_per_subcap"] == 0.483, fit["saving_vs_per_subcap"]
    worst = max(r["projected_turns"] for r in fit["categories"])
    assert worst == 309, worst
    assert fit["lane_turns"] >= worst, (
        f"the manifests declare {fit['lane_turns']} turns and the largest "
        f"category needs {worst} — size the lane to the work")
    assert fit["ok"] is True and fit["over"] == []
    assert fit["lane_equivalents"] <= cost.PARALLEL_LANES


def test_a_run_that_cannot_fit_still_says_so_and_why(tmp_path):
    """The check must keep being able to say no — and must not offer
    coarsening the grain as the way out, because `evidence_smear` is what
    stops capability grain becoming category grain."""
    run = _full_scope(tmp_path)
    fit = cost.lane_fit(run.open())
    import unittest.mock as mock
    # `kind=` arrived when the projection learned to model the challenge
    # lane as well as the category lanes.
    with mock.patch.object(cost, "lane_turn_budget", lambda kind="research": 100):
        tight = cost.lane_fit(run.open())
    assert tight["ok"] is False and len(tight["over"]) == 16
    assert "re-dispatched" in tight["why"] and "context floor" in tight["why"]
    assert "evidence_smear" in tight["why"]
    assert fit["projected_turns"] == tight["projected_turns"], (
        "the projection is a property of the WORK; only the verdict moves "
        "with the ceiling")


def test_the_projection_calls_the_same_cells_siblings_as_the_packet(tmp_path):
    """A second definition of 'capability' would drift from the first in
    silence — the packet would group cells one way and the driver would
    budget for another."""
    from engine.brief import capability_of
    tax = C.taxonomy()
    fit = cost.lane_fit(_full_scope(tmp_path).open())
    by_cat = {r["category"]: r["capabilities"] for r in fit["categories"]}
    seen: dict[str, set] = {}
    for cell in tax.selected(scope="T1_CORE", sv=None):
        seen.setdefault(cell.split(".")[0], set()).add(capability_of(cell))
    assert by_cat == {k: len(v) for k, v in seen.items()}


def test_a_small_category_does_fit(tmp_path):
    """The check must be able to say yes, or it is not a check."""
    run = F.new_run(tmp_path, n=4)
    fit = cost.lane_fit(run.open())
    assert fit["ok"] is True and fit["over"] == []


# ── the watchdog ────────────────────────────────────────────────────────

def _run_with_baseline(tmp_path, tools):
    run = F.new_run(tmp_path, n=4)
    run.open()
    cc.write_baseline(tools, str(run.root))
    return run


def test_a_run_with_no_connector_is_blocked_not_merely_stalled(tmp_path):
    run = _run_with_baseline(tmp_path, ["Read", "Bash", "WebSearch"])
    row = W.inspect(run)
    assert row["state"] == "BLOCKED_NO_CONNECTOR"
    assert "A HUMAN attaches the connector" in row["detail"]


def test_that_state_is_actionable_but_never_auto_revived():
    """Someone must be told; no agent can fix it from inside the container."""
    assert "BLOCKED_NO_CONNECTOR" in W.ACTIONABLE
    assert "BLOCKED_NO_CONNECTOR" not in W.AGENT_ADVANCEABLE


def test_a_run_that_holds_its_connectors_is_not_blocked(tmp_path):
    fam = cc.families()
    run = _run_with_baseline(tmp_path, [fam["exa"][0], fam["tavily"][0], fam["clay"][0]])
    assert W.inspect(run)["state"] != "BLOCKED_NO_CONNECTOR"


def test_revive_walks_agent_advanceable_not_actionable():
    """ACTIONABLE means "tell someone", not "an agent can fix it". `--revive`
    walked the wrong list, so it re-dispatched UNREADABLE and HALTED runs
    that AGENT_ADVANCEABLE already excluded."""
    import inspect as _inspect
    text = _inspect.getsource(W.main)
    assert 'r["state"] in AGENT_ADVANCEABLE' in text
    assert 'if r["state"] in ACTIONABLE:\n                revived.append(revive(' not in text


def test_the_lanes_share_no_prompt_prefix_to_warm():
    """The lever that ISN'T. Staggering lane starts so fifteen of sixteen
    read a warm prompt-prefix cache assumes the lanes share a prefix. They do
    not: each is its own `claude -p --agent research-p<X>c<Y>-producer`
    process whose system prompt IS that manifest, prompt caching is a PREFIX
    match, and two research manifests diverge at the agent's own name on line
    2 — 98%+ identical in CONTENT, 20 characters of shared prefix.

    Pinned because the reasoning is seductive and the arithmetic is not: a
    change sold on it would cost dispatch simplicity for nothing."""
    d = PLUGIN / "agents" / "research" / "categories"
    a = (d / "research-p1c1-producer.md").read_text()
    b = (d / "research-p2c2-producer.md").read_text()
    shared = 0
    for x, y in zip(a, b):
        if x != y:
            break
        shared += 1
    assert shared < 64, (
        f"{shared} characters of shared prefix (~{shared // 4} tokens). If "
        f"this ever grows past a few hundred tokens the stagger is worth "
        f"re-measuring; see the note beside cost.PARALLEL_LANES")
    import difflib
    assert difflib.SequenceMatcher(None, a, b).ratio() > 0.9, (
        "the manifests are nearly identical in content — which buys nothing, "
        "and that gap between similarity and shared PREFIX is the whole point")
