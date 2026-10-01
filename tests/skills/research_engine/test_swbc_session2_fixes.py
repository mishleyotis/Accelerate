"""Fixes from the second SWBC live run (2026-10-01), one test per defect.

J-09 closed cells the floors gate still refused were never handed back: the
     workflow batched only claim-less cells and told agents to skip the rest.
J-10 a placeholder publication date (the retrieval day) had no writer to fix
     it and no gate to catch it.
J-11 sixteen inlined Workflow calls overflowed the hook's inline budget.
J-12 a refused batch line lost its reason (stderr was not captured).
J-13 `update_row` could not clear a cell (openpyxl ignores value=None).
J-14 the heatmap evidence surfaces had no deterministic format step.
J-15 a bound connector measured DOWN still blocked every absence.
J-17 the internal documents reach the workflow args, not a dead-end brief.
J-18 the capability card skipped repair cells and never listed `primary`.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from engine import cli, contract as C, floors_gate, heatmap_live, ledger as L
from engine import orient, pipeline as P, pipeline_stub as S, preflight
from fixtures import (bank_evidence, fire_volleys, new_run, preflight_doc,
                      researched_run, two_category_selection)

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"


def _placeholder(wb, eid):
    """A legacy row dated the day it was retrieved (the I-51 shape)."""
    day = wb.evidence_index()[eid]["Retrieved_At"][:10]
    wb.update_row("Evidence_Detail", "E_ID", eid, {"Date_Published": day})
    return day


# ── J-13 ────────────────────────────────────────────────────────────────
def test_update_row_can_clear_a_cell(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False)
    wb = run.open()
    eid = bank_evidence(wb, wb.selected_subcaps()[0], n=2)[0]
    wb.update_row("Evidence_Detail", "E_ID", eid, {"Date_Published": None})
    assert not run.open().evidence_index()[eid]["Date_Published"]


# ── J-10 ────────────────────────────────────────────────────────────────
def test_placeholder_predicate():
    assert L.placeholder_date("2026-10-01", "2026-10-01T03:59:00Z", "no year here")
    assert not L.placeholder_date("2026-10-01", "2026-10-01T03:59:00Z", "Posted 1 Oct 2026")
    assert not L.placeholder_date("2026-09", "2026-09-30T00:00:00Z", "month only")
    assert not L.placeholder_date("2025-06-01", "2026-10-01T00:00:00Z", "older page")
    assert not L.placeholder_date(None, "2026-10-01T00:00:00Z")


def test_a_public_row_dated_today_needs_its_dated_words(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fire_volleys(wb, cell)
    today = L._utcnow()[:10]
    span = ("The homepage describes digital banking for members and lists the "
            "branch network without naming any launch or review date at all.")
    kw = dict(source_name="Acme home", source_url="https://acme.example/",
              tier="T2", excerpt=span, subcaps=[cell], published=today)
    with pytest.raises(L.LedgerRefusal, match="placeholder"):
        L.append_evidence(wb, **kw)
    assert L.append_evidence(wb, **kw, anchor_quote=f"Posted {today} by the press office")


def test_redate_clears_a_placeholder_and_the_gate_stops_blocking(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    eid = ev[cells[0]][0]
    day = _placeholder(wb, eid)
    g = floors_gate.run(run.open(), "P1C1", require_synthesis=True)
    assert {"subcap": cells[0], "e_id": eid} in g["date_placeholder"]
    assert "date_placeholder" in g["blocking"]
    with pytest.raises(L.LedgerRefusal, match="retrieved"):
        L.redate_evidence(wb, eid, published=day, reason="guessing it is today again")
    with pytest.raises(L.LedgerRefusal, match="why"):
        L.redate_evidence(wb, eid, published=None, reason="short")
    out = L.redate_evidence(wb, eid, published=None,
                            reason="the annual report page states no publication date")
    assert out["recency"] == C.RECENCY_UNVERIFIED
    fresh = run.open()
    assert not fresh.evidence_index()[eid]["Date_Published"]
    assert any(r.get("Step") == "evidence_redated" for r in fresh.rows("Provenance"))
    assert not floors_gate.run(fresh, "P1C1", require_synthesis=True)["date_placeholder"]


# ── J-09 ────────────────────────────────────────────────────────────────
def test_closed_cells_the_gate_refuses_are_repairs(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    eid = ev[cells[0]][0]
    _placeholder(wb, eid)
    wb = run.open()
    rep = P._repair_cells(wb, ["P1C1"])
    assert rep["P1C1"][cells[0]] == [f"date_placeholder:{eid}"]
    assert all(t not in P.CHALLENGER_TERMS for v in rep["P1C1"].values() for t in v)
    caps = P._with_repairs(P._open_capabilities(wb), rep)
    from engine.brief import capability_of
    assert caps["P1C1"][capability_of(cells[0])] >= 1, "a repair-only capability got no batch"


def _drive(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop,
                                      "finding-challenger": S.lane_noop})
    opts = P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                     push=False, folder_root=tmp_path / "client_out", ingest_poll_s=0,
                     sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                     max_rounds=2, stall_rounds=0, research_mode="workflow")
    p = P.Pipeline(run, opts)
    return p, p.run_all()


def test_the_handoff_carries_repairs_outages_and_documents(tmp_path):
    p, out = _drive(tmp_path)
    L.record_connector_down(p.run.root, "exa", status=402,
                            error="You have exceeded your credits limit")
    h = p._research_handoff()
    doc = json.loads(Path(h["file"]).read_text())
    for inv in doc["invocations"]:
        assert {"repair", "enrichment_down", "internal_docs"} <= set(inv)
        assert "exa" in inv["enrichment_down"]
    assert "repair_cells" in doc["estimate"]


# ── J-11 ────────────────────────────────────────────────────────────────
def _hook():
    spec = importlib.util.spec_from_file_location(
        "stage_advance", PLUGIN / "scripts" / "hooks" / "stage_advance.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    return sa


def test_long_workflow_calls_spill_to_a_sidecar_with_a_count(tmp_path):
    sa = _hook()
    inv = {"pillar": "P1", "cats": ["P1C1"], "run": "R", "root": "/r",
           "batches": {"P1C1": [[f"P1C1.{i}"] for i in range(1, 9)]},
           "repair": {"P1C1": {"P1C1.1.1": ["primary_unfired"]}}, "pad": "x" * 600}
    hand = tmp_path / "07_qa" / "research_workflow.json"
    hand.parent.mkdir(parents=True)
    hand.write_text(json.dumps({"workflow": "/w.js", "then": "engine.pipeline run",
                                "invocations": [dict(inv, cats=[f"P{i}C1"]) for i in range(16)]}))
    ev = {"tool_name": "Bash", "tool_input": {"command": "python3 -m engine.pipeline run"},
          "tool_response": {"stdout": f"AWAITING_WORKFLOW — {hand}"}}
    ctx = sa.awaiting_workflow(ev)["hookSpecificOutput"]["additionalContext"]
    assert len(ctx) <= sa.HOOK_INLINE_CHARS
    assert "ALL 16" in ctx and "roster" in ctx
    side = hand.with_name("research_workflow_calls.txt")
    assert len(side.read_text().strip().splitlines()) == 16


# ── J-12 ────────────────────────────────────────────────────────────────
def test_a_refused_batch_line_carries_its_reason(tmp_path, capsys):
    run, wb, cells, ev = researched_run(tmp_path)
    f = tmp_path / "ops.txt"
    f.write_text(f"redate --e-id {ev[cells[0]][0]} --undated --reason short\n")
    cli.main(["batch", "--run", run.run_id, "--root", str(run.root), "--file", str(f)])
    res = json.loads(capsys.readouterr().out)["results"][0]
    assert res["ok"] is False and "why" in res.get("error", "")


# ── J-15 ────────────────────────────────────────────────────────────────
def test_enrichment_degrades_only_when_every_web_family_is_measured_down(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False)
    wb = run.open()
    assert L.enrichment_binding(wb)["bound"]
    with pytest.raises(L.LedgerRefusal):
        L.record_connector_down(run.root, "exa", status=500, error="temporary server error, retry")
    L.record_connector_down(run.root, "exa", status=402, error="You have exceeded your credits limit")
    assert L.enrichment_binding(wb)["bound"], "Tavily still answers: it is the fallback"
    L.record_connector_down(run.root, "tavily", status=429,
                            error="Your request has been blocked due to excessive requests")
    b = L.enrichment_binding(wb)
    assert not b["bound"] and "MEASURED DOWN" in b["reason"]
    assert floors_gate.run(wb, wb.selected_subcaps()[0].split(".")[0]
                           )["enrichment_binding"]["absence_rigour"] == "REDUCED"
    L.record_connector_up(run.root, "tavily")
    assert L.enrichment_binding(wb)["bound"]


def test_the_absence_refusal_names_the_degraded_flag(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fire_volleys(wb, cell, n=0)
    for t, s, e in (("exa", 402, "You have exceeded your credits limit"),
                    ("tavily", 429, "blocked due to excessive requests")):
        L.record_connector_down(run.root, t, status=s, error=e)
    with pytest.raises(L.LedgerRefusal, match="--enrichment-unavailable"):
        L.declare_absence(wb, cell, actor="research-p1c1-producer",
                          ladder=[], proxy_log="x" * 50, what_was_hunted="y" * 50)


# ── J-14 ────────────────────────────────────────────────────────────────
def test_the_heatmap_evidence_surfaces_build_from_the_workbook(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    out = heatmap_live.build(run)
    assert not out["problems"], out["problems"]
    sec = json.loads(Path(out["evidence_section"]).read_text())
    assert len(sec["evidence"]) == len(wb.evidence_index())
    assert sec["e_ids"] == [i["e_id"] for i in sec["evidence"]]
    assert "evidence[*].tier" in sec["internal_only"]
    sk = json.loads(Path(out["skeleton"]).read_text())
    by = {c["subcap_id"]: c for c in sk["cells"]}
    assert by[cells[0]]["grounded_on"] == len(by[cells[0]]["items"]) > 0
    assert by[cells[0]]["synthesis"] is None
    absent = by[cells[-1]]
    assert absent["thin"] and absent["sources_searched"] and "closure_condition" in absent
    assert out["total"]["linked"] == len(cells) - 1


# ── J-18 ────────────────────────────────────────────────────────────────
def test_the_card_lists_a_synthesised_cell_that_still_owes_its_primary(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cell = cells[0]
    # Drop the primary volley from the log: the cell is synthesised yet owes it.
    ws = wb._sheet("Search_Log")
    cols = list(C.SHEETS["Search_Log"])
    for r in range(ws.max_row, 1, -1):
        if (ws.cell(row=r, column=cols.index("SubCap_ID") + 1).value == cell and
                ws.cell(row=r, column=cols.index("Facet") + 1).value == "primary"):
            ws.delete_rows(r)
    wb.save()
    from engine.brief import capability_of
    card = orient.capability_card(run.open(), capability_of(cell))
    row = next(c for c in card["open_cells"] if c["cell"] == cell)
    assert row["repair"] is True and "primary" in row["missing"]
    assert "primary_question" in row


# ── J-21 ────────────────────────────────────────────────────────────────
def test_workflow_spend_counts_each_message_once_and_corrects(tmp_path):
    from engine import cost
    run = new_run(tmp_path, n=2, prelim=False)
    d = tmp_path / "tx" / "proj" / "sess" / "subagents" / "workflows" / "wf_x"
    d.mkdir(parents=True)
    usage = {"cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 0,
             "input_tokens": 0, "output_tokens": 0}
    lines = []
    for mid in ("msg_1", "msg_2"):
        for block in range(3):        # one transcript line per content block
            lines.append(json.dumps({"type": "assistant", "message": {
                "id": mid, "model": "claude-sonnet-5-5", "usage": usage,
                "content": [{"type": "text", "text": f"{run.run_id} {block}"}]}}))
    (d / "agent-a1.jsonl").write_text("\n".join(lines))
    got = cost.capture_workflows(run, base=tmp_path / "tx")
    assert got["turns"] == 2, "each message counts once, not once per line"
    one = cost.cost_of(cache_read=2_000_000)["total_usd"]
    assert abs(got["usd"] - one) < 1e-6
    # An earlier overcount (the old per-line rule) is booked back as a correction.
    rec = run.qa_dir / cost._CAPTURED
    doc = json.loads(rec.read_text())
    doc["a1"] = {"usd": one * 3, "turns": 6, "tokens": {"cache_read": 6_000_000,
                 "cache_write": 0, "uncached": 0, "output": 0}}
    rec.write_text(json.dumps(doc))
    fix = cost.capture_workflows(run, base=tmp_path / "tx")
    assert fix["usd"] < 0 and fix["turns"] == -4


# ── J-22 ────────────────────────────────────────────────────────────────
def test_search_capacity_is_judged_before_a_handoff(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False)
    wb = run.open()
    cats = {c[:4] for c in wb.selected_subcaps()}
    ok = P._search_capacity(wb, cats, {}, {}, True)
    assert ok["fits"] and ok["owed_queries"] > 0
    dead = P._search_capacity(wb, cats, {}, {"exa": "402", "tavily": "429"}, False)
    assert dead["available"] == P.WEBSEARCH_SESSION_CAP
    assert dead["fits"] == (dead["owed_queries"] <= P.WEBSEARCH_SESSION_CAP)
    assert any("--allow-lanes" in o for o in dead["options"])


def test_the_workflow_prompt_names_clays_filter_field_and_the_pooled_budget():
    src = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert 'headline contains' in src
    assert "SESSION-POOLED" in src and "connector-down" in src and "redate" in src


# ── J-06 ────────────────────────────────────────────────────────────────
def _route():
    spec = importlib.util.spec_from_file_location(
        "route_client", PLUGIN / "scripts" / "route_client.py")
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)
    return rc


def test_an_in_flight_run_outranks_a_synthesis_answer():
    rc = _route()
    ptr = {"run_id": "DMA-RES-X-1", "pushed_at": "2026-10-01T02:13:27Z"}
    base = {"verdict": rc.READY_TO_SYNTHESISE, "display_id": "x", "why": "", "next": ""}
    out = rc.apply_in_flight(base, ptr, "X")
    assert out["verdict"] == rc.RESUME and "DMA-RES-X-1" in out["next"]
    assert out["superseded_verdict"] == rc.READY_TO_SYNTHESISE
    served = {**base, "verdict": rc.ALREADY_SERVED}
    assert rc.apply_in_flight(served, ptr, "X")["verdict"] == rc.ALREADY_SERVED
    assert rc.apply_in_flight(base, None, "X") == base


def test_the_snapshot_pointer_names_the_run_and_binding(tmp_path):
    from engine import snapshot
    run = new_run(tmp_path, n=2, prelim=False)
    ptr = snapshot.pointer(run, "Acme Credit Union")
    assert ptr["run_id"] == run.run_id and ptr["snapshot"] == snapshot.name_for(run.run_id)
    assert ptr["binding"]["sub_vertical"] == "CU"


def test_the_heatmap_page_brief_reads_the_prebuilt_sections_and_census(tmp_path):
    from engine import brief
    run, wb, cells, ev = researched_run(tmp_path)
    heatmap_live.build(run)
    pre = brief._prebuilt(run, "heatmap")
    assert "heatmap.evidence" in pre and "heatmap.cell_evidence" in pre
    assert pre["census"]["synthesis_owed"] == len(cells) - 1
    assert brief._prebuilt(run, "overview") == {}
