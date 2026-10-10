"""Root causes closed after R-INTERAC-20261010 (2026-10-10), each with the
measurement that showed it. See 07_qa/Interac_DMA_cost_RCA_stress_test.xlsx."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from engine import brief
from fixtures import new_run

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"


def _agent_run():
    spec = importlib.util.spec_from_file_location("agent_run", PLUGIN / "scripts" / "agent_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── RC2: PRELIM ran on opus ($4.31 of $4.86 against a $2 envelope) ─────────

def test_prelim_lanes_run_lean_on_sonnet_and_haiku_never_opus(tmp_path):
    run = new_run(tmp_path / "r", prelim=False)
    b = brief.prelim_brief(run.open(), run=run, out_dir=tmp_path / "p")
    rows = {r["label"]: r for r in json.loads(Path(b["batch"]).read_text())}
    assert rows["prelim-conductor"]["lean"]["model"] == "sonnet"
    assert rows["prelim-techscan"]["lean"]["model"] == "haiku"
    for r in rows.values():
        lean = r["lean"]
        assert lean["model"] != "opus"
        assert lean["cwd"] == str(run.root), "from the run dir: no repo CLAUDE.md in every turn"
        assert "WebSearch" in lean["tools"] and not any(t.startswith("mcp__") for t in lean["tools"])


def test_the_prelim_conductor_argv_names_its_model_and_holds_no_mcp(tmp_path):
    ar = _agent_run()
    spec = brief.prelim_lean_specs(None)["prelim-conductor"]
    cmd, cwd = ar.lean_command("research-conductor", spec, "prompt", stream=False,
                               scratch=tmp_path)
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert "--strict-mcp-config" in cmd and "--setting-sources" in cmd


# ── RC3: every volley fell to WebSearch, whose fee was 62% of a lane ───────

def _render(tmp_path, degraded: bool):
    import subprocess
    handoff = {
        "workflow": str(PLUGIN / "workflows" / "dma-pillar-research.js"),
        "invocations": [{"pillar": "P3", "cats": ["P3C1"], "run": "R-T", "root": str(tmp_path),
                         "eng": str(PLUGIN / "skills" / "dma-research"), "plugin": str(PLUGIN),
                         "batches": {"P3C1": [["P3C1.6", "P3C1.7"]]}, "repairs": {"P3C1": {}},
                         "repair_batches": {"P3C1": []},
                         "models": {"collector": "haiku", "synthesis": "sonnet", "challenge": "sonnet"},
                         "degraded": degraded, "entity": "Acme", "domain": "acme.example"}],
    }
    hp = tmp_path / f"h{int(degraded)}.json"; hp.write_text(json.dumps(handoff))
    out = tmp_path / f"p{int(degraded)}"
    r = subprocess.run(["node", str(PLUGIN / "workflows" / "render-prompts.mjs"), str(hp), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return (out / "P3C1_collect1.md").read_text()


def test_a_connector_backed_collector_searches_through_the_connectors_first(tmp_path):
    text = _render(tmp_path, degraded=False)
    assert "THE CONNECTORS ARE THE PRIMARY VOLLEY" in text
    assert "web_search (WebSearch) is the primary volley" not in text
    assert "ONLY for a query both connectors errored on" in text
    assert "AT MOST 8 CONNECTOR CALLS IN ONE MESSAGE" in text and "429" in text
    assert "10 parallel WebSearch calls" not in text


def test_a_degraded_collector_still_volleys_through_websearch_in_one_message(tmp_path):
    text = _render(tmp_path, degraded=True)
    assert "DEGRADED RUN" in text and "ONE message of parallel WebSearch calls" in text
    assert "THE CONNECTORS ARE THE PRIMARY VOLLEY" not in text


# ── RC4: 9 of 23 cells failed the challenge on rules the writer never saw ──

from engine import ledger as L, assessment as A  # noqa: E402
from fixtures import new_run as _new_run  # noqa: E402,F811


def test_the_ledger_band_table_is_the_scorers():
    assert L.BAND_TOP == A.BAND_TOP


def _wb_with_rows(tmp_path, rows):
    run = _new_run(tmp_path / "r")
    wb = run.open()
    reg = []
    for i, (url, recency) in enumerate(rows, 1):
        reg.append({"E_ID": f"E-9{i:02d}", "Source_URL": url, "Source_Name": url,
                    "Recency": recency, "Tier": "T2"})
    wb.evidence_index = lambda: {r["E_ID"]: r for r in reg}  # the register the rules read
    wb.own = None
    return wb, [r["E_ID"] for r in reg]


def _merged(band, claim="Interac acknowledges merchant complaints within five business days.",
            label="INFERENCE"):
    return {"Claim_Label": label, "Ceiling_Band": band, "Dominant_Claim": claim,
            "What_We_Found": claim, "Triangulation": "consistent with the policy page"}


def test_a_band_above_the_own_site_cap_is_refused_at_the_write(tmp_path, monkeypatch):
    wb, eids = _wb_with_rows(tmp_path, [("https://www.interac.ca/a", "CURRENT"),
                                        ("https://www.interac.ca/b", "CURRENT")])
    monkeypatch.setattr(L, "own_hosts", lambda wb: {"interac.ca"})
    bad = L.label_fit_problems(wb, "P3C1.7.1", _merged("Building"), eids)
    assert any("entity's own site (cap 2.0)" in p for p in bad), bad
    ok = L.label_fit_problems(wb, "P3C1.7.1", _merged("Activating"), eids)
    assert not any(p.startswith("Ceiling_Band") for p in ok), ok


def test_one_source_identity_caps_the_band_at_building(tmp_path, monkeypatch):
    wb, eids = _wb_with_rows(tmp_path, [("https://www.bankofcanada.ca/a", "CURRENT")])
    monkeypatch.setattr(L, "own_hosts", lambda wb: {"interac.ca"})
    assert any("one source identity" in p for p in
               L.label_fit_problems(wb, "P3C1.8.CIB3", _merged("Competing", label="CEILING_ESTIMATE"), eids))
    assert not any(p.startswith("Ceiling_Band") for p in
                   L.label_fit_problems(wb, "P3C1.8.CIB3", _merged("Building", label="CEILING_ESTIMATE"), eids))


@pytest.mark.parametrize("recency,claim,refused", [
    ("STALE", "Interac runs a regression test suite for every release.", True),
    ("ARCHIVAL", "Interac runs a regression test suite for every release.", True),
    ("STALE", "As of the 2019 posting, Interac ran a regression suite.", False),
    ("STALE", "Historically Interac ran a regression suite.", False),
    ("UNVERIFIED", "Interac runs a regression test suite for every release.", False),
    ("CURRENT", "Interac runs a regression test suite for every release.", False),
])
def test_tense_follows_the_recency_of_the_cited_rows(tmp_path, monkeypatch, recency, claim, refused):
    wb, eids = _wb_with_rows(tmp_path, [("https://example.org/a", recency),
                                        ("https://example.net/b", recency)])
    monkeypatch.setattr(L, "own_hosts", lambda wb: {"interac.ca"})
    got = L.label_fit_problems(wb, "P3C1.4.1", _merged("Building", claim=claim), eids)
    assert any(p.startswith("every row on this cell") for p in got) is refused, got


def test_the_orchestrator_is_told_both_rules_before_it_writes():
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "never above the evidence's own cap" in js and "never unqualified present tense" in js


# ── RC5: a smear written upstream could not be undone (P3C1.7.1/7.2/7.4) ──

def _evidence(wb, cell, n, url="https://www.interac.ca/en/complaints", actor="research-conductor"):
    excerpt = (f"Interac acknowledges receipt of a merchant complaint within five business days, "
               f"case {n}, and writes its final decision within thirty business days.")
    return L.append_evidence(wb, source_name=f"Interac complaint page {n}", source_url=f"{url}/{n}",
                             tier="T2", excerpt=excerpt, subcaps=[cell] if isinstance(cell, str) else cell,
                             published="2026-01-01", actor=actor)


def _siblings(wb, n=3):
    caps = {}
    for c in wb.selected_subcaps():
        caps.setdefault(c.rsplit(".", 1)[0], []).append(c)
    return next(sorted(v)[:n] for _, v in sorted(caps.items()) if len(v) >= n)


def test_registration_is_not_refused_but_a_smeared_cell_cannot_be_synthesised(tmp_path):
    """Asked at the register the rule was order-dependent and refused the
    engine's own one-source-many-cells notes (5 suite failures); asked at the
    judgement — collection complete — it is the gate's own measurement."""
    run = _new_run(tmp_path / "r")
    wb = run.open()
    sibs = _siblings(wb)
    shared = _evidence(wb, sibs, 1)                # registers: one span, three siblings
    syn = {"Dominant_Claim": "Acme acknowledges complaints within five business days.",
           "Claim_Label": "HYPOTHESIS"}
    sm = L.smear_of_cell(wb, sibs[0])
    assert sm and set(sibs) <= set(sm["subcaps"]) and any(shared in x for x in sm["shared_evidence"])
    with pytest.raises(L.LedgerRefusal, match="evidence_smear"):
        L.append_synthesis(wb, sibs[0], syn, actor=f"research-{sibs[0][:4].lower()}-producer")
    # the remedy the refusal names: detach from the siblings it does not answer
    actor = f"research-{sibs[0][:4].lower()}-producer"
    for c in sibs[1:]:
        L.detach_evidence(wb, shared, c, reason="the span answers only the first sibling's question",
                          actor=actor)
    assert L.smear_of_cell(wb, sibs[0]) is None


