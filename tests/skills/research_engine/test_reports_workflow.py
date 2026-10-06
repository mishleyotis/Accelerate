"""REPORTS hands every open section to the session as ONE persisted workflow.

Owner, 2026-10-06 (First Tech): two serial producer lanes, each rewriting a
whole report, then one validator reading all nineteen sections, took hours a
round. The real dispatcher now defaults to the section workflow; the stub and
`--reports-mode lanes` keep the old rounds.
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
                     reports_mode="workflow", **kw)
    return P.Pipeline(run, opts)


def _open_sections(wb):
    return sorted(f"{k}:{s.get('id') or s.get('section')}"
                  for k, r in N.state(wb)["reports"].items() if not r.get("ready")
                  for s in r.get("sections") or [] if s.get("status") != "READY")


def test_the_handoff_names_every_open_section_once_with_its_briefs(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    h = _pipe(tmp_path, run)._reports_handoff()
    assert not h.get("passed") and not h.get("stalled")
    doc = json.loads(Path(h["file"]).read_text())
    assert Path(doc["workflow"]).is_file()
    assert doc["workflow"].endswith("workflows/dma-report-sections.js")
    assert "--reports-mode lanes" in doc["how"]
    [inv] = doc["invocations"]
    names = sorted(f"{s['report']}:{s['section']}" for s in inv["sections"])
    assert names == _open_sections(wb) and len(names) == len(set(names))
    for s in inv["sections"]:
        assert Path(s["brief"]).is_file() and Path(s["validator_brief"]).is_file()
        assert s["producer"] == ("report-research-producer" if s["report"] == "client_research"
                                 else "report-assessment-producer")


def test_an_unchanged_open_set_stops_the_stage_instead_of_rebuying_agents(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    p = _pipe(tmp_path, run, stall_rounds=2)
    assert not p._reports_handoff().get("stalled")
    assert not p._reports_handoff().get("stalled")
    h = p._reports_handoff()
    assert h.get("stalled") and "stayed open" in h["summary"]


def test_the_cli_defaults_reports_to_the_workflow_with_the_real_dispatcher():
    from engine import pipeline as P
    src = Path(P.__file__).read_text()
    assert 'reports_mode=getattr(a, "reports_mode", None) or ("lanes" if a.dispatcher == "stub"' in src
    assert '"--reports-mode"' in src


def test_the_hook_turns_a_reports_handoff_into_one_workflow_call(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "stage_advance", PLUGIN / "scripts" / "hooks" / "stage_advance.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    f = tmp_path / "07_qa" / "reports_workflow.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"workflow": "/w/dma-report-sections.js", "then": "driver",
                             "invocations": [{"sections": [{"report": "assessment",
                                                            "section": "3"}]}]}))
    event = {"tool_name": "Bash",
             "tool_input": {"command": "python3 -m engine.pipeline run --run R"},
             "tool_response": {"stdout": f"AWAITING_WORKFLOW at REPORTS — {f}"}}
    ctx = sa.awaiting_workflow(event)["hookSpecificOutput"]["additionalContext"]
    assert ctx.count("Workflow({scriptPath:") == 1 and "REPORTS ARE YOURS" in ctx
    assert "--reports-mode lanes" in ctx


def test_the_reports_workflow_ships_reviews_independently_and_names_no_client():
    src = (PLUGIN / "workflows" / "dma-report-sections.js").read_text()
    assert src.startswith("export const meta")
    assert "narrative write" in src and "narrative review" in src
    assert "dma-insights:report-validator" in src
    for leaked in ("susser", "Susser", "swbc", "SWBC", "First Tech", "first-tech"):
        assert leaked not in src
