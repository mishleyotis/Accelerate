"""Regression: simulate-all-deploy-stages.sh must NOT silently pass
when explicitly-requested stages can't run.

Independent QA (2026-06-06) found two related bugs:

1. `TOTAL_STAGES=20` even though stage 21 (dma-real-sample-audit)
   is defined and recorded. The header showed `[21/20]` (off-by-one).

2. When `node_modules` is absent AND the operator passes
   `--stages 12`, the entire frontend block was skipped WITHOUT
   recording SKIP rows. The final tally was `0/0 PASS · 0 FAIL ·
   0 SKIP` and the script exited 0 -- CI/operator believed the
   deploy gate was green even though the requested gate didn't
   actually run.

The fix:
  - TOTAL_STAGES bumped to 21
  - The else-branch under `node_modules` absent now records SKIP
    for each requested frontend stage (not gated on ONLY_STAGES
    being empty)
  - Exit-code policy: ONLY_STAGES set AND any SKIP recorded →
    exit 1 (silent skip on explicit request hides infra drift)
  - ONLY_STAGES set AND total_run == 0 → exit 1 (no stage matched)

All three contracts are pinned as static-AST checks here.
"""
from __future__ import annotations

from pathlib import Path

SCRIPT = (
    Path(__file__).parent.parent.parent / "infra"
    / "simulate-all-deploy-stages.sh"
)


def test_total_stages_matches_defined_stages() -> None:
    """TOTAL_STAGES must equal the highest stage the script defines.

    History: 20 -> 21 (dma-real-sample-audit, 2026-06-06 QA-8
    off-by-one); 21 -> 24 (2026-07-02 master plan Part 14: stage 22
    pack-freshness-gate-sim, stage 23 gemini-cold-gate-sim, stage 24
    pack-parity-report). A mismatched header confuses operators (the
    original bug showed `[21/20]` and `1/20 PASS` implying 19 silent
    SKIPs)."""
    src = SCRIPT.read_text()
    assert "TOTAL_STAGES=24" in src, (
        "TOTAL_STAGES must equal 24 (stages 22-24 = the Part 14 "
        "deploy-gate simulations are defined and recorded)."
    )
    # Every stage 1..24 must actually be gated by an _in_only_stages call.
    for n in range(1, 25):
        assert f"_in_only_stages {n}" in src, (
            f"stage {n} has no `_in_only_stages {n}` gate -- TOTAL_STAGES "
            f"says 24 but stage {n} is undefined (header drift)."
        )


def test_missing_node_modules_records_skip_per_requested_stage() -> None:
    """When node_modules is absent, EACH explicitly-requested
    frontend stage (12, 13, 14, 15) must record SKIP -- not be
    silently absent."""
    src = SCRIPT.read_text()
    # The fix uses `_in_only_stages "$n"` inside the missing-prereq
    # branch so each requested stage records SKIP regardless of the
    # ONLY_STAGES emptiness rule.
    assert "_in_only_stages \"$n\"" in src, (
        "Inside the `node_modules absent` else-branch the script must "
        "iterate `for n in 12 13 14 15` and `_record SKIP` for each "
        "stage the operator explicitly requested. The pre-fix branch "
        "only recorded SKIP when ONLY_STAGES was empty -- silent on "
        "explicit requests."
    )
    # The pre-fix pattern MUST NOT appear (gated on empty ONLY_STAGES).
    assert "[[ -n \"${ONLY_STAGES:-}\" ]] || {" not in src, (
        "The script still has the old `[[ -n ONLY_STAGES ]] || { ... }` "
        "guard around the SKIP recording. That guard was the false-pass "
        "bug -- it suppressed SKIP records on explicit --stages runs."
    )


def test_explicit_stages_with_skip_exits_nonzero() -> None:
    """When ONLY_STAGES is set AND any stage was SKIPped, the script
    must exit 1. SKIP-on-explicit-request hides infra drift; the
    full-sweep tolerance does not apply."""
    src = SCRIPT.read_text()
    # The exit-code policy must mention both branches.
    assert "SKIP" in src and "exit 1" in src
    # Must check ONLY_STAGES and SKIP > 0 together.
    assert "ONLY_STAGES" in src
    assert "SKIP" in src
    # The literal guard from the fix:
    assert "\"$SKIP\" -gt 0" in src, (
        "The exit-code logic must have a `[[ \"$SKIP\" -gt 0 ]]` check "
        "under the ONLY_STAGES guard. Without it, an operator who "
        "explicitly passes --stages 12 and gets a SKIP gets exit 0 "
        "and CI keeps marching."
    )


def test_zero_stages_matched_exits_nonzero() -> None:
    """`--stages '99'` (nonexistent stage) used to silently exit 0
    because no stage block fired. Now must exit 1."""
    src = SCRIPT.read_text()
    assert "\"$total_run\" -eq 0" in src, (
        "The exit-code logic must check `total_run -eq 0` under the "
        "ONLY_STAGES guard -- a typo in --stages that matches nothing "
        "now FAILS instead of falsely succeeding."
    )
