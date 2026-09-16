"""Every agent tier gets ITS brief — and a stale install refuses the work.

Measured 2026-09-03: `session_brief.brief()` routed by the substring
"research-", so `report-research-producer` received the category
researcher's brief ("fire five volleys, engine.brief dispatch --category
<YOURS>") and `report-assessment-producer`, `report-validator` and the four
scoring producers received the production submit-boundary rule and no word
about templates, preconditions or the scoring stage. The install check
warned and repaired nothing.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "dma-insights"


def _sb():
    spec = importlib.util.spec_from_file_location(
        "session_brief", PLUGIN / "scripts" / "hooks" / "session_brief.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _brief(agent: str) -> str:
    return _sb().brief({"hook_event_name": "SubagentStart",
                        "agent_type": f"dma-insights:{agent}"})


def test_report_producers_get_the_report_brief_not_the_research_one():
    for agent in ("report-research-producer", "report-assessment-producer",
                  "report-validator"):
        t = _brief(agent)
        assert "narrative preconditions" in t, agent
        assert "references/templates/" in t and "gold_reference.json" in t, agent
        assert "engine.gold_standard report" in t, agent
        assert "engine.brief dispatch" not in t, agent
        assert "five volleys" not in t, agent
        assert "produce only the surface" not in t, agent


def test_the_scoring_tier_is_told_open_has_no_force():
    for agent in ("scoring-p1-producer", "scoring-p4-producer", "scoring-critic"):
        t = _brief(agent)
        assert "engine.assessment state" in t, agent
        assert "NO --force" in t, agent
        assert "engine.assessment gate" in t and "gold_reference.json" in t, agent
        assert "engine.brief dispatch" not in t, agent


def test_category_researchers_still_get_the_research_brief():
    for agent in ("research-p1c1-producer", "research-p4c4-producer",
                  "technographic-scanner"):
        t = _brief(agent)
        assert "five volleys" in t and "engine.brief dispatch" in t, agent
        assert "surface-producer" not in t, agent


def test_production_subagents_keep_the_production_brief():
    t = _brief("overview-hero-producer")
    assert "SUBAGENT" in t and "surface" in t
    assert "narrative preconditions" not in t


def test_a_stale_install_refuses_research_work(monkeypatch):
    sb = _sb()
    import sys
    import types
    fake = types.SimpleNamespace(
        compare=lambda: {"ok": False, "status": "STALE"},
        summary=lambda v: "STALE: installed 0.9.12 (47 agents) vs published 1.17.0 (74 agents)")
    monkeypatch.setitem(sys.modules, "plugin_version", fake)
    text = sb.install_warning()
    assert "RESEARCH, SCORING AND REPORT WORK IS REFUSED" in text
    assert "doctor.py --heal" in text
    assert "engine.pipeline run" in text
    # the healed-mid-session state is NOT a refusal
    fake.compare = lambda: {"ok": False, "status": "UPDATED_MID_SESSION"}
    text = sb.install_warning()
    assert "IS REFUSED" not in text and "doctor.py --heal" in text
    # an OK install says nothing
    fake.compare = lambda: {"ok": True, "status": "OK"}
    assert sb.install_warning() == ""


def test_the_top_session_brief_carries_the_install_verdict():
    sb = _sb()
    top = sb.brief({"source": "startup"})
    assert "research-conductor" in top


# ── the scope the brief now states as a fact ───────────────────────────
#
# "Work only your own category" was advice until 2026-09-14: no write path
# checked it (MEM-0514). The engine refuses it now, so the brief names the
# boundary the lane will actually meet — and names the route a genuine
# cross-category find takes, because a lane that has been refused needs
# somewhere to put the finding.

def test_a_category_lane_is_told_which_category_is_its_own():
    text = _brief("research-p3c2-producer")
    assert "YOUR SCOPE IS P3C2" in text
    assert "handback" in text, "a refusal with no route is a dead end"


def test_a_pillar_scorer_is_told_its_pillar():
    text = _brief("scoring-p4-producer")
    assert "YOUR SCOPE IS P4" in text and "pillar" in text


def test_an_agent_whose_name_declares_no_scope_is_not_given_one():
    """The conductor and the specialists write across the run by design."""
    for agent in ("research-conductor", "technographic-scanner",
                  "enrichment-web-specialist"):
        assert "YOUR SCOPE IS" not in _brief(agent), agent


def test_the_scope_sentence_agrees_with_the_engine_that_enforces_it():
    """Two statements of one rule drift. This asserts they agree today, and
    fails the day the engine's table and the brief disagree."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                           / "plugins" / "dma-insights" / "skills" / "dma-research"))
    from engine import scope as engine_scope
    for agent, expected in (("research-p3c2-producer", "P3C2"),
                            ("scoring-p4-producer", "P4")):
        assert engine_scope.classify(agent)["scope"] == expected
        assert f"YOUR SCOPE IS {expected}" in _brief(agent)


# ── the compaction case: the brief existed, the BINDING did not ──────────

