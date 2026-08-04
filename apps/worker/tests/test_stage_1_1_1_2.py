"""Stage 1.1/1.2 QA bullets as tests — the pure-logic layer.

Drive-dependent behaviour (scheduled traversal, scan diffing against
import_scans) is exercised against fixture trees in the integration
suite once the intake folder is shared; the contracts below are the
plan's verification bullets that hold without IO.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.classification import classify, detect_test_case
from dma_worker.dedup import Candidate, pick_winner
from dma_worker.entity_resolution import normalise_name, resolve


# ── 1.1 classification ─────────────────────────────────────────────────
def test_registry_ranks_by_source_priority():
    wb = classify("AlmaBank_Scoring_Workbook_v7.xlsx")
    report = classify("04_reports/Assessment_Report_AlmaBank.docx")
    profile = classify("AlmaBank_Client_Profile_Research_Report.docx")
    pkg = classify("evidence_index.csv")
    assert wb.priority == 1 and wb.kind == "scoring_workbook"
    assert report.priority == 2 and profile.priority == 3 and pkg.priority == 4
    assert classify("random_notes.txt") is None   # recorded, not dropped


# ── 1.1/1.2 test-case exclusion, recorded with the rule ────────────────
def test_test_folder_never_produces_an_entity():
    rule = detect_test_case(["Assessments", "TEST - AlmaBank rehearsal", "workbook.xlsx"])
    assert rule == "test_marker"
    # the rule id is what the audit records; a different marker names itself
    assert detect_test_case(["Demo Client", "pkg.zip"]) == "demo_marker"
    assert detect_test_case(["Assessments", "AlmaBank", "workbook.xlsx"]) is None


def test_marker_anywhere_up_the_tree_excludes_the_subtree():
    assert detect_test_case(["Sandbox", "AlmaBank", "real_looking.xlsx"]) == "sandbox_marker"


# ── 1.2 the four-signal cascade ────────────────────────────────────────
def test_manifest_wins_and_stops_the_cascade():
    r = resolve("alma-bank", "DMA-ASM-OTHER-20260101-0001", "Other Bank, N.A.", "other-folder")
    assert r.signal == "manifest" and r.entity_token == "alma-bank" and r.status == "ACTIVE"


def test_request_identifier_carries_the_entity_token():
    r = resolve(None, "DMA-ASM-ZION-20260503-0001", None, None)
    assert r.signal == "request_id" and r.entity_token == "ZION" and r.status == "ACTIVE"


def test_bot_format_identifies_run_not_entity():
    # REQ-{8 hex} has no entity token in its own structure -> cascade continues
    r = resolve(None, "REQ-9F2C1B7E", None, "AlmaBank")
    assert r.signal == "folder_name"


def test_header_resolves_against_known_suffixes_and_trading_names():
    known = {normalise_name("Alma Bank, N.A."): "alma-bank"}
    r = resolve(None, None, "ALMA BANK N.A.", None, known_names=known)
    assert r.signal == "document_header" and r.entity_token == "alma-bank" and r.status == "ACTIVE"


def test_unknown_header_is_pending_review():
    r = resolve(None, None, "Totally New Bancorp Inc.", None, known_names={})
    assert r.status == "PENDING_REVIEW"


def test_folder_name_is_pending_review_never_active():
    r = resolve(None, None, None, "First National Bank of Omaha")
    assert r.signal == "folder_name" and r.status == "PENDING_REVIEW"
    assert r.confidence < 0.5


# ── 1.2 dedup: strict order, reproducible, loser retained ─────────────
def _c(key, prio, when, sections):
    return Candidate(key, prio, when, sections)


def test_dedup_rule_order_is_strict():
    newer_but_lower_priority = _c("b", 4, datetime(2026, 7, 1, tzinfo=timezone.utc), 12)
    older_workbook = _c("a", 1, datetime(2026, 1, 1, tzinfo=timezone.utc), 3)
    out = pick_winner([newer_but_lower_priority, older_workbook])
    assert out.winner.stable_key == "a"           # priority beats recency
    assert out.losers[0][1] == "artefact_priority"

    d = datetime(2026, 7, 1, tzinfo=timezone.utc)
    out2 = pick_winner([_c("x", 1, d, 5), _c("y", 1, datetime(2026, 8, 1, tzinfo=timezone.utc), 3)])
    assert out2.winner.stable_key == "y"          # same priority: newer wins
    assert out2.losers[0][1] == "completion_date"

    out3 = pick_winner([_c("x", 1, d, 5), _c("y", 1, d, 9)])
    assert out3.winner.stable_key == "y" and out3.losers[0][1] == "parsed_section_count"


def test_dedup_is_reproducible_and_retains_losers():
    d = datetime(2026, 7, 1, tzinfo=timezone.utc)
    cands = [_c("m", 1, d, 5), _c("k", 1, d, 5), _c("z", 1, d, 5)]
    first = pick_winner(list(cands))
    second = pick_winner(list(reversed(cands)))
    assert first.winner.stable_key == second.winner.stable_key == "k"   # stable tiebreak
    assert {c.stable_key for c, _ in first.losers} == {"m", "z"}        # retained, marked
    assert all(rule == "stable_tiebreak" for _, rule in first.losers)
