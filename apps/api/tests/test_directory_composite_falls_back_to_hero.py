"""The clients directory shows a composite for a run whose workbook stated none.

A promoted run whose workbook omits the rollup composite writes runs.composite
NULL by design; the overview hero still shows overview_scores.composite. Before
0059 the directory read r.composite alone, so such a client's card showed its
four pillar bars and no overall score while its own overview page showed one
(measured on goeasy Ltd., run 02e840d4: runs.composite NULL, hero 2.11).

0059 rebuilds serving_directory to read COALESCE(r.composite, os.composite).
This test is STATIC (no database): it reads the latest migration that rebuilds
the view and asserts the composite column is the fallback, so a future rebuild
that carries the body forward and silently drops the COALESCE fails here rather
than in production on the next un-rollup'd workbook. `overview_scores` must stay
joined for os.composite to resolve.
"""
import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations" / "versions"


def _latest_view_migration() -> tuple[str, str]:
    """(revision, full text) of the highest-numbered migration that rebuilds
    serving_directory. Keyed on the CREATE, not on a variable name, so it finds
    the view whether its body is a literal (_VIEW_BODY = \"\"\") or a formatted
    template (_VIEW_BODY = _VIEW_BODY_TMPL.format(...))."""
    latest, text = None, None
    for path in sorted(MIGRATIONS.glob("*.py")):
        t = path.read_text()
        if "MATERIALIZED VIEW serving_directory AS" not in t:
            continue
        rev = path.name.split("_", 1)[0]
        if latest is None or rev > latest:
            latest, text = rev, t
    assert latest, "no migration creates the serving_directory materialised view"
    return latest, text


def test_latest_directory_view_uses_the_hero_composite_fallback():
    rev, text = _latest_view_migration()
    # The served composite must fall back to the overview hero, not read the
    # possibly-null workbook figure alone.
    assert re.search(r"COALESCE\(\s*r\.composite\s*,\s*os\.composite\s*\)", text), (
        f"migration {rev} rebuilds serving_directory but does not read "
        "COALESCE(r.composite, os.composite) AS composite — a run whose workbook "
        "stated no rollup composite will show no score on the clients page while "
        "its overview hero shows one (the recurrent defect 0059 closed)")


def test_the_fallback_source_is_still_joined():
    rev, text = _latest_view_migration()
    assert "LEFT JOIN overview_scores os" in text, (
        f"migration {rev} reads os.composite for the directory fallback but no "
        "longer joins overview_scores — the COALESCE would fail to resolve os")
