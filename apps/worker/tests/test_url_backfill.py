"""A stored row gets back the URL its package always carried — and nothing else.

T. Rowe Price, measured 2026-08-23: 757 of 894 served evidence items carry no
URL. Not one was researched wrong. The workbook register states 753 of 757 and
`01_evidence/evidence_index.json` states 748 of 752, and the worker's own
parser reads them correctly today. The run predates the fix — ingested
2026-08-10, and the ingest only began writing `source_url` on 2026-08-18.

Dry-run against the real package and the real served set: 747 fills, 10 rows
nothing could answer, 137 already had one.

The dangerous version of this file is the one that quietly does more than it
says. These tests are mostly about what it must NOT do.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.url_backfill import (apply, plan,          # noqa: E402
                                     urls_from_package)

SEC = "https://www.sec.gov/Archives/edgar/data/1113169/trow-20251231.htm"
FINRA = "https://files.brokercheck.finra.org/firm/firm_8348.pdf"


def _pkg(tmp_path, rows, name="01_evidence/evidence_index.json"):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"items": rows}))
    return tmp_path


# ── the join ──


def test_a_stored_id_joins_back_to_its_package_local_id(tmp_path):
    """`E-002` in the package became `E-TROW-002` in the store. THE MISTAKE
    THIS PINS: the first version keyed the lookup with `local_id`, which
    normalises package-local ids and returns None for every stored one — so
    the backfill would have run, reported success, and filled nothing."""
    root = _pkg(tmp_path, [{"evidence_id": "E-002", "url": SEC}])
    got = plan([{"e_id": "E-TROW-002", "source_url": None}],
               urls_from_package(root))
    assert got["fills"] == [{"e_id": "E-TROW-002", "source_url": SEC}]
    assert got["unanswered"] == []


@pytest.mark.parametrize("stored", ["E-TROW-002", "E-TROW-002-R2",
                                    "E-BCU-002", "E-UNK-002-1FCA91"])
def test_every_mint_variant_of_one_local_id_joins(tmp_path, stored):
    """A re-mint is the same source read again; it needs the same URL."""
    root = _pkg(tmp_path, [{"evidence_id": "E-002", "url": SEC}])
    got = plan([{"e_id": stored, "source_url": None}], urls_from_package(root))
    assert got["fills"] and got["fills"][0]["source_url"] == SEC


def test_a_server_minted_id_never_acquires_a_package_url(tmp_path):
    """`E-CC-104` is the server's own mint, not workbook-local. It must not
    collide with a bare `E-104` from the package — that would attach one
    source's URL to a different source's claim."""
    root = _pkg(tmp_path, [{"evidence_id": "E-104", "url": SEC}])
    got = plan([{"e_id": "E-CC-104", "source_url": None}],
               urls_from_package(root))
    assert got["fills"] == []
    assert got["unanswered"] == ["E-CC-104"]


# ── what it must not do ──


def test_a_stored_url_is_never_replaced(tmp_path):
    """A URL already in the store may have been repaired by hand. This file
    does not know better than a human who looked at it."""
    root = _pkg(tmp_path, [{"evidence_id": "E-002", "url": SEC}])
    got = plan([{"e_id": "E-TROW-002", "source_url": FINRA}],
               urls_from_package(root))
    assert got["fills"] == []
    assert got["already_had_one"] == 1


def test_a_row_the_package_cannot_answer_is_counted_not_invented(tmp_path):
    root = _pkg(tmp_path, [{"evidence_id": "E-002", "url": SEC}])
    got = plan([{"e_id": "E-TROW-999", "source_url": None}],
               urls_from_package(root))
    assert got["fills"] == []
    assert got["unanswered"] == ["E-TROW-999"]


def test_a_non_url_in_the_package_is_not_a_url(tmp_path):
    """`multiple`, `see source`, `N/A` are notes to a human. Filling one in
    would turn an honest blank into an unopenable link."""
    root = _pkg(tmp_path, [{"evidence_id": "E-002", "url": "multiple"},
                           {"evidence_id": "E-003", "url": "N/A"},
                           {"evidence_id": "E-004", "url": ""}])
    got = plan([{"e_id": f"E-TROW-{n}", "source_url": None}
                for n in ("002", "003", "004")], urls_from_package(root))
    assert got["fills"] == []
    assert len(got["unanswered"]) == 3


def test_apply_only_ever_fills_a_null():
    """The WHERE clause is the safety, not the caller's discipline."""
    seen = []

    class Cur:
        rowcount = 1

        def execute(self, sql, args):
            seen.append((sql, args))

    apply(Cur(), [{"e_id": "E-TROW-002", "source_url": SEC}])
    sql, args = seen[0]
    assert "UPDATE evidence_index" in sql
    assert "source_url IS NULL OR source_url = ''" in sql
    assert args == (SEC, "E-TROW-002")


# ── reading the stores ──


def test_the_richest_store_wins_and_a_later_one_does_not_overwrite(tmp_path):
    root = _pkg(tmp_path, [{"evidence_id": "E-002", "url": SEC}])
    (root / "01_evidence" / "ledger.jsonl").write_text(
        json.dumps({"evidence_id": "E-002", "url": FINRA}) + "\n")
    assert urls_from_package(root)["E-002"] == SEC


def test_a_jsonl_store_is_read(tmp_path):
    (tmp_path / "01_evidence").mkdir(parents=True)
    (tmp_path / "01_evidence" / "ledger.jsonl").write_text(
        json.dumps({"evidence_id": "E-009", "url": FINRA}) + "\n")
    assert urls_from_package(tmp_path)["E-009"] == FINRA


def test_a_missing_or_unreadable_store_is_not_a_crash(tmp_path):
    (tmp_path / "01_evidence").mkdir(parents=True)
    (tmp_path / "01_evidence" / "evidence_index.json").write_text("{not json")
    assert urls_from_package(tmp_path) == {}


def test_a_package_with_no_stores_yields_nothing_rather_than_failing(tmp_path):
    assert urls_from_package(tmp_path) == {}


# ── the real package, when this container has pulled it ──

PKG = Path("/root/.dma/packages/t-rowe-price-dma")


def _pulled() -> bool:
    try:
        return (PKG / "01_evidence" / "evidence_index.json").is_file()
    except OSError:
        return False


@pytest.mark.skipif(not _pulled(),
                    reason="T. Rowe package not pulled/readable here")
def test_the_real_package_answers_almost_every_stored_row():
    urls = urls_from_package(PKG)
    assert len(urls) > 700, f"only {len(urls)} URLs read from the package"
    got = plan([{"e_id": f"E-TROW-{n:03d}", "source_url": None}
                for n in range(2, 200)], urls)
    assert len(got["fills"]) > 150
    assert all(f["source_url"].startswith("http") for f in got["fills"])
