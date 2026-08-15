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


# ── the container name, written twice and compared nowhere ────────────
def test_counts_names_a_list_the_section_contract_actually_declares():
    """RULE_HELD_IN_TWO_PLACES_DRIFTS, measured.

    This register said `"counts": "employee"` for overview.sentiment against a
    section whose only rating list is `bars`. `data.get("employee")` returned
    None on every run that has ever promoted, so the card served `count: 0,
    thin: true` — "no retrievable rating was established" — while it rendered
    seven rated bars above the sentence, and while the connector's SG-S8 passed
    those same seven. Renderer and gate disagreed for the whole life of the
    feature, because the container name lived in two files and no test put them
    side by side.

    The section existence check above passed throughout. Naming a real section
    and then reading a key it does not have is the more common half of the
    mistake, and it was the unchecked half."""
    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    from dma_mcp.contracts import sections

    reg = json.loads((ROOT / "packages" / "shared" /
                      "enrichment_register.json").read_text())["surfaces"]
    for name, spec in reg.items():
        page, _, section = name.partition(".")
        fields = (sections(page).get(section) or {}).get("fields") or {}
        key = spec["counts"]
        assert key in fields, (
            f"{name}: counts names {key!r}, which the contract does not "
            f"declare — it has {sorted(fields)}. The status will count 0 rows "
            f"forever and the surface will read as thin whatever it serves.")
        assert fields[key].get("type") == "list", (
            f"{name}: counts names {key!r}, a "
            f"{fields[key].get('type')} — len() of a non-list is not a row "
            f"count.")


# ── ran: measured, or null, never a default wearing a measurement's clothes ──
def test_every_surface_declares_whether_ran_is_observable():
    """A surface that declares an enrichment source and no way to observe it
    served `ran: false` for every run in this product's history.

    firmographics, sentiment and thought_leadership each declared `clay` and
    neither `basis_key` nor `contact_keys`, so `enriched` was structurally 0
    and no payload could ever have cleared the badge that reads off it. The
    owner reported that badge four times; the cause was here, one field short,
    in a file whose completeness test checked five other fields.

    So the declaration is now mandatory and exclusive: measure it, or say why
    it cannot be measured."""
    reg = json.loads((ROOT / "packages" / "shared" /
                      "enrichment_register.json").read_text())["surfaces"]
    for name, spec in reg.items():
        observable = bool(spec.get("basis_key") or spec.get("contact_keys"))
        declared_un = spec.get("ran_observable") is False
        assert observable != declared_un, (
            f"{name}: declare exactly one — a basis_key/contact_keys that "
            f"evidences enrichment in the rows, or ran_observable: false. "
            f"Declaring neither is what served `ran: false` on three surfaces "
            f"that could never have said otherwise.")
        if declared_un:
            assert spec.get("ran_unobservable_reason"), (
                f"{name}: ran_observable false needs its reason — a reader of "
                f"the payload has to be able to tell 'enrichment reached "
                f"nothing' from 'this surface cannot tell'.")


def test_an_unobservable_surface_serves_null_not_false():
    """Invariant 9: derived values are computed or null, never a default that
    looks like data. `false` here is a claim the rows do not support."""
    s = _status("overview", "firmographics",
                {"fields": [{"field": "employees", "value": "1200"}] * 13})
    assert s["ran"] is None, "false is a measurement this surface cannot make"
    assert s["ran_unobservable_reason"], "null without its reason is a shrug"
    assert "enriched_rows" not in s, "a count of nothing observable is noise"
    assert s["count"] == 13 and s["thin"] is False, (
        "thin is still measurable — it counts rows, which are observable")


def test_an_observable_surface_still_measures_ran_both_ways():
    """The other half: where the mark exists, `ran` is a real reading and must
    stay one — the null branch must not swallow it."""
    off = _status("techstack", "techstack", {"items": [{"name": "x"}] * 30})
    on = _status("techstack", "techstack",
                 {"items": [{"detection_basis": "scan"}] * 30})
    assert off["ran"] is False and off["enriched_rows"] == 0
    assert on["ran"] is True and on["enriched_rows"] == 30


def test_sentiment_with_seven_rated_bars_is_not_thin():
    """The card the owner was looking at. Seven bars, count 0, "no retrievable
    rating carrying its sample size, scale and date was established"."""
    s = _status("overview", "sentiment",
                {"bars": [{"source": "App Store", "rating": 4.87,
                           "scale": "1-5 stars", "n": 95033}] * 7})
    assert s["count"] == 7, "the bars are the rows"
    assert s["thin"] is False, "seven established ratings is not 'no rating'"
    assert "thin_reason" not in s


def test_an_unreadable_register_leaves_sections_unflagged_rather_than_failing(
        monkeypatch):
    """Additive: a page rendering without this is worse than one rendering
    with it, and far better than one that 500s."""
    monkeypatch.setattr(computed, "_ENRICHMENT_REGISTER", {}, raising=False)
    data = {"items": []}
    computed.enrichment_status(data, "techstack", "techstack")
    assert "enrichment_status" not in data


def test_ran_is_measured_before_redaction_strips_what_it_measures():
    """The ordering in pages.py is load-bearing for this field specifically.

    `ran` on the leadership roster is evidenced by contact routes — email,
    linkedin_url, phone — and those are exactly what redaction strips for the
    customer audience. Compute after redaction and an enriched roster measures
    `ran: false`, which renders "no machine scan of the estate contributed rows
    here" to the client, about a roster that was enriched. A live false
    statement, produced by two correct components in the wrong order.

    Caught 2026-08-15 while replaying the promoted payload through the new
    logic: the CUSTOMER copy flipped true -> false and the internal copy did
    not. That was an artefact of replaying an already-redacted body, but it is
    precisely the defect the real order avoids, so it is pinned here."""
    enriched = [{"name": "A", "email": "a@x.com"},
                {"name": "B", "linkedin_url": "https://x"},
                {"name": "C", "phone": "+1"}, {"name": "D", "email": "d@x.com"}]
    assert _status("overview", "leadership", {"roster": enriched})["ran"] is True

    # The same roster as the customer audience receives it.
    redacted = [{k: v for k, v in r.items() if k == "name"} for r in enriched]
    assert _status("overview", "leadership", {"roster": redacted})["ran"] is False, (
        "if this ever stops being false, the test no longer guards anything")

    src = (ROOT / "apps" / "api" / "dma_api" / "pages.py").read_text()
    apply_at = src.find("computed_apply(cur, page, section")
    redact_at = src.find("redact_section(page, section")
    assert apply_at > 0 and redact_at > 0, "the serve path moved; re-anchor this"
    assert apply_at < redact_at, (
        "computed_apply must run BEFORE redact_section — the customer audience "
        "would otherwise be told no scan reached a roster that a scan reached.")
