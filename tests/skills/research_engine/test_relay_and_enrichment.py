"""The search_requests relay and the ENRICHMENT gate (MEM-0333; owner 2026-09-07).

The 2026-08-28 headless audit measured that the relay the docs described —
a lane emits `search_requests`, "the orchestrating session" runs them through
the real connectors, registers the evidence and re-invokes — had no
executable implementation. The owner's live runs then showed the shape that
produces: categories passing the floors gate on bare WebSearch, connector
usage "aspirational". These tests pin the mechanism that replaces the prose:
harvest → drain → reconcile → gate → heal → disclose, every step reading the
run tree and the workbook rather than a lane's report.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import pytest

from engine import brief, contract as C, ledger as L, pipeline as P, pipeline_stub as S, relay
from engine import preflight
from fixtures import bank_evidence, fire_volleys, new_run, preflight_doc

ROOT = Path(__file__).resolve().parents[3]
AGENT_RUN = ROOT / "plugins" / "dma-insights" / "scripts" / "agent_run.py"


def _agent_run():
    spec = importlib.util.spec_from_file_location("agent_run_for_relay_test", AGENT_RUN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _cat(wb):
    return sorted({brief.category_of(c) for c in wb.selected_subcaps()})[0]


def _flag(v) -> bool:
    return v if isinstance(v, bool) else str(v or "").strip().lower() in ("true", "1", "yes")


def _event(kind, **kw):
    return json.dumps({"type": kind, **kw})


def _result(text):
    return _event("result", result=text)


def _tool_use(name, inp):
    return _event("assistant", message={"content": [{"type": "tool_use", "name": name, "input": inp}]})


def _tool_result(text):
    return _event("user", message={"content": [{"type": "tool_result", "content": text}]})


def _transcript(logs: Path, lane: str, lines):
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"{lane}.jsonl").write_text("\n".join(lines) + "\n")


# ═══════════════════════════════════════════════════════════════════════════
# the measurement: which tool ran a category's searches
# ═══════════════════════════════════════════════════════════════════════════

def test_enrichment_status_counts_connector_searches_from_the_tool_column(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cells = wb.selected_subcaps()
    cat = _cat(wb)
    fire_volleys(wb, cells[0], n=2)                         # web_search only
    st = L.enrichment_status(run.open(), cat)
    assert st["searches"] == 6 and st["enrichment_searches"] == 0
    assert st["tools"] == ["web_search"] and st["enrichment_tools"] == []
    assert st["cells_with_enrichment"] == 0 and st["share"] == 0.0

    L.append_search(wb, subcap=cells[1], facet="works",
                    query='"Acme Credit Union" onboarding vendor', tool="exa", hits=3, kept=1)
    st = L.enrichment_status(run.open(), cat)
    assert st["enrichment_searches"] == 1 and st["enrichment_tools"] == ["exa"]
    assert st["cells_with_enrichment"] == 1 and 0 < st["share"] < 1


def test_enrichment_tools_is_every_search_tool_but_the_bare_web_pair():
    assert set(C.ENRICHMENT_TOOLS) == set(C.SEARCH_TOOLS) - {"web_search", "web_fetch"}
    assert {"exa", "tavily", "clay"} <= set(C.ENRICHMENT_TOOLS)


# ═══════════════════════════════════════════════════════════════════════════
# the third gate on a category, and what `blocking` means for it
# ═══════════════════════════════════════════════════════════════════════════

def test_last_gate_reports_whether_the_row_was_blocking(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    wb = run.open()
    cat = _cat(wb)
    L.append_gate(wb, gate="ENRICHMENT", scope=cat, verdict="FAIL",
                  detail="no enrichment connector was asked; heal=instruction", blocking=True)
    g = brief.last_gate(run.open(), "ENRICHMENT", cat)
    assert g["verdict"] == "FAIL" and g["is_blocking"] is True
    assert g["blocking"] == ["no enrichment connector was asked", "heal=instruction"]
    L.append_gate(wb, gate="ENRICHMENT", scope=cat, verdict="FAIL",
                  detail="DISCLOSED: no enrichment connector was asked", blocking=False)
    g = brief.last_gate(run.open(), "ENRICHMENT", cat)
    assert g["verdict"] == "FAIL" and g["is_blocking"] is False
    assert brief.last_gate(run.open(), "ENRICHMENT", "P9C9")["is_blocking"] is False


def test_a_blocking_enrichment_fail_reopens_a_floors_passed_category(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    wb = run.open()
    cat = _cat(wb)
    L.append_gate(wb, gate="FLOORS", scope=cat, verdict="PASS", detail="all terms met")
    L.append_gate(wb, gate="ENRICHMENT", scope=cat, verdict="FAIL",
                  detail="no enrichment connector was asked: 12 search(es) all through web_search",
                  blocking=True)
    need = brief.categories_needing_dispatch(run.open())
    assert cat in need["dispatch"] and cat not in need["passed"]
    assert any(r.startswith("enrichment: no enrichment connector") for r in need["reasons"][cat])
    assert brief.enrichment_failing_only(run.open(), need["dispatch"]) == [cat]


def test_a_disclosed_enrichment_fail_leaves_the_category_done(tmp_path):
    """The same FAIL, written non-blocking after the heal budget: still in the
    log, no longer a re-dispatch — the gap is stated, not worked forever."""
    run = new_run(tmp_path, n=4, prelim=False)
    wb = run.open()
    cat = _cat(wb)
    L.append_gate(wb, gate="FLOORS", scope=cat, verdict="PASS", detail="all terms met")
    L.append_gate(wb, gate="ENRICHMENT", scope=cat, verdict="FAIL",
                  detail="DISCLOSED (heal budget spent (1)): no enrichment connector was asked",
                  blocking=False)
    need = brief.categories_needing_dispatch(run.open())
    assert cat in need["passed"] and cat not in need["dispatch"]


def test_a_floors_fail_is_never_counted_as_enrichment_only(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    wb = run.open()
    cat = _cat(wb)
    L.append_gate(wb, gate="FLOORS", scope=cat, verdict="FAIL", detail="dq_gaps: 3")
    L.append_gate(wb, gate="ENRICHMENT", scope=cat, verdict="FAIL", detail="x", blocking=True)
    assert brief.enrichment_failing_only(run.open(), [cat]) == []


# ═══════════════════════════════════════════════════════════════════════════
# harvest: what a lane's output carries, in every shape lanes emit it
# ═══════════════════════════════════════════════════════════════════════════

REQ = {"query": '"Acme Credit Union" Alkami digital banking rollout', "facet": "works",
       "subcap": "P1C1.1.1", "tool": "mcp__Exa__web_search_exa",
       "falsifier": '"Acme Credit Union" Alkami delayed OR descoped',
       "proves": "a dated vendor rollout for the digital channel"}


def test_extract_reads_whole_json_fenced_json_and_the_key_in_prose():
    whole = json.dumps({"verdict": "ok", "search_requests": [REQ]})
    fenced = "Here is my report.\n```json\n" + whole + "\n```\nDone."
    prose = ('I could not run two searches. "search_requests": [' + json.dumps(REQ)
             + ', {"query": "Acme Credit Union core banking vendor 2025"}] — please relay.')
    for text in (whole, fenced, prose):
        rows = relay.extract_requests(text, category="P1C1")
        assert rows, text[:60]
        r = rows[0]
        assert r["query"] == REQ["query"] and r["facet"] == "works"
        assert r["subcap"] == "P1C1.1.1" and r["category"] == "P1C1"
        assert r["tool"] == "exa" and r["falsifier"] == REQ["falsifier"]
        assert r["id"].startswith("SR-") and len(r["id"]) == 13
    assert len(relay.extract_requests(prose, category="P1C1")) == 2


def test_extract_is_conservative_about_what_counts():
    assert relay.extract_requests("", category="P1C1") == []
    assert relay.extract_requests("no requests here", category="P1C1") == []
    # a bare list of strings is not identified as requests
    assert relay.extract_requests(json.dumps(["query one", "query two"])) == []
    # too short to be a query, or not a string
    rows = relay.extract_requests(json.dumps({"search_requests": ["ab", 7, None, {"q": "x"}]}))
    assert rows == []
    # an off-vocabulary facet is dropped, the request kept
    rows = relay.extract_requests(json.dumps({"search_requests": [
        {"query": "Acme Credit Union governance charter", "facet": "vibes"}]}))
    assert rows and rows[0]["facet"] is None


def test_the_same_request_in_two_casings_has_one_id():
    a = relay.extract_requests(json.dumps({"search_requests": [
        {"query": ' "Acme  Credit Union" Alkami ', "subcap": "P1C1.1.1"}]}))[0]
    b = relay.extract_requests(json.dumps({"search_requests": [
        {"query": '"acme credit union" alkami', "subcap": "P1C1.1.1"}]}))[0]
    assert a["id"] == b["id"]
    c = relay.extract_requests(json.dumps({"search_requests": [
        {"query": '"acme credit union" alkami', "subcap": "P1C1.1.2"}]}))[0]
    assert c["id"] != a["id"], "a different cell owes a different search"


def test_harvest_queues_each_request_once_and_reads_the_lane_transcript(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    logs = run.root / "agent_logs"
    _transcript(logs, "research-p1c1-producer", [
        _tool_use("WebSearch", {"query": "x"}),
        _result(json.dumps({"search_requests": [REQ]})),
    ])
    out = relay.harvest(run, ["P1C1"], logs_dir=logs, round_no=0)
    assert out["harvested"] == 1 and out["by_category"] == {"P1C1": 1}
    assert relay.queue_path(run).is_file()
    again = relay.harvest(run, ["P1C1"], logs_dir=logs, round_no=1)
    assert again["harvested"] == 0 and again["seen"] == 1, "a re-harvest queues nothing twice"
    st = relay.state(run)
    assert st["total"] == 1 and st["by_status"]["OPEN"] == 1
    rows = relay.open_requests(run, "P1C1")
    assert rows[0]["lane"] == "research-p1c1-producer" and rows[0]["round"] == 0


def test_harvest_without_categories_scans_every_research_lane(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    logs = run.root / "agent_logs"
    _transcript(logs, "research-p2c3-producer", [_result(json.dumps({"search_requests": [
        {"query": "Acme Credit Union chat servicing vendor", "subcap": "P2C3.1.1"}]}))])
    _transcript(logs, "scoring-p1-producer", [_result(json.dumps({"search_requests": [
        {"query": "this lane is not a research lane and is ignored"}]}))])
    out = relay.harvest(run, None, logs_dir=logs)
    assert out["harvested"] == 1 and out["by_category"] == {"P2C3": 1}


def test_a_torn_queue_line_is_skipped_not_fatal(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    logs = run.root / "agent_logs"
    _transcript(logs, "research-p1c1-producer", [_result(json.dumps({"search_requests": [REQ]}))])
    relay.harvest(run, ["P1C1"], logs_dir=logs)
    with relay.queue_path(run).open("a") as fh:
        fh.write('{"id": "SR-broken", "event": "open", "query": ')
    assert relay.state(run)["total"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# record and reconcile: the substrate closes a request, not the lane's word
# ═══════════════════════════════════════════════════════════════════════════

def _queued(tmp_path, req=REQ):
    run = new_run(tmp_path, n=4, prelim=False)
    logs = run.root / "agent_logs"
    _transcript(logs, "research-p1c1-producer", [_result(json.dumps({"search_requests": [req]}))])
    relay.harvest(run, ["P1C1"], logs_dir=logs)
    return run, relay.open_requests(run)[0]


def test_record_closes_a_request_and_refuses_a_blocked_with_no_reason(tmp_path):
    run, req = _queued(tmp_path)
    with pytest.raises(L.LedgerRefusal):
        relay.record(run, req["id"], "BLOCKED")
    with pytest.raises(L.LedgerRefusal):
        relay.record(run, "SR-0000000000", "SERVED")
    with pytest.raises(L.LedgerRefusal):
        relay.record(run, req["id"], "OPEN")
    relay.record(run, req["id"], "BLOCKED", note="mcp__Exa__web_search_exa was blocked. For security…",
                 actor="enrichment-web-specialist")
    row = relay.requests(run)[req["id"]]
    assert row["status"] == "BLOCKED" and "blocked" in row["note"]
    assert row["closed_by"] == "enrichment-web-specialist" and len(row["history"]) == 1
    assert relay.open_requests(run) == []


def test_reconcile_closes_from_a_matching_enrichment_search_and_nothing_else(tmp_path):
    run, req = _queued(tmp_path)
    wb = run.open()
    cell = req["subcap"]
    # the same query through bare web_search does NOT serve the request
    L.append_search(wb, subcap=cell, facet="works", query=req["query"], tool="web_search",
                    hits=4, kept=2)
    out = relay.reconcile(run, run.open())
    assert out["closed"] == {"SERVED": 0, "EMPTY": 0} and out["still_open"] == 1
    # through exa, with something kept → SERVED, noted with the row it came from
    L.append_search(wb, subcap=cell, facet="works", query=req["query"], tool="exa",
                    hits=4, kept=2)
    out = relay.reconcile(run, run.open())
    assert out["closed"]["SERVED"] == 1 and out["still_open"] == 0
    row = relay.requests(run)[req["id"]]
    assert row["status"] == "SERVED" and "Search_Log seq" in row["note"]


def test_reconcile_marks_a_connector_search_that_kept_nothing_as_empty(tmp_path):
    run, req = _queued(tmp_path)
    wb = run.open()
    L.append_search(wb, subcap=req["subcap"], facet="works", query=req["query"].upper(),
                    tool="tavily", hits=0, kept=0, outcome="no hits")
    out = relay.reconcile(run, run.open())
    assert out["closed"]["EMPTY"] == 1
    assert relay.requests(run)[req["id"]]["status"] == "EMPTY"


def test_reconcile_respects_the_cell_a_request_names(tmp_path):
    run, req = _queued(tmp_path)
    wb = run.open()
    other = [c for c in wb.selected_subcaps() if c != req["subcap"]][0]
    L.append_search(wb, subcap=other, facet="works", query=req["query"], tool="exa", hits=2, kept=1)
    assert relay.reconcile(run, run.open())["still_open"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# the drain brief: a lane that holds the connectors, told exactly what to do
# ═══════════════════════════════════════════════════════════════════════════

def test_drain_batch_writes_one_specialist_lane_per_category_with_a_label(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    logs = run.root / "agent_logs"
    _transcript(logs, "research-p1c1-producer", [_result(json.dumps({"search_requests": [REQ]}))])
    _transcript(logs, "research-p2c3-producer", [_result(json.dumps({"search_requests": [
        {"query": "Acme Credit Union chat servicing vendor", "subcap": "P2C3.1.1", "facet": "primary"}]}))])
    relay.harvest(run, None, logs_dir=logs)
    out = relay.drain_batch(run, run.open(), out_dir=tmp_path / "relay")
    assert out["lanes"] == 2 and out["requests"] == 2
    rows = json.loads(Path(out["batch"]).read_text())
    assert {r["agent"] for r in rows} == {relay.DRAIN_AGENT}
    assert sorted(r["label"] for r in rows) == [f"{relay.DRAIN_AGENT}@P1C1", f"{relay.DRAIN_AGENT}@P2C3"]
    text = Path(rows[0]["prompt_file"]).read_text()
    req = relay.open_requests(run, "P1C1")[0]
    assert req["id"] in text and req["query"] in text and req["falsifier"] in text
    for must in ("engine.cli search", "--tool exa", "engine.cli evidence", "engine.relay record",
                 "BLOCKED", "refusal text verbatim", f"--run {run.run_id} --root {run.root}"):
        assert must in text, must
    assert "WebSearch instead" in text, "the brief forbids the silent fallback"
    # restricted to one category when asked
    only = relay.drain_batch(run, run.open(), out_dir=tmp_path / "relay2", categories=["P2C3"])
    assert only["lanes"] == 1 and only["briefs"][0]["category"] == "P2C3"


def test_drain_batch_with_nothing_open_dispatches_nothing(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    out = relay.drain_batch(run, run.open(), out_dir=tmp_path / "relay")
    assert out == {"batch": None, "lanes": 0, "requests": 0, "briefs": []}
    assert not (tmp_path / "relay").exists()


def test_the_drain_agent_declares_the_connectors_it_is_briefed_to_use():
    m = relay.manifest_check(relay.DRAIN_AGENT)
    assert m["ok"], m
    names = " ".join(m["declares"])
    assert "mcp__Exa__web_search_exa" in names and "mcp__Tavily__tavily_search" in names


def test_batch_rows_carry_a_label_the_dispatcher_accepts(tmp_path):
    """The relay runs several lanes of ONE agent; agent_run must keep their
    transcripts apart, so its batch reader has to carry the label through."""
    m = _agent_run()
    batch = tmp_path / "batch.json"
    (tmp_path / "p.md").write_text("go")
    batch.write_text(json.dumps([
        {"agent": relay.DRAIN_AGENT, "prompt_file": str(tmp_path / "p.md"),
         "label": f"{relay.DRAIN_AGENT}@P1C1"},
        {"agent": relay.DRAIN_AGENT, "prompt_file": str(tmp_path / "p.md")}]))
    rows = m.read_batch(batch)
    assert rows[0]["label"] == f"{relay.DRAIN_AGENT}@P1C1"
    assert rows[1]["label"] == relay.DRAIN_AGENT, "the label defaults to the agent name"
    batch.write_text(json.dumps([{"agent": relay.DRAIN_AGENT, "prompt": "go", "label": "a/b"}]))
    with pytest.raises(SystemExit):
        m.read_batch(batch)


# ═══════════════════════════════════════════════════════════════════════════
# heal: which half is broken, measured — never inferred from empty rows alone
# ═══════════════════════════════════════════════════════════════════════════

def _web_only_category(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    wb = run.open()
    cat = _cat(wb)
    for c in wb.selected_subcaps()[:2]:
        bank_evidence(wb, c, n=2)                               # web_search volleys
    return run, cat


def test_heal_is_instruction_when_no_connector_was_ever_attempted(tmp_path):
    run, cat = _web_only_category(tmp_path)
    logs = run.root / "agent_logs"
    _transcript(logs, "research-p1c1-producer", [_tool_use("WebSearch", {"query": "x"})])
    plan = relay.heal_plan(run, run.open(), cat, logs_dir=logs)
    assert plan["heal"] == "instruction" and "no connector call" in plan["reason"]
    assert plan["manifest"]["ok"] and plan["grants"]["ok"] is True
    assert "mcp__Exa__web_search_exa" in plan["instruction"]


def test_heal_is_grants_when_the_transcript_shows_a_refusal(tmp_path):
    run, cat = _web_only_category(tmp_path)
    logs = run.root / "agent_logs"
    _transcript(logs, "research-p1c1-producer", [
        _tool_use("mcp__Exa__web_search_exa", {"query": "x"}),
        _tool_result("Tool mcp__Exa__web_search_exa was blocked. For security, this session "
                     "may only use approved tools."),
    ])
    plan = relay.heal_plan(run, run.open(), cat, logs_dir=logs)
    assert plan["heal"] == "grants" and "refused" in plan["reason"]
    assert plan["transcript"] == {**plan["transcript"], "attempted": 1, "refused": 1}
    assert "REFUSED" in plan["instruction"]


def test_heal_is_logging_when_a_connector_ran_but_was_logged_as_web_search(tmp_path):
    run, cat = _web_only_category(tmp_path)
    logs = run.root / "agent_logs"
    _transcript(logs, "research-p1c1-producer", [
        _tool_use("mcp__Tavily__tavily_search", {"query": "x"}),
        _tool_result("{\"results\": [{\"url\": \"https://acme.example\"}]}"),
    ])
    plan = relay.heal_plan(run, run.open(), cat, logs_dir=logs)
    assert plan["heal"] == "logging" and "mcp__Tavily" in plan["reason"]
    assert "--tool exa|tavily|clay|drive" in plan["instruction"]


def test_heal_is_none_when_a_connector_search_is_logged(tmp_path):
    run, cat = _web_only_category(tmp_path)
    wb = run.open()
    L.append_search(wb, subcap=wb.selected_subcaps()[0], facet="works",
                    query="Acme Credit Union vendor", tool="exa", hits=1, kept=1)
    plan = relay.heal_plan(run, run.open(), cat, logs_dir=run.root / "agent_logs")
    assert plan["heal"] is None and plan["instruction"] is None
    assert "1 of" in plan["reason"] and "exa" in plan["reason"]


def test_heal_is_manifest_for_a_lane_that_declares_no_connector(tmp_path, monkeypatch):
    run, cat = _web_only_category(tmp_path)
    monkeypatch.setattr(relay, "manifest_check",
                        lambda lane: {"path": None, "declares": [], "ok": False,
                                      "note": f"no manifest named {lane}.md"})
    plan = relay.heal_plan(run, run.open(), cat, logs_dir=run.root / "agent_logs")
    assert plan["heal"] == "manifest" and "rectifier" in plan["instruction"]


def test_grants_check_measures_agent_run_allowed():
    g = relay.grants_check()
    assert g["measured"] and g["ok"] is True and g["missing"] == []


def test_the_relay_and_agent_run_agree_on_what_a_refusal_reads_as():
    """Two carriers of one list. If agent_run learns a new refusal string and
    the relay does not, a lane refused in that way heals as `instruction`
    rather than `grants` — the wrong repair, confidently."""
    m = _agent_run()
    assert tuple(relay.BLOCKED_MARKERS) == tuple(m._BLOCKED_MARKERS)
    assert tuple(relay.CONNECTOR_NAMESPACES) == tuple(m.CONNECTOR_NAMESPACES)


# ═══════════════════════════════════════════════════════════════════════════
# the driver: harvest → drain → reconcile → gate → heal → disclose, per round
# ═══════════════════════════════════════════════════════════════════════════

def _fresh(tmp_path, n=4):
    run = new_run(tmp_path, n=n)
    preflight.record(run, preflight_doc())
    return run


def _opts(tmp_path, dispatcher, **over):
    kw = dict(dispatcher=dispatcher, reads=S.StubReads(), shipper=S.StubShipper(), push=False,
              folder_root=tmp_path / "client_out", ingest_poll_s=0, sleep=lambda s: None,
              log=lambda s: None, until="RESEARCH")
    kw.update(over)
    return P.Options(**kw)


def _lane_web_only(with_exa: bool = False, emit_requests: bool = False):
    """A research lane that does the whole category on bare web_search — the
    2026-09-07 shape — optionally logging one exa search, optionally emitting
    a search_requests array in a transcript the harvester will read."""
    def lane(agent, prompt_file, ctx):
        F = S.fixtures()
        cat = agent.split("-")[1].upper()
        wb = ctx.run.open()
        cells = [c for c in wb.selected_subcaps() if c.startswith(cat)]
        ev = {}
        for c in cells:
            row = wb.scoring_row(c) or {}
            if str(row.get("Dominant_Claim") or "").strip():
                continue
            ev[c] = F.bank_evidence(wb, c, n=5)
            F.synthesise(wb, c, F.good_synthesis(c, ev[c]), author=agent)
        if with_exa and not L.enrichment_status(wb, cat)["enrichment_searches"]:
            L.append_search(wb, subcap=cells[0], facet="works",
                            query='"Acme Credit Union" digital banking vendor', tool="exa",
                            hits=3, kept=1)
        F.client_facts(wb, wb.selected_subcaps(), S._evidence_by_cell(wb))
        if emit_requests:
            _transcript(ctx.run.root / "agent_logs", agent,
                        [_result(json.dumps({"search_requests": [REQ]}))])
    return lane


def test_a_category_on_bare_web_search_is_healed_once_then_disclosed(tmp_path):
    run = _fresh(tmp_path)
    disp = S.StubDispatcher({"research-p": _lane_web_only(), "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp, enrichment_heals=1)).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    research = [c for c in disp.calls if c["stage"] == "RESEARCH"]
    assert len(research) == 2, "one heal: a fresh lane instance, then disclosure"
    wb = run.open()
    rows = [g for g in wb.rows("Gate_Log") if g.get("Gate") == "ENRICHMENT"]
    verdicts = [(g["Verdict"], _flag(g["Blocking"])) for g in rows]
    assert verdicts == [("FAIL", True), ("FAIL", False)], verdicts
    assert "heal=instruction" in rows[0]["Detail"] and "fresh lane instance 1 of 1" in rows[0]["Detail"]
    assert rows[1]["Detail"].startswith("DISCLOSED")
    # the second brief carried the gate, the heal and the instruction
    second = Path(research[1]["prompt_file"])
    text = second.read_text()
    assert "ENRICHMENT gate refused" in text and "instruction" in text
    packet = json.loads(second.with_suffix(".json").read_text())
    assert packet["enrichment"]["heal"] == "instruction"
    assert packet["enrichment"]["last_gate"]["is_blocking"] is True
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())
    assert st["stages"]["RESEARCH"]["verdict"] == "PASS"
    assert "ENRICHMENT disclosed" in st["stages"]["RESEARCH"]["detail"]
    assert set(st["enrichment_disclosed"]) == {"P1C1"}
    assert st["enrichment_disclosed"]["P1C1"]["heal"] == "instruction"
    assert st["stages"]["RESEARCH"]["rounds"] == 2


def test_a_category_that_asked_a_connector_passes_the_gate_first_time(tmp_path):
    run = _fresh(tmp_path)
    disp = S.StubDispatcher({"research-p": _lane_web_only(with_exa=True),
                             "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp)).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    assert len([c for c in disp.calls if c["stage"] == "RESEARCH"]) == 1
    rows = [g for g in run.open().rows("Gate_Log") if g.get("Gate") == "ENRICHMENT"]
    assert [g["Verdict"] for g in rows] == ["PASS"] and "exa" in rows[0]["Detail"]
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())
    assert not st.get("enrichment_disclosed")


def test_zero_heals_discloses_immediately_and_still_records_the_gap(tmp_path):
    run = _fresh(tmp_path)
    disp = S.StubDispatcher({"research-p": _lane_web_only(), "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp, enrichment_heals=0)).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    assert len([c for c in disp.calls if c["stage"] == "RESEARCH"]) == 1
    rows = [g for g in run.open().rows("Gate_Log") if g.get("Gate") == "ENRICHMENT"]
    assert len(rows) == 1 and rows[0]["Verdict"] == "FAIL" and rows[0]["Detail"].startswith("DISCLOSED")


def test_harvested_requests_are_drained_by_a_specialist_lane_and_reconciled(tmp_path):
    """The relay end to end inside one research round: the lane emits a
    request it could not run, the driver dispatches the specialist over it,
    the specialist logs the connector search, the Search_Log closes the
    request, and the ENRICHMENT gate passes on the row the specialist wrote."""
    run = _fresh(tmp_path)
    drained = []

    def specialist(agent, prompt_file, ctx):
        text = Path(prompt_file).read_text()
        drained.append(text)
        wb = ctx.run.open()
        req = relay.open_requests(ctx.run)[0]
        L.append_search(wb, subcap=req["subcap"], facet=req["facet"], query=req["query"],
                        tool="exa", hits=3, kept=2, outcome="kept 2")
    disp = S.StubDispatcher({"research-p": _lane_web_only(emit_requests=True),
                             "finding-challenger": S.lane_noop,
                             relay.DRAIN_AGENT: specialist})
    out = P.Pipeline(run, _opts(tmp_path, disp)).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    stages = [(c["stage"], c["agent"]) for c in disp.calls]
    assert ("RELAY", relay.DRAIN_AGENT) in stages
    assert len([s for s in stages if s[0] == "RESEARCH"]) == 1, "the specialist's row satisfied the gate"
    assert drained and REQ["query"] in drained[0] and "engine.relay record" in drained[0]
    st = relay.state(run)
    assert st["by_status"]["SERVED"] == 1 and st["by_status"]["OPEN"] == 0
    rows = [g for g in run.open().rows("Gate_Log") if g.get("Gate") == "ENRICHMENT"]
    assert [g["Verdict"] for g in rows] == ["PASS"]


def test_no_relay_harvests_and_discloses_but_dispatches_no_specialist(tmp_path):
    run = _fresh(tmp_path)
    disp = S.StubDispatcher({"research-p": _lane_web_only(emit_requests=True),
                             "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp, relay=False, enrichment_heals=0)).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    assert not [c for c in disp.calls if c["stage"] == "RELAY"]
    st = relay.state(run)
    assert st["by_status"]["OPEN"] == 1, "harvested, held, stated"
    disclosed = json.loads((run.qa_dir / P.STATE_NAME).read_text())["enrichment_disclosed"]
    assert disclosed["P1C1"]["open_requests"] == 1


def test_a_relay_failure_leaves_the_category_as_the_floors_gate_found_it(tmp_path, monkeypatch):
    """Fail-safe by construction, like the verifier: a relay that raises must
    never block a run on a guess."""
    run = _fresh(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("relay exploded")
    monkeypatch.setattr(relay, "harvest", boom)
    monkeypatch.setattr(relay, "heal_plan", boom)
    disp = S.StubDispatcher({"research-p": _lane_web_only(), "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp)).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    assert not [g for g in run.open().rows("Gate_Log") if g.get("Gate") == "ENRICHMENT"]


def test_the_research_stage_runs_the_enrichment_step_after_the_verifier():
    src = inspect.getsource(P.Pipeline._stage_research)
    assert src.index("_verify_research") < src.index("_enrich_research")
    esrc = inspect.getsource(P.Pipeline._enrich_research)
    for must in ("relay.harvest", "relay.drain_batch", "relay.reconcile", "relay.heal_plan",
                 'gate="ENRICHMENT"', "enrichment_heals", "_disclose_enrichment"):
        assert must in esrc, must


def test_the_relay_cli_is_a_registered_engine_family():
    from engine import cli
    assert "relay" in cli._FAMILIES
    assert cli._family_main("relay") is relay.main
