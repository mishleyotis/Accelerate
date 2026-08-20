"""The audit that reported 21 defects and exited 0 every time it ran.

Two failures, and the second was caused by the first.

`audit_skills.py` resolved a path reference against the skill's own tree and
nowhere else, so twelve references that a reader follows without trouble —
`scripts/agent_run.py` at the plugin root, `scripts/tests/...` at the
repository root, `rulebooks/heatmap.md` written from a sibling inside
03-pages/ — came back as breakage. With 12 of 21 findings false, the report
was noise, and the eight real dead links sat inside it unread.

And it had no exit code. Every caller, CI included, read success from a script
whose stdout was a defect list. The two go together: a report that cannot be
trusted cannot be made to gate, and one that does not gate does not get fixed.

Each test below has its control. A resolver widened until everything resolves
would pass the "no false positives" half perfectly.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "audit_skills.py"
SKILLS = HERE.parent.parent / "skills"


def _load():
    spec = importlib.util.spec_from_file_location("audit_skills", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _run(*args):
    r = subprocess.run([sys.executable, str(SCRIPT), *args],
                       capture_output=True, text=True)
    return r, json.loads(r.stdout)


# A full audit spawns `--help` for all 70 bundled scripts, ~7s a run. Six of
# the tests below read the SAME default audit, so running it per test cost 54s
# of CI for one result. Cached by argument tuple; the tmp_path cases build
# their own tiny trees and are unaffected.
_cache: dict = {}


def audit(*args):
    if args not in _cache:
        _cache[args] = _run(*args)
    return _cache[args]


def test_the_audit_exits_nonzero_when_breakage_passes_the_ceiling():
    """The whole point. Before this, the number below could be anything."""
    r, out = audit("--max-broken", "0")
    assert r.returncode == 1, "a defect list still exited 0"
    assert out["broken_refs_total"] > 0
    assert "ceiling" in r.stderr


def test_the_audit_exits_zero_at_the_pinned_backlog():
    r, out = audit()
    assert r.returncode == 0, r.stderr[:400]
    assert out["broken_refs_total"] <= out["broken_refs_ceiling"]


def test_the_pinned_ceiling_is_not_slack():
    """A ceiling above the real count is a ratchet that never catches
    anything — it would absorb the next dead link silently, which is the
    behaviour this whole file exists to end."""
    mod = _load()
    _, out = audit()
    assert out["broken_refs_total"] == mod.MAX_BROKEN, (
        f"ceiling {mod.MAX_BROKEN} against {out['broken_refs_total']} actual "
        f"broken refs — lower MAX_BROKEN to the real count")


# ── the resolver: no false positives, and no free pass either ──


def test_a_plugin_level_script_reference_resolves():
    """`scripts/agent_run.py` in a skill doc means the plugin's scripts/,
    which is where it is. Reported broken for as long as the audit existed."""
    _, out = audit()
    dead = {(b["file"], b["ref"]) for b in out["broken_refs"]}
    for ref in ("scripts/agent_run.py", "scripts/client_memory.py",
                "scripts/source_yield.py", "scripts/subcap_match.py"):
        assert not any(r == ref for _, r in dead), f"{ref} still reported dead"
    assert (SKILLS.parent / "scripts" / "agent_run.py").exists(), (
        "the premise moved: agent_run.py is no longer at the plugin root, so "
        "this test is asserting against a file that does not exist")


def test_a_sibling_rulebook_reference_resolves_from_inside_the_section():
    _, out = audit()
    dead = {(b["file"], b["ref"]) for b in out["broken_refs"]}
    assert ("dma-surface-production/03-pages/rulebooks/insights.md",
            "rulebooks/heatmap.md") not in dead


def test_a_reference_that_resolves_nowhere_is_still_reported(tmp_path):
    """THE CONTROL ON THE RESOLVER. Widening the base list is only correct if
    it stops short of resolving everything; a name that exists under none of
    the seven bases must survive as breakage."""
    skill = tmp_path / "skills" / "made-up-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "See `helpers/does_not_exist_anywhere.py` for the details.\n")
    r, out = _run(str(tmp_path / "skills"), "--max-broken", "0")
    assert r.returncode == 1
    refs = [b["ref"] for b in out["broken_refs"]]
    assert "helpers/does_not_exist_anywhere.py" in refs, refs


def test_the_seven_dead_rulebook_links_are_still_reported():
    """The backlog is pinned, not hidden. If the rectifier fixes these the
    count drops and `test_the_pinned_ceiling_is_not_slack` demands MAX_BROKEN
    come down with it."""
    _, out = audit()
    dead = [b for b in out["broken_refs"]
            if b["file"].startswith("dma-surface-production/05-lifecycle/")]
    assert len(dead) == 7, [b["ref"] for b in dead]
    assert all(b["ref"].startswith("rulebooks/") for b in dead)


# ── the other half of the exit code ──


def test_a_script_that_fails_its_help_fails_the_audit(tmp_path):
    skill = tmp_path / "skills" / "broken-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("nothing to see\n")
    (skill / "boom.py").write_text("import sys\nsys.exit('no --help here')\n")
    r, out = _run(str(tmp_path / "skills"))
    assert r.returncode == 1, "a script that cannot run its own --help passed"
    assert out["scripts_fail"] == 1
    assert out["fails"][0]["path"].endswith("boom.py")


def test_an_empty_skills_tree_refuses_rather_than_reporting_clean(tmp_path):
    empty = tmp_path / "skills"
    empty.mkdir()
    r = subprocess.run([sys.executable, str(SCRIPT), str(empty)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "refusing to report a clean audit of nothing" in r.stderr


# ─────────────────────────────────────────────────────────────────────
# Argument handling. `--help` was once taken as a POSITIONAL path and exited
# 1 with "no skills directory at --help" — an auditor whose own usage line was
# unreachable. The positional default and the bad-path refusal are contract.
#
# These four predate the exit-code work above and are kept because adding an
# exit code is exactly the change that can break them: `--help` must still
# leave through argparse at 0, and a bad path must still leave at 1 for its
# own reason rather than through the new ceiling branch.
# ─────────────────────────────────────────────────────────────────────


def test_help_exits_zero_with_usage():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "usage:" in r.stdout
    assert "skills directory to audit" in r.stdout


def test_help_is_not_treated_as_a_path():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                       capture_output=True, text=True)
    assert "no skills directory at --help" not in (r.stdout + r.stderr)


def test_the_ceiling_flag_is_documented_in_the_usage():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                       capture_output=True, text=True)
    assert "--max-broken" in r.stdout, r.stdout


def test_bad_path_still_refuses_with_the_same_message():
    r = subprocess.run([sys.executable, str(SCRIPT), "/no/such/dir"],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "audit_skills: no skills directory at /no/such/dir" in r.stderr


def test_the_client_drive_tree_is_a_runtime_path_not_a_dead_link():
    """`DMA Insights/state.json` is a folder in the client's Drive tree. The
    path regex cannot carry the space, so the token arrives clipped to
    `Insights/state.json` and read as a skill-tree reference."""
    _, out = audit()
    assert not any(b["ref"].startswith("Insights/")
                   for b in out["broken_refs"])
    assert out["runtime_paths_total"] > 0
