"""Foreign-variant cells dropped on the way out, not only refused on the way in.

ET-05 refuses a foreign variant at SUBMIT, so a payload promoted under a
resolvable sub-vertical cannot carry one. This is for payloads promoted when
the entity was NOT resolvable.

Until 2026-08-15 `resolve_subvertical` matched only the whole normalised
string, so 44 of the 93 corpus manifests carrying a sub-vertical would have
ingested with no scope at all — and an unresolved entity keeps every cell,
deliberately and silently. Widening the resolver turns those entities from
unscoped into scoped, which retroactively makes their already-promoted
payloads wrong. The gate cannot reach back. This can.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.subverticals import scope_sections  # noqa: E402


def _payload():
    return {
        "cells": [
            {"subcap_id": "P1C1.1.1", "synthesis": "base cell"},
            {"subcap_id": "P2C4.6.RIA1", "synthesis": "the entity's own"},
            {"subcap_id": "P1C1.3.IC1", "synthesis": "insurance carrier"},
            {"subcap_id": "P1C1.3.CU1", "synthesis": "credit union"},
            {"subcap_id": "P1C2.7.BK1", "synthesis": "depository FAMILY"},
        ],
        "alerts": [{"subcap_id": "P1C1.3.IC1", "severity": "high"},
                   {"subcap_id": "P3C1.2.1", "severity": "medium"}],
        "card": {"linked_subcap_ids": ["P1C1.1.1", "P1C1.3.IC1", "P2C4.6.RIA1"],
                 "text": "a sentence"},
    }


def test_it_drops_the_foreign_variants_and_keeps_everything_else():
    p = _payload()
    n = scope_sections("SV5 — RIAs & Broker-Dealers (Canada)", p)
    kept = [c["subcap_id"] for c in p["cells"]]
    assert kept == ["P1C1.1.1", "P2C4.6.RIA1", "P1C2.7.BK1"], kept
    assert [a["subcap_id"] for a in p["alerts"]] == ["P3C1.2.1"]
    assert p["card"]["linked_subcap_ids"] == ["P1C1.1.1", "P2C4.6.RIA1"]
    assert n == 4, f"counted {n}; two cells, one alert, one citation"


def test_the_count_is_returned_so_a_caller_need_not_trust_it():
    """Invariant 8: counted from what was actually dropped, never assumed."""
    assert scope_sections("SV2", {"cells": []}) == 0
    assert scope_sections("SV2", {"cells": [{"subcap_id": "P1C1.3.CU1"}]}) == 0


def test_an_unresolved_entity_drops_nothing():
    """The one-sided rule, preserved: over-excluding hides a score the
    assessment actually made, and that is the worse direction."""
    p = _payload()
    assert scope_sections("HIGH", p) == 0
    assert len(p["cells"]) == 5
    assert scope_sections(None, p) == 0
    assert len(p["cells"]) == 5


def test_a_family_or_product_variant_is_never_foreign():
    """`BK` is the depository family and `PEN` a product line — neither names
    one sub-vertical, so neither is evidence of belonging to somebody else."""
    p = {"cells": [{"subcap_id": "P1C2.7.BK1"}, {"subcap_id": "P3C4.2.PEN1"},
                   {"subcap_id": "P1C1.3.WM1"}]}
    assert scope_sections("SV2", p) == 0
    assert len(p["cells"]) == 3


def test_it_recurses_into_nested_sections():
    p = {"outer": {"inner": {"items": [
        {"subcap_id": "P1C1.3.IC1"}, {"subcap_id": "P1C1.1.1"}]}}}
    assert scope_sections("SV2", p) == 1
    assert len(p["outer"]["inner"]["items"]) == 1


def test_a_scalar_cell_id_drops_its_whole_object():
    """A synthesis card ABOUT a cell that does not apply is not improved by
    deleting the id and leaving the prose — the sentence goes with it."""
    p = {"cards": [{"subcap_id": "P1C1.3.IC1",
                    "what_text": "prose that rests on a foreign cell"}]}
    scope_sections("SV2", p)
    assert p["cards"] == []


def test_non_cell_lists_are_untouched():
    """`e_ids` and prose lists must survive: dropping an evidence id because
    it is not a cell id would be the over-exclusion this rule avoids."""
    p = {"e_ids": ["E-CC-001", "E-CC-002"],
         "sources_searched": ["glassdoor.com", "sedarplus.ca"],
         "cells": [{"subcap_id": "P1C1.3.IC1"}]}
    assert scope_sections("SV2", p) == 1
    assert p["e_ids"] == ["E-CC-001", "E-CC-002"]
    assert len(p["sources_searched"]) == 2


def test_it_runs_before_redaction_in_the_serve_path():
    """Ordering, asserted on the source. Scoping after redaction would work
    on a body whose internal_only paths are already gone — and a cell id can
    live under one."""
    src = (ROOT / "apps" / "api" / "dma_api" / "pages.py").read_text()
    assert src.index("scope_sections(") < src.index("redact_section(page, section")
    assert src.index("computed_apply(cur, page") < src.index("scope_sections(")
