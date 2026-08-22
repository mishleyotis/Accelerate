"""The per-cell platform vocabulary survives BOTH catalogue generations.

`ccg_subcaps.l3_platform_areas` / `.l4_features` are what a producer is
handed when it asks the catalogue which platforms address a gap. v7.0 and
v5.0 write those two facts under different headers, and only the v7.0
spelling was listed — so every v5.0 cell loaded empty, and a platform
page for a run pinned to v5.0 was written with no catalogue vocabulary at
all. See migration 0025.

These tests are pure parser: they build the two header generations in
memory, so they run in CI without the workbooks (which live in GCS) and
without a database. The DB-backed coverage check below skips cleanly
where no catalogue is loaded.
"""
import os
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "migrations"))
from ccg_loader.parsers import _split, parse_capability_map  # noqa: E402


def _sheet(headers, *rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))
    return ws


# The two generations, verbatim from the shipped workbooks.
V7_HEADERS = ("Category", "L1_Capability", "Sub_Cap_ID", "Sub_Cap_Name",
              "Description", "Solution_Type", "Tier", "Personas",
              "L3_Platforms_Addressing_SubCap", "L4_Features_Available")
V7_ROW = ("P1C1", "Strategy Foundation & Alignment", "P1C1.1.1",
          "Digital Strategy Document", "…", "Hybrid", "T1", "CIO",
          "[L3-DB-MOSAIC] Databricks Mosaic AI / Agent Bricks; "
          "[L3-TW-ENGAGE] Twilio Engage",
          "Agentforce Builder [L3: L3-SF-AGENTFORCE, Salesforce Agentforce, ..]; "
          "Tableau Embedding API v3 [L3: L3-TBL-EMBED, Tableau Embedded Analytics, ..]")

V5_HEADERS = ("Category ID", "Category Name", "Cap ID", "Capability",
              "Sub-Cap ID", "Sub-Capability", "Description", "Tier",
              "Primary Products", "Key Features", "Integration Points")
V5_ROW = ("P1C1", "Digital Strategy & Vision", "P1C1.1",
          "Strategy Foundation & Alignment", "P1C1.1.1",
          "Digital Strategy Document", "…", "T1",
          "CRM Analytics, Tableau, Salesforce Platform",
          "Strategy visualization, KPI dashboards, OKR tracking",
          "Board portals, PPM tools, ERP")


def test_v7_header_spelling_carries_platforms_and_features():
    rows, _ = parse_capability_map(_sheet(V7_HEADERS, V7_ROW), "v7.0", "P1")
    assert len(rows) == 1
    assert rows[0]["l3_platform_areas"] == [
        "[L3-DB-MOSAIC] Databricks Mosaic AI / Agent Bricks",
        "[L3-TW-ENGAGE] Twilio Engage"]
    # A feature keeps its bracketed provenance whole: splitting on the
    # commas inside it used to produce a feature literally named "..]".
    assert rows[0]["l4_features"] == [
        "Agentforce Builder [L3: L3-SF-AGENTFORCE, Salesforce Agentforce, ..]",
        "Tableau Embedding API v3 [L3: L3-TBL-EMBED, Tableau Embedded Analytics, ..]"]


def test_v5_header_spelling_carries_the_same_two_facts():
    rows, _ = parse_capability_map(_sheet(V5_HEADERS, V5_ROW), "v5.0", "P1")
    assert len(rows) == 1
    assert rows[0]["l3_platform_areas"] == [
        "CRM Analytics", "Tableau", "Salesforce Platform"]
    assert rows[0]["l4_features"] == [
        "Strategy visualization", "KPI dashboards", "OKR tracking"]


def test_a_generation_never_reads_the_other_generations_column():
    """v5.0's `Integration Points` is not a platform list, and v7.0 has no
    `Primary Products` to fall back to. The aliases are tried in order, so
    neither generation can be served the wrong column."""
    v5, _ = parse_capability_map(_sheet(V5_HEADERS, V5_ROW), "v5.0", "P1")
    assert "Board portals" not in v5[0]["l3_platform_areas"]
    v7, _ = parse_capability_map(_sheet(V7_HEADERS, V7_ROW), "v7.0", "P1")
    assert all(p.startswith("[L3-") for p in v7[0]["l3_platform_areas"])


@pytest.mark.parametrize("raw,expected", [
    # Strong separator wins, and brackets hold their commas.
    ("A [x, y]; B [p, q]", ["A [x, y]", "B [p, q]"]),
    ("A | B", ["A", "B"]),
    ("A\nB", ["A", "B"]),
    # No strong separator: the comma list is the list.
    ("CRM Analytics, Tableau", ["CRM Analytics", "Tableau"]),
    # One item of either shape survives both passes.
    ("Salesforce Platform", ["Salesforce Platform"]),
    ("Agentforce Builder [L3: L3-SF-AGENTFORCE, ..]",
     ["Agentforce Builder [L3: L3-SF-AGENTFORCE, ..]"]),
    ("", []),
    (None, []),
])
def test_split_reads_both_list_dialects(raw, expected):
    assert _split(raw) == expected


# ── DB-backed: the standing check that a load did not lose the column ──
DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")


@pytest.fixture(scope="module")
def db():
    pg8000 = pytest.importorskip("pg8000.dbapi")
    host = DSN.split("@")[1].split(":")[0]
    try:
        conn = pg8000.connect(user="postgres", password="local", host=host,
                              port=5432, database="dma_insights")
    except Exception as exc:                              # no local database
        pytest.skip(f"no database: {exc}")
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM ccg_versions")
    if not cur.fetchone()[0]:
        pytest.skip("no catalogue loaded")
    yield conn
    conn.rollback()
    conn.close()


def test_every_loaded_version_carries_a_platform_vocabulary(db):
    """Not "some cells have platforms" — MOST do, in every generation. A
    version at zero is the signature of the alias miss this file exists to
    prevent, and it is the shape three separate columns arrived in.

    LOADED is the operative word, and it now says so in SQL. `ccg_versions`
    holds two kinds of row: a catalogue the loader filled, and a bare version
    identifier that exists so `runs.ccg_catalog_version` has an FK target on a
    database no catalogue has been loaded into (the repo-root conftest writes
    those, so the DB-backed suites can run in CI at all). A row with no
    `cell_count` is the second kind — no cells were read, so "how many of them
    carry a platform" is a question about nothing, and asserting on it fails
    every fresh database while catching no alias miss.

    Nothing is weakened. The defect this file exists for is `cell_count > 0`
    with `platform_mapped_cells` at zero or half, and every such row is still
    read here."""
    cur = db.cursor()
    cur.execute("""SELECT version, cell_count, platform_mapped_cells
                     FROM ccg_versions
                    WHERE cell_count IS NOT NULL AND cell_count > 0
                    ORDER BY version""")
    for version, cells, mapped in cur.fetchall():
        assert mapped, f"{version}: {cells} cells, none carrying a platform"
        assert mapped > cells / 2, (
            f"{version}: only {mapped} of {cells} cells carry a platform — "
            "a partial read of the platform column")
