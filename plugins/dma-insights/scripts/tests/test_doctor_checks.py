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
from unittest import mock
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
            (root / "agents" / "qa" / "qa-overseer.md").unlink()
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
            (root / "agents" / "qa" / "thirteenth.md").write_text(
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
        """Exit zero WHEN THE MACHINE IS PROVISIONED. On a runner without the
        skill dependencies or an activated account the doctor is right to
        exit 1 — that is an incomplete install, which is the question it
        exists to answer — so the exit assertion is made only when those
        machine rows are green (measured in CI, 2026-08-20)."""
        proc, _, failing = _offline_doctor_rows()
        if failing & ENVIRONMENT_DEPENDENT_ROWS:
            self.assertNotEqual(
                proc.returncode, 0,
                "an incomplete install must NOT report success")
        else:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rows = {c["check"]: c for c in json.loads(proc.stdout)["checks"]}
        self.assertIn("--no-probe",
                      rows["connector rejects an unauthenticated call"]["detail"])
        self.assertIn("SKIPPED",
                      rows["live tool roster reconciles"]["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


# Rows that describe THE MACHINE, not the install's correctness. A CI runner
# has no plugin skill dependencies installed and no Google account activated,
# so those two rows are legitimately red there and green on a provisioned
# workstation (measured 2026-08-20: CI reported "declared: 13 present: 3
# missing: 10" and "active google account: none active"). Asserting them
# green everywhere makes a test that fails for the environment rather than
# for the code — and a test that cries wolf is the one people delete. What
# stays asserted is the part that IS environment-independent: no row outside
# this set may fail, and the offline run must make no network call.
ENVIRONMENT_DEPENDENT_ROWS = {
    "skill script dependencies",
    "active google account",
    "identity source",
}


def _offline_doctor_rows():
    proc = subprocess.run(
        [sys.executable, str(HERE.parent / "doctor.py"), "--no-probe", "--json"],
        capture_output=True, text=True, timeout=300)
    rows = json.loads(proc.stdout)["checks"]
    failing = {r["check"] for r in rows if not r["ok"]}
    return proc, rows, failing


class NoProbeIsTrulyOffline(unittest.TestCase):
    """--no-probe must mean NO NETWORK, not "fewer network calls".

    Measured 2026-08-20: an offline doctor still shelled out to pip (through
    dma-deps' wheel resolution) and to gcloud (to mint an identity token),
    so on any machine without a network — or behind a proxy pip or gcloud
    does not trust — it reported red rows whose own detail text said
    everything was present. Both are pinned here because both were the same
    mistake: a network check wearing a local row's name.
    """

    def test_the_dependency_row_does_not_reach_pypi(self):
        import doctor as d
        seen = {}

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            class R:
                returncode = 0
                stdout = "declared: 13  present: 13  missing: 0\n"
                stderr = ""
            return R()

        with mock.patch.object(d.subprocess, "run", fake_run):
            row = d.deps_check(offline=True)
        self.assertTrue(row["ok"], row)
        self.assertIn("--offline", seen["cmd"],
                      "deps_check(offline=True) must ask dma-deps to skip the "
                      "wheel resolution; without the flag it reaches PyPI")

    def test_the_identity_mint_row_is_skipped_offline(self):
        _, rows, _ = _offline_doctor_rows()
        mint = [r for r in rows if r["check"] == "identity token mints"]
        self.assertEqual(len(mint), 1, "the row must still be REPORTED")
        self.assertTrue(mint[0]["ok"])
        self.assertIn("SKIPPED", mint[0]["detail"],
                      "an offline run must say it skipped, never claim a "
                      "mint it did not attempt")

    def test_no_row_outside_the_environment_set_fails_offline(self):
        """The whole point, stated so it can only fail for the right reason:
        an offline run may be red about the MACHINE (dependencies not
        installed, no account activated) and must be green about everything
        the repository controls — the manifest, the hooks, the connector
        definition, the skills inventory, the audience and the token rows."""
        proc, rows, failing = _offline_doctor_rows()
        unexpected = failing - ENVIRONMENT_DEPENDENT_ROWS
        self.assertEqual(unexpected, set(),
                         f"offline doctor is red on rows the code owns: "
                         f"{sorted(unexpected)}")
        if not failing:
            self.assertEqual(proc.returncode, 0,
                             "every row green must mean exit 0")


class ToolRosterReconciliation(unittest.TestCase):
    """The row that would have stopped every scheduled firing.

    `tool_roster_check` reconciles hook matchers against the connector's live
    tool list. It treated EVERY matcher as a connector tool name, so two
    legitimate kinds failed as though the connector had dropped a tool:

      * `Bash`, which has matched deny_credential_ops since that guard existed
        and is not a connector tool at all;
      * `mcp__.*`, which is how autoapprove_connector reaches the enrichment
        connectors — their server segment is an opaque per-attachment UUID
        that no exact matcher can name.

    Measured 2026-08-21T03:33Z: `13/14 checks passed`, the failing row naming
    both. The synthesis routine's STEP 0 requires a FULLY GREEN doctor, so
    that single row would have stopped the routine at the gate — a check that
    fails a correct configuration is worse than no check, because it teaches
    people to skip the row.

    The drift it exists for must still be caught, so both halves are tested.
    """

    LIVE = ["get_run_progress", "claim_run", "submit_page_payload",
            "promote_run", "register_evidence"]

    def _row(self, matchers):
        with mock.patch.object(doctor, "live_tool_names",
                               return_value=self.LIVE), \
             mock.patch.object(doctor, "hook_matchers",
                               return_value=matchers), \
             mock.patch.object(doctor, "_path_token",
                               return_value=("tok", "test")):
            return doctor.tool_roster_check(
                "https://example.invalid", "gcloud", "idtok",
                {"description": f"connector ({len(self.LIVE)} tools)"})

    def test_a_named_connector_tool_that_is_gone_still_fails(self):
        """THE DRIFT THE ROW EXISTS FOR — a hook that silently stopped firing."""
        row = self._row(["mcp__plugin_dma-insights_connector__deleted_tool"])
        self.assertFalse(row["ok"], row["detail"])
        self.assertIn("deleted_tool", row["detail"])

    def test_a_named_connector_tool_that_is_live_passes(self):
        row = self._row(["mcp__plugin_dma-insights_connector__promote_run"])
        self.assertTrue(row["ok"], row["detail"])

    def test_a_non_mcp_matcher_is_not_treated_as_a_connector_tool(self):
        """Bash matches the credential guard and is not a connector tool."""
        row = self._row(["Bash"])
        self.assertTrue(row["ok"], row["detail"])

    def test_a_pattern_matcher_is_not_name_checked(self):
        """`mcp__.*` cannot name a tool; its scoping lives in the hook script
        and that script's own tests, not in this row."""
        row = self._row(["mcp__.*"])
        self.assertTrue(row["ok"], row["detail"])

    def test_the_real_hooks_json_reconciles(self):
        row = self._row(doctor.hook_matchers())
        self.assertTrue(row["ok"], row["detail"])

    def test_the_row_says_what_it_did_not_name_check(self):
        """A row reporting 'all N resolve' while silently skipping most of
        them is the comfortable half-truth this build keeps removing."""
        row = self._row(["Bash", "mcp__.*",
                         "mcp__plugin_dma-insights_connector__promote_run"])
        self.assertTrue(row["ok"], row["detail"])
        self.assertIn("1 named connector matcher(s) resolve", row["detail"])
        self.assertIn("1 pattern", row["detail"])
        self.assertIn("1 non-connector", row["detail"])

    def test_a_drifted_advertised_count_still_fails(self):
        with mock.patch.object(doctor, "live_tool_names",
                               return_value=self.LIVE), \
             mock.patch.object(doctor, "hook_matchers", return_value=[]), \
             mock.patch.object(doctor, "_path_token",
                               return_value=("tok", "test")):
            row = doctor.tool_roster_check(
                "https://example.invalid", "gcloud", "idtok",
                {"description": "connector (99 tools)"})
        self.assertFalse(row["ok"], row["detail"])
        self.assertIn("99", row["detail"])


class AutoApproverIsWired(unittest.TestCase):
    """A scheduled firing that lacks the auto-approver does not fail — it HANGS.

    Three firings died that way on 2026-08-21, two on the connector and one on
    an enrichment lookup, each waiting on a permission prompt the owner has
    confirmed is never surfaced to a human at all.

    Instructions in the routine prompt cannot cover it: a session blocked
    mid-tool-call is not reading anything. So the check runs BEFORE work
    starts, in the row STEP 0 already requires green — which turns a stale
    plugin from a silently burned twelve-hour slot into a loud refusal at the
    gate.
    """

    def test_the_real_tree_has_the_approver_wired(self):
        row = doctor.hooks_wired_check()
        self.assertTrue(row["ok"], row["detail"])
        self.assertIn("auto-approver is present and wired", row["detail"])

    def test_a_missing_approver_fails_the_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = _copy_tree(Path(td))
            (root / "scripts" / "hooks" / "autoapprove_connector.py").unlink()
            row = doctor.hooks_wired_check(root)
        self.assertFalse(row["ok"], row["detail"])
        self.assertIn("hang on a permission prompt", row["detail"])

    def test_an_unwired_approver_fails_the_row(self):
        """Present on disk but named by no PreToolUse entry — the file exists
        and never runs, which is indistinguishable from absent at runtime."""
        with tempfile.TemporaryDirectory() as td:
            root = _copy_tree(Path(td))
            hj = root / "hooks" / "hooks.json"
            spec = json.loads(hj.read_text())
            spec["hooks"]["PreToolUse"] = [
                e for e in spec["hooks"]["PreToolUse"]
                if "autoapprove_connector.py" not in
                " ".join(h["command"] for h in e["hooks"])]
            hj.write_text(json.dumps(spec, indent=2))
            row = doctor.hooks_wired_check(root)
        self.assertFalse(row["ok"], row["detail"])
        self.assertIn("no PreToolUse entry runs it", row["detail"])
