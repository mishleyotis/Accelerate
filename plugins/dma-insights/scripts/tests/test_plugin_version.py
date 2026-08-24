"""The version floor reads the install, never a literal.

Owner, 2026-08-23: "The session still references old plugins. Ensure it
checks the installed plugin rather than hardcoding versions."

What made that necessary is pinned here as a fixture: on 2026-08-23 this
container carried dma-insights 0.2.0 (5 agents) while the checkout published
0.8.1 (47), the four routine prompts asserted floors of ">= 0.6.0" and
">= 0.8.0", and every one of them was satisfied by nothing and said nothing.
"""
import json
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import plugin_version as pv  # noqa: E402


@pytest.fixture(autouse=True)
def _no_provisioning_record(tmp_path, monkeypatch):
    """Every test below is about the INSTALL, so provisioning is pinned to a
    known-absent record rather than left to read whatever the machine has.

    Without this the suite reads /root/.dma/provisioning.json, which does not
    exist on a workstation and DOES exist on exactly the containers these
    tests are meant to describe — so the same assertions would exercise two
    different code paths depending on where they ran.
    """
    monkeypatch.setattr(pv, "PROV_FILE", tmp_path / "no-provisioning.json")


def _plugin_tree(plugin_dir: Path, version="0.8.1", agents=47, skills=6):
    """The tree BOTH sides build, so an install and a checkout at the same
    version are byte-identical by construction.

    They used not to be: `_repo` wrote skills and `_state` wrote agents, and
    the tests passed because nothing compared content. Adding the digest made
    every one of them DIVERGED — correctly, and the fixtures were the thing
    that was wrong.
    """
    (plugin_dir / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(json.dumps({
        "name": "dma-insights", "version": version,
        "agents": [f"./agents/a{i}.md" for i in range(agents)]}))
    (plugin_dir / "agents").mkdir(exist_ok=True)
    for i in range(agents):
        (plugin_dir / "agents" / f"a{i}.md").write_text(f"agent {i}\n")
    for i in range(skills):
        (plugin_dir / "skills" / f"s{i}").mkdir(parents=True, exist_ok=True)
        (plugin_dir / "skills" / f"s{i}" / "SKILL.md").write_text(f"skill {i}\n")
    return plugin_dir


def _repo(tmp_path, version="0.8.1", agents=47, market_version=None,
          skills=6):
    root = tmp_path / "repo"
    _plugin_tree(root / "plugins" / "dma-insights", version, agents, skills)
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "zennify-dma",
        "plugins": [{"name": "dma-insights",
                     "version": market_version or version}]}))
    return root


def _state(tmp_path, version="0.8.1", agents=47, scope="user", extra=(),
           skills=6, updated_at=None):
    """An installed_plugins.json plus the cache tree it points at."""
    cache = _plugin_tree(tmp_path / "cache" / str(version), version, agents,
                         skills)
    records = [{"scope": scope, "version": version,
                "installPath": str(cache), "gitCommitSha": "deadbeef"}]
    if updated_at:
        records[0]["lastUpdated"] = updated_at
    records += list(extra)
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"version": 2, "plugins": {
        "dma-insights@zennify-dma": records}}))
    return path


# ── the measured incident ─────────────────────────────────────────────────

def test_the_0_2_0_container_is_caught(tmp_path):
    """The exact state of this machine on 2026-08-23, and the exact reason
    the literal floors could not see it: 0.2.0 is below every floor that was
    written down, and no floor was ever evaluated against anything."""
    v = pv.compare(_repo(tmp_path), _state(tmp_path, "0.2.0", agents=5))
    assert v["status"] == "STALE" and not v["ok"]
    assert "0.2.0" in v["reasons"][0] and "0.8.1" in v["reasons"][0]
    assert "5" in v["reasons"][1] and "47" in v["reasons"][1], (
        "the roster gap is the consequence that matters — a session that "
        "dispatches to 42 agents it does not have fails one subagent at a time")
    assert "claude plugin update" in v["fix"]


