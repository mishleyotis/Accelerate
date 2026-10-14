"""PRELIM accounts for Enrichment_Needed before it signs off.

AAA Western and Central New York (2026-10-14): the connector had never seen
the client (`get_client_state` → unknown_entity), so `seed-enrichment` rightly
wrote no row — and nothing else accounted for the tab. PRELIM closed, sixteen
categories researched and four pillars scored, and the HANDOFF completeness
check then refused the empty tab, after the money was spent.
`prelim.complete` now refuses an Enrichment_Needed that is empty and
undeclared, and the driver raises that as a PRELIM stage failure.
"""
from pathlib import Path

import pytest

from engine import completeness, prelim

from fixtures import close_prelim, new_run

REPO = Path(__file__).resolve().parents[3]


def _unseeded(monkeypatch, run):
    monkeypatch.setattr(prelim, "seed_enrichment", lambda *a, **k: None)
    with pytest.raises(prelim.PrelimRefusal, match="Enrichment_Needed empty"):
        close_prelim(run)
    monkeypatch.undo()


def test_prelim_refuses_an_empty_undeclared_enrichment_tab(tmp_path, monkeypatch):
    run = new_run(tmp_path, prelim=False)
    _unseeded(monkeypatch, run)
    wb = run.open()
    assert wb.metadata().get("prelim_status") != "COMPLETE"
    assert not prelim.state(wb)["open"]          # every section closed …
    owed = prelim.enrichment_owed(wb)            # … and still refused, by name
    assert "new client" in owed and "completeness declare" in owed


def test_a_new_client_seeds_nothing_and_signs_off_once_declared(tmp_path, monkeypatch):
    run = new_run(tmp_path, prelim=False)
    _unseeded(monkeypatch, run)
    out = prelim.seed_enrichment(run.open(), {"error": "unknown_entity"})
    assert out["rows_added"] == []
    with pytest.raises(prelim.PrelimRefusal, match="Enrichment_Needed"):
        prelim.complete(run.open())
    completeness.declare(
        run.open(), "Enrichment_Needed",
        "new client: get_client_state answered unknown_entity with no "
        "did_you_mean, so the connector holds no facet state or staged gaps")
    prelim.complete(run.open())
    assert run.open().metadata()["prelim_status"] == "COMPLETE"


def test_seeded_rows_sign_off(tmp_path, monkeypatch):
    run = new_run(tmp_path, prelim=False)
    _unseeded(monkeypatch, run)
    prelim.seed_enrichment(run.open(), {"enrichment": {"facets": [
        {"facet": "leadership", "state": "never_enriched"}]}})
    prelim.complete(run.open())
    assert run.open().metadata()["prelim_status"] == "COMPLETE"


def test_the_driver_turns_the_refusal_into_a_prelim_stage_failure():
    src = (REPO / "plugins/dma-insights/skills/dma-research/engine/pipeline.py"
           ).read_text(encoding="utf-8")
    i = src.index("prelim.complete(self.wb)")
    window = src[i - 200:i + 400]
    assert "except prelim.PrelimRefusal" in window
    assert "StageRefused" in window
