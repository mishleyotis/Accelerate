"""A producer subagent must know the gate that will refuse it.

Owner, 2026-08-23, after eight surface defects on promoted runs: "Ensure to
place robust tests after fixing as well as enhancing subagents handling the
segments to avoid any future recurrence."

CG-40's depth floors and CG-41's contact baseline landed as connector gates.
A gate the producer does not know about is a gate that fires at SUBMIT, after
the search window has closed and the session's context is spent — the
producer then either re-runs the whole pass or writes a thin disclosure it
could have written deliberately. Measured on the day the floors landed: five
of the producers those floors govern mentioned CG-40 zero times.

So these tests bind the two together in both directions, which is the shape
`test_skill_antipatterns.py` already uses one layer up:

  · the producer that owns a gated section names its gate
  · every gate id a producer names is a gate that exists
  · the escape is stated wherever a floor is, because a floor with no escape
    is read as "refuse the package", which is the failure this whole round of
    work is about

The third is the one worth having. A producer told only "fifteen products or
the gate blocks" and not "a genuinely small institution has eight and that
run promotes, say what you searched" will refuse packages, and refusing
vetted packages is the defect the owner opened with.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS = ROOT / "plugins" / "dma-insights" / "agents" / "production"

sys.path.insert(0, str(ROOT / "apps" / "mcp"))

#: The producer that owns each gated section, the gate that governs it, and
#: what KIND of gate it is. Keyed by file so a rename fails here rather than
#: silently stopping the check — a test that skips a missing file proves
#: nothing.
#:
#: The kind matters and the first version of this file got it wrong: it asked
#: every gated producer for the depth-floor escape ("a floor on effort, never
#: on the world") and CG-39 failed, correctly. CG-39 is not a floor — it does
#: not ask for MORE of anything, it asks that work the analyst already did
#: reaches the page. Its escape is a different sentence: a recommendation you
#: deliberately leave off is a DISCARD WITH A REASON, not an omission.
#: Demanding the floor sentence there would have taught the producer that a
#: reconciliation failure can be disclosed away, which is the opposite of
#: what CG-39 refuses.
OWNERS = {
    "techstack/techstack-register-producer.md": ("CG-40", "floor"),
    "context/context-sentiment-producer.md": ("CG-40", "floor"),
    "overview/overview-whynow-producer.md": ("CG-40", "floor"),
    "overview/overview-people-producer.md": ("CG-41", "floor"),
    "platform/platform-fit-producer.md": ("CG-39", "reconciliation"),
}

#: Wherever a FLOOR is stated, the escape is stated with it. Any one of these
#: phrasings counts — the point is that the sentence exists, not that it is
#: worded one way.
ESCAPE_MARKERS = (
    "floor is on your effort", "floor is on effort",
    "never on the world", "floor on effort",
)

#: A reconciliation gate's escape instead: the thing you leave out is named
#: and reasoned, never dropped.
RECONCILIATION_MARKERS = ("discard with a reason", "discards with a reason",
                          "discard with reasons")

GATE_ID = re.compile(r"\b((?:AG|SG|ET|CG)-\d{2})\b")


def _read(rel):
    p = AGENTS / rel
    assert p.exists(), f"{rel} is gone — OWNERS is out of date, or a producer was"
    return p.read_text(encoding="utf-8")


def test_every_owned_producer_names_its_gate():
    """The measurement this test exists for: on 2026-08-23 the five producers
    CG-40 governs named it zero times between them."""
    missing = []
    for rel, (gate, _kind) in OWNERS.items():
        if gate not in _read(rel):
            missing.append(f"{rel} does not mention {gate}")
    assert missing == [], (
        "a producer does not know the gate that will refuse it, so the gate "
        "fires at submit with the search window closed:\n  "
        + "\n  ".join(missing))


def test_every_gate_a_producer_names_exists():
    """A file naming CG-42 teaches a producer that CG-42 will catch this. If
    the id were wrong or the gate were dropped, the lesson would be a
    confident falsehood in a document an agent follows."""
    from dma_mcp.gates import GATES
    bad = []
    for path in sorted(AGENTS.rglob("*.md")):
        for gid in set(GATE_ID.findall(path.read_text(encoding="utf-8"))):
            if gid not in GATES:
                bad.append(f"{path.relative_to(AGENTS)} names {gid}, which is "
                           f"not in the registry")
    assert bad == [], "\n  ".join(bad)


def test_a_floor_is_never_stated_without_its_escape():
    """THE TEST THAT MATTERS MOST HERE.

    Every one of these floors is satisfiable by disclosure — a genuinely
    small institution has eight detectable products, a two-year-old firm has
    two years of history, a private company's CFO has no reachable address —
    and the gates were written that way on purpose. A producer that reads the
    floor and not the escape refuses the package instead, which is precisely
    the behaviour the owner opened this round of work by reporting: "most
    default to rejecting in case of issues, rather than triaging and fixing".
    """
    missing = []
    for rel, (gate, kind) in OWNERS.items():
        if kind != "floor":
            continue
        text = _read(rel)
        if gate not in text:
            continue                       # named by the test above
        low = text.lower()
        if not any(m in low for m in ESCAPE_MARKERS):
            missing.append(
                f"{rel} states the {gate} floor and never says it is a floor "
                f"on effort rather than on the world")
    assert missing == [], (
        "a producer told a floor and not its escape will refuse packages "
        "that should promote:\n  " + "\n  ".join(missing))


def test_a_reconciliation_gate_states_the_discard_instead():
    """CG-39 is not a floor and must not read like one.

    It does not ask for MORE of anything — it asks that recommendations the
    analyst already wrote reach the page. Its escape is therefore the
    opposite sentence: a recommendation deliberately left off is a DISCARD
    WITH A REASON that renders, never a disclosure that it is thin. A
    producer that learned the floor escape here would disclose its way past a
    mapping bug, which is exactly what CG-39 refuses.
    """
    missing = []
    for rel, (gate, kind) in OWNERS.items():
        if kind != "reconciliation":
            continue
        low = _read(rel).lower()
        if not any(m in low for m in RECONCILIATION_MARKERS):
            missing.append(f"{rel} names {gate} without naming the discard")
    assert missing == [], "\n  ".join(missing)


def test_a_floor_names_what_would_raise_the_count():
    """"Further research" is not an answer a reader can act on. Where a
    producer explains a thin result, it names the specific missing thing — a
    key, a session, a domain that answers, a year that returned nothing."""
    vague = []
    for rel in ("techstack/techstack-register-producer.md",
                "overview/overview-whynow-producer.md",
                "context/context-sentiment-producer.md"):
        text = _read(rel)
        if "further research" in text.lower() and "never" not in text.lower():
            vague.append(rel)
        # And the positive: it says what to name instead.
        assert re.search(r"what would (?:raise|change) (?:the count|it|the answer)",
                         text, re.I), \
            f"{rel} asks for a disclosure without saying what it must contain"
    assert vague == []


def test_the_recursion_instruction_is_where_the_fifteen_floor_is():
    """Owner, 2026-08-23: "I expect at least 15 technology stack items through
    RECURSIVE searches." The count and the method arrived in one sentence and
    they have to stay in one place: a floor of fifteen with a flat four-query
    checklist under it is a floor nobody can reach, and the producer will
    read the number and disclose rather than search again."""
    text = _read("techstack/techstack-register-producer.md").lower()
    assert "15" in text and "recursi" in text
    assert "until a round yields nothing new" in text, \
        "the recursion has no stopping rule, so 'recursive' is decoration"


def test_the_three_year_span_reaches_both_producers_that_can_break_it():
    """why_now is where CG-40 measures the span, and the timeline shares its
    sources — so a C1 built one year wide produces a why_now that fails, and
    the repair lands in a file that never heard of the rule."""
    for rel in ("overview/overview-whynow-producer.md",
                "context/context-timeline-producer.md"):
        text = _read(rel)
        assert "three years" in text.lower(), rel
        assert re.search(r"once per year|year marker", text, re.I), (
            f"{rel} states the three-year span without the query habit that "
            f"loses it — a range query collapses toward recent results, which "
            f"is how a one-year timeline gets built by a correct search")


def test_the_contact_baseline_states_both_seat_states():
    """CG-41 has exactly two acceptable answers per seat and no third. A
    producer that reads only "resolved" will refuse a roster of honest
    negatives; one that reads only "record something" will write a token."""
    text = _read("overview/overview-people-producer.md")
    low = text.lower()
    assert "recorded negative" in low or "recorded_negative" in low
    assert "enrichment_basis" in text
    assert "title" in low and "matched" in low, \
        "the negative has a contract-defined shape and the producer needs it"
    assert re.search(r"token is not a basis", text, re.I), \
        "without this a seat gets 'n/a' and the gate cannot tell a search ran"


def test_the_fusion_fields_reach_the_producer_that_explains_them():
    """The engine hands the platform producer signal_ranks, rrf_score and a
    fusion_note. If the producer does not know they exist, the card stays
    "basic ... no deep reasoning" with the material sitting on the row."""
    text = _read("platform/platform-fit-producer.md")
    for field in ("signal_ranks", "rrf_score", "fusion_note"):
        assert field in text, f"platform-fit-producer never mentions {field}"
    assert re.search(r"never re-rank|do not compute them|never fuse anything",
                     text, re.I), \
        ("the producer must be told not to re-rank on the fused score — a "
         "producer re-weighting an audited calibration by hand is MEM-0095 "
         "in a new coordinate system")


def test_the_pillar_bar_defect_names_its_upstream_cause():
    """Two clients rendered pillar bars with no fill. The cause was an empty
    rollups.pillars on a run with 47 scored capabilities — a bundle defect,
    not an empty world. A producer that cannot tell those apart serves four
    null rows and the page looks broken in exactly the same way."""
    text = _read("overview/overview-hero-producer.md")
    assert "rollups.pillars" in text or "pillars_basis" in text
    assert re.search(r"not an empty world|bundle defect", text, re.I)
