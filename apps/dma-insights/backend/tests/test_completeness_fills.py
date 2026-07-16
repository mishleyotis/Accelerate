"""Pure-logic tests for the no-empty-state completeness fills (2026-06).

Covers the grounded fills that closed the 94-client empty-state gaps:
  * issue-register alias-aware parse (BOK ISS_ID/Finding, Chemung description)
  * derive_issues severity normalization + capability-gap severity banding
  * derive_leadership structured CSV roster parse + tenure
No DB required — the SQL-backed cohort/synthesis paths are exercised by the
live-PG suite; these pin the parsing/normalization primitives.
"""
from __future__ import annotations

from app.scripts.derive_issues import _META_TITLE_RE, _norm_sev, _sev_for
from app.scripts.derive_leadership import _leaders_from_csv, _tenure_months
from app.services.parsers.package_csvs import parse_issue_register_csv


# ── issue-register alias-aware parse ───────────────────────────────────
def test_issue_register_bok_iss_id_finding_headers() -> None:
    """BOK ships ISS_ID + Finding (not Issue_ID/Description) — must parse."""
    csv = (
        "ISS_ID,Check_ID,Severity,Category,Finding,Fix_Instruction,Source\n"
        "ISS-001,PV-01,MEDIUM,Proof,Proof completeness 54.3% (target >=95%),"
        "Add E-ID citations,AUTOMATED\n"
    )
    rows = parse_issue_register_csv(csv)
    assert len(rows) == 1
    assert rows[0].issue_id == "ISS-001"
    assert "Proof completeness" in rows[0].description
    assert rows[0].severity == "MEDIUM"


def test_issue_register_chemung_description_header() -> None:
    """Chemung CamelCase register uses `description` — must title from it."""
    csv = (
        "issue_id,pass,severity,category,check_id,description,fix_instruction,"
        "auto_fixable,status\n"
        "GOV-001,PASS_1,HIGH,SCORE,SI-07,1 rationales lack evidence citations,"
        "Add E-NNN citations,false,OPEN\n"
    )
    rows = parse_issue_register_csv(csv)
    assert len(rows) == 1
    assert rows[0].issue_id == "GOV-001"
    assert "lack evidence" in rows[0].description


# ── derive_issues severity normalization ───────────────────────────────
def test_norm_sev_maps_freetext_to_canonical_lowercase() -> None:
    assert _norm_sev("MATERIAL AT THE TIME") == "high"   # 19-char overflow case
    assert _norm_sev("Critical") == "critical"
    assert _norm_sev("moderate") == "medium"
    assert _norm_sev("Minor issue") == "low"
    assert _norm_sev("") == "medium"
    assert _norm_sev(None) == "medium"


def test_sev_for_score_bands() -> None:
    assert _sev_for(1.4) == "high"
    assert _sev_for(2.0) == "medium"
    assert _sev_for(2.74) == "medium"
    assert _sev_for(3.5) == "low"


# ── derive_issues meta-title reclassification (2026-07-06 deploy review) ──
# The 12 governance/QA rows that leaked onto the AE context register as
# kind='client'; all must match _META_TITLE_RE (→ reclassified to
# assessment_qa), while real client issues must NOT.
def test_meta_title_re_flags_governance_qa_rows() -> None:
    meta = [
        "gov_auditor.py v2.0 computes unweighted pillar average vs manifest 1.9690",
        "Evidence index contains 50 unique items; manifest reports 281 total refs",
        "run_manifest with matching run_id",
        "Assessment report initially existed only in .docx format; Excel export rec",
        "'Calculation_Chain sheet in workbook' absent — v5.5↔v2.4 schema drift",
        "Evidence count mismatch: manifest=0, registry=135",
        "Columns R/S/T absent from workbook (schema drift)",
        "evidence_index stored as JSON not CSV (v5.5/v2.4 schema drift)",
        "Workbook missing v2.4 schema tabs: {'Critic_Log'} (schema drift)",
        "Column S (Proof_Claims) absent from workbook — v5.5/v2.4 schema drift",
        "Column T (Proof_Links) absent from workbook — v5.5/v2.4 schema drift",
        "Calculation_Chain worksheet absent from workbook (v5.5/v2.4 schema drift)",
    ]
    assert all(_META_TITLE_RE.search(t) for t in meta)


