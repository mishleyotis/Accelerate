"""ship_page.py --claim / --verdicts-out: the two flags the driver needs.

The driver (`engine.pipeline`) ships pages as the work becomes ready, from
possibly several processes over an afternoon; `--claim` takes the run's
exclusive lease first and exits 3 — not 1 — when another session holds it,
so a refused claim is never read as a failed page. `--verdicts-out` lands
{page: {status, reasons}} on disk so the driver reads a file, not a
transcript.
"""
import importlib.util
import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
SCRIPT = PLUGIN / "skills" / "dma-surface-production" / "scripts" / "ship_page.py"


def _mod():
    spec = importlib.util.spec_from_file_location("ship_page", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sections(tmp_path, page="techstack"):
    d = tmp_path / "sections"
    d.mkdir()
    (d / f"{page}.techstack.json").write_text(json.dumps(
        {"items": [{"name": "Alkami", "vendor": "Alkami", "layer": "CUST",
                    "status": "CONFIRMED"}], "layers": [], "e_ids": ["E-001"]}))
    return d


def test_a_refused_claim_exits_three_and_submits_nothing(tmp_path, monkeypatch):
    m = _mod()
    calls = []

    def fake_mcp(tool, args):
        calls.append(tool)
        if tool == "claim_run":
            return {"refused": True, "held_by": "other-session", "expires_at": "later"}
        raise AssertionError("submitted past a refused claim")
    monkeypatch.setattr(m, "mcp", fake_mcp)
    out = tmp_path / "v.json"
    rc = m.main(["RUN-1", "techstack", "--sections", str(_sections(tmp_path)),
                 "--claim", "--verdicts-out", str(out)])
    assert rc == m.EXIT_CLAIM_REFUSED == 3
    assert calls == ["claim_run"]
    assert json.loads(out.read_text())["_claim"]["status"] == "claim_refused"


def test_a_granted_claim_precedes_the_submit_and_the_verdict_lands_on_disk(tmp_path, monkeypatch):
    m = _mod()
    calls = []

    def fake_mcp(tool, args):
        calls.append((tool, args.get("run_id"), args.get("producer_version")))
        if tool == "claim_run":
            assert args["session_id"]
            return {"claimed": True, "expires_at": "later"}
        return {"verdict": {"status": "fail", "reasons": ["CG-09 techstack.items[0].status"]}}
    monkeypatch.setattr(m, "mcp", fake_mcp)
    out = tmp_path / "v.json"
    rc = m.main(["RUN-1", "techstack", "--sections", str(_sections(tmp_path)),
                 "--claim", "--verdicts-out", str(out), "--producer", "engine.pipeline"])
    assert rc == 1                                            # a FAIL verdict is still exit 1
    assert [c[0] for c in calls] == ["claim_run", "submit_page_payload"]
    assert calls[0][1:] == ("RUN-1", "engine.pipeline")
    v = json.loads(out.read_text())
    assert v["techstack"]["status"] == "fail" and "CG-09" in v["techstack"]["reasons"][0]


def test_without_claim_the_behaviour_is_unchanged(tmp_path, monkeypatch):
    m = _mod()
    calls = []

    def fake_mcp(tool, args):
        calls.append(tool)
        return {"verdict": {"status": "pass", "reasons": []}}
    monkeypatch.setattr(m, "mcp", fake_mcp)
    rc = m.main(["RUN-1", "techstack", "--sections", str(_sections(tmp_path))])
    assert rc == 0 and calls == ["submit_page_payload"]


def test_the_session_id_prefers_the_harness_token(monkeypatch):
    m = _mod()
    monkeypatch.setenv("DMA_AGENT_SESSION", "sess-abc")
    assert m.session_id() == "sess-abc"
    monkeypatch.delenv("DMA_AGENT_SESSION")
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    assert m.session_id().startswith("ship-page-")
