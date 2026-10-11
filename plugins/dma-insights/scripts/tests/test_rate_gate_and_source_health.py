"""The plugin-side backstop for the raw fallback connectors (brief §6a, §6d).

Burst, breaker and coalescing live in the engine and are tested there; this
suite covers the hook: buckets per source, redirect on exhaustion, FAIL
OPEN on a corrupt state file, and the health log's sidecar + tail-scan."""
import json
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))
import rate_gate  # noqa: E402
import source_health  # noqa: E402

T = "mcp__plugin_dma-insights_"


def test_only_raw_fallbacks_are_gated():
    assert rate_gate.source_of(T + "searxng__searxng_web_search") == "searxng"
    assert rate_gate.source_of(T + "edgar__get_company_facts") == "edgar"
    assert rate_gate.source_of(T + "evidence__research_brief") is None
    assert rate_gate.source_of(T + "connector__get_evidence") is None
    assert rate_gate.source_of("WebSearch") is None


def test_bucket_denies_past_burst_and_refills(tmp_path):
    state = tmp_path / "s.json"
    t = [1000.0]
    clock = lambda: t[0]  # noqa: E731
    payload = {"tool_name": T + "fetch__fetch"}
    codes = [rate_gate.decide(payload, state_path=state, clock=clock)[0] for _ in range(3)]
    assert codes == [0, 0, 2]                     # burst 2, then denied
    code, msg = rate_gate.decide(payload, state_path=state, clock=clock)
    assert code == 2 and "research_brief" in msg and "fetch" in msg
    t[0] += 1.0                                   # 1/s refill
    assert rate_gate.decide(payload, state_path=state, clock=clock)[0] == 0


def test_edgar_gate_never_exceeds_its_rate(tmp_path):
    state = tmp_path / "s.json"
    t = [0.0]
    clock = lambda: t[0]  # noqa: E731
    allowed_at = []
    for i in range(100):
        t[0] += 0.05                              # callers hammer at 20/s
        if rate_gate.decide({"tool_name": T + "edgar__get_financials"}, state_path=state, clock=clock)[0] == 0:
            allowed_at.append(t[0])
    # in any sliding 1-second window at most burst + rate = 8 may pass
    for a in allowed_at:
        assert sum(1 for b in allowed_at if a <= b < a + 1.0) <= 8


def test_corrupt_state_file_fails_open(tmp_path, capsys):
    state = tmp_path / "s.json"
    state.write_text("{not json")
    code, _ = rate_gate.decide({"tool_name": T + "parallel__web_search"}, state_path=state)
    assert code == 0
    assert "fail open" in capsys.readouterr().err
    assert json.loads(state.read_text()) == {}


def test_lock_timeout_fails_open(tmp_path, capsys):
    state = tmp_path / "s.json"
    code, _ = rate_gate.decide({"tool_name": T + "parallel__web_search"}, state_path=state,
                               lock=lambda fh, timeout: False)
    assert code == 0
    assert "lock timeout" in capsys.readouterr().err


def test_health_log_and_sidecar(tmp_path):
    log = tmp_path / "source_health.jsonl"
    for i, resp in enumerate([{"content": [{"type": "text", "text": "ok"}]},
                              {"isError": True, "content": [{"type": "text", "text": "HTTP 429 Too Many Requests"}]},
                              {"content": []}]):
        rec = source_health.record({"tool_name": T + "edgar__get_company_facts", "tool_response": resp,
                                    "duration_ms": 10 + i}, log_path=log, clock=lambda: 1.0 + i)
        assert rec and "tool_response" not in rec
    assert source_health.record({"tool_name": "WebSearch", "tool_response": {}}, log_path=log) is None
    lines = [json.loads(l) for l in log.read_text().splitlines()]
    assert [l["outcome"] for l in lines] == ["ok", "error:429", "empty"]
    counts = json.loads((tmp_path / "source_health_counts.json").read_text())
    assert counts["edgar"]["total"] == 3 and counts["edgar"]["by_outcome"]["error:429"] == 1
    assert len(counts["edgar"]["window"]) == 3
    assert [r["outcome"] for r in source_health.tail(2, log)] == ["error:429", "empty"]


def test_health_never_raises_on_unwritable_path(capsys):
    rec = source_health.record({"tool_name": T + "fetch__fetch", "tool_response": {}},
                               log_path=Path("/proc/nope/x.jsonl"))
    assert rec is not None
    assert "not recorded" in capsys.readouterr().err
