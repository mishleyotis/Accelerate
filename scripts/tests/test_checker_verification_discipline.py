"""A checker that could not look must not report that nothing is there.

Measured 2026-08-23. One production session ran two challenge rounds over one
package and they contradicted each other on every material point:

  * Round two called the peer medians in `workbook_scores` FABRICATED. It had
    searched `/home/user/Accelerate` — the repository — while the package sat
    where `drive_fetch.py pull` put it, under /root/.dma/packages. Opening the
    real workbook showed Pillar_Summary!C2:C5, Category_Detail!D2:D17 and
    Peer_Median_Directional matching the producer's cited values exactly, and
    the Calculation_Chain sheet it had dismissed as non-existent was there.
  * It called the caps claims unverifiable for the same reason; the workbook's
    own cap distribution matched the payload exactly.
  * Its `unknown_gate` finding on eight `SG-` ids was CORRECT and got argued
    with, because a THIRD document defined ids of the same shape.

Two distinct defects, one shape each:

  1. A failed lookup laundered into an authoritative finding. `UNTESTED` and
     `BREAKS` are not interchangeable and the agents did not say so.
  2. A vocabulary collision. `explain_gate` is the only authority on a
     gate_id, and other documents defined `SG-`-shaped ids of their own, so a
     reader could find a "definition" for an id the connector has never heard
     of.

These tests hold both closed.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "dma-insights"
DISCIPLINE = (PLUGIN / "skills" / "dma-surface-production" / "02-inputs"
              / "6-verification-discipline.md")
GATES = ROOT / "apps" / "mcp" / "dma_mcp" / "gates.py"

#: Every agent whose job is to CHECK rather than produce. A producer may be
#: wrong; a checker that is wrong is believed.
CHECKERS = sorted(
    list((PLUGIN / "agents" / "checkers").glob("*.md"))
    + [PLUGIN / "agents" / "qa" / "adversarial-verifier.md"])


def test_the_discipline_exists_and_names_where_the_package_is():
    """The one fact the failing challenger did not have. A rule that does not
    say WHERE to look leaves the reader searching the repository, which is
    exactly what happened."""
    assert DISCIPLINE.is_file(), f"{DISCIPLINE} is the shared rule"
    text = DISCIPLINE.read_text()
    assert "/root/.dma/packages/" in text, "the package root, spelled out"
    assert "package_map.py" in text and "corpus_search.py" in text, (
        "how to resolve a package whose shape varies, and how to search it")
    assert "explain_gate" in text, "the gate-id authority"


@pytest.mark.parametrize("agent", CHECKERS, ids=lambda p: p.stem)
def test_every_checker_carries_the_discipline(agent):
    """A rule in a file nobody reads is a rule nobody follows. Each checker
    either states it or points at the shared copy."""
    text = agent.read_text()
    carries = ("6-verification-discipline.md" in text
               or "/root/.dma/packages/" in text)
    assert carries, (
        f"{agent.name} writes verdicts but never says where the package is "
        f"or that a failed lookup is a verdict about the search. Add the "
        f"pointer to 02-inputs/6-verification-discipline.md.")


@pytest.mark.parametrize("agent", CHECKERS, ids=lambda p: p.stem)
def test_every_checker_distinguishes_could_not_look_from_not_there(agent):
    """The distinction itself, not just the path. A checker that knows where
    to look can still fail to look and report a defect anyway."""
    text = agent.read_text().lower()
    assert re.search(r"untested|not_run|could not (look|find|verify|open)"
                     r"|could_not_verify", text), (
        f"{agent.name} carries no label for 'I could not test this'. Without "
        f"one, every failed lookup lands on a label that means the claim is "
        f"wrong.")


# ── the vocabulary collision ──────────────────────────────────────────────

def registry_ids() -> set:
    """The gate ids `explain_gate` will answer for, read from the registry
    rather than re-typed — a second list is how this class of defect starts."""
    src = GATES.read_text()
    return set(re.findall(r'^\s{4}"([A-Z]{2}-[A-Z0-9]+)":\s*\(', src, re.M))


def test_the_connector_defines_no_numeric_sg_id():
    """The premise the ban rests on. Every SG gate the connector actually has
    is letter-suffixed (SG-V4 grounding, SG-S8 sentiment), so `SG-<digits>`
    names a connector gate in no case at all — which is why the eight ids in
    the incident all came back `unknown_gate`, correctly."""
    numeric = sorted(i for i in registry_ids()
                     if re.fullmatch(r"SG-\d+", i))
    assert not numeric, (
        f"the registry now defines {numeric}; this file's ban on SG-<digits> "
        f"elsewhere assumed it never would. Reconcile deliberately.")
    assert {"SG-V4", "SG-S8"} <= registry_ids(), (
        "the registry lost its SG entries — read gates.py before trusting "
        "this test's premise")


#: `- SG-01: something` / `| SG-01 | something |` — a DEFINITION. A mention
#: inside a sentence is fine and often necessary (the incident is recorded in
#: prose in several places); it is the definition list that makes a reader
#: believe the id is real.
SG_DEFINITION = re.compile(
    r"^\s*(?:[-*+]|\|)\s*`?(SG-\d+)`?\s*(?::|\|)", re.M)


@pytest.mark.parametrize("doc", sorted(
    p for p in PLUGIN.rglob("*.md") if "node_modules" not in str(p)),
    ids=lambda p: str(p.relative_to(PLUGIN)))
def test_no_plugin_doc_defines_a_gate_the_connector_does_not_have(doc):
    """The `SG-` namespace belongs to apps/mcp/dma_mcp/gates.py alone.

    The dma-research skill defined SG-01..SG-06 for its own batch checks —
    real, useful checks, and nothing to do with payload safeguard gates. A
    challenger found them and argued that eight fabricated payload ids were
    legitimate. They are RS-01..RS-06 now. Any future check of a skill's own
    behaviour gets its own prefix too."""
    hits = [m.group(1) for m in SG_DEFINITION.finditer(doc.read_text())]
    unknown = [h for h in hits if h not in registry_ids()]
    assert not unknown, (
        f"{doc.relative_to(PLUGIN)} defines {unknown}, which the connector's "
        f"registry does not carry — `explain_gate` answers `unknown_gate` and "
        f"CG-22 refuses a payload naming it. If these are a skill's own "
        f"checks, give them their own prefix (dma-research's are RS-nn).")


def test_dma_research_batch_checks_left_the_sg_namespace():
    """The specific rename, pinned by name so a revert is loud."""
    skill = (PLUGIN / "skills" / "dma-research" / "SKILL.md").read_text()
    assert "RS-01:" in skill and "RS-06:" in skill, (
        "the research batch checks are RS-nn")
    assert not SG_DEFINITION.search(skill), (
        "and nothing there defines an SG-nn id any more")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
