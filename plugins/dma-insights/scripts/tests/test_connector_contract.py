"""Which connectors a firing may be STOPPED for, and where that answer comes from.

THE INCIDENT THESE PIN. On 2026-08-31 the intake Routine's connector
preflight was given a hand-typed list: "Exa, Tavily, Firecrawl, Clay and
Vibe-Prospecting", every one of them a hard STOP. Firecrawl appears in no
agent's `tools:` line, in no role in `scripts/provision_agent_tools.py`, and
nowhere in `docs/CONNECTORS.md`. The pipeline cannot call it. So the gate
would have stopped every firing, permanently, on a connector that does not
exist here — and nothing would have caught it, because a requirement written
as prose is never compared to anything.

The cure is that the requirement is DERIVED from the registry the agents are
provisioned from, and these tests are what make the derivation load-bearing:
they fail if somebody re-types the list, and they fail if a required family
stops being one the agents can actually call.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import connector_contract as cc  # noqa: E402


def test_the_registry_is_the_repo_s_own_and_not_a_second_copy():
    """`families()` reads EXTERNAL out of scripts/provision_agent_tools.py.
    A second declaration here would be a second answer, and the two would
    disagree the first time either moved."""
    assert cc._PROVISIONER.name == "provision_agent_tools.py"
    assert cc._PROVISIONER.is_file(), cc._PROVISIONER
    fam = cc.families()
    assert fam and all(isinstance(v, (list, tuple)) for v in fam.values())
    src = cc._PROVISIONER.read_text()
    for name in fam:
        assert f'"{name}"' in src or f"'{name}'" in src


def test_every_required_family_is_one_the_agents_can_actually_call():
    """THE FIRECRAWL TEST. A family named here and absent from EXTERNAL is a
    stop nobody can satisfy, so `contract()` refuses to produce one."""
    c = cc.contract()
    fam = cc.families()
    for name in c["required"] + [n for g in c["required_any"] for n in g]:
        assert name in fam, (
            f"{name} is required but no agent is provisioned with it")


def test_a_required_family_that_left_the_registry_breaks_loudly(monkeypatch):
    """And breaks as a REPO defect (exit 2), never as a session's failure:
    no firing should read 'you are missing firecrawl' when the truth is that
    the repo asked for something it does not define."""
    monkeypatch.setattr(cc, "REQUIRED", ("exa", "firecrawl"))
    with pytest.raises(cc.ContractBroken) as e:
        cc.contract()
    assert "firecrawl" in str(e.value)
    assert "add it to the registry first" in str(e.value)


def test_nothing_in_this_module_hardcodes_firecrawl():
    """The name that caused it, kept out by test rather than by memory."""
    body = Path(cc.__file__).read_text()
    decl = body[body.index("REQUIRED: tuple"):body.index("class ContractBroken")]
    assert "firecrawl" not in decl.lower()


def test_a_family_answers_when_any_one_of_its_tools_is_bound():
    """Any, not all: a connector can expose a subset and still do the work,
    and demanding the full list turns a working session into a stop."""
    fam = cc.families()
    one = fam["exa"][0]
    out = cc.check([one, fam["tavily"][0], fam["clay"][0]], now_families=fam)
    assert out["ok"] and "exa" in out["present"]


def test_a_missing_required_family_stops_and_says_which():
    fam = cc.families()
    out = cc.check([fam["exa"][0], fam["clay"][0]], now_families=fam)
    assert not out["ok"] and out["verdict"] == "STOP"
    assert "tavily" in out["missing"]
    assert "routines UI" in out["why"], "name the fix, not just the fault"


def test_either_half_of_the_firmographic_pair_satisfies_it():
    """Explorium and Clay answer the same question. Requiring both would stop
    a firing that could do the work."""
    fam = cc.families()
    base = [fam["exa"][0], fam["tavily"][0]]
    assert cc.check(base + [fam["clay"][0]], now_families=fam)["ok"]
    assert cc.check(base + [fam["explorium"][0]], now_families=fam)["ok"]
    out = cc.check(base, now_families=fam)
    assert not out["ok"] and "explorium or clay" in out["missing"]


def test_an_absent_optional_family_is_an_honest_absence_not_a_stop():
    """It becomes NOT_RUN with a reason in the enrichment ledger. Silently
    thinning the result instead is the defect the ledger exists to prevent."""
    fam = cc.families()
    out = cc.check([fam["exa"][0], fam["tavily"][0], fam["clay"][0]],
                   now_families=fam)
    assert out["ok"]
    assert "quartr" in out["optional_absent"]
    assert "NOT_RUN" in out["note_on_absent_optional"]


def test_an_empty_tool_list_never_reports_a_pass():
    """`--check` reads the caller's bound tools and cannot guess them. A
    session that supplies nothing must not be told it is ready."""
    assert not cc.check([])["ok"]
    assert not cc.check(["", "  "])["ok"]


def test_the_cli_exit_codes_separate_a_repo_defect_from_a_session_gap():
    """0 ready · 1 a session is short a connector · 2 the contract itself is
    unusable. A firing that cannot tell 1 from 2 blames the wrong thing."""
    def run(stdin, *args):
        return subprocess.run(
            [sys.executable, str(HERE / "connector_contract.py"), "check",
             "--tools", "-", *args],
            input=stdin, capture_output=True, text=True, timeout=60)

    fam = cc.families()
    ready = "\n".join([fam["exa"][0], fam["tavily"][0], fam["clay"][0]])
    assert run(ready, "--strict").returncode == 0
    short = run(fam["exa"][0], "--strict")
    assert short.returncode == 1 and "STOP" in short.stdout
    # without --strict a short session still reports, so a firing can quote
    # the verdict without the exit code deciding for it
    assert run(fam["exa"][0]).returncode == 0


def test_declare_prints_the_derivation_and_json_round_trips():
    out = subprocess.run(
        [sys.executable, str(HERE / "connector_contract.py"), "declare",
         "--json"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    c = json.loads(out.stdout)
    assert c["required"] and c["required_any"]
    human = subprocess.run(
        [sys.executable, str(HERE / "connector_contract.py"), "declare"],
        capture_output=True, text=True, timeout=60).stdout
    assert "provision_agent_tools.py" in human, (
        "the output must name where the answer came from, so a reader can "
        "check it rather than believe it")
