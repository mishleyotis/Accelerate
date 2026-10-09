"""RESEARCH as lean headless tiers (owner, 2026-10-09: "fix the context floor
too, run collectors headless").

Measured first-turn context of one haiku child on R-IMA-20261009:
in-session workflow subagent 73,778 tokens; `claude -p --agent` from the repo
root 31,189; from the run directory 18,344; run directory with no MCP server,
no settings source and four tools 6,537. A LEAN lane holds only what its job
needs — Bash/Read/WebSearch/WebFetch for a collector, Bash/Read for the
orchestrator and the challenger — and the driver reads its exact cost.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

from engine import cost, pipeline as P, pipeline_stub as S, preflight, verify
from fixtures import new_run, preflight_doc, two_category_selection

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"


def _agent_run():
    spec = importlib.util.spec_from_file_location("agent_run", PLUGIN / "scripts" / "agent_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── the lane runner ────────────────────────────────────────────────────────

def test_a_lean_lane_holds_only_what_the_row_names(tmp_path):
    ar = _agent_run()
    cmd, cwd = ar.lean_command(
        "research-evidence-collector",
        {"model": "haiku", "tools": ["Bash", "Read", "WebSearch", "WebFetch"],
         "cwd": str(tmp_path)}, "PROMPT", stream=True, scratch=tmp_path / ".lean")
    assert cmd[cmd.index("--model") + 1] == "haiku"
    assert "--strict-mcp-config" in cmd, "no MCP server: no connector schema in context"
    assert cmd[cmd.index("--setting-sources") + 1] == "", "no settings, so no plugin hooks or skills"
    assert cmd[cmd.index("--tools") + 1] == "Bash,Read,WebSearch,WebFetch"
    assert "--allowedTools=Bash,Read,WebSearch,WebFetch" in cmd
    assert "--agent" not in cmd, "the plugin-bound --agent path loads the 31K floor"
    sp = Path(cmd[cmd.index("--append-system-prompt-file") + 1])
    body = sp.read_text()
    assert "You collect evidence for ONE batch" in body and "model: haiku" not in body, \
        "the manifest BODY is the system prompt; its frontmatter is not"
    assert cmd[-1] == "PROMPT" and cwd == tmp_path


def test_a_lean_lane_must_name_its_tools(tmp_path):
    ar = _agent_run()
    with pytest.raises(ValueError, match="name its tools"):
        ar.lean_command("research-evidence-collector", {"cwd": str(tmp_path)}, "P",
                        stream=False, scratch=tmp_path)
    bad = tmp_path / "batch.json"
    bad.write_text(json.dumps([{"agent": "research-evidence-collector", "prompt": "x",
                                "lean": {"model": "haiku"}}]))
    with pytest.raises(SystemExit, match="must name its"):
        ar.read_batch(bad)


def test_a_lean_lane_carries_its_category_identity(tmp_path):
    ar = _agent_run()
    env = ar._child_env("research-evidence-collector", "research-p2c2-collector")
    assert env["DMA_ACTOR"] == "research-p2c2-collector" and env["DMA_IN_LANE"] == "1"
    assert ar._child_env("finding-challenger")["DMA_ACTOR"] == "finding-challenger"


def test_a_lean_batch_runs_the_lean_command_from_the_run_directory(tmp_path, monkeypatch):
    """Through run_batch, with a stand-in CLI that records its argv and cwd."""
    ar = _agent_run()
    rec = tmp_path / "argv.json"
    fake = tmp_path / "fake_claude"
    fake.write_text("#!/usr/bin/env python3\nimport json,os,sys\n"
                    f"json.dump({{'argv': sys.argv[1:], 'cwd': os.getcwd(), 'actor': os.environ.get('DMA_ACTOR')}}, open({str(rec)!r},'w'))\n"
                    "print(json.dumps({'type':'result','subtype':'success','result':'" + "x" * 300 + "',"
                    "'num_turns':3,'total_cost_usd':0.012,'usage':{'input_tokens':1,'output_tokens':9}}))\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(ar, "CLAUDE_BIN", str(fake))
    rundir = tmp_path / "run"; rundir.mkdir()
    rows = [{"agent": "research-evidence-collector", "prompt": "collect P2C2", "label": "c1",
             "lean": {"model": "haiku", "tools": ["Bash", "Read", "WebSearch", "WebFetch"],
                      "cwd": str(rundir), "actor": "research-p2c2-collector"}}]
    rc = ar.run_batch(rows, 1, 60, tmp_path, ar.ALLOWED, None, logs=tmp_path / "logs",
                      timing_out=tmp_path / "t.json")
    got = json.loads(rec.read_text())
    assert got["cwd"] == str(rundir) and got["actor"] == "research-p2c2-collector"
    assert "--strict-mcp-config" in got["argv"] and "--agent" not in got["argv"]
    t = json.loads((tmp_path / "t.json").read_text())
    assert t["usd"] == pytest.approx(0.012), "the lane's exact dollars reach the ledger row"
    assert rc == 0


# ── the driver ─────────────────────────────────────────────────────────────

def _tiers(tmp_path, **kw):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    disp = S.StubDispatcher(S.default_handlers())
    opts = dict(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(), push=False,
                folder_root=tmp_path / "out", ingest_poll_s=0, sleep=lambda s: None,
                log=lambda s: None, until="RESEARCH", research_mode="tiers",
                stage_budget={"RESEARCH": 100})
    opts.update(kw)
    p = P.Pipeline(run, P.Options(**opts))
    return p, disp, p.run_all()


def test_the_tiers_run_collect_orchestrate_challenge_and_pass_the_gate(tmp_path):
    p, disp, out = _tiers(tmp_path)
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    seq = [(c["stage"], c["agent"]) for c in disp.calls]
    assert ("RESEARCH", "research-evidence-collector") in seq
    assert ("RESEARCH", "research-category-orchestrator") in seq
    assert ("CHALLENGE", "research-challenger") in seq
    first = {a: i for i, (_s, a) in reversed(list(enumerate(seq)))}
    assert first["research-evidence-collector"] < first["research-category-orchestrator"] \
        < first["research-challenger"]
    batches = sorted((p.run.root / "briefs").glob("tiers_*_r*/batch.json"))
    rows = [r for b in batches for r in json.loads(b.read_text())]
    tools = {r["agent"]: r["lean"]["tools"] for r in rows}
    assert tools["research-evidence-collector"] == ["Bash", "Read", "WebSearch", "WebFetch"]
    assert tools["research-category-orchestrator"] == ["Bash", "Read"]
    assert tools["research-challenger"] == ["Bash", "Read"]
    actors = {r["lean"]["actor"] for r in rows}
    assert {"research-p1c1-collector", "research-p1c1-producer", "research-challenger"} <= actors


def test_only_categories_narrows_the_stage_and_says_the_rest_is_open(tmp_path):
    p, disp, out = _tiers(tmp_path, only_categories=["P1C1"])
    prompts = " ".join(Path(c["prompt_file"]).read_text() for c in disp.calls if c.get("prompt_file"))
    assert "category P1C2" not in prompts and "category P1C1" in prompts
    assert out["outcome"] == "SCOPE_COMPLETE" and "P1C1" in out["reason"], out


def test_auto_picks_tiers_on_a_degraded_run_and_the_workflow_otherwise(tmp_path):
    p, disp, out = _tiers(tmp_path, research_mode="auto")
    # the fixture's baseline is complete: connector-backed, so the workflow
    assert p.opts.research_mode == "workflow" and out["outcome"] == "AWAITING_WORKFLOW"
    run2 = new_run(tmp_path / "b", selected=two_category_selection(3))
    preflight.record(run2, preflight_doc())
    q = P.Pipeline(run2, P.Options(dispatcher=S.StubDispatcher(S.default_handlers()),
                                   reads=S.StubReads(), shipper=S.StubShipper(), push=False,
                                   folder_root=tmp_path / "o2", ingest_poll_s=0,
                                   sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                   research_mode="auto", stage_budget={"RESEARCH": 100}))
    q.state["enrichment_degraded"] = {"missing": ["exa", "tavily"]}
    q._save_state()
    q.run_all()
    assert q.opts.research_mode == "tiers"


def test_a_spent_envelope_stops_the_tiers_before_any_lane(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    cost.record(run, stage="RESEARCH", elapsed_s=1, usd=9.99)
    disp = S.StubDispatcher(S.default_handlers())
    p = P.Pipeline(run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                  push=False, folder_root=tmp_path / "o", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="tiers"))
    out = p.run_all()
    assert out["outcome"] == "STOPPED_STAGE_BUDGET", out
    assert not [c for c in disp.calls if c["stage"] in ("RESEARCH", "CHALLENGE")]


def test_lean_lanes_price_below_the_in_session_floor():
    a = cost.research_price(57, categories=1, capabilities=9)
    b = cost.research_price(57, categories=1, capabilities=9, lean=True)
    assert b["usd"] < a["usd"] * 0.75 and b["lean"] is True and "lean headless" in b["basis"]


# ── the verifier reads the collectors ──────────────────────────────────────

def _tx(path, tools):
    lines = []
    for name, inp in tools:
        lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": name, "input": inp}]}}))
    path.write_text("\n".join(lines) + "\n")


def test_collectors_that_logged_searches_nobody_ran_are_a_fabrication(tmp_path):
    log = {"command": "python3 -m engine.cli search --run R --subcap P2C2.1.1 --facet works "
                      "--tool web_search --query q --hits 3 --kept 1"}
    _tx(tmp_path / "research-p2c2-collect-p2c2_collect1-r0.jsonl", [("Bash", log)] * 4)
    _tx(tmp_path / "research-p2c2-collect-p2c2_collect2-r0.jsonl", [("Bash", log)] * 3)
    assert verify.research_lane_fabrication("P2C2", tmp_path)
    _tx(tmp_path / "research-p2c2-collect-p2c2_collect3-r0.jsonl", [("WebSearch", {"query": "q"})])
    assert verify.research_lane_fabrication("P2C2", tmp_path) == [], \
        "a sibling's retrieval witnesses the category's logged searches"


# ── depth: the cell's own question (P2C2 live, 2026-10-09) ─────────────────

def _empty_cells_of_one_capability(wb):
    from collections import defaultdict
    by = defaultdict(list)
    for c in wb.selected_subcaps():
        by[".".join(c.split(".")[:2])].append(c)
    cap, cells = next((k, v) for k, v in by.items() if len(v) >= 2)
    return cells[:2]


def test_an_absence_whose_primary_is_shared_with_a_sibling_is_refused(tmp_path):
    from engine import ledger as L
    from fixtures import fire_volleys
    run = new_run(tmp_path, n=8)
    wb = run.open()
    a, b = _empty_cells_of_one_capability(wb)
    for cell in (a, b):
        fire_volleys(wb, cell, n=0)
    # replace a's primary with the SAME capability-wide query b logged
    shared = '"Acme Credit Union" capability-wide primary'
    for cell in (a, b):
        L.append_search(wb, subcap=cell, facet="primary", query=shared, tool="web_search",
                        hits=0, kept=0, outcome="no hits")
    rows = wb.rows("Search_Log")
    # a cell whose ONLY primary is shared: drop a's own fixture primary from view
    own = [r for r in rows if r.get("SubCap_ID") == a and r.get("Facet") == "primary"
           and r.get("Query") != shared]
    probs = L._cell_own_hunt_problems(wb, a, "hunted text long enough to pass the floor, naming queries")
    if own:
        assert not any(p.startswith("primary_shared") for p in probs), "its own primary was asked"
    wb2 = run.open()
    # a cell that ONLY carries the shared primary is refused
    c = [x for x in wb2.selected_subcaps() if ".".join(x.split(".")[:2]) == ".".join(a.split(".")[:2])
         and x not in (a, b)]
    if c:
        L.append_search(wb2, subcap=c[0], facet="primary", query=shared, tool="web_search",
                        hits=0, kept=0, outcome="no hits")
        probs = L._cell_own_hunt_problems(wb2, c[0], "x" * 60)
        assert any(p.startswith("primary_shared") for p in probs), probs


def test_an_absence_repeating_a_siblings_hunt_is_refused(tmp_path):
    from engine import ledger as L
    from fixtures import declare_absent
    run = new_run(tmp_path, n=8)
    wb = run.open()
    a, b = _empty_cells_of_one_capability(wb)
    declare_absent(wb, a)
    hunted = str(next(r for r in wb.scoring_rows() if r["SubCap_ID"] == a).get("What_We_Found"))
    text = hunted.split("Searched and not found: ", 1)[-1].split(". Volleys fired", 1)[0]
    probs = L._cell_own_hunt_problems(run.open(), b, text)
    assert any(p.startswith("hunted_shared") for p in probs), probs
    assert not any(p.startswith("hunted_shared")
                   for p in L._cell_own_hunt_problems(run.open(), b, text + " and this cell's own query"))


def test_the_shared_card_carries_the_entity_s_vocabulary(tmp_path):
    p, disp, out = _tiers(tmp_path)
    cards = sorted((p.run.root / "briefs" / "research_cards").glob("*/_shared.json"))
    assert cards
    shared = json.loads(cards[0].read_text())
    lex = shared.get("search_lexicon")
    sv = str(p.wb.metadata().get("sub_vertical") or "").upper()
    if sv:
        assert lex and lex["sub_vertical"] == sv and lex["customer"] and lex["artefacts"]
    lexicon = json.loads((PLUGIN / "skills" / "dma-research" / "engine" / "data" /
                          "subvertical_lexicon.json").read_text())
    from engine import contract as C
    assert set(C.PILLAR_WEIGHTS) <= set(lexicon), "every sub-vertical has its vocabulary"
    assert "thin-file" in lexicon["IB"]["not_applicable"]


def test_the_collector_prompt_asks_each_cells_own_question_and_reads_pages_raw():
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "PRIMARY, ONE PER OPEN CELL" in js and "search_lexicon" in js
    assert "Never paste a card question into a search box" in js
    assert "python3 -m engine.cli fetch ${R} --url <U>" in js and "WebFetch only when fetch reports an error" in js
    assert "hunted_shared" in js and "primary_shared" in js


# ── the visible face, the job, the pool ────────────────────────────────────

def test_a_named_scope_that_passes_is_scope_complete_not_failed(tmp_path):
    p, disp, out = _tiers(tmp_path, only_categories=["P1C1"])
    assert out["outcome"] == "SCOPE_COMPLETE" and "P1C1" in out["reason"], out
    assert "SCOPE_COMPLETE" in P.EXIT_ZERO_OUTCOMES
    assert "--only-categories P1C1" in p.plan()["command"]


def test_tiers_with_a_session_hand_the_visible_workflow(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    disp = S.StubDispatcher(S.default_handlers())
    p = P.Pipeline(run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                  push=False, folder_root=tmp_path / "o", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="tiers", tiers_direct=False,
                                  stage_budget={"RESEARCH": 100}))
    out = p.run_all()
    assert out["outcome"] == "AWAITING_WORKFLOW", out
    doc = json.loads(Path(out["handoff"]).read_text())
    assert doc["workflow"].endswith("dma-research-tiers.js")
    assert all(i["tiers"] and i["round"] == 0 for i in doc["invocations"])
    # ONE runner for the round: a runner sits at the session's floor
    assert len(doc["invocations"]) == 1, "one face per round, not one per category"
    inv = doc["invocations"][0]
    assert len(inv["cats"]) == 2 and set(inv["batches"]) == set(inv["cats"])
    assert set(inv.get("budgets") or {}) == set(inv["cats"])
    assert not [c for c in disp.calls if c["stage"] in ("RESEARCH", "CHALLENGE")], \
        "the session's workflow runs the lanes, not the driver"
    js = (PLUGIN / "workflows" / "dma-research-tiers.js").read_text()
    assert "model: 'haiku', effort: 'low'" in js
    assert "engine.tiers start" in js and "engine.tiers wait" in js


def test_the_job_wait_reports_done_failed_and_a_vanished_process(tmp_path):
    from engine import tiers as T
    run = new_run(tmp_path, n=3)
    path = T._status_path(run, "P1C1")
    T._write(path, {"category": "P1C1", "state": "done", "gate": "PASS"})
    assert T.wait(run, "P1C1", 1)["state"] == "done"
    T._write(path, {"category": "P1C1", "state": "running", "pid": 999999})
    got = T.wait(run, "P1C1", 1)
    assert got["state"] == "failed" and "process is gone" in got["error"]
    assert T.wait(run, "P9C9", 1)["state"] == "not_started"
    T._write(path, {"category": "P1C1", "state": "running", "pid": os.getpid()})
    assert T.wait(run, "P1C1", 0.2)["note"].startswith("still running")
    again = T.start(run, "P1C1", 0)
    assert again["pid"] == os.getpid() and "already running" in again["note"], \
        "a running job is never started twice"


def test_the_lane_pool_holds_the_host_to_its_slots(tmp_path, monkeypatch):
    import threading
    import time as _t
    ar = _agent_run()
    monkeypatch.setenv("DMA_LANE_POOL", f"{tmp_path / 'pool'}:1")
    order = []

    def lane(name, hold):
        with ar.lane_slot(poll_s=0.05):
            order.append(("in", name))
            _t.sleep(hold)
            order.append(("out", name))

    t1 = threading.Thread(target=lane, args=("a", 0.4)); t1.start()
    _t.sleep(0.1)
    t2 = threading.Thread(target=lane, args=("b", 0.0)); t2.start()
    t1.join(); t2.join()
    assert order == [("in", "a"), ("out", "a"), ("in", "b"), ("out", "b")], order


# ── P2C1 live round 0 (2026-10-09): eight parallel collectors, one window ──

def test_parallel_collectors_each_hold_their_capabilitys_window(tmp_path):
    from engine import ledger as L
    run = new_run(tmp_path, n=8)
    wb = run.open()
    cells = wb.selected_subcaps()
    cat = cells[0].split(".")[0]
    caps = sorted({".".join(c.split(".")[:2]) for c in cells if c.startswith(cat + ".")})
    actor = f"research-{cat.lower()}-collector"
    # the category's window is spent by OTHER lanes of the same category
    for i in range(L.SEARCH_OP_CEILING):
        L.append_search(wb, subcap=f"{caps[0]}.1" if f"{caps[0]}.1" in cells else
                        [c for c in cells if c.startswith(caps[0] + ".")][0],
                        facet="works", query=f"lane one query {i}", tool="web_search",
                        hits=1, kept=0, actor=actor)
    other = [c for c in cells if c.startswith(cat + ".") and not c.startswith(caps[0] + ".")]
    if other:
        # a sibling lane on another capability still logs: its own conversation
        L.append_search(wb, subcap=other[0], facet="primary", query="its own question",
                        tool="web_search", hits=0, kept=0, actor=actor)
    # the lane that fired sixty on ITS capability is walled
    with pytest.raises(L.LedgerRefusal, match="ceiling"):
        L.append_search(wb, subcap=[c for c in cells if c.startswith(caps[0] + ".")][0],
                        facet="fails", query="the sixty-first", tool="web_search",
                        hits=0, kept=0, actor=actor)
    # a category producer (one conversation for the category) keeps the category window
    with pytest.raises(L.LedgerRefusal, match="ceiling"):
        L.append_search(wb, subcap=(other or cells)[0], facet="value", query="producer query",
                        tool="web_search", hits=0, kept=0, actor=f"research-{cat.lower()}-producer")
    assert L._collector_scope(actor, [caps[0] + ".1", caps[0] + ".2"]) == caps[0]
    assert L._collector_scope(actor, [caps[0] + ".1", "P9C9.1.1"]) is None
    assert L._collector_scope(f"research-{cat.lower()}-producer", [caps[0] + ".1"]) is None


def test_a_bare_evidence_id_or_a_domain_is_a_checkable_anchor():
    from engine import quality as Q
    assert Q.is_fluent_but_empty(
        "careers posting E-096 on imacorp.com lists a producer role with digital duties") is None
    assert Q.is_fluent_but_empty("the posting on imacorp.com describes the producer role in detail") is None
    assert Q.is_fluent_but_empty("the team seems engaged and the work feels meaningful overall") is not None


def test_the_orchestrator_is_told_every_rule_it_burned_turns_on():
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    for rule in ("--inferable and --validation-question come together",
                 "must appear in an excerpt registered on THAT cell",
                 "a Dominant_Claim that asserts an absence is not a synthesis",
                 "(>= 20 chars"):
        assert rule in js, rule


def test_one_wait_reports_every_category_in_brief(tmp_path):
    from engine import tiers as T
    run = new_run(tmp_path, n=3)
    T._write(T._status_path(run, "P1C1"), {"category": "P1C1", "state": "done", "gate": "PASS",
                                           "usd": 1.5, "result": {"phases": {"collect": {
                                               "lanes": 3, "ok": 3, "usd": 1.0, "elapsed_s": 90}}}})
    T._write(T._status_path(run, "P1C2"), {"category": "P1C2", "state": "running", "pid": os.getpid()})
    got = T.wait_all(run, ["P1C1", "P1C2"], 0.2)
    assert got["state"] == "running" and got["running"] == ["P1C2"] and got["categories"] is None
    T._write(T._status_path(run, "P1C2"), {"category": "P1C2", "state": "failed", "error": "boom"})
    got = T.wait_all(run, ["P1C1", "P1C2"], 1)
    assert got["state"] == "done" and got["done"] == 1 and got["failed"] == 1 and got["usd"] == 1.5
    rows = {r["category"]: r for r in got["categories"]}
    assert rows["P1C1"]["phases"] == ["collect: 3 lanes, 3 ok, $1.00, 90s"]
    assert "result" not in rows["P1C1"], "a runner never re-reads the whole round result"
    assert rows["P1C2"]["error"] == "boom"


def test_the_tiers_runner_is_booked_to_research():
    from engine import cost
    assert cost.stage_of_agent({"workflowPhase": "Tiers", "label": "tiers · 16 categories"}, "") == "RESEARCH"


# ── dating: the date the page states, recorded at fetch, filled at the write ─

def test_the_page_states_its_date_and_nothing_else_does():
    from engine import fetch as F
    assert F.published_date('<meta property="article:published_time" content="2025-10-07T12:00Z">', "u") \
        == ("2025-10-07", "meta")
    assert F.published_date('{"datePublished": "2024-03-01T00:00"}', "u")[0] == "2024-03-01"
    assert F.published_date("", "https://www.businessinsurance.com/article/20230406/NEWS06/1/IMA")[0] == "2023-04-06"
    assert F.published_date("", "https://imacorp.com/wp-content/uploads/2024/07/Report.pdf")[0] == "2024-07-01"
    # never a modified date, an event's <time>, a copyright year or nothing at all
    assert F.published_date('<meta property="article:modified_time" content="2025-10-07">', "https://x.com/a") == (None, None)
    assert F.published_date('<time datetime="2026-11-01">Webinar</time>', "https://x.com/events") == (None, None)
    assert F.published_date("© 2024 IMA", "https://imacorp.com/about") == (None, None)


def test_an_omitted_date_is_filled_from_the_fetched_page(tmp_path):
    from engine import fetch as F
    from engine import ledger as L
    run = new_run(tmp_path, n=3)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    url = "https://news.example.org/story-about-acme"
    text = ("Acme Credit Union launched a new digital account opening flow that lets members "
            "open accounts in under five minutes, the credit union said in its announcement. ") * 3
    F.store_text(run, url, text, published=("2025-06-02", "meta"))
    e = L.append_evidence(wb, source_name="Example News", source_url=url, tier="T3",
                          excerpt=text[:200].strip(), subcaps=[cell], run=run,
                          actor=f"research-{cell.split('.')[0].lower()}-collector")
    row = next(r for r in run.open().rows("Evidence_Detail") if r["E_ID"] == e)
    assert str(row["Date_Published"])[:10] == "2025-06-02" and row["Recency"] != "UNVERIFIED"
    # an undated page stays undated: never today's date
    url2 = "https://acme.example.com/about"
    F.store_text(run, url2, text)
    e2 = L.append_evidence(wb, source_name="Acme", source_url=url2, tier="T5",
                           excerpt=text[:180].strip(), subcaps=[cell], run=run,
                           actor=f"research-{cell.split('.')[0].lower()}-collector")
    row2 = next(r for r in run.open().rows("Evidence_Detail") if r["E_ID"] == e2)
    assert not str(row2["Date_Published"] or "").strip() and row2["Recency"] == "UNVERIFIED"
