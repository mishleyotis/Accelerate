"""A section that promoted with nothing in it is not a section that never
promoted.

H-05 / H-08, measured on run d7ed1d90-d406-4e8e-9ab0-75f91a0c15bb: the
producer worked `heatmap.workbook_scores` and `heatmap.cohort_patterns`, could
publish neither, and wrote the reason for each — the pillar grain the workbook
does not resolve, and the cohort floor of five promoted runs in one
sub-vertical against a corpus holding two — with its sources searched and its
closure condition. Both reasons were discarded at promote, because a section
with an empty collection writes no serving rows, `assemble` returns None for a
section with no rows, and pages.py then serves

    {"kind": "section_not_promoted", "reason": "no serving row for this run"}

which is the plumbing, not the reason. The pillar zoom rendered four bare
chips and the cohort table rendered a header over nothing, in both cases with
no word about why.

The fix is the shape `heatmap.value_chain` has always had: an ENVELOPE-ONLY
serving row. The writer leaves one when the collection is empty; the reader
takes its envelope and does not mistake it for an item.

`test_value_chain.py::test_wired_into_the_heatmap_page_read` asserts this
shape for H9 alone; these tests are the generalisation.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_api.serving_spec import assemble, readers  # noqa: E402


def _cols(page, section):
    r = readers()[(page, section)]
    return r, list(r["item_cols"])


def _row(page, section, **over):
    """One serving row: every column the reader knows about, all null unless
    named. That is what the database hands back for an envelope-only row."""
    r = readers()[(page, section)]
    row = {c: None for c in
           list(r["item_cols"]) + list(r["env_cols"]) + list(r["sys_cols"])
           + list(r["section_cols"]) + list(r["derived_cols"])}
    row.update(over)
    return row


REASON = {
    "reason": ("One credit union in the corpus carries a served score for "
               "these categories, so every cohort sits below the minimum of "
               "five and nothing is published"),
    "sources_searched": ["the promoted corpus", "the sub-vertical index"],
    "closure_condition": "Three more promoted credit-union runs.",
}


def test_an_envelope_only_row_serves_the_reason_not_a_null_item():
    """cohort_patterns is item-grain: the envelope-only row must give the
    section its empty_state and add nothing to the collection."""
    row = _row("heatmap", "cohort_patterns",
               empty_state=REASON, producer_version="p/2026-08-18")
    built = assemble("heatmap", "cohort_patterns", [row])

    assert built is not None, (
        "an envelope-only row must serve — returning None here is what makes "
        "promoted-with-nothing-in-it indistinguishable from never-promoted")
    assert built["env"]["empty_state"] == REASON, \
        "the producer's own reason must survive the read"

    r = readers()[("heatmap", "cohort_patterns")]
    items = built["data"]
    for seg in r["item_field"].split("."):
        items = items[seg]
    assert items == [], (
        "the envelope-only row was read as an item: the collection now "
        f"carries {items!r}, which is a cohort pattern with no statement, no "
        "category and no cohort size — a row of pure nulls rendered to a "
        "reader as data")


def test_a_real_item_is_still_an_item():
    """The skip is on a row with NO item content at all, so nothing that
    carries a single stated field is ever dropped."""
    real = _row("heatmap", "cohort_patterns",
                sub_vertical="CU", category_id="P1C1",
                pattern_statement="A stated pattern", cohort_size=5,
                affected_count=3, empty_state=None)
    built = assemble("heatmap", "cohort_patterns", [real])
    r = readers()[("heatmap", "cohort_patterns")]
    items = built["data"]
    for seg in r["item_field"].split("."):
        items = items[seg]
    assert len(items) == 1, "a promoted pattern was dropped as envelope-only"


def test_an_envelope_only_row_beside_real_items_drops_only_itself():
    # promote stamps the envelope on EVERY row of a section, so a section
    # that carries rows and a declared absence at once carries the absence on
    # all of them; the envelope is read from the first row that has it.
    real = _row("heatmap", "cohort_patterns",
                sub_vertical="CU", category_id="P1C1",
                pattern_statement="A stated pattern", empty_state=REASON)
    env_only = _row("heatmap", "cohort_patterns", empty_state=REASON)
    built = assemble("heatmap", "cohort_patterns", [real, env_only])
    r = readers()[("heatmap", "cohort_patterns")]
    items = built["data"]
    for seg in r["item_field"].split("."):
        items = items[seg]
    assert len(items) == 1
    assert built["env"]["empty_state"] == REASON, (
        "a section can carry rows AND a declared absence at once; the "
        "absence must still reach the envelope")


def test_workbook_scores_ignores_an_envelope_only_row_by_construction():
    """H4 is the map-inverse shape: a row is a pillar row or a category row,
    and one that names neither has always been ignored. The envelope-only row
    therefore needs no new guard here — but it must still serve its reason,
    which is the half that was missing."""
    row = _row("heatmap", "workbook_scores",
               empty_state={"reason": "The workbook resolves no pillar grain "
                                      "for this run.",
                            "sources_searched": [],
                            "closure_condition": "A workbook carrying a "
                                                 "pillar table."})
    built = assemble("heatmap", "workbook_scores", [row])
    assert built is not None
    assert built["env"]["empty_state"]["reason"].startswith("The workbook")
    assert not built["data"].get("pillars")
    assert not built["data"].get("categories")


def test_the_writer_leaves_a_row_for_an_empty_collection():
    """The other half of the fix, read at source: promote must not return
    zero rows for a section it was handed."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "promote.py").read_text()
    assert "envelope_only = not rows and isinstance(section_payload, dict)" in src, (
        "a section submitted with an empty collection still writes nothing, "
        "so its empty_state is destroyed at promote")
    body = src[src.index("def _write_section"):]
    assert body.index("envelope_only = not rows") \
        < body.index("cols, exprs, per_row_sources = [], [], []"), \
        "the envelope-only row must be decided before the columns are built"


def test_pages_still_reports_a_section_that_truly_did_not_promote():
    """The `section_not_promoted` state is not being deleted — it is being
    made honest. A section with NO rows at all still says so."""
    assert assemble("heatmap", "cohort_patterns", []) is None
    src = (ROOT / "apps" / "api" / "dma_api" / "pages.py").read_text()
    assert '"kind": "section_not_promoted"' in src


def test_an_envelope_only_alert_row_takes_no_lifecycle_state():
    """`serving_directory.open_alerts` counts heatmap_alerts rows whose status
    is 'open'. heatmap.alerts is item-grain, so a run whose queue promoted
    empty would gain an envelope-only row — and stamped with the lifecycle
    initial it would put ONE OPEN ALERT, naming no cell, on the directory of
    every such run. That is the same defect class the whole H-01 fix is
    about: a count asserted where the run asserts nothing."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "promote.py").read_text()
    assert '"lifecycle": True' in src, \
        "the lifecycle initial must be identifiable to suppress it"
    assert 'if envelope_only and c.get("lifecycle"):' in src, \
        "an envelope-only row must take no lifecycle state"
    body = src[src.index("def _write_section"):]
    assert body.index("envelope_only = not rows") < \
        body.index('if envelope_only and c.get("lifecycle")')
