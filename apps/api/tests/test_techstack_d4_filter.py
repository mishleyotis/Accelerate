"""DECISIONS D4 — the customer tech register carries CONFIRMED and ABSENT
rows only (RC-08 / D-12).

MEASURED 2026-10-04 on SWBC (gold audit, slice INS-TS-03/04): all 36 register
rows served to the customer audience, 12 of them INFERRED and 11 CLAIMED.
plugins/dma-insights/docs/DECISIONS.md D4 says a row surfaces on the customer
page only when its status is CONFIRMED or ABSENT and calls that an enforced
serve-side filter — no such filter existed in redaction.py or pages.py, and
nothing tested it. The owner confirmed D4 stands (2026-10-04).

The landscape tiles and the layer rollup are recomputed from the FILTERED
register for the customer (invariant 8: the T2 landscape recomputes from the
T1 register — the register the reader is shown, not the one they are not).

Fixture rows are SHAPED like the measured ones and carry no client text.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.redaction import redact_section                      # noqa: E402


def _row(ts, status, layer="CUST"):
    return {"ts_id": ts, "product": f"Product {ts}", "vendor": "Vendor",
            "layer": layer, "pillar_id": "P2", "status": status,
            "evidence_level": "L2", "e_ids": ["E-CC-1"],
            "linked_subcap_ids": ["P2C1.1.1"], "detection_basis": "x"}


STATUSES = ["CONFIRMED", "INFERRED", "CLAIMED", "ABSENT", "CONFIRMED",
            "INFERRED", "CLAIMED", "CONFIRMED"]
BODY = {
    "items": [_row(f"TS-{i:03d}", s, "CUST" if i % 2 else "OPS")
              for i, s in enumerate(STATUSES, 1)],
    "layers": [
        {"layer": "OPS", "pillar_id": "P3", "detected": 3,
         "detected_basis": "register rows in this layer corroborated to "
                           "CONFIRMED or INFERRED", "expected": 40,
         "expected_basis": "cells", "is_primary_gap": False},
        {"layer": "CUST", "pillar_id": "P2", "detected": 2,
         "detected_basis": "register rows in this layer corroborated to "
                           "CONFIRMED or INFERRED", "expected": 50,
         "expected_basis": "cells", "is_primary_gap": True},
    ],
}


def test_no_claimed_or_inferred_row_reaches_a_customer():
    out, rep = redact_section("techstack", "techstack", copy.deepcopy(BODY),
                              [], "customer")
    served = {r["status"] for r in out["items"]}
    assert served <= {"CONFIRMED", "ABSENT"}, served
    assert len(out["items"]) == 4          # 3 CONFIRMED + 1 ABSENT
    # Order is meaning (rule 10): the survivors keep the producer's order.
    assert [r["ts_id"] for r in out["items"]] == [
        "TS-001", "TS-004", "TS-005", "TS-008"]
    assert rep["d4_rows_withheld"] == 4


def test_the_internal_register_is_untouched():
    out, _ = redact_section("techstack", "techstack", copy.deepcopy(BODY),
                            [], "internal")
    assert [r["status"] for r in out["items"]] == STATUSES


def test_a_row_with_no_status_is_withheld_not_guessed():
    """Default-deny: status is REQUIRED per row (charter correction table);
    a row without one cannot be shown to satisfy D4."""
    body = {"items": [_row("TS-1", "CONFIRMED"), {**_row("TS-2", None)}]}
    body["items"][1].pop("status")
    out, _ = redact_section("techstack", "techstack", body, [], "customer")
    assert [r["ts_id"] for r in out["items"]] == ["TS-1"]


def test_layer_rollup_is_recomputed_from_the_filtered_register():
    out, _ = redact_section("techstack", "techstack", copy.deepcopy(BODY),
                            [], "customer")
    by = {l["layer"]: l for l in out["layers"]}
    # CUST (odd indices): TS-001 C, 003 CL, 005 C, 007 CL -> 2 CONFIRMED.
    # OPS (even): TS-002 I, 004 A, 006 I, 008 C -> 1 CONFIRMED.
    assert by["CUST"]["detected"] == 2
    assert by["OPS"]["detected"] == 1
    for l in out["layers"]:
        assert "INFERRED" not in l["detected_basis"]
    # The catalogue denominator is an outside number: unchanged.
    assert by["CUST"]["expected"] == 50


def test_landscape_tiles_follow_the_filtered_register():
    tiles = [{"kind": k, "count": n, "basis": f"{n} · L1–L2 evidence",
              "detail": "d", "named_items": []}
             for k, n in (("CONFIRMED", 3), ("INFERRED", 2), ("CLAIMED", 2),
                          ("GAPS", 1))]
    body = {"tiles": tiles, "reconciles_to_register": True}
    out, rep = redact_section("insights", "landscape", copy.deepcopy(body),
                              [], "customer")
    assert [t["kind"] for t in out["tiles"]] == ["CONFIRMED", "GAPS"]
    assert out["reconciles_to_register"] is True
    internal, _ = redact_section("insights", "landscape", copy.deepcopy(body),
                                 [], "internal")
    assert len(internal["tiles"]) == 4
