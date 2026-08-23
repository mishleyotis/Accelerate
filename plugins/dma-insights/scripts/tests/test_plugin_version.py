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
           skills=6):
    """An installed_plugins.json plus the cache tree it points at."""
    cache = _plugin_tree(tmp_path / "cache" / str(version), version, agents,
                         skills)
    records = [{"scope": scope, "version": version,
                "installPath": str(cache), "gitCommitSha": "deadbeef"}]
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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
