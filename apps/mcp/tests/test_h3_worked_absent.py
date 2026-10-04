"""CG-40b — a WORKED_ABSENT alert shows the ladder that worked it.

RC-05 (SWBC gold audit, 2026-10-04; slice HM-05). The H3 contract defines
WORKED_ABSENT as "the ladder ran across all mandatory sources and found
nothing — a FINDING about the client", and says "LOG EVERY QUERY". SWBC
promoted 190 WORKED_ABSENT alerts; 87 had `queries_run: []`, and every one
carried a mandatory connector tier recorded as NOT_RUN. A finding about the
client with no query behind it is an assertion.

Refused: WORKED_ABSENT with an empty queries_run, or with a rung whose outcome
is open (NOT_RUN, not fetched, BLOCKED) and no failover recorded. A NOT_RUN
tier whose failover ran is complete — owner default 2026-10-04: WebSearch /
WebFetch is an acceptable failover when Exa/Tavily credit is exhausted.

Not enforced here (left open, see residuals): the tier-10 CONTRADICTORY query
"at least one per cell" — it would refuse the Baxter and Logix gold runs,
whose WORKED_ABSENT alerts log no contradictory probe, and needs an owner call.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import _check_worked_absent_ladder as check  # noqa: E402


def _alert(**kw):
    a = {"subcap_id": "P1C1.2.1", "state": "WORKED_ABSENT",
         "queries_run": ["SWBC multi-year digital roadmap 2026"],
         "sources_searched": [
             "Package evidence index for 'Multi-Year Roadmap' — RESOLVED: one "
             "row, not a roadmap",
             "Web search 'SWBC digital roadmap' — VERIFIED ABSENT"],
         "closure_condition": "A multi-year digital roadmap."}
    a.update(kw)
    return a


def _run(*alerts):
    return check("heatmap", {"alerts": {"alerts": list(alerts)}})


def test_worked_absent_with_no_queries_is_refused():
    out = _run(_alert(queries_run=[]))
    assert len(out) == 1
    assert out[0]["gate_id"] == "CG-40b"
    assert out[0]["path"] == "alerts.alerts[0].queries_run"


def test_a_not_run_tier_without_failover_is_refused():
    out = _run(_alert(sources_searched=[
        "Web search 'SWBC roadmap' — VERIFIED ABSENT",
        "Exa/Tavily/Firecrawl connector rung: NOT_RUN — credit exhausted"]))
    assert len(out) == 1 and "NOT_RUN" in out[0]["message"]


def test_a_not_run_tier_with_its_failover_passes():
    assert _run(_alert(sources_searched=[
        "Web search 'SWBC roadmap' — VERIFIED ABSENT",
        "Exa/Tavily/Firecrawl connector rung: NOT_RUN — credit exhausted "
        "(2026-10-01); built-in web search ran in its place: VERIFIED ABSENT"])
    ) == []


def test_a_worked_ladder_passes_and_other_states_are_untouched():
    assert _run(_alert()) == []
    assert _run(_alert(state="UNWORKED", queries_run=[])) == []
    assert _run(_alert(state="WORKED_FOUND", queries_run=[])) == []


def test_only_the_heatmap_page_is_read():
    assert check("overview", {"alerts": {"alerts": [_alert(queries_run=[])]}}) \
        == []
