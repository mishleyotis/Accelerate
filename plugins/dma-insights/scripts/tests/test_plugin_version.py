"""The version floor reads the install, never a literal.

Owner, 2026-08-23: "The session still references old plugins. Ensure it
checks the installed plugin rather than hardcoding versions."

What made that necessary is pinned here as a fixture: on 2026-08-23 this
container carried dma-insights 0.2.0 (5 agents) while the checkout published
0.8.1 (47), the four routine prompts asserted floors of ">= 0.6.0" and
">= 0.8.0", and every one of them was satisfied by nothing and said nothing.
"""
import json
import os
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
    # THE BIND IS PINNED UNMEASURED, and this pin is the one that bit first.
    # `bound_root()` reads the REAL session this suite runs in — the
    # connector process spawned by the session's own pid — so, run from
    # inside a Claude Code session, every fixture below was overridden by
    # the live checkout the session had actually bound (26 failures,
    # 2026-09-16). The tests that are ABOUT measuring the bind unpin it.
    monkeypatch.setattr(pv, "bound_root", lambda session_pid=None: {
        "path": None, "source": None,
        "reason": "pinned unmeasured by the test fixture"})
    monkeypatch.setattr(pv, "BOUND_DIR", tmp_path / "bound")
    # ENABLEMENT IS PINNED FOR THE SAME REASON. `enabled_state()` reads the
    # real settings.json, so without this a suite about installs would answer
    # DISABLED or not depending on whether the machine running it happens to
    # have the plugin switched on. The tests that are ABOUT enablement point
    # it back at fixtures of their own.
    monkeypatch.setattr(pv, "SETTINGS_FILES", (tmp_path / "no-settings.json",))


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
    # The fix must say BOTH things, and it did not always. It used to
    # prescribe only the version bump — correct as durable advice and useless
    # to a firing that cannot edit the repo. It now leads with the
    # container-local repair (measured to work) and still names the bump,
    # because reinstalling without one leaves the cache on a version number
    # that no longer describes its contents.
    assert "uninstall" in v["fix"], (
        "an update is a no-op on an equal version number — measured")
    assert "bump it in BOTH manifests" in v["fix"]


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
    assert "same firing" in note
    assert "DISK" in note
    assert "--heal" in note, "the note must offer the self-healing path"


# ── the script's own guidance must prescribe production, never an ending ──
#
# Measured 2026-08-24 ~14:00Z, the third distinct stop in one day on the same
# verdict: a firing whose PROMPT said to produce trusted this script's
# freshly-read output over the stored prompt — reasonably; a prompt can be
# stale or manipulated and this file cannot — and this file still said "end
# the firing; the next session picks it up". The prompt fix moved the
# contradiction instead of removing it. These pins make every written
# authority say the same thing.

def test_the_mid_session_guidance_prescribes_recovery_mode():
    note = pv.SESSION_NOTE
    assert "RECOVERY MODE" in note
    assert "agent_run.py" in note, (
        "the productive path must be named IN the script's own output — a "
        "session that trusts only this file must still learn how to produce")


def test_no_note_tells_a_session_to_end_the_firing():
    """The exact sentence three firings died on, banned from both notes.
    The historical quotation of it is allowed; the instruction is not."""
    for name in ("UPDATE_NOTE", "SESSION_NOTE"):
        note = getattr(pv, name)
        head, _, tail = note.partition("(Until 2026-08-24")
        assert "end the firing" not in head.lower(), (
            f"{name} instructs ending the firing outside the historical "
            f"quotation — that is the sentence that killed three firings")


