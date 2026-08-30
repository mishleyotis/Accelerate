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
import re
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

    # It must be EMITTED as a PIN, never a REFUSE. Checked at the emission
    # site rather than by proximity to the first mention of the phrase: prose
    # above the code discusses coarse grain too (the read-ceiling fix explains
    # how a truncated read could have PINned a subcapability workbook as
    # coarse), and a test that keys on the first occurrence starts measuring
    # the commentary instead of the behaviour.
    emissions = [m for m in re.finditer(r'note\(\s*"(\w+)"\s*,\s*\n?\s*f?"?COARSE GRAIN', src)]
    assert emissions, "no note(...) call emits the coarse-grain finding at all"
    assert all(m.group(1) == "PIN" for m in emissions), (
        f"the coarse-grain finding must be a PIN, got "
        f"{[m.group(1) for m in emissions]}")
    assert 'note("REFUSE"' not in src[src.index("COARSE GRAIN"):
                                      src.index("COARSE GRAIN") + 600], (
        "and nothing near it may refuse")


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


# ── a minority of bad rows is not a bad package ───────────────────────────
#
# Measured 2026-08-23 over the pending queue's head, 14 packages: the corpus
# rate sat at 85.7% and one of the two refusals was V5 on a package carrying
# 48 short excerpts out of 312 populated — 15.4% short, 84.6% usable, median
# 82 characters. The whole package was refused for a sixth of its rows.
#
# THE PROTECTION IS ALREADY DOWNSTREAM AND FAIL-CLOSED. An excerpt under 50
# characters cannot be registered (invariant 4), so it cannot be cited, so it
# cannot reach a client. Those 48 rows go out as GAPs exactly like an explicit
# absence; the other 264 produce. Refusing the package discards the 264 to
# protect against something already prevented row by row.
#
# A MAJORITY short is a different fact — the excerpt column is not carrying
# quotations at all, and there is no evidence tier to produce from. That still
# refuses. After the change the same corpus reads 92.9%.

def _v5_verdict(short, populated):
    """The rule as vet_workbooks applies it: proportion decides."""
    pct = (short / populated * 100) if populated else 100.0
    return "REFUSE" if pct >= 50 else "PIN"


def test_the_measured_package_is_pinned_not_refused():
    """48 of 312, exactly as measured."""
    assert _v5_verdict(48, 312) == "PIN"


def test_a_majority_short_still_refuses():
    """No usable evidence tier to produce from."""
    assert _v5_verdict(200, 312) == "REFUSE"


def test_the_boundary_is_half():
    assert _v5_verdict(156, 312) == "REFUSE"
    assert _v5_verdict(155, 312) == "PIN"


def test_the_source_applies_the_proportion_and_names_the_denominator():
    src = VETTER.read_text()
    assert "pct >= 50" in src, "proportion decides, not a bare count"
    assert "populated - short" in src, (
        "the PIN tells the producer how many rows still produce")
    assert "invariant 4" in src, (
        "and why the package need not be refused: registration already "
        "refuses each short row individually")


def test_an_explicit_absence_is_in_neither_half():
    """The denominator is rows that OFFER a quotation. An absence marker is
    not a failed excerpt and must not inflate the short share — the same
    distinction this file already draws for the [NO_EVIDENCE] case."""
    src = VETTER.read_text()
    assert "populated = len(excerpts) - absent" in src