def test_nothing_in_the_module_hardcodes_a_version():
    """The point of the exercise. A literal here would be the same defect in
    a new file — every version in play is read from a manifest or the install
    state at call time."""
    source = Path(pv.__file__).read_text()
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#"))
    # Strip docstrings: the incident IS recorded there, in prose, on purpose.
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    assert not re.search(r"""["']\d+\.\d+\.\d+["']""", code), (
        "a version literal in the checker is the bug it exists to catch")


# ── the comparison ────────────────────────────────────────────────────────

def test_a_matching_whole_install_is_ok(tmp_path):
    v = pv.compare(_repo(tmp_path), _state(tmp_path))
    assert v["status"] == "OK" and v["ok"] and not v["fix"]


def test_a_newer_install_names_the_checkout_as_the_stale_half(tmp_path):
    """`git pull`, not `plugin update`. Telling a session to update the
    plugin here would downgrade the only correct half of the pair."""
    v = pv.compare(_repo(tmp_path, "0.8.1"), _state(tmp_path, "0.9.0"))
    assert v["status"] == "AHEAD" and not v["ok"]
    assert "pull the branch" in v["fix"]
    assert "plugin update" not in v["fix"]


def test_same_version_different_content_is_caught(tmp_path):
    """THE VERSION CHECK'S OWN BLIND SPOT, found within an hour of writing it:
    the repo published 0.8.2, the install was 0.8.2, `compare` said OK — and
    three files differed, including the exact rule a vetter agent needed in
    order to stop refusing packages. A number is not content."""
    repo, state = _repo(tmp_path), _state(tmp_path)
    assert pv.compare(repo, state)["status"] == "OK", "identical to start with"
    # Edit the checkout after the version was built, exactly as happened.
    (repo / "plugins" / "dma-insights" / "agents" / "vetter.md").write_text(
        "a rule the install does not carry")
    v = pv.compare(repo, state)
    assert v["status"] == "DIVERGED" and not v["ok"]
    assert "vetter.md" in v["reasons"][0]
    assert "bump the version in BOTH manifests" in v["fix"], (
        "reinstalling without a bump leaves the cache on a version number "
        "that no longer describes its contents")


def test_a_pycache_difference_is_not_divergence(tmp_path):
    """Build artefacts are not plugin content. Counting them would put every
    install permanently in DIVERGED and the status would mean nothing."""
    repo, state = _repo(tmp_path), _state(tmp_path)
    assert pv.compare(repo, state)["status"] == "OK", "same tree, same version"
    cache = repo / "plugins" / "dma-insights" / "scripts" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "x.cpython-311.pyc").write_bytes(b"\x00\x01")
    assert pv.compare(repo, state)["status"] == "OK"


def test_digest_is_none_for_a_tree_that_is_not_there(tmp_path):
    """A missing tree must not hash to the same value as another missing
    tree — that would report two absent plugins as identical."""
    assert pv.digest(tmp_path / "nope") is None


def test_a_missing_digest_never_triggers_divergence(tmp_path, monkeypatch):
    """NOT_INSTALLED and the CLI fallback carry no tree to hash. Comparing
    None to a real digest as 'different' would fail every CI runner."""
    monkeypatch.setattr(pv, "_from_cli", dict)
    v = pv.compare(_repo(tmp_path), tmp_path / "absent.json")
    assert v["status"] == "NOT_INSTALLED" and v["ok"]


def test_a_short_tree_at_the_right_version_is_incomplete(tmp_path):
    """A version number matches while the packaged tree is short — an
    interrupted unpack. The version comparison alone calls this healthy."""
    state = _state(tmp_path, "0.8.1", agents=47)
    cache = json.loads(state.read_text())["plugins"][
        "dma-insights@zennify-dma"][0]["installPath"]
    for stray in list(Path(cache, "agents").glob("a4*.md")):
        stray.unlink()
    v = pv.compare(_repo(tmp_path), state)
    assert v["status"] == "INCOMPLETE" and not v["ok"]
    assert "declares" in v["reasons"][0]


