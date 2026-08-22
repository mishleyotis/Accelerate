"""Stage 2.1 QA bullets — the contract registry.

- Every section has a contract, and the count reconciles with the
  serving-table list (34 sections, 6 pages, 32 required).
- No list-of-object field lacks doc text stating its item keys.
- The contract tool returns doc text verbatim.
- The universal envelope is on every section.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import (ENVELOPE, PAGES, SERVING_TABLES, all_sections,
                               get_page_contract, registry, sections)

EXPECTED_COUNTS = {"heatmap": 9, "overview": 12, "insights": 2,
                   "platform": 5, "context": 5, "techstack": 1}


def test_thirty_four_sections_reconcile_with_the_serving_tables():
    secs = all_sections()
    assert len(secs) == 34
    for page, n in EXPECTED_COUNTS.items():
        assert len(sections(page)) == n, page
    # every section maps to a serving table, and no table is orphaned
    assert set(secs) == set(SERVING_TABLES)
    assert len(set(SERVING_TABLES.values())) == 34  # incl. evidence_index
    # 32 of 34 are required
    required = [s for p, s in secs if sections(p)[s].get("required", True)]
    assert len(required) == 32


def test_every_list_of_object_field_states_its_item_keys():
    for page, name in all_sections():
        for fname, spec in sections(page)[name]["fields"].items():
            if spec["type"] == "list" and spec.get("item_type") == "object":
                doc = spec["doc"]
                assert re.search(r"\{[^}]+\}", doc), (
                    f"{page}.{name}.{fname}: list-of-object with no item "
                    f"schema in doc — the agent would have to guess")


def test_envelope_is_universal_and_returned_verbatim():
    for page in PAGES:
        contract = get_page_contract(page)
        for name, sec in contract["sections"].items():
            for env_field in ENVELOPE:
                assert env_field in sec["fields"], f"{page}.{name}.{env_field}"
            # verbatim: the served doc string is the registry's doc string
            for fname, spec in sec["fields"].items():
                assert spec["doc"] == sections(page)[name]["fields"][fname]["doc"]


def test_no_colour_reaches_any_contract():
    for page, name in all_sections():
        for fname, spec in sections(page)[name]["fields"].items():
            assert not re.search(r"hex|#[0-9A-Fa-f]{6}|colou?r_code", fname), fname
            assert "#185F60" not in spec["doc"]   # the M5 hex must not exist


def test_no_gate_id_is_defined_twice():
    """A duplicate key in the GATES literal is silent: Python keeps the last
    one, so an earlier definition vanishes and a verdict citing that id gets
    somebody else's description.

    Measured 2026-08-14: CG-16 and CG-17 were added for must-present members
    and empty required lists while the SAME ids were already in use as the two
    transport gates. The registry kept the transport pair, the new entries
    disappeared from `explain_gate`, and the validator went on emitting ids
    that resolved to the wrong explanation. Renumbered to CG-18/CG-19; this
    test is what makes the next collision a failure instead of a silence.
    """
    import re
    from collections import Counter
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "dma_mcp" / "gates.py"
    ids = re.findall(r'^\s*"([A-Z]{2}-\d+)":', src.read_text(), re.M)
    dupes = sorted(k for k, n in Counter(ids).items() if n > 1)
    assert not dupes, f"gate ids defined more than once: {dupes}"


def test_every_gate_the_validator_emits_is_in_the_registry():
    """A verdict may only name a gate the registry can explain."""
    import re
    from pathlib import Path

    from dma_mcp.gates import GATES

    root = Path(__file__).resolve().parents[1] / "dma_mcp"
    emitted = set()
    for mod in ("validation.py", "validation2.py", "transport.py"):
        emitted |= set(re.findall(r'_reason\(\s*"([A-Z]{2}-\d+)"',
                                  (root / mod).read_text()))
    missing = sorted(emitted - set(GATES))
    assert not missing, f"emitted but unregistered: {missing}"
