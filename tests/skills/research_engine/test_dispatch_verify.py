"""The dispatch verifier — a lane's logged searches must be witnessed by its
own transcript.

The floors gate decides a cell's volleys from the Search_Log the lane itself
wrote, and trusts it. A lane that shells `engine.cli search …` without ever
calling a retrieval tool satisfies the evidence floor with rows nobody ran, and
no substrate gate can see it — the coordination gap the owner named. This gate
reads the lane's CLI transcript (`agent_logs/<lane>.jsonl`, overwritten per
dispatch, so exactly this round's work) and refuses a category whose logged
searches no retrieval in the transcript could have produced.

Conservative and fail-safe by construction: it accuses only when the lane
demonstrably ran, logged at least two searches, and made ZERO retrieval-shaped
calls of any kind; anything it cannot read it treats as witnessed.
"""
import inspect
import json

from engine import brief, pipeline, verify
from engine import ledger as L

from fixtures import new_run


def _event(name, inp):
    return json.dumps({"type": "assistant",
                       "message": {"content": [{"type": "tool_use",
                                                "name": name, "input": inp}]}})


def _bash(cmd):
    return _event("Bash", {"command": cmd})


def _log_search(cell, facet, query):
    return _bash(f"python3 -m engine.cli search --run R --subcap {cell} "
                 f"--facet {facet} --query {query!r}")


def _write(logs, cat, lines):
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"research-{cat.lower()}-producer.jsonl").write_text("\n".join(lines))


# ── the fabrication the substrate cannot see ──────────────────────────

def test_logged_searches_with_no_retrieval_are_refused(tmp_path):
    logs = tmp_path / "agent_logs"
    _write(logs, "P1C1", [
        _log_search("P1C1.1.1", "primary", "digital strategy"),
        _log_search("P1C1.1.1", "works", "cloud migration"),
        _log_search("P1C1.1.2", "fails", "legacy core"),
    ])
    out = verify.research_lane_fabrication("P1C1", logs)
    assert out and "fabricated_search" in out[0]
    assert "3 search(es)" in out[0]


def test_a_lane_that_actually_retrieved_passes(tmp_path):
    logs = tmp_path / "agent_logs"
    _write(logs, "P1C2", [
        _event("WebSearch", {"query": "governance risk appetite"}),
        _log_search("P1C2.1.1", "primary", "governance"),
        _event("mcp__Exa__web_search_exa", {"query": "risk framework"}),
        _log_search("P1C2.1.1", "works", "risk framework"),
    ])
    assert verify.research_lane_fabrication("P1C2", logs) == []


def test_a_connector_fetch_counts_as_retrieval(tmp_path):
    logs = tmp_path / "agent_logs"
    _write(logs, "P4C1", [
        _event("mcp__Tavily__tavily_search", {"query": "data governance"}),
        _log_search("P4C1.1.1", "primary", "data governance"),
        _log_search("P4C1.1.2", "works", "lineage"),
    ])
    assert verify.research_lane_fabrication("P4C1", logs) == []


def test_a_shell_fetch_counts_as_retrieval(tmp_path):
    logs = tmp_path / "agent_logs"
    _write(logs, "P3C1", [
        _bash("curl -s https://acme.example/about | head"),
        _log_search("P3C1.1.1", "primary", "automation"),
        _log_search("P3C1.1.2", "works", "straight through"),
    ])
    assert verify.research_lane_fabrication("P3C1", logs) == []


def test_a_url_inside_an_engine_call_is_not_a_retrieval(tmp_path):
    """The exclusion that keeps the gate honest: `engine.cli search --query`
    can carry a URL, and that is the engine talking to itself, not a fetch. A
    lane whose only network-shaped strings are inside engine calls retrieved
    nothing."""
    logs = tmp_path / "agent_logs"
    _write(logs, "P2C1", [
        _bash("python3 -m engine.cli search --run R --subcap P2C1.1.1 "
              "--facet primary --query 'see https://acme.example/x'"),
        _bash("python3 -m engine.cli search --run R --subcap P2C1.1.1 "
              "--facet works --query 'https://acme.example/y'"),
    ])
    out = verify.research_lane_fabrication("P2C1", logs)
    assert out and "fabricated_search" in out[0]


