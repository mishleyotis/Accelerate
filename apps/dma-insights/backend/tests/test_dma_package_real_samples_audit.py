"""2026-05-28 final audit: regression tests against the 5 REAL DMA samples.

These tests run the `parse_package` orchestrator against the actual
sanitized sample packages the user uploaded (Alma / Calprivate / Nicola /
Odlum / WSFS). Each test pins a specific count or contract the audit
identified — they FAIL if the parser regresses.

Sample fixtures live at
`backend/tests/fixtures/dma_packages_real_samples/<entity>__DMA/<inner>/`
with the inner folder name matching the n8n pipeline's actual emission.

The acceptance matrix from the audit (verified against the real samples
after all P0/P1 patches landed):

  | Sample     | sub | ev  | rec | peer | iss | tch | sect | firm |
  |------------|-----|-----|-----|------|-----|-----|------|------|
  | Alma       | 698 | 105 | 7   | 5    | 9   | 33  | 72   | Y    |
  | Calprivate | 698 | 125 | 0   | 5    | 3   | 25  | 47   | Y    |
  | Nicola     | 709 | 149 | 0   | 5    | 3   | 32  | 73   | Y    |
  | Odlum      | 709 | 127 | 6   | 4    | 5   | 12  | 54   | Y    |
  | WSFS       | 708 | 106 | 0   | 4    | 7   | 25  | 56   | Y    |

The recommendation 0 counts are NOT defects — the sample packages
genuinely don't ship recommendation JSON files for those entities.

Defects pinned (each test names the fix):
  P0-A  parse_run_manifest entity_name/institution alias (Calprivate/Odlum)
  P0-B  _synthesize_run_manifest_from_handoff (Nicola)
  P0-C  issue register variant discovery (GOV_*, L2_*, A7_*, A8_*)
  P0-D  tech stack variant discovery (Technographic*, *TechStack*)
  P0-E  tech stack sheet selection (Confirmed_Tech_Stack priority)
  P0-F  recommendations variant discovery (07_governance/recommendations_register)
  P0-G  peer benchmarks variant shape (peer_set str list + peer_overall_scores)
  P0-H  firmographics fallback to client profile DOCX (Alma/Odlum)
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _find_app_root(start: Path) -> Path:
    for c in [start, *start.parents]:
        if (c / "backend").is_dir() and (c / "infra").is_dir():
            return c
    raise RuntimeError(f"app root not found from {start}")


APP_ROOT = _find_app_root(Path(__file__).resolve())
SAMPLES_DIR = (
    APP_ROOT / "backend" / "tests" / "fixtures" / "dma_packages_real_samples"
)


def _sample_path(entity: str) -> Path:
    """Return the absolute path to the parsable inner folder of a sample."""
    outer = SAMPLES_DIR / f"{entity}__DMA"
    if not outer.exists():
        pytest.skip(f"real sample fixture not present: {outer}")
    return outer


@pytest.fixture(scope="module")
def parse_package_fn():
    from app.services.parsers.dma_package import parse_package
    return parse_package


# ── Alma reference baseline (canonical layout, no synthesis needed) ───


def test_alma_real_sample_baseline_counts(parse_package_fn) -> None:
    """Alma is the canonical reference layout. Catching a regression
    here means a P0 in the orchestrator, not a variant issue."""
    pkg = parse_package_fn(_sample_path("Alma_Bank"))
    rm = pkg.run_manifest
    assert rm.institution_name == "Alma Bank"
    assert rm.run_id == "DMA-ASM-ALMA-20260519-0001"
    assert len(pkg.subcap_scores) == 698
    assert len(pkg.evidence) == 105
    assert len(pkg.recommendations) == 7
    assert len(pkg.peers) == 5
    # 2026-07-06 issue-register rework: Alma's 07_governance CSV is the
    # bot's own QA checklist (check_id/fix_instruction headers) — its 9
    # rows are kept but classified assessment_qa (Health-page material,
    # namespaced QA-* ids). The CLIENT rows come from
    # layer1_issue_register.json: 8 REAL issues (2015 NY DFS Consent
    # Order, 2019 FDIC CMP, CIO vacancy…) that the old first-non-empty
    # pick shadowed entirely.
    qa_rows = [r for r in pkg.issue_register if r.kind == "assessment_qa"]
    client_rows = [r for r in pkg.issue_register if r.kind == "client"]
    assert len(qa_rows) == 9
    assert len(client_rows) == 8
    assert all(r.issue_id.startswith("QA-") for r in qa_rows)
    assert any("Consent Order" in r.description for r in client_rows)
    assert len(pkg.tech_stack) == 30  # Zennify taxonomy classify drops 4 noise/dup
    #                                    rows; the 30 are all real platforms (AWS,
    #                                    CyberArk PAM, FIS Horizon, MuleSoft, Splunk…)
    assert pkg.firmographics is not None  # via client_profile DOCX fallback
    assert len(pkg.firmographics.leadership) >= 5


# ── Calprivate: entity_name alias + variant issue register + tech stack ──


def test_calprivate_real_sample_institution_name_via_entity_name_alias(parse_package_fn) -> None:
    """P0-A: Calprivate's run_manifest.json uses `entity_name` (NOT
    `institution_name`). Prior parser left institution_name blank;
    after fix, the entity_name alias is honoured.
    """
    pkg = parse_package_fn(_sample_path("Calprivate_Bank"))
    assert pkg.run_manifest.institution_name == "CalPrivate Bank"
    assert pkg.run_manifest.run_id.startswith("DMA-RES-CPB")


def test_calprivate_real_sample_minimum_counts(parse_package_fn) -> None:
    """Audit acceptance: >=690 subcaps, >=100 evidence, issues + tech +
    firmographics present.
    """
    pkg = parse_package_fn(_sample_path("Calprivate_Bank"))
    assert len(pkg.subcap_scores) >= 690, len(pkg.subcap_scores)
    assert len(pkg.evidence) >= 100, len(pkg.evidence)
    assert len(pkg.issue_register) > 0, "P0-C: variant issue register not discovered"
    assert len(pkg.tech_stack) > 0, "P0-D/E: variant tech stack not discovered"
    assert pkg.firmographics is not None


def test_calprivate_real_sample_tech_stack_uses_technographic_variant(parse_package_fn) -> None:
    """P0-D + P0-E: Calprivate ships
    `CalPrivate_Technographic_Stack_Explorium.xlsx` (NOT the canonical
    `*_Explorium_Tech_Stack.xlsx`), and the workbook's tech data lives
    in the `Confirmed_Tech_Stack` sheet with a combined
    `Vendor / Product` column. Prior parser missed both variants.
    """
    pkg = parse_package_fn(_sample_path("Calprivate_Bank"))
    assert len(pkg.tech_stack) >= 20, len(pkg.tech_stack)
    # Vendor column was a combined "Vendor / Product" header — verify
    # we extracted real vendor strings, not blanks. (≥14 distinct after the
    # Zennify taxonomy collapses vendor aliases; 16 real vendors today.)
    vendors = {t.vendor for t in pkg.tech_stack if t.vendor}
    assert len(vendors) >= 14


# ── Nicola: synthesize run manifest from research handoff ──


def test_nicola_real_sample_synthesizes_run_manifest_from_handoff(parse_package_fn) -> None:
    """P0-B: Nicola has NO run_manifest.json anywhere. Prior parser
    raised `ValueError: no run manifest found`. After fix, the parser
    falls back to `_synthesize_run_manifest_from_handoff`, which reads
    `02_research_workbook/NicolaWealth_research_handoff.json`.
    """
    pkg = parse_package_fn(_sample_path("Nicola_Wealth"))
    rm = pkg.run_manifest
    assert rm is not None
    assert rm.institution_name == "Nicola Wealth Management Ltd."
    assert rm.run_id.startswith("DMA-RES-NICW")
    # Warning surfaces that synthesis happened.
    assert any(
        "synthesized run_manifest from handoff" in w for w in pkg.parser_warnings
    ), pkg.parser_warnings


def test_nicola_real_sample_minimum_counts(parse_package_fn) -> None:
    """Audit acceptance for Nicola."""
    pkg = parse_package_fn(_sample_path("Nicola_Wealth"))
    assert len(pkg.subcap_scores) >= 690, len(pkg.subcap_scores)
    assert len(pkg.evidence) >= 100, len(pkg.evidence)
    assert len(pkg.peers) > 0, "P0-G: variant peer benchmark shape not parsed"
    assert len(pkg.issue_register) > 0
    assert len(pkg.tech_stack) > 0


def test_nicola_real_sample_peers_via_peer_overall_scores_shape(parse_package_fn) -> None:
    """P0-G: Nicola's `06_peers/02_peer_benchmarks.json` has peer_set
    as a list of STRINGS (peer names) + `peer_overall_scores` as a
    dict. Prior parser only knew the dict-of-dicts shape.
    """
    pkg = parse_package_fn(_sample_path("Nicola_Wealth"))
    assert len(pkg.peers) >= 4
    # Peers have aggregated pillar scores from the per-category
    # benchmarks dict; at least the overall score should be populated.
    overall_with_score = [p for p in pkg.peers if "overall" in (p.scores or {})]
    assert len(overall_with_score) >= 1


# ── Odlum: institution alias + recommendations variant + tech stack ──


def test_odlum_real_sample_institution_via_institution_alias(parse_package_fn) -> None:
    """P0-A: Odlum's run_manifest.json uses `institution` (NOT
    `institution_name`). Prior parser left it blank.
    """
    pkg = parse_package_fn(_sample_path("Odlum_BROWN"))
    assert pkg.run_manifest.institution_name == "Odlum Brown Limited"


def test_odlum_real_sample_recommendations_via_register_variant(parse_package_fn) -> None:
    """P0-F: Odlum ships `07_governance/recommendations_register.json`
    instead of the canonical `08_appendices/recommendations_detail.json`.
    Prior parser missed it; recommendations rendered as 0 on D4.
    """
    pkg = parse_package_fn(_sample_path("Odlum_BROWN"))
    assert len(pkg.recommendations) >= 5


def test_odlum_real_sample_firmographics_via_client_profile_docx(parse_package_fn) -> None:
    """P0-H: Odlum has no research_handoff.json. The firmographics
    fallback parses `04_reports/OdlumBrown_ClientProfile_FINAL.docx`
    and extracts leadership. Without the fix, firm was None and the
    D5 Context panel rendered as the empty state.
    """
    pkg = parse_package_fn(_sample_path("Odlum_BROWN"))
    assert pkg.firmographics is not None
    assert pkg.firmographics.legal_name == "Odlum Brown Limited"
    assert len(pkg.firmographics.leadership) >= 5


def test_odlum_real_sample_minimum_counts(parse_package_fn) -> None:
    pkg = parse_package_fn(_sample_path("Odlum_BROWN"))
    assert len(pkg.subcap_scores) >= 690, len(pkg.subcap_scores)
    assert len(pkg.evidence) >= 100, len(pkg.evidence)
    assert len(pkg.issue_register) > 0
    assert len(pkg.tech_stack) > 0


def test_odlum_real_sample_tech_stack_picks_confirmed_sheet_not_explorium_match(
    parse_package_fn,
) -> None:
    """P0-E: Odlum's tech stack xlsx has FOUR sheets — the FIRST sheet
    `Explorium_Match` is NOT a tech list (it's a match-quality table
    with cols Field/Value/Status/Notes). Sheet `Confirmed_Tech_Stack`
    has the actual rows. Prior parser read sheet [0] and got nothing.
    """
    pkg = parse_package_fn(_sample_path("Odlum_BROWN"))
    assert len(pkg.tech_stack) >= 10, len(pkg.tech_stack)
    # Spot-check that we extracted real vendor names, not the
    # Explorium_Match labels like "Company Name" / "Confidence_Score".
    vendors = {t.vendor for t in pkg.tech_stack if t.vendor}
    forbidden = {"Company Name", "Confidence_Score", "MATCHED"}
    assert not (vendors & forbidden), forbidden & vendors


# ── WSFS reference baseline (canonical layout) ───


def test_wsfs_real_sample_baseline_counts(parse_package_fn) -> None:
    """WSFS canonical layout — full coverage check."""
    pkg = parse_package_fn(_sample_path("WSFS_Bank"))
    rm = pkg.run_manifest
    assert rm.institution_name.startswith("WSFS")
    assert len(pkg.subcap_scores) >= 700
    assert len(pkg.evidence) >= 100
    assert len(pkg.issue_register) >= 5
    # Zennify taxonomy classify keeps only real platforms (drops languages/OS/
    # noise) — 15 today (nCino, Jack Henry, Salesforce, Workday, Splunk…).
    assert len(pkg.tech_stack) >= 12
    assert pkg.firmographics is not None
    # WSFS report sections — 4 P*_deep_dive + intro + recs + risks etc.
    assert len(pkg.report_sections) >= 30


# ── Cross-sample contract: every parsed manifest has a non-blank institution ──


def test_every_real_sample_has_non_blank_institution_name(parse_package_fn) -> None:
    """Audit P1: the audit explicitly required institution_name to NOT
    be blank for Calprivate / Nicola / Odlum / WSFS. This test pins
    that contract across ALL five real samples; one regression in
    one sample breaks the suite.
    """
    blanks: list[str] = []
    for entity in (
        "Alma_Bank", "Calprivate_Bank", "Nicola_Wealth", "Odlum_BROWN", "WSFS_Bank",
    ):
        pkg = parse_package_fn(_sample_path(entity))
        if not (pkg.run_manifest.institution_name or "").strip():
            blanks.append(entity)
    assert not blanks, f"blank institution_name on real samples: {blanks}"


def test_every_real_sample_meets_minimum_subcap_count(parse_package_fn) -> None:
    """Audit acceptance: every sample must produce ≥690 subcap scores.
    Lower means either the sample itself lacks the data (which the
    audit denies for the 4 samples it pins) OR the parser variant
    pattern broke. Catches xlsx fallback regressions.
    """
    too_few: dict[str, int] = {}
    for entity in (
        "Alma_Bank", "Calprivate_Bank", "Nicola_Wealth", "Odlum_BROWN", "WSFS_Bank",
    ):
        pkg = parse_package_fn(_sample_path(entity))
        n = len(pkg.subcap_scores)
        if n < 690:
            too_few[entity] = n
    assert not too_few, f"subcap counts below 690: {too_few}"


def test_every_real_sample_has_firmographics_or_warns(parse_package_fn) -> None:
    """Audit P1: every sample must produce firmographics (either via
    research_handoff JSON OR client_profile DOCX fallback). Lack of
    firmographics on a sample with a client_profile DOCX is a fix.
    """
    missing: list[str] = []
    for entity in (
        "Alma_Bank", "Calprivate_Bank", "Nicola_Wealth", "Odlum_BROWN", "WSFS_Bank",
    ):
        pkg = parse_package_fn(_sample_path(entity))
        if pkg.firmographics is None:
            missing.append(entity)
    assert not missing, f"firmographics missing on real samples: {missing}"
