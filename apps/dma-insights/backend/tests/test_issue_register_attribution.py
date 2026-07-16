"""Context-page Issue Register defect family (2026-07-06) — regression pins.

User mandate: "It should present the issues and not the name of the
documents… attribute the issue to how it affects the digital maturity
assessment."

Pack-wide symptoms pinned here against REAL corpus fixtures:
  - 219/662 rows were assessment-QA meta ("Missing governance artifact:
    caps_applied_log.csv"), 48 literally named files, 150 had blank
    titles, linked_subcap_ids on only 14%, heatmap issue_overlay dark.
  - The REAL issues lived unparsed in 08_appendices/A5_issue_register.csv
    (Wescom: Barracuda ESG breach, no-SOC-2) / A6_issues_register.csv
    (Bank of Utah: FDIC Consent Order FDIC-23-0038b, "CAPS P1C2 @3.0,
    P3C3 @2.5") and in 69/80 Client Profile Research Report DOCX
    "Risk & Issues" sections.

Covers: header classification (client vs assessment_qa), tolerant
row parsing (S1-S4 severities, fuzzy dates, cap-level mining, evidence
E-IDs, synthesized ids), package-level selection (client register wins,
QA rows namespaced + kept), DOCX issue mining + subcap-grain trigger
merge, persistence params (blank titles impossible, status/kind/caps/
dma_impact), and the derive_issues quality-gate classifier.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parsers.package_csvs import (
    canonical_issue_status,
    classify_issue_register_headers,
    compose_dma_impact,
    looks_like_assessment_qa_title,
    mine_cap_levels,
    mine_p_codes,
    parse_issue_register_csv,
)


def _find_app_root(start: Path) -> Path:
    for c in [start, *start.parents]:
        if (c / "backend").is_dir() and (c / "infra").is_dir():
            return c
    raise RuntimeError(f"app root not found from {start}")


APP_ROOT = _find_app_root(Path(__file__).resolve())
BATCHES = APP_ROOT / "backend" / "tests" / "fixtures" / "dma_packages_batches"
WESCOM = BATCHES / "batch_05" / "Wescom Financial - DMA"
BOK = BATCHES / "batch_14" / "Bank of Utah - DMA"
LPL_A5 = (BATCHES / "batch_08" / "LPL Financials - DMA" / "02_Evidence"
          / "A5_Issue_Register.csv")
SECFIN_A5 = (BATCHES / "batch_04" / "Security Finance - DMA"
             / "08_appendices" / "A5_issue_register.csv")


def _skip_unless(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"fixture not present: {path}")


@pytest.fixture(scope="module")
def wescom_pkg():
    _skip_unless(WESCOM)
    from app.services.parsers.dma_package import parse_package
    return parse_package(WESCOM)


@pytest.fixture(scope="module")
def bok_pkg():
    _skip_unless(BOK)
    from app.services.parsers.dma_package import parse_package
    return parse_package(BOK)


# ── Header classification ────────────────────────────────────────────


def test_qa_checklist_headers_classify_assessment_qa() -> None:
    # Wescom 07_governance (Check_ID/Fix) + BOK governance (check_id/fix).
    assert classify_issue_register_headers(
        ["Issue_ID", "Check_ID", "Severity", "Category", "Title",
         "Detail", "Fix"]) == "assessment_qa"
    assert classify_issue_register_headers(
        ["issue_id", "check_id", "severity", "name", "detail", "fix"]
    ) == "assessment_qa"
    # Odlum L2 (source_check/auto_fixable).
    assert classify_issue_register_headers(
        ["issue_id", "source_check", "severity", "category", "description",
         "detail", "fix_instruction", "auto_fixable", "status", "pass"]
    ) == "assessment_qa"


def test_client_register_headers_classify_client() -> None:
    for headers in (
        # Wescom A5
        ["Issue_ID", "Type", "Severity", "Status", "Description",
         "Regulator", "Date", "Capability_Impact", "Cap_Value",
         "Evidence_IDs"],
        # Bank of Utah A6
        ["Issue_ID", "Severity", "Title", "Date", "Status", "Source",
         "Subcaps", "Ceiling_Impact"],
        # LPL A5 (keyed by evidence_id)
        ["evidence_id", "regulator", "penalty_amount", "date",
         "description", "severity", "cap_impact", "status"],
        # Security Finance A5 (no id column)
        ["Issue", "Regulator", "Date", "Severity", "Status", "Milestones",
         "E_IDs"],
    ):
        assert classify_issue_register_headers(headers) == "client", headers


# ── Cap-level + P-code mining ─────────────────────────────────────────


def test_mine_cap_levels_bok_ceiling_impact_shape() -> None:
    assert mine_cap_levels("CAPS P1C2 @3.0, P3C3 @2.5") == {
        "P1C2": 3.0, "P3C3": 2.5,
    }


def test_mine_cap_levels_never_misreads_plain_lists() -> None:
    # A bare id list carries NO cap tokens — nothing may be invented,
    # and a following pair must not leak backward onto P1C2.
    assert mine_cap_levels("P4C4.7, P4C4.8, P3C4.5") == {}
    assert mine_cap_levels("P1C2, P3C3 @2.5") == {"P3C3": 2.5}


def test_mine_cap_levels_cap_and_max_score_phrasings() -> None:
    assert mine_cap_levels("P1C4 cap 4.0") == {"P1C4": 4.0}
    assert mine_cap_levels(
        "P3C2.4 max score M3.5 (real loss event managed)"
    ) == {"P3C2.4": 3.5}
    assert mine_cap_levels(
        "the active FDIC consent order capping P3C3 Compliance at 2.5"
    ) == {"P3C3": 2.5}


def test_mine_p_codes_orders_and_dedups() -> None:
    assert mine_p_codes(
        "P1C2 Governance Structure, P4C3 Technology Architecture; P1C2"
    ) == ["P1C2", "P4C3"]


# ── Row parsing against REAL fixture CSVs ─────────────────────────────


def test_bank_of_utah_a6_rows_parse_with_caps_and_dates() -> None:
    csv_path = BOK / "08_appendices" / "A6_issues_register.csv"
    _skip_unless(csv_path)
    rows = parse_issue_register_csv(csv_path.read_text())
    assert [r.kind for r in rows] == ["client"] * 4
    fdic = rows[0]
    assert fdic.description == "FDIC Consent Order FDIC-23-0038b"
    assert fdic.severity == "HIGH"  # S2
    assert fdic.opened_on == "2024-02-27"
    assert fdic.caps == {"P1C2": 3.0, "P3C3": 2.5}
    assert fdic.affected_categories[:3] == ["P1C2", "P3C3", "P3C4"]
    assert fdic.evidence_ids == ["E-015"]
    assert fdic.dma_impact is not None
    assert "P1C2 at M3" in fdic.dma_impact
    # S4 rows map to LOW.
    assert rows[2].severity == "LOW"


def test_lpl_a5_rows_keyed_by_evidence_id_with_resolved_status() -> None:
    _skip_unless(LPL_A5)
    rows = parse_issue_register_csv(LPL_A5.read_text())
    assert rows, "LPL register parsed empty"
    first = rows[0]
    assert first.issue_id == "E-075"
    assert first.severity == "HIGH"  # S2
    assert first.regulator == "SEC"
    # Subcap-grain attribution from cap_impact.
    assert "P3C3.2" in first.affected_categories
    # "Resolved Jan 2025" → canonical RESOLVED with a mined date.
    assert canonical_issue_status(first.status) == "RESOLVED"
    assert first.resolved_on == "2025-01-01"


def test_security_finance_a5_rows_synthesize_ids_and_mine_subcaps() -> None:
    """The Security Finance register has NO id column (`Issue,Regulator,
    Date,…`) and writes its capability refs inside E_IDs. The old parser
    dropped every row (no iid); rows must now synthesize sequential ids
    and mine the P-codes."""
    _skip_unless(SECFIN_A5)
    rows = parse_issue_register_csv(SECFIN_A5.read_text())
    assert len(rows) >= 3
    assert all(r.issue_id for r in rows)
    assert all((r.description or "").strip() for r in rows)
    first = rows[0]
    assert first.description.startswith("No identified CDO/CTO/CIO role")
    assert "P1C2" in first.affected_categories
    assert "P4C3" in first.affected_categories


def test_every_corpus_issue_register_row_has_a_title() -> None:
    """Blank titles impossible: sweep EVERY issue-register CSV in the
    fixture corpus — no parsed row may carry an empty description (the
    pack had 150 blank-titled rows; 10 clients rendered all-blank)."""
    if not BATCHES.is_dir():
        pytest.skip("batch fixtures not present")
    import re
    name_re = re.compile(r"issues?_?register|issueregister", re.I)
    swept = 0
    for csv_path in BATCHES.rglob("*.csv"):
        if not name_re.search(csv_path.name):
            continue
        rows = parse_issue_register_csv(
            csv_path.read_text(encoding="utf-8", errors="replace")
        )
        for r in rows:
            assert (r.description or "").strip(), (
                f"{csv_path} produced a blank-titled row {r.issue_id}"
            )
        swept += 1
    assert swept >= 50, f"corpus sweep found only {swept} registers"


# ── Package-level selection (Wescom + Bank of Utah) ───────────────────


def test_wescom_client_register_wins_over_governance_checklist(
    wescom_pkg,
) -> None:
    """The canonical user-visible defect: Wescom's context register
    showed 'Missing governance artifact: caps_applied_log.csv' (the
    bot's QA checklist) while 08_appendices/A5_issue_register.csv held
    the 10 REAL issues."""
    client = [r for r in wescom_pkg.issue_register if r.kind == "client"]
    qa = [r for r in wescom_pkg.issue_register if r.kind == "assessment_qa"]
    assert len(client) == 10
    assert len(qa) == 3
    # No client row is a filename/meta row.
    assert not any(looks_like_assessment_qa_title(r.description)
                   for r in client)
    # QA rows are kept (Health page) but namespaced out of collision.
    assert all(r.issue_id.startswith("QA-") for r in qa)
    descs = " | ".join(r.description for r in client)
    assert "Barracuda ESG breach" in descs
    assert "SOC 2" in descs


def test_wescom_barracuda_row_carries_subcap_grade_attribution(
    wescom_pkg,
) -> None:
    """Category caps from the A5 CSV (P4C4/P3C4 @ 3.0) PLUS subcap-grain
    caps merged from the Client Profile DOCX trigger table (P4C4.7,
    P4C4.8, P3C4.5, P3C4.6 @ 3.0) — DMA impact reaches heatmap grain."""
    barracuda = next(
        r for r in wescom_pkg.issue_register
        if r.kind == "client" and "Barracuda" in r.description
    )
    assert barracuda.caps.get("P4C4") == 3.0
    assert barracuda.caps.get("P4C4.7") == 3.0
    assert barracuda.caps.get("P3C4.5") == 3.0
    assert barracuda.severity == "CRITICAL"
    assert canonical_issue_status(barracuda.status) == "RESOLVED"  # SETTLED
    assert barracuda.opened_on == "2022-10-01"
    assert barracuda.evidence_ids == ["E-026", "E-069"]
    assert barracuda.dma_impact and barracuda.dma_impact.startswith("Caps ")


def test_bank_of_utah_fdic_consent_order_surfaces(bok_pkg) -> None:
    """Bank of Utah's pack rows were ALL blank-titled (governance CSV
    header row `issue_id,check_id,severity,name,detail,fix`); the A6
    appendix register with the FDIC consent order never surfaced."""
    client = [r for r in bok_pkg.issue_register if r.kind == "client"]
    qa = [r for r in bok_pkg.issue_register if r.kind == "assessment_qa"]
    assert any("FDIC Consent Order" in r.description for r in client)
    fdic = next(r for r in client if "FDIC Consent Order" in r.description)
    assert fdic.caps == {"P1C2": 3.0, "P3C3": 2.5}
    # The governance QA rows keep a real title too (name column aliased).
    assert all((r.description or "").strip() for r in qa)
    # And every row in the whole register is titled.
    assert all((r.description or "").strip()
               for r in bok_pkg.issue_register)


# ── Client Profile DOCX mining ────────────────────────────────────────


def test_wescom_profile_docx_mines_issue_register_table() -> None:
    docx = (WESCOM / "04_reports"
            / "Wescom_Financial_Client_Profile_Research_Report.docx")
    _skip_unless(docx)
    from app.services.parsers.client_profile import parse_client_profile_path
    r = parse_client_profile_path(docx)
    assert len(r.issue_rows) == 10
    assert r.issue_rows[0]["source"] == "docx:issue_table"
    assert any("Barracuda" in d["description"] for d in r.issue_rows)
    # Trigger table → subcap-grain caps.
    assert len(r.issue_cap_triggers) >= 5
    barracuda_trig = next(t for t in r.issue_cap_triggers
                          if "Barracuda" in t["trigger"])
    assert "P4C4.7" in barracuda_trig["subcap_ids"]
    assert barracuda_trig["max_score"] == 3.0


def test_bok_profile_docx_mines_risk_prose_sentences() -> None:
    docx = BOK / "04_reports" / "DMA_Client_Profile_Research_Report_V3.docx"
    _skip_unless(docx)
    from app.services.parsers.client_profile import parse_client_profile_path
    r = parse_client_profile_path(docx)
    assert r.issue_rows, "risk prose mined nothing"
    assert all(d["source"] == "docx:risk_prose" for d in r.issue_rows)
    fdic = next((d for d in r.issue_rows
                 if "consent order" in d["description"].lower()), None)
    assert fdic is not None
    assert fdic["regulator"] == "FDIC"
    # Positive/clean-standing statements are never emitted as issues.
    assert not any("zero" in d["description"].lower()
                   for d in r.issue_rows)
    # The cap sentence carries subcap-level attribution.
    capped = [d for d in r.issue_rows if d.get("caps")]
    assert any(d["caps"].get("P3C3") == 2.5 for d in capped)


# ── Persistence params (pure) ─────────────────────────────────────────


def test_issue_register_params_blank_titles_impossible() -> None:
    from app.schemas.package import IssueRow
    from app.services.parsers.package_persist import issue_register_params

    rows = [
        IssueRow(issue_id="ISS-001", severity="HIGH", description="   "),
        IssueRow(issue_id="ISS-002", severity="HIGH", description=""),
        IssueRow(issue_id="ISS-003", severity="S2",
                 description="FDIC Consent Order FDIC-23-0038b",
                 status="ACTIVE", opened_on="2024-02-27",
                 caps={"P1C2": 3.0, "P3C3": 2.5},
                 affected_categories=["P1C2", "P3C3"],
                 dma_impact="Caps P1C2 at M3, P3C3 at M2.5 — open",
                 kind="client"),
    ]
    params = issue_register_params("rid", "eid", rows)
    assert len(params) == 1  # both untitled rows skipped
    p = params[0]
    assert p["title"] == "FDIC Consent Order FDIC-23-0038b"
    assert p["st"] == "OPEN"
    assert p["kind"] == "client"
    assert p["od"] is not None and p["od"].isoformat() == "2024-02-27"
    assert p["ls"] == ["P1C2", "P3C3"]
    import json
    assert json.loads(p["caps"]) == {"P1C2": 3.0, "P3C3": 2.5}
    assert p["impact"].startswith("Caps ")


def test_issue_register_params_crafts_title_for_overlong_text() -> None:
    from app.schemas.package import IssueRow
    from app.services.parsers.package_persist import issue_register_params

    long_desc = (
        "The organization's customer master data quality issues span "
        "duplicate records across three separate core banking systems, "
        "which materially degrades campaign targeting, servicing "
        "hand-offs and regulatory reporting accuracy across the retail "
        "and commercial lines of business."
    )
    params = issue_register_params(
        "rid", "eid",
        [IssueRow(issue_id="ISS-009", severity="HIGH",
                  description=long_desc, kind="client")],
    )
    assert len(params) == 1
    title = params[0]["title"]
    assert title.strip()
    assert len(title) <= 200
    # Full text preserved in rationale.
    assert long_desc in (params[0]["rat"] or "")


def test_issue_register_params_resolved_status_from_settled() -> None:
    from app.schemas.package import IssueRow
    from app.services.parsers.package_persist import issue_register_params

    params = issue_register_params(
        "rid", "eid",
        [IssueRow(issue_id="ISS-001", severity="CRITICAL",
                  description="Barracuda ESG breach settled Sep 2025",
                  status="SETTLED", kind="client")],
    )
    assert params[0]["st"] == "RESOLVED"


# ── Serve-time DTO status derivation ──────────────────────────────────


def test_to_issue_register_prefers_stored_canonical_status() -> None:
    from dataclasses import dataclass, field

    from app.services.context_extras import to_issue_register

    @dataclass
    class _Row:
        id: str = "u1"
        issue_id: str = "ISS-001"
        title: str = "Barracuda ESG breach"
        severity: str = "critical"
        rationale: str | None = None
        opened_on: object = None
        resolved_on: object = None
        status: str | None = "RESOLVED"
        linked_subcap_ids: list = field(default_factory=list)
        kind: str = "client"
        dma_impact: str | None = "Caps P4C4 at M3 — Security, resolved"
        caps: dict = field(default_factory=lambda: {"P4C4": 3.0})

    out = to_issue_register([_Row()])
    assert out[0].status == "RESOLVED"  # no resolved_on date needed
    assert out[0].dma_impact == "Caps P4C4 at M3 — Security, resolved"
    assert out[0].caps == {"P4C4": 3.0}
    assert out[0].kind == "client"


# ── Quality-gate meta classifier (derive_issues + migration 055) ─────


def test_assessment_qa_title_classifier() -> None:
    for meta in (
        "Missing governance artifact: caps_applied_log.csv",
        "Missing governance artifact: contradiction_log.csv",
        "run_manifest missing required fields",
        "Report citation density ≥30 E-IDs",
        "17 rationales missing E-ID refs",
        "Sheet naming mismatch P2C3",
    ):
        assert looks_like_assessment_qa_title(meta), meta
    for client in (
        "FDIC Consent Order FDIC-23-0038b",
        "Barracuda ESG breach: 34,515 individuals",
        "No SOC 2 or ISO 27001 attestation for WRG",
        "Customer master data quality issues",
    ):
        assert not looks_like_assessment_qa_title(client), client


def test_compose_dma_impact_shapes() -> None:
    from app.schemas.package import IssueRow

    caps_row = IssueRow(
        issue_id="ISS-001", severity="HIGH", description="x",
        caps={"P1C2": 3.0, "P3C3": 2.5}, type="Regulatory",
        regulator="FDIC", status="ACTIVE",
    )
    line = compose_dma_impact(caps_row)
    assert line == "Caps P1C2 at M3, P3C3 at M2.5 — Regulatory (FDIC), open"
    # Ceiling + affected fallback.
    ceil_row = IssueRow(
        issue_id="ISS-002", severity="HIGH", description="x",
        cap_ceiling=3.0, affected_categories=["P4C4", "P3C4"],
        status="SETTLED",
    )
    assert compose_dma_impact(ceil_row) == \
        "Caps P4C4, P3C4 at M3 — resolved"
    # Nothing to attribute → honest None.
    assert compose_dma_impact(
        IssueRow(issue_id="ISS-003", severity="LOW", description="x")
    ) is None
