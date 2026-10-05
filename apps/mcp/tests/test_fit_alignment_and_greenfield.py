"""Strategic alignment and greenfield are WEIGHED, not left at zero.

Owner, 2026-10-05: "the greenfield opportunities and strategic alignment
parameters rarely receive scores. Ensure each of these parameters is weighed
accordingly." Measured on Cross Insurance Agency: every card read
`alignment_basis: impact_fallback` (alignment weight 0.0, renormalised away)
and `Greenfield family: 0.0`, on a run that served five client-stated focus
areas with verbatim quotes and a 32-row scanned register.

  · alignment is computed from the run's own focus areas (heatmap.focus_areas)
    when a producer states none;
  · greenfield is graded: the share of a card's cells no detected incumbent
    holds, 0 when the register already runs that product, unmeasured (and
    said so) with no scanned register.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from dma_mcp import fit as fit_mod  # noqa: E402
import platform_fit as engine  # noqa: E402

CELLS = [("P2C3.2.1", 1.0, "P2C3", "crm"), ("P2C3.2.4", 1.0, "P2C3", "crm"),
         ("P2C3.3.1", 1.5, "P2C3", "crm"), ("P4C1.3.1", 1.0, "P4C1", "data"),
         ("P4C1.3.2", 1.0, "P4C1", "data"), ("P4C1.4.1", 1.5, "P4C1", "data")]

FOCUS = [{"fa_id": "FA-1", "involved_subcap_ids": ["P2C3.2.1", "P2C3.3.9"],
          "verbatim_quote": "By engaging our customers in a digital space, we "
                            "can provide excellent service and security."}]


def _page(sql, args):
    """The page a submissions read asks for: bound (`page = %s`) or inline
    (`page = 'techstack'`, as _register_staged writes it)."""
    if "'techstack'" in sql:
        return "techstack"
    return args[1] if args and len(args) > 1 else None


class _Cur:
    def __init__(self, focus=None, items=None):
        self.focus, self.items, self._rows = focus, items, []

    def execute(self, sql, args=None):
        if "FROM runs WHERE id" in sql:
            self._rows = [("run",)]
        elif "FROM subcap_scores" in sql:
            self._rows = [(s, sc, cat, None, [a]) for s, sc, cat, a in CELLS]
        elif "FROM submissions" in sql and _page(sql, args) == "heatmap":
            self._rows = ([({"focus_areas": {"focus_areas": self.focus}},)]
                          if self.focus is not None else [])
        elif "FROM submissions" in sql and _page(sql, args) == "techstack":
            self._rows = ([({"techstack": {"items": self.items}},)]
                          if self.items is not None else [])
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


def _fit(cands, focus=None, items=None):
    out = fit_mod.platform_fit(_Conn(_Cur(focus, items)), "run", cands)
    return {r["platform"]: r for r in out["platforms"]}, out["context"]


def _factor(row, name):
    return {f["name"]: f for f in row["factors"]}[name]


CRM = {"platform": "Financial Services Cloud", "l3_area": "crm",
       "readiness": "green"}
DATA = {"platform": "Data Cloud", "l3_area": "data", "readiness": "green"}


# ── alignment ──────────────────────────────────────────────────────────

def test_focus_areas_give_an_unstated_card_a_weighed_alignment():
    rows, ctx = _fit([CRM, DATA], focus=FOCUS)
    crm = rows["Financial Services Cloud"]
    assert crm["alignment_basis"] == engine.ALIGNMENT_FOCUS_AREAS
    a = _factor(crm, "Strategic alignment")
    assert a["weight"] == round(engine.W_ALIGNMENT, 4) and a["value"] > 0
    assert crm["alignment_quote"].startswith("FA-1: By engaging our customers")
    assert ctx["alignment_source"] == engine.ALIGNMENT_FOCUS_AREAS


def test_alignment_is_matched_at_capability_grain_and_is_a_share():
    # FA-1 names capabilities P2C3.2 and P2C3.3; the CRM card reaches both
    # (P2C3.3.9 is not one of its cells, but P2C3.3.1 is).
    rows, _ = _fit([CRM], focus=FOCUS)
    assert _factor(rows["Financial Services Cloud"],
                   "Strategic alignment")["value"] == 1.0


def test_a_card_reaching_no_stated_priority_is_measured_at_zero_not_dropped():
    rows, _ = _fit([DATA], focus=FOCUS)
    data = rows["Data Cloud"]
    assert data["alignment_basis"] == engine.ALIGNMENT_FOCUS_AREAS
    assert _factor(data, "Strategic alignment")["value"] == 0.0
    assert _factor(data, "Strategic alignment")["weight"] > 0


def test_aligned_beats_unaligned_on_otherwise_equal_ground():
    rows, _ = _fit([CRM, DATA], focus=FOCUS)
    assert (_factor(rows["Financial Services Cloud"], "Strategic alignment")
            ["contribution"] > _factor(rows["Data Cloud"],
                                       "Strategic alignment")["contribution"])


def test_a_stated_alignment_still_wins_over_the_derived_one():
    stated = dict(DATA, alignment=0.9, alignment_quote="their own words")
    rows, _ = _fit([stated], focus=FOCUS)
    assert rows["Data Cloud"]["alignment_basis"] == engine.ALIGNMENT_STATED
    assert _factor(rows["Data Cloud"], "Strategic alignment")["value"] == 0.9


def test_with_no_focus_areas_alignment_renormalises_and_says_why():
    rows, ctx = _fit([CRM], focus=None)
    assert rows["Financial Services Cloud"]["alignment_basis"] == \
        engine.ALIGNMENT_FALLBACK
    assert any("focus areas" in n for n in ctx["notes"])


def test_a_focus_area_without_a_verbatim_quote_is_not_a_stated_objective():
    unquoted = [dict(FOCUS[0], verbatim_quote="")]
    rows, _ = _fit([CRM], focus=unquoted)
    assert rows["Financial Services Cloud"]["alignment_basis"] == \
        engine.ALIGNMENT_FALLBACK


# ── greenfield ─────────────────────────────────────────────────────────

REGISTER = [{"status": "INFERRED", "product": "Snowflake",
             "linked_subcap_ids": ["P4C1.3.1"]},
            {"status": "INFERRED", "product": "Salesforce CRM",
             "linked_subcap_ids": ["P2C3.2.1"]}]


def test_greenfield_is_graded_by_the_cells_no_incumbent_holds():
    rows, ctx = _fit([CRM, DATA], items=REGISTER)
    crm = _factor(rows["Financial Services Cloud"], "Greenfield family")
    data = _factor(rows["Data Cloud"], "Greenfield family")
    assert crm["value"] == round(2 / 3, 4) and data["value"] == round(2 / 3, 4)
    assert crm["contribution"] > 0
    assert rows["Data Cloud"]["greenfield_basis"] == \
        engine.GREENFIELD_OPEN_GROUND
    assert ctx["greenfield_source"] == "register"


def test_a_product_the_register_already_runs_is_an_expansion_not_greenfield():
    rows, _ = _fit([{"platform": "Snowflake", "l3_area": "data",
                     "readiness": "green"}], items=REGISTER)
    snow = rows["Snowflake"]
    assert _factor(snow, "Greenfield family")["value"] == 0.0
    assert snow["greenfield_basis"] == engine.GREENFIELD_INCUMBENT


def test_an_absent_row_still_scores_the_full_term():
    items = REGISTER + [{"status": "ABSENT", "product": "Data Cloud",
                         "linked_subcap_ids": ["P4C1.4.1"]}]
    rows, _ = _fit([DATA], items=items)
    assert _factor(rows["Data Cloud"], "Greenfield family")["value"] == 1.0
    assert rows["Data Cloud"]["greenfield_basis"] == engine.GREENFIELD_ABSENT


def test_without_a_scanned_register_greenfield_is_unmeasured_not_open():
    rows, ctx = _fit([DATA], items=None)
    assert _factor(rows["Data Cloud"], "Greenfield family")["value"] == 0.0
    assert rows["Data Cloud"]["greenfield_basis"] == \
        engine.GREENFIELD_UNMEASURED
    assert ctx["greenfield_source"] == engine.GREENFIELD_UNMEASURED


def test_the_greenfield_weight_is_still_the_audited_share():
    """The 2026-07 skew audit set the absent term low on purpose; grading the
    value must not move its weight."""
    rows, _ = _fit([DATA], focus=FOCUS, items=REGISTER)
    assert _factor(rows["Data Cloud"], "Greenfield family")["weight"] == \
        round(engine.W_ABSENT, 4)


def test_breakdown_still_equals_the_headline():
    rows, _ = _fit([CRM, DATA], focus=FOCUS, items=REGISTER)
    for r in rows.values():
        sub = sum(f["contribution"] for f in r["factors"])
        rel = 1.0 if r["relevance"] is None else r["relevance"]  # unchecked
        assert abs(100 * sub * r["readiness_multiplier"] * rel
                   - r["fit_score"]) <= 0.1
