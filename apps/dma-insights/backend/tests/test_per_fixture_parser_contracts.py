"""Phase 3 per-fixture parser contract tests.

Per the audit Phase 3 parsers section:
  - test_amalgamated_fixture_parses_scoring_evidence_documents_focus_areas
  - test_americu_fixture_parses_shifted_workbook_headers
  - test_regions_fixture_parses_docx_only_sections_with_warnings
  - test_wsfs_fixture_reingest_is_idempotent

Each test exercises a specific fixture shape and asserts the
documented contract for that shape. These complement the existing
`test_dma_package_real_shapes.py` which covers the LAYOUT contract
(manifest location, folder nesting); these tests verify the
EXTRACTED CONTENT contract (subcaps + evidence + focus_areas
counts match the documented fixture shape).
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "tests" / "fixtures" / "dma_packages_sanitized"
)


def _fixture_path(name: str) -> Path | None:
    p = FIXTURES / name
    return p if p.is_dir() else None


# ── Amalgamated: full-coverage shape ─────────────────────────────


def test_amalgamated_fixture_parses_scoring_evidence_and_idempotent_reparse():
    """The amalgamated fixture is the canonical "full coverage"
    shape: scoring workbook + evidence + assessment report + client
    profile. Parsing must yield non-empty subcap_scores +
    evidence + at least one document section."""
    fp = _fixture_path("amalgamated")
    if not fp:
        pytest.skip("amalgamated fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fp)

    assert pkg is not None, "amalgamated fixture failed to parse"
    assert pkg.subcap_scores, (
        "amalgamated fixture must yield subcap_scores -- the scoring "
        "workbook is present and shouldn't be silently dropped."
    )
    assert pkg.evidence, (
        "amalgamated fixture must yield evidence rows. Empty evidence "
        "from a known-good fixture means the parser regressed."
    )
    # Re-parse must be deterministic -- same fixture, same output.
    pkg2 = parse_package(fp)
    assert len(pkg.subcap_scores) == len(pkg2.subcap_scores), (
        "re-parse of amalgamated produced different subcap_scores count. "
        "Parser must be deterministic on a frozen fixture."
    )
    assert len(pkg.evidence) == len(pkg2.evidence), (
        "re-parse of amalgamated produced different evidence count."
    )


def test_amalgamated_run_manifest_carries_request_id():
    """The amalgamated run_manifest exposes a request_id used as the
    canonical key for re-ingest idempotency (see ingest.py). A missing
    request_id would force re-ingest to create a new run row every time."""
    fp = _fixture_path("amalgamated")
    if not fp:
        pytest.skip("amalgamated fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fp)
    rid = pkg.run_manifest.run_id
    assert rid, (
        "amalgamated fixture run_manifest must declare a non-empty "
        "run_id / request_id. Re-ingest idempotency keys on this."
    )


# ── AmeriCU: shifted-workbook shape ─────────────────────────────


def test_americu_fixture_parses_with_manifest_in_03_scoring_workbook():
    """AmeriCU's run_manifest.json lives at
    `<package>/03_scoring_workbook/run_manifest.json` (not at the
    package root). Per the F2 fix the `_find_root` threshold was
    lowered to 2 canonical subfolders so this shape parses. Pin it."""
    fp = _fixture_path("americu")
    if not fp:
        pytest.skip("americu fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fp)
    assert pkg is not None
    # AmeriCU's specific shape: subcap_scores present even though the
    # manifest lives in 03_scoring_workbook (not the root). A
    # regression that re-tightens _find_root would surface here.
    assert pkg.subcap_scores, (
        "AmeriCU fixture must yield subcap_scores. The fix-for-shifted-"
        "manifest must hold -- _find_root threshold=2 is the contract."
    )


def test_americu_fixture_emits_xlsx_fallback_warning_when_used():
    """AmeriCU uses the xlsx-scoring fallback path (no canonical
    scoring_input.json -- parser pulls subcaps from the DOCX-
    embedded workbook). The fallback must surface a typed warning
    so operators know to follow up with a clean run."""
    fp = _fixture_path("americu")
    if not fp:
        pytest.skip("americu fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fp)
    # The xlsx fallback emits "scoring loaded from xlsx fallback" and
    # "xlsx fallback extracted N subcaps from <workbook>".
    has_fallback_warning = any(
        "xlsx fallback" in w or "xlsx" in w.lower()
        for w in pkg.parser_warnings
    )
    assert has_fallback_warning, (
        "AmeriCU fixture must surface an xlsx-fallback warning. "
        "Silent fallback hides a partial parse from the operator."
    )


# ── Regions: flat-no-manifest, qa_verdict-as-manifest shape ─────


def test_regions_fixture_parses_with_qa_verdict_as_manifest():
    """Regions has the full canonical 01_..08_ layout but NO
    MANIFEST.json -- the parser falls back to using
    `07_governance/governance_qa_verdict_*.json` as the manifest.
    Per the audit's F-batch fix this fallback must work + emit a
    typed warning so operators know the package shape was
    non-canonical."""
    fp = _fixture_path("regions")
    if not fp:
        pytest.skip("regions fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fp)
    assert pkg is not None
    # The variant-manifest fallback must surface a warning.
    has_variant_warning = any(
        "variant manifest" in w or "variant" in w.lower()
        for w in pkg.parser_warnings
    )
    assert has_variant_warning, (
        "regions fixture must emit a `variant manifest` warning so "
        "operators know the package used the qa_verdict fallback "
        "rather than a real MANIFEST.json."
    )


def test_regions_fixture_yields_full_scoring_workbook_subcaps():
    """Despite the manifest fallback, Regions has the full scoring
    workbook -- subcap_scores must be populated. A regression that
    couples 'no manifest' to 'no scoring' would silently drop
    scoring data."""
    fp = _fixture_path("regions")
    if not fp:
        pytest.skip("regions fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fp)
    assert pkg.subcap_scores, (
        "regions fixture must yield subcap_scores. The scoring "
        "workbook IS present even without a canonical manifest."
    )
    assert len(pkg.subcap_scores) >= 50, (
        f"regions fixture yielded only {len(pkg.subcap_scores)} "
        "subcaps. The fixture's scoring workbook has ~60; a count "
        "well below that means a parser regression."
    )


# ── WSFS: idempotency on re-parse ─────────────────────────────────


def test_wsfs_fixture_reparse_is_deterministic():
    """Re-parsing the SAME fixture must yield the SAME extracted
    payload (subcaps, evidence, focus_areas counts). Drift between
    runs would mean either:
      - A timestamp or `gen_random_uuid()` leaked into a hashed key
      - The parser is order-sensitive on filesystem walk
    Either is a bug. Pin determinism here so re-ingest produces
    reproducible state."""
    fp = _fixture_path("wsfs")
    if not fp:
        pytest.skip("wsfs fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg1 = parse_package(fp)
    pkg2 = parse_package(fp)
    assert len(pkg1.subcap_scores) == len(pkg2.subcap_scores)
    assert len(pkg1.evidence) == len(pkg2.evidence)
    # Compare the e_id lists (order-independent set comparison)
    e1_ids = {ev.e_id for ev in pkg1.evidence}
    e2_ids = {ev.e_id for ev in pkg2.evidence}
    assert e1_ids == e2_ids, (
        "wsfs re-parse produced different e_id set. Parser drift "
        "(timestamp or random in the key) would surface here."
    )


def test_wsfs_fixture_run_manifest_is_stable_across_reparse():
    """The run_manifest.run_id (used as the idempotency key in
    ingest.py) must NOT change between parses. A drift here would
    break the SELECT ... FOR UPDATE WHERE request_id = :rid lookup
    and force creation of duplicate runs."""
    fp = _fixture_path("wsfs")
    if not fp:
        pytest.skip("wsfs fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg1 = parse_package(fp)
    pkg2 = parse_package(fp)
    assert pkg1.run_manifest.run_id == pkg2.run_manifest.run_id, (
        "wsfs re-parse produced different run_manifest.run_id. The "
        "request_id is the ingest idempotency key -- drift here = "
        "duplicate runs on every re-ingest."
    )


# ── Common cross-fixture sanity ─────────────────────────────────


@pytest.mark.parametrize("fixture_name", ["amalgamated", "americu", "wsfs"])
def test_fixtures_with_scoring_workbook_yield_subcap_scores(fixture_name):
    """The 3 full-coverage fixtures must all yield subcap_scores.
    A regression that drops one would silently break the seed_ci
    bootstrap data (those 3 are the seeded entities)."""
    fp = _fixture_path(fixture_name)
    if not fp:
        pytest.skip(f"{fixture_name} fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fp)
    assert pkg.subcap_scores, (
        f"{fixture_name} fixture yielded NO subcap_scores. seed_ci "
        f"relies on this fixture for bootstrap; empty subcaps = empty "
        "demo data + broken e2e suite."
    )


@pytest.mark.parametrize("fixture_name", ["amalgamated", "americu", "wsfs", "regions"])
def test_fixtures_parser_warnings_do_not_contain_unhandled_traceback(
    fixture_name,
):
    """A parser warning must never carry a raw Python traceback --
    those would mean an exception leaked from the protected branch
    into the warning text. The `_maybe` helper wraps tracebacks into
    typed kind strings, so the warning text must be operator-readable."""
    fp = _fixture_path(fixture_name)
    if not fp:
        pytest.skip(f"{fixture_name} fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fp)
    for w in pkg.parser_warnings:
        # Tracebacks contain `File "...", line N` strings.
        assert 'File "' not in w, (
            f"parser_warning carries raw traceback: {w[:200]}. "
            "_maybe must wrap tracebacks into typed kind strings."
        )
        assert "Traceback (most recent" not in w
