"""REPORTS hands every writable section to the session as persisted workflows
(one per report, `workflows/dma-reports.js`), and the handoff cannot loop.

Owner, 2026-10-06 (First Tech): "start /workflows to enable the report go
faster ... future runs always spin /agents". Two serial producer lanes, each
rewriting a whole report, then one validator reading all nineteen sections,
took hours a round. The real dispatcher now defaults to the workflow; the
stub and `--report-mode lanes` keep the round loop.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine import narrative as N
from fixtures import scored_run

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"


def _pipe(tmp_path, run, **kw):
    from engine import pipeline as P, pipeline_stub as S
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "out",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None,
                     report_mode="workflow", **kw)
    return P.Pipeline(run, opts)


def _quiet_preflight(monkeypatch):
    """The preflight's own blockers (probes nobody ran in a fixture) are
    tested elsewhere; these tests are about the handoff."""
    from engine import brief
    monkeypatch.setattr(brief, "report_preflight", lambda wb, run=None: [])


def test_the_handoff_names_every_writable_section_once_with_its_brief(tmp_path, monkeypatch):
    _quiet_preflight(monkeypatch)
    run, wb, cells, ev = scored_run(tmp_path)
    h = _pipe(tmp_path, run)._reports_handoff()
    assert not h.get("passed")
    doc = json.loads(Path(h["file"]).read_text())
    assert Path(doc["workflow"]).is_file()
    assert doc["workflow"].endswith("workflows/dma-reports.js")
    names = []
    for inv in doc["invocations"]:
        for s in inv["sections"]:
            names.append(f"{inv['report']}:{s['section']}")
            assert Path(s["brief"]).is_file()
            assert s["agent"] == ("report-research-producer" if inv["report"] == "client_research"
                                  else "report-assessment-producer")
    writable = sorted(f"{k}:{s}" for k, r in N.state(wb)["reports"].items()
                      for s in r.get("writable") or [])
    assert sorted(names) == writable and len(names) == len(set(names))


def test_an_unchanged_open_set_stops_the_stage_instead_of_rebuying_agents(tmp_path, monkeypatch):
    from engine import pipeline as P
    _quiet_preflight(monkeypatch)
    run, wb, cells, ev = scored_run(tmp_path)
    p = _pipe(tmp_path, run, stall_rounds=2)
    p._reports_handoff()
    p._reports_handoff()
    try:
        p._reports_handoff()
    except P.StageRefused as e:
        assert "same work" in str(e)
    else:
        raise AssertionError("the third identical handoff was not refused")


def test_section_briefs_carry_the_template_numbers_rule(tmp_path, monkeypatch):
    _quiet_preflight(monkeypatch)
    run, wb, cells, ev = scored_run(tmp_path)
    h = _pipe(tmp_path, run)._reports_handoff()
    doc = json.loads(Path(h["file"]).read_text())
    for inv in doc["invocations"]:
        for s in inv["sections"]:
            text = Path(s["brief"]).read_text()
            assert "guidance, not constants" in text and "never refused" in text


def test_the_cli_defaults_reports_to_the_workflow_with_the_real_dispatcher():
    from engine import pipeline as P
    src = Path(P.__file__).read_text()
    assert 'report_mode=getattr(a, "report_mode", None) or ("lanes" if a.dispatcher == "stub"' in src
    assert '"--report-mode"' in src


def test_the_hook_turns_a_reports_handoff_into_workflow_calls(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "stage_advance", PLUGIN / "scripts" / "hooks" / "stage_advance.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    f = tmp_path / "07_qa" / "reports_workflow.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"workflow": "/w/dma-reports.js", "then": "driver",
                             "invocations": [{"report": "assessment"},
                                             {"report": "client_research"}]}))
    event = {"tool_name": "Bash",
             "tool_input": {"command": "python3 -m engine.pipeline run --run R"},
             "tool_response": {"stdout": f"AWAITING_WORKFLOW at REPORTS — {f}"}}
    ctx = sa.awaiting_workflow(event)["hookSpecificOutput"]["additionalContext"]
    assert ctx.count("Workflow({scriptPath:") == 2 and "REPORTS IS YOURS" in ctx


def test_the_reports_workflow_ships_and_names_no_client():
    src = (PLUGIN / "workflows" / "dma-reports.js").read_text()
    assert src.startswith("export const meta")
    assert "narrative write" in src and "narrative review" in src
    assert "length_notes" in src
    for leaked in ("susser", "Susser", "swbc", "SWBC", "First Tech", "first-tech"):
        assert leaked not in src
