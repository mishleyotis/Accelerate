"""The three red rows every DMA session met at its first doctor run — pinned.

Interac, 2026-10-10 (and SWBC, Arbor, B1, IMA before it): `doctor.py --heal`
read 14/17 with

  installed plugin           UPDATED_MID_SESSION — the session checked out
                             the local default branch, which a restored
                             snapshot had left 122 commits behind, and pulled
                             it straight back to the commit it started on
  connector contract         UNVERIFIED: no baseline — the baseline needed a
                             run root that did not exist yet, and 334 tool
                             names typed by hand
  live tool roster           "manifest advertises 35 tools, the connector
                             serves 36"

Each is replayed here as the session met it, and each must now come out
right without a human: the round trip reads OK (and a REAL change still
reads UPDATED_MID_SESSION, naming the files), the roster is measured from
the transcript (and a connector that drops mid-session is seen as dropped),
and the stale ref is fast-forwarded before anyone checks it out (and a ref
holding somebody's work is left alone).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import connector_contract as cc  # noqa: E402
import doctor  # noqa: E402
import git_refs  # noqa: E402
import plugin_version as pv  # noqa: E402
import session_roster as sr  # noqa: E402

CONNECTOR = "mcp__plugin_dma-insights_connector__"
FULL = ["mcp__Exa__web_search_exa", "mcp__Tavily__tavily_search",
        "mcp__Clay__search-companies", "mcp__Quartr__get_conference",
        CONNECTOR + "promote_run"]


def _line(**o):
    return json.dumps(o) + "\n"


def _delta(added=(), removed=(), readded=(), sidechain=False):
    return _line(type="attachment", isSidechain=sidechain,
                 attachment={"type": "deferred_tools_delta",
                             "addedNames": list(added),
                             "removedNames": list(removed),
                             "readdedNames": list(readded)})


def _call(tid, name, inp=None):
    return _line(type="assistant", isSidechain=False, message={
        "role": "assistant",
        "content": [{"type": "tool_use", "id": tid, "name": name,
                     "input": inp or {}}]})


def _result(tid, text, is_error=False):
    return _line(type="user", isSidechain=False, message={
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tid,
                     "content": text, "is_error": is_error}]})


class _Session(unittest.TestCase):
    """A fake Claude Code session: config dir, session id, transcript."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sid = "sess-0000-interac"
        self.proj = self.tmp / "cfg" / "projects" / "-home-user-Accelerate"
        self.proj.mkdir(parents=True)
        self.transcript = self.proj / f"{self.sid}.jsonl"
        self.env = mock.patch.dict(os.environ, {
            "CLAUDE_CONFIG_DIR": str(self.tmp / "cfg"),
            "CLAUDE_CODE_SESSION_ID": self.sid,
            "DMA_SESSION_ROSTER": "1",
            "DMA_RUN_ROOT": str(self.tmp / "no-run-yet")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, *lines):
        with open(self.transcript, "a") as fh:
            fh.writelines(lines)


# ── 1 · the roster is measured, not typed ───────────────────────────────────

class RosterFromTranscript(_Session):
    def test_the_roster_folds_every_delta_in_order(self):
        self.write(_delta(added=FULL + ["mcp__Indeed__search_jobs"]),
                   _delta(removed=["mcp__Indeed__search_jobs"]),
                   _delta(readded=["mcp__Vibe_Prospecting__match-business"]))
        r = sr.current()
        self.assertTrue(r["found"])
        self.assertNotIn("mcp__Indeed__search_jobs", r["tools"])
        self.assertIn("mcp__Vibe_Prospecting__match-business", r["tools"])
        self.assertIn("mcp__Exa__web_search_exa", r["mcp_tools"])

    def test_a_subagents_roster_is_not_this_sessions(self):
        self.write(_delta(added=FULL),
                   _delta(added=["mcp__Secret__x"], sidechain=True))
        self.assertNotIn("mcp__Secret__x", sr.current()["tools"])

    def test_workflow_is_unknown_until_a_workflow_call_answers(self):
        self.write(_delta(added=FULL))
        self.assertIsNone(sr.current()["workflow_tool"])
        self.write(_call("t1", "Workflow"), _result("t1", "started wf_abc"))
        self.assertTrue(sr.current()["workflow_tool"])

    def test_a_refused_workflow_call_reads_as_lost(self):
        self.write(_delta(added=FULL), _call("t1", "Workflow"),
                   _result("t1", "No such tool available: Workflow. Workflow "
                           "is disabled for this session", is_error=True))
        self.assertIs(sr.current()["workflow_tool"], False)

    def test_a_file_that_QUOTES_the_refusal_is_not_evidence(self):
        """Measured while writing this: matching the phrase anywhere read a
        session holding Workflow as one that had lost it, because a Bash
        result had printed connector_contract.py's comment."""
        self.write(_delta(added=FULL), _call("b1", "Bash"),
                   _result("b1", "# ('No such tool available: Workflow. "
                           "Workflow is disabled for this session' — SWBC)"))
        self.assertIsNone(sr.current()["workflow_tool"])

    def test_a_session_with_no_transcript_is_unmeasured_not_empty(self):
        self.transcript.unlink(missing_ok=True)
        r = sr.current()
        self.assertFalse(r["found"])
        self.assertIn("not found", r["reason"])

    def test_tool_search_off_means_no_roster_not_no_tools(self):
        self.write(_call("b1", "Bash"), _result("b1", "ok"))
        r = sr.current()
        self.assertFalse(r["found"])

    def test_the_opt_out_is_honoured(self):
        self.write(_delta(added=FULL))
        with mock.patch.dict(os.environ, {"DMA_SESSION_ROSTER": "0"}):
            self.assertFalse(sr.current()["found"])

    def test_a_session_id_cannot_escape_the_projects_dir(self):
        self.assertIsNone(sr.transcript_path("../../etc/passwd"))


class BaselineIsAdopted(_Session):
    def test_ensure_adopts_once_and_never_overwrites(self):
        self.write(_delta(added=FULL))
        root = self.tmp / "run"
        first = cc.ensure_baseline(root)
        self.assertTrue(first["adopted"])
        self.assertEqual(first["sources"], ["transcript"])
        self.assertIn("exa", first["present"])
        before = (root / "connectors_baseline.json").read_bytes()
        self.write(_delta(removed=["mcp__Exa__web_search_exa"]))
        again = cc.ensure_baseline(root)
        self.assertFalse(again["adopted"])
        self.assertEqual((root / "connectors_baseline.json").read_bytes(), before)

    def test_a_typed_list_is_unioned_with_the_transcript(self):
        """Interac's first typed list abbreviated whole families; the
        transcript fills what the typing dropped."""
        self.write(_delta(added=FULL))
        rc = cc.main(["baseline", "--tools", os.devnull, "--root",
                      str(self.tmp / "r")])
        self.assertEqual(rc, 0)
        rec = json.loads((self.tmp / "r" / "connectors_baseline.json").read_text())
        self.assertEqual(rec["sources"], ["transcript"])
        typed = self.tmp / "typed.txt"
        typed.write_text("Bash\nRead\nAgent\nWorkflow\nmcp__Extra__tool\n")
        cc.main(["baseline", "--tools", str(typed), "--root", str(self.tmp / "u")])
        rec = json.loads((self.tmp / "u" / "connectors_baseline.json").read_text())
        self.assertEqual(rec["sources"], ["typed", "transcript"])
        self.assertIn("mcp__Extra__tool", rec["mcp_tools"])
        self.assertIn("mcp__Exa__web_search_exa", rec["mcp_tools"])
        self.assertIs(rec["workflow_tool"], True)

    def test_no_roster_and_no_file_is_still_none(self):
        self.assertIsNone(cc.ensure_baseline(self.tmp / "r"))

    def test_probe_from_session_sees_a_connector_drop_mid_session(self):
        self.write(_delta(added=FULL))
        root = self.tmp / "r"
        cc.ensure_baseline(root)
        self.write(_delta(removed=["mcp__Exa__web_search_exa",
                                   "mcp__Exa__web_fetch_exa"]))
        out = cc.probe(sr.current()["tools"], root)
        self.assertEqual(out["verdict"], "DEGRADED")
        self.assertIn("exa", out["lost_required"])

    def test_check_from_session_is_strict_on_a_short_roster(self):
        self.write(_delta(added=["mcp__Clay__search-companies"]))
        self.assertEqual(cc.main(["check", "--from-session", "--strict"]), 1)
        self.write(_delta(added=FULL))
        self.assertEqual(cc.main(["check", "--from-session", "--strict"]), 0)


class OpaqueServerNames(unittest.TestCase):
    """The verification session for PR #89 held every connector under a
    per-attachment UUID (`mcp__767c83d5-…__web_search_exa`) and the contract,
    matching friendly names exactly, read "present: none" over 302 tools."""

    U = "767c83d5-ff58-4e3f-b900-e68d469eed7a"
    V = "a2a0fb32-e011-42b6-a375-cb87e878286f"
    C = "1b306a35-0082-4326-b8b4-f10f6540dc15"
    X = "b978d40e-c704-447d-8130-e74da6b51487"

    def _t(self, srv, *names):
        return [f"mcp__{srv}__{n}" for n in names]

    def test_the_verification_sessions_real_roster_is_ready(self):
        held = (self._t(self.U, "web_search_exa", "web_fetch_exa")
                + self._t(self.V, "tavily_search", "tavily_extract",
                          "tavily_crawl")
                + self._t(self.C, "search-contacts", "search-companies",
                          "get-task-context")
                + self._t(self.X, "match-business", "enrich-business"))
        out = cc.check(held)
        self.assertEqual(out["verdict"], "READY", out)
        self.assertEqual(set(out["present"]),
                         {"exa", "tavily", "clay", "explorium"})

    def test_one_shared_generic_name_is_not_a_signature(self):
        """Dice serves `search_jobs` too; that alone is not Indeed."""
        held = self._t("5e0fe4f4-8fd9-448d-a1b5-fafc63f9aa67",
                       "search_jobs", "get_company", "get_job_details")
        self.assertNotIn("indeed", cc.check(held)["present"])
        self.assertNotIn("indeed", cc.check(["mcp__Dice__search_jobs",
                                             "mcp__Dice__get_company"])["present"])

    def test_a_brand_bearing_name_is_its_own_signature(self):
        self.assertIn("exa", cc.check(self._t(self.U, "web_search_exa"))
                      ["present"])
        self.assertIn("tavily", cc.check(self._t(self.V, "tavily_search"))
                      ["present"])

    def test_generic_names_split_across_two_servers_do_not_add_up(self):
        held = (self._t(self.C, "search-contacts")
                + self._t(self.X, "get-task-context"))
        self.assertNotIn("clay", cc.check(held)["present"])

    def test_friendly_spellings_still_resolve(self):
        out = cc.check(["mcp__claude_ai_Exa__web_search_exa",
                        "mcp__Tavily__tavily_search"])
        self.assertEqual(set(out["present"]), {"exa", "tavily"})

    def test_a_short_opaque_roster_is_still_short(self):
        out = cc.check(self._t(self.C, "search-contacts", "search-companies"))
        self.assertEqual(out["verdict"], "STOP")
        self.assertIn("exa", out["missing"])


class DoctorContractRow(_Session):
    def test_the_first_doctor_run_is_green_without_a_run_root(self):
        """THE INTERAC ROW: doctor before any root exists."""
        self.write(_delta(added=FULL))
        row = doctor.connector_contract_check()
        self.assertTrue(row["ok"], row["detail"])
        self.assertIn("transcript", row["detail"])
        self.assertFalse((self.tmp / "no-run-yet").exists(),
                         "the doctor measures; it must not write")

    def test_a_short_measured_roster_is_still_red(self):
        self.write(_delta(added=["mcp__Clay__search-companies"]))
        row = doctor.connector_contract_check()
        self.assertFalse(row["ok"])
        self.assertIn("SHORT", row["detail"])

    def test_nothing_measurable_is_still_unverified(self):
        row = doctor.connector_contract_check()
        self.assertFalse(row["ok"])
        self.assertIn("UNVERIFIED", row["detail"])


# ── 2 · a branch round trip is not a mid-session change ─────────────────────

def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=True).stdout.strip()


