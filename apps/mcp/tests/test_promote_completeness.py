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
    def __init__(self, peered=(), catalogue=()):
        self.peered, self.catalogue, self._rows = list(peered), list(catalogue), []

    def execute(self, sql, args=None):
        s = " ".join(sql.split())
        if "FROM peer_scores" in s:
            self._rows = [(c,) for c in self.peered]
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
    state = {"raise": None}

    def platform_fit(conn, run_id, cands):
        if state["raise"]:
            raise state["raise"]
        return {"platforms": [{"platform": c["platform"], "rank": i + 1, "fit_score": 70 - i,
                               "state": "READY" if i < 7 else "INSUFFICIENT_EVIDENCE"}
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
