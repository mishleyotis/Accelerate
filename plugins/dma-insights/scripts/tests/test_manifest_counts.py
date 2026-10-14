"""The install ads' counts are derived, never typed (Interac, 2026-10-10).

plugin.json said 35 tools against 36 registered, marketplace.json said 34
tools and 74 agents against 76 — and the doctor failed every DMA session's
preflight on it. These tests are the CI half: a PR that adds a tool or an
agent without `manifest_counts.py --write` fails here, at review time.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import manifest_counts  # noqa: E402

REPO = HERE.parents[3]


class TheCheckoutIsInSync(unittest.TestCase):
    def test_no_drift_between_the_ads_and_their_sources(self):
        out = manifest_counts.drift(REPO)
        self.assertEqual(out["problems"], [], "run: python3 plugins/"
                         "dma-insights/scripts/manifest_counts.py --write")

    def test_the_server_registers_tools_the_regex_can_see(self):
        tools = manifest_counts.server_tools(REPO)
        self.assertIsNotNone(tools)
        self.assertGreater(len(tools), 20)
        self.assertEqual(len(tools), len(set(tools)))
        for name in ("promote_run", "submit_page_payload", "claim_run"):
            self.assertIn(name, tools)

    def test_the_count_matches_the_decorators(self):
        src = (REPO / "apps" / "mcp" / "server.py").read_text()
        self.assertEqual(len(manifest_counts.server_tools(REPO)),
                         src.count("\n@mcp.tool("))


class DriftIsCaughtAndHealed(unittest.TestCase):
    """Fault injection on a copy: add a tool, add an agent, split the ads."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for rel in ("apps/mcp/server.py",
                    "plugins/dma-insights/.claude-plugin/plugin.json",
                    ".claude-plugin/marketplace.json"):
            dst = self.tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, dst)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _p(self, rel):
        return self.tmp / rel

    def test_a_new_tool_is_drift_until_written(self):
        srv = self._p("apps/mcp/server.py")
        srv.write_text(srv.read_text() + "\n\n@mcp.tool()\n@_traced\n"
                       "async def brand_new_tool(x: str) -> dict:\n"
                       "    return {}\n")
        out = manifest_counts.drift(self.tmp)
        self.assertTrue(any("tools" in p for p in out["problems"]), out)
        healed = manifest_counts.write(self.tmp)
        self.assertEqual(healed["problems"], [])
        self.assertIn(f"({healed['want']['tools']} tools)", json.loads(
            self._p("plugins/dma-insights/.claude-plugin/plugin.json")
            .read_text())["description"])

    def test_a_new_agent_is_drift_until_written(self):
        mp = self._p("plugins/dma-insights/.claude-plugin/plugin.json")
        m = json.loads(mp.read_text())
        m["agents"].append("./agents/new-thing.md")
        mp.write_text(json.dumps(m, indent=2) + "\n")
        self.assertTrue(manifest_counts.drift(self.tmp)["problems"])
        healed = manifest_counts.write(self.tmp)
        self.assertEqual(healed["problems"], [])
        self.assertEqual(healed["have"]["agents"], len(m["agents"]))

    def test_a_split_marketplace_ad_is_drift_and_heals_to_one_ad(self):
        mk = self._p(".claude-plugin/marketplace.json")
        market = json.loads(mk.read_text())
        market["plugins"][0]["description"] = "old (34 tools), 74 DMA agents"
        mk.write_text(json.dumps(market, indent=2) + "\n")
        self.assertTrue(manifest_counts.drift(self.tmp)["problems"])
        manifest_counts.write(self.tmp)
        plugin = json.loads(self._p(
            "plugins/dma-insights/.claude-plugin/plugin.json").read_text())
        market = json.loads(mk.read_text())
        self.assertEqual(market["plugins"][0]["description"],
                         plugin["description"])

    def test_write_is_idempotent(self):
        manifest_counts.write(self.tmp)
        before = [self._p(r).read_bytes() for r in (
            "plugins/dma-insights/.claude-plugin/plugin.json",
            ".claude-plugin/marketplace.json")]
        manifest_counts.write(self.tmp)
        after = [self._p(r).read_bytes() for r in (
            "plugins/dma-insights/.claude-plugin/plugin.json",
            ".claude-plugin/marketplace.json")]
        self.assertEqual(before, after)

    def test_a_tree_without_the_connector_source_is_not_drift(self):
        (self.tmp / "apps/mcp/server.py").unlink()
        out = manifest_counts.drift(self.tmp)
        self.assertIsNone(out["want"]["tools"])
        self.assertFalse(any("tools" in p for p in out["problems"]))


if __name__ == "__main__":
    unittest.main()
