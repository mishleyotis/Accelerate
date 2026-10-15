"""CG-COMPLETE at promote (AAA WCNY, 2026-10-15): deterministic, server-side,
for every promote path — the driver, a hand-driven agent, a Routine.

Arithmetic over the staged payloads, the package's peer_scores and the fit
engine over the WHOLE catalogue. Each test is the failing shape the owner saw
and the refusal it now gets."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _promote_fake import RUN  # noqa: E402
from dma_mcp import gates, promote_checks as PC  # noqa: E402


class _Cur:
    def __init__(self, peered=(), catalogue=(), vendors=()):
        self.peered, self.catalogue, self._rows = list(peered), list(catalogue), []
        self.vendors = list(vendors)

    def execute(self, sql, args=None):
        s = " ".join(sql.split())
        if "FROM peer_scores" in s:
            self._rows = [(c,) for c in self.peered]
        elif "SELECT DISTINCT p.vendor" in s:
            self._rows = [(v,) for v in self.vendors]
        elif "FROM ccg_l3_platforms" in s:
            self._rows = list(self.catalogue)
        else:
            self._rows = []

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur


CAT = [(f"L3-{i}", f"P{i}") for i in range(10)]


@pytest.fixture
def engine(monkeypatch):
    from dma_mcp import fit as fit_mod
    state = {"raise": None, "estate": {}}

    def platform_fit(conn, run_id, cands):
        if state["raise"]:
            raise state["raise"]
        return {"platforms": [{"platform": c["platform"], "rank": i + 1, "fit_score": 70 - i,
                               "state": "READY" if i < 7 else "INSUFFICIENT_EVIDENCE",
                               **state["estate"].get(c["platform"], {})}
                              for i, c in enumerate(cands)]}
    monkeypatch.setattr(fit_mod, "platform_fit", platform_fit)
    return state


def _live(tiles=5, cards=6, peer=1.5, cat_peer=1.4, order=None):
    cs = [{"platform": f"P{i}", "rank": i + 1, "fit_score": 70 - i} for i in range(cards)]
    ts = [{"platform": f"P{i}", "rank": i + 1, "composite": 70 - i} for i in (order or range(tiles))]
    return {
        "overview": {"payload": {"scores": {"pillars": [{"pillar_id": "P1", "peer_median": peer}]},
                                 "opportunity": {"tiles": ts}}},
        "heatmap": {"payload": {"workbook_scores": {
            "pillars": {"P1": {"peer_median": peer}},
            "categories": {"P1C1": {"peer_median": cat_peer}}}}},
        "platform": {"payload": {"platform_story": {"platforms": cs}}},
    }


def _run(live, peered=("P1C1",)):
    return PC.completeness(_Conn(_Cur(peered, CAT)), RUN, live)


def test_cg_complete_is_a_registered_blocking_gate():
    assert gates.GATES["CG-COMPLETE"][-1] == "block"


def test_a_complete_run_passes(engine):
    assert _run(_live()) == {}


def test_the_aaa_first_promotion_shape_is_refused(engine):
    """No peers served, two tiles, three cards — what reached the client."""
    out = _run(_live(tiles=2, cards=3, peer=None, cat_peer=None))
    msgs = [r["message"] for rs in out.values() for r in rs]
    assert all(r["gate_id"] == "CG-COMPLETE" and r["severity"] == "block"
               for rs in out.values() for r in rs)
    assert any("peer_median is null for P1" in m for m in out["overview"] for m in [m["message"]])
    assert any("P1C1" in r["path"] for r in out["heatmap"])
    assert any("2 tile(s)" in m for m in msgs)
    assert any("missing P3, P4" in m for m in msgs)


def test_tiles_out_of_card_rank_order_are_refused(engine):
    out = _run(_live(order=[1, 0, 2, 3, 4]))
    assert any("card-rank order" in r["message"] for r in out["overview"])


def test_a_null_peer_with_no_peer_table_is_not_refused(engine):
    """A category the package never scored is a stated absence, not a gap."""
    assert _run(_live(peer=None, cat_peer=None), peered=()) == {}


def test_a_fit_engine_failure_refuses_instead_of_skipping(engine):
    engine["raise"] = RuntimeError("down")
    out = _run(_live())
    assert out["overview"][0]["gate_id"] == "CG-COMPLETE"
    assert "unchecked, not complete" in out["overview"][0]["message"]


def test_it_runs_inside_every_promote_recheck(engine, monkeypatch):
    monkeypatch.setattr(PC, "refit", lambda *a: {})
    monkeypatch.setattr(PC, "gold_parity", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(PC, "_sub_vertical", lambda *a: None)
    merged, _ = PC.extra_reasons(_Conn(_Cur(("P1C1",), CAT)), RUN,
                                 _live(tiles=2, cards=3))
    assert any(r["gate_id"] == "CG-COMPLETE" for rs in merged.values() for r in rs)


# ── the estate: optimize what the client owns, never sell it back ──────────

def _estate_live(tiles, discarded=(), recs="", ctx="Verify the rollout first."):
    cs = [{"platform": f"P{i}", "rank": i + 1, "fit_score": 70 - i} for i in range(10)]
    return {
        "overview": {"payload": {"scores": {"pillars": []},
                                 "opportunity": {"tiles": [
                                     {"platform": f"P{i}", "rank": i + 1, "composite": 70 - i,
                                      "their_stack_context": ctx} for i in tiles],
                                     "discarded": [{"platform": d, "reason": "x"} for d in discarded]}}},
        "heatmap": {"payload": {}},
        "platform": {"payload": {"platform_story": {"platforms": cs},
                                 "recommendations": {"recommendations": [{"title": recs}]}}},
        "techstack": {"payload": {"techstack": {"items": [
            {"vendor": "Salesforce", "product": "Salesforce Sales Cloud", "status": "INFERRED"}]}}},
    }


def _estate_run(live, vendors=("Salesforce",)):
    return PC.completeness(_Conn(_Cur((), CAT, vendors)), RUN, live)


def test_a_platform_the_client_runs_is_never_a_tile(engine):
    engine["estate"] = {"P1": {"in_estate": "CLAIMED"}}
    out = _estate_run(_estate_live([0, 1, 2, 3, 4], recs="Salesforce org health check"))
    msgs = [r["message"] for r in out.get("overview", [])]
    assert any("already in the client's estate (CLAIMED)" in m for m in msgs)
    assert any("'P1' is in the client's estate" in m and "discarded" in m for m in msgs)


def test_a_replacement_is_discarded_not_tiled(engine):
    engine["estate"] = {"P2": {"replaces_in_estate": ["Power BI"]}}
    out = _estate_run(_estate_live([0, 1, 2, 3, 4], recs="Salesforce"))
    assert any("would replace Power BI" in r["message"] for r in out["overview"])


def test_an_extension_of_an_owned_org_must_say_verify(engine):
    engine["estate"] = {"P0": {"vendor_in_estate": "INFERRED"}}
    bad = _estate_run(_estate_live([0, 1, 2, 3, 4], recs="Salesforce", ctx="Extends the org."))
    assert any("verify its rollout" in r["message"] for r in bad["overview"])
    good = _estate_run(_estate_live([0, 1, 2, 3, 4], recs="Salesforce",
                                    ctx="Verify the FSC rollout and edition on the org first."))
    assert not [r for r in good.get("overview", []) if "verify" in r["message"]]


def test_every_owned_vendor_gets_an_optimization_recommendation(engine):
    out = _estate_run(_estate_live([0, 1, 2, 3, 4], recs="Tableau Pulse adoption"))
    assert any("already runs Salesforce" in r["message"] for r in out["platform"])
    ok = _estate_run(_estate_live([0, 1, 2, 3, 4], recs="Optimize the Salesforce org first"))
    assert "platform" not in ok


def test_the_tiles_skip_owned_cards_when_ranked(engine):
    engine["estate"] = {"P0": {"in_estate": "INFERRED"}}
    out = _estate_run(_estate_live([1, 2, 3, 4, 5], discarded=["P0"], recs="Salesforce"))
    assert not [r for r in out.get("overview", []) if "card-rank order" in r["message"]]


def test_selling_beside_an_owned_vendor_is_not_optimizing_it(engine):
    out = _estate_run(_estate_live([0, 1, 2, 3, 4], recs="Extend Salesforce with Service Cloud"))
    assert any("already runs Salesforce" in r["message"] for r in out["platform"])
