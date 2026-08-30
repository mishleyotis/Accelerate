"""CG-48 — a value is refused at submit if its column cannot hold it.

MEM-0136 and MEM-0194, both BLOCKER, both the same shape. A producer put a
prose locator into `heatmap_focus_areas.source_page`, an INTEGER column:

    "¶4 of the release (Sharps quote), immediately after ¶3's introduction
     of Andrew Reich"

Every submit gate passed the page. It failed later, inside `promote_run`, as
Postgres SQLSTATE 22P02 — `invalid input syntax for type integer` — naming a
parameter index and nothing a producer can act on. And it failed there HAVING
ALREADY PASSED at submit, so the run was part-way through an atomic promotion
of six pages when the database refused it.

MEM-0194 measured the surface rather than the field: 135 values type-checked
across 33 tables, 6 mismatches, every one a numeric column receiving a string.
Three were that `source_page`. The other three were `platform_roadmap.phase`
(SMALLINT) carrying '1', '2', '3' — which Postgres coerced from an
unknown-typed literal and which therefore did NOT fail. That is the same
defect surviving on an accident of type inference, and it is why a numeric
string is refused here too.

Both inputs already shipped in the package: `writer_spec.json` maps every
section field to its column, `column_types.json` is generated from the
migrations that create it. Nothing read them together until this gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dma_mcp.validation2 as V2         # noqa: E402


def run(page, payload):
    return V2._check_values_fit_their_columns(page, payload)


def ids(out):
    return [r["gate_id"] for r in out]


# The exact value from MEM-0136, verbatim.
PROSE_LOCATOR = ("¶4 of the release (Sharps quote), immediately after ¶3's "
                 "introduction of Andrew Reich")


def focus(*pages):
    return {"focus_areas": {"focus_areas": [
        {"fa_id": f"FA-{i}", "source_page": p} for i, p in enumerate(pages)]}}


# ── the two reported defects ──────────────────────────────────────────

def test_a_prose_locator_in_an_integer_column_is_refused():
    out = run("heatmap", focus(PROSE_LOCATOR))
    assert ids(out) == ["CG-48"], out
    m = out[0]["message"]
    assert "heatmap_focus_areas.source_page" in m
    assert "INTEGER" in m
    assert out[0]["path"] == "heatmap.focus_areas.focus_areas[0].source_page"
    assert out[0]["severity"] == "block"


def test_the_verdict_says_where_it_used_to_surface_instead():
    """A gate that only refuses teaches nothing. This one says why catching
    it here matters: the alternative is a raw SQLSTATE mid-promotion."""
    m = run("heatmap", focus(PROSE_LOCATOR))[0]["message"]
    assert "22P02" in m
    assert "part-way through an atomic promotion" in m


def test_source_page_says_where_the_paragraph_detail_should_go():
    """The one column whose right repair is not obvious from the type."""
    m = run("heatmap", focus(PROSE_LOCATOR))[0]["message"]
    assert "A web source has no page number" in m
    assert "source_document" in m


def test_a_numeric_string_in_a_smallint_is_refused_too():
    """MEM-0194's other three. Postgres COERCED these, so they did not fail —
    a value that survives only by type inference is one inference change away
    from the outage its neighbour already caused."""
    out = run("platform", {"roadmap": {"phases": [
        {"phase": "1"}, {"phase": 2}, {"phase": "3"}]}})
    assert len(out) == 2, out
    assert [r["path"] for r in out] == [
        "platform.roadmap.phases[0].phase", "platform.roadmap.phases[2].phase"]
    assert "SMALLINT" in out[0]["message"]


# ── what must not be refused ──────────────────────────────────────────

def test_a_real_page_number_passes():
    assert run("heatmap", focus(12)) == []


def test_null_passes_because_the_column_is_nullable():
    assert run("heatmap", focus(None)) == []


def test_a_field_the_payload_omits_is_not_invented():
    """Absent is not wrong. CG-02 owns required-ness."""
    assert run("heatmap", {"focus_areas": {"focus_areas": [{"fa_id": "FA-1"}]}}) == []


def test_only_the_offending_item_is_named():
    out = run("heatmap", focus(1, PROSE_LOCATOR, 3, None))
    assert len(out) == 1
    assert out[0]["path"].endswith("[1].source_page")


def test_a_float_in_a_numeric_column_passes():
    assert run("heatmap", {"focus_areas": {"focus_areas": [
        {"fa_id": "FA-1", "entity_score": 2.75, "peer_score": 3.0}]}}) == []


def test_a_score_sent_as_a_string_is_refused():
    out = run("heatmap", {"focus_areas": {"focus_areas": [
        {"fa_id": "FA-1", "entity_score": "2.75"}]}})
    assert ids(out) == ["CG-48"]
    assert "NUMERIC" in out[0]["message"]


# ── the type families, and the ones deliberately not read ─────────────

@pytest.mark.parametrize("sqltype,family", [
    ("INTEGER", "numeric"), ("SMALLINT", "numeric"), ("BIGINT", "numeric"),
    ("NUMERIC(4,2)", "numeric"), ("DOUBLE PRECISION", "numeric"),
    ("BOOLEAN", "boolean"),
    ("DATE", "dateish"), ("TIMESTAMPTZ", "dateish"),
])
def test_the_families_that_can_hard_fail_a_write_are_read(sqltype, family):
    assert V2._sql_family(sqltype) == family


@pytest.mark.parametrize("sqltype", [
    "TEXT", "TEXT[]", "UUID", "JSONB", "band_t", "confidence_t", "", None])
def test_text_arrays_and_enums_are_deliberately_not_read(sqltype):
    """Almost anything is a valid TEXT, and an enum's members belong to CG-08
    and the contract. Reading them here would produce a verdict list nobody
    can act on."""
    assert V2._sql_family(sqltype) is None


def test_a_boolean_sent_as_a_word_is_refused():
    assert not V2._fits("true", "boolean")
    assert V2._fits(True, "boolean")
    assert V2._fits(None, "boolean")


def test_a_bool_is_not_a_number():
    """Python says True == 1. A BOOLEAN in an INTEGER column is a different
    mistake and must not pass as a number."""
    assert not V2._fits(True, "numeric")


def test_a_phrase_about_time_is_not_a_date():
    assert not V2._fits("shortly after the merger closed", "dateish")
    assert V2._fits("2026-08-23", "dateish")
    assert V2._fits("2026-08", "dateish")
    assert not V2._fits(20260823, "dateish")


# ── the generated index this gate reads ───────────────────────────────

def test_the_column_index_carries_the_two_columns_that_caused_this():
    assert V2.COLUMN_TYPES["heatmap_focus_areas"]["source_page"] == "INTEGER"
    assert V2.COLUMN_TYPES["platform_roadmap"]["phase"] == "SMALLINT"


def test_the_index_expanded_the_shared_envelope():
    """Serving tables splice a {ENVELOPE} placeholder for run_id, promoted_at
    and the rest. An extractor that missed it would lose a quarter of every
    table's columns and silently check less than it claims."""
    fa = V2.COLUMN_TYPES["heatmap_focus_areas"]
    assert fa.get("run_id") == "UUID"
    assert fa.get("promoted_at") == "TIMESTAMPTZ"