def test_heal_is_a_noop_on_verdicts_an_update_cannot_change():
    """--heal must never run installs on OK / UPDATED_MID_SESSION /
    AHEAD — an update there is at best pointless and at worst a downgrade."""
    for status in ("OK", "UPDATED_MID_SESSION", "AHEAD", "NOT_INSTALLED"):
        v, log = pv.heal({"status": status})
        assert v == {"status": status} and log == [], status


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
    # FRESH BY DEFAULT, and it used to be a hardcoded date. Once
    # `provisioning()` learned to read the record's AGE — a record hours old
    # means setup ran at snapshot-build time and is not re-running per
    # session — a literal timestamp made every fixture a stale snapshot the
    # moment the calendar passed it. A fixture that ages into a different
    # verdict tests something other than what it says. Tests that want an
    # OLD record now pass one explicitly.
    import datetime as _d
    _now = _d.datetime.now(_d.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = {"bootstrap_ran_at": _now,
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


def test_an_install_that_would_not_take_is_its_own_cause(tmp_path):
    """The setup script ran, the checkout was current, and the install STILL
    came out behind. That is neither "it did not run" nor "the checkout was
    stale", and telling a reader either one sends them to the wrong place."""
    p = pv.provisioning(_prov(tmp_path, plugin_installed="0.6.2",
                              plugin_expected="0.9.8"))
    assert p["state"] == "stale_install"
    assert p["recurs"] is True
    assert "0.6.2" in p["reason"] and "0.9.8" in p["reason"]


def test_a_stale_install_outranks_a_stale_checkout(tmp_path):
    """Both can be true at once. The install is the more specific fact — it
    names the version the session actually bound — so it is reported."""
    p = pv.provisioning(_prov(tmp_path, checkout_current=False,
                              plugin_installed="0.6.2",
                              plugin_expected="0.9.8"))
    assert p["state"] == "stale_install"


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


# ── enablement: installed, current, and loading nothing ───────────────────
#
# MEASURED 2026-08-31 on a live container. `claude plugin install` prints
# "This plugin is disabled by default — enable it with: claude plugin enable"
# and the install record carries no flag saying so. So a heal that installed
# and stopped there left the container holding a complete, current plugin
# that loaded none of it — and every check that read only
# installed_plugins.json called that OK.

def _settings(tmp_path, value, name="settings.json"):
    path = tmp_path / name
    path.write_text(json.dumps(
        {"enabledPlugins": {"dma-insights@zennify-dma": value}}
        if value is not None else {}))
    return path


def test_a_switched_off_plugin_is_not_ok(tmp_path, monkeypatch):
    repo, state = _repo(tmp_path), _state(tmp_path)
    monkeypatch.setattr(pv, "SETTINGS_FILES", (_settings(tmp_path, False),))
    v = pv.compare(repo, state)
    assert v["status"] == "DISABLED" and not v["ok"]
    assert "enable" in v["fix"]
    assert "loads none of its" in " ".join(v["reasons"])


def test_an_enabled_plugin_at_the_right_version_is_ok(tmp_path, monkeypatch):
    repo, state = _repo(tmp_path), _state(tmp_path)
    monkeypatch.setattr(pv, "SETTINGS_FILES", (_settings(tmp_path, True),))
    assert pv.compare(repo, state)["status"] == "OK"


def test_no_settings_file_is_not_read_as_disabled(tmp_path, monkeypatch):
    """A CI runner and a bare checkout have no settings.json. Manufacturing
    DISABLED out of that would red-flag every machine that is simply not a
    Claude Code container."""
    repo, state = _repo(tmp_path), _state(tmp_path)
    monkeypatch.setattr(pv, "SETTINGS_FILES", (tmp_path / "absent.json",))
    assert pv.enabled_state((tmp_path / "absent.json",)) is None
    assert pv.compare(repo, state)["status"] == "OK"


def test_enabled_at_either_scope_is_enough(tmp_path):
    """User and project scope both register the plugin, and the session loads
    from whichever carries it. True anywhere wins over False elsewhere."""
    off = _settings(tmp_path, False, "off.json")
    on = _settings(tmp_path, True, "on.json")
    assert pv.enabled_state((off, on)) is True
    assert pv.enabled_state((on, off)) is True
    assert pv.enabled_state((off,)) is False


def test_a_wrong_tree_is_reported_before_a_switched_off_one(tmp_path,
                                                            monkeypatch):
    """Both wrong at once: the tree is named, because its repair (uninstall,
    install, enable) fixes the enablement on the way out, while enabling a
    stale tree fixes nothing."""
    repo = _repo(tmp_path, version="0.9.0")
    state = _state(tmp_path, version="0.8.1")
    monkeypatch.setattr(pv, "SETTINGS_FILES", (_settings(tmp_path, False),))
    assert pv.compare(repo, state)["status"] == "STALE"


# ── the heal plans, and why they are not one plan ─────────────────────────

def test_every_heal_path_ends_by_enabling_the_plugin():
    """The measured defect this table exists for: an install lands the plugin
    disabled, so a plan that installs and stops leaves a container loading
    nothing. Every plan therefore ends in `enable` — including DISABLED's,
    which is only that."""
    for status in ("STALE", "MISSING", "INCOMPLETE", "DIVERGED", "DISABLED"):
        plan = pv._plan_for({"status": status, "installed": {}})
        assert plan, status
        assert plan[-1][:3] == ["claude", "plugin", "enable"], status


def test_a_diverged_tree_is_reinstalled_and_never_merely_updated():
    """MEASURED 2026-08-31, and the whole reason this is a table rather than
    one command list: with the checkout and the install both at 1.13.0 and
    their trees differing, `plugin update` answered 'already at the latest
    version' and `plugin install` answered 'already installed' — both exit 0,
    neither copying a byte. Only an uninstall first replaced the tree."""
    plan = pv._plan_for({"status": "DIVERGED", "installed": {}})
    verbs = [c[2] for c in plan if c[1] == "plugin"]
    assert "uninstall" in verbs, "an update cannot reconcile an equal version"
    assert verbs.index("uninstall") < verbs.index("install")
    assert "update" not in verbs


def test_the_stale_plan_updates_rather_than_uninstalling():
    """A version bump is what `update` is for, and uninstalling to get it
    would throw away a working install to solve a problem it does not have."""
    verbs = [c[2] for c in pv._plan_for({"status": "STALE", "installed": {}})
             if c[1] == "plugin"]
    assert "update" in verbs and "uninstall" not in verbs


def test_every_heal_command_pins_the_user_scope(tmp_path):
    """MEASURED: `install --scope project` records `projectPath` as the
    CURRENT WORKING DIRECTORY, so a repair run from anywhere but the repo
    root writes a third, wrong registration. All scopes share one cache
    directory keyed by version, so user scope releases the tree the project
    record points at too. A repair must not depend on where it was invoked."""
    for status in ("STALE", "DIVERGED", "DISABLED"):
        for argv in pv._plan_for({"status": status,
                                  "installed": {"scope": "project"}}):
            if "--scope" in argv:
                assert argv[argv.index("--scope") + 1] == "user", (status, argv)


def test_the_diverged_fix_text_names_the_command_that_works():
    """The fix line used to prescribe UPDATE, which is the command measured
    NOT to reconcile a diverged tree. A fix that cannot fix is worse than
    none: it spends the firing and reports success."""
    assert "uninstall" in pv.REINSTALL
    assert pv.REINSTALL.endswith(pv.ENABLE), (
        "a reinstall that does not re-enable leaves the plugin switched off")


# ── the snapshot that provisions once and is restored for days ────────────
#
# OWNER, 2026-08-31: "I keep on getting this." The recurrence is the point.
# `ok` said the setup script ran, brought the checkout to the tip and
# installed what it expected — all true, and all true LAST TIME IT RAN. It
# said nothing about when. Measured: one firing's record was stamped
# 2026-08-27, four days before it fired; this container's was 17.8 hours
# old. Setup runs when the environment SNAPSHOT is built, not at session
# start, so every session on that image inherits the plugin that was current
# whenever setup last ran — the roster binds short, --heal fixes the disk
# too late, and the firing falls back to agent_run.py, which is why nothing
# appears in the agent panel.

def test_a_provisioning_record_hours_old_is_a_restored_snapshot(tmp_path):
    import datetime as _d
    old = (_d.datetime.now(_d.timezone.utc)
           - _d.timedelta(hours=18)).strftime("%Y-%m-%dT%H:%M:%SZ")
    prov = _prov(tmp_path, bootstrap_ran_at=old)
    out = pv.provisioning(prov)
    assert out["state"] == "stale_snapshot"
    assert out["recurs"] is True, (
        "a snapshot reproduces this on every session; reporting it as a "
        "one-off is the livelock this function exists to name")
    assert 17 <= out["age_hours"] <= 19


def test_a_freshly_provisioned_container_is_still_ok(tmp_path):
    """Setup that runs per session leaves a record minutes old."""
    import datetime as _d
    fresh = (_d.datetime.now(_d.timezone.utc)
             - _d.timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = pv.provisioning(_prov(tmp_path, bootstrap_ran_at=fresh))
    assert out["state"] == "ok" and out["recurs"] is False


def test_the_fix_names_a_setting_that_exists(tmp_path):
    """--heal repairs the DISK and the session has already bound its roster,
    so prescribing it again would prescribe paying the same cost forever.

    And the fix must be REACHABLE. For two weeks this line said "run the
    setup script at SESSION START ... the setup script must execute on each
    session" — a setting Claude Code on the web does not offer: the setup
    script runs once, the filesystem is snapshotted, and the snapshot is
    reused until the script or the allowed hosts change or about seven days
    pass (docs, cloud-environments § Environment caching). Whoever owned the
    environment was sent to change a setting that does not exist."""
    import datetime as _d
    old = (_d.datetime.now(_d.timezone.utc)
           - _d.timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fix = pv.provisioning(_prov(tmp_path, bootstrap_ran_at=old))["fix"]
    assert "ONCE per environment snapshot" in fix
    assert "DIRECTORY source" in fix and "rebuild the snapshot" in fix
    assert "must execute on each session" not in fix
    assert "SESSION START" not in fix


def test_a_stale_snapshot_says_a_fresh_session_will_not_fix_it(tmp_path):
    """The correction that matters operationally: the staleness is in the
    IMAGE, not the session, so a new session on the same image binds the
    same short roster."""
    import datetime as _d
    old = (_d.datetime.now(_d.timezone.utc)
           - _d.timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    why = pv.provisioning(_prov(tmp_path, bootstrap_ran_at=old))["reason"]
    assert "fresh session" in why and "does not fix it" in why


def test_an_unreadable_timestamp_does_not_manufacture_a_verdict(tmp_path):
    assert pv.provisioning_age_h({}) is None
    assert pv.provisioning_age_h({"bootstrap_ran_at": "not a date"}) is None
    out = pv.provisioning(_prov(tmp_path, bootstrap_ran_at="not a date"))
    assert out["state"] == "ok", "no timestamp is not evidence of staleness"


# ── the bind is MEASURED, never read off the install record ───────────────
#
# THE DEFECT THAT REWROTE `installed()`, measured 2026-09-16 on a cloud
# container (Claude Code 2.1.273). `installed_plugins.json`, restored from a
# five-day-old snapshot, recorded 1.19.0 at the cache path (73 agents); the
# checkout published 1.20.0 (74). Everything read the record: STALE at the
# SessionStart hook, research and scoring REFUSED, `--heal` run, then
# UPDATED_MID_SESSION and a firing in RECOVERY MODE. The session's own
# connector process carried CLAUDE_PLUGIN_ROOT=<checkout>/plugins/dma-insights
# — it had bound the checkout in place, all 74 agents, from its first turn.
# Every verdict was about a tree the session was not running.

#: Captured at import, before any test's autouse pin replaces it.
_real_bound_root = pv.bound_root


def _unpin_bind(monkeypatch):
    monkeypatch.setattr(pv, "bound_root", _real_bound_root)


def _measured(path, source="process"):
    return lambda session_pid=None: {"path": str(path), "source": source,
                                     "reason": "test"}


def test_a_session_that_binds_the_checkout_in_place_is_ok_despite_a_stale_record(
        tmp_path, monkeypatch):
    """The live incident, reproduced: record 1.19.0, checkout 1.20.0, and the
    session binds the checkout. OK — and the record's lag is named as
    cosmetic, so nobody heals what nothing runs."""
    repo = _repo(tmp_path, "1.20.0", agents=74)
    state = _state(tmp_path, "1.19.0", agents=73)
    # the fixture tree was written a moment ago; the session under test
    # starts after it, as a real session starts after its clone
    import time as _t
    monkeypatch.setattr(pv, "session_started_at", lambda: _t.time() + 10)
    monkeypatch.setattr(pv, "bound_root",
                        _measured(repo / "plugins" / "dma-insights"))
    v = pv.compare(repo, state)
    assert v["status"] == "OK" and v["ok"], v["reasons"]
    inst = v["installed"]
    assert inst["in_place"] is True
    assert inst["version"] == "1.20.0" and inst["agents"] == 74
    assert inst["record_version"] == "1.19.0"
    joined = " ".join(v["reasons"])
    assert "MEASURED BIND" in joined and "cosmetic" in joined
    assert "1.19.0" in joined, "the lagging record is named, not hidden"
    assert v["fix"] == "", "nothing to heal: the record's copy is not run"
    assert pv.heal(v) == (v, []), "--heal must not touch an OK verdict"
    line = pv.summary(v)
    assert line.startswith("OK: installed 1.20.0 (74 agents)")
    assert "bound in place" in line and "1.19.0 (cosmetic)" in line


def test_a_record_that_lags_is_never_called_updated_mid_session(tmp_path,
                                                                 monkeypatch):
    """The heal's own aftermath. `claude plugin update` rewrites the record
    AFTER the session started; the old code compared that timestamp to the
    session start and said UPDATED_MID_SESSION — RECOVERY MODE — for a
    session whose bound tree had not moved at all."""
    import datetime as dt
    repo = _repo(tmp_path, "1.20.0", agents=74)
    began = dt.datetime.fromisoformat("2026-09-16T02:36:50+00:00").timestamp()
    monkeypatch.setattr(pv, "session_started_at", lambda: began)
    tree = repo / "plugins" / "dma-insights"
    # the checkout was cloned just BEFORE the session existed
    for f in tree.rglob("*"):
        os.utime(f, (began - 0.05, began - 0.05))
    state = _state(tmp_path, "1.20.0", agents=74,
                   updated_at="2026-09-16T02:41:00Z")     # the heal, later
    monkeypatch.setattr(pv, "bound_root", _measured(tree))
    v = pv.compare(repo, state)
    assert v["status"] == "OK", v["reasons"]
    assert v["installed"]["loaded_by_this_session"] is True


def test_a_bound_checkout_that_moved_under_the_session_is_caught(tmp_path,
                                                                  monkeypatch):
    """The genuine mid-session case for an in-place bind: a pull rewrites an
    agent file minutes after the session began. Agents bind once, so this
    IS recovery mode — named for the tree it is about."""
    import datetime as dt
    repo = _repo(tmp_path, "1.20.0", agents=74)
    began = dt.datetime.fromisoformat("2026-09-16T02:36:50+00:00").timestamp()
    monkeypatch.setattr(pv, "session_started_at", lambda: began)
    tree = repo / "plugins" / "dma-insights"
    for f in tree.rglob("*"):
        os.utime(f, (began - 1, began - 1))
    os.utime(tree / "agents" / "a3.md", (began + 300, began + 300))
    monkeypatch.setattr(pv, "bound_root", _measured(tree))
    v = pv.compare(repo, _state(tmp_path, "1.20.0", agents=74))
    assert v["status"] == "UPDATED_MID_SESSION" and not v["ok"]
    joined = " ".join(v["reasons"])
    assert "in place" in joined and str(tree) in joined
    assert "RECOVERY MODE" in v["fix"]


def test_a_write_to_a_script_is_not_a_mid_session_rebind(tmp_path, monkeypatch):
    """Scripts are read when invoked; only the components read ONCE count.
    A checkout is written to constantly (`__pycache__`, a run log, a test
    fixture) and none of that moves the roster."""
    import datetime as dt
    repo = _repo(tmp_path, "1.20.0", agents=74)
    began = dt.datetime.fromisoformat("2026-09-16T02:36:50+00:00").timestamp()
    monkeypatch.setattr(pv, "session_started_at", lambda: began)
    tree = repo / "plugins" / "dma-insights"
    for f in tree.rglob("*"):
        os.utime(f, (began - 1, began - 1))
    (tree / "scripts").mkdir(exist_ok=True)
    (tree / "scripts" / "doctor.py").write_text("# edited mid-session\n")
    (tree / "scripts" / "__pycache__").mkdir(exist_ok=True)
    (tree / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"\0")
    (tree / "skills" / "s0" / "notes.md").write_text("a skill's own notes\n")
    monkeypatch.setattr(pv, "bound_root", _measured(tree))
    v = pv.compare(repo, _state(tmp_path, "1.20.0", agents=74))
    assert v["status"] == "OK", v["reasons"]


def test_the_grace_covers_the_clone_that_precedes_the_launch(tmp_path,
                                                             monkeypatch):
    """Measured margin on the live container: HEAD written 34 ms before the
    session process existed. A write inside the grace is provisioning."""
    import datetime as dt
    repo = _repo(tmp_path, "1.20.0", agents=74)
    began = dt.datetime.fromisoformat("2026-09-16T02:36:50+00:00").timestamp()
    monkeypatch.setattr(pv, "session_started_at", lambda: began)
    tree = repo / "plugins" / "dma-insights"
    for f in tree.rglob("*"):
        os.utime(f, (began + pv.MID_SESSION_GRACE_S - 0.5,
                     began + pv.MID_SESSION_GRACE_S - 0.5))
    monkeypatch.setattr(pv, "bound_root", _measured(tree))
    assert pv.compare(repo, _state(tmp_path, "1.20.0", agents=74))["status"] == "OK"
    for f in tree.rglob("*"):
        os.utime(f, (began + pv.MID_SESSION_GRACE_S + 0.5,
                     began + pv.MID_SESSION_GRACE_S + 0.5))
    assert pv.compare(repo, _state(tmp_path, "1.20.0", agents=74)
                      )["status"] == "UPDATED_MID_SESSION"


def test_a_stale_tree_bound_in_place_is_stale_and_an_update_is_not_the_fix(
        tmp_path, monkeypatch):
    """The bind outranks the record in BOTH directions. A session binding an
    old checkout in place is stale however current the cache copy is — and
    `claude plugin update` would refresh the copy it does not run."""
    repo = _repo(tmp_path, "1.20.0", agents=74)
    old_tree = _plugin_tree(tmp_path / "other-checkout" / "plugins" /
                            "dma-insights", "1.18.0", agents=70)
    monkeypatch.setattr(pv, "bound_root", _measured(old_tree))
    v = pv.compare(repo, _state(tmp_path, "1.20.0", agents=74))
    assert v["status"] == "STALE" and not v["ok"]
    assert v["installed"]["version"] == "1.18.0"
    assert "70 agents" in " ".join(v["reasons"])
    assert "claude plugin update" not in v["fix"].split("`claude plugin update` refreshes")[0]
    assert "IN PLACE" in v["fix"] and str(old_tree) in v["fix"]


def test_a_stale_cache_copy_that_is_actually_bound_still_takes_the_update(
        tmp_path, monkeypatch):
    """A CLI that loads the cache copy (the record's own path) is the case
    the old code assumed everywhere. Measured as such, the old verdict and
    the old fix are exactly right."""
    repo = _repo(tmp_path, "1.20.0", agents=74)
    state = _state(tmp_path, "1.19.0", agents=73)
    cache = tmp_path / "cache" / "1.19.0"
    monkeypatch.setattr(pv, "bound_root", _measured(cache))
    v = pv.compare(repo, state)
    assert v["status"] == "STALE"
    assert v["installed"]["in_place"] is False
    assert v["installed"]["bound_source"] == "process"
    assert "claude plugin update" in v["fix"]
    assert "MEASURED BIND: this session loads the install record's tree" in \
        " ".join(v["reasons"])


def test_an_unmeasured_bind_inside_a_session_says_the_verdict_is_about_the_record(
        tmp_path, monkeypatch):
    """No process, no record, but a session (CLAUDE_PID set): the record is
    what there is, and the output must not dress it up as the session."""
    monkeypatch.setenv("CLAUDE_PID", "1")
    v = pv.compare(_repo(tmp_path), _state(tmp_path, "0.2.0", agents=5))
    assert v["status"] == "STALE"
    assert "BIND NOT MEASURED" in " ".join(v["reasons"])
    monkeypatch.delenv("CLAUDE_PID")
    v = pv.compare(_repo(tmp_path), _state(tmp_path, "0.2.0", agents=5))
    assert "BIND NOT MEASURED" not in " ".join(v["reasons"]), (
        "outside a session there is no bind to have measured")


def test_a_bound_tree_with_no_install_record_is_still_compared(tmp_path,
                                                                monkeypatch):
    """`--plugin-dir` and skills-dir loads have no record at all. A measured
    bind is a tree to compare; the missing record is not NOT_INSTALLED."""
    repo = _repo(tmp_path, "1.20.0", agents=74)
    tree = repo / "plugins" / "dma-insights"
    import time as _t
    monkeypatch.setattr(pv, "session_started_at", lambda: _t.time() + 10)
    monkeypatch.setattr(pv, "bound_root", _measured(tree, "env"))
    v = pv.compare(repo, tmp_path / "no-state.json")
    assert v["status"] == "OK", v["reasons"]
    assert v["installed"]["in_place"] is True
    assert v["installed"]["record_version"] is None


# ── the three rungs of `bound_root`, each measured, each filtered by name ─

def test_env_rung_reads_claude_plugin_root_for_this_plugin_only(tmp_path,
                                                                 monkeypatch):
    _unpin_bind(monkeypatch)
    ours = _plugin_tree(tmp_path / "ours", "1.0.0", agents=1)
    theirs = tmp_path / "theirs"
    (theirs / ".claude-plugin").mkdir(parents=True)
    (theirs / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "probe-plugin", "version": "0.0.1"}))
    monkeypatch.setattr(pv, "_proc_candidates", lambda: [])
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(theirs))
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    out = pv.bound_root()
    assert out["path"] is None, "another plugin's root is not our bind"
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(ours))
    out = pv.bound_root()
    assert out["source"] == "env" and out["path"] == str(ours.resolve())


def test_process_rung_takes_only_a_direct_child_of_the_session(tmp_path,
                                                               monkeypatch):
    """A `claude -p` child session started after a heal binds a DIFFERENT
    tree; its MCP server is a grandchild and must not answer for the parent."""
    _unpin_bind(monkeypatch)
    old = _plugin_tree(tmp_path / "old", "1.19.0", agents=73)
    new = _plugin_tree(tmp_path / "new", "1.20.0", agents=74)
    other = tmp_path / "other"
    (other / ".claude-plugin").mkdir(parents=True)
    (other / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "something-else"}))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PID", "122")
    monkeypatch.setattr(pv, "_proc_candidates", lambda: [
        (900, 122, str(other)),      # another plugin's server, direct child
        (1236, 122, str(old)),       # OUR connector, spawned by the session
        (3001, 2612, str(new)),      # a child session's connector (grandchild)
    ])
    out = pv.bound_root()
    assert out["source"] == "process" and out["path"] == str(old.resolve())
    monkeypatch.setattr(pv, "_proc_candidates", lambda: [(3001, 2612, str(new))])
    out = pv.bound_root()
    assert out["path"] is None and "no plugin subprocess" in out["reason"]


