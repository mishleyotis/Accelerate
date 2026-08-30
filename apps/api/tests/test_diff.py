"""The run-to-run diff — the read that makes a rerun visible.

What is asserted, in order of what would have shipped a lie:

1. With one promoted run there is NO diff — an explicit `no_base_run` state
   and zero cells. The prototype's base was `score - 0.2 - charCode % 5 / 12`;
   nothing here may produce a base from the target by any route.
2. Every number is subtraction over two promoted scores. Nothing weights,
   ranks or re-derives, and the composite delta comes from the two promoted
   composites rather than from a mean of the compared subset.
3. Across a catalogue bump, a renamed cell resolves through `ccg_aliases`
   (read, never inferred) and a cell that exists in only one version is
   NOT_COMPARABLE with a named reason and counts toward no movement figure —
   Baxter's served run is pinned to v5.0 while v7.0 is current, so the first
   genuine rerun crosses exactly this boundary.
4. Order is stable: largest movement first, cell id breaking ties.

Fake cursor, per the suite's style; no live DB.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.diff import NOT_COMPARABLE, build_diff        # noqa: E402
from dma_api.pages import ApiError                          # noqa: E402

R1 = "c1351d25-a612-4dbe-b498-127bccaf6810"
R2 = "2af3a5bc-8a0d-4bc2-828a-a8d38e9304ce"
ENTITY = "22222222-2222-2222-2222-222222222222"


def _dir_row(run_id, run_seq, version, composite, active):
    """A serving_directory row in the two column orders this module reads:
    resolve_run's twenty-one, and _pick_runs' twelve."""
    return {"run_id": run_id, "run_seq": run_seq, "version": version,
            "composite": composite, "active": active}


def _cell(subcap_id, score, cat="P1C1", pillar="P1", ev=4, thin=False,
          name=None, cap=None):
    return (subcap_id, cap or subcap_id.rsplit(".", 1)[0], cat, pillar,
            name or f"cell {subcap_id}", score, "HIGH", ev, thin)


class _Conn:
    def __init__(self, runs, cells, aliases=(), catalogue=None):
        self.runs = list(runs)
        self.cells = dict(cells)          # run_id -> [row tuples]
        self.aliases = list(aliases)      # (from, to, reason)
        self.catalogue = catalogue or {}  # version -> {subcap_id}
        self.statements = []
        self._out = []

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.statements.append((sql, list(params or [])))
        p = list(params or [])
        if "FROM serving_directory" in sql and "assessment_date_source" in sql:
            # resolve_run's twenty-one columns
            self._out = [
                (ENTITY, "baxter-credit-union-bcu", "Baxter Credit Union (BCU)",
                 "SV2", None, r["run_id"], f"REQ-{r['run_seq']}", r["run_seq"],
                 r["active"], "PROMOTED", r["composite"], 765, 836, r["version"],
                 datetime(2026, 3, 30, tzinfo=timezone.utc),
                 datetime(2026, 8, 8, tzinfo=timezone.utc),
                 None, "DERIVED_REQUEST_ID_TOKEN", "manifest.run_id", None,
                 None)                              # entity_domain (0045)
                for r in self.runs]
            self._out.sort(key=lambda r: (not r[8],))
        elif "FROM serving_directory" in sql:
            # _pick_runs' twelve columns
            self._out = sorted(
                [(r["run_id"], f"REQ-{r['run_seq']}", r["run_seq"], r["active"],
                  datetime(2026, 8, 8, tzinfo=timezone.utc),
                  datetime(2026, 3, 30, tzinfo=timezone.utc), r["version"],
                  r["composite"], 765, None, "DERIVED_REQUEST_ID_TOKEN", None)
                 for r in self.runs],
                key=lambda r: -(r[2] or 0))
        elif "FROM serving_subcaps" in sql:
            self._out = list(self.cells.get(p[0], []))
        elif "FROM ccg_aliases" in sql:
            self._out = list(self.aliases)
        elif "FROM ccg_subcaps" in sql:
            self._out = [(c,) for c in sorted(self.catalogue.get(p[0], ()))]
        else:                                          # pragma: no cover
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchall(self):
        return self._out

    def fetchone(self):
        return self._out[0] if self._out else None


# ── one run is not a diff ──────────────────────────────────────────────
def test_one_promoted_run_yields_no_diff_and_says_so():
    conn = _Conn([_dir_row(R1, 1, "v5.0", 2.71, True)],
                 {R1: [_cell("P1C1.1", 3.0)]})
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    assert body["comparable"] is False
    assert body["cells"] == []
    assert body["base"] is None
    assert body["summary"] is None
    assert body["empty_state"]["kind"] == "no_base_run"
    assert body["empty_state"]["promoted_runs"] == 1
    assert "never derived" in body["empty_state"]["reason"]


def test_a_base_is_never_synthesised_from_the_target():
    """The prototype's `score - 0.2 - charCode % 5 / 12`. With one run the
    target's own cells must not appear as anybody's base."""
    conn = _Conn([_dir_row(R1, 1, "v5.0", 2.71, True)],
                 {R1: [_cell("P1C1.1", 3.0), _cell("P1C1.2", 2.0)]})
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    blob = repr(body)
    assert "base_score" not in blob
    assert body["cells"] == [] and body["base"] is None


# ── two runs, same catalogue ───────────────────────────────────────────
def _two_runs(base_cells, target_cells, base_version="v7.0",
              target_version="v7.0", aliases=(), catalogue=None,
              base_composite=2.50, target_composite=2.71):
    return _Conn(
        [_dir_row(R2, 2, target_version, target_composite, True),
         _dir_row(R1, 1, base_version, base_composite, False)],
        {R1: base_cells, R2: target_cells}, aliases=aliases,
        catalogue=catalogue)


def test_the_delta_is_subtraction_over_two_promoted_scores():
    conn = _two_runs([_cell("P1C1.1", 2.0), _cell("P1C1.2", 3.0),
                      _cell("P1C1.3", 2.5)],
                     [_cell("P1C1.1", 3.0), _cell("P1C1.2", 2.5),
                      _cell("P1C1.3", 2.5)])
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    assert body["comparable"] is True
    by_id = {c["subcap_id"]: c for c in body["cells"]}
    assert by_id["P1C1.1"]["delta"] == 1.0
    assert by_id["P1C1.2"]["delta"] == -0.5
    assert by_id["P1C1.3"]["delta"] == 0.0
    assert by_id["P1C1.1"]["base_score"] == 2.0
    assert by_id["P1C1.1"]["target_score"] == 3.0
    s = body["summary"]
    assert (s["compared"], s["moved"], s["improved"], s["declined"],
            s["unchanged"]) == (3, 2, 1, 1, 1)


def test_the_composite_delta_is_the_two_promoted_composites():
    """Not a mean of the compared subset: a mean of 3 of 765 cells is not the
    run's composite, and printing one as the other invites the reader to
    treat them as the same number."""
    conn = _two_runs([_cell("P1C1.1", 1.0)], [_cell("P1C1.1", 5.0)],
                     base_composite=2.50, target_composite=2.71)
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    assert body["summary"]["base_composite"] == 2.50
    assert body["summary"]["target_composite"] == 2.71
    assert body["summary"]["composite_delta"] == 0.21


def test_a_missing_composite_gives_a_null_delta_not_a_zero():
    conn = _two_runs([_cell("P1C1.1", 1.0)], [_cell("P1C1.1", 2.0)],
                     base_composite=None)
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    assert body["summary"]["composite_delta"] is None


def test_largest_movement_first_and_the_order_is_stable():
    conn = _two_runs(
        [_cell("P1C1.3", 2.0), _cell("P1C1.1", 2.0), _cell("P1C1.2", 2.0)],
        [_cell("P1C1.3", 2.1), _cell("P1C1.1", 1.0), _cell("P1C1.2", 3.0)])
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    assert [c["subcap_id"] for c in body["cells"]] == \
        ["P1C1.1", "P1C1.2", "P1C1.3"]
    again = build_diff(_Conn(conn.runs, conn.cells).cursor(),
                       "baxter-credit-union-bcu")
    assert [c["subcap_id"] for c in again["cells"]] == \
        [c["subcap_id"] for c in body["cells"]]


def test_a_cell_with_no_score_on_one_side_is_not_comparable_not_a_delta():
    conn = _two_runs([_cell("P1C1.1", None)], [_cell("P1C1.1", 3.0)])
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    assert body["cells"] == []
    assert body["not_comparable"][0]["reason"] == "SCORE_MISSING_ON_BASE"
    assert body["not_comparable"][0]["reason"] in NOT_COMPARABLE
    assert body["summary"]["compared"] == 0
    assert body["summary"]["not_comparable"] == 1


# ── across a catalogue bump ────────────────────────────────────────────
def test_a_renamed_cell_resolves_through_the_catalogue_s_own_alias_bridge():
    conn = _two_runs(
        [_cell("P1C1.9", 2.0)], [_cell("P1C1.9b", 3.0)],
        base_version="v5.0", target_version="v7.0",
        aliases=[("P1C1.9", "P1C1.9b", "renamed")],
        catalogue={"v5.0": {"P1C1.9"}, "v7.0": {"P1C1.9b"}})
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    cell = body["cells"][0]
    assert cell["bridged"] == {"from": "P1C1.9", "to": "P1C1.9b",
                               "reason": "renamed"}
    assert cell["delta"] == 1.0
    assert body["catalogue"]["crossed_a_bump"] is True
    assert body["catalogue"]["bridged_cells"] == 1


def test_a_killed_category_is_not_comparable_and_counts_toward_nothing():
    """All 31 v5→v7 NOT_COMPARABLE cells are P1C5, the ESG category v7.0
    killed. Scoring their disappearance as movement would report a taxonomy
    change as a client regression."""
    conn = _two_runs(
        [_cell("P1C5.1", 2.0, cat="P1C5"), _cell("P1C1.1", 2.0)],
        [_cell("P1C1.1", 2.5)],
        base_version="v5.0", target_version="v7.0",
        catalogue={"v5.0": {"P1C5.1", "P1C1.1"}, "v7.0": {"P1C1.1"}})
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    assert [c["subcap_id"] for c in body["cells"]] == ["P1C1.1"]
    killed = [c for c in body["not_comparable"] if c["subcap_id"] == "P1C5.1"]
    assert killed and killed[0]["reason"] == "CELL_ABSENT_FROM_TARGET_CATALOGUE"
    assert body["summary"]["moved"] == 1
    assert body["summary"]["declined"] == 0


def test_a_cell_new_in_the_target_catalogue_is_named_not_dropped():
    conn = _two_runs(
        [_cell("P1C1.1", 2.0)],
        [_cell("P1C1.1", 2.0), _cell("P2C9.1", 3.0, cat="P2C9", pillar="P2")],
        base_version="v5.0", target_version="v7.0",
        catalogue={"v5.0": {"P1C1.1"}, "v7.0": {"P1C1.1", "P2C9.1"}})
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    new = [c for c in body["not_comparable"] if c["subcap_id"] == "P2C9.1"]
    assert new and new[0]["reason"] == "CELL_ABSENT_FROM_BASE_CATALOGUE"
    assert new[0]["target_score"] == 3.0 and new[0]["base_score"] is None


def test_no_bump_means_no_alias_lookup_at_all():
    conn = _two_runs([_cell("P1C1.1", 2.0)], [_cell("P1C1.1", 3.0)])
    build_diff(conn.cursor(), "baxter-credit-union-bcu")
    assert not any("ccg_aliases" in s for s, _ in conn.statements)
    assert not any("ccg_subcaps" in s for s, _ in conn.statements)


# ── argument handling ──────────────────────────────────────────────────
def test_naming_the_same_run_twice_is_refused():
    conn = _two_runs([_cell("P1C1.1", 2.0)], [_cell("P1C1.1", 3.0)])
    with pytest.raises(ApiError) as e:
        build_diff(conn.cursor(), "baxter-credit-union-bcu", base=R1, target=R1)
    assert e.value.status == 400 and e.value.code == "same_run"


def test_an_unpromoted_run_cannot_be_either_end():
    """serving_directory holds promoted runs only, so Baxter's second,
    never-promoted run is not addressable here at all."""
    conn = _two_runs([_cell("P1C1.1", 2.0)], [_cell("P1C1.1", 3.0)])
    with pytest.raises(ApiError) as e:
        build_diff(conn.cursor(), "baxter-credit-union-bcu",
                   base="00000000-0000-0000-0000-000000000000")
    assert e.value.status == 404


def test_an_entity_with_no_promoted_run_is_404():
    conn = _Conn([], {})
    with pytest.raises(ApiError) as e:
        build_diff(conn.cursor(), "nobody")
    assert e.value.status == 404 and e.value.code == "entity_not_found"


def test_the_base_defaults_to_the_run_before_the_target():
    conn = _Conn(
        [_dir_row("r3", 3, "v7.0", 3.0, True),
         _dir_row(R2, 2, "v7.0", 2.8, False),
         _dir_row(R1, 1, "v7.0", 2.5, False)],
        {"r3": [_cell("P1C1.1", 3.0)], R2: [_cell("P1C1.1", 2.8)],
         R1: [_cell("P1C1.1", 2.5)]})
    body = build_diff(conn.cursor(), "baxter-credit-union-bcu")
    assert body["target"]["run_id"] == "r3"
    assert body["base"]["run_id"] == R2, "the run before, not the oldest"


def test_the_diff_writes_nothing():
    conn = _two_runs([_cell("P1C1.1", 2.0)], [_cell("P1C1.1", 3.0)])
    build_diff(conn.cursor(), "baxter-credit-union-bcu")
    for sql, _ in conn.statements:
        assert not any(v in sql.upper()
                       for v in ("INSERT ", "UPDATE ", "DELETE "))
