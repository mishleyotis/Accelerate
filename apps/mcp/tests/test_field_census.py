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

The section-level sweep alone was not enough, twice over:

  · It looked only at the keys a SECTION declares, so the ITEM level — the
    keys a section's item shape states as `Per issue: {…}` — was never
    resolved against the writer's `item:` bindings at all.
    `context.issue_register.issues[].capped_subcap_ids` was validated at
    submit and dropped at promote for exactly as long as that hole existed,
    and with it the finding's anchor score, the opportunity tile's headline
    and the stack row's verification date. The item-level sweep below is
    the same test one level down.
  · The item shape is stated in PROSE, and the expression that reads it
    (`validation2._PER_ITEM_RE`) recognises the lead-in by noun. A section
    whose noun is missing from that list opts out of both this census and
    AG-03 silently — which is what `Per issue:` did. So a shape that cannot
    be parsed is a FAILURE here, not a skip.

**Upstream**: a gate registry that names a field the contract does not
declare polices nothing, silently, forever. Every path in the new
registries (`_ITEM_DATING`, `_FACE_BUDGETS`) is therefore resolved against
the contract here, so a field renamed in `contracts_data.json` breaks this
test rather than quietly switching a gate off.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import ENVELOPE, SECTION_META, sections
from dma_mcp.gates import GATES
from dma_mcp.validation import (_CONTRACT_VOCABULARIES, _FACE_BUDGETS,
                                _ITEM_DATING)
from dma_mcp.validation2 import _PER_ITEM_RE

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

# The ITEM-level equivalent: keys a section's item shape declares that no
# `item:` column stores, each with the source it is recomputed from at read.
# Nothing else may be absent. `-R` a key from a writer without landing it here
# and the sweep below says so by name.
ITEM_COMPUTED_AT_READ = {
    ("heatmap", "cell_evidence", "items"):
        "the resolved form of the row's own e_ids — one evidence_index row per "
        "id, which is exactly {e_id, tier, claim_label, recency, source_title, "
        "publisher, excerpt}. grounded_on is GENERATED as the length of that "
        "very array, so storing the objects too would be the second code path "
        "invariant 8 forbids",
    ("heatmap", "cell_evidence", "thin"):
        "grounded_on < 3 — the contract's own rule ('below three linked items, "
        "mark the cell thin'), computed from a GENERATED column",
}


def _item_shape(page: str, section: str, item_field: str):
    """The item keys a section's contract states in prose, or None.

    The shape lives in the `doc` text and nowhere else, so this reads it with
    the SAME expression the validator's AG-03 uses. That is deliberate: if the
    expression cannot see a section's shape then AG-03 cannot either, and both
    the citation gate and this census switch themselves off for that section
    without saying so.
    """
    fields = sections(page)[section]["fields"]
    spec = fields.get(item_field.split(".")[0])
    if spec is None:
        return None
    doc = spec.get("doc") or ""
    m = _PER_ITEM_RE.search(doc) or re.search(
        re.escape(item_field.split(".")[0]) + r"\[\]\s*\{([^}]*)\}", doc)
    if not m:
        return None
    return [k.strip().rstrip("[]") for k in m.group(1).split(",")
            if re.match(r"^[a-z_][a-z0-9_]*\[?\]?$", (k or "").strip())]


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


def test_an_item_level_contract_key_is_either_stored_or_deliberately_computed():
    """CG-13 one level down — the sweep that was missing entirely.

    A section's items are where the client actually reads: the issue with the
    cells it caps, the finding with the score its chip quotes, the stack row
    with the date it was verified. Every one of those was validated at submit
    and dropped at promote because the writer had no `item:` column for it, and
    the section-level sweep could not see them because they are not section
    fields. `capped_subcap_ids` is the case that named this test.

    Bound means an `item:` source claims the key, or a GENERATED column
    computes it. A column that merely SHARES the key's name is not enough —
    `platform_roadmap.capabilities` holds rec_ids by its own DDL comment, so
    matching on name would have declared the contract's separate capabilities[]
    stored when it was being discarded.
    """
    spec = json.loads(_SPEC.read_text())
    orphans, unreadable = [], []
    for page_spec in spec["specs"]:
        for w in page_spec["writers"]:
            page, name, item_field = page_spec["page"], w["section"], w.get("item_field")
            if not item_field:
                continue                  # run grain: the section IS the row
            item_paths, generated = set(), set()
            for c in w["columns"]:
                kind, _, rest = c["source"].partition(":")
                if kind == "item":
                    item_paths.add(rest.split(".")[0])
                elif kind == "skip" and "GENERATED ALWAYS" in rest:
                    generated.add(c["column"].strip('"'))
            keys = _item_shape(page, name, item_field)
            if keys is None:
                unreadable.append(f"{page}.{name}.{item_field}")
                continue
            for key in keys:
                if key in item_paths or key in generated:
                    continue
                if (page, name, key) in ITEM_COMPUTED_AT_READ:
                    continue
                orphans.append(f"{page}.{name}.{item_field}[].{key}")
    assert not unreadable, (
        "an item shape validation2._PER_ITEM_RE cannot parse — the section is "
        "invisible to BOTH this census and AG-03's citation check, silently. "
        "Add its lead-in noun to _PER_ITEM_RE: " + ", ".join(sorted(unreadable)))
    assert not orphans, (
        "CG-13: item-level contract keys with no column and no recorded "
        "reason — each is validated at submit and then discarded at "
        "promotion: " + ", ".join(sorted(orphans)))


