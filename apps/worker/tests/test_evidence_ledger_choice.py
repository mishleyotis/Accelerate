"""The richest evidence ledger wins, not the first-named one.

Measured on Golden 1 Credit Union (`DMA-2026-GOLDEN1-001`, run
40971653-aa3e-4373-9163-a967c57a9305), 2026-09-01. The workbook carries THREE
evidence ledgers — `Evidence_Master` (8 columns), `Evidence_Register` (a
byte-identical mirror) and `Evidence_Detail` (17 columns: 727/727 verbatim
excerpts inside the 50-500 band, 727/727 dated, 723/727 subcap-linked).

`_EV_TABS` is an ordered tuple and the reader took `next(...)` over it, so
`Evidence_Master` won on index order — the only one of the three with no
excerpt column, no date column and no subcap column. The consequence, recorded
by the connector on the live run: `evidence_excerpt_uncitable` 589, excerpts
mined out of scoring rationales at 142 of 631, and 38 of 65 rejection rows
(ET-04 x38, CG-50 x36, ET-07 x1) raised against a package that had supplied
every one of those spans.

`_EV_TABS` exists because 15 of 153 corpus packages name the tab something
other than `Evidence_Master`. It was never meant to RANK tabs when several are
present. Shape decides now; the tuple order survives as the tie-break, so a
package carrying one ledger reads exactly as it did before.
"""
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.workbook_parser import parse_evidence_master

# The two real shapes, verbatim from the Golden 1 workbook's header rows.
MASTER_COLS = ["Evidence_ID", "Source", "URL", "Tier", "Recency",
               "Claim_Type", "Finding", "Origin"]
DETAIL_COLS = ["E_ID", "Fact_ID", "Source_Name", "Source_URL", "Tier", "ERS",
               "Date_Published", "Recency", "Claim_Type", "Fact_Count",
               "SubCap_IDs", "Excerpt", "Anchor_Quote", "Retrieved_At",
               "Origin", "Access_Status", "Conflict"]

EXCERPT = ("Golden 1 Credit Union entered a three-year technology agreement "
           "for AML RightSource Automated EDD and the AI Automated "
           "Investigator, which automate enhanced due diligence review.")
FINDING = ("AML RightSource selected for automated enhanced due diligence "
           "under a three-year agreement.")


def _master_row(eid):
    return [eid, "AML RightSource press release", "https://example.org/a",
            "T3", "LEGACY", "FACT", FINDING, "public"]


def _detail_row(eid):
    return [eid, "F1", "AML RightSource press release", "https://example.org/a",
            "T3", "3.1", "2023-03-08", "LEGACY", "FACT", "1", "P3C2.5.3",
            EXCERPT, EXCERPT, "2026-08-31T06:19:15Z", "public", "OK", "none"]


