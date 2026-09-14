"""The orchestrator-side relay batch (C3-4).

The connectors are held by the ORCHESTRATOR's session, not by a headless
lane: they bind once, at session start, and a `claude -p` child is a
different session with none of them. So a lane emits `search_requests` and
the conductor services them — and the question this file pins is what
"services them" costs.

The measured shape it replaces: `drain_batch` grouped the open requests by
CATEGORY and dispatched one `enrichment-web-specialist` lane per group into
the same container that has no connector — sixteen lane context floors per
round (~290K tokens) before a single query ran, one connector call per
request, and the same query paid for twice when two categories asked it.

What replaces it: one batch file plus one SELF-CONTAINED prompt per
capability, written to disk and dispatched by nothing. Queries are
deduplicated by their normalised form across the whole run, so one search
closes every request that asked for it; each query carries the single
`engine.cli search` call whose repeated `--subcap` writes a row per cell and
charges the search-op ceiling once, and the single `engine.relay record
--ids a,b` that closes every request behind it. The conductor dispatches a
fresh in-process subagent per batch, so a batch's prompt must carry that
batch's work and NOTHING else — the other batches' cells in its context are
tokens it pays for on every turn and work it might do twice.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import contract as C, ledger as L, relay

from fixtures import new_run


def _result(text):
    return json.dumps({"type": "result", "result": text})


def _transcript(logs: Path, lane: str, reqs):
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"{lane}.jsonl").write_text(
        _result(json.dumps({"search_requests": list(reqs)})) + "\n")


def _run_with(tmp_path, lanes: dict):
    """A started run whose relay queue holds exactly what `lanes` emitted."""
    run = new_run(tmp_path, n=4, prelim=False)
    logs = run.root / "agent_logs"
    for lane, reqs in lanes.items():
        _transcript(logs, lane, reqs)
    relay.harvest(run, None, logs_dir=logs)
    return run


def _queries(out):
    return [q for g in out["groups"] for q in g["queries"]]


# ═══════════════════════════════════════════════════════════════════════════
# propose_tool: a small table, and a request's own choice wins
# ═══════════════════════════════════════════════════════════════════════════

def test_a_people_query_proposes_clay():
    assert relay.propose_tool({"query": "who is the CIO of Acme Credit Union"}) == "clay"
    assert relay.propose_tool({"query": "Acme Credit Union leadership team"}) == "clay"
    assert relay.propose_tool({"query": "Acme Credit Union headcount 2025"}) == "clay"


def test_a_technographic_query_proposes_vibe():
    assert relay.propose_tool(
        {"query": "Acme Credit Union core banking vendor"}) == "vibe"
    assert relay.propose_tool(
        {"query": "what CRM does Acme Credit Union run"}) == "vibe"


def test_anything_else_proposes_exa():
    assert relay.propose_tool(
        {"query": "Acme Credit Union mobile app redesign announcement"}) == "exa"
    assert relay.propose_tool({"query": ""}) == "exa"


def test_the_requests_own_tool_is_honoured_when_it_is_an_enrichment_tool():
    # A lane that named a connector knows something the keyword table does
    # not; the table is the fallback, never the override.
    assert relay.propose_tool(
        {"query": "who is the CIO of Acme", "tool": "tavily"}) == "tavily"
    # `web_search` is not an enrichment tool: the relay exists because the
    # lane could not reach a connector, so a bare-web preference is ignored.
    assert relay.propose_tool(
        {"query": "who is the CIO of Acme", "tool": "web_search"}) == "clay"
    assert relay.propose_tool({"query": "anything", "tool": "not-a-tool"}) == "exa"


def test_every_proposal_is_a_tool_the_search_log_accepts():
    for q in ("who is the CIO", "core banking platform", "anything at all"):
        assert relay.propose_tool({"query": q}) in C.ENRICHMENT_TOOLS


# ═══════════════════════════════════════════════════════════════════════════
# batch: dedupe by query, group by capability
# ═══════════════════════════════════════════════════════════════════════════

DUPE = '"Acme Credit Union" core banking platform'


def test_the_same_query_from_two_categories_collapses_to_one_command(tmp_path):
    """The cross-category dedupe. Two lanes asked the same thing about two
    cells; that is ONE connector call, one Search_Log write naming both
    cells, and one record closing both requests."""
    run = _run_with(tmp_path, {
        "research-p1c1-producer": [
            {"query": DUPE, "subcap": "P1C1.1.1", "facet": "works"}],
        "research-p2c3-producer": [
            {"query": " " + DUPE.upper() + " ", "subcap": "P2C3.1.1", "facet": "works"}],
    })
    out = relay.batch(run, run.open())
    qs = _queries(out)
    assert len(qs) == 1, f"one query, not {len(qs)}"
    q = qs[0]
    assert sorted(q["subcaps"]) == ["P1C1.1.1", "P2C3.1.1"]
    assert len(q["request_ids"]) == 2, "both requests ride the one search"
    cmd = q["command_search"]
    assert cmd.count("--subcap ") == 2 and "P1C1.1.1" in cmd and "P2C3.1.1" in cmd
    for rid in q["request_ids"]:
        assert rid in q["command_record"]
    assert out["requests"] == 2 and out["queries"] == 1


def test_requests_group_by_capability_not_by_category(tmp_path):
    run = _run_with(tmp_path, {"research-p1c1-producer": [
        {"query": "acme credit union online account opening flow", "subcap": "P1C1.1.1"},
        {"query": "acme credit union branch appointment booking", "subcap": "P1C1.1.2"},
        {"query": "acme credit union data warehouse migration", "subcap": "P1C1.2.1"},
    ]})
    out = relay.batch(run, run.open())
    assert sorted(g["key"] for g in out["groups"]) == ["P1C1.1", "P1C1.2"], (
        "the capability is the grain — one category is not one batch")
    by_key = {g["key"]: g for g in out["groups"]}
    assert len(by_key["P1C1.1"]["queries"]) == 2
    assert len(by_key["P1C1.2"]["queries"]) == 1


def test_grouping_by_tool_is_available_for_a_connector_run(tmp_path):
    run = _run_with(tmp_path, {"research-p1c1-producer": [
        {"query": "who is the CIO of Acme Credit Union", "subcap": "P1C1.1.1"},
        {"query": "acme credit union core banking vendor", "subcap": "P1C1.2.1"},
    ]})
    out = relay.batch(run, run.open(), group_by="tool")
    assert sorted(g["key"] for g in out["groups"]) == ["clay", "vibe"]
    assert all(g["key"] == g["tool"] for g in out["groups"])


def test_the_search_command_is_one_call_that_charges_the_ceiling_once(tmp_path):
    run = _run_with(tmp_path, {"research-p1c1-producer": [
        {"query": "acme credit union alkami digital banking", "subcap": "P1C1.1.1",
         "facet": "works", "tool": "exa"}]})
    out = relay.batch(run, run.open())
    q = _queries(out)[0]
    cmd = q["command_search"]
    assert cmd.startswith("python3 -m engine.cli search ")
    assert cmd.count("python3 -m engine.cli search") == 1, "one call, not one per cell"
    for must in (f"--run {run.run_id}", f"--root {run.root}", "--subcap P1C1.1.1",
                 "--facet works", "--tool exa", "--hits N", "--kept K"):
        assert must in cmd, must
    assert "acme credit union alkami digital banking" in cmd
    rec = q["command_record"]
    assert rec.startswith("python3 -m engine.relay record ")
    assert f"--ids {q['request_ids'][0]}" in rec
    assert "--status SERVED|EMPTY|BLOCKED" in rec and "--tool exa" in rec


def test_a_request_naming_no_cell_becomes_a_prelim_search(tmp_path):
    run = _run_with(tmp_path, {"research-p1c1-producer": [
        {"query": "acme credit union total assets and member count"}]})
    out = relay.batch(run, run.open())
    q = _queries(out)[0]
    assert "--prelim" in q["command_search"]
    assert "--subcap" not in q["command_search"]


def test_a_query_with_a_quote_survives_the_command_line(tmp_path):
    """The commands are pasted into a shell. A query carrying an apostrophe
    that ends its own quote is a command that does something else."""
    import shlex
    run = _run_with(tmp_path, {"research-p1c1-producer": [
        {"query": "acme's core banking platform", "subcap": "P1C1.1.1"}]})
    q = _queries(relay.batch(run, run.open()))[0]
    parts = shlex.split(q["command_search"])
    assert "acme's core banking platform" in parts


# ═══════════════════════════════════════════════════════════════════════════
# the artefacts: one batch file, one self-contained prompt per capability
# ═══════════════════════════════════════════════════════════════════════════

def _two_capabilities(tmp_path):
    return _run_with(tmp_path, {"research-p1c1-producer": [
        {"query": "acme credit union online account opening flow",
         "subcap": "P1C1.1.1", "facet": "works"},
        {"query": "acme credit union data warehouse migration",
         "subcap": "P1C1.2.1", "facet": "works"},
    ]})


def test_batch_writes_the_json_the_md_and_one_prompt_per_capability(tmp_path):
    run = _two_capabilities(tmp_path)
    out = relay.batch(run, run.open(), out_dir=tmp_path / "briefs" / "relay_r0")
    bf = Path(out["batch_file"])
    assert bf.is_file() and bf.parent == run.qa_dir and bf.name == "relay_batch_r0.json"
    assert json.loads(bf.read_text())["groups"]
    assert bf.with_suffix(".md").is_file(), "a .md beside it, for a person"
    names = sorted(p.name for p in (tmp_path / "briefs" / "relay_r0").glob("*.md"))
    assert names == ["P1C1.1.md", "P1C1.2.md"]


def test_a_prompt_names_only_its_own_batchs_cells(tmp_path):
    """The conductor dispatches a FRESH subagent per batch. Whatever else is
    in that prompt is context the subagent pays for on every turn and work it
    may do twice, so a batch's prompt carries its own cells and no others."""
    run = _two_capabilities(tmp_path)
    out = relay.batch(run, run.open(), out_dir=tmp_path / "briefs" / "relay_r0")
    prompts = {Path(p["prompt_file"]).stem: Path(p["prompt_file"]).read_text()
               for p in out["prompts"]}
    assert "P1C1.1.1" in prompts["P1C1.1"] and "P1C1.2.1" not in prompts["P1C1.1"]
    assert "P1C1.2.1" in prompts["P1C1.2"] and "P1C1.1.1" not in prompts["P1C1.2"]
    assert "data warehouse migration" not in prompts["P1C1.1"]
    assert "online account opening" not in prompts["P1C1.2"]