def test_two_manifests_publishing_different_versions_is_reported(tmp_path):
    """An install resolves one of them and nothing says which. Picking one
    here silently is how a plugin ships as two versions."""
    v = pv.compare(_repo(tmp_path, "0.8.1", market_version="0.7.0"),
                   _state(tmp_path, "0.8.1"))
    assert v["status"] == "MANIFEST_SPLIT" and not v["ok"]
    assert "0.8.1" in v["reasons"][0] and "0.7.0" in v["reasons"][0]


# ── the two ways "not installed" can mean opposite things ─────────────────

def test_no_install_state_at_all_is_not_a_failure(tmp_path, monkeypatch):
    """A CI runner and a bare checkout have no state file. There is no drift
    to measure and nothing is wrong — the repo-inventory rows already say
    whether the checkout is whole. Failing here would make the doctor red on
    every CI run for a reason that is not a defect.

    The CLI fallback is stubbed away because THIS machine has a real install:
    without that the test would measure the developer's laptop, which is the
    class of mistake this whole module exists to end."""
    monkeypatch.setattr(pv, "_from_cli", dict)
    v = pv.compare(_repo(tmp_path), tmp_path / "does-not-exist.json")
    assert v["status"] == "NOT_INSTALLED"
    assert v["ok"], "nothing to compare against is not a defect"


def test_the_cli_answers_only_when_there_is_no_state_file(tmp_path,
                                                          monkeypatch):
    """`claude plugin list` is a fallback for a machine with no state file,
    never an override of one. A state file that exists and omits the plugin
    is the defect; letting the CLI answer over it papers that over."""
    monkeypatch.setattr(pv, "_from_cli",
                        lambda: {"version": "9.9.9", "source": "cli"})
    absent = pv.installed(tmp_path / "nope.json")
    assert absent["version"] == "9.9.9"

    present = tmp_path / "installed_plugins.json"
    present.write_text(json.dumps({"version": 2, "plugins": {}}))
    assert pv.installed(present)["version"] is None


def test_a_state_file_that_omits_the_plugin_is_a_failure(tmp_path):
    """The other half. Plugins are installed on this machine and ours is not
    among them — that IS the defect the row exists for."""
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"version": 2, "plugins": {
        "something-else@elsewhere": [{"scope": "user", "version": "1.0.0"}]}}))
    v = pv.compare(_repo(tmp_path), path)
    assert v["status"] == "MISSING" and not v["ok"]


# ── the duplicate a session had to guess about ────────────────────────────

def test_a_shadowed_scope_is_named_rather_than_dropped(tmp_path):
    """Measured 2026-08-23: a routine session found user scope at 0.8.1 and
    project scope at 0.6.2, and spent a paragraph reasoning to "probably a
    stale duplicate record, not what's actually loaded" — a guess, in the one
    place the routine is meant to be certain. The max() still picks
    correctly; what changed is that it says so."""
    state = _state(tmp_path, "0.8.1", extra=[
        {"scope": "project", "version": "0.6.2", "installPath": ""}])
    v = pv.compare(_repo(tmp_path), state)
    assert v["status"] == "OK", "the highest version loads; this is not a defect"
    joined = " ".join(v["reasons"])
    assert "0.6.2" in joined and "project" in joined and "shadowed" in joined


def test_the_highest_version_is_the_one_reported(tmp_path):
    state = _state(tmp_path, "0.8.1", extra=[
        {"scope": "project", "version": "0.6.2", "installPath": ""}])
    assert pv.installed(state)["version"] == "0.8.1"


# ── reading the strings ───────────────────────────────────────────────────

def test_an_unreadable_version_compares_as_unknown_not_as_zero(tmp_path):
    """A sentinel that sorts low would make every unreadable install look
    STALE and send a session into an update loop it cannot win."""
    assert pv._tuple("not-a-version") is None
    assert pv._tuple("") is None
    assert pv._tuple("0.10.0") > pv._tuple("0.9.9"), "numeric, not lexical"


