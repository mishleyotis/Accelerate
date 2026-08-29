"""The binding preflight: sub-vertical and mode are choices with a recorded WHY.

The sub-vertical selects 165 variant cells and withdraws their superseded
bases; the evidence mode decides every DQ's askability. Both were previously
bare CLI flags — a caller could bind a multi-LOB entity to the wrong
sub-vertical and nothing anywhere would hold the reason, so nothing could
audit it. Now the CLI requires a rationale for each, the engine refuses a
rationale-shaped token, the workbook stores the record, and resume reports
whether a binding was stated at all.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2].parent / (
    "plugins/dma-insights/skills/dma-research")
sys.path.insert(0, str(ENGINE))

from engine import runstate  # noqa: E402

BASIS_SV = "NCUA-chartered federal credit union per charter 24680; single LOB"
BASIS_MODE = "engagement letter 2026-08-01 grants public-only review"


def test_a_filler_rationale_is_refused():
    for junk in ("tbd", "n/a", "because I said so tbd", "x" * 19,
                 "TODO fill this in later on", "placeholder rationale here"):
        with pytest.raises(ValueError, match="not a binding rationale"):
            runstate.vet_basis("--sv-basis", junk)


def test_a_real_rationale_is_kept_verbatim_and_whitespace_folded():
    assert runstate.vet_basis("--sv-basis", "  NCUA charter,\n single LOB, "
                              "confirmed 2026-08-29 ") == \
        "NCUA charter, single LOB, confirmed 2026-08-29"


def test_the_refusal_tells_the_caller_to_ask_not_guess():
    """The sentence that matters: an ambiguous entity is the engagement
    owner's question. The refusal must say so, because the agent reading it
    is deciding what to do next."""
    with pytest.raises(ValueError, match="stop and ask"):
        runstate.vet_basis("--sv-basis", "tbd")


def test_start_stores_the_binding_record(tmp_path):
    run = runstate.start(
        run_id="R-BIND-1", entity_name="Acme CU", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE",
        reference_date="2026-08-29", root=tmp_path,
        sv_basis=BASIS_SV, mode_basis=BASIS_MODE,
        lob_census="retail deposits + consumer lending; RB rejected: no OCC charter")
    md = run.open().metadata()
    assert md["sv_basis"] == BASIS_SV
    assert md["mode_basis"] == BASIS_MODE
    assert "RB rejected" in md["lob_census"]
    ctx = json.loads((tmp_path / "00_entity_profile" / "context.json").read_text())
    assert ctx["sv_basis"] == BASIS_SV


def test_an_api_start_without_a_basis_is_unstated_not_invented(tmp_path):
    """The API path (tests, fixtures) stays callable bare — but the stored
    value SAYS nobody recorded a rationale, rather than posing as one.
    Invariant 9's shape: honest absence, never a default that looks like
    data."""
    run = runstate.start(
        run_id="R-BIND-2", entity_name="Acme CU", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE",
        reference_date="2026-08-29", root=tmp_path)
    md = run.open().metadata()
    assert md["sv_basis"].startswith("UNSTATED")
    assert md["mode_basis"].startswith("UNSTATED")
    _, state = runstate.resume("R-BIND-2", tmp_path)
    assert state["binding_stated"] is False


def test_resume_reports_a_stated_binding(tmp_path):
    runstate.start(
        run_id="R-BIND-3", entity_name="Acme CU", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE",
        reference_date="2026-08-29", root=tmp_path,
        sv_basis=BASIS_SV, mode_basis=BASIS_MODE)
    _, state = runstate.resume("R-BIND-3", tmp_path)
    assert state["binding_stated"] is True


def test_the_cli_requires_both_rationales(tmp_path):
    """`engine.cli start` is the conductor's path, and the conductor is the
    one actor positioned to have done the preflight — so the CLI, not the
    API, carries the hard requirement."""
    r = subprocess.run(
        [sys.executable, "-m", "engine.cli", "start", "--run", "R-BIND-4",
         "--root", str(tmp_path), "--entity", "Acme CU", "--entity-id",
         "acme-cu", "--sv", "CU", "--scope", "T1_CORE",
         "--reference-date", "2026-08-29"],
        cwd=ENGINE, capture_output=True, text=True)
    assert r.returncode != 0
    assert "--sv-basis" in r.stderr


def test_the_cli_start_records_and_echoes_the_binding(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "engine.cli", "start", "--run", "R-BIND-5",
         "--root", str(tmp_path), "--entity", "Acme CU", "--entity-id",
         "acme-cu", "--sv", "CU", "--scope", "T1_CORE",
         "--reference-date", "2026-08-29",
         "--sv-basis", BASIS_SV, "--mode-basis", BASIS_MODE],
        cwd=ENGINE, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["binding"]["sv_basis"] == BASIS_SV


def test_the_wrong_subverticals_variants_never_enter_the_run(tmp_path):
    """The mechanism binding protects: seeding is keyed to the bound SV, so
    another sub-vertical's variant cells are structurally absent — not
    present-and-unworked."""
    run = runstate.start(
        run_id="R-BIND-6", entity_name="Acme CU", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="FULL",
        reference_date="2026-08-29", root=tmp_path,
        sv_basis=BASIS_SV, mode_basis=BASIS_MODE)
    from engine import contract
    tax = contract.taxonomy()
    chosen = set(run.open().selected_subcaps())
    foreign = [c for c in tax.variants
               if c in chosen and not tax.tier[c].endswith("-CU")]
    assert not foreign, f"non-CU variants seeded: {foreign[:5]}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
