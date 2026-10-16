"""The maturity SCORE scale is a five-level rubric; the display BANDS are four.

Until 28-09-2026 `engine/rubric.py` was the one engine module no test
imported (QA audit F-J03: 42 modules, one with zero test rows). A green
suite over 41 of 42 modules is the shape regression seed 6 names — the
untested path is where the crash hides — so the rubric gets its own rows
and `test_every_engine_module_is_tested.py` keeps the count at zero.
"""
from pathlib import Path

import pytest

from engine import contract as C
from engine import rubric as R


def test_five_levels_named_m1_to_m5_with_the_stated_ranges():
    assert [lv for lv, *_ in R.RUBRIC] == ["M1", "M2", "M3", "M4", "M5"]
    assert [name for _, name, *_ in R.RUBRIC] == [
        "Foundational", "Developing", "Established", "Advanced", "Leading"]
    assert [rng for _, _, rng, _ in R.RUBRIC] == [
        "1.0-1.4", "1.5-2.4", "2.5-3.4", "3.5-4.4", "4.5-5.0"]


@pytest.mark.parametrize("score,level", [
    (1.0, "M1"), (1.49, "M1"), (1.5, "M2"), (2.49, "M2"), (2.5, "M3"),
    (3.49, "M3"), (3.5, "M4"), (4.49, "M4"), (4.5, "M5"), (5.0, "M5"),
    ("2.7", "M3"),
])
def test_maturity_level_is_strict_less_than_at_every_cut(score, level):
    assert R.maturity_level(score) == level


@pytest.mark.parametrize("bad", [None, "", "x", object()])
def test_a_null_or_unparseable_score_gives_no_level(bad):
    """Invariant 9: null in, '' out — never a default that looks like data."""
    assert R.maturity_level(bad) == ""


def test_level_name_round_trips_every_row_and_refuses_an_unknown_level():
    for lv, name, _, _ in R.RUBRIC:
        assert R.level_name(lv) == name
    assert R.level_name("M9") == ""
    assert R.level_name("") == ""


def test_the_fifth_level_is_not_the_banned_band_word():
    """Charter invariant 6: M5/Transformational must not exist in code, enum
    or prose. The fifth SCORE level is a rubric row named without it."""
    assert R.level_name("M5") == "Leading"
    src = Path(R.__file__).read_text(encoding="utf-8")
    assert "Transformational" not in src


def test_the_rubric_scale_and_the_band_vocabulary_stay_distinct():
    """Five score levels, four rendered bands — both on purpose, neither a
    fifth band."""
    assert len(R.RUBRIC) == 5
    assert len(C.BANDS) == 4
    assert not set(name for _, name, _, _ in R.RUBRIC) & set(C.BANDS)
