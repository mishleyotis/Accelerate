"""A mandatory sentiment family nobody searched is named before any page lane.

AAA WCNY (2026-10-15): CG-40 refused overview.sentiment on version B for 'app
stores' and 'Trustpilot or Google reviews' — families no search had touched —
after the page lanes were paid for.
"""
import json
from pathlib import Path

from engine import ledger as L
from engine import page_preflight as PP

from fixtures import new_run

REPO = Path(__file__).resolve().parents[3]


def test_the_vendored_families_equal_the_connectors():
    shared = json.loads((REPO / "packages/shared/contracts_data.json").read_text())
    vend = json.loads(PP._SENTIMENT_FAMILIES.read_text())
    assert vend["mandatory_families"] == shared["overview"]["sentiment"]["mandatory_families"]


def test_an_unsearched_family_blocks_the_overview_and_a_search_clears_it(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False, folder=False)
    wb = run.open()
    first = {b["detail"] for b in PP.sentiment_ladder(wb)}
    assert any("'Trustpilot or Google reviews'" in d for d in first)
    L.append_search(wb, subcap=[], facet="issues", query='site:trustpilot.com "Acme Credit Union"',
                    tool="evidence_engine", hits=0, kept=0,
                    outcome="Trustpilot: no listing — VERIFIED_ABSENT", prelim=True,
                    actor="enrichment-connector-specialist")
    after = {b["detail"] for b in PP.sentiment_ladder(run.open())}
    assert not any("'Trustpilot or Google reviews'" in d for d in after)
    assert all(b["severity"] == "block" for b in PP.sentiment_ladder(run.open()))


def test_the_check_runs_only_for_the_overview(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False, folder=False)
    sentiment = lambda bl: [b for b in bl if b["gate"] == "CG-40" and "sentiment family" in b["detail"]]
    assert not sentiment(PP.preflight(run.open(), pages=("techstack",)))
    assert sentiment(PP.preflight(run.open(), pages=("overview",)))
