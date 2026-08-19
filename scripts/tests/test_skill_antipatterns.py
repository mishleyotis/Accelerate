"""The producer skill must carry the antipatterns, and they must stay true.

An antipattern file that drifts from the gates is worse than none: it teaches a
rule the connector does not enforce, or omits one it does, and a producer
follows the file. These tests bind the two together.

Every entry in `04-craft/9-antipatterns.md` names either the gate that refuses
it or says in as many words that no gate can see it — because "no gate sees
this" is the most important sentence in the file and the easiest to lose.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL = ROOT / "plugins" / "dma-insights" / "skills" / "dma-surface-production"
DOC = SKILL / "04-craft" / "9-antipatterns.md"

sys.path.insert(0, str(ROOT / "apps" / "mcp"))


def test_the_antipattern_file_exists_and_is_reachable():
    assert DOC.exists(), "the producer skill lost its antipatterns"
    readme = (SKILL / "04-craft" / "README.md").read_text()
    assert "9-antipatterns" in readme, \
        "the file is there and nothing points a producer at it"


def test_every_gate_it_names_is_a_gate_that_exists():
    """A file naming AG-11 teaches a producer that AG-11 will catch this. If
    the gate were renamed or dropped, the lesson would be a lie in a document
    people follow."""
    from dma_mcp.gates import GATES
    named = set(re.findall(r"\b((?:AG|CG|ET|SG)-[A-Z0-9]+)\b", DOC.read_text()))
    missing = sorted(g for g in named if g not in GATES)
    assert missing == [], (
        f"the antipatterns name gates the registry does not have: {missing}")


def test_the_round_four_gates_are_all_taught():
    """The five gates written for the round-4 report each exist because a
    person found the defect on a rendered page. A gate with no antipattern
    entry is a rule nobody was told about until it refused them."""
    text = DOC.read_text()
    for gate in ("AG-11", "AG-12", "CG-26", "CG-27", "CG-28"):
        assert gate in text, f"{gate} has no antipattern entry"


def test_the_unguarded_ones_say_so_in_as_many_words():
    """Three of the nine cannot be caught at the payload boundary: a peer
    figure from a second cohort, a field the renderer cannot read, and an
    absence explained rather than removed. Saying "no gate sees this" is what
    stops a producer assuming the connector will catch it."""
    text = DOC.read_text().lower()
    assert text.count("no gate") >= 3, (
        "the antipatterns no longer distinguish what is enforced from what is "
        "only taught, which is the distinction a producer most needs")


def test_it_carries_the_measured_text_not_a_paraphrase():
    """Each entry shows what was actually promoted. A paraphrase is arguable;
    the real sentence is not."""
    text = DOC.read_text()
    for measured in [
        "2.52, 2.70, 2.50 and 2.36",              # the score recap
        "do not quite line up",                    # the accusation
        "greater CFPB scrutiny",                   # the misquoted testimony
        '"scale": 5',                              # the unread field
    ]:
        assert measured in text, f"the measured example {measured!r} is gone"


def test_the_verbatim_rule_and_the_gate_agree_on_which_fields_are_quotes():
    """The file tells a producer that quotes, excerpts, source titles and a
    stated role are never rewritten. CG-27 has to exclude the same set, or one
    of them is wrong."""
    from dma_mcp.validation import _VERBATIM_FIELDS
    for field in ("excerpt", "quote", "source_title", "author_role",
                  "verbatim_quote"):
        assert field in _VERBATIM_FIELDS, \
            f"CG-27 would rewrite {field}, which the antipatterns call verbatim"
