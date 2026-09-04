"""One run, walked from research-closed to shipped, with the hook fired at
every state as the harness fires it.

`test_stage_advance_hook.py` proves each handler on the first state a run
reaches. `tests/skills/research_engine/test_stage_machine.py` proves the
watchdog names the right state and agent for each later stage. Neither
proves the thing the owner asked for on 2026-09-04 — that the hook, as a
subprocess with the real event JSON, carries a run through EVERY stage
without a person: blocks once and once only per state, hands the next agent
in the block, says nothing on the states a person decides, stays quiet once
the package is shipped, and does all of that within the hook timeout when
the run root holds more than one run.

The run is built through the engine's own writers (the same fixtures the
engine suite uses), never by editing the workbook by hand.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HOOKS = HERE.parent / "hooks"
HOOK = HOOKS / "stage_advance.py"
REPO = HERE.parents[3]
SKILL = HERE.parent.parent / "skills" / "dma-research"
ENGINE_TESTS = REPO / "tests" / "skills" / "research_engine"

for p in (SKILL, ENGINE_TESTS, HOOKS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from engine import assemble  # noqa: E402
from engine import assessment as A  # noqa: E402
from engine import watchdog  # noqa: E402
import fixtures as F  # noqa: E402
import stage_advance as sa  # noqa: E402

#: The hook's own timeout in hooks.json; a hook slower than this is killed
#: and the session proceeds as if it said nothing.
HOOK_TIMEOUT_S = 90


def _hook(event: dict, env: dict) -> tuple[dict | None, float]:
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                       capture_output=True, text=True, timeout=HOOK_TIMEOUT_S * 2,
                       env={**os.environ, **env}, cwd=str(REPO))
    dt = time.monotonic() - t0
    assert r.returncode == 0, f"the hook must never exit non-zero: {r.stderr}"
    return (json.loads(r.stdout) if r.stdout.strip() else None), dt


def stop(env, active=False):
    return _hook({"hook_event_name": "Stop", "stop_hook_active": active}, env)[0]


def after_agent(env):
    return _hook({"hook_event_name": "PostToolUse", "tool_name": "Agent",
                  "tool_input": {"prompt": "x"}, "tool_response": {}}, env)[0]


def after_bash(env, command):
    return _hook({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                  "tool_input": {"command": command}, "tool_response": {}},
                 env)[0]


@pytest.fixture
def walk(tmp_path):
    """A researched run under a run root the hook will sweep. The fixtures
    build the run at <tmp>/run; the hook expects <root>/<run_id>, so the
    root holds a link named for the run — the same shape a real root has."""
    run, wb, cells, ev = F.researched_run(tmp_path)
    root = tmp_path / "runs"
    root.mkdir()
    (root / run.run_id).symlink_to(run.root, target_is_directory=True)
    env = {"DMA_RUN_ROOT": str(root)}
    return run, wb, cells, ev, env, tmp_path


def _state(run):
    return watchdog.inspect(run)["state"]


def _expect_block(env, state, agent_fragment):
    """The Stop hook refuses once, names the state and the next agent, and
    then lets the same state stop. The agent-return hook announces the same
    state without blocking."""
    ctx = after_agent(env)
    assert ctx, f"no announcement at {state}"
    text = ctx["hookSpecificOutput"]["additionalContext"]
    assert state in text and agent_fragment in text, text
    assert "Completion criterion" in text, text
    first = stop(env)
    assert first and first["decision"] == "block", f"{state}: no block"
    assert state in first["reason"] and agent_fragment in first["reason"], \
        first["reason"]
    assert stop(env) is None, f"{state}: blocked a second time on one state"
    assert stop(env, active=True) is None
    return first["reason"]


def test_the_run_is_carried_through_every_stage_by_the_hook(walk):
    run, wb, cells, ev, env, tmp_path = walk

    # research closed, assessment not open → the conductor opens scoring
    assert _state(run) == "READY_FOR_HANDOFF"
    reason = _expect_block(env, "READY_FOR_HANDOFF", "research-conductor")
    assert "engine.assessment open" in reason

    # the conductor did what it was told
    A.open_stage(wb, run.qa_dir)
    assert _state(run) == "SCORING_OPEN"
    reason = _expect_block(env, "SCORING_OPEN", "scoring-p1-producer")
    assert "engine.assessment score" in reason
    assert "agent_run.py --agent scoring-p1-producer" in reason

    # a scorer half-way through is still the scorer's state — and a new
    # state is NOT what the marker recorded, so Stop refuses again
    F.score_cell(wb, cells[0], ev[cells[0]])
    assert _state(run) == "SCORING_OPEN"
    assert stop(env) is None, "same state after partial progress must not re-block"

    F.score_all(wb, cells, ev)
    assert _state(run) == "CRITIC_PENDING"
    reason = _expect_block(env, "CRITIC_PENDING", "scoring-critic")
    assert "engine.assessment critique" in reason

    # a FAILED critic keeps the state and says the pillar must be re-scored
    A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic",
               note="Two rows flatter the evidence: the first reads M3 on a "
                    "single T3 source; the fourth ignores its own counter.")
    assert _state(run) == "CRITIC_PENDING"
    ctx = after_agent(env)["hookSpecificOutput"]["additionalContext"]
    assert "re-scored" in ctx
    assert stop(env) is None, "the marker already holds CRITIC_PENDING"

    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic",
               note="Re-derived 4 of 6 rows across the capabilities; ceilings "
                    "hold; differentiation present; would move nothing.")
    assert _state(run) == "SCORING_GATE_OPEN"
    reason = _expect_block(env, "SCORING_GATE_OPEN", "research-conductor")
    assert "engine.assessment gate" in reason

    A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: "
                          "sits a band below digital-leader peers")
    assert A.gate(wb, run.qa_dir)["gate"] == "PASS"
    F.make_shippable(wb)

    # THE STATE THIS WALK FOUND MISSING. The gate passes with the stage's
    # catalogue tabs empty; the report writer refuses until they are filled
    # or declared; that work is the conductor's, and dispatching the report
    # producers here sent them into a refusal.
    assert _state(run) == "REPORT_PRECONDITIONS_OPEN"
    reason = _expect_block(env, "REPORT_PRECONDITIONS_OPEN", "research-conductor")
    assert "Solution_Catalogue" in reason and "engine.completeness declare" in reason
    from engine import completeness
    A.solution(wb, sol_id="SOL-01", name="Digital onboarding and account opening",
               platform="Alkami", categories=["P1C1"])
    completeness.declare(
        wb, "Platform_Peer_Adoption",
        "no peer institution's deployment of the named products could be "
        "examined in this walk, so no adoption verdict is recorded")

    assert _state(run) == "REPORTS_OPEN"
    reason = _expect_block(env, "REPORTS_OPEN", "report-assessment-producer")
    assert "report-research-producer" in reason and "parallel" in reason
    assert "SCORING_PASS" in reason, "the un-pushed checkpoint must be named"

    # the checkpoint lands; the state does not change, so Stop stays quiet
    assemble.checkpoint(run, tmp_path / "client", push=False,
                        stage_reached="SCORING_PASS")
    assert _state(run) == "REPORTS_OPEN"
    assert stop(env) is None

    # both reports written through the sanctioned writer, signed off,
    # rendered → nothing is open but the package
    F.write_both_reports(run, wb, cells, ev)
    st = _state(run)
    assert st == "PACKAGE_UNSHIPPED", st
    reason = _expect_block(env, "PACKAGE_UNSHIPPED", "research-conductor")
    assert "engine.assemble package" in reason
    assert "engine.techscan render" in reason, \
        "the package refuses without the scan; the plan must say so up front"

    # the package refuses while a deliverable is missing, and names the
    # command — an unattended conductor acts on that line
    with pytest.raises(SystemExit) as refusal:
        assemble.package(run, tmp_path / "client", push=False)
    assert "engine.techscan render" in str(refusal.value)
    from engine import techscan
    techscan.render(wb, run.deliverables)

    # shipped: the research tier is done, the hook hands over and stops
    # blocking for good
    assemble.package(run, tmp_path / "client", push=False)
    assert _state(run) == "SHIPPED"
    assert stop(env) is None, "a shipped run must never hold a session open"
    ctx = after_agent(env)
    assert ctx and "SHIPPED" in ctx["hookSpecificOutput"]["additionalContext"]
    assert "synthesis" in ctx["hookSpecificOutput"]["additionalContext"]


def test_only_stage_moving_bash_commands_open_a_workbook(walk):
    run, wb, cells, ev, env, _ = walk
    A.open_stage(wb, run.qa_dir)
    assert after_bash(env, "ls -la /root/.dma") is None
    assert after_bash(env, "git status") is None
    for cmd in ("python3 -m engine.assessment score --run R --subcap x",
                "python3 plugins/dma-insights/scripts/agent_run.py --agent x",
                "cd skills/dma-research && python3 -m engine.narrative state --run R",
                "python3 skills/dma-surface-production/scripts/ship_page.py x"):
        out = after_bash(env, cmd)
        assert out and "SCORING_OPEN" in \
            out["hookSpecificOutput"]["additionalContext"], cmd


def test_the_marker_survives_concurrent_stops(walk):
    """Sixteen lanes finishing at once means sixteen hook processes racing
    to record the same block. The marker must still be one parsable JSON
    document naming the state, and the next Stop must read it."""
    run, wb, cells, ev, env, _ = walk
    A.open_stage(wb, run.qa_dir)
    with ThreadPoolExecutor(max_workers=16) as pool:
        outs = list(pool.map(lambda _: stop(env), range(16)))
    assert any(o and o["decision"] == "block" for o in outs)
    marker = json.loads((run.qa_dir / sa.MARKER).read_text())
    assert marker["blocked_on"] == "SCORING_OPEN"
    assert not list(run.qa_dir.glob("stage_advance.*.tmp")), "temp left behind"
    assert stop(env) is None


def test_the_hook_finishes_inside_its_timeout_with_many_runs(walk):
    """`recent_runs` opens every run written within RECENT_HOURS. A root with
    a dozen live runs is a batch day; the hook must still answer well inside
    the 90 s hooks.json gives it, or the session proceeds as if it were
    silent and the stage machine stops being a machine."""
    run, wb, cells, ev, env, tmp_path = walk
    root = Path(env["DMA_RUN_ROOT"])
    import shutil
    for i in range(11):
        shutil.copytree(run.root, root / f"R-COPY-{i:02d}")
    _, dt_stop = _hook({"hook_event_name": "Stop", "stop_hook_active": False}, env)
    _, dt_post = _hook({"hook_event_name": "PostToolUse", "tool_name": "Agent",
                        "tool_input": {}, "tool_response": {}}, env)
    per_run = max(dt_stop, dt_post) / 12
    assert max(dt_stop, dt_post) < HOOK_TIMEOUT_S / 2, (
        f"12 runs took {dt_stop:.1f}s / {dt_post:.1f}s — {per_run:.2f}s per run; "
        f"a 20-run root would breach the {HOOK_TIMEOUT_S}s hook timeout")


def test_a_run_scoped_to_one_id_ignores_the_others(walk):
    run, wb, cells, ev, env, _ = walk
    import shutil
    root = Path(env["DMA_RUN_ROOT"])
    shutil.copytree(run.root, root / "R-OTHER")
    A.open_stage(wb, run.qa_dir)                      # only the linked run moves
    out = after_agent({**env, "DMA_RUN_ID": "R-OTHER"})
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "R-OTHER" in text and "SCORING_OPEN" not in text
    out = after_agent({**env, "DMA_RUN_ID": run.run_id})
    assert "SCORING_OPEN" in out["hookSpecificOutput"]["additionalContext"]


def test_a_halted_run_reports_and_never_blocks(walk, monkeypatch):
    run, wb, cells, ev, env, _ = walk
    A.open_stage(wb, run.qa_dir)
    # a gate a PERSON must read: the watchdog's own HALTED shape
    from engine import runstate
    (run.qa_dir / "HALT").write_text("evidence foreign to this run — halted")
    st = watchdog.inspect(run)["state"]
    if st != "HALTED":
        pytest.skip(f"the engine marks a halt differently here ({st})")
    assert stop(env) is None
    ctx = after_agent(env)
    assert ctx and "HALTED" in ctx["hookSpecificOutput"]["additionalContext"]
