"""CG-30 — the fit on the card is the fit the engine computed.

Reported 2026-08-19: "Platform fit scores calculation is very different from
Baxter's." Four definitions of one number were in play. The contract's rule
has always been that the producer EXPLAINS the fit and never recomputes or
re-ranks it; there was no engine to read from, so nothing could enforce it.

These cases pin the enforcement, including the two failure modes that are not
a wrong number: a card with no score at all, and a correct score in the wrong
order.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from dma_mcp import validation2 as V  # noqa: E402

CHECK = V._check_platform_fit_is_the_engine_s


def page(*platforms):
    return {"platform_story": {"platforms": list(platforms)}}




def test_another_page_is_not_this_gate_s_business():
    assert CHECK(None, "run", "overview", page({"platform": "X"})) == []


def test_a_section_with_no_platforms_is_not_a_violation():
    """An absent section is CG-01's business. Two gates refusing one payload
    for the same reason sends a producer to the wrong field."""
    assert CHECK(None, "run", "platform", {"platform_story": {}}) == []
    assert CHECK(None, "run", "platform", {}) == []




def test_an_engine_that_cannot_run_is_a_refusal_not_a_pass():
    """This module's whole subject is checks that report clean because they
    never ran. `conn=None` makes the engine raise; the gate must say so."""
    out = CHECK(None, "run", "platform", page({"platform": "X", "fit_score": 70.0}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "refusal, not a pass" in out[0]["message"]


class _Cur:
    """The four reads `fit.platform_fit` makes, answered from fixtures."""

    def __init__(self, cells):
        self.cells, self._rows = cells, []

    def execute(self, sql, args=None):
        if "FROM runs WHERE id" in sql:
            self._rows = [("run",)]
        elif "FROM subcap_scores" in sql:
            self._rows = [(sid, sc, cat, None, [area])
                          for sid, sc, cat, area in self.cells]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur


CELLS = [("P1C1.1.1", 2.0, "P1C1", "integration"),
         ("P1C1.1.2", 1.5, "P1C1", "integration")]


def test_a_card_with_no_fit_score_the_engine_can_score_is_refused():
    """Five nulls is exactly what the reported client shipped. A platform page
    whose cards cannot be ranked is not a ranking — and the refusal quotes the
    number the engine had ready, so the resubmission is a read, not a guess."""
    wide = CELLS + [("P1C1.1.3", 1.0, "P1C1", "integration")]
    out = CHECK(_Conn(_Cur(wide)), "run", "platform",
                page({"platform": "MuleSoft", "l3_area": "Integration",
                      "fit_score": None, "alignment": 0.5,
                      "readiness": "green"}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "read the number" in out[0]["message"].lower()
    assert "state" in out[0]["message"]  # names what it computed


def test_the_gate_names_a_handful_not_a_wall():
    out = CHECK(_Conn(_Cur(CELLS)), "run", "platform",
                page(*[{"platform": f"P{i}", "l3_area": "Integration",
                        "fit_score": None} for i in range(20)]))
    assert 0 < len(out) <= 6


def test_a_score_the_engine_did_not_produce_is_refused():
    conn = _Conn(_Cur(CELLS))
    out = CHECK(conn, "run", "platform",
                page({"platform": "MuleSoft", "l3_area": "Integration",
                      "fit_score": 91.4, "alignment": 0.5, "readiness": "green"}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "the engine computes" in out[0]["message"]


def test_the_engine_s_own_number_passes():
    conn = _Conn(_Cur(CELLS))
    from dma_mcp import fit as fit_mod
    got = fit_mod.platform_fit(_Conn(_Cur(CELLS)), "run", [
        {"platform": "MuleSoft", "l3_area": "Integration",
         "alignment": 0.5, "readiness": "green"}])["platforms"][0]
    out = CHECK(conn, "run", "platform",
                page({"platform": "MuleSoft", "l3_area": "Integration",
                      "fit_score": got["fit_score"], "rank": got["rank"],
                      "alignment": 0.5, "readiness": "green"}))
    assert out == [], out


def test_a_correct_score_in_the_wrong_order_is_still_refused():
    """The reader takes the top card as the recommendation, so the ordering
    is the claim — not a presentation detail."""
    from dma_mcp import fit as fit_mod
    got = fit_mod.platform_fit(_Conn(_Cur(CELLS)), "run", [
        {"platform": "MuleSoft", "l3_area": "Integration",
         "alignment": 0.5, "readiness": "green"}])["platforms"][0]
    out = CHECK(_Conn(_Cur(CELLS)), "run", "platform",
                page({"platform": "MuleSoft", "l3_area": "Integration",
                      "fit_score": got["fit_score"], "rank": 3,
                      "alignment": 0.5, "readiness": "green"}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "wrong order" in out[0]["message"]


def test_the_refusal_carries_the_basis_that_explains_the_right_number():
    """A producer told only "that is wrong" resubmits a guess."""
    out = CHECK(_Conn(_Cur(CELLS)), "run", "platform",
                page({"platform": "MuleSoft", "l3_area": "Integration",
                      "fit_score": 91.4, "alignment": 0.5, "readiness": "green"}))
    assert "multiplier" in out[0]["message"]


def test_an_area_that_reaches_no_cell_is_named_rather_than_scored_silently():
    from dma_mcp import fit as fit_mod
    got = fit_mod.platform_fit(_Conn(_Cur(CELLS)), "run", [
        {"platform": "Nowhere", "l3_area": "Nothing here", "alignment": 0.5}])
    assert got["unmatched"] and got["unmatched"][0]["platform"] == "Nowhere"


# ── the two shapes the corpus actually writes ──────────────────────────

def test_an_area_matches_on_its_catalogue_code():
    """`[L3-SF-DC-CORE] Data Cloud (count: 3)` is one real catalogue value.
    The label drifts — a producer writes "Data Cloud", the catalogue writes
    "Salesforce Data Cloud" — and the "(count: N)" suffix is a vote tally
    welded onto it. The code is the stable half."""
    from dma_mcp.fit import _norm_area
    assert _norm_area("[L3-SF-DC-CORE] Data Cloud") == "L3-SF-DC-CORE"
    assert _norm_area("[L3-SF-DC-CORE] Salesforce Data Cloud (count: 3)") \
        == "L3-SF-DC-CORE"
    assert _norm_area("[l3-sf-dc-core] whatever") == "L3-SF-DC-CORE"


def test_an_area_with_no_code_falls_back_to_its_cleaned_label():
    from dma_mcp.fit import _norm_area
    assert _norm_area("  Salesforce   Data Cloud (count: 9) ") \
        == "salesforce data cloud"


def test_the_readiness_verdict_phrase_is_understood():
    """A producer states readiness as the page's own verdict, not as a
    traffic light: "READY WITH CONDITIONS" is what one promoted card says."""
    from dma_mcp.fit import _readiness_token
    assert _readiness_token({"verdict": "READY WITH CONDITIONS"}) == "amber"
    assert _readiness_token("READY") == "green"
    assert _readiness_token({"verdict": "NOT READY"}) == "red"


def test_an_unmapped_readiness_phrase_is_red_not_green():
    """The multiplier is a SAFETY property. Guessing green on a phrase nobody
    mapped is how a red platform renders hot — the defect the multiplicative
    shape was chosen to make impossible."""
    from dma_mcp.fit import _readiness_token
    assert _readiness_token("mostly fine probably") == "red"
    assert _readiness_token({"verdict": "SOMEWHAT READY"}) == "red"


def test_an_absent_readiness_is_green_because_nothing_was_claimed():
    """Distinct from an unmapped one: a card that states no readiness has
    made no claim to contradict, and penalising silence would push producers
    to write green rather than to check."""
    from dma_mcp.fit import _readiness_token
    assert _readiness_token(None) == "green"


# ── an empty register is unmeasured, not neutral ───────────────────────

class _CtxCur(_Cur):
    """Adds the two raw registers, so a test can make them empty on purpose."""

    def __init__(self, cells, issues=None, stack=None, sub="CU"):
        super().__init__(cells)
        self.issues, self.stack, self.sub = issues or [], stack or [], sub

    def execute(self, sql, args=None):
        if "FROM entities" in sql or "e.sub_vertical" in sql:
            self._rows = [(self.sub,)]
        elif "issue_register_raw" in sql:
            self._rows = [(p,) for p in self.issues]
        elif "techstack_raw" in sql:
            self._rows = [(p,) for p in self.stack]
        elif "evidence_subcap_links" in sql:
            self._rows = []
        else:
            super().execute(sql, args)


def test_an_empty_issue_register_is_reported_not_silently_neutral():
    """Both raw registers are EMPTY on a promoted run. With no issues every
    cell falls to the neutral severity weight, and returning the scores
    without saying so is a term that could not run reading as a term that ran
    and found nothing."""
    from dma_mcp import fit as fit_mod
    got = fit_mod.platform_fit(_Conn(_CtxCur(CELLS)), "run", [
        {"platform": "MuleSoft", "l3_area": "Integration", "alignment": 0.5}])
    notes = " ".join(got["context"]["notes"])
    assert got["context"]["issue_rows"] == 0
    assert "issue register is empty" in notes
    assert "flat because nothing was linked" in notes


def test_an_empty_technology_register_says_zero_means_unmeasured():
    from dma_mcp import fit as fit_mod
    got = fit_mod.platform_fit(_Conn(_CtxCur(CELLS)), "run", [
        {"platform": "MuleSoft", "l3_area": "Integration", "alignment": 0.5}])
    assert "zero here means unmeasured" in " ".join(got["context"]["notes"])


def test_the_context_counts_what_the_engine_actually_read():
    from dma_mcp import fit as fit_mod
    got = fit_mod.platform_fit(_Conn(_CtxCur(CELLS)), "run", [
        {"platform": "MuleSoft", "l3_area": "Integration", "alignment": 0.5}])
    ctx = got["context"]
    assert ctx["cells_scored"] == len(CELLS)
    assert ctx["cells_with_citable_evidence"] == 0
    assert ctx["entity_subvertical_code"] == "CU"


# ── the honest null, and the inputs the gate must not drop ─────────────

def _mlflow_ranked(depends_on=None):
    card = {"platform": "MuleSoft", "l3_area": "Integration",
            "alignment": 0.5, "readiness": "green"}
    if depends_on is not None:
        card["depends_on"] = depends_on
    return card


def test_a_null_fit_is_honest_when_the_engine_itself_cannot_rank_it():
    """TOO_NARROW is the engine's own verdict for an area binding fewer than
    MIN_CELLS cells. A null with that state on the card renders as "not
    scored: too narrow to rank"; a 0.0 would render as the worst platform on
    the page — a sentinel that looks like data (invariant 9)."""
    out = CHECK(_Conn(_Cur(CELLS)), "run", "platform",
                page({"platform": "Nowhere", "l3_area": "Nothing here",
                      "fit_score": None, "state": "TOO_NARROW"}))
    assert out == [], out


def test_a_null_fit_without_the_engine_s_state_is_refused():
    out = CHECK(_Conn(_Cur(CELLS)), "run", "platform",
                page({"platform": "Nowhere", "l3_area": "Nothing here",
                      "fit_score": None}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "state" in out[0]["message"]


def test_a_null_fit_with_a_state_the_engine_did_not_give_is_refused():
    out = CHECK(_Conn(_Cur(CELLS)), "run", "platform",
                page({"platform": "Nowhere", "l3_area": "Nothing here",
                      "fit_score": None, "state": "INSUFFICIENT_EVIDENCE"}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "TOO_NARROW" in out[0]["message"]


def test_depends_on_reaches_the_engine_so_its_own_ordering_passes():
    """The engine refuses to rank a card above something it depends on. A
    gate that dropped `depends_on` would refuse a producer for shipping the
    engine's own ranks — the workload-above-foundation defect, reintroduced
    by the check meant to prevent it."""
    from dma_mcp import fit as fit_mod
    two = [("P1C1.1.1", 2.0, "P1C1", "integration"),
           ("P1C1.1.2", 1.5, "P1C1", "integration"),
           ("P1C1.2.1", 1.0, "P1C1", "workload"),
           ("P1C1.2.2", 1.0, "P1C1", "workload"),
           ("P1C1.2.3", 1.0, "P1C1", "workload")]
    cands = [
        {"platform": "Foundation", "l3_area": "Integration",
         "alignment": 0.2, "readiness": "green"},
        {"platform": "Workload", "l3_area": "workload",
         "alignment": 0.9, "readiness": "green",
         "depends_on": ["Foundation"]},
    ]
    got = fit_mod.platform_fit(_Conn(_Cur(two)), "run", cands)["platforms"]
    by = {p["platform"]: p for p in got}
    # the premise of the case: on raw fit the workload would lead
    assert by["Workload"]["fit_score"] >= by["Foundation"]["fit_score"]
    assert by["Foundation"]["rank"] < by["Workload"]["rank"]
    cards = []
    for c in cands:
        r = by[c["platform"]]
        cards.append({**c, "fit_score": r["fit_score"], "rank": r["rank"]})
    out = CHECK(_Conn(_Cur(two)), "run", "platform", page(*cards))
    assert out == [], out
