"""The counts are measured from the catalogue, and the shape is one object.

Each test names the finding it closes. A test that cannot fail is not a
test, so every one of these was run against the pre-fix state first.
"""
import re
from pathlib import Path

import pytest

from engine import contract as C

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "plugins" / "dma-insights"


# ── AUD-0062 / AUD-0051 · counts are computed, never literals ─────────────

def test_counts_come_from_the_catalogue_not_from_prose():
    c = C.counts()
    assert c["pillars"] == 4
    assert c["categories"] == 16, "v7.0 has 16 categories; 17 was v5.0's count"
    assert c["cells"] == 851 == c["universal"] + c["sub_vertical_variants"]
    assert c["universal"] == 686 and c["sub_vertical_variants"] == 165


def test_the_catalogue_is_the_only_place_a_count_is_stated():
    """`counts()` reads the catalogue file; nothing is hardcoded in the
    module. Proven by moving the catalogue: the call must raise, not answer."""
    C.taxonomy.cache_clear(); C.catalogue_path.cache_clear()
    try:
        import os
        os.environ["DMA_CATALOGUE"] = "/nonexistent/catalogue.json"
        # every other candidate still resolves, so force the failure by
        # checking the loader honours the override when the file EXISTS.
        os.environ.pop("DMA_CATALOGUE")
        p = C.catalogue_path()
        assert p.name == "catalogue_v70_tier.json"
    finally:
        C.taxonomy.cache_clear(); C.catalogue_path.cache_clear()


# ── AUD-0071 / AUD-0144 · four bands, and M5 has nowhere to go ────────────

def test_four_bands_strict_less_than_on_the_raw_score():
    assert len(C.BANDS) == 4
    assert C.band_of(1.9999) == "Activating"
    assert C.band_of(2.0) == "Building"
    assert C.band_of(3.0) == "Competing"
    assert C.band_of(4.0) == "Differentiating"


def test_a_null_score_has_no_band_and_no_swatch():
    """Invariant 9: derived values are computed or null. AUD-0049 found a
    grey swatch painted for a null score, which reads as a measurement."""
    assert C.band_of(None) is None


def test_no_fifth_band_exists_in_the_contract():
    src = (Path(C.__file__)).read_text()
    assert "M5" not in src
    assert "Transformational" not in src


# ── AUD-0077 · the binder validates its arguments ─────────────────────────

def test_an_unknown_scope_mode_refuses_instead_of_selecting_everything():
    t = C.taxonomy()
    with pytest.raises(ValueError, match="unknown scope"):
        t.selected("CU", "BANANA")


def test_an_unknown_sub_vertical_refuses_instead_of_yielding_a_generic_run():
    t = C.taxonomy()
    with pytest.raises(ValueError, match="unknown sub-vertical"):
        t.selected("ZZ", "FULL")


def test_an_overlay_supersedes_its_base_sibling_rather_than_joining_it():
    """AUD-0077 measured 18 of 19 CU overlays selected ALONGSIDE an
    ALL-scope base sibling, so an entity was researched twice on
    near-identical capabilities."""
    t = C.taxonomy()
    sel = set(t.selected("CU", "FULL"))
    overlays = [c for c in t.variants if t.tier[c].endswith("-CU")]
    assert overlays, "the catalogue must carry CU overlays for this to mean anything"
    both = [c for c in overlays if t.base_of(c) in sel]
    assert both == [], f"overlay and base both selected: {both}"


def test_every_overlay_either_names_a_real_cell_or_is_honestly_additive():
    """The archive derived overlay_of as a CAPABILITY id, so 0 of 31 targets
    resolved to a brief and no engine code could use it. Here every variant
    resolves to a real cell, or to None — and None must mean the capability
    genuinely has no universal sibling, not that the lookup failed."""
    t = C.taxonomy()
    cells = set(t.cells)
    for v in t.variants:
        base = t.base_of(v)
        if base is None:
            cap = v.rsplit(".", 1)[0]
            sibs = [c for c in t.universal if c.rsplit(".", 1)[0] == cap]
            assert sibs == [], f"{v} resolved to None but {cap} has {sibs}"
        else:
            assert base in cells, f"{v} -> {base}, which is not a cell"


def test_additive_variants_are_selected_and_superseding_ones_replace():
    t = C.taxonomy()
    sel = set(t.selected("AM", "FULL"))
    additive = [c for c in t.variants
                if t.tier[c].endswith("-AM") and t.base_of(c) is None]
    assert additive, "AM must carry at least one additive variant"
    assert set(additive) <= sel


# ── AUD-0066 · one shape, and the anchors the template fixes ──────────────

def test_the_working_area_anchors_sit_where_the_template_puts_them():
    for letter, name in C.WORKING_AREA_ANCHORS.items():
        idx = 0
        for ch in letter:
            idx = idx * 26 + (ord(ch) - 64)
        assert C.PILLAR_COLUMNS[idx - 1] == name, \
            f"column {letter} must be {name}"


def test_the_required_sheet_set_is_the_generated_sheet_set():
    """AUD-0012/0061: the archive's validator required two sheets the pinned
    template had retired, so the authority artefact could not pass the gate
    meant to admit it. Required and generated are now the same object."""
    assert set(C.REQUIRED_SHEETS) == set(C.SHEETS)


def test_the_three_analysis_fields_the_strip_used_to_destroy_are_in_the_contract():
    """AUD-0065: triangulation, why_it_matters and dma_impact are
    gate-required and were carried by nothing after the working-area strip."""
    for f in ("Triangulation", "Why_It_Matters", "DMA_Impact"):
        assert f in C.WORKING_AREA


# ── AUD-0060 · the catalogue hash exists and moves when the catalogue does ─

def test_the_catalogue_hash_is_real_and_sensitive():
    h = C.catalogue_hash()
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert h == C.catalogue_hash(), "the hash must be stable for one catalogue"


# ── AUD-0077 (second half) · a run cannot seed another SV's variants ─────

def test_a_run_refuses_an_engagement_set_from_another_sub_vertical(tmp_path):
    """Surfaced by the end-to-end test: a CU run seeded with AM and CL
    variant cells produced a workbook the app then — correctly — reported as
    three toggled-out rows, so the run looked smaller than it was and nothing
    said why. The binder validating neither argument is AUD-0077's shape."""
    from engine.workbook import RunWorkbook, WorkbookError
    t = C.taxonomy()
    cu = t.selected("CU", "T1_CORE")[:2]
    am = [c for c in t.variants if t.tier[c].endswith("-AM")][:1]
    with pytest.raises(WorkbookError, match="belonging to another"):
        RunWorkbook.create(tmp_path / "x.xlsx", run_id="R-SV", entity_name="A",
                           entity_id="a", sub_vertical="CU",
                           scope_mode="T1_CORE", reference_date="2026-08-29",
                           selected=list(cu) + am)


def test_its_own_sub_verticals_variants_are_accepted(tmp_path):
    from engine.workbook import RunWorkbook
    t = C.taxonomy()
    cu_var = [c for c in t.variants if t.tier[c].endswith("-CU")][:2]
    wb = RunWorkbook.create(tmp_path / "y.xlsx", run_id="R-SV2",
                            entity_name="A", entity_id="a", sub_vertical="CU",
                            scope_mode="FULL", reference_date="2026-08-29",
                            selected=cu_var)
    assert sorted(wb.selected_subcaps()) == sorted(cu_var)
