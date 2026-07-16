"""Regression: every `--region=...` flag in infra scripts must use
`"$REGION"` (or a sanctioned variable expansion), never a hardcoded
literal like `us-central1`.

Why this matters: when an operator deploys in a non-default region
(e.g. `REGION=europe-west1 bash infra/deploy.sh`), hardcoded
`--region=us-central1` arguments silently target the wrong regional
endpoint. Cloud Run / Cloud SQL / Cloud Scheduler all return 404
or NOT_FOUND for resources in another region, which surfaces as
opaque "service missing" errors that operators don't immediately
connect back to a region mismatch.

The fix is mechanical (replace `--region=us-central1` with
`--region="$REGION"` plus `REGION="${REGION:-us-central1}"` at the
top of each script). This test ensures the fix is never undone.
"""
from __future__ import annotations

import re
from pathlib import Path


def _find_infra_dir() -> Path:
    """Locate apps/dma-insights/infra by walking up from this file."""
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        candidate = ancestor / "infra" / "preflight-parameters.sh"
        if candidate.exists():
            return candidate.parent
        canonical = ancestor / "apps" / "dma-insights" / "infra" / "preflight-parameters.sh"
        if canonical.exists():
            return canonical.parent
    raise RuntimeError(
        f"could not locate apps/dma-insights/infra from {here}"
    )


INFRA = _find_infra_dir()


# Lines that ARE allowed to mention `us-central1`. Three categories:
#  (a) canonical default-value shapes for REGION (`${REGION:-us-central1}`,
#      `${REGION:=us-central1}`, or the `Zennify-canonical NON_SECRET_DEFAULTS`
#      entry for VERTEX_LOCATION);
#  (b) operator-facing example messages -- "e.g. us-central1", "export
#      REGION=us-central1", error/help text that gives the canonical value
#      as an example;
#  (c) comments / heredocs / shebang-banner examples that say "PROJECT_ID=…
#      REGION=us-central1 \\" as documentation;
#  (d) the simulation harness's own grep literal (false positive --
#      this file's grep target appears inside its own source).
ALLOWED_PATTERNS = (
    # (a) Canonical default-value shapes
    re.compile(r'REGION="\$\{REGION:-us-central1\}"'),
    re.compile(r'"\$\{REGION:=us-central1\}"'),
    re.compile(r"\[VERTEX_LOCATION\]=us-central1"),
    # (b) Operator-facing example / error messages
    re.compile(r"\(e\.g\. us-central1\)"),
    re.compile(r"export REGION=us-central1"),
    re.compile(r"REGION=us-central1\b.*\\\\?"),  # heredoc continuation
    # (c) Doc-comment examples
    re.compile(r"^\s*#.*REGION=us-central1"),
    # (d) Simulation harness self-references
    re.compile(r"simulate-all-deploy-stages\.sh"),
    re.compile(r'"--region=us-central1"'),
    re.compile(r"Stage 19: no hardcoded us-central1"),
    re.compile(r'"REGION=\\"\\\$\{REGION:-us-central1\}\\""'),
)


def test_no_hardcoded_region_flags_in_infra_scripts() -> None:
    """For every `.sh` file under infra/, any line containing
    `us-central1` must match one of the ALLOWED_PATTERNS.

    The simulation harness `simulate-all-deploy-stages.sh` is exempt
    from scanning because IT IS the regression detector for this
    contract -- its source must reference the forbidden literal as
    part of its own grep target. (Scanning it would chase its tail.)
    """
    offenders: list[str] = []
    for sh in sorted(INFRA.glob("*.sh")):
        if sh.name == "simulate-all-deploy-stages.sh":
            # Self-referential by design; skip.
            continue
        for lineno, line in enumerate(sh.read_text().splitlines(), start=1):
            if "us-central1" not in line:
                continue
            if any(p.search(line) for p in ALLOWED_PATTERNS):
                continue
            offenders.append(f"{sh.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Found hardcoded us-central1 references that aren't on the "
        "allowed list (canonical default + example + Zennify-canonical "
        "VERTEX_LOCATION). Either fix them to use \"$REGION\" or add a "
        "documented exception to ALLOWED_PATTERNS:\n  "
        + "\n  ".join(offenders)
    )


def test_recover_db_passwords_uses_region_variable() -> None:
    """Sanity: the recover script -- which had the most hardcoded uses
    historically -- must reference $REGION at least 7 times after the
    multi-region cleanup."""
    sh = (INFRA / "recover-db-passwords.sh").read_text()
    n = sh.count('--region="$REGION"')
    assert n >= 7, (
        f"recover-db-passwords.sh has only {n} `--region=\"$REGION\"` "
        f"uses (expected ≥ 7 after the 2026-06-06 multi-region cleanup). "
        f"Did a follow-up commit re-introduce hardcodes?"
    )


def test_deploy_sh_no_hardcoded_region_in_cloud_run_commands() -> None:
    """The main deploy script must use $REGION for every Cloud Run /
    Cloud SQL gcloud invocation."""
    sh = (INFRA / "deploy.sh").read_text()
    # Allow `${REGION}` and `"$REGION"` forms; reject the literal.
    bad = re.findall(r"gcloud run [a-z-]+ [^\n]*--region=us-central1", sh)
    assert not bad, (
        "deploy.sh contains hardcoded `--region=us-central1` on a "
        f"gcloud run command: {bad}. Use $REGION instead."
    )
