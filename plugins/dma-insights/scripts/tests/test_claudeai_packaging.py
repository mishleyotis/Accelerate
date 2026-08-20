"""The claude.ai upload rules, pinned — each one cost a failed upload.

The uploader's rules surface one rejection at a time and `claude plugin
validate` does not enforce them (measured 2026-08-20: it passed a
734-character description the uploader refused). package_plugin.py carries
the rule list; these tests make sure the plugin as it sits in the tree
satisfies every learned rule, and that the checker itself can still FAIL
(negative controls), so a green run means uploadable rather than unchecked.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import package_plugin as pkg  # noqa: E402


def _manifest():
    return json.loads(
        (pkg.PLUGIN / ".claude-plugin" / "plugin.json").read_text())


def test_tree_passes_every_learned_upload_rule():
    fails = pkg.check(_manifest(), list(pkg.iter_files()))
    assert fails == [], fails


def test_description_is_at_most_500_chars():
    assert len(_manifest()["description"]) <= 500


def test_description_keeps_the_tools_count_doctor_parses():
    import re
    assert re.search(r"\(\d+ tools\)", _manifest()["description"])


def test_no_top_level_bin_directory():
    assert not (pkg.PLUGIN / "bin").exists()


def test_checker_fails_on_overlong_description():
    """Negative control: the rule can actually fire."""
    m = _manifest()
    m["description"] = "x" * 501 + " (33 tools)"
    fails = pkg.check(m, list(pkg.iter_files()))
    assert any("chars (max 500)" in f for f in fails)


def test_checker_fails_on_top_level_bin():
    fails = pkg.check(_manifest(),
                      list(pkg.iter_files()) + [Path("bin/dma-deps")])
    assert any("top-level bin/" in f for f in fails)


def test_no_agent_carries_forbidden_front_matter():
    """All sixteen agents carried mcpServers until 2026-08-20; the hosted
    schema forbids it and disallowedTools is the real guard."""
    fails = pkg.check(_manifest(), list(pkg.iter_files()))
    assert not any("front matter carries" in f for f in fails)


def test_checker_fails_on_url_in_description():
    m = _manifest()
    m["description"] = "See https://example.com for details (33 tools)"
    fails = pkg.check(m, list(pkg.iter_files()))
    assert any("contains a URL" in f for f in fails)


def test_manifest_has_no_schema_field():
    """$schema is outside the uploader's documented field set."""
    assert "$schema" not in _manifest()


def test_zip_builds_clean(tmp_path):
    rc = pkg.main(["--out", str(tmp_path)])
    assert rc == 0
    out = next(tmp_path.glob("dma-insights-*.zip"))
    import zipfile
    names = zipfile.ZipFile(out).namelist()
    assert ".claude-plugin/plugin.json" in names
    assert not any(n.startswith("bin/") for n in names)
    assert not any("__pycache__" in n for n in names)


def test_every_shipped_agent_is_declared_in_the_manifest():
    """The taxonomy folders are safe only because plugin.json declares every
    agent file individually (the manifest schema takes file paths, not
    directories) — a loader that does not recurse must still see the roster.
    Both drift directions fail: a shipped-but-undeclared agent, and a declared
    ghost."""
    import json
    manifest = json.loads((pkg.PLUGIN / ".claude-plugin"
                           / "plugin.json").read_text())
    entries = list(pkg.iter_files())
    assert not pkg.check(manifest, entries), "the real tree must be in sync"

    undeclared = dict(manifest, agents=manifest["agents"][:-1])
    fails = pkg.check(undeclared, entries)
    assert any("not declared in plugin.json" in f for f in fails)

    ghost = dict(manifest,
                 agents=manifest["agents"] + ["./agents/qa/never-written.md"])
    fails = pkg.check(ghost, entries)
    assert any("no such file ships" in f for f in fails)