def _sb_mod():
    return _sb()


def test_the_compact_brief_carries_the_resume_pointer():
    """A compacted session has to recover WHERE IT WAS from the run, not
    from the summary — the summariser chose what to keep, and what it kept
    is not evidence of what the run holds."""
    t = _sb().brief({"hook_event_name": "SessionStart", "source": "compact"})
    assert "COMPACTED" in t
    assert "engine.cli resume" in t
    assert ROUTING_IN(t)


def ROUTING_IN(t: str) -> bool:
    return "routing.md" in t


def test_post_compact_gets_the_same_brief_as_a_compact_session_start():
    """The binding was what was missing: `BY_SOURCE["compact"]` existed and
    only SessionStart could reach it, so a compaction that did NOT restart
    the session re-entered with no brief at all."""
    post = _sb().brief({"hook_event_name": "PostCompact", "trigger": "auto"})
    start = _sb().brief({"hook_event_name": "SessionStart", "source": "compact"})
    assert post == start
    assert "COMPACTED" in post


def test_post_compact_emits_the_json_shape_not_bare_stdout():
    """Only SessionStart takes plain stdout. Printing prose on PostCompact
    would be swallowed — the AUD-0004 failure wearing a fix."""
    import json as _json
    import subprocess as _sp
    import sys as _sys
    hook = PLUGIN / "scripts" / "hooks" / "session_brief.py"
    p = _sp.run([_sys.executable, str(hook)],
                input=_json.dumps({"hook_event_name": "PostCompact",
                                   "trigger": "manual"}),
                capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    doc = _json.loads(p.stdout)
    assert doc["hookSpecificOutput"]["hookEventName"] == "PostCompact"
    assert "COMPACTED" in doc["hookSpecificOutput"]["additionalContext"]


def test_a_session_start_still_prints_prose():
    import json as _json
    import subprocess as _sp
    import sys as _sys
    hook = PLUGIN / "scripts" / "hooks" / "session_brief.py"
    p = _sp.run([_sys.executable, str(hook)],
                input=_json.dumps({"hook_event_name": "SessionStart",
                                   "source": "startup"}),
                capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip().startswith("dma-insights: route before you produce")


# ── the hook states the bind as a fact, for the checks that run later ─────
#
# Measured 2026-09-16: `doctor.py`, run from the Bash tool, has no
# CLAUDE_PLUGIN_ROOT and read the install record — 1.19.0, a cache copy the
# session was not running. The hook has the variable and IS a file in the
# bound tree; it writes the fact down where `plugin_version.bound_root` reads
# it back.

def test_the_session_start_hook_records_the_tree_it_ran_from(tmp_path, monkeypatch):
    import json
    import os
    import subprocess
    import sys
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN)
    env["CLAUDE_PID"] = str(os.getpid())
    env["DMA_BOUND_PLUGIN_DIR"] = str(tmp_path)
    env["CLAUDE_CODE_SESSION_ID"] = "sess-test"
    proc = subprocess.run(
        [sys.executable, str(PLUGIN / "scripts" / "hooks" / "session_brief.py")],
        input=json.dumps({"session_id": "sess-test",
                          "hook_event_name": "SessionStart", "source": "startup"}),
        capture_output=True, text=True, env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr
    rec = json.loads((tmp_path / f"bound_plugin-{os.getpid()}.json").read_text())
    assert rec["pid"] == os.getpid()
    assert rec["session_id"] == "sess-test"
    assert rec["plugin_root"] == str(PLUGIN.resolve())
    assert rec["recorded_at"] > 0


def test_the_hook_survives_an_unwritable_record_dir(tmp_path, monkeypatch):
    """Fail OPEN: a breadcrumb that cannot be written must not cost the brief."""
    import json
    import os
    import subprocess
    import sys
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN)
    env["CLAUDE_PID"] = str(os.getpid())
    blocker = tmp_path / "a-file-not-a-dir"
    blocker.write_text("x")
    env["DMA_BOUND_PLUGIN_DIR"] = str(blocker / "under-a-file")
    proc = subprocess.run(
        [sys.executable, str(PLUGIN / "scripts" / "hooks" / "session_brief.py")],
        input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
        capture_output=True, text=True, env=env, timeout=60)
    assert proc.returncode == 0
    assert "route before you produce" in proc.stdout


def test_a_hook_run_from_the_bound_checkout_reports_no_stale_install(tmp_path):
    """The live false alarm, end to end: a hook whose CLAUDE_PLUGIN_ROOT is
    this checkout must not tell the session it is NOT running the checkout,
    whatever a five-day-old install record says about a cache copy."""
    import json
    import os
    import subprocess
    import sys
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN)
    env["CLAUDE_PID"] = str(os.getpid())
    env["DMA_BOUND_PLUGIN_DIR"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(PLUGIN / "scripts" / "hooks" / "session_brief.py")],
        input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
        capture_output=True, text=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "NOT running what the checkout publishes" not in proc.stdout, proc.stdout
    assert "IS REFUSED" not in proc.stdout
