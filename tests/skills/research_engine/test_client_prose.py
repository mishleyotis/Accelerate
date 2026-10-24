"""The absence projector writes prose a CUSTOMER may read.

Build owner, 2026-10-07: "It is the customer view that lacks heatmap details
for most clients … Fix the evidence drawer too … Ensure no recurrence."
Measured on First Tech the same day: 63 of 619 cell drawers carried a
synthesis the serve layer deletes for the customer, because the projector
copied the research lane's search log into it ("three Exa queries returned…",
"Tavily returned HTTP 432 and was unusable", "NOT_RUN: web_search budget
exhausted"). The connector's CG-52 now refuses that at submit; this pins the
projector so an engine run never writes it in the first place, and pins the
packaged rule copy to the shared one so a Cowork install without a checkout
applies the same rule.
"""
from pathlib import Path

from engine import client_prose as P, ledger as L, surface_export as X
from fixtures import fire_volleys, new_run

REPO = Path(__file__).resolve().parents[3]


def test_the_packaged_rule_is_byte_identical_to_the_shared_one():
    shared = REPO / "packages" / "shared" / "internal_ids.py"
    packaged = REPO / "plugins" / "dma-insights" / "skills" / "dma-research" / "engine" / "data" / "internal_ids.py"
    assert packaged.read_bytes() == shared.read_bytes(), (
        "engine/data/internal_ids.py drifted from packages/shared/internal_ids.py — "
        "copy the shared file over it")


def test_a_search_log_absence_projects_without_a_pipeline_term(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fire_volleys(wb, cell, n=0)
    q = f'"Acme Credit Union" {cell} sustainability report'
    pq = f'"Acme Credit Union" {cell} proxy: ESG explainer'
    for query in (q, pq):
        L.append_search(wb, subcap=cell, facet="works", query=query, tool="exa",
                        hits=0, kept=0, outcome="no hits")
    L.declare_absence(
        wb, cell, actor="research-p1c1-producer",
        ladder=[{"rung": "direct", "query": q}, {"rung": "proxy", "query": pq}],
        what_was_hunted=("a materiality assessment; three Exa queries returned only the "
                         "2024 annual report, and Tavily returned HTTP 432 and was unusable"),
        proxy_log=("Counter-reading: NOT_RUN: web_search budget exhausted; only Exa "
                   "volleys ran and they found the 2022 ESG explainer"))
    out = X.absence_rows(wb, run=run)
    row = next(r for r in out["cells"] if r["subcap_id"] == cell)
    for key in ("synthesis", "closure_condition", "reach_note"):
        assert P.names_pipeline_term(row[key]) is None, (key, row[key])
    assert "2024 annual report" in row["synthesis"]
    assert "HTTP" not in row["synthesis"] and "budget" not in row["synthesis"]
    # the search record itself is kept, where no customer reads it
    assert any("via exa" in s.lower() for s in row["sources_searched"])
