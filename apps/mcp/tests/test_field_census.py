"""CG-13 — every required field, and every field a gate names, has
somewhere to live.

The recurring defect this build keeps shipping, in two directions.

**Downstream**: a required contract field with no column is validated at
submit and then discarded at promotion. `context_sentiment.context_tiles`,
the leadership contact route and `techstack.dropped` each rendered empty
under a real client's name and nothing failed. The sweep already exists on
the serving side (`apps/api/tests/test_serving_read_path.py`); it is
mirrored here over the CONNECTOR's own writer spec, which is the copy
promote actually walks — the two files are identical today and a divergence
is itself the defect.

**Upstream**: a gate registry that names a field the contract does not
declare polices nothing, silently, forever. Every path in the new
registries (`_ITEM_DATING`, `_FACE_BUDGETS`) is therefore resolved against
the contract here, so a field renamed in `contracts_data.json` breaks this
test rather than quietly switching a gate off.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import ENVELOPE, SECTION_META, sections
from dma_mcp.gates import GATES
from dma_mcp.validation import (_CONTRACT_VOCABULARIES, _FACE_BUDGETS,
                                _ITEM_DATING)

_SPEC = Path(__file__).resolve().parents[1] / "dma_mcp" / "writer_spec.json"

# Required, and deliberately NOT persisted — each recomputed at read from a
# source of truth that already exists, with that source named. Same register
# as the serving-side sweep; kept verbatim so a divergence is visible as a
# diff rather than as an argument.
COMPUTED_AT_READ = {
    ("overview", "firmographics", "undated_pct"): "share of fields[] with no as_of",
    ("overview", "evidence_coverage", "item_count"): "census of the evidence store",
    ("overview", "evidence_coverage", "fact_count"): "census of the evidence store",
    ("overview", "evidence_coverage", "tiers"): "tier histogram of the evidence store",
    ("overview", "evidence_coverage", "claim_classes"): "claim histogram of the evidence store",
    ("overview", "evidence_coverage", "self_sourced_pct"): "share of items on the entity's own domains",
    ("insights", "landscape", "tiles"): "recomputed from the techstack register",
    ("insights", "landscape", "reconciles_to_register"): "the assertion, not the counts",
    ("techstack", "techstack", "layers"): "rollup over techstack_items (techLayersOf)",
    ("heatmap", "cell_evidence", "linking_stats"): "reach counters over cells[]",
    ("heatmap", "evidence_age", "stale_pct"): "share of rows[] banded stale",
    ("heatmap", "evidence_age", "undated_pct"): "share of rows[] with no date",
    ("heatmap", "safeguard_gates", "gates"): "gate_results, written by the connector",
    ("heatmap", "evidence", "evidence"): "evidence_index (ingested tier)",
    ("heatmap", "workbook_scores", "pillars"): "expanded to rows by _expand_h4_maps",
    ("heatmap", "workbook_scores", "categories"): "expanded to rows by _expand_h4_maps",
}


def _bound():
    spec = json.loads(_SPEC.read_text())
    out = {}
    for page_spec in spec["specs"]:
        for w in page_spec["writers"]:
            keys = set()
            for c in w["columns"]:
                kind, _, rest = c["source"].partition(":")
                if kind in ("item", "section"):
                    keys.add(rest.split(".")[0])
            out[(page_spec["page"], w["section"])] = (keys, w.get("item_field"))
    return out


def test_a_required_field_is_either_stored_or_deliberately_computed():
    orphans = []
    for (page, name), (keys, item_field) in _bound().items():
        fields = sections(page)[name]["fields"]
        for fname, spec in fields.items():
            if not spec.get("required"):
                continue
            if fname in ENVELOPE or fname in SECTION_META:
                continue                 # env: / section: bindings
            if fname in keys or fname == item_field:
                continue                 # stored
            if (page, name, fname) in COMPUTED_AT_READ:
                continue                 # deliberate, and its source is named
            orphans.append(f"{page}.{name}.{fname}")
    assert not orphans, (
        "CG-13: required contract fields with no column and no recorded "
        "reason — each is validated at submit and then discarded at "
        "promotion: " + ", ".join(sorted(orphans)))


def test_the_connector_and_the_serving_tier_walk_the_same_writer_spec():
    """Two copies of one spec. Promote writes from the connector's; the
    read path and the serving-side census read the API's. A divergence is
    the same defect class one level up — a column that exists on one side
    of the boundary and not the other."""
    api = (Path(__file__).resolve().parents[3] / "apps" / "api" / "dma_api"
           / "writer_spec.json")
    if not api.exists():
        return                            # connector image: nothing to compare
    assert json.loads(api.read_text()) == json.loads(_SPEC.read_text())


def test_every_field_a_gate_registry_names_exists_in_the_contract():
    """A registry entry pointing at a field the contract does not declare
    is a gate that is switched off and says nothing about it."""
    missing = []
    registries = [("CG-10", {k: (v[0],) for k, v in _ITEM_DATING.items()}),
                  ("CG-12", {k: tuple(e[0] for e in v)
                             for k, v in _FACE_BUDGETS.items()}),
                  ("CG-09", {k: tuple(v) for k, v in
                             _CONTRACT_VOCABULARIES.items()})]
    for gate, registry in registries:
        for key, paths in registry.items():
            page, _, name = key.partition(".")
            fields = sections(page).get(name, {}).get("fields")
            if fields is None:
                missing.append(f"{gate}: {key} is not a section")
                continue
            for path in paths:
                container = path.partition("[")[0].partition(".")[0]
                if container not in fields:
                    missing.append(f"{gate}: {key}.{container}")
    assert not missing, ("gate registries naming fields no contract "
                         "declares: " + ", ".join(missing))


def test_every_gate_a_validator_can_emit_is_in_the_registry():
    """"A gate id absent from this registry cannot appear in a verdict" —
    asserted, rather than trusted, over every module that emits one."""
    import re
    emitted = set()
    for module in ("validation.py", "validation2.py", "vacuity.py"):
        src = (_SPEC.parent / module).read_text()
        emitted.update(re.findall(r'"((?:AG|SG|ET|CG)-[A-Z0-9]{2})"', src))
    assert emitted <= set(GATES), sorted(emitted - set(GATES))
    # and the seven added this round are all there
    assert {"CG-10", "CG-11", "CG-12", "CG-13", "CG-14",
            "ET-04", "ET-05"} <= set(GATES)
    # CG-15 lives in its own module; the sweep has to reach it, or the
    # invariant is asserted over the two files that happen to be listed.
    assert "CG-15" in emitted and "CG-15" in GATES
