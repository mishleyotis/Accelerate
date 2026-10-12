"""A locked peer set can be WIDENED by its owner while no figure rests on it.

R-INTERAC-20261010 (2026-10-12): PRELIM locked one peer; REPORTS refused
(client_research §4 fails below three) with "the engagement owner widens the
set" — and `lock_peer_set` refused any different set, so nothing could.
`engine.prelim widen-peers` only adds, only while every Peer_Median,
quartile and Peer_Scores cell is blank, and records the owner and reason.
"""
import pytest

from engine import prelim as PR
from engine import brief

from fixtures import new_run

RULE = ("national debit and real-time payment scheme operators serving "
        "financial institutions in comparable markets")


def _locked(tmp_path):
    run = new_run(tmp_path, n=4, prelim=False, folder=False)
    wb = run.open()
    PR.peers(wb, ["Peer A"], rule=RULE, basis="cannot_estimate")
    return run


def _widen(wb, add=("Peer B", "Peer C"), **kw):
    args = dict(rule=RULE, owner="dma@zennify.com",
                why="client_research §4 requires three peers; owner approved")
    args.update(kw)
    return PR.widen_peers(wb, list(add), **args)


def test_the_owner_widens_a_set_no_figure_rests_on(tmp_path):
    run = _locked(tmp_path)
    out = _widen(run.open())
    assert out["locked_peer_set"] == ["Peer A", "Peer B", "Peer C"]
    wb = run.open()
    lock = wb.handoff_lock()
    assert lock["locked_peer_set"] == "Peer A|Peer B|Peer C"
    assert int(lock["peer_n"]) == 3
    assert all(int(r["Peer_N"]) == 3 and "Peer C" in r["Peer_Names"]
               for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID"))
    assert any(r.get("Gate") == "PEER_SET_WIDENED" for r in wb.rows("Gate_Log"))
    assert not [b for b in brief.report_preflight(wb) if b["kind"] == "owner"]


def test_a_set_with_a_figure_written_is_not_widened(tmp_path):
    run = _locked(tmp_path)
    wb = run.open()
    cid = next(r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID"))
    wb.update_row("Peer_Benchmarks", "Category_ID", cid, {"Peer_Median": 2.5})
    with pytest.raises(PR.PrelimRefusal, match="peer figures are already written"):
        _widen(run.open())


def test_widening_never_removes_and_needs_owner_and_reason(tmp_path):
    run = _locked(tmp_path)
    with pytest.raises(PR.PrelimRefusal, match="already in the locked set"):
        _widen(run.open(), add=["Peer A"])
    with pytest.raises(PR.PrelimRefusal, match="engagement owner"):
        _widen(run.open(), owner="")
    with pytest.raises(PR.PrelimRefusal, match="why"):
        _widen(run.open(), why="short")
    out = _widen(run.open(), add=["Peer B"])
    assert "Peer A" in out["locked_peer_set"]


# ── the probe round opens a fresh RELAY window ──────────────────────────
#
# Same run: RESEARCH left the RELAY window at 955 against 60 and nothing
# reset it, so all 56 report-probe searches ran and were refused unlogged.

from types import SimpleNamespace

from engine import ledger as L
from engine import pipeline as P

from engine import pipeline_stub as S
from fixtures import researched_run


def test_the_report_probe_round_resets_the_relay_window(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    # fill RELAY's window the way a long research stage does
    for i in range(L.SEARCH_OP_CEILING + 5):
        try:
            L.append_search(wb, subcap=[cells[0]], facet="corroborates", tool="exa",
                            query=f"relay connector volley {i}", hits=0, kept=0,
                            outcome="EMPTY", actor="enrichment-web-specialist")
        except L.LedgerRefusal:
            break
    assert L._ops_since_checkpoint(run.open(), "RELAY") >= L.SEARCH_OP_CEILING
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None)
    P.Pipeline(run, opts)._report_probes()
    assert L._ops_since_checkpoint(run.open(), "RELAY") < L.SEARCH_OP_CEILING


# ── a version-A page can be deferred to version B ───────────────────────
#
# Same run: techstack failed ET-07/ET-12 on version A against evidence the
# server ingested before the workbook's repairs, and a page halted on A
# stopped the run. `--defer-to-b techstack` moves it, logged.

def test_a_deferred_page_is_not_owed_on_version_a(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None,
                     defer_to_b=("techstack",))
    pl = P.Pipeline(run, opts)
    assert pl._deferred() == ("techstack",)
    ok, why = pl.done("PAGES_A")
    assert why == "pending: heatmap"           # techstack is no longer owed on A
    assert any(r.get("Gate") == "PAGES_DEFERRED_TO_B" for r in run.open().rows("Gate_Log"))
    # remembered on resume without the flag
    opts2 = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                      shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o",
                      ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None)
    assert P.Pipeline(run, opts2)._deferred() == ("techstack",)


# ── a report that quotes its gates cannot re-trip GS-RPT-NOTOKENS ────────

def test_a_leftover_token_finding_names_tokens_without_braces(tmp_path):
    from engine import gold_standard as G
    import inspect, re
    src = inspect.getsource(G)
    assert "leftover template token(s)" in src
    # the finding text the Gate_Log will carry has no {{...}}
    tok = ["{{CATALOGUE_VERSION}}", "{{CATALOGUE_HASH}}"]
    names = sorted({t.strip("{} ") for t in tok})
    assert not re.search(r"\{\{", ", ".join(names))


def test_the_gate_table_renders_the_latest_verdict_per_gate_and_scope(tmp_path):
    from engine import ledger as L, reports as R, report_spec as RS
    run, wb, cells, ev = researched_run(tmp_path)
    L.append_gate(wb, gate="GS", scope="report:research", verdict="FAIL", blocking=True,
                  detail="1 finding(s): GS-RPT-NOTOKENS: ['{{CATALOGUE_VERSION}}']")
    L.append_gate(wb, gate="GS", scope="report:research", verdict="PASS", blocking=True,
                  detail="PASS — 0 findings")
    sec = next(s for spec in RS.SPECS.values() for s in spec.sections
               if "Gate_Log" in s.inputs)
    tables = R._tables_for(run.open(), sec)
    text = repr(tables)
    assert "{{CATALOGUE_VERSION}}" not in text
    assert "PASS — 0 findings" in text


def test_a_deferred_page_ships_last_and_its_halt_does_not_block_the_others(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None,
                     defer_to_b=("techstack",))
    pl = P.Pipeline(run, opts)
    order = []

    def ship(pages, version, produce=True):
        order.append(tuple(pages))
        if "techstack" in pages:
            raise P.StageRefused("techstack halted on ET-12")
        return list(pages)
    pl._ship_pages = ship
    pl._pages_prepare = lambda pages: None
    import pytest
    with pytest.raises(P.StageRefused, match="every other page shipped to version B") as e:
        pl._stage_pages_b()
    assert order[-1] == ("techstack",)
    assert "overview" in str(e.value) and "context" in str(e.value)


def test_a_report_section_citation_with_no_cell_is_advisory_not_a_halt(tmp_path):
    """Identity evidence cited from a report section supports no cell; the
    page states why on the surface. The preflight warns, it does not halt."""
    from engine import page_preflight as PP, ledger as L
    run, wb, cells, ev = researched_run(tmp_path)
    eid = L.append_evidence(wb, source_name="Acme 2024 Annual Report", source_url="https://acme.example/ar",
                            tier="T2", excerpt="Acme employed more than nine hundred people across its offices in 2024.",
                            subcaps=[], origin="public")
    wb.append("Report_Narrative", {"Section_ID": "3", "Evidence_IDs": eid})
    found = [b for b in PP.preflight(run.open(), ("overview",)) if eid in b["detail"]]
    assert found and all(b["severity"] == "warn" for b in found)
