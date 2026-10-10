"""The enforcement sweep's rules hold without a network: a zero is verified
only against a control; an unrecognised page is NOT_RUN; the summary's
`verified` is the predicate the context page states."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "plugins" / "dma-insights" / "scripts" / "enforcement_search.py"
spec = importlib.util.spec_from_file_location("enforcement_search", SCRIPT)
ES = importlib.util.module_from_spec(spec)
sys.modules["enforcement_search"] = ES
spec.loader.exec_module(ES)


def test_a_zero_is_verified_only_when_the_control_found_orders():
    zero = ES.rung("CFPB", "Acme Bank", "VERIFIED_ABSENT", hits=0)
    assert ES.apply_control(zero, 0, "Wells Fargo")["outcome"] == "NOT_RUN"
    assert ES.apply_control(zero, None, "Wells Fargo")["outcome"] == "NOT_RUN"
    ok = ES.apply_control(zero, 12, "Wells Fargo")
    assert ok["outcome"] == "VERIFIED_ABSENT" and ok["control"] == {"name": "Wells Fargo", "hits": 12}


def test_a_hit_is_resolved_whatever_the_control_said():
    hit = ES.rung("CFPB", "Acme Bank", "RESOLVED", hits=2)
    assert ES.apply_control(hit, 0, "Wells Fargo")["outcome"] == "RESOLVED"


def test_not_run_needs_a_reason_and_outcomes_are_closed():
    with pytest.raises(ValueError):
        ES.rung("x", "y", "NOT_RUN")
    with pytest.raises(ValueError):
        ES.rung("x", "y", "CLEAN")


def test_cfpb_page_shapes():
    assert ES.cfpb_count('<article class="o-post-preview">a</article><article class="o-post-preview">b</article>') == 2
    assert ES.cfpb_count('<p>Showing 14 results</p><div class="o-post-preview"></div>') == 14
    assert ES.cfpb_count("<p>No results found for your search.</p>") == 0
    assert ES.cfpb_count("<html><body>maintenance</body></html>") is None, "unknown shape is NOT zero"


def test_the_summary_predicate_matches_the_context_contract():
    rungs = [ES.rung("a", "q", "VERIFIED_ABSENT", hits=0), ES.rung("b", "q", "VERIFIED_ABSENT", hits=0)]
    s = ES.summarise(rungs, names=["q"])
    assert s["verified"] and not s["actions_found"]
    s = ES.summarise(rungs + [ES.rung("c", "q", "NOT_RUN", reason="HTTP 403 from the registry")], names=["q"])
    assert not s["verified"], "a rung that did not complete is not a verified absence"
    s = ES.summarise(rungs + [ES.rung("c", "q", "RESOLVED", hits=1)], names=["q"])
    assert s["actions_found"] and not s["verified"]
    assert not ES.summarise([], names=["q"])["verified"]


def test_an_unconfigured_state_is_a_named_not_run_rung(monkeypatch):
    monkeypatch.setattr(ES, "cfpb_rung", lambda n: ES.rung("CFPB", n, "VERIFIED_ABSENT", hits=0))
    monkeypatch.setattr(ES, "run_browser_steps", lambda steps: [
        {"id": s["id"], "ok": True, "rows": 3 if s["id"].endswith(":control") else 0, "no_results": True}
        for s in steps])
    doc = ES.sweep(["Acme Bank"], cert="", state="ZZ", with_controls=True)
    kinds = {(r["source"], r["outcome"]) for r in doc["sources_searched"]}
    assert ("ZZ state banking department orders", "NOT_RUN") in kinds
    assert not doc["verified"]
    # the FDIC name rung was controlled and came back verified
    assert any(r["outcome"] == "VERIFIED_ABSENT" and r["source"].startswith("FDIC") for r in doc["sources_searched"])


def test_a_browser_that_cannot_run_is_not_run_per_rung(monkeypatch):
    monkeypatch.setattr(ES, "cfpb_rung", lambda n: ES.rung("CFPB", n, "VERIFIED_ABSENT", hits=0))
    monkeypatch.setattr(ES, "PW_CORE", "/nonexistent/playwright-core")
    doc = ES.sweep(["Acme Bank"], cert="123", state="NE", with_controls=False)
    fdic = [r for r in doc["sources_searched"] if r["source"].startswith("FDIC")]
    assert fdic and all(r["outcome"] == "NOT_RUN" and "playwright-core" in r["reason"] for r in fdic)
