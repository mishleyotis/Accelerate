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


# ── multi-id citation cells, the measured 9,935-reference mode ────────────
#
# 2,532 rows across 15 packages of the last-60 cohort carry a DELIMITED LIST
# in their named id column — `E-001, E-002` on research tabs,
# `E-030:F9;E-031:F1` fact-qualified on scoring tabs — beside a source_urls
# cell that is a parallel list on 44% of them. `_base_eid` matches one id,
# so every such row dropped whole: 1,218 on one client. After expansion the
# same 15 packages went from 80% to 98% URL coverage.


def _citation_pkg(tmp_path, ids, urls, extra_cols=None):
    root = tmp_path / "pkg"
    (root / "03_scoring_workbook").mkdir(parents=True)
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    ws = wb.create_sheet("P1_Subcap_Scoring")
    hdr = ["SubCap_ID", "Score", "Evidence_IDs", "Source_URLs"]
    row = ["P1C1.1", 3, ids, urls]
    for k, v in (extra_cols or {}).items():
        hdr.append(k); row.append(v)
    ws.append(hdr); ws.append(row)
    wb.save(root / "03_scoring_workbook" / "DMA_Scoring_Workbook_X.xlsx")
    return root


def test_parallel_lists_pair_positionally(tmp_path):
    """The 44% case: id list and url list the same length — the pairing is
    stated by the row itself."""
    root = _citation_pkg(tmp_path, "E-001; E-002; E-003",
                         "https://a.test/1; https://b.test/2; https://c.test/3")
    records, _, unrec = en.merge(root)
    assert set(records) == {"E-001", "E-002", "E-003"}
    assert records["E-002"]["url"] == "https://b.test/2"
    assert sum(len(v) for v in unrec.values()) == 0
    assert records["E-002"]["field_provenance"]["url"]["how"] == "citation"


def test_a_single_url_against_many_ids_attaches_to_none(tmp_path):
    """A single URL against three ids is the ROW's source; guessing which id
    owns it is how a drawer gets a wrong link. The ids are still minted —
    they are real citations — with nothing attached."""
    root = _citation_pkg(tmp_path, "E-001, E-002, E-003", "https://only.test/x")
    records, _, _ = en.merge(root)
    assert set(records) == {"E-001", "E-002", "E-003"}
    assert all("url" not in records[e] for e in records)


def test_mismatched_list_lengths_attach_nothing(tmp_path):
    root = _citation_pkg(tmp_path, "E-001; E-002; E-003",
                         "https://a.test/1; https://b.test/2")
    records, _, _ = en.merge(root)
    assert set(records) == {"E-001", "E-002", "E-003"}
    assert all("url" not in records[e] for e in records)


def test_fact_qualified_ids_resolve_to_their_base(tmp_path):
    """`E-030:F9;E-031:F1` — the scoring tabs' spelling. The fact suffix
    names which fact inside the id; the record is the id."""
    root = _citation_pkg(tmp_path, "E-030:F9;E-031:F1",
                         "https://a.test/1;https://b.test/2")
    records, _, _ = en.merge(root)
    assert set(records) == {"E-030", "E-031"}
    assert records["E-031"]["url"] == "https://b.test/2"


def test_an_excerpt_is_never_split_attached(tmp_path):
    """An excerpt is ONE verbatim span. Splitting a cell on delimiters and
    attaching the fragments manufactures quotations — the fabrication
    incident in miniature. Even a length-matched excerpt list is refused."""
    long_a = "A" * 60
    long_b = "B" * 60
    root = _citation_pkg(tmp_path, "E-001; E-002",
                         "https://a.test/1; https://b.test/2",
                         extra_cols={"Evidence_Excerpt": f"{long_a}; {long_b}"})
    records, _, _ = en.merge(root)
    assert all("excerpt" not in records[e] for e in records), (
        "a split fragment attached as an excerpt is a fabricated span")


def test_a_url_containing_a_comma_is_not_shredded(tmp_path):
    """Comma splits only when the next token is itself a URL."""
    u1 = "https://a.test/report?ids=1,2,3"
    u2 = "https://b.test/x"
    root = _citation_pkg(tmp_path, "E-001, E-002", f"{u1}, {u2}")
    records, _, _ = en.merge(root)
    assert records["E-001"]["url"] == u1
    assert records["E-002"]["url"] == u2


def test_absence_markers_with_qualifiers_are_not_unrecognised(tmp_path):
    """Measured: 188 rows of `NO_EVIDENCE (ladder-complete)` in one id
    column — the assessment stating its search ladder completed empty. An
    explicit absence is the row's statement, never an unrecognised id."""
    root = tmp_path / "pkg"
    (root / "01_evidence").mkdir(parents=True)
    (root / "01_evidence" / "evidence_index.csv").write_text(
        "evidence_id,url\n"
        "NO_EVIDENCE (ladder-complete),\n"
        "N/A,\n"
        "E-001,https://x.test/1\n")
    records, _, unrec = en.merge(root)
    assert set(records) == {"E-001"}
    assert sum(len(v) for v in unrec.values()) == 0


def test_citation_rows_never_shadow_the_register(tmp_path):
    """A citation-supplied url is rank-arbitrated by the same _attach rules
    as everything else — a register that later states a different url is a
    recorded conflict, not a silent overwrite."""
    root = _citation_pkg(tmp_path, "E-001; E-002",
                         "https://cite.test/1; https://cite.test/2")
    (root / "01_evidence").mkdir(parents=True)
    (root / "01_evidence" / "evidence_index.csv").write_text(
        "evidence_id,url\nE-001,https://register.test/1\n")
    records, conflicts, _ = en.merge(root)
    assert any(c["eid"] == "E-001" and c["field"] == "url"
               for c in conflicts), "the disagreement must be visible"
