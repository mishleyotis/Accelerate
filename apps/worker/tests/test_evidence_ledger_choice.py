"""Two defects of the evidence-ledger reader, measured on Golden 1 Credit
Union (2026-09-01) and ported onto the multi-tab merge the parser now does.

- `Evidence_Master.Finding` is an excerpt-class column under a name the alias
  table did not list: 731 of 731 rows populated at 64-227 characters, all
  inside the 50-500 band, and a register carrying it and nothing else served
  no excerpt at all. It joins the summary tail, never ahead of a real
  quotation column.
- The per-column census read the PARSED rows under the alias names, while the
  rows carry the band as `stated_recency` and the date as `published_date`,
  so it counted zero every time and reported a 731/731 populated Recency
  column as `column_mapped_but_empty` — a systematic false positive on every
  package carrying those headers.

The richest-ledger tie-break the original commit added is not ported: the
parser on this line reads EVERY ledger tab and fills holes from the
secondaries (`evidence_ledger_merged`), which covers the Golden 1 shape by a
different route and is pinned by test_evidence_urls_come_from_every_tab.py.
"""
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.workbook_parser import parse_evidence_master  # noqa: E402

# The real shape, verbatim from the Golden 1 workbook's Evidence_Master header.
MASTER_COLS = ["Evidence_ID", "Source", "URL", "Tier", "Recency",
               "Claim_Type", "Finding", "Origin"]

EXCERPT = ("Golden 1 Credit Union entered a three-year technology agreement "
           "for AML RightSource Automated EDD and the AI Automated "
           "Investigator, which automate enhanced due diligence review.")
FINDING = ("AML RightSource selected for automated enhanced due diligence "
           "under a three-year agreement.")


def _master_row(eid, recency="DATED"):
    return [eid, "AML RightSource press release", "https://example.org/a",
            "T3", recency, "FACT", FINDING, "public"]


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


def test_a_lone_master_reads_and_announces_no_merge(tmp_path):
    """The single-ledger case is most of the corpus: one tab, nothing to
    merge from, nothing narrated as a choice."""
    path = _workbook(tmp_path, [
        ("Evidence_Master", MASTER_COLS, [_master_row("E-9095")]),
    ])
    obs = []
    rows = parse_evidence_master(path, obs)
    assert len(rows) == 1
    assert rows[0]["e_id"] == "E-9095"
    assert not _obs(obs, "evidence_ledger_merged")


def test_finding_is_read_as_an_excerpt_where_it_is_the_only_text(tmp_path):
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
    path = _workbook(tmp_path, [
        ("Evidence_Master", MASTER_COLS, [_master_row("E-1"), _master_row("E-2")]),
    ])
    obs = []
    rows = parse_evidence_master(path, obs)
    assert all(r["stated_recency"] == "DATED" for r in rows)
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