def test_meta_title_re_spares_real_client_issues() -> None:
    legit = [
        "nCino LOS, Salesforce CRM, and wealth data reside in disparate silos",
        "Salesforce Financial Services Cloud absent",
        "Financial spreading for commercial credit analysis is fragmented",
        "No enterprise integration platform; 200+ tools connected point-to-point",
    ]
    assert not any(_META_TITLE_RE.search(t) for t in legit)


# ── derive_leadership structured CSV roster ────────────────────────────
def test_leaders_from_csv_full_name_title(tmp_path) -> None:
    p = tmp_path / "A2_Leadership_Register.csv"
    p.write_text(
        "EXEC_ID,Title,Full Name,Appointment Date,Credentials,Key Digital Signal\n"
        "EX-001,President & CEO,Myrna Wiebe,2025-09-02,MBA,Drove core conversion\n"
        "EX-002,SVP Technology,,2024-01-15,BSc,\n"   # no name → skipped
        "EX-003,CIO,Jane A. Doe,2023-06-01,,Cloud migration lead\n",
        encoding="utf-8",
    )
    rows = _leaders_from_csv(str(p))
    names = [r["name"] for r in rows]
    assert "Myrna Wiebe" in names and "Jane A. Doe" in names
    assert len(rows) == 2  # the title-only row is dropped
    myrna = next(r for r in rows if r["name"] == "Myrna Wiebe")
    assert myrna["title"] == "President & CEO"
    assert myrna["background"] and "core conversion" in myrna["background"]


def test_tenure_months_from_appointment_date() -> None:
    assert _tenure_months(None) is None
    assert _tenure_months("not-a-date") is None
    m = _tenure_months("2020-01-01")
    assert isinstance(m, int) and m >= 60  # >= 5 years by 2026


# ── pipeline-QA quarantine (2026-07-06 production fix) ─────────────────
# The IBKR governance register is the DMA bot auditing ITS OWN artifacts
# (rows keyed on file names); the Context page rendered those file names
# as the client's issues. `is_pipeline_artifact_issue` must classify the
# real register rows as pipeline-QA and keep genuine client issues.

_IBKR_REGISTER = (
    "tests/fixtures/dma_packages_batches/batch_15/"
    "Interactive Brokers - DMA/07_governance/IBKR_GOV_Issue_Register.csv"
)


def test_real_ibkr_register_rows_all_classify_pipeline() -> None:
    import pathlib

    import pytest

    from app.scripts.derive_issues import is_pipeline_artifact_issue

    p = pathlib.Path(__file__).resolve().parents[1] / _IBKR_REGISTER
    if not p.exists():
        pytest.skip("IBKR fixture not present")
    rows = parse_issue_register_csv(p.read_text(encoding="utf-8"))
    assert len(rows) >= 4
    for r in rows:
        assert is_pipeline_artifact_issue(
            description=r.description, category=r.type,
        ), f"{r.issue_id} not classified pipeline: {r.description[:80]}"


def test_pipeline_classifier_shapes() -> None:
    from app.scripts.derive_issues import is_pipeline_artifact_issue

    # file-name-led title (the production symptom)
    assert is_pipeline_artifact_issue(
        title="caps_applied_log.csv absent as standalone CSV file.")
    # artifact-file affected id
    assert is_pipeline_artifact_issue(affected_id="contradiction_log.csv")
    # pipeline category codes
    assert is_pipeline_artifact_issue(
        title="anything", category="INPUT_VALIDATION")
    assert is_pipeline_artifact_issue(
        title="anything", category="ARTIFACT_PROVENANCE")
    # E-ID bookkeeping prose
    assert is_pipeline_artifact_issue(description=(
        "Evidence ID E-003 is cited in subcap rationales but is absent "
        "from evidence_index.json."))


