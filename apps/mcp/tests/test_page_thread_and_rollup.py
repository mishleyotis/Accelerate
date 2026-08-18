"""CG-23 and CG-24 — the two gates the third client's promoted run needed.

Both close the same class of failure: a page that satisfies every field-shape
rule and still reads wrong to a human. One was a page with no thread through
it; the other was two figures on the same card counting different things.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dma_mcp import contracts, validation  # noqa: E402


def _reasons(page, payload):
    return validation.validate_pass1(page, payload)


def _ids(reasons, gate):
    return [r for r in reasons if r.get("gate_id") == gate]


# ── CG-23 · every page's own thread is written ─────────────────────────

def _thread_binding_sections():
    """(page, section) for every section whose writer stores a thread.

    Read from the contract registry, which merges the field in only where
    writer_spec.json says the column is bound — so this list is the gate's
    own scope, derived the same way the gate derives it.
    """
    out = []
    for page in contracts.PAGES:
        for name, sec in contracts.sections(page).items():
            if "narrative_thread" in sec["fields"]:
                out.append((page, name))
    return out


def test_the_gate_has_a_scope_and_it_is_not_everything():
    """Six of the writers bind the thread at item grain and must stay exempt.

    If this ever equals the full section count, the derivation broke and the
    gate would start refusing sections that have nowhere to store a thread.
    """
    bound = _thread_binding_sections()
    total = sum(len(contracts.sections(p)) for p in contracts.PAGES)
    assert 0 < len(bound) < total, (len(bound), total)


def test_a_bound_section_with_no_thread_is_refused():
    page, section = _thread_binding_sections()[0]
    body = {"produced_at": "2026-08-18T00:00:00Z", "producer_version": "t",
            "e_ids": [], "internal_only": []}
    hits = _ids(_reasons(page, {section: body}), "CG-23")
    assert hits, f"{page}.{section} sent no thread and was not refused"
    assert hits[0]["path"] == f"{section}.narrative_thread"
    assert hits[0]["severity"] == "block"


@pytest.mark.parametrize("thread", [None, "", "   ", "\n\t "])
def test_blank_is_not_a_thread(thread):
    page, section = _thread_binding_sections()[0]
    body = {"produced_at": "2026-08-18T00:00:00Z", "producer_version": "t",
            "e_ids": [], "internal_only": [], "narrative_thread": thread}
    assert _ids(_reasons(page, {section: body}), "CG-23")


def test_a_written_thread_passes():
    page, section = _thread_binding_sections()[0]
    body = {"produced_at": "2026-08-18T00:00:00Z", "producer_version": "t",
            "e_ids": [], "internal_only": [],
            "narrative_thread": "The line through this page, written last."}
    assert not _ids(_reasons(page, {section: body}), "CG-23")


# ── CG-24 · a rollup agrees with the rows it rolls up ──────────────────

def _ts(items, layers):
    return {"techstack": {
        "produced_at": "2026-08-18T00:00:00Z", "producer_version": "t",
        "e_ids": [], "internal_only": [], "narrative_thread": "thread",
        "items": items, "layers": layers}}


def _row(ts_id, layer, status):
    return {"ts_id": ts_id, "layer": layer, "status": status,
            "vendor": "Acme Corporation", "product": "Acme Core",
            "pillar_id": "P3", "evidence_level": "L2",
            "detection_basis": "named in a first-party artefact",
            "as_of": None, "linked_subcap_ids": [], "e_ids": ["E-CC-001"]}


def test_the_shape_that_shipped():
    """Six named OPS products beside detected: 0 on the OPS card."""
    items = [_row(f"TS-{i:03d}", "OPS", "INFERRED") for i in range(1, 7)]
    reasons = _ids(_reasons("techstack",
                            _ts(items, [{"layer": "OPS", "pillar_id": "P3",
                                         "detected": 0, "expected": 7}])),
                   "CG-24")
    assert reasons, "detected 0 against six detected rows was not refused"
    msg = reasons[0]["message"]
    # Charter invariant 12: a verdict names the gate, the path and the
    # ARITHMETIC. A reader of this message must not have to go and count.
    assert "detected=0" in msg and "6" in msg
    assert reasons[0]["path"] == "techstack.layers[0].detected"


def test_a_computed_rollup_passes():
    items = ([_row(f"TS-{i:03d}", "OPS", "CONFIRMED") for i in range(1, 4)]
             + [_row("TS-010", "OPS", "CLAIMED"),
                _row("TS-011", "OPS", "ABSENT"),
                _row("TS-020", "DATA", "INFERRED")])
    # OPS: five rows, one ABSENT -> four detected. DATA: one row, none absent.
    layers = [{"layer": "OPS", "pillar_id": "P3", "detected": 4, "expected": 7},
              {"layer": "DATA", "pillar_id": "P4", "detected": 1, "expected": 5}]
    assert not _ids(_reasons("techstack", _ts(items, layers)), "CG-24")


def test_absent_is_the_only_status_that_is_not_a_detection():
    """The definition, pinned, because there are two plausible ones.

    ABSENT means a slot was searched and nothing was found. CLAIMED means
    something was found on a supplier's word alone — weak, and the row's own
    badge says so. The frontend computes this figure by subtracting ABSENT
    (live-adapter.jsx techLayersOf), and two definitions of one word on one
    page is the defect this gate exists to refuse.
    """
    items = [_row("TS-001", "OPS", "CLAIMED"), _row("TS-002", "OPS", "ABSENT")]
    assert not _ids(_reasons("techstack",
                             _ts(items, [{"layer": "OPS", "pillar_id": "P3",
                                          "detected": 1, "expected": 7}])),
                    "CG-24")
    reasons = _ids(_reasons("techstack",
                            _ts(items, [{"layer": "OPS", "pillar_id": "P3",
                                         "detected": 2, "expected": 7}])),
                   "CG-24")
    assert reasons and "detected=2" in reasons[0]["message"]


def test_expected_is_a_judgement_and_is_not_checked():
    """A reference-class denominator is not a count of these rows.

    Deriving it from them makes it unfalsifiable: a register with no ABSENT
    rows then reads "15 of 15 detected", which is what a promoted client
    showed over a payload stating 12 of 17.
    """
    items = [_row("TS-001", "OPS", "CONFIRMED")]
    assert not _ids(_reasons("techstack",
                             _ts(items, [{"layer": "OPS", "pillar_id": "P3",
                                          "detected": 1, "expected": 40}])),
                    "CG-24")


def test_a_layer_with_no_rows_must_send_zero():
    reasons = _ids(_reasons("techstack",
                            _ts([_row("TS-001", "OPS", "CONFIRMED")],
                                [{"layer": "INFRA", "pillar_id": "P4",
                                  "detected": 2, "expected": 4}])),
                   "CG-24")
    assert reasons, "a layer with no register rows claimed two detections"


def test_status_and_layer_matching_is_case_and_space_insensitive():
    items = [{**_row("TS-001", " ops ", "confirmed")}]
    assert not _ids(_reasons("techstack",
                             _ts(items, [{"layer": "OPS", "pillar_id": "P3",
                                          "detected": 1, "expected": 7}])),
                    "CG-24")


def test_a_missing_detected_is_not_this_gates_business():
    """CG-01/CG-03 own a missing or mistyped field; this gate owns DISAGREEMENT.

    Two gates refusing one defect makes the verdict harder to act on, not
    safer.
    """
    assert not _ids(_reasons("techstack",
                             _ts([_row("TS-001", "OPS", "CONFIRMED")],
                                 [{"layer": "OPS", "pillar_id": "P3",
                                   "expected": 7}])), "CG-24")
