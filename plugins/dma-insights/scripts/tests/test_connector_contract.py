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


# ── a connector lost mid-session ──────────────────────────────────────────
#
# Owner, 2026-08-31: "The connectors may be lost mid session even after being
# attached. How do we safeguard against this?" A session cannot re-attach one
# — they bind at start — so the safeguard is not recovery, it is TELLING THE
# TWO CASES APART, because they call for opposite responses:
#
#   never had it    -> a preflight stop; nothing is researched yet
#   had it, lost it -> not a stop. Prior work stands; everything after must
#                      record NOT_RUN with the loss as its reason, because a
#                      dead connector and an empty world read identically in
#                      a payload and mean opposite things.
#
# A check alone cannot see the difference. Only a baseline can.

def _tools(*families):
    fam = cc.families()
    return [fam[f][0] for f in families]


def test_a_baseline_records_what_the_session_actually_held(tmp_path):
    rec = cc.write_baseline(_tools("exa", "tavily", "clay"), tmp_path)
    assert sorted(rec["present"]) == ["clay", "exa", "tavily"]
    assert cc.baseline_path(tmp_path).is_file()
    assert rec["recorded_at"], "a baseline with no time cannot date a loss"


def test_a_lost_required_connector_is_degraded_and_not_ok(tmp_path):
    cc.write_baseline(_tools("exa", "tavily", "clay"), tmp_path)
    out = cc.probe(_tools("exa", "tavily"), tmp_path)
    assert out["verdict"] == "DEGRADED" and not out["ok"]
    assert out["lost"] == ["clay"] and out["lost_required"] == ["clay"]
    assert "NOT_RUN" in out["why"], (
        "a loss the payload cannot distinguish from an absence of evidence "
        "is the defect this exists to prevent")


def test_a_lost_optional_connector_degrades_without_stopping(tmp_path):
    """Quartr going away is worth recording and not worth abandoning a run
    for: the facets it answers become honest NOT_RUNs."""
    cc.write_baseline(_tools("exa", "tavily", "clay", "quartr"), tmp_path)
    out = cc.probe(_tools("exa", "tavily", "clay"), tmp_path)
    assert out["verdict"] == "DEGRADED"
    assert out["ok"], "an optional family is not a required one"
    assert out["lost"] == ["quartr"] and not out["lost_required"]


def test_an_unchanged_session_is_stable(tmp_path):
    held = _tools("exa", "tavily", "clay")
    cc.write_baseline(held, tmp_path)
    out = cc.probe(held, tmp_path)
    assert out["verdict"] == "STABLE" and out["ok"] and not out["lost"]


def test_a_connector_that_comes_back_is_named_as_recovered(tmp_path):
    cc.write_baseline(_tools("exa", "tavily"), tmp_path)
    out = cc.probe(_tools("exa", "tavily", "clay"), tmp_path)
    assert out["verdict"] == "RECOVERED" and out["regained"] == ["clay"]
    assert out["ok"]


def test_probing_without_a_baseline_refuses_rather_than_guessing(tmp_path):
    """The whole point is the comparison. Answering 'nothing lost' from no
    baseline would report the safest-sounding thing and mean nothing."""
    with pytest.raises(cc.ContractBroken) as e:
        cc.probe(_tools("exa"), tmp_path)
    assert "no connector baseline" in str(e.value)


def test_the_baseline_is_run_scoped_not_container_scoped(tmp_path):
    """Two runs in one container are two sessions with two rosters. A shared
    file would have the second overwrite the first's evidence."""
    a, b = tmp_path / "run-a", tmp_path / "run-b"
    cc.write_baseline(_tools("exa", "tavily", "clay"), a)
    cc.write_baseline(_tools("exa", "tavily"), b)
    assert cc.probe(_tools("exa", "tavily", "clay"), a)["verdict"] == "STABLE"
    assert cc.probe(_tools("exa", "tavily", "clay"), b)["verdict"] == "RECOVERED"


def test_the_probe_cli_separates_a_loss_from_a_broken_contract(tmp_path):
    def run(cmd, stdin, *args):
        return subprocess.run(
            [sys.executable, str(HERE / "connector_contract.py"), cmd,
             "--tools", "-", "--root", str(tmp_path), *args],
            input=stdin, capture_output=True, text=True, timeout=60)

    full = "\n".join(_tools("exa", "tavily", "clay"))
    assert run("baseline", full).returncode == 0
    assert run("probe", full, "--strict").returncode == 0
    lost = run("probe", "\n".join(_tools("exa", "tavily")), "--strict")
    assert lost.returncode == 1 and "DEGRADED" in lost.stdout
    # 2 is reserved for a contract that cannot be evaluated at all
    missing = subprocess.run(
        [sys.executable, str(HERE / "connector_contract.py"), "probe",
         "--tools", "-", "--root", str(tmp_path / "never")],
        input=full, capture_output=True, text=True, timeout=60)
    assert missing.returncode == 2 and "CONTRACT BROKEN" in missing.stderr
