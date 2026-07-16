"""Batch 11 — pin the operator-runbook contract.

Per the integrated batched plan §11 ("Continuous regression discipline,
post-prod-gate steady state"), the operator runbook
``docs/qa/qa_runbook.md`` is the canonical operator-facing how-to.
This contract test ensures:

  1. The runbook file exists and is non-empty.
  2. It documents the 4 production-grade QA harnesses (render,
     adversarial, language, self-heal+learning).
  3. It documents the corpus-restore procedure (which test_seed_ci.py
     destroys; operators have lost ~20 minutes to manual restoration).
  4. It cross-references the gate evidence docs so operators can
     drill from "should we ship?" to "what's pinned by which test".
  5. The QA-CONTRACT § "Recurring QA discipline" exists with the
     per-PR + quarterly + per-fixture cadences.
  6. The cross-link from `qa_executive_summary.md` to the runbook
     exists.

If a future PR removes the runbook or breaks the cross-links, this
test FAILs immediately. Defense against the "doc bit-rot" risk that
the v2 plan flagged.
"""
from __future__ import annotations

from pathlib import Path

QA_DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "qa"
RUNBOOK = QA_DOCS_DIR / "qa_runbook.md"
EXEC_SUMMARY = QA_DOCS_DIR / "qa_executive_summary.md"
GATE_PROD = QA_DOCS_DIR / "qa_gates" / "gate_prod_evidence.md"
QA_CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "QA-CONTRACT.md"


def test_runbook_exists_and_non_empty() -> None:
    assert RUNBOOK.is_file(), f"qa_runbook.md missing at {RUNBOOK}"
    content = RUNBOOK.read_text()
    # >=200 lines is the floor; today's runbook is ~470. A drop below
    # 200 = someone truncated the file.
    assert len(content.splitlines()) >= 200, (
        f"qa_runbook.md is {len(content.splitlines())} lines; "
        f"expected ≥ 200 (operator-grade detail required)"
    )


def test_runbook_documents_4_harnesses() -> None:
    """Every production-grade harness must have an operator-runnable
    command in the runbook."""
    content = RUNBOOK.read_text()
    expected_harnesses = (
        "qa_render_validation",
        "qa_adversarial_resilience",
        "qa_rendered_language_audit",
        "qa_self_healing_learning_audit",
    )
    missing = [h for h in expected_harnesses if h not in content]
    assert not missing, (
        f"qa_runbook.md missing harness reference(s): {missing}. "
        f"Every production-grade harness from the qa-gates cloudbuild "
        f"stage needs an operator-runnable command."
    )


def test_runbook_documents_corpus_restore() -> None:
    """Operators have lost ~20min to manual restoration when
    test_seed_ci.py runs and shrinks the DB to 6 fixtures. The runbook
    must document the restore procedure with all 4 steps (drop schema /
    upgrade head / historical_backfill / verify)."""
    content = RUNBOOK.read_text()
    required_steps = (
        "DROP SCHEMA public CASCADE",
        "alembic upgrade head",
        "historical_backfill",
        "--force",
        "104 entities",
    )
    missing = [s for s in required_steps if s not in content]
    assert not missing, (
        f"qa_runbook.md missing corpus-restore step(s): {missing}. "
        f"Operators need the full restore procedure inline."
    )


def test_runbook_cross_references_gate_evidence() -> None:
    """The runbook must point operators to the cascade-gate evidence
    docs so they can drill from "should we ship?" to "what's pinned
    by which test"."""
    content = RUNBOOK.read_text()
    required_refs = (
        "qa_executive_summary.md",
        "qa_full_report.md",
        "qa_patch_backlog.md",
        "qa_gates/gate_prod_evidence.md",
        "docs/QA-CONTRACT.md",
    )
    missing = [r for r in required_refs if r not in content]
    assert not missing, (
        f"qa_runbook.md missing cross-reference(s): {missing}"
    )


def test_runbook_documents_j_journeys() -> None:
    """The 6 J-journeys (J1-J6) are the user-facing acceptance bar.
    The runbook must document every journey so on-call can walk
    through them."""
    content = RUNBOOK.read_text()
    for j in ("J1", "J2", "J3", "J4", "J5", "J6"):
        assert f"### {j} —" in content, f"qa_runbook.md missing {j} journey"


def test_qa_contract_has_recurring_discipline_section() -> None:
    """The Batch 11 mandate: QA-CONTRACT.md must document the
    recurring cadence (per-PR + quarterly + per-fixture)."""
    content = QA_CONTRACT.read_text()
    assert "## Recurring QA discipline" in content, (
        "QA-CONTRACT.md missing § Recurring QA discipline (Batch 11 mandate)"
    )
    # Three cadences MUST appear inline so the operator doesn't
    # navigate elsewhere to find them.
    for cadence in ("### Per PR", "### Quarterly", "### Per fixture addition"):
        assert cadence in content, (
            f"QA-CONTRACT.md § Recurring QA discipline missing cadence "
            f"heading {cadence!r}"
        )


def test_executive_summary_cross_links_runbook() -> None:
    """Operator reading the executive summary must find the runbook
    pointer without navigating to a TOC."""
    content = EXEC_SUMMARY.read_text()
    assert "qa_runbook.md" in content, (
        "qa_executive_summary.md must cross-link qa_runbook.md so "
        "operators can drill from 'should we ship?' to the day-to-day "
        "playbook"
    )


def test_gate_prod_references_runbook_chain() -> None:
    """The Production-Ready Gate evidence must cite the runbook +
    the executive summary + the patch backlog as the audit-trail
    package required by the plan."""
    content = GATE_PROD.read_text()
    # The full v2 plan terminal acceptance: "a production-readiness
    # reviewer reads qa_executive_summary.md in 15 minutes". The
    # gate_prod_evidence.md must mention this acceptance chain.
    assert "qa_executive_summary.md" in content, (
        "gate_prod_evidence.md must reference qa_executive_summary.md "
        "(the 15-min operator verdict)"
    )
    assert "qa_patch_backlog.md" in content, (
        "gate_prod_evidence.md must reference qa_patch_backlog.md "
        "(the 10-field template P0..P3 issue list)"
    )


def test_runbook_documents_env_vars() -> None:
    """Operators in a fresh shell need to set DATABASE_URL +
    DATABASE_URL_SYNC + SEED_CI_PG_URL. The runbook must list them
    inline so operators don't have to dig through tests/conftest.py."""
    content = RUNBOOK.read_text()
    for env in ("DATABASE_URL", "DATABASE_URL_SYNC", "SEED_CI_PG_URL"):
        assert env in content, f"qa_runbook.md missing env var {env}"


def test_runbook_lists_21_pinned_properties() -> None:
    """The Production-Ready Gate certifies 21 defense-in-depth
    properties. The runbook's appendix lists them so the operator
    can verify each periodically."""
    content = RUNBOOK.read_text()
    # 21 numbered entries in the cumulative list.
    properties_section = content.split("Defense-in-depth properties pinned")
    assert len(properties_section) == 2, (
        "qa_runbook.md missing § Defense-in-depth properties pinned section"
    )
    body = properties_section[1]
    # Count the numbered entries; expect at least 18 (the cumulative
    # count grows over batches; the floor is the Batch 9 baseline).
    import re
    numbered = re.findall(r"^\d+\.\s+", body, re.M)
    assert len(numbered) >= 18, (
        f"qa_runbook.md § Defense-in-depth lists only {len(numbered)} "
        f"properties; expected ≥ 18 (cumulative Batch 1-9 floor)"
    )
