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
