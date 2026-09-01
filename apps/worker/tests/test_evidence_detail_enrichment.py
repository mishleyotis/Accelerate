"""A ledger without excerpts is enriched from its sibling Evidence_Detail.

The general_dma research package ships its evidence ledger as `Evidence_Master`
— ids, source, url, tier, claim — and the VERBATIM SPANS, publication dates
and recency bands in a separate `Evidence_Detail` tab anchored on the same
ids. `_EV_TABS` names the first present tab as the ledger, so `Evidence_Master`
won every time and `Evidence_Detail` was never read: every row landed
excerpt-less (weakly mined from Rationale) and date-less (banded UNVERIFIED).
Downstream, every cited chip on the heatmap opened onto nothing and tripped
ET-04 at submit — measured on the Golden 1 Credit Union run, 727 of 727
evidence rows uncitable while their spans sat one tab over.

parse_evidence_master now joins that sibling back on by exact id, additively:
a field the ledger already filled is never overwritten, and a package with a
single evidence tab is untouched.
"""
import sys
from datetime import date
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                       / "packages" / "shared"))

from dma_worker.workbook_parser import parse_evidence_master  # noqa: E402


def _span(i: int) -> str:
    """A verbatim sentence comfortably inside the 50-500 fail-closed window."""
    return (f"Golden 1 Credit Union stated fact number {i} in its own filing, "
            f"a whole sentence of ordinary length that ends as sentences do.")


def _write(path, *, with_detail: bool, master_has_excerpt: bool = False):
    wb = openpyxl.Workbook()
    m = wb.active
    m.title = "Evidence_Master"
    if master_has_excerpt:
        m.append(["Evidence_ID", "Source", "URL", "Tier", "Recency",
                  "Claim_Type", "Excerpt", "Origin"])
        m.append(["E-001", "Golden 1 2025 Annual Report", "https://g1.example",
                  "T2", "CURRENT", "FACT", "A DIFFERENT primary span the "
                  "ledger itself carried, long enough to pass the window.",
                  "public"])
    else:
        # The shape that broke: no excerpt column, no date column.
        m.append(["Evidence_ID", "Source", "URL", "Tier", "Recency",
                  "Claim_Type", "Finding", "Origin"])
        m.append(["E-001", "Golden 1 2025 Annual Report", "https://g1.example",
                  "T2", "CURRENT", "FACT", "assets ~$21.7B", "public"])
    m.append(["E-002", "Fiserv case study", "https://fiserv.example", "T3",
              "RECENT", "FACT",
              ("A different span the ledger carried." if master_has_excerpt
               else "real-time payments live"), "public"])

    if with_detail:
        d = wb.create_sheet("Evidence_Detail")
        d.append(["E_ID", "Source_Name", "Source_URL", "Tier", "Date_Published",
                  "Recency", "Claim_Type", "Excerpt", "Anchor_Quote"])
        d.append(["E-001", "Golden 1 2025 Annual Report", "https://g1.example",
                  "T2", "2025-12-31", "CURRENT", "FACT", _span(1), _span(1)])
        d.append(["E-002", "Fiserv case study", "https://fiserv.example", "T3",
                  "2024-11-01", "RECENT", "FACT", _span(2), _span(2)])
    wb.save(path)


def test_master_ledger_is_enriched_from_sibling_detail(tmp_path):
    p = tmp_path / "wb.xlsx"
    _write(p, with_detail=True)
    obs = []
    rows = parse_evidence_master(str(p), obs)
    by_id = {r["e_id"]: r for r in rows}

    # Every row now opens onto a real verbatim span in the fail-closed window.
    for e_id in ("E-001", "E-002"):
        exc = (by_id[e_id]["excerpt"] or "").strip()
        assert 50 <= len(exc) <= 500, f"{e_id} excerpt not in window: {exc!r}"

    # The date came across too, so the row bands by its date, not UNVERIFIED.
    assert by_id["E-001"]["published_date"] == date(2025, 12, 31)
    assert by_id["E-002"]["published_date"] == date(2024, 11, 1)

    # The join is reported, not silent, and names the counts.
    enr = [o for o in obs if o.kind == "evidence_detail_enrichment"]
    assert len(enr) == 1
    assert enr[0].detail["detail_tab"] == "Evidence_Detail"
    assert enr[0].detail["excerpts_filled"] == 2
    assert enr[0].detail["dates_filled"] == 2


def test_single_tab_package_is_unchanged(tmp_path):
    """No sibling detail tab: the reader lends nothing and does not crash."""
    p = tmp_path / "wb.xlsx"
    _write(p, with_detail=False)
    obs = []
    rows = parse_evidence_master(str(p), obs)
    assert {r["e_id"] for r in rows} == {"E-001", "E-002"}
    assert all(not (r.get("excerpt") or "") for r in rows)
    assert not [o for o in obs if o.kind == "evidence_detail_enrichment"]


def test_ledgers_own_excerpt_is_authoritative_and_not_overwritten(tmp_path):
    """Enrichment is additive: a span the ledger carried itself is kept."""
    p = tmp_path / "wb.xlsx"
    _write(p, with_detail=True, master_has_excerpt=True)
    obs = []
    rows = parse_evidence_master(str(p), obs)
    e001 = next(r for r in rows if r["e_id"] == "E-001")
    assert e001["excerpt"].startswith("A DIFFERENT primary span")
    # The date was still absent from the ledger, so THAT is filled.
    assert e001["published_date"] == date(2025, 12, 31)
    enr = [o for o in obs if o.kind == "evidence_detail_enrichment"]
    assert enr and enr[0].detail["excerpts_filled"] == 0
    assert enr[0].detail["dates_filled"] == 2
