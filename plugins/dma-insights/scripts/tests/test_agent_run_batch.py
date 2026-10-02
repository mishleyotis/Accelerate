"""Sixteen lanes have to actually be sixteen, and be graded like one.

REPORTED 2026-08-30 from a live research run in another account: "the agents
seem not to be running concurrently ... the agents keep on blocking until one
completes. How is parallelism achieved?"

They were right, and the gap was structural rather than a bug in any one
place:

  * `engine.cost.schedule()` divides projected wall clock by
    `PARALLEL_LANES = 16` and its own docstring says "parallelism is a
    property of the DISPATCH, not of the work".
  * `research-conductor` says "dispatch independent categories in parallel
    where the harness allows" — a hedge nothing measures.
  * `agent_run.py`, the ONLY dispatch this plugin ships for sessions with no
    Agent tool, ran `subprocess.run` — one child, synchronously, per
    process invocation.

So the estimate divided by sixteen and the dispatch supplied one. A run
projected at two hours took sixteen times its research phase, and nothing in
the pipeline could notice, because no one had written down that the divisor
had to come from somewhere.

`--batch` is that somewhere. These tests hold it to the two things that make
it worth having: the lanes are concurrent IN FACT, and a lane is graded
exactly as strictly as a solo dispatch.
"""
import importlib.util
import json
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "dma-insights" / "scripts" / "agent_run.py"
if not SCRIPT.exists():                     # running from the repo root
    SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "agent_run.py"


