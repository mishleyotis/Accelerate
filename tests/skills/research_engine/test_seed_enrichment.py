"""The client's server-side enrichment state reaches the workbook and the
manifest before PRELIM (QA audit F-N06-014).

Measured 28-09-2026: a promoted run showed 4 of 7 facets never_enriched,
blocking = 4, done = false — held by the connector and read by nothing on
the research side. `engine.prelim seed-enrichment` writes what
`get_client_state` and `list_enrichment_gaps` say into Enrichment_Needed;
the manifest carries the same facets.
"""
import json

from engine import assemble, prelim
from fixtures import new_run

CLIENT_STATE = {
    "entity_id": "e-1", "display_id": "acme-cu", "entity_name": "Acme Credit Union",
    "runs": [{"run_id": "r-18", "run_seq": 18, "status": "PROMOTED"}],
    "served_pages": [{"page": "overview", "promoted_at": "2026-09-03T00:00:00Z"}],
    "enrichment": {"facets": [
        {"facet": "leadership", "state": "current", "enriched_at": "2026-09-01"},
        {"facet": "techstack", "state": "never_enriched"},
        {"facet": "why_now", "state": "never_enriched"},
        {"facet": "sentiment", "state": "enriched_not_promoted"},
    ], "counts": {"current": 1, "never_enriched": 2, "enriched_not_promoted": 1},
       "blocking": ["techstack", "why_now", "sentiment"], "done": False},
}
GAPS = {"gaps": [
    {"kind": "must_present_member", "page": "overview", "section": "leadership",
     "field": "people", "closes_with": "a named holder of the digital remit, with a route"},
    {"kind": "empty_optional", "page": "context", "section": "timeline", "field": "events"},
    {"kind": "empty_required", "page": "techstack", "section": "techstack", "field": "items",
     "doc": "one row per named product"},
]}


def test_seed_writes_facets_and_gaps_idempotently(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    out = prelim.seed_enrichment(wb, CLIENT_STATE, GAPS)
    assert out["facets"] == {"leadership": "RESOLVED", "techstack": "OPEN",
                             "why_now": "OPEN", "sentiment": "PARTIAL"}
    assert out["facets_blocking"] == ["sentiment", "techstack", "why_now"]
    assert out["staged_gaps"] == 2 and out["prior_runs"] == 1
    assert len(out["rows_added"]) == 6
    rows = wb.rows("Enrichment_Needed")
    assert {(r["Area"], r["Field / cell"], r["Status"]) for r in rows} >= {
        ("connector facet", "techstack", "OPEN"),
        ("connector facet", "leadership", "RESOLVED"),
        ("staged gap", "overview.leadership.people", "OPEN"),
        ("staged gap", "techstack.techstack.items", "OPEN")}
    again = prelim.seed_enrichment(wb, CLIENT_STATE, GAPS)
    assert again["rows_added"] == [] and again["rows_total"] == out["rows_total"]


def test_the_manifest_carries_the_facets_and_validates(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    doc = assemble.manifest_doc(wb, status="IN_PROGRESS", stage="PRELIM", run=run)
    assert doc["enrichment"] == {"facets": {}, "gaps_open": 0, "seeded": False}
    assemble.validate_manifest(doc)
    prelim.seed_enrichment(wb, CLIENT_STATE, GAPS)
    doc = assemble.manifest_doc(wb, status="IN_PROGRESS", stage="PRELIM", run=run)
    assert doc["enrichment"]["seeded"] is True and doc["enrichment"]["gaps_open"] == 2
    assert doc["enrichment"]["facets"]["techstack"] == "OPEN"
    assemble.validate_manifest(doc)
    schema = assemble.manifest_schema()
    assert "enrichment" in schema["required"]


def test_the_cli_seeds_from_files(tmp_path, capsys):
    run = new_run(tmp_path, prelim=False)
    cs = tmp_path / "client_state.json"
    cs.write_text(json.dumps(CLIENT_STATE))
    gp = tmp_path / "gaps.json"
    gp.write_text(json.dumps(GAPS))
    rc = prelim.main(["seed-enrichment", "--run", run.run_id, "--root", str(run.root),
                      "--client-state", str(cs), "--gaps", str(gp)])
    assert rc in (0, None)
    out = json.loads(capsys.readouterr().out)
    assert out["facets"]["why_now"] == "OPEN"


def test_an_unknown_client_seeds_nothing(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    out = prelim.seed_enrichment(wb, {"error": "unknown_entity", "did_you_mean": []})
    assert out["facets"] == {} and out["rows_added"] == []
