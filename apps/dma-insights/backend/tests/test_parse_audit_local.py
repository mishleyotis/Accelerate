"""Regression: app.scripts.parse_audit_local — local-filesystem variant
of the DMA-Drive parse-only audit.

The production audit (`historical_backfill.py --parse-only --sample N`)
walks Google Drive and requires SA credentials. The sidecar exercised
here walks a local directory and emits the IDENTICAL PARSEONLY JSON line
shape, so CI can exercise the parser-robustness contract against the
real fixture distribution without Drive access.

Coverage:
  - argv contract: `--dir` required; `--sample` accepts > 0 only; bad
    inputs exit 2 with an actionable stderr message.
  - Discovery: only directories that look like DMA packages
    (MANIFEST.json or 03_scoring_workbook/) are enumerated; junk
    siblings are silently dropped.
  - Sampling determinism: `--seed` and DMA_SAMPLE_SEED both pin the
    shuffle so the same N folders come back across runs.
  - End-to-end against the 5 in-repo real samples
    (tests/fixtures/dma_packages_real_samples/): every folder parses
    cleanly and emits a PARSEONLY line with the documented JSON keys.
  - Exit code: 0 when every folder parses, 1 if at least one raises.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.scripts import parse_audit_local

REAL_SAMPLES_DIR = (
    Path(__file__).parent
    / "fixtures" / "dma_packages_real_samples"
)


def _capture(capsys, argv: list[str]) -> tuple[int, str, str]:
    rc = parse_audit_local.main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


# ── argv contract ─────────────────────────────────────────────────────


def test_missing_dir_exits_2(capsys) -> None:
    """`--dir` is required — omitting it must exit 2."""
    rc, _, err = _capture(capsys, [])
    assert rc == 2, f"expected exit 2 for missing --dir, got {rc}"
    assert "--dir" in err.lower() or "required" in err.lower()


def test_dir_does_not_exist_exits_2(capsys, tmp_path) -> None:
    """A non-existent --dir must exit 2 with a clear stderr message."""
    missing = tmp_path / "nope"
    rc, _, err = _capture(capsys, ["--dir", str(missing)])
    assert rc == 2
    assert "FATAL" in err
    assert str(missing) in err


def test_dir_is_a_file_exits_2(capsys, tmp_path) -> None:
    """A --dir that points at a file (not a directory) exits 2."""
    f = tmp_path / "x.txt"
    f.write_text("hi")
    rc, _, err = _capture(capsys, ["--dir", str(f)])
    assert rc == 2
    assert "FATAL" in err


def test_sample_zero_exits_2(capsys) -> None:
    """`--sample 0` is a no-op trap — exit 2 not silent."""
    rc, _, err = _capture(
        capsys, ["--dir", str(REAL_SAMPLES_DIR), "--sample", "0"],
    )
    assert rc == 2
    assert "--sample" in err and ">" in err


def test_sample_negative_exits_2(capsys) -> None:
    """`--sample -1` must exit 2."""
    rc, _, _ = _capture(
        capsys, ["--dir", str(REAL_SAMPLES_DIR), "--sample", "-1"],
    )
    assert rc == 2


# ── Discovery ─────────────────────────────────────────────────────────


def test_discovery_picks_manifest_dirs(tmp_path) -> None:
    """A child dir with MANIFEST.json is a candidate."""
    pkg = tmp_path / "Test_DMA"
    pkg.mkdir()
    (pkg / "MANIFEST.json").write_text("{}")
    found = parse_audit_local._discover_packages(tmp_path)
    assert len(found) == 1
    assert found[0].name == "Test_DMA"


def test_discovery_picks_scoring_workbook_dirs(tmp_path) -> None:
    """A child dir with 03_scoring_workbook/ is a candidate."""
    pkg = tmp_path / "Foo_DMA"
    (pkg / "03_scoring_workbook").mkdir(parents=True)
    found = parse_audit_local._discover_packages(tmp_path)
    assert len(found) == 1


def test_discovery_skips_junk_siblings(tmp_path) -> None:
    """Random unrelated directories must NOT be enumerated."""
    real = tmp_path / "Real_DMA"
    real.mkdir()
    (real / "MANIFEST.json").write_text("{}")
    (tmp_path / "junk").mkdir()
    (tmp_path / "junk" / "readme.md").write_text("not a DMA package")
    (tmp_path / "file.txt").write_text("loose file")
    found = parse_audit_local._discover_packages(tmp_path)
    assert [p.name for p in found] == ["Real_DMA"]


def test_discovery_returns_sorted(tmp_path) -> None:
    """Enumeration order is name-sorted (deterministic)."""
    for name in ["Charlie_DMA", "Alpha_DMA", "Bravo_DMA"]:
        d = tmp_path / name
        d.mkdir()
        (d / "MANIFEST.json").write_text("{}")
    found = parse_audit_local._discover_packages(tmp_path)
    assert [p.name for p in found] == [
        "Alpha_DMA", "Bravo_DMA", "Charlie_DMA",
    ]


# ── Sampling determinism ──────────────────────────────────────────────


def test_seed_pins_shuffle(capsys, monkeypatch) -> None:
    """Same --seed → same N-folder slice across two runs."""
    if not REAL_SAMPLES_DIR.exists():
        pytest.skip("real sample fixtures not present")
    monkeypatch.delenv("DMA_SAMPLE_SEED", raising=False)
    rc1, out1, _ = _capture(
        capsys,
        ["--dir", str(REAL_SAMPLES_DIR), "--sample", "2", "--seed", "pin-A"],
    )
    rc2, out2, _ = _capture(
        capsys,
        ["--dir", str(REAL_SAMPLES_DIR), "--sample", "2", "--seed", "pin-A"],
    )
    assert rc1 == 0 == rc2, "seeded runs must both exit 0"
    # Extract the two folder names from each PARSEONLY line
    names1 = sorted(
        json.loads(line[len("PARSEONLY "):])["folder_name"]
        for line in out1.splitlines() if line.startswith("PARSEONLY ")
    )
    names2 = sorted(
        json.loads(line[len("PARSEONLY "):])["folder_name"]
        for line in out2.splitlines() if line.startswith("PARSEONLY ")
    )
    assert names1 == names2, (
        f"--seed didn't pin the sample: {names1} vs {names2}"
    )


def test_env_var_seed_pins_shuffle(capsys, monkeypatch) -> None:
    """DMA_SAMPLE_SEED env var pins the shuffle when --seed omitted."""
    if not REAL_SAMPLES_DIR.exists():
        pytest.skip("real sample fixtures not present")
    monkeypatch.setenv("DMA_SAMPLE_SEED", "env-pin")
    _, out1, _ = _capture(
        capsys, ["--dir", str(REAL_SAMPLES_DIR), "--sample", "2"],
    )
    _, out2, _ = _capture(
        capsys, ["--dir", str(REAL_SAMPLES_DIR), "--sample", "2"],
    )
    names1 = sorted(
        json.loads(line[len("PARSEONLY "):])["folder_name"]
        for line in out1.splitlines() if line.startswith("PARSEONLY ")
    )
    names2 = sorted(
        json.loads(line[len("PARSEONLY "):])["folder_name"]
        for line in out2.splitlines() if line.startswith("PARSEONLY ")
    )
    assert names1 == names2 != []


# ── End-to-end against 5 real fixtures ────────────────────────────────


def test_end_to_end_against_real_samples(capsys) -> None:
    """Every in-repo real DMA fixture parses cleanly + emits a
    well-formed PARSEONLY JSON line. This is the production-grade
    `--parse-only --sample 50` audit equivalent that CI runs in every
    environment, no Drive creds needed.

    Counts only — see `test_evidence_is_grounded_in_research_workbook`
    for the substantive grounding contract (E-IDs, source URLs,
    excerpts, subcap mappings)."""
    if not REAL_SAMPLES_DIR.exists():
        pytest.skip("real sample fixtures not present")
    rc, out, _ = _capture(capsys, ["--dir", str(REAL_SAMPLES_DIR)])
    assert rc == 0, f"audit exited {rc} — expected 0 (no parse errors)"

    payloads = [
        json.loads(line[len("PARSEONLY "):])
        for line in out.splitlines()
        if line.startswith("PARSEONLY ")
    ]
    assert len(payloads) == 5, (
        f"expected 5 PARSEONLY lines, got {len(payloads)}"
    )

    required_keys = {
        "folder_id", "folder_name", "run_id", "institution",
        "subcap_count", "evidence_count", "recommendation_count",
        "peers_count", "parser_warnings_count", "parser_warnings",
        "parser_observations_count",
    }
    for p in payloads:
        missing = required_keys - p.keys()
        assert not missing, f"{p['folder_name']} missing keys: {missing}"
        # Every real sample has a populated catalogue + ≥1 evidence row.
        assert p["subcap_count"] > 0, p["folder_name"]
        assert p["evidence_count"] > 0, p["folder_name"]
        # parser_warnings is bounded (head [:10]) — list shape preserved.
        assert isinstance(p["parser_warnings"], list)
        assert len(p["parser_warnings"]) <= 10
        # No error markers leaked through.
        assert "PARSEONLY_ERROR" not in p["run_id"]

    # Every fixture surfaces a different institution — sanity check that
    # the audit isn't accidentally re-parsing the same folder five times.
    institutions = {p["institution"] for p in payloads}
    assert len(institutions) == 5, (
        f"expected 5 distinct institutions, got {institutions}"
    )


# ── Substantive grounding contract (not just `count > 0`) ─────────────


_E_ID_RE = re.compile(r"^E-\d+$")
_SUBCAP_RE = re.compile(r"^P[1-4]C\d+(\.\d+){1,2}$")


def test_evidence_is_grounded_in_research_workbook() -> None:
    """The DEEP grounding contract: parsing a real DMA package must
    produce evidence rows that are individually well-formed AND
    cross-linked to the scored subcaps they support — NOT just counted.

    The user's mandate: 'if it is parsing evidence, is the evidence
    parsed and grounded and validated against the research workbook'.
    This is the assertion battery that backs that mandate:

      1.  Every evidence row has a well-formed E-ID (E-NNN format
          that the n8n pipeline assigns; cross-checked at the dedup
          + audit layer via content_hash). A malformed E-ID would
          break the cite-chip resolver on EvidenceDrawer.
      2.  Every evidence row has a non-empty source_url that survived
          the parser_warnings strip-pass — the URL is what the
          freshness_band SQL trigger AND content_hash compute against,
          so an empty URL would collapse the dedup contract.
      3.  Every evidence row has a substantive excerpt (>20 chars) —
          short of that the RAG bundle has no payload to ground a
          synthesized answer on, and the citation validator would
          fail-closed.
      4.  Every evidence row has at least one subcap mapping that
          targets a real scored subcap — `subcap_mappings` is what
          the heatmap drawer reads to surface 'this score is supported
          by N evidence rows'. An evidence row mapped to a non-scored
          subcap is orphan grounding and silently disappears from
          the drawer.
      5.  At least 90% of the evidence rows' subcap_mappings overlap
          the scored subcap set — strict 100% is too brittle (the
          AlmaBank fixture has 24/709 entity-profile-level evidence
          that maps to no specific subcap by design), but a regression
          that drops to <90% indicates the parser is producing
          orphan mappings.
      6.  Every scored subcap has BOTH a numeric score AND a non-empty
          rationale (>30 chars) — the visualisation skeleton requires
          both. A scored subcap with no rationale is what the UI
          treats as the 'no data' empty state, even though the score
          itself exists.
      7.  The pillar_scores aggregate matches what the AlmaBank
          research workbook actually produced (within ±0.02 of the
          historically-frozen Q2 2026 baseline) — this catches a
          parser regression that silently drops a pillar's evidence.

    Run against the AlmaBank fixture specifically because it's the
    richest in-repo sample (698 subcaps, 105 evidence, full
    catalogue v5.5 pinning).
    """
    fixture = REAL_SAMPLES_DIR / "Alma_Bank__DMA"
    if not fixture.exists():
        pytest.skip("Alma_Bank__DMA fixture not present")

    # Import inside the test so a missing dep surfaces here cleanly
    # rather than at module import.
    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fixture)

    # ── 1. Every E-ID is well-formed
    malformed = [e.e_id for e in pkg.evidence if not _E_ID_RE.match(e.e_id)]
    assert not malformed, (
        f"evidence E-IDs must be E-NNN; malformed: {malformed[:5]}"
    )

    # ── 2. Every evidence row has a non-empty source_url
    no_url = [
        e.e_id for e in pkg.evidence
        if not e.source_url or len(e.source_url) < 10
    ]
    assert not no_url, (
        f"evidence rows missing source_url: {no_url[:5]} of "
        f"{len(pkg.evidence)} total"
    )

    # ── 3. Every evidence row has a substantive excerpt
    short_excerpts = [
        e.e_id for e in pkg.evidence
        if not e.excerpt or len(e.excerpt) < 20
    ]
    assert not short_excerpts, (
        f"evidence rows with excerpt<20 chars: {short_excerpts[:5]}"
    )

    # ── 4. Every evidence row has subcap_mappings
    no_mapping = [e.e_id for e in pkg.evidence if not e.subcap_mappings]
    assert not no_mapping, (
        f"evidence rows with no subcap_mappings: {no_mapping[:5]} -- "
        f"these would be orphan grounding the heatmap drawer can't "
        f"surface"
    )

    # ── 5. ≥90% of subcap_mappings target real scored subcaps
    score_ids = {s.subcap_id for s in pkg.subcap_scores}
    ev_mapping_targets: set[str] = set()
    for e in pkg.evidence:
        for m in e.subcap_mappings or []:
            if _SUBCAP_RE.match(m):
                ev_mapping_targets.add(m)
    assert ev_mapping_targets, (
        "no evidence subcap_mappings matched the P*C*.*.* shape "
        "after parsing -- catalogue resolver would dead-end"
    )
    overlap = ev_mapping_targets & score_ids
    overlap_pct = len(overlap) / len(ev_mapping_targets)
    assert overlap_pct >= 0.90, (
        f"only {overlap_pct:.1%} of evidence subcap_mappings overlap "
        f"the scored subcap set ({len(overlap)}/{len(ev_mapping_targets)}); "
        f"regression: parser is producing orphan grounding"
    )

    # ── 6. Every scored subcap has a score AND a rationale
    no_score = [s.subcap_id for s in pkg.subcap_scores if s.score is None]
    assert not no_score, (
        f"scored subcaps with no numeric score: {no_score[:5]} -- "
        f"the heatmap renders these as 'no data' even though the "
        f"score row exists"
    )
    no_rationale = [
        s.subcap_id for s in pkg.subcap_scores
        if not s.rationale or len(s.rationale) < 30
    ]
    assert not no_rationale, (
        f"scored subcaps with no rationale: {no_rationale[:5]} -- "
        f"the rationale is what the subcap drawer shows when the "
        f"AE clicks a cell; without it the drawer is empty"
    )

    # ── 7. Pillar scores match the AlmaBank Q2 2026 baseline within ±0.02
    expected = {"P1": 1.943, "P2": 1.754, "P3": 2.44, "P4": 1.878}
    for pillar, expected_score in expected.items():
        actual = pkg.run_manifest.pillar_scores.get(pillar)
        assert actual is not None, f"pillar {pillar} missing from manifest"
        assert abs(actual - expected_score) < 0.02, (
            f"AlmaBank pillar {pillar} score drifted from baseline: "
            f"expected {expected_score:.3f}, got {actual:.3f}. "
            f"Either the workbook changed (regenerate baselines) or "
            f"the parser dropped evidence (real regression)."
        )

    # ── 8. Overall score is the weighted aggregate, not a raw sum
    overall = pkg.run_manifest.overall_score
    assert overall is not None
    assert 1.5 <= overall <= 2.5, (
        f"AlmaBank overall_score outside the expected band "
        f"[1.5, 2.5]: got {overall}"
    )


def test_research_workbook_evidence_merged_into_csv_rows() -> None:
    """`parser_warnings` is the audit ledger for what the research-
    workbook merge contributed: each AlmaBank/WSFS/Regions package's
    DMA_Research_Workbook_*.xlsx is cross-referenced against the CSV-
    parsed evidence rows by E-ID, with workbook subcap mappings AND
    rationales merged into the canonical evidence_index.

    The audit emits a parser_warning like:
        'xlsx_name_enrichment: +N subcap names +M rationales merged'
        'research_workbook_evidence: +K new E-IDs, Q CSV rows enriched'

    Confirm that this cross-reference is actually running -- a silent
    parser regression that skips the workbook merge would still parse
    the CSVs cleanly but the merge audit lines would disappear from
    `parser_warnings`, and the DMA-package-vs-research-workbook
    grounding contract would silently degrade.
    """
    fixture = REAL_SAMPLES_DIR / "Alma_Bank__DMA"
    if not fixture.exists():
        pytest.skip("Alma_Bank__DMA fixture not present")

    from app.services.parsers.dma_package import parse_package

    pkg = parse_package(fixture)

    # The AlmaBank fixture emits BOTH merge markers:
    #   xlsx_name_enrichment   → workbook → CSV row enrichment
    #   research_workbook_evidence → research_workbook → evidence merge
    joined_warnings = "\n".join(pkg.parser_warnings)
    assert "xlsx_name_enrichment:" in joined_warnings, (
        "expected the xlsx_name_enrichment audit line in parser_warnings; "
        "if missing, the workbook → CSV row merge silently stopped firing. "
        f"current warnings: {pkg.parser_warnings}"
    )
    assert "research_workbook_evidence:" in joined_warnings, (
        "expected the research_workbook_evidence audit line in "
        "parser_warnings; if missing, the research workbook merge "
        "silently stopped firing. current warnings: "
        f"{pkg.parser_warnings}"
    )

    # The xlsx_name_enrichment marker should report +698 subcap names
    # +698 rationales merged for the AlmaBank workbook (one rationale
    # per subcap). A drift here means either the workbook content
    # changed (regen baseline) or the parser regressed.
    enrich_line = next(
        (w for w in pkg.parser_warnings if "xlsx_name_enrichment:" in w),
        "",
    )
    m = re.search(r"\+(\d+) subcap names \+(\d+) rationales", enrich_line)
    assert m, (
        f"xlsx_name_enrichment audit line shape changed: {enrich_line!r}"
    )
    names_count = int(m.group(1))
    rationales_count = int(m.group(2))
    assert names_count >= 600 and rationales_count >= 600, (
        f"workbook enrichment dropped: names={names_count}, "
        f"rationales={rationales_count} (expected ≥600 each for AlmaBank)"
    )


def test_parse_failure_returns_exit_1(capsys, tmp_path, monkeypatch) -> None:
    """When parse_package raises, the audit emits PARSEONLY_ERROR and
    exits 1 so CI flags the regression."""
    pkg = tmp_path / "Broken_DMA"
    pkg.mkdir()
    # Mark it as a DMA candidate but leave it empty so parse fails.
    (pkg / "MANIFEST.json").write_text("not valid json")

    def _boom(_folder):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(
        "app.services.parsers.dma_package.parse_package", _boom,
    )
    rc, out, _ = _capture(capsys, ["--dir", str(tmp_path)])
    assert rc == 1, f"expected exit 1 on parse error, got {rc}"
    assert "PARSEONLY_ERROR" in out
    assert "Broken_DMA" in out


def test_help_flag_exits_zero(capsys) -> None:
    """--help is a happy path — argparse prints + exits 0."""
    rc, _, _ = _capture(capsys, ["--help"])
    assert rc == 0
