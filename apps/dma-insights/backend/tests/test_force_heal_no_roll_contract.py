"""Regression: deploy-two-phase.sh MUST call force-heal-db.sh with
`--no-roll` so the heal repairs credentials without rolling the live
backend service.

Independent QA (2026-06-06) confirmed the symptom: during Phase 4
candidate probing, an internal force-heal cycle fired and rolled a
fresh LIVE backend revision OUT OF the candidate isolation flow.
The candidate tag URL then served the stale prior revision while
the live service URL served the freshly-healed one, and the probe
loop saw a confusing pattern of 503s + ready responses depending on
which URL was hit. Operators observed: "force-heal rolls revisions,
then the candidate probe sees repeated 503s."

The contract:
  - force-heal-db.sh --no-roll is the credential-only heal mode
  - deploy-two-phase.sh's call sites all use --no-roll because the
    script issues its OWN targeted candidate roll via
    `gcloud run services update --no-traffic --tag candidate-...`

This static AST check ensures the contract holds in CI Stage 1.
"""
from __future__ import annotations

import re
from pathlib import Path

INFRA = Path(__file__).parent.parent.parent / "infra"
DEPLOY = INFRA / "deploy-two-phase.sh"
HEAL = INFRA / "force-heal-db.sh"


def test_force_heal_db_supports_no_roll_flag() -> None:
    src = HEAL.read_text()
    # The flag must be documented in the usage block.
    assert "--no-roll" in src, (
        "force-heal-db.sh must support --no-roll. Without it, every "
        "credential heal also rolls the backend service -- defeats "
        "the two-phase deploy's candidate-isolation contract."
    )
    # The flag must short-circuit the revision-roll block.
    # The pattern: `if ! $ROLL; then ... exit 0; fi` BEFORE any
    # `gcloud run services update` call.
    no_roll_idx = src.find('if ! $ROLL; then')
    update_idx = src.find('gcloud run services update "$BACKEND_SVC"')
    assert no_roll_idx > 0, (
        "force-heal-db.sh must guard the revision-roll on the $ROLL "
        "flag. Without the guard, --no-roll has no effect."
    )
    assert update_idx > no_roll_idx, (
        "The `gcloud run services update` revision-roll must come "
        "AFTER the `$ROLL` guard. Otherwise --no-roll runs the "
        "revision roll anyway."
    )


def test_deploy_two_phase_uses_no_roll_for_all_force_heal_invocations() -> None:
    """Every `force-heal-db.sh` invocation in deploy-two-phase.sh
    MUST pass `--no-roll`. The script issues its own candidate-
    isolated revision roll via `--no-traffic --tag candidate-...`
    -- letting force-heal also roll would create a competing live
    revision OUTSIDE the candidate isolation."""
    src = DEPLOY.read_text()
    # Find every force-heal-db.sh invocation (an actual command call,
    # not a comment / docstring mention). Excludes lines starting with
    # `#`, and excludes the variable-resolution form `SCRIPT_DIR}/force-heal-db.sh"`
    # being assigned to a variable. The pattern we match is the command
    # being executed -- i.e. preceded by `! ` or starting at the line.
    invocations: list[str] = []
    for line in src.splitlines():
        # Strip leading whitespace; skip comment lines
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # An actual invocation is one where force-heal-db.sh" is the
        # COMMAND being executed -- the immediate next non-whitespace
        # is either end-of-statement (`;`, `&&`, `||`, end-of-line) or
        # an argument (a flag starting with `--`). Lines like
        # `[[ -x ".../force-heal-db.sh" ]]` are CHECKS not invocations
        # and have a `]` after the quote -- excluded by the lookahead.
        # Lines like `echo ".../force-heal-db.sh"` are documentation
        # within a string and have arbitrary content after -- excluded
        # by anchoring to the start with a command-prefix pattern.
        if re.search(
            r'(?:^|\bif\s+!\s+|\b&&\s+|\b\|\|\s+)"\$\{SCRIPT_DIR\}/force-heal-db\.sh"'
            r'(?=\s*(?:--\S+|;|\&\&|\|\||$))',
            line,
        ):
            invocations.append(line)

    assert invocations, (
        "Could not find any `force-heal-db.sh` invocation in "
        "deploy-two-phase.sh. The discovery regex may be wrong, or "
        "the script restructured."
    )

    missing_no_roll: list[str] = []
    for line in invocations:
        if "--no-roll" not in line:
            missing_no_roll.append(line.strip())

    assert not missing_no_roll, (
        f"{len(missing_no_roll)} force-heal-db.sh invocation(s) "
        f"in deploy-two-phase.sh missing --no-roll:\n  "
        + "\n  ".join(missing_no_roll)
        + "\n\nAdd --no-roll so the heal repairs credentials WITHOUT "
        "rolling the backend service. The deploy issues its own "
        "candidate-isolated roll via `--no-traffic --tag`."
    )
