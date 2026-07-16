"""QA-verdict discovery regression tests.

Orphaned-verdict bug (audited 2026-06-15): the L2 discovery in
`parsers/dma_package.py` iterated ONLY `07_governance/` and matched the
`qa_verdict` token, so OZK-shaped packages — which ship the verdict
exclusively in `08_qa/qa_verdict.json` and/or
`07_governance/governance_verdict.json` (no "qa_verdict" token) — resolved
`qa_verdict=None` and silently dropped D6 Health's QA gate.

These tests build minimal synthetic packages in tmp dirs and assert the
three discovery outcomes:
  1. verdict ONLY in `08_qa/`                  → resolves
  2. verdict ONLY in `07_governance/governance_verdict.json` → resolves
  3. neither                                   → qa_verdict is None (no crash)

Plus an order-stability check (07_governance wins when both dirs ship a
verdict) and a guard that a `*.md` summary in `08_qa/` is never picked up.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.parsers.dma_package import _CANONICAL_SUBFOLDERS, parse_package

# A verdict JSON in the shape `parse_qa_verdict` accepts (WSFS-style keys).
_PASS_VERDICT = {
    "overall_verdict": "PASS_WITH_NOTES",
    "recommended_action": "DELIVER",
    "verdict_note": "all checks green",
    "pass1_results": {"organic_critical": 0, "organic_high": 1},
}
_PASS_NOTES_FROM_GOV = {
    "overall_verdict": "CONDITIONAL_PASS",
    "ag_fails": ["RC-15: Insufficient peer references (3)"],
}


def _make_package(tmp_path: Path, name: str) -> Path:
    """Minimal canonical-layout package root carrying enough DMA signal
    that `_find_root` keeps `root` as the effective root (a MANIFEST plus
    a `07_governance/` subfolder)."""
    root = tmp_path / name
    (root / "07_governance").mkdir(parents=True)
    # A MANIFEST.json gives `_find_root` an unambiguous root anchor.
    (root / "MANIFEST.json").write_text(
        json.dumps({"run_id": "DMA-ASM-SYNTH-20260615-0001"}),
        encoding="utf-8",
    )
    return root


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ── 1. verdict ONLY in 08_qa/ ───────────────────────────────────────────

def test_qa_verdict_resolves_from_08_qa_only(tmp_path: Path) -> None:
    root = _make_package(tmp_path, "OnlyQaDir")
    _write_json(root / "08_qa" / "qa_verdict.json", _PASS_VERDICT)

    pkg = parse_package(root)

    assert pkg.qa_verdict is not None, "08_qa/qa_verdict.json was orphaned"
    assert pkg.qa_verdict.verdict == "PASS_WITH_NOTES"
    assert pkg.qa_verdict.recommendation == "DELIVER"


# ── 2. verdict ONLY in 07_governance/governance_verdict.json ────────────

def test_qa_verdict_resolves_from_governance_verdict_json(tmp_path: Path) -> None:
    root = _make_package(tmp_path, "OnlyGovVerdict")
    _write_json(
        root / "07_governance" / "governance_verdict.json", _PASS_NOTES_FROM_GOV
    )

    pkg = parse_package(root)

    assert pkg.qa_verdict is not None, "governance_verdict.json was orphaned"
    assert pkg.qa_verdict.verdict == "CONDITIONAL_PASS"


# ── 3. neither → None, no crash ─────────────────────────────────────────

def test_qa_verdict_none_when_no_verdict_artifact(tmp_path: Path) -> None:
    root = _make_package(tmp_path, "NoVerdict")
    # A non-verdict JSON the broad sweep must NOT pick up.
    _write_json(
        root / "07_governance" / "governance_partial.json",
        {"overall_verdict": None, "ap_fails": ["AP-03: missing"]},
    )

    pkg = parse_package(root)

    assert pkg.qa_verdict is None


# ── 4. order-stability: 07_governance wins when both dirs ship one ──────

def test_qa_verdict_prefers_07_governance_over_08_qa(tmp_path: Path) -> None:
    root = _make_package(tmp_path, "BothDirs")
    _write_json(
        root / "07_governance" / "qa_verdict.json",
        {"overall_verdict": "PASS", "recommended_action": "FROM_GOV"},
    )
    _write_json(
        root / "08_qa" / "qa_verdict.json",
        {"overall_verdict": "FAIL", "recommended_action": "FROM_QA"},
    )

    pkg = parse_package(root)

    assert pkg.qa_verdict is not None
    # Deterministic precedence: the 07_governance canonical name is the
    # first explicit candidate, so it must win every time.
    assert pkg.qa_verdict.verdict == "PASS"
    assert pkg.qa_verdict.recommendation == "FROM_GOV"


# ── 5. a `.md` summary in 08_qa/ is never mistaken for a verdict ────────

def test_qa_verdict_ignores_markdown_summary(tmp_path: Path) -> None:
    root = _make_package(tmp_path, "MdSummary")
    qa_dir = root / "08_qa"
    qa_dir.mkdir(parents=True)
    (qa_dir / "PHASE8_EXECUTION_SUMMARY.md").write_text(
        "# QA Verdict\n\nverdict: PASS\n", encoding="utf-8"
    )

    pkg = parse_package(root)

    # No JSON verdict anywhere → None (the .md must not be parsed).
    assert pkg.qa_verdict is None


# ── 6. canonical-subfolder allow-list includes 08_qa ────────────────────

def test_08_qa_is_a_canonical_subfolder() -> None:
    assert "08_qa" in _CANONICAL_SUBFOLDERS
    # And we didn't drop the pre-existing appendices entry.
    assert "08_appendices" in _CANONICAL_SUBFOLDERS
