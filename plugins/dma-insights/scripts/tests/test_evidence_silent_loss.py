"""Two silent losses in the evidence merge, both measured on the real corpus.

Neither raised a warning, a count or a gap. Both made a package look thin
when the package was holding the answer in plain sight — which is why the
owner kept seeing evidence drawers with no URLs.

  1. A workbook tab was read only if its TITLE contained "evidence". The
     P1..P4 `_Scoring_Detail` and `_Subcap_Scoring` tabs are titled neither,
     and carry `Evidence_IDs`, `Evidence_URLs`, `Evidence_Excerpt`. Measured
     across 19 corpus packages: 134 tabs skipped, 22,501 rows, every one
     with a URL column and 9,552 with an excerpt column.

  2. An evidence id was recognised only if it began `E-`. One client writes
     `EV-P1C1-001`, agreed across five separate stores; `merge()` returned
     ZERO records and the tool printed `"records": 0`, which reads as an
     empty package rather than an unrecognised vocabulary.

After the fix, corpus-wide: 3,767 records against 2,647, URL coverage 79.9%.
That one client went 0 -> 203.
"""
import json
import sys
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import evidence_normalize as en  # noqa: E402


def _pkg(tmp_path, sheets=None, csvs=None):
    """A minimal package package_map will classify."""
    root = tmp_path / "pkg"
    (root / "03_scoring_workbook").mkdir(parents=True)
    (root / "01_evidence").mkdir(parents=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in (sheets or {"Evidence_Master": [["Evidence_ID"], ["E-1"]]}).items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.save(root / "03_scoring_workbook" / "DMA_Scoring_Workbook_X.xlsx")
    for rel, text in (csvs or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


# ── loss 1: an evidence-SHAPED tab, not an evidence-NAMED one ────────────

def test_a_scoring_detail_tab_is_read_for_its_evidence(tmp_path):
    """The measured case, in miniature. This tab is named nothing like
    "evidence" and carries three evidence columns."""
    root = _pkg(tmp_path, sheets={"P1_Subcap_Scoring": [
        ["SubCap_ID", "Score", "Evidence_IDs", "Source_URLs", "Evidence_Excerpt"],
        ["P1C1.1", 3, "E-101", "https://example.com/a",
         "A" * 60],
        ["P1C1.2", 4, "E-102", "https://example.com/b", "B" * 60]]})
    records, _, _ = en.merge(root)
    assert set(records) == {"E-101", "E-102"}, (
        "a tab whose header carries an id column beside url and excerpt "
        "columns is an evidence store, whatever it is called")
    assert records["E-101"]["url"] == "https://example.com/a"
    assert len(records["E-101"]["excerpt"]) >= 50


def test_a_tab_with_no_evidence_shape_is_still_skipped(tmp_path):
    """The other direction. Reading every tab would sweep in calculation
    chains and metadata, and an id-shaped string in a formula column would
    become an evidence row."""
    root = _pkg(tmp_path, sheets={
        "Calculation_Chain": [["Level", "ID", "Score", "Weight"],
                              ["pillar", "P1", 3.2, 0.25]],
        "Evidence_Master": [["Evidence_ID", "URL", "Excerpt"],
                            ["E-1", "https://example.com/x", "X" * 60]]})
    records, _, _ = en.merge(root)
    assert set(records) == {"E-1"}


def test_an_evidence_named_tab_without_content_columns_yields_nothing(tmp_path):
    """Shape decides, both ways: a linkage tab with only ids and subcaps
    defines no evidence."""
    root = _pkg(tmp_path, sheets={
        "Evidence_Linkage": [["Evidence_ID", "SubCap_ID"], ["E-9", "P1C1.1"]]})
    records, _, _ = en.merge(root)
    assert records == {} or "url" not in records.get("E-9", {})


# ── loss 2: an id vocabulary that is not `E-` ─────────────────────────────

@pytest.mark.parametrize("eid", ["EV-P1C1-001", "EV-CONN-001", "INT-BRIEF-2",
                                 "US-014", "PX-P1C1.1.1-1", "SRC-12"])
def test_a_non_e_dash_id_in_a_named_column_is_recognised(tmp_path, eid):
    """All measured in the corpus. The first two are one client's entire
    register — 1,013 rows across five agreeing stores — which merged to 0."""
    root = _pkg(tmp_path, sheets={"Evidence_Index": [
        ["Evidence_ID", "URL", "Excerpt"],
        [eid, "https://example.com/z", "Z" * 60]]})
    records, _, _ = en.merge(root)
    assert list(records) == [eid.upper()], f"{eid} was dropped"
    assert records[eid.upper()]["url"] == "https://example.com/z"


def test_a_catalogue_cell_id_is_never_an_evidence_id(tmp_path):
    """`P1C1.1.1` is a capability cell. Widening the id pattern must not
    turn the scoring grid into evidence rows."""
    assert en._base_eid("P1C1.1.1", wide=True) is None
    assert en._base_eid("P1C1.3.CU1", wide=True) is None


def test_the_wide_pattern_applies_only_to_a_named_id_column(tmp_path):
    """Value-scanning a whole row with the wide pattern would make every
    product code, ticket number and document reference an evidence id. The
    widening is safe only because the column is already known to be the id
    column."""
    assert en._base_eid("EV-CONN-001", wide=True) == "EV-CONN-001"
    assert en._base_eid("EV-CONN-001", wide=False) is None


def test_an_unrecognised_id_is_counted_and_named(tmp_path):
    """"records: 0" was the only trace of 1,013 rows. Now the drop is
    reported with the store and examples — "I found nothing" and "I did not
    recognise what I found" must stay distinguishable."""
    root = _pkg(tmp_path, csvs={"01_evidence/evidence_index.csv":
                                "evidence_id,url\n@@bad@@,https://x.test/1\n"})
    records, _, unrecognised = en.merge(root)
    dropped = sum(len(v) for v in unrecognised.values())
    assert dropped >= 1
    assert any("@@bad@@" in ex for v in unrecognised.values() for ex in v)


def test_cell_ids_do_not_pollute_the_unrecognised_count(tmp_path):
    """One real package carries 712 cell ids in an id column. Reporting them
    as dropped evidence buries the handful that are real."""
    root = _pkg(tmp_path, csvs={"01_evidence/evidence_index.csv":
                                "evidence_id,url\nP1C1.1.1,https://x.test/1\n"})
    _, _, unrecognised = en.merge(root)
    assert sum(len(v) for v in unrecognised.values()) == 0


# ── the contract ──────────────────────────────────────────────────────────

def test_merge_returns_three_things(tmp_path):
    """The third is the loss report. It is part of the contract precisely
    so a caller cannot forget to look at it."""
    out = en.merge(_pkg(tmp_path))
    assert len(out) == 3
    assert isinstance(out[2], dict)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
