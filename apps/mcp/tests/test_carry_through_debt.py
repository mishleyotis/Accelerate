"""Gate debt on unchanged content is named, and it still blocks.

MEM-0177 / MEM-0197, measured 2026-08-23: a heatmap resubmission drew 51
blocking reasons, of which 14 (27%) were CG-23 and CG-27 on sections verified
BYTE-EXACT against a submission that PASSED on 2026-08-17. CG-23 was created
2026-08-18 — one day of drift, and repairing any one section re-exposed the
whole page to a registry that had moved underneath it.

The shortcut the charter forbids is grandfathering: a retained PASS is a DATED
observation, and promoting on one puts content on a client surface this
connector would refuse today (promote.py says exactly that in its own refusal
text). So the debt still blocks. What changes is that it is LABELLED — the
difference between "your change has 51 problems" and "your change has 37; the
other 14 are on sections you did not touch, against a gate younger than the
last time they passed".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dma_mcp import submit  # noqa: E402
# ── gate debt is named, never waived ──────────────────────────────────────
#
# MEM-0177 / MEM-0197, measured 2026-08-23: a heatmap resubmission drew 51
# blocking reasons, of which 14 (27%) were CG-23 and CG-27 on sections
# verified BYTE-EXACT against a submission that PASSED on 2026-08-17. CG-23
# was created 2026-08-18 — one day of drift, and repairing any one section
# re-exposed the whole page to a registry that had moved underneath it.
#
# The shortcut the charter forbids is grandfathering: a retained PASS is a
# DATED observation, and promoting on one puts content on a client surface
# this connector would refuse today. So the debt still blocks. What changes is
# that it is LABELLED, which is the difference between "your change has 51
# problems" and "your change has 37; 14 are on sections you did not touch".

class _Cur:
    def __init__(self, row=None, raises=False):
        self._row, self._raises = row, raises
    def execute(self, *a, **kw):
        if self._raises:
            raise RuntimeError("no such column")
    def fetchone(self):
        return self._row


def _reasons():
    return [
        {"gate_id": "CG-23", "section": "cell_evidence", "severity": "block",
         "message": "narrative_thread is null"},
        {"gate_id": "AG-03", "section": "safeguard_gates", "severity": "block",
         "message": "caps cite no evidence"},
    ]


PRIOR = {"cell_evidence": {"rows": [{"a": 1}], "n": 2},
         "safeguard_gates": {"caps": []}}


def test_an_unchanged_section_is_labelled_carry_through():
    reasons = _reasons()
    payload = {"cell_evidence": {"n": 2, "rows": [{"a": 1}]},   # reordered keys
               "safeguard_gates": {"caps": [{"cap_id": "X"}]}}  # CHANGED
    submit.mark_carry_through(
        _Cur(("sub-123", PRIOR, "2026-08-17T19:39:02Z")),
        "run-1", "heatmap", payload, reasons)
    cg23 = next(r for r in reasons if r["gate_id"] == "CG-23")
    ag03 = next(r for r in reasons if r["gate_id"] == "AG-03")
    assert cg23.get("carry_through") is True
    assert cg23["unchanged_since"]["submission_id"] == "sub-123"
    assert "2026-08-17" in cg23["unchanged_since"]["passed_at"]
    assert "carry_through" not in ag03, (
        "the section the producer actually changed is THEIR change")


def test_key_order_is_not_content():
    """A producer that re-emitted the same section through a different
    serialiser did not change it."""
    reasons = [{"gate_id": "CG-27", "section": "cell_evidence",
                "severity": "block", "message": "API unexplained"}]
    submit.mark_carry_through(
        _Cur(("sub-1", {"cell_evidence": {"x": 1, "y": 2}}, "t")),
        "r", "heatmap", {"cell_evidence": {"y": 2, "x": 1}}, reasons)
    assert reasons[0].get("carry_through") is True


def test_the_reason_still_blocks():
    """THE LINE THAT MUST NOT MOVE. Labelling is not waiving — severity and
    the reason itself are untouched, because a retained verdict is a dated
    observation and grandfathering it would serve content the connector
    refuses today."""
    reasons = _reasons()
    before = [(r["gate_id"], r["severity"], r["message"]) for r in reasons]
    submit.mark_carry_through(
        _Cur(("s", PRIOR, "t")), "r", "heatmap",
        {"cell_evidence": {"rows": [{"a": 1}], "n": 2}}, reasons)
    after = [(r["gate_id"], r["severity"], r["message"]) for r in reasons]
    assert before == after, "no reason removed, no severity softened"


def test_no_prior_pass_annotates_nothing():
    reasons = _reasons()
    submit.mark_carry_through(_Cur(None), "r", "heatmap", PRIOR, reasons)
    assert not any("carry_through" in r for r in reasons)


def test_a_query_that_raises_annotates_nothing_and_says_nothing_false():
    """A comparison that could not run is not a comparison that found no
    debt. The verdict is returned complete, simply without the labels."""
    reasons = _reasons()
    submit.mark_carry_through(_Cur(raises=True), "r", "heatmap", PRIOR, reasons)
    assert not any("carry_through" in r for r in reasons)


def test_reasons_with_no_section_are_left_alone():
    reasons = [{"gate_id": "CG-01", "section": None, "severity": "block",
                "message": "page-level"}]
    submit.mark_carry_through(_Cur(("s", PRIOR, "t")), "r", "heatmap",
                              PRIOR, reasons)
    assert "carry_through" not in reasons[0]
