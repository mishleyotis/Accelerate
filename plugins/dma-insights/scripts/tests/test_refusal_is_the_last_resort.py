"""A package that was vetted and passed must not then be rejected.

Owner, 2026-08-23: the routines "default to rejecting in case of issues,
rather than triaging and fixing the issues especially if package was already
vetted and passed. I believe from above we expect 0% failure rates."

What produced that sentence, measured the same day against the real corpus.
Session accelerate-63 vetted three packages and refused all three. The
surface-production vetter — the checker that actually gates the routine —
returns ZERO refusals on all three; they were refused by
`dma-assessment/scripts/validate_scoring_quality.py`, which the package-vetter
agent was told to treat as binding: "a CRITICAL is a REFUSE ... this is not
advisory".

Re-run today, on the workbook `package_map` resolves rather than a hand-picked
path:

    houlihan-lokey   0 CRITICAL, 17 WARNING     ← was refused
    richwood-bank    0 CRITICAL, 18 WARNING     ← was refused
    lawley           4 CRITICAL,  6 WARNING     ← every one of them "scoring
                                                  at CAPABILITY level"

Two of the three carried no CRITICAL at all once the caps-log check was fixed,
and the third's four are one disclosable fact about grain. vet_corpus over all
three: 3 of 3 PRODUCIBLE.

Three separable rules come out of that, and these tests hold each.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
PLUGIN = HERE.parent
VETTER = (PLUGIN / "skills" / "dma-surface-production" / "scripts"
          / "vet_workbooks.py")
GOV = (PLUGIN / "skills" / "dma-governance" / "scripts" / "gov_auditor.py")
AGENT = PLUGIN / "agents" / "orchestration" / "package-vetter.md"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gov = _load(GOV, "gov_auditor_under_test")


def _occurrences(text: str, needle: str):
    i = text.find(needle)
    while i != -1:
        yield i
        i = text.find(needle, i + 1)


# ── rule 1: an authoring gate is not a production gate ────────────────────

def test_the_vetter_no_longer_treats_a_phase4_critical_as_binding():
    """The exact sentence that cost three clients in one firing."""
    text = AGENT.read_text()
    # The correction quotes the old sentence as the reason the rule exists,
    # so a quoted claim is exempt — the same exemption the routine-prompt
    # guards use. What is banned is the instruction, not the history.
    live = [i for i in _occurrences(text, "a CRITICAL is a REFUSE")
            if '"' not in text[max(0, i - 40):i + 30]]
    assert not live, (
        "validate_scoring_quality.py answers 'should an assessor ship this "
        "workbook?'. The vetter's question is 'can six honest pages be "
        "produced from what was delivered?' — a delivered package is not "
        "going to be re-emitted.")
    # Whitespace-normalised: the sentence is wrapped across lines in the
    # source, and a test that breaks on re-wrapping teaches people to reflow
    # around it rather than to keep the rule.
    flat = " ".join(text.split())
    assert "EVIDENCE FOR YOUR JUDGEMENT, NOT A REFUSAL" in flat


def test_the_vetter_is_told_to_resolve_the_workbook_not_glob_it():
    """One package carries DMA_Scoring_Workbook_Houlihan_Lokey.xlsx,
    DMA_Scoring_Workbook_HL.xlsx (the RESEARCH workbook) and a third marked
    INTERIM. Pointed at the second, the validator reports 712/712 rationales
    too short and 2 CRITICAL — a damning verdict about a file that was never
    meant to carry rationales. Reproduced while writing this test."""
    text = AGENT.read_text()
    assert "package_map.py" in text and "['scoring']['primary']" in text
    assert "NEVER hand a path to a glob" in text


def test_the_closed_refusal_list_is_still_the_only_refusal_authority():
    """Widening what may refuse is how this recurs. The vetter's own codes are
    the list; nothing else may end a firing."""
    src = VETTER.read_text()
    assert "SCRIPT_REFUSALS" in src and "AGENT_REFUSALS" in src
    assert "refusal without a listed code" in src, (
        "note() must still refuse to emit a REFUSE with no registered code")


# ── rule 2: grain is a disclosure ─────────────────────────────────────────

def test_coarse_grain_is_pinned_not_refused():
    """A capability-grain workbook is a real assessment at a coarser grain.
    What changes is how much of the grid carries a score — a number the
    payload states."""
    src = VETTER.read_text()
    assert "COARSE GRAIN" in src
    assert "DISCLOSURE, not dirt" in src
    # and it must be a PIN, never a REFUSE
    idx = src.index("COARSE GRAIN")
    window = src[max(0, idx - 400):idx]
    assert 'note("PIN"' in window, "the coarse-grain finding is emitted as PIN"


def test_the_grain_threshold_is_a_measurement_not_a_guess():
    """144 / 713 / 795 across the three packages, nothing between."""
    src = VETTER.read_text()
    assert "144" in src and "713" in src and "795" in src, (
        "the floor between the grains cites the corpus it was read off")


# ── rule 3: a check that could not run is not a failure ───────────────────

def test_gov_auditor_has_a_not_run_status():
    assert gov.NOT_RUN == "NOT_RUN"
    r = gov.not_run("AG-01", "desc", "no weight column")
    assert r.status == gov.NOT_RUN and not r.ran
    assert r.severity == "INFO", "a NOT_RUN never carries CRITICAL"
    assert "no weight column" in r.details, "the reason travels with it"


def test_a_not_run_is_not_a_fail():
    """Every roll-up counts `status == "FAIL"`. NOT_RUN must fall outside it,
    or the fix reintroduces the defect under a new name."""
    assert gov.not_run("AG-08", "d", "why").status != "FAIL"
    assert gov.CheckResult("AG-08", "PASS", "CRITICAL", "d").ran


def test_the_absent_weight_column_no_longer_sums_zeros():
    """AG-01's mechanism. `[sf(s.get('Weight', ... 0)) for s in subcaps]`
    yields a non-empty list of ZEROS when the column is absent, so
    `if weights` is satisfied, the sum is 0.0, and every capability is
    reported as violating a rule about a column the workbook does not have."""
    src = GOV.read_text()
    assert 'sf(s.get("Weight", s.get("weight", s.get("Subcap_Weight", 0))))' \
        not in src, "the zero-defaulting comprehension is the defect"
    assert "WEIGHT_KEYS" in src and "nothing to sum: not a violation" in src


def test_the_summary_sheet_is_found_by_shape_not_by_literal_name():
    """Real packages carry Pillar_Summary, Executive_Summary,
    Overall_Summary. Requiring the literal name graded a naming convention as
    an aggregation defect."""
    src = GOV.read_text()
    assert 'if "Summary" in wb.sheetnames:\n        summary_rows' not in src
    assert '"summary" in n.strip().lower()' in src


@pytest.mark.parametrize("check_id", ["AG-05", "AG-06", "AG-07", "AG-09"])
def test_cannot_verify_is_reported_as_not_run(check_id):
    """"Cannot verify — Calculation_Chain missing" is the definition of
    NOT_RUN and it used to print as CRITICAL."""
    src = GOV.read_text()
    assert f'CheckResult("{check_id}", "FAIL", "CRITICAL"' not in src, (
        f"{check_id} still reports an absent input as a critical failure")


def test_the_audit_summary_names_what_did_not_run():
    """The alternative to reporting an unrun check as CRITICAL is reporting
    it — not hiding it. A reader must be able to tell a clean audit from an
    audit that could not look; both used to print the same numbers."""
    src = GOV.read_text()
    assert '"checks_not_run"' in src and '"checks_declared"' in src
    assert "Not run:" in src, "and it prints on the console too"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
