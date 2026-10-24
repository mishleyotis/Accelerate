"""H5 does not disclose a safeguard about a surface the reader is not shown
(RC-08 / D-34).

MEASURED 2026-10-04 on SWBC (gold audit, slices S-02, XC-08, HM-08): the
customer H5 served the SG-S8 row — "Sentiment rests on a single source" —
while `overview.sentiment` itself was withheld from that audience. A
disclosure about a card the reader cannot open reads as a defect in a card
that does not exist.

OWNER DECISION 1 (2026-10-04) then changed the premise for SG-S8 itself: the
customer now receives a REDUCED sentiment card, so SG-S8's target IS served
and the row correctly stays. The rule this file pins is the general one — a
gate row is dropped for an audience when EVERY section it targets is
withheld from that audience — and the SG-S8 case is pinned both ways: kept
under today's rules, dropped the moment its target is withheld again.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import redaction                                      # noqa: E402
from dma_api.redaction import redact_section                      # noqa: E402

BODY = {"gates": [
    {"gate_id": "SG-V4", "plain_label": "Every claim is checked against this "
     "assessment's own evidence before it reaches you", "result": "PASS",
     "detail": None, "not_run_reason": None},
    {"gate_id": "SG-S8", "plain_label": "Sentiment rests on a single source, "
     "so treat it as indicative only", "result": "FAIL", "detail": None,
     "not_run_reason": None},
], "caps": []}


def _gate_ids(out):
    return [g["gate_id"] for g in out["gates"]]


def test_sg_s8_row_absent_from_the_customer_h5_when_sentiment_is_withheld(
        monkeypatch):
    """The measured state: sentiment withheld, SG-S8 still disclosed."""
    monkeypatch.setattr(redaction, "CUSTOMER_WITHHELD",
                        redaction.CUSTOMER_WITHHELD
                        | {("overview", "sentiment")})
    out, rep = redact_section("heatmap", "safeguard_gates",
                              copy.deepcopy(BODY), [], "customer")
    assert _gate_ids(out) == ["SG-V4"]
    assert rep["gates_withheld_target"] == ["SG-S8"]


def test_sg_s8_stays_now_that_customers_get_the_reduced_card():
    """Owner decision 1: overview.sentiment is served (reduced) to the
    customer, so its safeguard is about a surface the reader can open."""
    assert ("overview", "sentiment") not in redaction.CUSTOMER_WITHHELD
    out, _ = redact_section("heatmap", "safeguard_gates",
                            copy.deepcopy(BODY), [], "customer")
    assert _gate_ids(out) == ["SG-V4", "SG-S8"]


def test_the_internal_audience_keeps_every_gate_row():
    out, _ = redact_section("heatmap", "safeguard_gates",
                            copy.deepcopy(BODY), [], "internal")
    assert _gate_ids(out) == ["SG-V4", "SG-S8"]


def test_every_target_of_a_known_gate_is_a_real_section():
    """A target map naming a section that does not exist would drop nothing
    and look like it worked."""
    from dma_api.serving_spec import page_sections
    for gate, targets in redaction.SG_GATE_TARGETS.items():
        for page, section in targets:
            assert section in page_sections(page), (gate, page, section)


def test_a_gate_with_no_declared_target_is_kept():
    """Default to disclosure: an unmapped gate (SG-V4 checks every page) is
    never dropped by this rule."""
    body = {"gates": [{"gate_id": "SG-ZZ9", "plain_label": "x",
                       "result": "PASS", "detail": None,
                       "not_run_reason": None}]}
    out, _ = redact_section("heatmap", "safeguard_gates", body, [],
                            "customer")
    assert _gate_ids(out) == ["SG-ZZ9"]