def test_a_repo_with_no_readable_version_says_so(tmp_path):
    root = tmp_path / "repo"
    (root / "plugins" / "dma-insights" / ".claude-plugin").mkdir(parents=True)
    v = pv.compare(root, _state(tmp_path))
    assert v["status"] == "UNREADABLE" and not v["ok"]


def test_summary_is_one_quotable_line(tmp_path):
    line = pv.summary(pv.compare(_repo(tmp_path), _state(tmp_path, "0.2.0",
                                                         agents=5)))
    assert "\n" not in line
    assert "STALE" in line and "0.2.0" in line and "0.8.1" in line


# ── the real repo ─────────────────────────────────────────────────────────

def test_this_checkout_publishes_one_version_in_both_manifests():
    """Guards the MANIFEST_SPLIT case against the live repo rather than a
    fixture: the two files are edited separately and drift silently."""
    pub = pv.published()
    assert pub["version"], "plugins/dma-insights/.claude-plugin/plugin.json"
    assert pub["marketplace_version"] == pub["version"], (
        f"plugin.json publishes {pub['version']}, marketplace.json publishes "
        f"{pub['marketplace_version']}")


def test_the_manifest_agent_list_matches_the_agent_files():
    """`expected_agents` in the doctor derives the count from this list, so
    the list has to be the truth about the tree."""
    root = Path(pv.__file__).resolve().parents[3]
    on_disk = {p.stem for p in (root / "plugins" / "dma-insights" / "agents"
                                ).rglob("*.md") if p.name != "README.md"}
    declared = {Path(a).stem for a in json.loads(
        (root / "plugins" / "dma-insights" / ".claude-plugin" /
         "plugin.json").read_text())["agents"]}
    assert declared == on_disk, (
        f"only in manifest: {sorted(declared - on_disk)}; "
        f"only on disk: {sorted(on_disk - declared)}")


# ── the disk is not the session ───────────────────────────────────────────
#
# Reported by a routine session, 2026-08-23: it ran `claude plugin update`,
# re-ran this check inside the same firing, got OK, and filed the module's own
# guidance — "the update applies at NEXT session start" — as contradicted by
# observation. Both halves were true of different things. The state file and
# the cache tree change immediately, and this script reads exactly those; the
# agents, skills and hooks a session dispatches were bound at session start
# and do not reload. The old note asserted a mechanism; these tests measure
# one.

SESSION_START = "2026-08-23T05:21:19+00:00"
BEFORE, AFTER = "2026-08-23T04:00:00Z", "2026-08-23T08:16:12Z"


def _began(monkeypatch, when=SESSION_START):
    import datetime as dt
    monkeypatch.setattr(pv, "session_started_at",
                        lambda: dt.datetime.fromisoformat(when).timestamp())


def test_an_install_written_after_this_session_started_is_not_ok(
        tmp_path, monkeypatch):
    """The live case, reproduced: on the container that reported this, the
    session process began 05:21:19Z and the install record was last written
    08:16:12Z. The disk is right and the session is running something else,
    and the caller's next act — produce, or end the firing — turns on the
    session, not the disk."""
    _began(monkeypatch)
    v = pv.compare(_repo(tmp_path), _state(tmp_path, updated_at=AFTER))
    assert v["status"] == "UPDATED_MID_SESSION"
    assert not v["ok"], (
        "exit 0 here sends a routine to work on the very agents it was "
        "trying to stop using")
    joined = " ".join(v["reasons"])
    assert AFTER in joined and "05:21:19Z" in joined, (
        "both timestamps, so a reader can check the claim rather than "
        "believe it")


def test_an_install_older_than_the_session_is_plain_ok(tmp_path, monkeypatch):
    """The ordinary path. bootstrap_session.sh installs during environment
    setup, BEFORE the session exists, so the routine's own provisioning must
    not trip this."""
    _began(monkeypatch)
    v = pv.compare(_repo(tmp_path), _state(tmp_path, updated_at=BEFORE))
    assert v["status"] == "OK" and v["ok"]


