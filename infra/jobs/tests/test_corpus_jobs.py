"""The two corpus Jobs: what they measure, and what they refuse to conclude.

Run with:  python3 -m pytest infra/jobs -q

The load-bearing behaviours are the refusals. A corpus gate that quietly
passes is worse than one that is missing, because it is evidence of a check
that did not happen — so a measure with a zero denominator, a gate with no
ceiling, and a ceiling naming a measure this scanner does not implement all
come back NOT_RUN with a reason, and none of them comes back PASS.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "infra" / "jobs"))

from corpus_jobs.gate_scan import MEASURES, evaluate, read_ceilings  # noqa: E402
from corpus_jobs.pack import PAGE_TABLES, build_pack, pack_bytes     # noqa: E402

NOW = datetime(2026, 8, 8, 3, 0, tzinfo=timezone.utc)
RUN = "c1351d25-a612-4dbe-b498-127bccaf6810"


class _Conn:
    """serving_directory plus one integer per counter query."""

    def __init__(self, directory, counters):
        self.directory = list(directory)
        self.counters = dict(counters)
        self._out = []

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        if "FROM serving_directory" in sql:
            self._out = list(self.directory)
            return
        for key, value in self.counters.items():
            if key in sql:
                self._out = [(value,)]
                return
        self._out = [(0,)]

    def fetchall(self):
        return self._out

    def fetchone(self):
        return self._out[0] if self._out else None


def _dir_row(display_id="baxter-credit-union-bcu", basis="DERIVED_REQUEST_ID_TOKEN",
             adate=None, due=None):
    from datetime import date
    return (display_id, "Baxter Credit Union (BCU)", "SV2", RUN,
            "DMA-ASM-BCU-20260330-0001", 1, 2.71, 765, 836, "v5.0", NOW,
            adate if adate is not None else date(2026, 3, 30), basis,
            due)


def _pack(**over):
    counters = {"FROM serving_subcaps WHERE run_id = %s\n": 765}
    conn = _Conn([_dir_row(**over)], {
        "overview_scores": 1, "heatmap_workbook_scores": 1, "insight_cards": 4,
        "platform_story": 1, "context_timeline": 3, "techstack_items": 23,
        "is_thin_evidence": 11, "subcap_name IS NULL": 0,
        "score IS NULL": 0, "heatmap_alerts": 11,
        "result = 'NOT_RUN'": 1, "FROM gate_results WHERE run_id": 6,
        "FROM serving_subcaps": 765,
    })
    return build_pack(conn.cursor(), as_of=NOW), counters


# ── the pack ───────────────────────────────────────────────────────────
def test_the_pack_carries_a_denominator_for_every_count():
    pack, _ = _pack()
    c = pack["clients"][0]
    assert c["cells"] == 765
    assert c["pages_expected"] == len(PAGE_TABLES) == 6
    assert c["pages_promoted"] == 6
    assert pack["counts"]["clients"] == 1
    assert pack["counts"]["cells"] == 765


def test_the_pack_carries_the_cadence_and_whether_the_date_was_stated():
    pack, _ = _pack()
    c = pack["clients"][0]
    assert c["assessment_date"] == "2026-03-30"
    assert c["assessment_date_basis"] == "DERIVED_REQUEST_ID_TOKEN"
    assert c["assessment_date_is_stated"] is False


def test_an_unresolvable_date_gives_no_overdue_verdict():
    pack, _ = _pack(basis="UNKNOWN", adate=None, due=None)
    c = pack["clients"][0]
    assert c["refresh_due_date"] is None
    assert c["refresh_overdue"] is None, "unknown must not read as 'not overdue'"


def test_the_pack_bytes_are_stable_for_an_unchanged_corpus():
    a, _ = _pack()
    b, _ = _pack()
    assert pack_bytes(a) == pack_bytes(b)


# ── the scanner's refusals ─────────────────────────────────────────────
def test_no_ceilings_configured_means_no_verdicts_at_all():
    pack, _ = _pack()
    assert evaluate(pack, {}) == []


def test_the_shipped_ceilings_file_is_still_empty_and_that_is_deliberate():
    """It is populated at stage 8, by MEASUREMENT of the corpus. If this
    starts failing, the scanner's measures need checking against it."""
    gates = json.loads((ROOT / "packages" / "shared" / "corpus_gates.json")
                       .read_text(encoding="utf-8"))
    assert gates["gates"] == {}