def test_pipeline_classifier_keeps_client_issues() -> None:
    from app.scripts.derive_issues import is_pipeline_artifact_issue

    # genuine client issues with a maturity impact must NOT classify
    assert not is_pipeline_artifact_issue(
        title="FINRA AWC: failure to report 300+ written complaints",
        description="Manual complaint intake lacks structured case "
                    "management; certification due within 180 days.")
    assert not is_pipeline_artifact_issue(
        title="No marketing automation platform for 4.4M accounts",
        description="Every new account arrives with no onboarding journey.")
    assert not is_pipeline_artifact_issue(
        title="Capability gap: Unified Client Profile",
        description='Maturity 2.1/5 — 0.9 pts below the peer median. '
                    'Observed in the research evidence [E-032]: "The firm '
                    'has no CDP; profiles are stitched manually."')


def test_mined_rows_filter_drops_pipeline_keeps_client(tmp_path) -> None:
    from app.scripts.derive_issues import _mine_issue_rows

    gov = tmp_path / "07_governance"
    gov.mkdir()
    (gov / "issue_register.csv").write_text(
        "issue_id,severity,category,check_id,affected_id,description\n"
        "ISS-001,HIGH,INPUT_VALIDATION,IV-05,caps_applied_log.csv,"
        "caps_applied_log.csv absent as standalone CSV file\n"
        "ISS-002,HIGH,COMPLIANCE,CP-01,complaints,"
        "Complaint backlog exceeds regulatory SLA in two states\n",
        encoding="utf-8",
    )
    rows = _mine_issue_rows(str(tmp_path))
    assert [r.issue_id for r in rows] == ["ISS-002"]


# ── enforcement-detail composition (2026-07-06 production fix) ──────────
# The D5 "Regulatory standing" card drills an OPEN regulatory issue into
# IssueDetail; the audit found bare titles with rationale==title and no
# evidence anchor. `compose_enforcement_detail` must append the entity's
# OWN enforcement excerpt VERBATIM with its E-ID and inherit subcap links.


class _Ev:
    def __init__(self, e_id, excerpt, subs=None):
        self.e_id = e_id
        self.excerpt = excerpt
        self.linked_subcap_ids = subs or []


def test_enforcement_detail_appends_verbatim_quote_and_subcaps() -> None:
    from app.scripts.derive_issues import compose_enforcement_detail

    excerpt = ("FINRA AWC 2024: the firm failed to report 300+ written "
               "customer complaints; a remediation certification is due "
               "within 180 days.")
    got = compose_enforcement_detail(
        title="FINRA AWC: complaint-reporting failure",
        rationale="FINRA AWC: complaint-reporting failure",  # dup of title
        linked_subcap_ids=[],
        evidence=[
            _Ev("E-002", "Generic paragraph about regulators and markets "
                         "with enforcement mentioned once in passing only."),
            _Ev("E-051", excerpt, subs=["P1C2.1.1", "P3C1.2.2"]),
        ],
    )
    assert got is not None
    rationale, subs = got
    # verbatim excerpt, quoted, with its E-ID; the duplicated title is
    # replaced by real descriptive detail.
    assert '[E-051]' in rationale
    assert excerpt in rationale  # fits budget → fully verbatim, no drift
    assert not rationale.startswith("FINRA AWC: complaint-reporting failure F")
    assert subs == ["P1C2.1.1", "P3C1.2.2"]


def test_enforcement_detail_skips_non_regulatory_and_already_cited() -> None:
    from app.scripts.derive_issues import compose_enforcement_detail

    ev = [_Ev("E-051", "Consent order penalty of $9M for BSA failures "
                       "entered against the bank in 2024.")]
    # non-regulatory issue → None
    assert compose_enforcement_detail(
        title="Slow loan onboarding", rationale="Manual steps",
        linked_subcap_ids=[], evidence=ev) is None
    # already evidence-anchored → idempotent None
    assert compose_enforcement_detail(
        title="BSA consent order", rationale='Cited [E-051]: "…"',
        linked_subcap_ids=[], evidence=ev) is None


def test_enforcement_detail_requires_same_event_grounding() -> None:
    from app.scripts.derive_issues import compose_enforcement_detail

    # An enforcement excerpt about an unrelated action (no shared content
    # tokens) must not be attached — no generic regulatory padding.
    assert compose_enforcement_detail(
        title="AML program remediation underway",
        rationale=None, linked_subcap_ids=[],
        evidence=[_Ev("E-009", "The state insurance regulator issued a "
                               "cease and desist over annuity sales "
                               "practices at a subsidiary broker.")],
    ) is None


