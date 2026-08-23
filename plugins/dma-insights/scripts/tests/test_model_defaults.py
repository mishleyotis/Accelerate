"""Sonnet 5 is the default; an agent switches only through its own config.

Owner, 2026-08-23: "All models run on sonnet 5 as default with agents and
subagents being able to model switch dependent on their configuration."

Two halves, and they pull in opposite directions, so both are pinned here:

  * The DEFAULT — what a session or a Routine runs when nothing says
    otherwise — is sonnet. Measured 2026-08-23 before the change: lane A ran
    claude-sonnet-5, the rectification and drift Routines ran claude-opus-5,
    and the watchdog and lane B named no model at all, so the same fleet was
    running three different answers to one question.
  * The OVERRIDE stays. All 47 agents declare a model in their own front
    matter, which is exactly the mechanism the owner is asking to keep: a
    grader that needs to reason harder says so where it is defined, not
    wherever it happens to be dispatched from. A change that forced every
    agent to sonnet would satisfy the first half by destroying the second.
"""
import re
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2]          # plugins/dma-insights
ROOT = PLUGIN.parents[1]                              # the checkout
AGENTS = sorted(p for p in PLUGIN.glob("agents/**/*.md")
                if p.name != "README.md")
SETTINGS = ROOT / ".claude" / "settings.json"

# AN EMPTY POPULATION MUST NOT PASS. A wrong ROOT made AGENTS empty on the
# first run of this file, and the parametrised tests reported "skipped" —
# the same shape as the defect class this repo tracks as
# CHECK_NEVER_RAN_READS_AS_UNKNOWN. Assert the denominator at import.
assert len(AGENTS) > 40, (
    f"found {len(AGENTS)} agent files under {PLUGIN / 'agents'} — the roster "
    f"is 47; a path that resolves to nothing would make every test below "
    f"vacuous")
assert SETTINGS.is_file(), f"{SETTINGS} does not exist"

#: The alias vocabulary. Full ids resolve too, but a codebase that uses both
#: `sonnet` and `claude-sonnet-5` for one model has two names for one thing —
#: which is the drift class this repo already tracks as
#: RULE_HELD_IN_TWO_PLACES_DRIFTS.
ALIASES = {"sonnet", "opus", "haiku", "fable", "inherit"}


def declared(path: Path) -> str | None:
    """The `model:` from the front matter, or None."""
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    d = re.search(r"^model:\s*(\S+)\s*$", m.group(1), re.M)
    return d.group(1) if d else None


def test_the_repo_default_is_sonnet():
    """What a session runs when nothing overrides it."""
    import json
    cfg = json.loads(SETTINGS.read_text())
    assert cfg.get("model") == "sonnet", (
        f"{SETTINGS} sets model={cfg.get('model')!r}; the owner's default is "
        f"sonnet")


@pytest.mark.parametrize("agent", AGENTS, ids=lambda p: p.stem)
def test_every_agent_declares_its_own_model(agent):
    """The override mechanism. An agent with no declaration inherits whatever
    dispatched it, which makes its behaviour depend on the caller — the
    opposite of "dependent on their configuration"."""
    assert declared(agent), (
        f"{agent.name} declares no model, so it runs whatever dispatched it")


@pytest.mark.parametrize("agent", AGENTS, ids=lambda p: p.stem)
def test_agents_name_models_in_one_vocabulary(agent):
    """`sonnet` and `claude-sonnet-5` are one model under two names, and a
    reader comparing two agents cannot tell whether a difference is
    deliberate. Two agents carried full ids until 2026-08-23."""
    m = declared(agent)
    assert m in ALIASES, (
        f"{agent.name} names its model as {m!r}; use one of "
        f"{sorted(ALIASES)} so a difference between two agents always means "
        f"a real difference")


def test_the_overrides_that_exist_are_preserved():
    """The half a careless fix would delete. Twelve agents deliberately run
    opus and one runs haiku; that spread IS the configuration the owner is
    keeping."""
    models = [declared(a) for a in AGENTS]
    assert models.count("opus") >= 10, (
        "the agents that need to reason harder still say so")
    assert "haiku" in models, "and the cheap mechanical one still says so"
    assert models.count("sonnet") > len(models) / 2, (
        "with sonnet the majority, matching the default")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