def test_an_unknown_session_start_judges_neither_way(tmp_path, monkeypatch):
    """No /proc, no CLAUDE_PID — a CI runner, a non-Linux box. An unmeasured
    start time must not manufacture a verdict in either direction; the whole
    point of the correction is to stop asserting this."""
    monkeypatch.setattr(pv, "session_started_at", lambda: None)
    v = pv.compare(_repo(tmp_path), _state(tmp_path, updated_at=AFTER))
    assert v["status"] == "OK" and v["ok"]
    assert pv.installed(_state(tmp_path, updated_at=AFTER)
                        )["loaded_by_this_session"] is None


def test_a_missing_timestamp_judges_neither_way(tmp_path, monkeypatch):
    """The other unknown. A record with no lastUpdated and no installedAt
    carries no answer, and None is the answer."""
    _began(monkeypatch)
    assert pv.installed(_state(tmp_path))["loaded_by_this_session"] is None


def test_a_disk_disagreement_outranks_a_session_disagreement(tmp_path,
                                                              monkeypatch):
    """Ordering, which is load-bearing. A session running a stale tree that
    the DISK also disagrees with needs the disk fixed first — reporting
    UPDATED_MID_SESSION there would name the wrong problem and print the
    wrong fix."""
    _began(monkeypatch)
    v = pv.compare(_repo(tmp_path, "0.8.1"),
                   _state(tmp_path, "0.2.0", agents=5, updated_at=AFTER))
    assert v["status"] == "STALE"
    assert "claude plugin update" in v["fix"]


def test_the_fix_for_a_mid_session_update_installs_nothing(tmp_path,
                                                            monkeypatch):
    """There is nothing to install. Printing the update command again is how
    a session ends up re-running a command that already worked."""
    _began(monkeypatch)
    v = pv.compare(_repo(tmp_path), _state(tmp_path, updated_at=AFTER))
    assert "claude plugin update" not in v["fix"]
    assert "end the firing" in v["fix"]


def test_the_update_note_no_longer_claims_the_recheck_is_pointless():
    """The sentence that was wrong. The re-check DOES work in the same
    firing — it reads the disk at call time — and the note now says which
    half of the question that answers."""
    note = pv.UPDATE_NOTE
    assert "NEXT session start" not in note, (
        "the corrected claim: the state file and cache change immediately")
    assert "same firing" in note and "session start" in note
    assert "DISK" in note


def test_session_start_is_read_from_the_process_not_guessed(monkeypatch):
    """A wrong-but-plausible implementation is `time.time() - something`.
    /proc/<pid> is created with the process, so its ctime IS the start."""
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    assert pv.session_started_at() is None
    monkeypatch.setenv("CLAUDE_PID", "not-a-pid")
    assert pv.session_started_at() is None
    monkeypatch.setenv("CLAUDE_PID", "999999999")
    assert pv.session_started_at() is None, "a pid that does not exist"


# ── why the drift happened, and whether the next firing will differ ───────
#
# THE LIVELOCK, reported by two synthesis lanes on 2026-08-24. Every routine's
# STEP 0 answers UPDATED_MID_SESSION with "end the firing, the next one picks
# it up". That is true of a one-off and false of a container that reproduces
# the state, and nothing could tell the two apart — so the lanes ended every
# firing with a clean report and produced no client at all. These pin the
# distinction the report needs to make.

def _prov(tmp_path, **fields):
    rec = {"bootstrap_ran_at": "2026-08-24T09:11:02Z",
           "repo_dir": "/home/user/Accelerate",
           "branch": "claude/dma-insights-onboarding-0ryrd0",
           "checkout_current": True, "checkout_state": "reset",
           "checkout_note": "", "plugin_installed": "0.8.1",
           "plugin_expected": "0.8.1"}
    rec.update(fields)
    path = tmp_path / "provisioning.json"
    path.write_text(json.dumps(rec))
    return path


