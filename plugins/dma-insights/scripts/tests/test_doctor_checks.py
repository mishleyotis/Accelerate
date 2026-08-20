#!/usr/bin/env python3
"""The doctor's local checks, against the real tree and broken copies of it.

The network rows (audience, enforcement, tool roster) are not probed here: a
test that needs the deployed connector fails on exactly the machines the
doctor exists to diagnose. Broken states are staged in a tempdir copy — the
real tree is never mutated.

    python3 test_doctor_checks.py
    python3 -m pytest tests/
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import doctor  # noqa: E402

PLUGIN = HERE.parent.parent


def _copy_tree(into: Path) -> Path:
    root = into / "plugin"
    shutil.copytree(PLUGIN, root,
                    ignore=shutil.ignore_patterns("__pycache__", "tests"))
    return root


class HooksWired(unittest.TestCase):
    def test_real_tree_passes(self):
        row = doctor.hooks_wired_check()
        self.assertTrue(row["ok"], row["detail"])
        self.assertIn("exits 0 on a benign event", row["detail"])

    def test_real_tree_matchers_stay_fully_scoped(self):
        matchers = doctor.hook_matchers()
        self.assertIn(
            "mcp__plugin_dma-insights_connector__submit_page_payload", matchers)
        self.assertIn(
            "mcp__plugin_dma-insights_connector__promote_run", matchers)

    def test_unparseable_hooks_json_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = _copy_tree(Path(td))
            (root / "hooks" / "hooks.json").write_text("{not json")
            row = doctor.hooks_wired_check(root)
            self.assertFalse(row["ok"])
            self.assertIn("does not parse", row["detail"])

    def test_missing_handler_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = _copy_tree(Path(td))
            (root / "scripts" / "hooks" / "precheck_submit.py").unlink()
            row = doctor.hooks_wired_check(root)
            self.assertFalse(row["ok"])
            self.assertIn("precheck_submit.py", row["detail"])

    def test_missing_timeout_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = _copy_tree(Path(td))
            hooks_file = root / "hooks" / "hooks.json"
            spec = json.loads(hooks_file.read_text())
            del spec["hooks"]["SessionStart"][0]["hooks"][0]["timeout"]
            hooks_file.write_text(json.dumps(spec))
            row = doctor.hooks_wired_check(root)
            self.assertFalse(row["ok"])
            self.assertIn("timeout", row["detail"])

    def test_crashing_handler_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = _copy_tree(Path(td))
            (root / "scripts" / "hooks" / "session_brief.py").write_text(
                "import sys\nsys.exit(3)\n")
            row = doctor.hooks_wired_check(root)
            self.assertFalse(row["ok"])
            self.assertIn("exited 3", row["detail"])


class ExactInventory(unittest.TestCase):
    def test_real_tree_counts_exactly(self):
        rows = doctor.inventory_checks()
        self.assertTrue(all(r["ok"] for r in rows), rows)

    def test_hidden_agent_fails_the_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = _copy_tree(Path(td))
            (root / "agents" / "qa-overseer.md").unlink()
            rows = {r["check"]: r for r in doctor.inventory_checks(root)}
            self.assertFalse(rows["agents inventory"]["ok"])
            # Derived from EXPECTED_AGENTS rather than written out: the literal
            # was "15 of exactly 16" and went stale the first time the agent
            # roster grew, failing a test that was still testing the right
            # thing — one missing file is caught by the equality check.
            self.assertIn(
                f"{doctor.EXPECTED_AGENTS - 1} of exactly "
                f"{doctor.EXPECTED_AGENTS}",
                rows["agents inventory"]["detail"])
            self.assertNotIn("qa-overseer",
                             rows["agents inventory"]["detail"])
            self.assertTrue(rows["skills inventory"]["ok"])

    def test_extra_agent_fails_the_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = _copy_tree(Path(td))
            (root / "agents" / "thirteenth.md").write_text(
                "---\nname: thirteenth\n---\n")
            rows = {r["check"]: r for r in doctor.inventory_checks(root)}
            self.assertFalse(rows["agents inventory"]["ok"])

    def test_hidden_skill_fails_the_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = _copy_tree(Path(td))
            shutil.rmtree(root / "skills" / "dma-governance")
            rows = {r["check"]: r for r in doctor.inventory_checks(root)}
            self.assertFalse(rows["skills inventory"]["ok"])
            self.assertIn("5 of exactly 6", rows["skills inventory"]["detail"])


class EnabledState(unittest.TestCase):
    def test_reports_shipped_disabled_and_never_fails(self):
        row = doctor.enabled_state_check({"defaultEnabled": False})
        self.assertTrue(row["ok"])
        self.assertIn("defaultEnabled=false", row["detail"])
        self.assertIn("ships disabled", row["detail"])

    def test_never_fails_even_when_the_field_is_absent(self):
        row = doctor.enabled_state_check({})
        self.assertTrue(row["ok"])
        self.assertIn("defaultEnabled=null", row["detail"])


class ToolRoster(unittest.TestCase):
    def test_no_probe_skips_and_passes(self):
        row = doctor.tool_roster_check(None, None, None, {})
        self.assertTrue(row["ok"])
        self.assertIn("SKIPPED", row["detail"])

    def test_no_identity_token_skips_never_fails(self):
        row = doctor.tool_roster_check(
            "https://example-abc123-uc.a.run.app", None, None,
            {"description": "(33 tools)"})
        self.assertTrue(row["ok"])
        self.assertIn("SKIPPED", row["detail"])

    def test_scoped_prefix_derives_from_manifest_and_mcp_json(self):
        prefixes = doctor._scoped_prefixes(doctor.read_manifest())
        self.assertEqual(prefixes, ["mcp__plugin_dma-insights_connector__"])

    def test_manifest_advertises_a_parseable_tool_count(self):
        description = doctor.read_manifest().get("description") or ""
        self.assertRegex(description, r"\(\d+ tools\)")


class BaseUrlDefault(unittest.TestCase):
    def test_manifest_base_url_reads_the_manifest_default(self):
        self.assertEqual(doctor.manifest_base_url(),
                         "https://dmai-mcp-dukrne5v4a-uc.a.run.app")

    def test_no_probe_run_skips_the_network_rows_and_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(HERE.parent / "doctor.py"),
             "--no-probe", "--json"],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rows = {c["check"]: c for c in json.loads(proc.stdout)["checks"]}
        self.assertIn("--no-probe",
                      rows["connector rejects an unauthenticated call"]["detail"])
        self.assertIn("SKIPPED",
                      rows["live tool roster reconciles"]["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
