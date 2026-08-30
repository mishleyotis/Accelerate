"""A gate the connector refuses on, that the plugin never mentions, is a trap.

The producer agents read the plugin. The connector enforces the gates. When a
gate exists in one and not the other, a producer meets it as a surprise
rejection with no guidance on how to satisfy it — and the standing complaint
about this system is that it defaults to REJECTING rather than triaging.
Every undocumented gate is one more way to earn that.

Measured 2026-08-24 before this test existed: 65 gates in the connector, 16
of them mentioned nowhere in the plugin — including CG-08 (there is no fifth
band, which is charter invariant 6) and all six of the gates added the same
day. The six were the honest cause: I wrote them, tested them against the
corpus, deployed them, and never told the agents that have to satisfy them.

THE RATCHET IS THE POINT. This test does not ask for good prose — it cannot
judge that. It asks whether the gate id appears anywhere a producer reads. A
gate that needs no producer guidance goes in NOT_PRODUCER_FACING **with its
reason**, so "nobody needs to know this" is a decision on the record rather
than a silence that looks identical to an oversight.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "dma-insights"
# Every module that can REFUSE a payload, not just the two obvious ones.
# The first version of this test read validation.py and validation2.py alone
# and reported CG-13, CG-16 and CG-17 as documented-but-nonexistent — they
# are enforced in gates.py, and a coverage test that cannot see a third of
# the enforcement is a coverage test that lies in both directions.
VALIDATORS = ("validation.py", "validation2.py", "gates.py", "submit.py",
              "promote.py", "register.py", "contracts.py", "transport.py")

GATE_RE = re.compile(r"\b(?:AG|CG|ET|SG)-\d+\b")

#: Gates a producer cannot act on, each with the reason it is exempt. Adding
#: to this list is allowed and is the escape hatch; adding to it WITHOUT a
#: reason is not, and the test below checks that too.
NOT_PRODUCER_FACING: dict[str, str] = {}


def _gate_ids(text: str) -> set:
    return {m.group(0) for m in GATE_RE.finditer(text)}


def connector_gates() -> set:
    src = ""
    for name in VALIDATORS:
        p = ROOT / "apps" / "mcp" / "dma_mcp" / name
        if p.exists():
            src += "\n" + p.read_text()
        else:                       # a renamed module is drift, not absence
            raise AssertionError(
                f"{name} is named as an enforcement module and does not "
                f"exist — fix VALIDATORS rather than letting the coverage "
                f"measurement quietly shrink")
    assert src, "no validator source found — this test would pass vacuously"
    return _gate_ids(src)


#: `dma-governance` numbers its own 108 audit checks AG-01…AG-nn, enforced by
#: its own gov_auditor.py and unrelated to the connector's analysis gates. The
#: prefix collides and the meanings do not: governance AG-06 is "category
#: scores match capability aggregation", which has nothing to do with any
#: connector gate that might one day take that id.
#:
#: This exclusion is not tidying — it is the difference between a coverage
#: test and a coincidence detector. Without it the reverse direction reports
#: four permanent phantoms, AND the forward direction would count a future
#: connector AG-06 as documented on the strength of a governance table row
#: about something else entirely. A check that can be satisfied by an
#: unrelated string is worse than no check.
GOVERNANCE_NAMESPACE = PLUGIN / "skills" / "dma-governance"


def plugin_gates() -> set:
    """Every CONNECTOR gate id the plugin mentions where a producer reads.

    grep rather than a file walk: the guidance is spread across skills,
    rulebooks, agent front matter and docs, and pinning a list of files here
    would go stale the first time one moved.
    """
    # Tests are excluded on their own merit, not to make a number look
    # better: a gate id appearing only in a test file is not guidance, and a
    # producer never reads one. It is also where the governance namespace
    # leaks past the directory exclusion — gov_auditor's own tests live
    # outside the skill folder.
    r = subprocess.run(
        ["grep", "-rho", "-E", r"\b(AG|CG|ET|SG)-[0-9]+\b", str(PLUGIN),
         "--exclude-dir", GOVERNANCE_NAMESPACE.name,
         "--exclude-dir", "tests", "--exclude", "test_*.py"],
        capture_output=True, text=True)
    return set(r.stdout.split())


def test_the_governance_namespace_is_actually_excluded():
    """Pinned, because the exclusion is load-bearing and a silently-ineffective
    --exclude-dir would restore the conflation without failing anything."""
    gov = subprocess.run(
        ["grep", "-rho", "-E", r"\bAG-(06|07|08|10)\b",
         str(GOVERNANCE_NAMESPACE)], capture_output=True, text=True)
    assert gov.stdout.split(), \
        "the governance skill no longer uses these ids — re-check the collision"
    assert not ({"AG-06", "AG-07", "AG-08", "AG-10"} & plugin_gates()), \
        "governance's own audit-check numbering is leaking into the connector "\
        "gate measurement again"


def test_every_connector_gate_is_documented_for_the_producers():
    live, documented = connector_gates(), plugin_gates()
    missing = sorted(live - documented - set(NOT_PRODUCER_FACING),
                     key=lambda g: (g[:2], int(g[3:])))
    assert not missing, (
        f"{len(missing)} gate(s) refuse a payload and appear nowhere in the "
        f"plugin: {missing}. Document each in "
        f"skills/dma-surface-production/05-lifecycle/1-gates.md — what it "
        f"checks, what a passing payload looks like, and what it must NOT "
        f"push a producer into inventing. If a gate genuinely needs no "
        f"producer guidance, add it to NOT_PRODUCER_FACING with the reason.")


def test_the_exemption_list_carries_a_reason_for_every_entry():
    """An exemption with no reason is the silence this test exists to break."""
    for gate, reason in NOT_PRODUCER_FACING.items():
        assert GATE_RE.fullmatch(gate), f"{gate!r} is not a gate id"
        assert len(reason or "") >= 40, (
            f"{gate} is exempt with reason {reason!r} — say why a producer "
            f"cannot act on it, in a sentence someone can disagree with")


def test_the_exemption_list_does_not_name_a_gate_that_no_longer_exists():
    """A stale exemption hides a gate that came back under the same id."""
    live = connector_gates()
    for gate in NOT_PRODUCER_FACING:
        assert gate in live, (
            f"{gate} is exempt but the connector no longer has it — remove "
            f"the exemption so a future gate with this id is not born exempt")


def test_the_plugin_does_not_document_gates_the_connector_dropped():
    """The other direction, reported and not raised.

    Guidance for a retired gate is stale rather than dangerous — it teaches a
    habit that is merely unnecessary — so this states the drift and does not
    fail. What it must never do is stay silent about it.
    """
    live, documented = connector_gates(), plugin_gates()
    ghosts = sorted(documented - live, key=lambda g: (g[:2], int(g[3:])))
    if ghosts:
        print(f"\nNOTE: the plugin mentions {len(ghosts)} gate id(s) the "
              f"connector does not define: {ghosts}. Retired, renamed, or "
              f"documented ahead of being built — worth a look, not a "
              f"failure.")


def test_the_measurement_is_not_vacuous():
    """Both halves must actually find something, or a passing result means
    only that a path was wrong. Two greps returning nothing agree perfectly."""
    live, documented = connector_gates(), plugin_gates()
    assert len(live) >= 50, f"only {len(live)} connector gates found"
    assert len(documented) >= 50, f"only {len(documented)} in the plugin"


@pytest.mark.parametrize("gate", ["CG-08", "CG-44", "CG-45", "CG-46",
                                  "CG-47", "CG-48", "CG-49"])
def test_the_gates_this_test_was_written_for_are_documented(gate):
    """Pinned individually, because a set comparison passing tells you
    nothing about WHICH gates it covered. CG-08 is charter invariant 6 — the
    four-band rule — and it was undocumented for the producers."""
    assert gate in plugin_gates()


def test_the_producer_rulebook_is_where_they_live():
    """Not merely 'mentioned somewhere' for the six added on 2026-08-24: the
    gates file is what a producer reads before submitting."""
    book = (PLUGIN / "skills" / "dma-surface-production" / "05-lifecycle"
            / "1-gates.md").read_text()
    for gate in ("CG-44", "CG-45", "CG-46", "CG-47", "CG-48", "CG-49"):
        assert f"### {gate}" in book, f"{gate} has no section of its own"


def test_the_reach_gate_does_not_teach_inventing_utilization():
    """CG-45 asks a card to state the client's existing estate. The one way
    to satisfy it wrongly is to make up adoption figures, so the guidance has
    to say so where the producer reads it — this is the standing instruction
    'no utilization inference', enforced against the documentation itself."""
    book = (PLUGIN / "skills" / "dma-surface-production" / "05-lifecycle"
            / "1-gates.md").read_text()
    body = book.split("### CG-45")[1].split("### ")[0]
    assert "never push you into inventing utilization" in body
    assert "nothing observed says how much of it is switched on" in body


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
