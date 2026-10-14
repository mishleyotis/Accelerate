"""A compaction loses nothing the run records: PreCompact writes the run's
parameters, PostCompact echoes them.

Measured 28-09-2026 (QA audit F-E10-034): after a compaction the brief
re-injected the routing rule only — no run id, root, stage or budget. The
echo is written by `scripts/hooks/param_echo.py` before the compaction
and read back by `session_brief.py` after it; the last test is the echo
diff, which is zero.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from fixtures import new_run

HOOKS = Path(__file__).resolve().parents[3] / "plugins/dma-insights/scripts/hooks"
PLUGIN = HOOKS.parents[1]


def _run_hook(script, event, env):
    e = {**os.environ, **env, "DMA_BRIEF_NO_CONNECTOR": "1"}
    r = subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(event),
                       capture_output=True, text=True, timeout=120, env=e)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _env(run):
    return {"DMA_RUN_ID": run.run_id, "DMA_RUN_ROOT": str(run.root)}


def test_precompact_writes_the_runs_parameters(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    out = _run_hook("param_echo.py", {"hook_event_name": "PreCompact", "trigger": "auto"}, _env(run))
    assert out.strip() == "", "PreCompact prints nothing; it writes"
    doc = json.loads((run.qa_dir / "param_echo.json").read_text())
    assert doc["schema_version"] == "param_echo_v1"
    assert doc["run_id"] == run.run_id and doc["root"] == str(run.root)
    assert doc["workbook_stage"] == "research"
    assert set(doc["budget"]) == {"spent", "ceiling", "remaining", "exhausted"}
    assert set(doc["rounds"]) == {"done", "max", "remaining", "exhausted"}
    assert doc["resume"] == f"python3 -m engine.cli resume --run {run.run_id} --root {run.root}"


def test_postcompact_echoes_what_precompact_wrote(tmp_path):
    """THE ECHO DIFF: every figure the brief prints after the compaction is
    the figure on disk from before it."""
    run = new_run(tmp_path, n=3, prelim=False)
    _run_hook("param_echo.py", {"hook_event_name": "PreCompact"}, _env(run))
    doc = json.loads((run.qa_dir / "param_echo.json").read_text())
    out = _run_hook("session_brief.py", {"hook_event_name": "PostCompact", "trigger": "auto"}, _env(run))
    text = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "PARAMETER ECHO" in text
    for needle in (doc["run_id"], doc["root"], f"workbook stage {doc['workbook_stage']}",
                   doc["written_at"], doc["resume"]):
        assert needle in text, needle
    assert "COMPACTED" in text, "the routing brief is still there"


def test_a_compact_session_start_gets_the_echo_too(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    _run_hook("param_echo.py", {"hook_event_name": "PreCompact"}, _env(run))
    out = _run_hook("session_brief.py", {"hook_event_name": "SessionStart", "source": "compact"}, _env(run))
    assert "PARAMETER ECHO" in out and run.run_id in out
    plain = _run_hook("session_brief.py", {"hook_event_name": "SessionStart", "source": "startup"}, _env(run))
    assert "PARAMETER ECHO" not in plain, "a fresh start lost nothing to echo"


def test_no_run_means_nothing_written_and_the_brief_says_so(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    env = {"DMA_RUN_ROOT": str(empty), "DMA_RUN_ID": ""}
    assert _run_hook("param_echo.py", {"hook_event_name": "PreCompact"}, env).strip() == ""
    assert list(empty.rglob("param_echo.json")) == []
    out = _run_hook("session_brief.py", {"hook_event_name": "PostCompact"}, env)
    text = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "PARAMETER ECHO: none on disk" in text and "engine.cli resume" in text


def test_an_echo_for_another_run_is_not_read(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("param_echo", HOOKS / "param_echo.py")
    pe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pe)
    run = new_run(tmp_path, n=3, prelim=False)
    run.qa_dir.mkdir(parents=True, exist_ok=True)
    (run.qa_dir / "param_echo.json").write_text(json.dumps({"run_id": "R-OTHER", "root": "/x"}))
    assert pe.read_echo(run) is None
    assert "none on disk" in pe.render(None)


def test_precompact_is_bound_to_the_echo():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    cmds = [h["command"] for e in hooks.get("PreCompact", []) for h in e["hooks"]]
    assert any("param_echo.py" in c for c in cmds), "PreCompact is not bound"
    post = [h["command"] for e in hooks["PostCompact"] for h in e["hooks"]]
    assert any("session_brief.py" in c for c in post)
