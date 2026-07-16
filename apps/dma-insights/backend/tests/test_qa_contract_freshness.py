"""CI guard: QA-CONTRACT.md must stay in sync with the repo.

Mirrors `tests/test_infra_safeguards.py` — 10 assertions pinning the
standing QA contract against reality:

  1. file exists + non-empty (>= 35 KB)
  2. every apps/dma-insights/* path it references resolves on disk
  3. all three phase headings present (Pre-Deployment / Deployment / Production)
  4. all 7 release-gate command refs present
  5. all 8 hard rules present (verbatim phrases)
  6. peer-delta-arrow tri-state contract documented (ε=0.05, '·' middle dot,
     '▲' above, '▼' below) — caught a plan-v1 omission
  7. every git SHA in the findings register exists on the branch
  8. each phase enumerates >= N numbered segments
     (PD: 14, DEP: 13, PROD: 15)
  9. edge-case matrix (Appendix G) has >= 30 entries (G-01..G-32)
 10. prior-sessions cross-reference (Appendix H) labels both pre-thread
     and this-thread rounds

The contract document itself is the source of truth — these tests guard
against drift, they do not duplicate its content.
"""
import re
import subprocess
from pathlib import Path


def _find_app_root(start: Path) -> Path:
    """Walk up from `start` until we find a directory containing both
    `backend/` and `infra/`. Works regardless of where the repo is
    mounted — Cloud Build mounts apps/dma-insights/ as /workspace,
    local dev has /home/.../Accelerate/apps/dma-insights/.

    Mirrors the same helper in `test_infra_safeguards.py` — keeping
    the resolution rule identical means future moves don't bit-rot
    just one of the two guards.
    """
    for candidate in [start, *start.parents]:
        if (candidate / "backend").is_dir() and (candidate / "infra").is_dir():
            return candidate
    raise RuntimeError(
        f"Could not find app root (looking for sibling backend/ + infra/) "
        f"starting from {start}. Test must run from inside "
        f"apps/dma-insights/ or have it mounted at /workspace."
    )


APP_ROOT = _find_app_root(Path(__file__).resolve())
CONTRACT = APP_ROOT / "docs" / "QA-CONTRACT.md"


def _resolves_under_app_root(referenced_path: str) -> bool:
    """The contract references files by their REPO-relative path
    (`apps/dma-insights/backend/foo.py`). In Cloud Build the repo
    root isn't accessible — only apps/dma-insights/ is mounted at
    /workspace. Strip the `apps/dma-insights/` prefix so the lookup
    always runs against APP_ROOT, which exists in both contexts.

    Returns False ONLY when the path is genuinely missing from disk
    under APP_ROOT — not because of a layout mismatch.
    """
    prefix = "apps/dma-insights/"
    relative = referenced_path[len(prefix):] if referenced_path.startswith(prefix) else referenced_path
    return (APP_ROOT / relative).exists()


def test_contract_exists_and_non_empty():
    assert CONTRACT.exists(), f"QA-CONTRACT.md not found at {CONTRACT}"
    assert CONTRACT.stat().st_size > 35_000, (
        f"QA-CONTRACT.md is suspiciously small ({CONTRACT.stat().st_size} bytes); "
        "expected ~50 KB+ for the full 42-segment standing contract."
    )


def test_every_referenced_path_resolves():
    """Every apps/dma-insights/* file path mentioned in the contract must
    exist on disk. Catches the contract bit-rotting against repo moves.

    Path resolution: contract references are repo-relative
    (`apps/dma-insights/backend/foo.py`); `_resolves_under_app_root`
    strips the prefix so lookups work in both local + CI layouts.
    """
    text = CONTRACT.read_text()
    referenced = set(
        re.findall(
            r"apps/dma-insights/[a-zA-Z0-9_./\-]+\.(?:py|ts|tsx|jsx|js|css|yaml|md|sh)",
            text,
        )
    )
    missing = sorted(p for p in referenced if not _resolves_under_app_root(p))
    assert not missing, f"contract references missing files: {missing}"


def test_three_phases_present():
    text = CONTRACT.read_text()
    for phase in ("Pre-Deployment QA", "Deployment QA", "Production QA"):
        assert phase in text, f"missing phase heading: {phase}"


def test_release_gate_refs_present():
    text = CONTRACT.read_text()
    for needle in (
        "ci-live-migration.sh",
        "verify-deploy.sh",
        "post-deploy-smoke.sh",
        "test:visual:standalone",
        "test:e2e",
        "build:standalone",
        "build.sh --dry-run",
        "frontend-image-smoke",
    ):
        assert needle in text, f"contract missing release-gate ref: {needle}"