def test_record_rung_accepts_only_this_process_s_fresh_record(tmp_path,
                                                                monkeypatch):
    """Pids repeat across containers and /root/.dma survives in a snapshot,
    so a record for pid 122 from last week must not describe today's 122."""
    _unpin_bind(monkeypatch)
    tree = _plugin_tree(tmp_path / "tree", "1.20.0", agents=74)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PID", "122")
    monkeypatch.setattr(pv, "_proc_candidates", lambda: [])
    began = 1_789_526_210.0
    monkeypatch.setattr(pv, "session_started_at", lambda: began)
    import time as _t
    monkeypatch.setattr(_t, "time", lambda: began + 60)
    assert pv.record_bound_root(str(tree), pid="122") is not None
    out = pv.bound_root()
    assert out["source"] == "record" and out["path"] == str(tree.resolve())
    # the same file, stamped before this process existed: a snapshot's
    rec = json.loads(pv._bound_record_path(122).read_text())
    rec["recorded_at"] = began - 5 * 86400
    pv._bound_record_path(122).write_text(json.dumps(rec))
    out = pv.bound_root()
    assert out["path"] is None and "predates this process" in out["reason"]
    # a record for some other pid says nothing about this one
    pv._bound_record_path(122).unlink()
    pv.record_bound_root(str(tree), pid="999")
    out = pv.bound_root()
    assert out["path"] is None and "no SessionStart record" in out["reason"]