def _workbook(tmp_path, tabs, name="wb.xlsx"):
    """tabs: [(title, header, [rows])] in the order the file declares them."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, header, rows in tabs:
        ws = wb.create_sheet(title=title)
        ws.append(list(header))
        for r in rows:
            ws.append(list(r))
    path = tmp_path / name
    wb.save(path)
    return str(path)


def _obs(observations, kind):
    return [o for o in observations if o.kind == kind]


def test_the_golden_1_shape_reads_the_detail_tab_not_the_master(tmp_path):
    """The measured regression: three ledgers present, the richest wins."""
    path = _workbook(tmp_path, [
        ("Evidence_Master", MASTER_COLS, [_master_row("E-9095")]),
        ("Evidence_Register", MASTER_COLS, [_master_row("E-9095")]),
        ("Evidence_Detail", DETAIL_COLS, [_detail_row("E-9095")]),
    ])
    obs = []
    rows = parse_evidence_master(path, obs)

    assert len(rows) == 1
    row = rows[0]
    # All three invariant-4 obligations land, and they only exist on Detail.
    assert row["excerpt"] == EXCERPT, "the verbatim span must come from Evidence_Detail"
    assert 50 <= len(row["excerpt"]) <= 500
    assert str(row["published_date"]) == "2023-03-08", "Evidence_Master carries no date column at all"
    assert row["subcaps"] == ["P3C2.5.3"], "Evidence_Master carries no subcap column at all"

    chosen = _obs(obs, "evidence_ledger_tab_chosen")
    assert chosen, "a reader that passed over two ledgers must say so"
    assert chosen[0].detail["chose"] == "Evidence_Detail"
    assert {p["tab"] for p in chosen[0].detail["passed_over"]} == {
        "Evidence_Master", "Evidence_Register"}


def test_a_lone_master_still_reads_exactly_as_before(tmp_path):
    """The tie-break must not change the single-ledger case, which is most
    of the corpus. Nothing is passed over, so nothing is announced."""
    path = _workbook(tmp_path, [
        ("Evidence_Master", MASTER_COLS, [_master_row("E-9095")]),
    ])
    obs = []
    rows = parse_evidence_master(path, obs)

    assert len(rows) == 1
    assert rows[0]["e_id"] == "E-9095"
    assert not _obs(obs, "evidence_ledger_tab_chosen"), \
        "one candidate is not a choice and must not be narrated as one"


def test_identical_shapes_keep_the_declared_tab_order(tmp_path):
    """Evidence_Register is a byte-identical mirror of Evidence_Master on the
    real workbook. Where shape cannot separate two ledgers the historical
    `_EV_TABS` order still decides, so this fix moves nothing it need not."""
    path = _workbook(tmp_path, [
        ("Evidence_Register", MASTER_COLS, [_master_row("E-1")]),
        ("Evidence_Master", MASTER_COLS, [_master_row("E-1")]),
    ])
    obs = []
    parse_evidence_master(path, obs)
    chosen = _obs(obs, "evidence_ledger_tab_chosen")
    assert chosen and chosen[0].detail["chose"] == "Evidence_Master", \
        "_EV_TABS lists Master before Register; a tie must not reorder them"


def test_finding_is_read_as_an_excerpt_where_it_is_the_only_text(tmp_path):
    """Evidence_Master.Finding is 731/731 populated at 64-227 chars on the
    real workbook — an excerpt-class column under a name the alias table did
    not list, so a register carrying it and nothing else served no excerpt."""
    path = _workbook(tmp_path, [
        ("Evidence_Master", MASTER_COLS, [_master_row("E-9095")]),
    ])
    rows = parse_evidence_master(path, [])
    assert rows[0]["excerpt"] == FINDING


def test_a_real_quotation_outranks_finding_when_both_are_present(tmp_path):
    """`finding` sits in the summary tail. A column named for the assessor's
    finding must never displace one named for the source's words."""
    cols = MASTER_COLS + ["Anchor_Quote"]
    path = _workbook(tmp_path, [
        ("Evidence_Master", cols, [_master_row("E-9095") + [EXCERPT]]),
    ])
    rows = parse_evidence_master(path, [])
    assert rows[0]["excerpt"] == EXCERPT


def test_a_populated_recency_column_is_never_reported_empty(tmp_path):
    """The per-column census reads the PARSED rows, which carry the band under
    `stated_recency` and the date under `published_date`. Keyed on the alias
    name it counted zero every time: the connector recorded
    `column_mapped_but_empty` for Evidence_Master.recency on a column that is
    731/731 populated."""
    path = _workbook(tmp_path, [
        ("Evidence_Master", MASTER_COLS, [_master_row("E-1"), _master_row("E-2")]),
    ])
    obs = []
    rows = parse_evidence_master(path, obs)

    assert all(r["stated_recency"] == "LEGACY" for r in rows)
    empties = {o.detail["field"] for o in _obs(obs, "column_mapped_but_empty")}
    assert "recency" not in empties, \
        "a fully populated Recency column was reported as read-but-empty"


def test_a_genuinely_empty_column_is_still_reported(tmp_path):
    """The census must keep catching what it was built for — the renaming fix
    must not blind it. MEM-0006, third sighting."""
    rows_in = [["E-1", "src", "https://example.org/a", "T3", None,
                "FACT", FINDING, "public"]]
    path = _workbook(tmp_path, [("Evidence_Master", MASTER_COLS, rows_in)])
    obs = []
    parse_evidence_master(path, obs)
    empties = {o.detail["field"] for o in _obs(obs, "column_mapped_but_empty")}
    assert "recency" in empties, \
        "a header that WAS found and read nothing from must still be named"