def test_hard_rules_present():
    """All 8 hard rules must appear verbatim in the contract."""
    text = CONTRACT.read_text()
    for required in (
        "Color is a contract",
        "No fabricated values",
        "Every chip explains itself",
        "Persistence = 8 dimensions",
        "Adversarial color rules",
        "Cross-surface consistency",
        "SQL truth-check",
        "Every breakpoint matters",
    ):
        assert required in text, f"missing hard rule: {required}"


def test_peer_delta_arrow_tri_state_contract_documented():
    """Peer-median arrow has THREE states (above / equal / below) with
    ε=0.05 — pinned by `frontend/src/lib/maturity.ts::peerDeltaArrow`
    lines 92-115. Plan v1 missed the 'equal' state; this guard prevents
    that regression in the contract.
    """
    text = CONTRACT.read_text()
    for needle in (
        "tri-state",
        "0.05",
        "at peer median",
        "peerDeltaArrow",
        "var(--z-mid)",
        "var(--z-below)",
        "var(--z-muted)",
    ):
        assert needle in text, (
            f"contract missing peer-delta-arrow contract token: {needle}"
        )


def test_findings_register_commits_resolve():
    """Every git SHA referenced via backticks (in the findings register
    or stress tests) must exist on the branch. Catches stale SHAs from
    rebases or force-pushes.

    Skips gracefully in any of these CI / minimal-env conditions:
      a. `git` binary not installed (python:3.12-slim is the Cloud Build
         stage-0 image and ships WITHOUT git — `pip install` lines in
         cloudbuild.yaml don't pull it in, so subprocess.run raises
         FileNotFoundError). Earlier CI run failed here.
      b. No git repo at all (Cloud Build extracts a tar of
         apps/dma-insights/ without .git).
      c. Shallow clone (depth=1) — historical SHAs in the findings
         register predate the shallow window and would all fail; the
         test would produce false positives in any CI doing a shallow
         checkout, so we skip rather than enforce.

    Local pre-push runs (full clone, git installed) still enforce the
    invariant, which is where stale SHAs would actually be introduced.
    """
    text = CONTRACT.read_text()
    shas = set(re.findall(r"`([0-9a-f]{7,40})`", text))
    if not shas:
        return

    def _git(*args: str) -> "subprocess.CompletedProcess | None":
        """Run a git subcommand. Returns None if git is unavailable
        (FileNotFoundError) so callers can skip cleanly."""
        try:
            return subprocess.run(
                ["git", *args],
                cwd=str(APP_ROOT),
                capture_output=True,
            )
        except FileNotFoundError:
            return None

    # (a) git installed?
    probe = _git("rev-parse", "--git-dir")
    if probe is None:
        return  # git binary missing — CI minimal image
    # (b) in a git repo?
    if probe.returncode != 0:
        return  # no .git anywhere in tree — Cloud Build tar extract
    # (c) shallow clone?
    shallow = _git("rev-parse", "--is-shallow-repository")
    if shallow is not None and shallow.returncode == 0 and shallow.stdout.strip() == b"true":
        return  # shallow clone — historical SHAs intentionally unfetched

    bad = []
    for sha in sorted(shas):
        r = _git("cat-file", "-e", sha)
        if r is None:
            return  # git vanished between probes — give up cleanly
        if r.returncode != 0:
            bad.append(sha)
    assert not bad, f"contract references unknown git SHAs: {bad}"


def test_each_phase_has_min_segments():
    """Pre-deploy >= 14 (added PD-13 catalogue + PD-14 synthesis + PD-15
    workers + PD-16 section routing); Deploy >= 13 (added DEP-13
    build_qa_gates); Production >= 15 (added PROD-13 races + PROD-14
    hygiene + PROD-15 browser compat).
    """
    text = CONTRACT.read_text()
    minimums = {"PD-": 14, "DEP-": 13, "PROD-": 15}
    for prefix, minimum in minimums.items():
        ids = set(re.findall(rf"\b{prefix}\d{{2}}\b", text))
        assert len(ids) >= minimum, (
            f"phase {prefix} only has {len(ids)} segments (need >= {minimum})"
        )


def test_edge_case_matrix_complete():
    """Appendix G enumerates >= 30 edge cases (G-01..G-32 from the plan)."""
    text = CONTRACT.read_text()
    edge_ids = set(re.findall(r"\bG-\d{2}\b", text))
    assert len(edge_ids) >= 30, (
        f"edge case matrix has only {len(edge_ids)} entries; expected >= 30"
    )


def test_prior_sessions_cross_reference_present():
    """Appendix H must reference both pre-thread and this-thread rounds
    so future contributors can trace a finding back to the original
    QA-round that surfaced it.
    """
    text = CONTRACT.read_text()
    assert "Pre-thread" in text and "This thread" in text, (
        "Appendix H must label both 'Pre-thread' and 'This thread' rounds"
    )
