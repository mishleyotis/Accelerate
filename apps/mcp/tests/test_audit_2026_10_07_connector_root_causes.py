"""Connector-side root causes the Arbor Bank run (2026-10-05..07) exposed:

  D  SG-V4 embedded producer metadata sitting directly on an object
  E  a card's sayable `l3_area` matched no cell unless it carried the code
  F  heatmap_evidence_age.e_id took the package-local id and hit the FK
  N  AG-01's verdict vocabulary lived only in pass 2, so the local precheck
     could not see a WITHDRAWN verdict before the server refused it
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import fit as fit_mod  # noqa: E402
from dma_mcp import promote  # noqa: E402
from dma_mcp import validation as V1  # noqa: E402
from dma_mcp import validation2 as V2  # noqa: E402


# ── D ────────────────────────────────────────────────────────────────────

def test_v4_skips_producer_metadata_on_direct_string_fields():
    long = "a sentence long enough to be prose about the entity and its systems " * 2
    payload = {"alerts": {"items": [{"subcap_id": "P1C1.1.1", "synthesis": long,
                                     "rationale": long, "closure_condition": long,
                                     "not_run_reason": long, "r_layer": {"counter": long},
                                     "url": "https://x.example/" + "p" * 60}]}}
    paths = [p for p, *_ in V2._v4_fields(payload)]
    assert "alerts.items[0].synthesis" in paths
    assert not any(p.endswith((".rationale", ".closure_condition", ".not_run_reason"))
                   for p in paths), paths
    assert not any(".r_layer" in p for p in paths)
    assert not any(p.endswith(".url") for p in paths)


def test_the_skip_list_is_the_same_one_the_nested_walk_uses():
    assert "rationale" in V2._V4_SKIP_KEYS and "r_layer" in V2._V4_SKIP_KEYS


# ── E ────────────────────────────────────────────────────────────────────

class _Cur:
    def __init__(self, cells, l3=()):
        self.cells, self.l3, self._rows = cells, list(l3), []

    def execute(self, sql, args=None):
        s = " ".join(sql.split())
        if "FROM runs WHERE id" in s:
            self._rows = [("run",)]
        elif "FROM subcap_scores" in s:
            self._rows = [(sid, sc, cat, None, [area]) for sid, sc, cat, area in self.cells]
        elif "FROM ccg_l3_platforms" in s:
            self._rows = list(self.l3)
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


L3 = [("L3-SF-FSC", "Salesforce", "Financial Services Cloud"),
      ("L3-MULE", "MuleSoft", "MuleSoft Anypoint Platform"),
      ("L3-SF-DC-CORE", "Salesforce", "Salesforce Data Cloud")]
CELLS = [("P2C1.1.1", 2.0, "P2C1", "[L3-SF-FSC] Financial Services Cloud (count: 3)"),
         ("P2C1.1.2", 1.5, "P2C1", "[L3-SF-FSC] Financial Services Cloud (count: 3)"),
         ("P2C1.1.3", 1.0, "P2C1", "[L3-SF-FSC] Financial Services Cloud (count: 3)"),
         ("P4C3.1.1", 2.0, "P4C3", "[L3-MULE] MuleSoft Anypoint Platform (count: 2)"),
         ("P4C3.1.2", 2.0, "P4C3", "[L3-MULE] MuleSoft Anypoint Platform (count: 2)"),
         ("P4C3.1.3", 2.0, "P4C3", "[L3-MULE] MuleSoft Anypoint Platform (count: 2)")]


def _fit(cards, l3=L3):
    return fit_mod.platform_fit(_Conn(_Cur(CELLS, l3)), "run", cards)


def test_a_sayable_name_resolves_to_the_catalogue_code():
    out = _fit([{"platform": "Salesforce Financial Services Cloud",
                 "l3_area": "Financial Services Cloud", "readiness": "green"},
                {"platform": "MuleSoft", "l3_area": "MuleSoft Anypoint Platform (Integration)",
                 "readiness": "green"}])
    assert not out.get("unmatched"), out.get("unmatched")
    by = {p["platform"]: p for p in out["platforms"]}
    assert by["Salesforce Financial Services Cloud"]["cells_addressed"] == 3
    assert by["MuleSoft"]["cells_addressed"] == 3


def test_the_vendor_prefix_is_optional_either_way():
    out = _fit([{"platform": "Data Cloud", "l3_area": "Data Cloud", "readiness": "green"},
                {"platform": "x", "l3_area": "Salesforce Financial Services Cloud",
                 "readiness": "green"}])
    names = {u["l3_area"] for u in out.get("unmatched", [])}
    assert "Salesforce Financial Services Cloud" not in names
    # "Data Cloud" names a catalogue platform; no cell in THIS run lists it,
    # and the reason says which of the two it is
    dc = next(u for u in out["unmatched"] if u["l3_area"] == "Data Cloud")
    assert dc["resolved_to"] == "L3-SF-DC-CORE"
    assert "no cell this run serves" in dc["reason"]


def test_an_unknown_label_stays_unmatched_and_says_why():
    out = _fit([{"platform": "Acme Thing", "l3_area": "Integration", "readiness": "green"}])
    u = out["unmatched"][0]
    assert u["resolved_to"] == "integration"
    assert "names no catalogue platform" in u["reason"]


def test_a_bracketed_code_still_wins_over_the_name():
    out = _fit([{"platform": "Whatever", "l3_area": "[L3-MULE] something else", "readiness": "green"}])
    assert not out.get("unmatched")


# ── F ────────────────────────────────────────────────────────────────────

class _InsertCur:
    def __init__(self, aliases):
        self.aliases, self.inserts, self._rows = aliases, [], []

    def execute(self, sql, args=None):
        s = " ".join(sql.split())
        if s.startswith("INSERT INTO"):
            self.inserts.append((s, list(args or [])))
            self._rows = []
        elif "FROM evidence_package_ids" in s:
            self._rows = list(self.aliases.items())
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def _writer(page, section):
    return next(w for (p, s_), w in promote.writer_registry() if (p, s_) == (page, section))


def test_a_package_local_e_id_resolves_through_the_alias_table_at_promote():
    w = _writer("heatmap", "evidence_age")
    cur = _InsertCur({"E-001": "E-ARBORBAN-001"})
    ctx = {"run_id": "run", "entity_id": "ent", "producer_version": "p@1", "provenance": {}}
    rows = [{"reference_date": "2026-10-05", "e_id": "E-001", "title": "a",
             "source_domain": "x.example", "published_or_asof": "2025-01-01",
             "age_months": 20, "band": "DATED", "status": "DATED"},
            {"reference_date": "2026-10-05", "e_id": "E-CC-0007", "title": "b",
             "source_domain": "y.example", "published_or_asof": None,
             "age_months": None, "band": "undated", "status": "UNDATED"}]
    n = promote._write_section(cur, w, ctx, {"rows": rows})
    assert n == 2
    cols = cur.inserts[0][0].split("(")[1].split(")")[0].split(",")
    i = cols.index("e_id")
    assert cur.inserts[0][1][i] == "E-ARBORBAN-001"
    assert cur.inserts[1][1][i] == "E-CC-0007", "a stored id is written as given"


def test_no_alias_rows_leaves_every_id_as_given():
    w = _writer("heatmap", "evidence_age")
    cur = _InsertCur({})
    ctx = {"run_id": "run", "entity_id": "ent", "producer_version": "p@1", "provenance": {}}
    promote._write_section(cur, w, ctx, {"rows": [{"reference_date": "2026-10-05", "e_id": "E-001"}]})
    cols = cur.inserts[0][0].split("(")[1].split(")")[0].split(",")
    assert cur.inserts[0][1][cols.index("e_id")] == "E-001"


# ── N ────────────────────────────────────────────────────────────────────

def _cohort(verdict):
    return {"cohort_patterns": {"patterns": [{"pattern_id": "cp-1", "r_layer": {"verdict": verdict}}]}}


def test_pass1_refuses_a_rejected_or_unreadable_verdict():
    got = V1.check_r_layer_verdicts("heatmap", _cohort("WITHDRAWN"))
    assert got and got[0]["gate_id"] == "AG-01" and "WITHDRAWN" in got[0]["message"]
    got = V1.check_r_layer_verdicts("heatmap", _cohort("maybe"))
    assert got and "vocabulary" in got[0]["message"]
    assert V1.check_r_layer_verdicts("heatmap", _cohort("HOLDS")) == []
    # a missing verdict is pass 2's (shape-bound) business, not a pass-1 refusal
    assert V1.check_r_layer_verdicts("heatmap", {"cohort_patterns": {"patterns": [{"pattern_id": "x"}]}}) == []
    # an unranked section is nobody's business here
    assert V1.check_r_layer_verdicts("heatmap", {"alerts": {"items": [{"r_layer": {"verdict": "REJECT"}}]}}) == []


def test_validate_pass1_carries_the_check_and_pass2_shares_the_vocabulary():
    reasons = V1.validate_pass1("heatmap", _cohort("REJECT"))
    assert any(r["gate_id"] == "AG-01" and "REJECT" in r["message"] for r in reasons)
    assert V2._ACCEPTING_VERDICTS is V1._ACCEPTING_VERDICTS
    assert V2._REJECTING_VERDICTS is V1._REJECTING_VERDICTS
    assert V2._RANKED_SECTIONS == V1.RANKED_SECTIONS
