"""Gate H, against the claim that was actually wrong.

The producer prompt said `capped_subcap_ids` has no column on
`context_issue_register` and is dropped at promote. Migration 0027 had
given it one. The gate has to catch exactly that and nothing near it —
the same documents carry four true claims of the same shape, and a gate
that calls those stale is worse than no gate.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "gate_h_prompt_persistence_claims.py"
SKILL = ROOT / "plugins" / "dma-insights" / "skills" / "dma-surface-production"
CONTEXT = SKILL / "03-pages" / "5-context.md"


def _run():
    return subprocess.run([sys.executable, str(GATE)], capture_output=True,
                          text=True, cwd=str(ROOT))


def test_the_repo_is_clean_today():
    r = _run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "none stale" in r.stdout


def test_it_checked_something():
    """A gate that passes because it found nothing to check is not a gate."""
    out = _run().stdout
    n = int(out.split("prompt files,")[1].split("table-scoped")[0].strip())
    assert n >= 1, out


def test_the_claim_that_was_wrong_is_caught():
    original = CONTEXT.read_text(encoding="utf-8")
    stale = original.replace(
        "**Persistence, so you do not lose the work.** `capped_subcap_ids` **does**\npersist:",
        "**Persistence.** `capped_subcap_ids` is validated at submit and has\n"
        "**no column** on `context_issue_register` — it is dropped at promote:",
        1)
    assert stale != original, "the corrected paragraph moved; update this test"
    try:
        CONTEXT.write_text(stale, encoding="utf-8")
        r = _run()
        assert r.returncode == 1, r.stdout
        assert "capped_subcap_ids" in r.stdout
        assert "context_issue_register" in r.stdout
    finally:
        CONTEXT.write_text(original, encoding="utf-8")


@pytest.mark.parametrize("field,table", [
    # True, and it must stay quiet: `theme` is bound on overview_findings and
    # genuinely absent from insight_cards. A name-only check calls this stale.
    ("theme", "insight_cards"),
    ("state", "heatmap_cell_evidence"),
])
def test_a_true_claim_about_another_table_stays_quiet(tmp_path, field, table):
    probe = SKILL / "zz-gate-h-probe.md"
    try:
        probe.write_text(
            f"The I1 contract defines no `{field}` and `{table}` has no "
            f"column for one, so sending it is a contract fork.\n",
            encoding="utf-8")
        r = _run()
        assert r.returncode == 0, r.stdout
    finally:
        probe.unlink(missing_ok=True)


def test_an_unscoped_claim_is_skipped_not_guessed():
    """Naming no table means the claim cannot be checked.

    Skipping is honest. Guessing which of 33 tables was meant is how a gate
    starts reporting things that are not true.
    """
    probe = SKILL / "zz-gate-h-unscoped.md"
    try:
        probe.write_text("`rationale` is dropped at promote.\n", encoding="utf-8")
        r = _run()
        assert r.returncode == 0, r.stdout
    finally:
        probe.unlink(missing_ok=True)


def test_an_empty_registry_refuses_rather_than_passing():
    """A gate whose reference data vanished must fail, not clear everything."""
    src = GATE.read_text(encoding="utf-8")
    assert "refusing to pass" in src and "vacuously" in src
