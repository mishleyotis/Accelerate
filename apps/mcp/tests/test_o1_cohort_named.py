"""O1 names the cohort whenever one exists, even with cannot_estimate
(SWBC gold audit 2026-10-04, RC-10(c)(d); D-17).

SWBC's overview.scores pillars carried peer_basis cannot_estimate and the
proxy_disclosure "The comparison organisations identified for this
assessment were not scored against the same cells" — naming none of the
three identified peers. The null was earned (owner decision: peers not
scored); the stated reason never named who. Owner default 2026-10-04: the
identified peers may be named to the customer as "identified, not scored".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import peer_set as PS          # noqa: E402

PEERS = {"assurant": "Assurant", "fortegra": "Fortegra", "trustage": "TruStage"}
SWBC_DISCLOSURE = ("No peer comparison is shown for this pillar. The comparison "
                   "organisations identified for this assessment were not scored "
                   "against the same cells, so no like-for-like median exists and "
                   "none is estimated.")


def scores(disclosure, basis="cannot_estimate", median=None):
    return {"scores": {"composite": 2.01, "pillars": [
        {"pillar_id": f"P{i}", "score": 2.0, "peer_median": median,
         "peer_basis": basis, "proxy_disclosure": disclosure} for i in range(1, 5)]}}


def test_swbc_disclosure_naming_no_peer_is_refused():
    out = PS.o1_cohort_findings("overview", scores(SWBC_DISCLOSURE), PEERS)
    assert out and out[0]["gate_id"] == "CG-44"
    assert "Assurant" in out[0]["message"]
    assert out[0]["path"] == "scores.pillars[].proxy_disclosure"


def test_naming_the_cohort_identified_not_scored_passes():
    d = ("Assurant, Fortegra and TruStage were identified, not scored, so no "
         "like-for-like median exists for this pillar.")
    assert PS.o1_cohort_findings("overview", scores(d), PEERS) == []


def test_a_null_peer_basis_on_an_identified_set_is_refused():
    d = "Assurant, Fortegra and TruStage were identified, not scored."
    out = PS.o1_cohort_findings("overview", scores(d, basis=None), PEERS)
    assert out and "cannot_estimate" in out[0]["message"]


def test_a_pillar_with_a_median_needs_no_disclosure():
    assert PS.o1_cohort_findings("overview", scores("", median=2.5), PEERS) == []


def test_no_identified_set_is_silent():
    assert PS.o1_cohort_findings("overview", scores(SWBC_DISCLOSURE), {}) == []


def test_map_shaped_pillars_are_read_too():
    body = {"scores": {"pillars": {"P1": {"peer_median": None,
                                          "peer_basis": "cannot_estimate",
                                          "proxy_disclosure": SWBC_DISCLOSURE}}}}
    assert PS.o1_cohort_findings("overview", body, PEERS)