def _repo(root: Path) -> Path:
    repo = root / "repo"
    plug = repo / "plugins" / "dma-insights"
    (plug / "agents").mkdir(parents=True)
    (plug / "hooks").mkdir()
    (plug / ".claude-plugin").mkdir()
    (plug / "scripts").mkdir()
    (plug / ".mcp.json").write_text("{}")
    _git(root, "init", "-q", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    return repo


def _commit(repo, version, agent_body, msg):
    plug = repo / "plugins" / "dma-insights"
    (plug / ".claude-plugin" / "plugin.json").write_text(json.dumps(
        {"name": "dma-insights", "version": version,
         "description": f"x ({version}) (36 tools)",
         "agents": ["./agents/a.md"]}))
    (plug / "agents" / "a.md").write_text(agent_body)
    (plug / "hooks" / "hooks.json").write_text('{"hooks": {}}')
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = _repo(self.tmp)
        self.plug = self.repo / "plugins" / "dma-insights"
        self.old = _commit(self.repo, "1.20.0", "old agent", "old")
        self.new = _commit(self.repo, "1.21.0", "new agent", "new")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_checkout_back_and_forth_leaves_no_moved_component(self):
        bound = pv.bound_fingerprint(self.plug)
        _git(self.repo, "checkout", "-q", self.old)
        self.assertIn("agents/a.md", pv.moved_components(self.plug, bound))
        _git(self.repo, "checkout", "-q", self.new)
        self.assertEqual(pv.moved_components(self.plug, bound), [])

    def test_a_version_or_description_bump_alone_is_not_movement(self):
        bound = pv.bound_fingerprint(self.plug)
        m = json.loads((self.plug / ".claude-plugin" / "plugin.json").read_text())
        m["version"], m["description"] = "9.9.9", "(37 tools)"
        (self.plug / ".claude-plugin" / "plugin.json").write_text(json.dumps(m))
        self.assertEqual(pv.moved_components(self.plug, bound), [])

    def test_no_recorded_fingerprint_answers_none_not_empty(self):
        self.assertIsNone(pv.moved_components(self.plug, None))

    def _installed_after(self, mutate):
        """installed() for a session that bound `self.plug` in place, after
        `mutate` rewrote the tree post-start."""
        bound_dir = self.tmp / "bound"
        with mock.patch.dict(os.environ, {"CLAUDE_PID": "4242",
                                          "CLAUDE_PLUGIN_ROOT": str(self.plug)}), \
             mock.patch.object(pv, "BOUND_DIR", bound_dir), \
             mock.patch.object(pv, "session_started_at", return_value=1000.0):
            with mock.patch("time.time", return_value=1000.5):
                pv.record_bound_root(str(self.plug), pid="4242")
            mutate()
            for f in self.plug.rglob("*"):
                if f.is_file():
                    os.utime(f, (5000, 5000))      # written well after start
            state = self.tmp / "installed_plugins.json"
            state.write_text(json.dumps({"plugins": {
                "dma-insights@zennify-dma": [{
                    "scope": "user", "version": "1.20.0",
                    "installPath": str(self.tmp / "cache" / "1.20.0"),
                    "installedAt": "2026-10-06T07:47:54Z"}]}}))
            return pv.installed(state)

    def test_the_interac_round_trip_reads_loaded_not_updated(self):
        def round_trip():
            _git(self.repo, "checkout", "-q", self.old)
            _git(self.repo, "checkout", "-q", self.new)
        inst = self._installed_after(round_trip)
        self.assertTrue(inst["in_place"], inst)
        self.assertTrue(inst["loaded_by_this_session"], inst)
        self.assertTrue(inst["round_trip"])

    def test_a_real_change_is_still_updated_mid_session_and_named(self):
        def real():
            (self.plug / "agents" / "a.md").write_text("a third body")
        inst = self._installed_after(real)
        self.assertIs(inst["loaded_by_this_session"], False)
        self.assertEqual(inst["moved"], ["agents/a.md"])

    def test_the_fingerprint_is_taken_once_per_session(self):
        """The hook also fires on compaction; a re-record after the tree
        moved must not launder the move into the 'bound' fingerprint."""
        bound_dir = self.tmp / "bound"
        with mock.patch.dict(os.environ, {"CLAUDE_PID": "4242"}), \
             mock.patch.object(pv, "BOUND_DIR", bound_dir), \
             mock.patch.object(pv, "session_started_at", return_value=1000.0):
            with mock.patch("time.time", return_value=1000.5):
                pv.record_bound_root(str(self.plug), pid="4242")
            first = json.loads((bound_dir / "bound_plugin-4242.json").read_text())
            (self.plug / "agents" / "a.md").write_text("moved")
            with mock.patch("time.time", return_value=2000.0):
                pv.record_bound_root(str(self.plug), pid="4242")
            second = json.loads((bound_dir / "bound_plugin-4242.json").read_text())
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(pv.moved_components(self.plug, second["fingerprint"]),
                         ["agents/a.md"])


# ── 3 · the stale ref is fast-forwarded before anyone checks it out ────────

class StaleRef(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.origin = _repo(self.tmp)
        self.c1 = _commit(self.origin, "1.0.0", "one", "c1")
        _git(self.tmp, "clone", "-q", str(self.origin), str(self.tmp / "clone"))
        self.clone = self.tmp / "clone"
        _git(self.clone, "config", "user.email", "t@t")
        _git(self.clone, "config", "user.name", "t")
        # the session's own branch, at the tip, checked out
        for i in range(3):
            self.tip = _commit(self.origin, f"1.0.{i + 1}", f"b{i}", f"c{i}")
        _git(self.clone, "fetch", "-q", "origin")
        _git(self.clone, "checkout", "-q", "-b", "ccr-session", "origin/main")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_stale_default_ref_is_fast_forwarded_without_the_worktree(self):
        head_before = _git(self.clone, "rev-parse", "HEAD")
        mtimes = {p: p.stat().st_mtime_ns for p in self.clone.rglob("*.md")}
        out = git_refs.freshen(self.clone, "main")
        self.assertEqual(out["action"], "fast_forwarded", out)
        self.assertEqual(out["behind"], 3)
        self.assertEqual(_git(self.clone, "rev-parse", "main"), self.tip)
        self.assertEqual(_git(self.clone, "rev-parse", "HEAD"), head_before)
        self.assertEqual(mtimes, {p: p.stat().st_mtime_ns
                                  for p in self.clone.rglob("*.md")})
        # and the checkout the Interac session ran now rewrites nothing
        _git(self.clone, "checkout", "-q", "main")
        self.assertEqual(mtimes, {p: p.stat().st_mtime_ns
                                  for p in self.clone.rglob("*.md")})

    def test_the_checked_out_branch_is_never_moved(self):
        _git(self.clone, "checkout", "-q", "main")
        out = git_refs.freshen(self.clone, "main")
        self.assertEqual(out["action"], "skipped")
        self.assertEqual(_git(self.clone, "rev-parse", "main"), self.c1)

    def test_a_ref_holding_somebodys_work_is_left_alone(self):
        _git(self.clone, "checkout", "-q", "main")
        _commit(self.clone, "local", "mine", "local work")
        mine = _git(self.clone, "rev-parse", "main")
        _git(self.clone, "checkout", "-q", "ccr-session")
        out = git_refs.freshen(self.clone, "main")
        self.assertEqual(out["action"], "diverged")
        self.assertEqual(_git(self.clone, "rev-parse", "main"), mine)

    def test_running_it_twice_is_a_no_op(self):
        git_refs.freshen(self.clone, "main")
        self.assertEqual(git_refs.freshen(self.clone, "main")["action"],
                         "current")

    def test_an_unreachable_origin_fails_open(self):
        _git(self.clone, "remote", "set-url", "origin", str(self.tmp / "gone"))
        out = git_refs.freshen(self.clone, "main")
        self.assertEqual(out["action"], "fetch_failed")
        self.assertEqual(_git(self.clone, "rev-parse", "main"), self.c1)

    def test_the_branch_is_the_harness_base_ref_else_the_bootstrap_default(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_BASE_REF": "refs/heads/x"}):
            self.assertEqual(git_refs.default_branch(), "x")
        env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDE_CODE_BASE_REF", "DMA_REPO_BRANCH")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(git_refs.default_branch(),
                             "claude/dma-insights-onboarding-0ryrd0")

    def test_only_a_real_session_start_spawns_the_freshener(self):
        sys.path.insert(0, str(HERE.parent / "hooks"))
        import session_brief
        with mock.patch.object(git_refs, "spawn") as sp:
            session_brief.freshen_refs({})                     # doctor's probe
            session_brief.freshen_refs({"hook_event_name": "PostCompact"})
            session_brief.freshen_refs({"hook_event_name": "SessionStart",
                                        "agent_type": "x"})
            sp.assert_not_called()
            session_brief.freshen_refs({"hook_event_name": "SessionStart"})
            sp.assert_called_once()

    def test_spawn_is_off_under_the_opt_out(self):
        with mock.patch.dict(os.environ, {"DMA_FRESHEN_REFS": "0"}):
            self.assertFalse(git_refs.spawn(self.clone))


if __name__ == "__main__":
    unittest.main()