def test_the_index_is_current_with_the_migrations():
    """A migration that retypes a column must not leave the gate enforcing
    the old type. This is the same check CI runs."""
    import subprocess
    root = Path(__file__).resolve().parents[3]
    r = subprocess.run([sys.executable, "scripts/gen_column_types.py",
                        "--check"], capture_output=True, text=True, cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr


# ── scope and safety ──────────────────────────────────────────────────

def test_server_allocated_and_jsonb_columns_are_skipped():
    """`sys:` columns are written by the server and `jsonb` holds arbitrary
    shapes — checking either would refuse a producer for something it does
    not control."""
    assert run("heatmap", {"focus_areas": {"focus_areas": [
        {"fa_id": "FA-1", "r_layer": {"anything": [1, "two"]}}]}}) == []


@pytest.mark.parametrize("bad", [None, [], "x", 42,
                                 {"focus_areas": "not-a-dict"},
                                 {"focus_areas": {"focus_areas": "no"}},
                                 {"focus_areas": {"focus_areas": ["x", None]}}])
def test_malformed_payloads_do_not_raise(bad):
    run("heatmap", bad)


def test_an_unknown_page_is_not_a_finding():
    assert run("nonsense", focus(PROSE_LOCATOR)) == []


def test_the_finding_list_is_bounded():
    out = run("heatmap", focus(*[PROSE_LOCATOR] * 40))
    assert len(out) <= 8, "a verdict nobody can read is a verdict nobody acts on"


def test_a_missing_index_disables_the_gate_rather_than_the_connector(monkeypatch):
    """Additive by construction: a stale or absent generated file must not
    turn into an outage. `--check` in CI is what keeps it present."""
    monkeypatch.setattr(V2, "COLUMN_TYPES", {})
    assert run("heatmap", focus(PROSE_LOCATOR)) == []


def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-48" in GATES
    assert GATES["CG-48"][-1] == "block"
    why = GATES["CG-48"][3]
    assert "22P02" in why
    assert "atomic promotion" in why
    assert "accident of type inference" in why, (
        "the registry records why a numeric STRING is refused even though "
        "Postgres would coerce it")


def test_it_runs_inside_pass_two():
    import inspect
    src = inspect.getsource(V2.validate_pass2)
    assert "_check_values_fit_their_columns" in src, \
        "CG-48 is defined but never dispatched"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