def test_the_item_provenance_column_does_not_take_the_envelope_s():
    """Two facts, two columns, and neither may eat the other.

    The envelope's `provenance` says who produced the SECTION and is the
    submission-level stamp the serving envelope reads; the contract's per-item
    `provenance` says how THIS row was arrived at. Sourcing one column from
    both is how the per-item value came to be validated and then dropped — and
    rebinding the envelope column to the item would have traded that for a
    section stamp that serves NULL. So: wherever an item declares provenance,
    the writer carries both, from different sources.
    """
    spec = json.loads(_SPEC.read_text())
    for page_spec in spec["specs"]:
        for w in page_spec["writers"]:
            item_field = w.get("item_field")
            if not item_field:
                continue
            keys = _item_shape(page_spec["page"], w["section"], item_field) or []
            sources = {c["column"].strip('"'): c["source"] for c in w["columns"]}
            assert sources.get("provenance") == "sys:provenance", (
                f"{page_spec['page']}.{w['section']}: the envelope's provenance "
                "column must stay the submission stamp")
            if "provenance" in keys:
                assert sources.get("item_provenance") == "item:provenance", (
                    f"{page_spec['page']}.{w['section']} declares a per-item "
                    "provenance and has nowhere to put it")


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


def test_the_storyline_challenge_record_has_somewhere_to_land():
    """0044. The skill tells a producer to put the storyline through five
    adversarial volleys before promoting and to record each challenge, the
    answer and what changed. Nothing declared it: not the contract, so
    CG-04 never swept it; not the writer spec, so promote had nowhere to
    put it; not the schema, so there was no column. A producer following
    the skill wrote the record and it was dropped in the same transaction
    that promoted the storyline it defends.

    Contract, column and writer binding land together, because each one
    alone is a defect this build has already shipped twice."""
    import json
    from pathlib import Path
    from dma_mcp.contracts import sections

    field = sections("overview")["exec_summary"]["fields"].get("storyline_challenge")
    assert field, "the contract must declare what the skill asks for"
    doc = field["doc"]
    for expected in ("volleys", "challenger", "outcome", "survived",
                     "held", "changed", "REQUIRED"):
        assert expected in doc, expected
    assert "finding" in doc, "five held outcomes is a finding, not a triumph"

    for path in ("apps/mcp/dma_mcp/writer_spec.json",
                 "apps/api/dma_api/writer_spec.json"):
        spec = json.loads((Path(__file__).resolve().parents[3] / path).read_text())
        cols = [c for p in spec["specs"] for w in p["writers"]
                if w["table"] == "overview_exec_summary" for c in w["columns"]]
        binding = [c for c in cols if c["column"] == "storyline_challenge"]
        assert binding, f"{path}: no writer binding"
        assert binding[0]["source"] == "section:storyline_challenge"
        assert binding[0]["jsonb"] is True


def test_the_challenge_record_is_internal_by_construction():
    """It is the r_layer's family — our preparation for the room, not the
    client's assessment — so it is stripped by KEY rather than left to a
    producer's marking, from the moment the field exists."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "api"))
    from dma_api.redaction import CUSTOMER_STRIP_KEYS, redact_section
    assert "storyline_challenge" in CUSTOMER_STRIP_KEYS

    data = {"situation": "A credit union with 370,000 members.",
            "storyline_challenge": {"survived": True, "volleys": [
                {"volley": 1, "challenger": "incumbent_vendor",
                 "challenge": "You are describing our roadmap as a gap.",
                 "outcome": "held"}]}}
    out, rep = redact_section("overview", "exec_summary", dict(data), [], "customer")
    assert "storyline_challenge" not in out
    assert out["situation"] == data["situation"]
    assert "storyline_challenge" in rep["keys_stripped"]
    keep, _ = redact_section("overview", "exec_summary", dict(data), [], "internal")
    assert keep["storyline_challenge"]["survived"] is True
