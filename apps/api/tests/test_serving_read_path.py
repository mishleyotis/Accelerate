"""Stage 5 QA: the serving read path.

The load-bearing invariant is that writer ∘ reader is the identity for
every field the spec maps — the connector decomposes a section payload
into columns and the API puts it back, from ONE description of the
mapping. These tests drive the connector's real writer helpers, so a
column that moves in the spec cannot move in only one direction.

The redaction tests are the other half: default-deny, server-side, and
verified on the produced object rather than by reading the marking logic.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_api.pages import etag_for                              # noqa: E402
from dma_api.redaction import (CUSTOMER_WITHHELD, page_forbidden,  # noqa: E402
                               redact_section)
from dma_api.serving_spec import assemble, page_sections, readers  # noqa: E402
from dma_mcp.promote import _expand_h4_maps, _value               # noqa: E402

STAMPS = {"run_id": "11111111-1111-1111-1111-111111111111",
          "entity_id": "22222222-2222-2222-2222-222222222222",
          "promoted_at": "2026-08-05T04:00:00+00:00",
          "producer_version": "test@1", "provenance": "producer"}


def write_rows(page: str, section: str, payload: dict) -> list[dict]:
    """What promote would INSERT for this section, as column dicts — the
    same _value() the connector writes with."""
    r = readers()[(page, section)]
    if r["grain"] == "run":
        items = [None]
    elif r["item_field"]:
        items = payload.get(r["item_field"]) or []
    else:
        items = _expand_h4_maps(payload)
    rows = []
    for item in items:
        row = {}
        for col, source in _sources(page, section).items():
            v = _value(source, STAMPS, payload, item)
            if v is ...:
                continue
            row[col] = json.dumps(v) if isinstance(v, (dict, list)) else v
        rows.append(row)
    return rows


def _sources(page: str, section: str) -> dict:
    spec = json.loads((ROOT / "apps" / "api" / "dma_api" / "writer_spec.json").read_text())
    for p in spec["specs"]:
        if p["page"] != page:
            continue
        for w in p["writers"]:
            if w["section"] == section:
                return {c["column"]: c["source"] for c in w["columns"]}
    raise KeyError(f"{page}.{section}")


def test_writer_spec_is_one_file_in_two_places():
    """Both services read the mapping; drift between the copies would let a
    column move in one direction only."""
    a = (ROOT / "apps" / "mcp" / "dma_mcp" / "writer_spec.json").read_bytes()
    b = (ROOT / "apps" / "api" / "dma_api" / "writer_spec.json").read_bytes()
    assert a == b, "writer_spec.json copies have drifted"


def test_every_section_has_a_reader_and_the_order_is_stable():
    pages = ("heatmap", "overview", "insights", "platform", "context", "techstack")
    total = sum(len(page_sections(p)) for p in pages)
    assert total == 34, f"34 section writers expected, {total} readable"
    # order is load-bearing: the same list, twice
    assert page_sections("overview") == page_sections("overview")
    assert page_sections("overview")[0] == "scores"


def test_round_trip_run_grain_section():
    payload = {"situation": "A credit union with 370,000 members.",
               "complication": "The data layer trails the strategy layer.",
               "question": "Fix the foundation or fund the next feature?",
               "answer": "Foundation first, then service consolidation.",
               "sequencing_rationale": "Two caps lift together.",
               "cost_of_delay": "A merger lands on point-to-point plumbing.",
               "claim_label": "FACT",
               "produced_at": "2026-08-05T04:00:00+00:00",
               "producer_version": "test@1",
               "e_ids": ["E-BCU-061", "E-BCU-066"], "internal_only": []}
    rows = write_rows("overview", "exec_summary", payload)
    built = assemble("overview", "exec_summary", rows)
    for k in ("situation", "complication", "question", "answer",
              "sequencing_rationale", "cost_of_delay"):
        assert built["data"][k] == payload[k], k
    assert built["env"]["e_ids"] == payload["e_ids"]
    assert built["stamps"]["producer_version"] == "test@1"


def test_round_trip_item_grain_section():
    payload = {"focus_areas": [
        {"fa_id": "FA-1", "name": "Unify the member-data foundation",
         "verbatim_quote": "awash in data but no strategy",
         "source_document": "PYMNTS panel", "source_page": None,
         "involved_subcap_ids": ["P4C1.1.2", "P4C1.1.3"],
         "entity_score": 1.95, "peer_score": 2.5,
         "currency_status": "CONFIRMED_CURRENT",
         "currency_note": "Restated on a panel in August 2025."},
        {"fa_id": "FA-2", "name": "Extend the agentic pattern",
         "verbatim_quote": "exciting first steps to become an agentic enterprise",
         "source_document": "Salesforce story", "source_page": None,
         "involved_subcap_ids": ["P2C3.1.6"],
         "entity_score": 2.12, "peer_score": 3.0,
         "currency_status": "CONFIRMED_CURRENT",
         "currency_note": "Published January 2026."}],
        "produced_at": "2026-08-05T04:00:00+00:00", "producer_version": "test@1",
        "e_ids": ["E-BCU-058"], "internal_only": []}
    rows = write_rows("heatmap", "focus_areas", payload)
    assert len(rows) == 2
    built = assemble("heatmap", "focus_areas", rows)
    got = built["data"]["focus_areas"]
    assert [x["fa_id"] for x in got] == ["FA-1", "FA-2"]
    assert got[0]["involved_subcap_ids"] == ["P4C1.1.2", "P4C1.1.3"]
    assert got[1]["entity_score"] == 2.12
    assert got[0]["verbatim_quote"] == "awash in data but no strategy"


def test_per_item_citations_survive_the_round_trip():
    """The defect this pins: why_now's e_ids column was bound to the
    section envelope, so four signals that were each submitted with their
    own citation all arrived empty and every card read 'no evidence yet'.
    At item grain the column is the ITEM's citation list, and the section
    envelope is the union over items — computed, never stored."""
    payload = {"signals": [
        {"wn_id": "WN-1", "trigger": "A merger was announced in June 2026.",
         "window": "Runs from announcement to conversion.",
         "e_ids": ["E-CC-004", "E-BCU-032"]},
        {"wn_id": "WN-2", "trigger": "A leadership evolution dated July 2026.",
         "window": "New-leadership agendas set within the first quarter.",
         "e_ids": ["E-CC-003"]}],
        "produced_at": "2026-08-05T04:00:00+00:00", "producer_version": "test@1",
        "e_ids": ["E-CC-004", "E-BCU-032", "E-CC-003"], "internal_only": []}
    built = assemble("overview", "why_now",
                     write_rows("overview", "why_now", payload))
    signals = built["data"]["signals"]
    assert [s["e_ids"] for s in signals] == [["E-CC-004", "E-BCU-032"], ["E-CC-003"]]
    # the union, in first-seen order, with no duplicates
    assert built["env"]["e_ids"] == ["E-CC-004", "E-BCU-032", "E-CC-003"]


def test_the_envelope_union_follows_the_column_not_the_key():
    """The same union, where the item key is NOT `e_ids`.

    insight_cards binds `e_ids <- item:supporting_e_ids`, so the column is
    consumed by the item and no `env:e_ids` binding remains. The guard tested
    the payload KEYS for `e_ids` — which by construction is not among them —
    so every insights section served with no envelope citations while each
    card carried its own. The test is on the column."""
    payload = {"cards": [
        {"ic_id": "IC-01", "title": "Three cores, one member",
         "severity": "critical", "linked_subcap_id": "P4C1.1.1",
         "supporting_e_ids": ["E-BCU-016", "E-BCU-020"]},
        {"ic_id": "IC-02", "title": "Servicing load sits on manual work",
         "severity": "high", "linked_subcap_id": "P3C2.4.2",
         "supporting_e_ids": ["E-BCU-020", "E-CC-010"]}],
        "produced_at": "2026-08-05T04:00:00+00:00", "producer_version": "test@1",
        "e_ids": ["E-BCU-016", "E-BCU-020", "E-CC-010"], "internal_only": []}
    built = assemble("insights", "insights",
                     write_rows("insights", "insights", payload))
    cards = built["data"]["cards"]
    assert [c["supporting_e_ids"] for c in cards] == [
        ["E-BCU-016", "E-BCU-020"], ["E-BCU-020", "E-CC-010"]], \
        "the per-card citation list is what the adapter reads"
    assert built["env"]["e_ids"] == ["E-BCU-016", "E-BCU-020", "E-CC-010"], \
        "deduplicated union in first-seen order, computed not stored"


def test_a_reserved_word_column_is_read_under_its_bare_name():
    """`window` is quoted in the spec because PostgreSQL reserves it. The
    writer needs the quotes; the reader must not keep them, or the driver's
    bare key never matches and the field silently vanishes from the card."""
    assert "window" in readers()[("overview", "why_now")]["item_cols"]
    for (page, section), r in readers().items():
        for group in ("item_cols", "section_cols", "env_cols", "sys_cols"):
            for col in r[group]:
                assert '"' not in col, f"{page}.{section}.{group}: {col!r} kept its quoting"


def test_round_trip_h4_object_maps():
    """H4's pillars/categories are object MAPS, flattened to rows by the
    expander; the reader must put them back under the right key."""
    payload = {"pillars": {"P1": {"score": 3.11, "peer_median": 2.9,
                                  "source_cell": "Pillar_Summary!C2"},
                           "P4": {"score": 2.53, "peer_median": 2.88,
                                  "source_cell": "Pillar_Summary!C5"}},
               "categories": {"P4C1": {"score": 1.95, "peer_median": 2.5,
                                       "source_cell": "Category_Detail!D15"}},
               "produced_at": "2026-08-05T04:00:00+00:00",
               "producer_version": "test@1", "e_ids": [], "internal_only": []}
    rows = write_rows("heatmap", "workbook_scores", payload)
    assert len(rows) == 3
    built = assemble("heatmap", "workbook_scores", rows)
    assert set(built["data"]["pillars"]) == {"P1", "P4"}
    assert built["data"]["pillars"]["P1"]["score"] == 3.11
    assert built["data"]["pillars"]["P4"]["peer_median"] == 2.88
    assert set(built["data"]["categories"]) == {"P4C1"}
    assert built["data"]["categories"]["P4C1"]["source_cell"] == "Category_Detail!D15"


def test_a_section_that_did_not_promote_is_not_an_empty_section():
    assert assemble("overview", "exec_summary", []) is None


# ── redaction ──────────────────────────────────────────────────────────
def test_customer_audience_strips_marked_paths_only():
    data = {"rows": [{"e_id": "E-1", "ers": 4.5, "scoring_rationale": "internal"},
                     {"e_id": "E-2", "ers": 2.1, "scoring_rationale": "internal"}],
            "undated_pct": 0.0}
    internal = ["rows[*].ers", "rows[*].scoring_rationale"]
    out, rep = redact_section("heatmap", "evidence_age", dict(data), internal, "internal")
    assert out["rows"][0]["ers"] == 4.5, "internal audience keeps marked fields"

    out, rep = redact_section("overview", "evidence_coverage", json.loads(json.dumps(data)),
                              internal, "customer")
    assert all("ers" not in r and "scoring_rationale" not in r for r in out["rows"])
    assert out["rows"][0]["e_id"] == "E-1", "unmarked fields survive"
    assert out["undated_pct"] == 0.0
    assert set(rep["paths_stripped"]) == set(internal)


def test_cohort_entity_ids_are_stripped_for_every_audience():
    """Charter invariant 5: audit-only, and never dependent on a producer
    remembering to mark them."""
    payload = {"threshold_pct": 60.0,
               "patterns": [{"category_id": "P4C1", "share_pct": 67.0,
                             "entity_ids": ["e1", "e2", "e3", "e4"]}],
               "insufficient_cohorts": [{"sub_vertical": "SV2", "entity_count": 1,
                                         "entity_ids": ["e9"]}]}
    for audience in ("internal", "customer"):
        out, _ = redact_section("heatmap", "cohort_patterns",
                                json.loads(json.dumps(payload)), [], audience)
        if out is None:            # withheld entirely from the customer
            assert audience == "customer"
            continue
        assert "entity_ids" not in out["patterns"][0]
        assert out["patterns"][0]["share_pct"] == 67.0
        assert "entity_ids" not in out["insufficient_cohorts"][0]


def test_withheld_sections_and_pages():
    for section in ("ceilings", "sentiment", "thought_leadership"):
        assert ("overview", section) in CUSTOMER_WITHHELD
        out, rep = redact_section("overview", section, {"rows": [1]}, [], "customer")
        assert out is None and rep["withheld"] is True
        keep, _ = redact_section("overview", section, {"rows": [1]}, [], "internal")
        assert keep == {"rows": [1]}
    assert page_forbidden("context", "customer", None), "D5 is locked, not partial"
    assert page_forbidden("context", "internal", "AE"), "an AE has no Context route"
    assert page_forbidden("overview", "customer", "AE") is None
    assert page_forbidden("context", "internal", "ANALYST") is None


def test_redaction_never_mutates_the_shared_payload():
    # a section that is redacted rather than withheld
    data = {"rows": [{"ers": 4.5}]}
    out, _ = redact_section("heatmap", "cell_evidence", data, ["rows[*].ers"], "customer")
    assert data["rows"][0]["ers"] == 4.5, "the promoted payload is shared across readers"
    assert "ers" not in out["rows"][0]


def test_etag_carries_run_promotion_and_audience():
    run = {"run_id": "abc", "promoted_at": "2026-08-05T04:00:00+00:00"}
    internal = etag_for(run, "internal")
    customer = etag_for(run, "customer")
    assert internal.startswith('W/"abc.') and internal.endswith('.internal"')
    assert internal != customer, "one run serves two documents"
    assert etag_for({"run_id": "abc", "promoted_at": None}, "internal") == 'W/"abc.0.internal"'


def test_active_run_predicate_matches_the_real_enum():
    """runs.status is run_status_t (INGESTED · CLAIMED · SYNTHESISING ·
    STAGED · PROMOTED · SUPERSEDED) — there is no 'ACTIVE' value, and
    comparing against one aborts the query with 22P02. The active run is
    the one promote flagged: is_active AND promoted_at IS NOT NULL."""
    src = (ROOT / "apps" / "api" / "dma_api" / "pages.py").read_text()
    assert "status = 'ACTIVE'" not in src
    # resolution reads the one view svc_api is granted, never the base
    # tables (svc_api holds no SELECT on entities or runs by design)
    assert "FROM serving_directory" in src
    assert "FROM entities" not in src and "FROM runs" not in src
    # and the envelope reports status and the active flag separately
    assert '"status": picked[9]' in src and '"is_active": bool(picked[8])' in src


def test_generated_columns_are_read_back_read_only():
    """band, delta, grounded_on, age_months/band/status, share_pct and
    below_threshold are GENERATED ALWAYS: the database computes them from the
    promoted values, and they are exactly the figures the surfaces show. The
    writer never writes them; the reader must still return them."""
    r = readers()[("heatmap", "evidence_age")]
    assert set(r["derived_cols"]) == {"age_months", "band", "status"}
    assert readers()[("heatmap", "workbook_scores")]["derived_cols"] == ["band", "delta"]
    assert readers()[("overview", "scores")]["derived_cols"] == ["band"]
    assert readers()[("heatmap", "cell_evidence")]["derived_cols"] == ["grounded_on"]

    # item grain: the DB's value lands on the item, beside the written ones
    rows = [{"e_id": "E-1", "title": "NCUA data", "source_domain": "ncua.gov",
             "published_or_asof": "2025-09-01", "reference_date": "2026-03-30",
             "identity_ok": True, "age_months": 7, "band": "current",
             "status": "FRESH"}]
    built = assemble("heatmap", "evidence_age", rows)
    row = built["data"]["rows"][0]
    assert row["age_months"] == 7 and row["status"] == "FRESH"
    assert row["published_or_asof"] == "2025-09-01", "written columns still land"

    # run grain: onto the section object
    built = assemble("overview", "scores", [{"composite": 2.71, "band": "building"}])
    assert built["data"]["band"] == "building"

    # a NULL generated value is absent, never a default that looks like data
    built = assemble("heatmap", "evidence_age",
                     [{"e_id": "E-2", "age_months": None, "band": None}])
    assert "age_months" not in built["data"]["rows"][0]


def test_dotted_item_field_nests_like_the_payload():
    """platform.stairstep's item_field is `ladder.steps`. The payload nests it
    under ladder; assigning the dotted string as a literal key produced a
    data["ladder.steps"] that no consumer could find, while the section-level
    ladder.theme landed correctly under ladder — two shapes for one object."""
    assert readers()[("platform", "stairstep")]["item_field"] == "ladder.steps"
    rows = [{"step_level": 1, "label": "Lay the integration backbone",
             "ladder_theme": "Foundation before features", "unlocks": "reusable APIs"}]
    built = assemble("platform", "stairstep", rows)
    assert "ladder.steps" not in built["data"], "the dotted key must not survive"
    assert built["data"]["ladder"]["steps"][0]["label"] == "Lay the integration backbone"


def test_catalogue_reads_the_real_ceilings_table():
    """The stated category names come from the ceilings serving table. Its name
    is in the writer spec (overview_ceilings) — an invented one takes the whole
    catalogue endpoint down with 42P01, and the front end boots off it."""
    spec = json.loads((ROOT / "apps" / "api" / "dma_api" / "writer_spec.json").read_text())
    tables = {w["table"] for p in spec["specs"] for w in p["writers"]}
    src = (ROOT / "apps" / "api" / "dma_api" / "main.py").read_text()
    import re
    for t in re.findall(r"FROM\s+(\w+)", src):
        if t.startswith(("overview_", "heatmap_", "insights_", "platform_",
                         "context_", "techstack_")):
            assert t in tables, f"{t} is not a serving table in the writer spec"


def test_a_required_field_is_either_stored_or_deliberately_computed():
    """The defect class this whole registry keeps hitting, pinned.

    A REQUIRED contract field with no column is validated, promoted into
    nothing, and gone — that is how `context_sentiment.context_tiles`, the
    leadership contact route and `techstack.dropped` each rendered empty under
    a real client's name. But the answer is not "give every required field a
    column": some are COUNTS, and counts are computed, never stored, where a
    source of truth exists (invariant 8).

    So every required field must be one or the other, on purpose. This test
    lists the deliberate exceptions by name; anything else that loses its
    column shows up here rather than as an empty card.
    """
    import json
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp"))
    from dma_mcp.contracts import sections, ENVELOPE, SECTION_META

    # Required, and deliberately NOT persisted — each recomputed at read from a
    # source of truth that already exists, with that source named.
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
        # Not computed — read from a DIFFERENT table. The connector writes every
        # SG result to `gate_results` as it runs (see _run_s8), and that table is
        # what renders to the client with its plain_label and NOT_RUN reason. A
        # column here would be a second copy of a record the run already keeps,
        # free to disagree with the gate that produced it.
        ("heatmap", "safeguard_gates", "gates"): "gate_results, written by the connector",
        # Not written by promote at all: heatmap.evidence serves straight from
        # the INGESTED evidence_index, which is read-only once scanned.
        ("heatmap", "evidence", "evidence"): "evidence_index (ingested tier)",
        # H4's object-map grain: these are containers that _expand_h4_maps turns
        # into rows keyed by pillar_id / category_id, not fields of their own.
        ("heatmap", "workbook_scores", "pillars"): "expanded to rows by _expand_h4_maps",
        ("heatmap", "workbook_scores", "categories"): "expanded to rows by _expand_h4_maps",
    }

    spec = json.loads(
        (Path(__file__).resolve().parents[1] / "dma_api" / "writer_spec.json").read_text())
    bound = {}
    for page_spec in spec["specs"]:
        for w in page_spec["writers"]:
            keys = set()
            for c in w["columns"]:
                kind, _, rest = c["source"].partition(":")
                if kind in ("item", "section"):
                    keys.add(rest.split(".")[0])
            bound[(page_spec["page"], w["section"])] = (keys, w.get("item_field"))

    orphans = []
    for (page, name), (keys, item_field) in bound.items():
        fields = sections(page)[name]["fields"]
        for fname, spec_f in fields.items():
            if not spec_f.get("required"):
                continue
            if fname in ENVELOPE or fname in SECTION_META:
                continue          # env: / section: bindings, checked elsewhere
            if fname in keys or fname == item_field:
                continue          # stored
            if (page, name, fname) in COMPUTED_AT_READ:
                continue          # deliberate, and the source is named above
            orphans.append(f"{page}.{name}.{fname}")

    assert not orphans, (
        "required contract fields with no column and no recorded reason — each "
        "is validated at submit and then discarded at promotion: "
        + ", ".join(sorted(orphans)))