def test_a_prompt_carries_the_connector_the_queries_and_the_record_commands(tmp_path):
    run = _two_capabilities(tmp_path)
    out = relay.batch(run, run.open(), out_dir=tmp_path / "briefs" / "relay_r0")
    text = Path(out["prompts"][0]["prompt_file"]).read_text()
    for must in ("engine.cli search", "engine.relay record", "--status SERVED|EMPTY|BLOCKED",
                 "engine.cli evidence", run.run_id):
        assert must in text, must
    assert "exa" in text.lower()
    assert "BLOCKED" in text and "never log a connector search you did not run" in text.lower()


def test_batch_with_nothing_open_writes_nothing(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    out = relay.batch(run, run.open(), out_dir=tmp_path / "briefs" / "relay_r0")
    assert out["groups"] == [] and out["queries"] == 0
    assert out["batch_file"] is None
    assert not (tmp_path / "briefs" / "relay_r0").exists()


def test_batch_can_be_restricted_to_the_categories_of_this_round(tmp_path):
    run = _run_with(tmp_path, {
        "research-p1c1-producer": [{"query": "acme credit union alpha lookup",
                                    "subcap": "P1C1.1.1"}],
        "research-p2c3-producer": [{"query": "acme credit union beta lookup",
                                    "subcap": "P2C3.1.1"}],
    })
    out = relay.batch(run, run.open(), categories=["P2C3"],
                      out_dir=tmp_path / "briefs" / "relay_r0")
    assert [g["key"] for g in out["groups"]] == ["P2C3.1"]


# ═══════════════════════════════════════════════════════════════════════════
# record: many ids at once, and a partial failure that names its id
# ═══════════════════════════════════════════════════════════════════════════

def _three(tmp_path):
    run = _run_with(tmp_path, {"research-p1c1-producer": [
        {"query": f"acme credit union lookup number {i}", "subcap": f"P1C1.1.{i}"}
        for i in (1, 2, 3)]})
    return run, [r["id"] for r in relay.open_requests(run)]


def test_record_closes_many_ids_in_one_call(tmp_path):
    run, ids = _three(tmp_path)
    out = relay.record(run, ids, "SERVED", note="one exa call answered all three",
                       actor="research-conductor", tool="exa")
    assert out["ids"] == ids and out["status"] == "SERVED"
    st = relay.state(run)
    assert st["by_status"]["SERVED"] == 3 and st["by_status"]["OPEN"] == 0


def test_a_single_id_still_works_and_still_returns_id(tmp_path):
    run, ids = _three(tmp_path)
    out = relay.record(run, ids[0], "EMPTY", note="nothing usable")
    assert out["id"] == ids[0] and out["ids"] == [ids[0]]
    assert relay.state(run)["by_status"]["EMPTY"] == 1


def test_an_unknown_id_is_named_and_the_rest_are_still_recorded(tmp_path):
    """A partial failure must not cost the ids that were good: the conductor
    would otherwise re-run every query in the batch to close one request."""
    run, ids = _three(tmp_path)
    with pytest.raises(L.LedgerRefusal) as e:
        relay.record(run, [ids[0], "SR-ffffffffff", ids[1]], "SERVED", note="two of three")
    assert "SR-ffffffffff" in str(e.value), "the refusal names the id that failed"
    st = relay.state(run)
    assert st["by_status"]["SERVED"] == 2, "the good ids are recorded"
    assert st["by_status"]["OPEN"] == 1


def test_record_still_refuses_a_blocked_with_no_reason_and_an_unknown_status(tmp_path):
    run, ids = _three(tmp_path)
    with pytest.raises(L.LedgerRefusal):
        relay.record(run, ids, "BLOCKED")
    with pytest.raises(L.LedgerRefusal):
        relay.record(run, ids, "OPEN")
    assert relay.state(run)["by_status"]["OPEN"] == 3, "a refused call records nothing"


# ═══════════════════════════════════════════════════════════════════════════
# drain_batch modes: orchestrator writes and dispatches nothing; lane is kept
# ═══════════════════════════════════════════════════════════════════════════

def test_orchestrator_mode_writes_the_files_and_dispatches_no_lane(tmp_path):
    run = _two_capabilities(tmp_path)
    out_dir = tmp_path / "briefs" / "relay_r0"
    out = relay.drain_batch(run, run.open(), out_dir=out_dir)
    assert out["lanes"] == 0, "no headless specialist — the conductor holds the connectors"
    assert out["pending"] == 2
    assert Path(out["batch_file"]).is_file()
    assert not (out_dir / "batch.json").exists(), "no agent_run batch array is written"
    assert sorted(p.name for p in out_dir.glob("*.md")) == ["P1C1.1.md", "P1C1.2.md"]


def test_orchestrator_is_the_default_mode(tmp_path):
    run = _two_capabilities(tmp_path)
    assert relay.DEFAULT_RELAY_MODE == "orchestrator"
    out = relay.drain_batch(run, run.open(), out_dir=tmp_path / "b" / "relay_r0")
    assert out["lanes"] == 0


def test_lane_mode_is_unchanged(tmp_path):
    run = _run_with(tmp_path, {
        "research-p1c1-producer": [{"query": "acme credit union alpha lookup",
                                    "subcap": "P1C1.1.1", "facet": "works"}],
        "research-p2c3-producer": [{"query": "acme credit union beta lookup",
                                    "subcap": "P2C3.1.1", "facet": "works"}],
    })
    out = relay.drain_batch(run, run.open(), out_dir=tmp_path / "relay", mode="lane")
    assert out["lanes"] == 2 and out["requests"] == 2
    rows = json.loads(Path(out["batch"]).read_text())
    assert {r["agent"] for r in rows} == {relay.DRAIN_AGENT}
    assert sorted(r["label"] for r in rows) == [f"{relay.DRAIN_AGENT}@P1C1",
                                                f"{relay.DRAIN_AGENT}@P2C3"]


def test_an_unknown_mode_is_refused(tmp_path):
    run = _two_capabilities(tmp_path)
    with pytest.raises(ValueError):
        relay.drain_batch(run, run.open(), out_dir=tmp_path / "x", mode="magic")


# ═══════════════════════════════════════════════════════════════════════════
# the command line
# ═══════════════════════════════════════════════════════════════════════════

def test_the_batch_verb_prints_the_batch(tmp_path, capsys):
    run = _two_capabilities(tmp_path)
    rc = relay.main(["batch", "--run", run.run_id, "--root", str(run.root), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert sorted(g["key"] for g in out["groups"]) == ["P1C1.1", "P1C1.2"]
    assert Path(out["batch_file"]).is_file()


def test_the_batch_verb_takes_group_by_tool(tmp_path, capsys):
    run = _two_capabilities(tmp_path)
    rc = relay.main(["batch", "--run", run.run_id, "--root", str(run.root),
                     "--group-by", "tool", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["group_by"] == "tool"
    assert all(g["key"] in C.ENRICHMENT_TOOLS for g in out["groups"])


def test_the_record_verb_takes_ids(tmp_path, capsys):
    run, ids = _three(tmp_path)
    rc = relay.main(["record", "--run", run.run_id, "--root", str(run.root),
                     "--ids", ",".join(ids[:2]), "--status", "SERVED",
                     "--note", "one call", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ids"] == ids[:2]
    assert relay.state(run)["by_status"]["SERVED"] == 2


def test_the_record_verb_still_takes_a_single_id(tmp_path, capsys):
    run, ids = _three(tmp_path)
    rc = relay.main(["record", "--run", run.run_id, "--root", str(run.root),
                     "--id", ids[0], "--status", "EMPTY", "--json"])
    assert rc == 0
    assert relay.state(run)["by_status"]["EMPTY"] == 1


def test_the_record_verb_needs_one_of_id_or_ids(tmp_path):
    run, ids = _three(tmp_path)
    with pytest.raises(SystemExit):
        relay.main(["record", "--run", run.run_id, "--root", str(run.root),
                    "--status", "SERVED"])


def test_the_docstring_names_the_verbs_that_exist():
    doc = relay.__doc__
    for verb in ("batch", "record", "harvest", "reconcile"):
        assert f"engine.relay {verb}" in doc, verb
    assert "--ids" in doc


def test_the_relay_and_the_brief_agree_on_what_a_capability_is():
    """`relay.capability_of` is derived locally on purpose — the relay is the
    one module a conductor runs on its own, and a batch that cannot be
    written because the brief builder failed to import is a batch nobody
    services. Two definitions of one grain still have to agree."""
    from engine import brief
    for cell in ("P1C1.1.1", "P1C1.1.CU2", "P2C3.4.10", "P4C2.11.3"):
        assert relay.capability_of(cell) == brief.capability_of(cell)