# ── conservative and fail-safe ────────────────────────────────────────

def test_one_logged_search_is_below_the_floor(tmp_path):
    """A single row is left to the transcript's own noise; the gate wants the
    pattern, not one line that a truncated stream could explain."""
    logs = tmp_path / "agent_logs"
    _write(logs, "P1C3", [_log_search("P1C3.1.1", "primary", "innovation")])
    assert verify.research_lane_fabrication("P1C3", logs) == []


def test_a_missing_transcript_never_accuses(tmp_path):
    logs = tmp_path / "agent_logs"
    logs.mkdir()
    assert verify.research_lane_fabrication("P4C4", logs) == []


def test_a_blank_transcript_proves_nothing(tmp_path):
    logs = tmp_path / "agent_logs"
    _write(logs, "P2C2", ["", "   "])
    assert verify.research_lane_fabrication("P2C2", logs) == []


def test_garbage_lines_do_not_crash_the_verifier(tmp_path):
    logs = tmp_path / "agent_logs"
    _write(logs, "P3C3", [
        "{not json at all",
        json.dumps({"type": "result", "total_cost_usd": 1.2}),
        _log_search("P3C3.1.1", "primary", "compliance"),
        _log_search("P3C3.1.2", "works", "surveillance"),
    ])
    out = verify.research_lane_fabrication("P3C3", logs)
    assert out and "fabricated_search" in out[0]


def test_witness_counts_each_kind(tmp_path):
    logs = tmp_path / "agent_logs"
    _write(logs, "P1C4", [
        _event("WebSearch", {"query": "culture"}),
        _log_search("P1C4.1.1", "primary", "culture"),
        _log_search("P1C4.1.2", "works", "change"),
    ])
    w = verify.witness(logs / "research-p1c4-producer.jsonl")
    assert w == {"ran": 3, "logged_searches": 2, "retrievals": 1}


# ── the REVISE flows back through the round loop ──────────────────────

def _category(wb):
    from engine.brief import category_of
    return sorted({category_of(c) for c in wb.selected_subcaps()})[0]


def test_a_verify_fail_reopens_a_floors_passed_category(tmp_path):
    """The load-bearing integration: a category the floors gate PASSED but the
    verifier FAILED is put back into dispatch, with the verifier's reason."""
    run = new_run(tmp_path, n=8, prelim=False)
    wb = run.open()
    cat = _category(wb)
    L.append_gate(wb, gate="FLOORS", scope=cat, verdict="PASS",
                  detail="all terms met")
    need = brief.categories_needing_dispatch(wb)
    assert cat in need["passed"] and cat not in need["dispatch"]

    L.append_gate(wb, gate="DISPATCH_VERIFY", scope=cat, verdict="FAIL",
                  detail="fabricated_search: 3 logged, 0 retrieved")
    wb2 = run.open()
    need = brief.categories_needing_dispatch(wb2)
    assert cat in need["dispatch"] and cat not in need["passed"]
    assert any("dispatch verifier" in r for r in need["reasons"][cat])


def test_a_verify_pass_leaves_a_floors_passed_category_done(tmp_path):
    run = new_run(tmp_path, n=8, prelim=False)
    wb = run.open()
    cat = _category(wb)
    L.append_gate(wb, gate="FLOORS", scope=cat, verdict="PASS",
                  detail="all terms met")
    L.append_gate(wb, gate="DISPATCH_VERIFY", scope=cat, verdict="PASS",
                  detail="logged searches witnessed")
    need = brief.categories_needing_dispatch(run.open())
    assert cat in need["passed"] and cat not in need["dispatch"]


def test_the_research_stage_calls_the_verifier():
    src = inspect.getsource(pipeline.Pipeline._stage_research)
    assert "_verify_research" in src, \
        "the verifier is defined but never called by the research stage"
    vsrc = inspect.getsource(pipeline.Pipeline._verify_research)
    assert "DISPATCH_VERIFY" in vsrc and "research_lane_fabrication" in vsrc
