"""Pack-fidelity: the heatmap grid snapshot must carry the durable per-subcap
synthesis so cold/pack-first serve renders the SynthesisDrawer's AI synthesis
(the live per-subcap endpoint is unreachable when the app serves the pack
first). These pin the pure merge helper `merge_subcap_synthesis` — the SHARED
twin in services.subcap_synthesis, consumed by both the exporter and the live
heatmap grid route — that folds `subcap_narratives` rows into `heatmap.json`'s
`narrative.per_subcap_md` + `per_subcap_meta`; the latter is what the
`heatmap_subcap_synthesis_clients` pack counter reads.
"""
from app.scripts.qa_coverage_contract import collect_heatmap_counters
from app.services.subcap_synthesis import (
    merge_subcap_synthesis as _merge_subcap_synthesis,
)


def test_merge_populates_narrative_from_scratch():
    body: dict = {"cells": [{"id": "P1C1.1.1"}], "narrative": None}
    _merge_subcap_synthesis(
        body,
        {"P1C1.1.1": "Digital Strategy scored 2.0 (M2). Grounding [E-043]: '...'"},
        {"P1C1.1.1": "heuristic"},
    )
    narr = body["narrative"]
    assert narr["per_subcap_md"]["P1C1.1.1"].startswith("Digital Strategy")
    assert narr["per_subcap_meta"]["P1C1.1.1"] == "heuristic"
    # And the pack counter now reads this client as carrying synthesis.
    got = collect_heatmap_counters({"heatmap": body})
    assert got["heatmap_subcap_synthesis_clients"] == (1.0, None)


def test_merge_preserves_section_routing_and_lets_narratives_win():
    # Existing section-routing narrative for one subcap; subcap_narratives
    # covers the same one (wins) plus a new one (added).
    body = {
        "narrative": {
            "per_subcap_md": {"P1C1.1.1": "report deep-dive text",
                              "P2C1.1.1": "untouched section-routing text"},
            "per_subcap_meta": {"P1C1.1.1": "heuristic"},
            "benchmark_md": "keep me",
        },
    }
    _merge_subcap_synthesis(
        body,
        {"P1C1.1.1": "durable synthesis", "P3C1.1.1": "new synthesis"},
        {"P1C1.1.1": "llm", "P3C1.1.1": "heuristic"},
    )
    md = body["narrative"]["per_subcap_md"]
    meta = body["narrative"]["per_subcap_meta"]
    # subcap_narratives authoritative for overlapping key
    assert md["P1C1.1.1"] == "durable synthesis"
    assert meta["P1C1.1.1"] == "llm"
    # section-routing-only key preserved
    assert md["P2C1.1.1"] == "untouched section-routing text"
    # new key added
    assert md["P3C1.1.1"] == "new synthesis"
    # sibling narrative fields untouched
    assert body["narrative"]["benchmark_md"] == "keep me"


def test_merge_is_a_noop_when_no_synthesis_rows():
    body = {"narrative": {"benchmark_md": "x"}}
    _merge_subcap_synthesis(body, {}, {})
    assert body["narrative"] == {"benchmark_md": "x"}
    # A client with no narratives keeps the counter at 0 (honest gap).
    assert collect_heatmap_counters({"heatmap": body})[
        "heatmap_subcap_synthesis_clients"] == (0.0, None)