def test_recording_refuses_a_root_that_is_not_this_plugin(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PID", "122")
    assert pv.record_bound_root(str(tmp_path / "nowhere"), pid="122") is None
    assert pv.record_bound_root(str(tmp_path), pid="not-a-pid") is None
    assert not list((tmp_path / "bound").glob("*")) if (tmp_path / "bound").exists() else True


def test_outside_a_session_the_bind_is_unmeasured_and_says_why(monkeypatch):
    _unpin_bind(monkeypatch)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    out = pv.bound_root()
    assert out["path"] is None and out["source"] is None
    assert "CLAUDE_PID is unset" in out["reason"]


def test_bound_components_ignore_pycache_and_scripts(tmp_path):
    tree = _plugin_tree(tmp_path / "t", "1.0.0", agents=2)
    for f in tree.rglob("*"):
        os.utime(f, (1000, 1000))
    (tree / "scripts").mkdir()
    (tree / "scripts" / "x.py").write_text("x")
    (tree / "agents" / "__pycache__").mkdir()
    (tree / "agents" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    assert pv.bound_components_changed_at(tree) == 1000
    os.utime(tree / "hooks" if (tree / "hooks").exists() else tree / "agents" / "a0.md",
             (2000, 2000))
    assert pv.bound_components_changed_at(tree) == 2000
    assert pv.bound_components_changed_at(tmp_path / "absent") is None


def test_a_snapshot_with_an_in_place_bind_does_not_claim_a_short_roster(tmp_path):
    """The false diagnosis, banned: an old record on a session that binds
    the fresh checkout is a fact about the record, not a defect that recurs."""
    import datetime as _d
    old = (_d.datetime.now(_d.timezone.utc)
           - _d.timedelta(hours=119)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = pv.provisioning(_prov(tmp_path, bootstrap_ran_at=old), in_place=True)
    assert out["state"] == "snapshot_record_only"
    assert out["recurs"] is False and out["fix"] == ""
    assert "binds short" not in out["reason"]
    assert "binds the checkout in place" in out["reason"]
    # and the cache-bound reading is unchanged
    out = pv.provisioning(_prov(tmp_path, bootstrap_ran_at=old), in_place=False)
    assert out["state"] == "stale_snapshot" and out["recurs"] is True


def test_the_live_session_if_any_binds_what_the_checkout_publishes(monkeypatch):
    """Run INSIDE a Claude Code session on this checkout, this is the
    end-to-end proof; anywhere else it is skipped rather than faked."""
    _unpin_bind(monkeypatch)
    monkeypatch.setattr(pv, "BOUND_DIR", pv.PROV_FILE.parent)
    if not os.environ.get("CLAUDE_PID"):
        pytest.skip("not inside a Claude Code session")
    out = pv.bound_root()
    if out["path"] is None:
        pytest.skip(f"bind not measurable here: {out['reason']}")
    assert out["source"] in ("env", "process", "record")
    v = pv.compare()
    assert v["installed"]["bound_path"] == out["path"]
    if Path(out["path"]).resolve() == Path(v["published"]["tree"]).resolve():
        assert v["status"] in ("OK", "UPDATED_MID_SESSION"), v["reasons"]


def test_heal_declines_to_rewrite_a_cache_copy_the_session_does_not_load(
        tmp_path, monkeypatch):
    """Four exit-0 commands that change nothing the session runs is the shape
    of success with none of it. The heal says so instead."""
    repo = _repo(tmp_path, "1.20.0", agents=74)
    old_tree = _plugin_tree(tmp_path / "other-checkout" / "plugins" /
                            "dma-insights", "1.18.0", agents=70)
    monkeypatch.setattr(pv, "bound_root", _measured(old_tree))
    v = pv.compare(repo, _state(tmp_path, "1.20.0", agents=74))
    assert v["status"] == "STALE"
    ran = []
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", lambda *a, **k: ran.append(a) or None)
    out, log = pv.heal(v)
    assert out == v and ran == []
    assert log and "declined" in log[0] and str(old_tree) in log[0]
    assert "RESTORED SNAPSHOT" in v["fix"] and "attach the repository" in v["fix"]


def test_heal_still_updates_a_cache_copy_that_is_bound(tmp_path, monkeypatch):
    """The measured cache-bound case keeps its heal: there the update IS
    what the next session loads."""
    repo = _repo(tmp_path, "1.20.0", agents=74)
    state = _state(tmp_path, "1.19.0", agents=73)
    monkeypatch.setattr(pv, "bound_root", _measured(tmp_path / "cache" / "1.19.0"))
    monkeypatch.setattr(pv, "_under_plugin_cache", lambda p: True)
    v = pv.compare(repo, state)
    assert v["status"] == "STALE"
    ran = []
    import subprocess as _sp

    class _R:
        returncode = 0
    monkeypatch.setattr(_sp, "run", lambda argv, **k: ran.append(argv) or _R())
    out, log = pv.heal(v)
    assert out is None, "something ran: the caller re-measures"
    assert [a[1:3] for a in ran] == [["plugin", "marketplace"], ["plugin", "update"],
                                     ["plugin", "install"], ["plugin", "enable"]]