def test_enforcement_detail_keeps_existing_rationale_and_subcaps() -> None:
    from app.scripts.derive_issues import compose_enforcement_detail

    got = compose_enforcement_detail(
        title="CFPB consent order",
        rationale="Remediation program is 40% complete per the register.",
        linked_subcap_ids=["P1C1.1.1"],
        evidence=[_Ev("E-014", "CFPB consent order (2023) required $12M in "
                               "customer restitution and new complaint "
                               "handling controls.", subs=["P9C9.9.9"])],
    )
    assert got is not None
    rationale, subs = got
    assert rationale.startswith("Remediation program is 40% complete")
    assert '[E-014]' in rationale
    assert subs == ["P1C1.1.1"]  # existing links never overwritten


def test_pipeline_classifier_ewb_gov_register_shapes() -> None:
    """EWB 07_governance register (live 2026-07-06): report-audit metric
    rows leaked through the IBKR-shaped patterns — every one is the bot
    auditing its own report, never a client issue."""
    from app.scripts.derive_issues import is_pipeline_artifact_issue

    for title in (
        "Range-style references: 1 found",
        "Citations: total=31 (≥30: True), exec=3 (≥5: False)",
        "URL validity: 237/642 (37%) missing URLs — expected in PUBLIC "
        "mode with ceiling estimates",
        "Source attribution: 237/642 (37%) have NO_EVIDENCE — expected "
        "for ceiling estimate subcaps",
        "Critic log: No formal critic worksheet generated (Phase 4.5 was "
        "implicit in scoring loop).",
        "Report citations: 31 unique E-IDs (target ≥50, minimum ≥30)",
        "Peer integration: 0 total peer refs, 5 in exec summary",
        "Anti-generic: forbidden=0, generic_exec=38% (8/21 sentences)",
        "Proof completeness 54.3% (target >=95%)",
    ):
        assert is_pipeline_artifact_issue(title=title), title
    # near-miss client issues must survive the new lead patterns
    for title in (
        "Citation backlog at the call center exceeds SLA",
        "2015 BSA/AML enforcement — TERMINATED 2018",
        "10-K technological disruption risk: larger competitors may "
        "outpace in innovation",
        "Glassdoor: manual work and low digitalization",
    ):
        assert not is_pipeline_artifact_issue(title=title), title


# ── synthesized-gap composition (2026-07-06 live-run fixes) ─────────────


def test_clean_subcap_rationale_strips_rubric_and_scratch() -> None:
    from app.scripts.derive_issues import clean_subcap_rationale

    raw = ("No CRM/MAP confirmed. 4.4M accounts without digital marketing "
           "automation. Self-directed model but greenfield gap confirmed "
           "via proxy. [E-020,E-042,E-052] Evidence: E-042, E-023 "
           "Q: Does the organization have a formal digital marketing "
           "strategy with defined objectives, ta Final: M1.4 from raw "
           "M1.4, ceil level 5.0")
    out = clean_subcap_rationale(raw)
    assert out.startswith("No CRM/MAP confirmed.")
    assert "[E-020,E-042,E-052]" in out       # analyst citation preserved
    assert "Q:" not in out and "Final:" not in out and "Evidence:" not in out

    piped = ("Change governance relies on Steering Committee. | Evidence "
             "ceiling: 5.0 | Diagnostic: Does the organization have a "
             "digital champions program with defined selection criteria an")
    out2 = clean_subcap_rationale(piped)
    assert out2 == "Change governance relies on Steering Committee."


def test_gap_display_name_prefers_real_name_over_stub() -> None:
    from app.scripts.derive_issues import gap_display_name

    assert gap_display_name("Champions Program", "whatever", "P1C4.3.1") \
        == "Champions Program"
    # stub/jargon catalogue names fall back to the rationale's lead clause
    assert gap_display_name(
        "Subcap P2C1.1.1",
        "No CRM/MAP confirmed. 4.4M accounts without automation.",
        "P2C1.1.1",
    ) == "No CRM/MAP confirmed"
    assert gap_display_name(None, None, "P2C1.1.1") == "P2C1.1.1"