def _module():
    spec = importlib.util.spec_from_file_location("agent_run", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Result:
    def __init__(self, code=0, out="x" * 300, err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def _sleeper(seconds, **kw):
    def fake(cmd, **_):
        time.sleep(seconds)
        return _Result(**kw)
    return fake


def _rows(n):
    names = [f"research-p{p}c{c}-producer"
             for p in (1, 2, 3, 4) for c in (1, 2, 3, 4)]
    return [{"agent": names[i % 16], "prompt": "go"} for i in range(n)]


def test_lanes_run_concurrently_in_fact(monkeypatch, tmp_path):
    """The claim under test is wall clock, so wall clock is what is measured.

    Eight children that each sleep 0.4s take ~3.2s in one lane. If eight
    lanes do not finish in well under that, they are not lanes.
    """
    m = _module()
    monkeypatch.setattr(m.subprocess, "run", _sleeper(0.4))
    rows = _rows(8)

    t0 = time.monotonic()
    assert m.run_batch(rows, 8, 60, tmp_path, "X", None) == 0
    parallel = time.monotonic() - t0

    assert parallel < 1.6, (
        f"eight 0.4s children took {parallel:.2f}s across eight lanes — "
        f"serial would be ~3.2s, so these lanes are not concurrent")


def test_one_lane_is_still_serial(monkeypatch, tmp_path):
    """--lanes 1 must remain a real escape hatch.

    A caller that hits a rate limit, or wants a reproducible ordering, needs
    to be able to turn the fan-out off and get the old behaviour back.
    """
    m = _module()
    monkeypatch.setattr(m.subprocess, "run", _sleeper(0.3))
    t0 = time.monotonic()
    assert m.run_batch(_rows(4), 1, 60, tmp_path, "X", None) == 0
    assert time.monotonic() - t0 >= 1.1, "lanes=1 did not serialise"


def test_a_lane_is_graded_as_strictly_as_a_solo_dispatch(monkeypatch, tmp_path):
    """An empty verdict in a lane is a failure, exactly as it is alone.

    This is the defect that would matter most if it were missed: sixteen
    starved children exit 0, and a batch that only checked exit codes would
    report sixteen categories as researched. MEM-0111 is that failure at
    n=1; a batch multiplies it.
    """
    m = _module()
    monkeypatch.setattr(m.subprocess, "run", _sleeper(0, out="tiny"))
    assert m.run_batch(_rows(3), 3, 60, tmp_path, "X", None) == 1, (
        "a batch of empty verdicts reported success — the >=200-character "
        "floor that guards a solo dispatch is not guarding a lane")


def test_a_blocked_child_fails_its_lane(monkeypatch, tmp_path):
    """The measured blocked-marker phrases still count inside a batch."""
    m = _module()
    blocked = "y" * 300 + " was blocked. For security"
    monkeypatch.setattr(m.subprocess, "run", _sleeper(0, out=blocked))
    assert m.run_batch(_rows(2), 2, 60, tmp_path, "X", None) == 1


def test_one_bad_lane_fails_the_batch(monkeypatch, tmp_path):
    """A batch is only as done as its worst lane."""
    m = _module()
    calls = {"n": 0}

    def mixed(cmd, **_):
        calls["n"] += 1
        return _Result(code=0 if calls["n"] != 2 else 3)
    monkeypatch.setattr(m.subprocess, "run", mixed)
    assert m.run_batch(_rows(4), 4, 60, tmp_path, "X", None) == 1


def test_each_lane_gets_its_own_transcript(monkeypatch, tmp_path):
    """Sixteen children writing one stream is a transcript nobody can read,
    and the orchestrator needs each verdict WHOLE to relay it onward."""
    m = _module()
    monkeypatch.setattr(m.subprocess, "run", _sleeper(0))
    out = tmp_path / "lanes"
    assert m.run_batch(_rows(4), 4, 60, tmp_path, "X", out) == 0
    written = sorted(p.name for p in out.glob("*.out"))
    assert len(written) == 4, f"expected one file per lane, got {written}"
    for p in out.glob("*.out"):
        assert len(p.read_text()) >= 200


def test_a_bad_batch_fails_before_it_spends_anything(monkeypatch, tmp_path):
    """Validation is up front: a half-wrong batch must not pay for the half
    that is right before discovering the half that is not."""
    m = _module()
    spent = {"n": 0}

    def counted(cmd, **_):
        spent["n"] += 1
        return _Result()
    monkeypatch.setattr(m.subprocess, "run", counted)

    bad = tmp_path / "b.json"
    bad.write_text(json.dumps([
        {"agent": "research-p1c1-producer", "prompt": "fine"},
        {"agent": "no-such-agent", "prompt": "also fine"},
    ]))
    with pytest.raises(SystemExit) as e:
        m.read_batch(bad)
    assert "unknown agent" in str(e.value)
    assert spent["n"] == 0, "a child ran before the batch was validated"


def test_an_empty_prompt_is_refused_per_row(tmp_path):
    m = _module()
    bad = tmp_path / "b.json"
    bad.write_text(json.dumps([{"agent": "research-p1c1-producer",
                                "prompt": "   "}]))
    with pytest.raises(SystemExit) as e:
        m.read_batch(bad)
    assert "no-op" in str(e.value)


def test_the_default_lane_count_matches_what_the_cost_model_divides_by():
    """The estimate and the dispatch must agree, or the estimate is fiction.

    `cost.schedule()` divides the research phase by PARALLEL_LANES. If the
    dispatch's default is lower, every projection under-reports wall clock
    by exactly that ratio — which is the reported bug, written down as a
    number instead of a hedge.
    """
    m = _module()
    spec = importlib.util.spec_from_file_location(
        "cost", ROOT / "dma-insights" / "skills" / "dma-research"
        / "engine" / "cost.py")
    if not spec or not Path(spec.origin or "").exists():
        pytest.skip("cost.py not resolvable from this layout")
    cost = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(cost)
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"cost.py not importable standalone: {exc}")
    assert m.DEFAULT_LANES == cost.PARALLEL_LANES, (
        f"dispatch defaults to {m.DEFAULT_LANES} lanes while the cost model "
        f"divides wall clock by {cost.PARALLEL_LANES} — every schedule it "
        f"prints is wrong by that ratio")