def test_an_absent_record_with_nothing_beside_it_means_it_did_not_run(tmp_path):
    p = pv.provisioning(tmp_path / "nothing-here.json")
    assert p["state"] == "not_run"
    assert p["recurs"] is True
    assert "did not run" in p["reason"]
    assert "bootstrap_session.sh" in p["fix"]


def test_an_absent_record_beside_a_landed_key_says_it_ran_and_was_old(tmp_path):
    """The setup script lands the key and the path token beside this record.
    Key present + record absent means it RAN, from a revision built before it
    wrote one — reporting that as "did not run" sends someone to check a
    setting that is already correct, which is the same class of mistake as
    the loop this diagnosis exists to break."""
    (tmp_path / "sa.json").write_text("{}")
    p = pv.provisioning(tmp_path / "nothing-here.json")
    assert p["state"] == "not_run"
    assert p["recurs"] is True
    assert "DID run" in p["reason"]
    assert "did not run" not in p["reason"]
    assert "re-point" in p["fix"]


def test_a_stale_checkout_is_named_as_the_cause(tmp_path):
    """The checkout IS the marketplace, so a checkout left off the branch
    installs an old plugin on purpose."""
    p = pv.provisioning(_prov(tmp_path, checkout_current=False,
                              checkout_state="dirty",
                              checkout_note="local modifications"))
    assert p["state"] == "stale_checkout"
    assert p["recurs"] is True
    assert "origin/claude/dma-insights-onboarding-0ryrd0" in p["fix"]


def test_a_healthy_record_does_not_claim_recurrence(tmp_path):
    p = pv.provisioning(_prov(tmp_path))
    assert p["state"] == "ok"
    assert p["recurs"] is False
    assert p["fix"] == ""


def test_a_recurring_cause_says_ending_the_firing_will_not_fix_it(tmp_path):
    """The sentence the routines were missing."""
    v = pv.compare(_repo(tmp_path), _state(tmp_path, "0.2.0", agents=5),
                   tmp_path / "nothing-here.json")
    assert v["status"] == "STALE"
    joined = " ".join(v["reasons"])
    assert "ENDING THE FIRING WILL NOT FIX THIS" in joined
    assert v["provisioning"]["recurs"] is True


def test_a_one_off_is_not_dressed_up_as_a_provisioning_defect(tmp_path):
    """A correctly provisioned container that still drifts is a NEW fact, and
    ending the firing really is the right answer there. Crying provisioning
    at it would send someone to fix a setting that is already correct."""
    v = pv.compare(_repo(tmp_path), _state(tmp_path, "0.2.0", agents=5),
                   _prov(tmp_path))
    assert v["status"] == "STALE"
    joined = " ".join(v["reasons"])
    assert "ENDING THE FIRING WILL NOT FIX THIS" not in joined
    assert v["provisioning"]["recurs"] is False


def test_a_healthy_install_is_not_narrated(tmp_path):
    """No provisioning commentary on an OK verdict: a check that explains a
    working machine every time teaches its reader to skim it."""
    v = pv.compare(_repo(tmp_path), _state(tmp_path),
                   tmp_path / "nothing-here.json")
    assert v["status"] == "OK"
    assert not any("cause:" in r for r in v["reasons"])


def test_the_root_cause_line_is_printed_separately(tmp_path, capsys):
    """It addresses whoever owns the environment, not the session, and it was
    unreadable folded into `fix` behind nested parentheses."""
    pv.main(["--repo-root", str(_repo(tmp_path)),
             "--state", str(_state(tmp_path, "0.2.0", agents=5)),
             "--provisioning", str(tmp_path / "nothing-here.json")])
    out = capsys.readouterr().out
    assert "=> ROOT CAUSE, RECURS EVERY FIRING:" in out
    assert out.count("=> ROOT CAUSE") == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