def test_a_ceiling_naming_an_unknown_measure_is_not_run_not_pass():
    pack, _ = _pack()
    v = evaluate(pack, {"CG-99": {"measure": "vibes", "ceiling": 0.1}})[0]
    assert v["result"] == "NOT_RUN"
    assert "vibes" in v["not_run_reason"]
    assert v["result"] != "PASS"


def test_a_gate_with_no_ceiling_is_not_run():
    pack, _ = _pack()
    v = evaluate(pack, {"CG-01": {"measure": "cells_thin_evidence"}})[0]
    assert v["result"] == "NOT_RUN"
    assert v["not_run_reason"] == "the gate states no ceiling"


def test_a_zero_denominator_is_not_run_not_pass():
    conn = _Conn([_dir_row()], {})          # every counter zero, cells zero
    pack = build_pack(conn.cursor(), as_of=NOW)
    v = evaluate(pack, {"CG-01": {"measure": "cells_thin_evidence",
                                  "ceiling": 0.0}})[0]
    assert v["result"] == "NOT_RUN"
    assert "denominator is zero" in v["not_run_reason"]


def test_an_empty_corpus_cannot_pass_a_per_client_gate():
    conn = _Conn([], {})
    pack = build_pack(conn.cursor(), as_of=NOW)
    assert pack["counts"]["clients"] == 0
    for v in evaluate(pack, {g: {"measure": m, "ceiling": 0.0}
                             for g, m in [("CG-01", "cells_thin_evidence"),
                                          ("CG-02", "assessment_date_not_stated")]}):
        assert v["result"] == "NOT_RUN"


# ── the verdicts it does reach ─────────────────────────────────────────
def test_a_breach_names_the_arithmetic_and_the_clients():
    pack, _ = _pack()
    v = evaluate(pack, {"CG-01": {"measure": "cells_thin_evidence",
                                  "ceiling": 0.01}})[0]
    assert v["result"] == "FAIL"
    assert v["detail"]["arithmetic"] == "11/765 = 0.0144 vs ceiling 0.01"
    assert v["detail"]["worst_clients"][0]["display_id"] == "baxter-credit-union-bcu"


def test_a_rate_at_the_ceiling_passes():
    pack, _ = _pack()
    v = evaluate(pack, {"CG-01": {"measure": "assessment_date_not_stated",
                                  "ceiling": 1.0}})[0]
    assert v["result"] == "PASS"
    assert v["detail"]["numerator"] == 1 and v["detail"]["denominator"] == 1


def test_the_date_provenance_is_measurable_corpus_wide():
    """The defect this build removed is now a rate a ceiling can ratchet."""
    pack, _ = _pack()
    num, den, _ = MEASURES["assessment_date_not_stated"](pack)
    assert (num, den) == (1, 1)
    pack2, _ = _pack(basis="STATED")
    num2, _, _ = MEASURES["assessment_date_not_stated"](pack2)
    assert num2 == 0


def test_every_measure_is_callable_on_an_empty_corpus_without_raising():
    conn = _Conn([], {})
    pack = build_pack(conn.cursor(), as_of=NOW)
    for name, fn in MEASURES.items():
        num, den, rows = fn(pack)
        assert (num, den, rows) == (0, 0, []), name


def test_missing_ceilings_file_reads_as_no_gates_not_as_a_crash():
    assert read_ceilings("/nonexistent/corpus_gates.json") == {}