def test_detach_undoes_an_upstream_citation_audited_and_conductor_only(tmp_path):
    run = _new_run(tmp_path / "r")
    wb = run.open()
    cell = _siblings(wb, 1)[0]
    e = _evidence(wb, cell, 4)
    with pytest.raises(L.LedgerRefusal, match="conducting tier"):
        L.detach_evidence(wb, e, cell, reason="does not answer this cell's question",
                          actor=f"research-{cell[:4].lower()}-collector")
    with pytest.raises(L.LedgerRefusal, match="conducting tier"):
        other = "p4c4" if not cell.upper().startswith("P4C4") else "p1c1"
        L.detach_evidence(wb, e, cell, reason="does not answer this cell's question",
                          actor=f"research-{other}-producer")
    with pytest.raises(L.LedgerRefusal, match="reason"):
        L.detach_evidence(wb, e, cell, reason="no", actor="research-conductor")
    out = L.detach_evidence(wb, e, cell, reason="a complaint SLA, not exception categorisation",
                            actor="research-conductor")
    assert e not in str(wb.scoring_row(cell).get("Evidence_IDs") or "")
    assert cell not in str(wb.evidence_index()[e].get("SubCap_IDs") or "")
    assert any(r.get("Step") == "detach" and e in str(r.get("Detail")) for r in wb.rows("Provenance"))
    assert out["detached"] == e
    with pytest.raises(L.LedgerRefusal, match="nothing to detach"):
        L.detach_evidence(wb, e, cell, reason="a complaint SLA, not exception categorisation",
                          actor="research-conductor")


def test_detach_refuses_while_the_synthesis_still_names_the_row(tmp_path):
    run = _new_run(tmp_path / "r")
    wb = run.open()
    cell = _siblings(wb, 1)[0]
    e = _evidence(wb, cell, 5)
    wb.set_scoring(cell, {"What_We_Found": f"Interac's complaint page ({e}) sets a five-day SLA."})
    with pytest.raises(L.LedgerRefusal, match="still names"):
        L.detach_evidence(wb, e, cell, reason="a complaint SLA, not exception categorisation",
                          actor="research-conductor")
