"""The signal that told nobody a surface needed enrichment.

Until 2026-08-14 nothing in this product recorded that a surface DEPENDED on an
enrichment source, so a section built without a scan and a section built with
one rendered identically. Measured that day: one client's technology register
served 12 rows against another's 51, its own `empty_state` said "the
technographic scan that would normally widen this register did not run", and
no surface, gate, checker or routine read that sentence. The section was
honest and its reader could not tell.

The build owner asked the question these tests answer: *what intelligently
flags that enrichment is required for a surface?* Nothing did. This is it.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import computed  # noqa: E402


def _status(page, section, data):
    computed.enrichment_status(data, page, section)
    return data.get("enrichment_status")


# ── the measurement that motivated it, as an assertion ────────────────
def test_the_two_promoted_registers_are_separated_by_the_floor():
    """12 rows vs 51 — the exact shapes production served. The floor exists to
    tell these apart, so if it ever stops doing that it is the wrong floor."""
    thin = _status("techstack", "techstack",
                   {"items": [{"detection_basis": "x"}] * 12})
    full = _status("techstack", "techstack",
                   {"items": [{"detection_basis": "x"}] * 51})
    assert thin["thin"] is True and full["thin"] is False
    assert thin["count"] == 12 and full["count"] == 51


def test_a_thin_surface_says_why_and_what_closes_it():
    s = _status("techstack", "techstack", {"items": []})
    assert s["required"] is True
    assert "scan" in s["thin_reason"]
    assert "Explorium" in s["closes_with"] or "Clay" in s["closes_with"]
    assert set(s["sources"]) == {"explorium", "clay"}


def test_a_healthy_surface_carries_no_reason_to_render():
    s = _status("techstack", "techstack",
                {"items": [{"detection_basis": "x"}] * 51})
    assert "thin_reason" not in s and "closes_with" not in s


# ── `ran` is EVIDENCED, not asserted ──────────────────────────────────
def test_ran_is_false_when_no_row_shows_enrichment_reached_it():
    """A producer claiming a scan ran while no row carries a basis would be
    believed by any check that read a boolean. This reads the rows."""
    s = _status("techstack", "techstack",
                {"items": [{"vendor": "V", "product": "P"}] * 30})
    assert s["ran"] is False and s["enriched_rows"] == 0
    assert s["thin"] is False, "30 rows clears the floor; `ran` is a separate claim"


def test_a_contact_route_counts_as_enrichment_on_the_roster():
    """Leadership has no `detection_basis`; a route IS the evidence it ran."""
    s = _status("overview", "leadership",
                {"roster": [{"name": "A", "email": "a@x.example"},
                            {"name": "B"}, {"name": "C"}, {"name": "D"}]})
    assert s["ran"] is True and s["enriched_rows"] == 1
    assert s["thin"] is False


def test_the_live_roster_shape_is_thin_and_says_so():
    """5 named leaders, 1 contact route — the shape actually served."""
    s = _status("overview", "leadership",
                {"roster": [{"name": "A", "email": "a@x.example"}]
                           + [{"name": n} for n in "BCDE"]})
    assert s["ran"] is True
    assert s["thin"] is False, "5 clears the roster floor of 4"
    assert s["enriched_rows"] == 1, "but only one route was established"


def test_blank_strings_are_not_evidence_of_enrichment():
    s = _status("overview", "leadership",
                {"roster": [{"name": "A", "email": "   ", "phone": ""}]})
    assert s["ran"] is False


# ── it must not touch what it does not govern ─────────────────────────
def test_a_surface_not_in_the_register_is_untouched():
    data = {"cells": []}
    computed.enrichment_status(data, "heatmap", "cell_evidence")
    assert "enrichment_status" not in data


def test_a_non_dict_section_does_not_raise():
    computed.enrichment_status([], "techstack", "techstack")


def test_a_missing_count_key_reads_as_zero_not_as_an_error():
    s = _status("techstack", "techstack", {})
    assert s["count"] == 0 and s["thin"] is True


# ── the register itself ───────────────────────────────────────────────
def test_the_register_is_loadable_and_every_entry_is_complete():
    reg = json.loads((ROOT / "packages" / "shared" /
                      "enrichment_register.json").read_text())["surfaces"]
    assert reg, "an empty register silently unflags every surface"
    for name, spec in reg.items():
        assert spec.get("sources"), name
        assert set(spec["sources"]) <= {"explorium", "clay"}, name
        assert spec.get("counts"), name
        assert isinstance(spec.get("thin_below"), int), name
        # A floor with no reason renders a flag nobody can act on.
        assert spec.get("thin_reason"), name
        assert spec.get("closes_with"), name


def test_every_registered_surface_exists_in_the_contract():
    """A register naming a section that does not exist flags nothing, forever
    — the same shape as the check that never ran."""
    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    from dma_mcp.contracts import sections

    reg = json.loads((ROOT / "packages" / "shared" /
                      "enrichment_register.json").read_text())["surfaces"]
    for name in reg:
        page, _, section = name.partition(".")
        assert section in sections(page), f"{name} is not a real section"


def test_an_unreadable_register_leaves_sections_unflagged_rather_than_failing(
        monkeypatch):
    """Additive: a page rendering without this is worse than one rendering
    with it, and far better than one that 500s."""
    monkeypatch.setattr(computed, "_ENRICHMENT_REGISTER", {}, raising=False)
    data = {"items": []}
    computed.enrichment_status(data, "techstack", "techstack")
    assert "enrichment_status" not in data
